# 08 — CyberBoss 固定来源代码变更地图

> 目的：让 Codex/Claude Code 不需要重新遍历整个来源包才知道改哪里。
> Stage 0 先用 pinned commit 校验并导入固定本地 source bundle；之后所有路径
> 都以本地 bundle 为准，不保留 upstream remote、submodule、`#main` dependency、
> 自动同步或运行时下载。

## 1. 改造原则

```text
保留协议与功能内核
→ 在边界增加durability/identity/security/operations
→ 通过adapter和feature flag切换
→ 不把云部署逻辑散落到业务代码
→ 不重写Timeline
```

所有变更必须分成可回滚小提交；P0可靠性补丁不得与UI美化混在同一提交。

## 2. P0 文件级地图

| Historical Source Path | 当前职责 | 目标改造 | 关键测试 |
|---|---|---|---|
| `src/adapters/channel/weixin/index.js` | long poll、sync buffer、sendmessage、chunk | poll返回`messages + candidateCursor`；不在adapter内部先提交cursor；send通过provider contract返回receipt/unknown outcome | crash-cut、duplicate update、send fault |
| `src/core/app.js` | 命令、消息处理、线程、approval、queue、`/bind` | 接入DurableInbox/JobScheduler/DurableOutbox；删除in-memory作为唯一队列；`/bind`只接受alias；状态与delivery分离 | E2E、state machine、workspace、cancel |
| `src/adapters/runtime/codex/index.js` | initialize、thread/turn、model、Runtime event | 加入RuntimeSupervisor contract、error taxonomy、ready/auth、correlation、cancel、false-success guard | app-server simulator、crash、overload |
| `src/adapters/runtime/codex/rpc-client.js` | WebSocket JSON-RPC | loopback allowlist、bounded pending calls、reconnect、duplicate/late response、abort、metrics | RPC contract/reconnect |
| `scripts/shared-start.js` | 启动shared app-server与bridge | 改为systemd可管理entrypoint；不daemonize；child同cgroup；singleton；signal/exit传播 | process tree、100 restart race |
| `src/integrations/timeline/` | Timeline工具与服务 | canonical source adapter、redaction、build/search/status；cache可重建 | clean rebuild/search/DLP |
| `src/core/config.js`或等价 | env、state/workspace配置 | cloud paths、provider/simulator、resource profile、credential file refs、feature flags、alias schema | config validation/secret negative |
| `package.json` / lockfile | scripts/deps/Node engine | 增加cloud start、migrate、status、backup、restore、validate:no-wait；依赖最小化 | npm scripts/lockfile audit |
| `src/core/config.js` + persona/instruction templates | user identity defaults | 支持 `CYBERBOSS_USER_GENDER=neutral`，不得把未声明性别默认为女性或男性 | config/template unit test |
| `test/` | 现有Codex/Timeline/stream tests | 复用并新增durable、fault、simulator、no-wait、security suites | Pipeline A/B |

## 3. Durable Channel Contract

### 3.1 现状风险

当前WeChat adapter内部获取updates后保存新sync buffer，然后上层再处理消息。该顺序无法证明：

```text
cursor已前进 ⇒ 对应message已进入durable inbox
```

### 3.2 目标接口

建议职责接口（名称可适配上游风格）：

```ts
type PolledBatch = {
  accountId: string;
  messages: NormalizedInbound[];
  candidateCursor: string | null;
  providerBatchId?: string;
};

interface ChannelProvider {
  poll(signal?: AbortSignal): Promise<PolledBatch>;
  commitCursor(candidateCursor: string): Promise<void>;
  send(message: OutboundMessage): Promise<DeliveryAttempt>;
}
```

核心流程：

```ts
const batch = await channel.poll(signal);
const durable = await inbox.ingestBatch(batch.messages);
await channel.commitCursor(batch.candidateCursor);
await outbox.ensureAcceptedReceipts(durable.jobs);
```

必须处理：

- batch中部分message重复；
- cursor commit失败；
- commit成功后process crash；
- provider重新投递；
-空batch；
- source ID缺失时稳定派生，不使用随机ID导致重复。

### 3.3 兼容迁移

- Feature flag：`CB_DURABLE_INBOX=true`；
- 旧adapter包装成provider；
- 先在simulator验证；
- 禁止同时运行旧poll loop和新poll loop；
- migration完成后删除“adapter自行推进cursor”的路径。

## 4. Runtime Spool与状态机

新增建议模块：

```text
src/services/db/
  database-adapter.js
  migrations.js
src/services/inbox/durable-inbox.js
src/services/jobs/job-store.js
src/services/jobs/job-state-machine.js
src/services/jobs/scheduler.js
src/services/outbox/durable-outbox.js
src/services/canonical/canonical-sync.js
src/services/status/status-exporter.js
src/services/runtime/runtime-supervisor.js
src/services/clock/clock.js
```

不要求精确沿用目录名，但职责必须隔离。

### 4.1 数据库边界

- 事务入口集中，业务层不能散落raw SQL；
- `node:sqlite`与备用driver通过同一adapter；
- WAL、foreign keys、busy timeout、integrity check启动时验证；
- `source_message_id`、`outbox_key`、`canonical_event_id`唯一；
- payload正文默认只在active encrypted/ephemeral区，普通event存hash/摘要；
- migration additive；
- online backup不用直接复制活跃db文件。

### 4.2 Scheduler

```text
queued
→ resource/workspace/runtime predicates
→ acquire global lease
→ running
→ result/approval/cancel/error
→ durable outbox
→ canonical_pending
```

- active lease=1；
- FIFO为默认；
- mutation job crash后不能盲重放；
- read-only/idempotent job可按policy重试；
- job expiry测试使用fake clock；
- queue protect按条数/字节/资源，不按开发等待。

## 5. Durable Outbox

### 5.1 状态

```text
pending → sending → delivered
              └→ retry
              └→ failed_terminal
```

### 5.2 Unknown Outcome

Provider call可能已经送达但响应丢失。实现必须：

- stable outbox key；
- provider receipt/context；
- retry前查询/去重能力若provider支持；
- 不支持时采用用户可见dedupe marker/chunk sequence和最保守策略；
- “Runtime succeeded”与“微信 delivered”分别显示；
- 模拟100组unknown outcome。

## 6. `/bind`与Workspace

当前命令使用绝对路径。目标：

```text
/bind cyberboss
```

配置：

```json
{
  "cyberboss": {
    "path": "/srv/cyberboss-workspaces/cyberboss",
    "repo": "LinzeColin/MetaDatabase",
    "project_subpath": "CyberBoss",
    "write_globs": ["CyberBoss/**"],
    "mode": "mutating",
    "max_bytes": 8589934592
  }
}
```

校验：

- alias regex；
- configured key；
- `realpath`在workspace root；
- symlink/submodule escape；
- sensitive path deny；
- Git状态/checkpoint；
- 不把绝对路径回显到微信/status。

## 7. Codex Runtime Supervisor

### 7.1 Process

- systemd启动主entrypoint；
- Codex child与bridge同cgroup；
- App Server loopback；
- startup检查ready predicate；
- signal传播；
- child crash分类并重启；
- pending RPC有上限；
- 不在代码中后台daemonize。

### 7.2 Error Taxonomy

```text
AUTH_INVALID
APP_SERVER_NOT_READY
SERVER_OVERLOADED
TRANSPORT_RESET
TURN_CANCELLED
TURN_FAILED_RETRYABLE
TURN_FAILED_TERMINAL
APPROVAL_REQUIRED
UNKNOWN_OUTCOME
```

每类定义：job transition、retry policy、user message、status severity、evidence。不允许所有异常都变成generic failed。

### 7.3 Simulator First

真实device auth未完成时：

```text
CB_RUNTIME_PROVIDER=simulator
```

同一supervisor contract跑成功、进度、approval、cancel、crash、overload和false-success。切换真实Codex只改provider/config，不改状态机。

## 8. Timeline与搜索

### 8.1 保留

- 固定本地 bundle 的 `src/integrations/timeline/`；
- `cyberboss_timeline_write/build/serve/dev/screenshot`；
-现有Timeline integration/service tests。

### 8.2 新增

- `CanonicalTimelineSource`通过 Private-Database client get/list/verify 后从
  本地有界 canonical cache 读取；
- redaction在write前；
- build output进入可重建cache；
- search index只含日期/category/workspace alias/job ID/脱敏摘要；
- build失败保留上一good build；
- `cyberboss.linzezhang.com/timeline/`经Access；
- status输出last write/build/hash/entry count。

### 8.3 不新增

- 第二套timeline数据库；
- Elasticsearch/Meilisearch；
- 常驻Chromium；
- 为截图功能长期运行浏览器。

## 9. Canonical Sync

逻辑批次内容（物理存储由 Private-MetaDatabase 内容寻址对象和 manifest 管理）：

```text
events-<partition>.ndjson.zst
timeline-<partition>.tar.zst
status-<snapshot-id>.json
release-<version>.json
```

实现：

- stable event ID/hash；
- batch by count/bytes；
- terminal/high-risk explicit flush；
- `private_db_client.py ingest Private-MetaDatabase <batch> --domain CyberBoss`；
- manifest 409 时 refetch/retry，并按 event ID set 验证；
- same ID/different hash隔离为integrity incident；
- 403/429尊重provider hint；
- no clone/fetch/rebase/push Private-Database；
- Private-Database client identity与code repo credential分离；
- SQLite `sync_spool`保存未同步event；
- Private-Database API恢复后reconcile/verify。

## 10. Status接入

新增本机安全snapshot：

```text
/run/cyberboss/status.json
```

写法：temp file → fsync/close → atomic rename。字段至少：

- version/commit/release/profile；
- process/poll/send/runtime/E2E；
- active/queued/outbox/sync counts；
- Timeline write/build；
- Private-Database/GitHub-final-publication/R2/OCI activation/health；
- CPU/RAM/load/disk/inode/swap；
- last self-heal/backup/restore/rollback；
- generated_at/generation_id。

禁止：prompt、result、微信ID、thread ID、token、绝对路径、私人文件名。

现有`status.linzezhang.com`只需adapter读取该contract；不得部署第二套全局Status。

## 11. systemd / Release改造

### 11.1 Unit

- dedicated user；
- `KillMode=control-group`；
- `Restart=on-failure`；
- bounded start limit；
- `NoNewPrivileges=true`；
- `ProtectSystem=strict`和必要WritablePaths；
- MemoryHigh/Max由preflight生成drop-in；
- EnvironmentFile引用secret slots；
- ExecStart不含shell插值secret。

### 11.2 Release

```text
releases/<commit>
current -> releases/<commit>
previous -> releases/<previous>
```

- deploy创建新目录；
- offline checks；
- predicate health；
- atomic symlink；
- request-countCanary；
- failure立即rollback；
- 不用固定sleep；
- 数据schema additive。

## 12. 测试落点

建议新增：

```text
test/weixin-durable-cursor.test.js
test/inbox-idempotency.test.js
test/outbox-unknown-outcome.test.js
test/job-state-machine.test.js
test/workspace-alias-security.test.js
test/runtime-simulator.test.js
test/runtime-supervisor-crash.test.js
test/canonical-sync-conflict.test.js
test/timeline-canonical-rebuild.test.js
test/status-contract-dlp.test.js
test/backup-restore-reconcile.test.js
test/no-wait-release.test.js
```

复用：

- `codex-reconnect.test.js`；
- `codex-rpc-client.test.js`；
- `codex-approval.test.js`；
- `stream-delivery.test.js`；
- `system-inbound.test.js`；
- `timeline-integration.test.js`；
- `timeline-service.test.js`。

## 13. 推荐提交序列

1. `chore: pin fixed source bundle and cloud config boundary`
2. `test: add channel and runtime simulators`
3. `feat: add sqlite spool and job state machine`
4. `fix: persist inbox before weixin cursor commit`
5. `feat: add durable outbox and delivery state`
6. `feat: add workspace aliases and runtime supervisor`
7. `feat: add private-metadatabase canonical sync`
8. `feat: adapt timeline/search/status`
9. `ops: add systemd resource profiles and release slots`
10. `ops: add r2/oci backup and restore reconcile`
11. `test: add accelerated fault/model/security pipelines`
12. `release: request-count canary and handover`

每个提交必须独立测试、可review、可revert；不要一个巨型“cloud rewrite”提交。
