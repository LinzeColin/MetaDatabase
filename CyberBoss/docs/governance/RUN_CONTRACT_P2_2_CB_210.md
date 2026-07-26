# Run Contract — P2.2 / CB-210 Durable Inbox Before Cursor

## 1. Goal

本 Run 只执行 Task DAG 节点 `P2.2 / CB-210`：

> Make durable inbox precede WeChat cursor commit and enforce idempotency.

以已通过的 `P2.1 / CB-200` closure
`4f914e3b6ed3145a16c1572f4176068b9829b920` 为冻结输入，交付
candidate-cursor API、durable inbox coordinator、cursor continuity guard、
1,000 次 source replay 幂等和 fetch/durable/cursor 三类受控 crash
recovery。

本 Run 不执行 `CB-220`、`CB-230`、`CB-240` 或 `PG-2`，不激活真实
WeChat/Runtime/Private-MetaDatabase，不切目标机 `current` 或 service，
不创建新 repo，不发布 GitHub。

## 2. Authoritative scope

- Task：`04_TASK_DAG_EXECUTION_PACK.yaml / CB-210`；
- Acceptance：
  - `AC-004`：inbox/cursor 每个可观测切点 crash，重启后消息不丢且
    synthetic execution counter 恰为 1；
  - `AC-023`：同一 source ID 重放 1,000 次，只有一个 inbox、一个 job、
    一次 synthetic execution；
  - `AC-063`：事务切点 crash 后 committed inbox RPO 0，并保留 CB-200
    mock canonical outage/recovery `set_diff=0` 能力；
- Invariants：
  - `INV-001`：一个 source message 最多对应一个 executable job；
  - `INV-002`：cursor 不得越过最高连续 durable message；
- cut points：`after_fetch_before_durable`、
  `after_durable_before_cursor`、`after_cursor`；
- planned modules：
  `app/src/adapters/channel/weixin/index.js`、
  `app/src/adapters/channel/weixin/sync-buffer-store.js`、
  `app/src/services/inbox/durable-inbox.js`；
- planned tests：
  `app/test/durable-inbox-crash-cut.test.js`、
  `app/test/weixin-cursor-commit.test.js`；
- release artifact：
  `/opt/cyberboss-cloud/releases/<implementation-commit>/evidence/durable-inbox-matrix.json`。

## 3. Minimum implementation

- `getUpdates` 被拆为只返回 raw messages 与 candidate cursor 的 fetch；
  fetch 本身不得写 cursor 或 context-token state；
- cursor commit 是显式 API：
  - safe path、无 symlink、目录 `0700`、文件 `0600`；
  - compare-and-set 防 stale writer；
  - numeric cursor 拒绝 regression；
  - temp write、file fsync、atomic rename、directory fsync；
- durable coordinator：
  - 对 user messages 形成稳定 source identity；优先 provider
    `message_id`，缺失时只接受可验证稳定的 provider fallback，否则
    fail closed；
  - deterministic ordering；
  - numeric cursor fixture 必须满足
    `committed+1 ... candidate` 唯一连续；gap、duplicate sequence、
    regression 全部拒绝且不提交 cursor；
  - opaque cursor 只有在该 response 的全部可处理 user message 已 durable
    后才提交；
  - normalized payload/context 进入 CB-200 AES-256-GCM spool；同一 source
    replay 返回 existing job，禁止第二个 executable job；
  - policy-rejected message 仍写 durable rejected inbox，但不创建 job；
  - cursor 只在整个 batch durable 后推进；
- App 默认 `CB_DURABLE_INBOX=true`，缺少 runtime DB 或 owner-only
  32-byte key files 时 fail closed；仅 staging 可显式回退 imported baseline
  flow，production activation 继续 blocked；
- 已 durable 且 queued 的 job 可由 deterministic synthetic harness 验证
  execution count；真实 scheduler/global lease/Runtime lifecycle 属于
  `CB-220`，本 Run 不声称 arbitrary Runtime crash exactly-once；
- real WeChat 与 real Runtime evidence 保持 `activation_pending`。

## 4. Explicit phase boundary

- `CB-220` 才实现 scheduler、global active lease、resource gate、real Runtime
  lifecycle 和 claim 后任意 crash recovery；本 Run 不越界；
- `CB-230` 才实现 durable outbox worker、retry、send receipt 与 confirmation；
  本 Run 不把 cursor 后 ack/send 路径声称为已完成；
- `CB-240` 才使用 no-clone Private-MetaDatabase client；本 Run 只继承
  CB-200 mock reconcile capability；
- `PG-2` 必须在 CB-200–CB-240 全部通过后的独立 Run 执行；
- candidate-only target acceptance 不 enable/start service，不注入真实
  credential，不修改 canonical runtime DB。

## 5. Allowed repository modifications

- `CyberBoss/app/package.json`
- `CyberBoss/app/scripts/durable-inbox-acceptance.js`
- `CyberBoss/app/src/adapters/channel/weixin/index.js`
- `CyberBoss/app/src/adapters/channel/weixin/message-utils.js`
- `CyberBoss/app/src/adapters/channel/weixin/sync-buffer-store.js`
- `CyberBoss/app/src/core/app.js`
- `CyberBoss/app/src/core/config.js`
- `CyberBoss/app/src/services/db/database-adapter.js`
- `CyberBoss/app/src/services/inbox/durable-inbox.js`
- `CyberBoss/app/test/cloud-walking-skeleton-live.test.js`
- `CyberBoss/app/test/durable-inbox-crash-cut.test.js`
- `CyberBoss/app/test/weixin-cursor-commit.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P2_2_CB_210.md`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-inbox.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-durable-inbox-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-durable-inbox.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js`
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb210.py`
- `CyberBoss/tests/durable-inbox.test.js`
- `CyberBoss/docs/evidence/CB-210/**`
- closure 时的 `CyberBoss/machine/facts/task_state.json`、
  `CyberBoss/README.md`、`CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`

其他路径不得修改。尤其冻结 `CyberBoss/vendor/**`、CB-000–CB-200 与
PG-0/PG-1 evidence、Task DAG、PRD、Architecture、Roadmap、source lock、
许可证与母仓其他项目。

## 6. Local validation

```bash
node --test CyberBoss/app/test/weixin-cursor-commit.test.js
node --test CyberBoss/app/test/durable-inbox-crash-cut.test.js
node --test CyberBoss/tests/durable-inbox.test.js
cd CyberBoss/app && npm run check && npm test
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-durable-inbox.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-inbox.sh
python3 CyberBoss/scripts/validate_cb210.py --prepare
python3 CyberBoss/scripts/validate_prestage0.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
```

专项测试必须真实执行：

- fetch 不提前提交 cursor/context；
- `after_fetch_before_durable`、`after_durable_before_cursor`、
  `after_cursor` 三个进程 crash/restart；
- 同一 source ID 1,000 次 replay；
- reversed multi-message batch、numeric gap、duplicate sequence、cursor
  regression property；
- inbox/job/query counts 与 synthetic execution counter；
- DB/WAL/SHM、cursor、log/evidence plaintext/secret scan；
- `integrity_check=ok` 与 inherited mock canonical recovery
  `set_diff=0`。

## 7. Authorized target sequence

1. 从受保护本地记录解析既有授权目标并匹配
   `target_id_sha256=7865f743d174`；地址不输出、不落库；
2. fresh read-only preflight：service disabled/inactive、process/listener/
   incoming=0、canonical `runtime.db` 不存在、CB-210 candidate/staging
   无冲突、`current`/workspace 保持冻结值；
3. builder 只能从 clean exact implementation commit 生成 complete
   Corresponding Source、manifest、checksums；
4. installer `--check` 必须证明 persistent writes/live commands=false；
5. 只把 exact artifact set 送入
   `/var/lib/cyberboss/incoming/cb210-<commit>`；
6. 两次 `--apply` 与一次 `--verify`：candidate immutable，第二次幂等，
   不切 `current`、不 enable/start service；
7. 只在 `/var/lib/cyberboss/cb210-staging` 和独立 synthetic runtime root
   使用 ephemeral keys/state 执行 target acceptance；
8. 导出脱敏 crash matrix、DB query、ordering/replay/execution evidence；
9. 删除 CB-210 staging/env/incoming、synthetic runtime root 与 keys，保留
   inactive candidate；
10. 最终确认 service disabled/inactive、process/listener=0、canonical
    `runtime.db` 仍不存在、`current`/workspace 不变。

## 8. Risks, rollback and stop conditions

- **Cursor loss/regression：** fetch 写 cursor、cursor 越过 undurable/gap
  message、CAS stale writer 成功或 regression 成功，立即停止；
- **Unstable identity：** provider 无稳定 message identity 时 fail closed，
  不以随机值或接收时间伪造幂等；
- **RPO/idempotency：** 任一 crash 切点 silently loses message、1,000 replay
  产生第二个 job 或 synthetic execution count 不等于 1，立即停止；
- **Privacy：** plaintext payload/context/target、key、真实 identity/secret
  出现在 DB/WAL/SHM、cursor、日志或 evidence，立即停止；
- **Scope creep：** 需要 scheduler/lease/outbox worker/real canonical adapter
  才能通过时停止，不借机做 CB-220+；
- **Rollback：** staging 可显式回退 imported baseline poll flow；production
  仍 blocked。目标机只删除 exact CB-210 staging/env/incoming/synthetic
  runtime；`current`、workspace、历史 candidate 和业务数据不参与回滚；
- **硬停止：** integrity check 失败、目标出现无法清理的
  process/listener，或必须公开 Runtime/注入真实 credential。

## 9. Completion rule

只有 AC-004、AC-023、AC-063 的全部 executable evidence、本地完整回归、
exact-commit target candidate install/acceptance 和最终清理都通过，才能把
`CB-210` 标为 `passed`。

`CB-220`–`CB-540` 与 `PG-2`–`PG-5` 保持 `not_started`。本 Run 不 push，
不创建 PR/tag/release；strict
`AGPL-3.0-only AND GPL-3.0-only`、原源码/许可证/冲突记录和
`upstream_clarification_received=false` 必须保持。
