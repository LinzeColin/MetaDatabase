# Run Contract — P2.4 / CB-230 Durable Outbox and Delivery Truth

## 1. Goal

本 Run 只执行 Task DAG 节点 `P2.4 / CB-230`：

> Implement durable outbox, retries, reply dedupe and process recovery.

以已通过的 `P2.3 / CB-220` closure
`916651854a6402254724c885398060b2e267e496` 为冻结输入，在 schema v3、
durable inbox 与 singleton Runtime scheduler 之上交付：

- accepted、final result、terminal error/cancelled reply 在 provider 调用前
  进入 encrypted SQLite outbox；
- deterministic chunk sequence、stable outbox dedupe key 与 stable provider
  client ID；
- 最多 5 次、bounded jittered exponential retry，全部时间与随机源可注入；
- provider 明确确认后才写 `confirmed`，全部 final chunks 确认后才把 job
  标为 `replied`；
- restart 对 pending、安全的 pre-dispatch claim 和 ambiguous
  post-dispatch claim 进行不同恢复，ambiguous 绝不自动重发；
- 401/invalid-context 等 terminal failure 保留可见状态，并在 fixture
  存在新的已知 context 时发送脱敏、可操作的 re-login 建议。

本 Run 不执行 `CB-240` 或 `PG-2`，不调用 Private-MetaDatabase，不激活真实
WeChat/Codex/Cloudflare/OCI，不切目标机 `current` 或 service，不创建新 repo，
不 push，不创建 PR/tag/release。

## 2. Authoritative scope

- Task：`04_TASK_DAG_EXECUTION_PACK.yaml / CB-230`；
- dependencies：`CB-210`、`CB-220`，均已 `passed`；
- Acceptance：
  - `AC-020`：send 前 kill/crash 时 outbox row 已存在，重启后可继续；
  - `AC-021`：虚拟时钟下 503、503、200，退避序列正确、attempts=3、
    无真实等待；
  - `AC-022`：同一 outbox key 重放 1,000 次，confirmed delivery count=1；
  - `AC-024`：401/invalid context 进入 `failed_terminal`；用户只收到脱敏、
    可操作的 re-login 建议；
  - `AC-025`：3×单消息上限结果被 deterministic chunk；index/total 连续，
    重建 SHA-256 与原文相同；
  - `AC-062`：pending/pre-dispatch/post-dispatch/confirmation-commit 故障矩阵
    由状态 predicate 驱动恢复，无固定 sleep、不假绿；
- invariants：
  - provider 调用前必须存在 committed outbox row；
  - `replied` 只能由全部 required final chunks 的 confirmed receipt 推导；
  - 对没有 provider idempotency 保证的 post-dispatch unknown outcome，
    自动重发次数必须为 0；
  - DB/event/evidence 不含 secret、context token、完整私人 reply、原始用户
    ID 或目标地址；
- release artifact：
  `/opt/cyberboss-cloud/releases/<implementation-commit>/evidence/outbox-recovery-matrix.json`。

## 3. Minimum implementation

### 3.1 Additive durable schema and repository

- 新 migration 只能 add column/table/index/trigger，不 drop/rename/vacuum
  既有对象；v1 reader 继续可读既有列；
- outbox row 至少保存 stable dedupe key、chunk index/count、encrypted
  payload/target、payload hash、attempt/max/next-attempt、claim/dispatch、
  confirmation/receipt 与 terminal error；
- attempt ledger append-only，记录 started、retry、confirmed、
  failed-terminal 或 ambiguous，不保存 payload/target；
- `BEGIN IMMEDIATE` claim 串行选择 due row；owner/lease 不匹配时不能
  confirm、retry 或 terminal；
- 相同 dedupe key + 相同 job/payload/chunk 是 idempotent；任一字段冲突
  fail closed；
- active payload/target 继续 AES-256-GCM 与 TTL redaction，key 不写
  DB/log/evidence/artifact。

### 3.2 Stable chunk and provider transport

- 对最终文本先规范化，再按 Unicode code point deterministic 分块；
- 每段包含稳定可解析的 `index/total` header，单段不超过配置上限；
- dedupe key 与 provider client ID 从 job/logical-message/chunk/payload hash
  稳定派生，不使用随机 UUID；
- outbox worker 只能调用 single-chunk provider API；旧 direct multi-chunk
  helper 不得承载 durable delivery；
- provider transport 必须返回结构化确认；void、异常、非零 ret/errcode
  或错误 HTTP 不能标记 confirmed。

### 3.3 Retry, failure and confirmation truth

- retryable 仅限明确响应的 408/425/429/5xx、provider overload 或明确
  transient code；
- 401/403/session/context invalid 为 terminal；
- timeout、connection reset、invalid response 等 provider 是否已收件
  不可证明的情况为 `ambiguous_send_outcome`，禁止自动重发；
- backoff 为 bounded exponential + jitter，默认最多 5 attempts，支持
  provider retry hint、injectable clock/random/timer；
- provider receipt 归一化后 hash 保存；raw response 不进入普通日志；
- final outbox confirmed 之前 job 最多到 `reply_pending`；全部 final
  chunks confirmed 才能 `replied`；terminal/ambiguous final delivery
  推导 `reply_failed`；
- terminal advice 使用固定脱敏文本；只有刷新后的有效 context 与独立
  outbox key 才发送，不能把 provider 错误正文转发给用户。

### 3.4 Restart recovery and App wiring

- accepted ack 在 cursor commit 前 staged；duplicate inbound replay 只得到
  同一 accepted outbox rows；
- durable Runtime target 绑定 job ID；result/error/cancelled delivery 只能走
  outbox worker；
- startup exclusive recovery：
  - `pending` 保持 due；
  - `sending` 且 dispatch 未开始 → safe retry；
  - `sending` 且 dispatch 已开始、无 confirmation commit →
    ambiguous terminal/manual reconcile，绝不自动重发；
  - `confirmed` 保持 immutable success；
- worker start/stop 与 App lifecycle 绑定；next-due 使用 predicate/timer，
  验收使用虚拟 clock，不等待真实退避；
- 本 Run 不把 command/help/typing/media 等所有旧 surface 泛化改造为 durable
  消息总线；只覆盖 Task 明列的 accepted/final/error/cancelled job reply。

## 4. Explicit phase boundary

- `CB-240` 才实现 canonical sync、Private-MetaDatabase ingest/reconcile 与
  Timeline source；
- `CB-340` 才完成全服务 self-heal/status/retention operational loop；
- `PG-2` 必须等 CB-200–CB-240 全部通过后独立执行；
- provider 无端到端查询/幂等合同，因此 ambiguous row 本 Run 只能
  fail closed + manual reconcile，不能声称 exactly-once provider delivery；
- candidate-only target acceptance 不 enable/start service，不注入真实
  credential，不修改 canonical runtime DB。

## 5. Allowed repository modifications

- `CyberBoss/app/migrations/004_cb230_durable_outbox.sql`
- `CyberBoss/app/package.json`
- `CyberBoss/app/scripts/durable-outbox-acceptance.js`
- `CyberBoss/app/src/adapters/channel/weixin/api.js`
- `CyberBoss/app/src/adapters/channel/weixin/index.js`
- `CyberBoss/app/src/core/app.js`
- `CyberBoss/app/src/core/config.js`
- `CyberBoss/app/src/core/stream-delivery.js`
- `CyberBoss/app/src/services/db/database-adapter.js`
- `CyberBoss/app/src/services/inbox/durable-inbox.js`
- `CyberBoss/app/src/services/jobs/job-scheduler.js`
- `CyberBoss/app/src/services/outbox/durable-outbox.js`
- `CyberBoss/app/test/durable-inbox-crash-cut.test.js`
- `CyberBoss/app/test/durable-outbox-crash-cut.test.js`
- `CyberBoss/app/test/runtime-spool.test.js`
- `CyberBoss/app/test/stream-delivery.test.js`
- `CyberBoss/app/test/turn-gate-store.test.js`
- `CyberBoss/app/test/weixin-outbox-transport.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P2_4_CB_230.md`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-outbox.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-durable-outbox-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-durable-outbox.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js`
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb230.py`
- `CyberBoss/tests/durable-outbox.test.js`
- `CyberBoss/docs/evidence/CB-230/**`
- closure 时的 `CyberBoss/machine/facts/task_state.json`、
  `CyberBoss/README.md`、`CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`

其他路径不得修改。尤其冻结 `CyberBoss/vendor/**`、CB-000–CB-220 与
PG-0/PG-1 evidence、Task DAG、PRD、Architecture、Roadmap、source lock、
许可证与母仓其他项目。

## 6. Local validation

```bash
node --test CyberBoss/app/test/durable-outbox-crash-cut.test.js
node --test CyberBoss/app/test/stream-delivery.test.js
node --test CyberBoss/app/test/weixin-outbox-transport.test.js
node --test CyberBoss/tests/durable-outbox.test.js
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb230.py --prepare
python3 CyberBoss/scripts/validate_prestage0.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
```

专项测试必须真实执行：

- accepted/final/error staged-before-send crash cuts；
- virtual 503→503→200，attempts=3、bounded backoff、真实等待次数=0；
- 同一 outbox key stage/replay 1,000 次，provider confirmed count=1；
- 401/invalid-context terminal + refreshed-context actionable advice receipt；
- 3× limit result，chunk index/count 连续且 reconstruction hash 相同；
- pending、claimed-before-dispatch、dispatch-started-before-confirm、
  confirmed-after-restart matrix；
- stale owner fencing、void response/伪 receipt 拒绝、payload/target
  encryption与证据 DLP；
- 全量 App regression、无真实 provider/Runtime/private database call。

## 7. Authorized target sequence

1. 从受保护本地部署记录解析既有授权目标并匹配
   `target_id_sha256=7865f743d174`；地址不输出、不落库；
2. fresh read-only preflight：service disabled/inactive、process/listener/
   incoming=0、canonical `runtime.db` 不存在、CB-230 candidate/staging
   无冲突、`current`/workspace 保持冻结值；
3. builder 只能从 clean exact implementation commit 生成 complete
   Corresponding Source、manifest、checksums 与 outbox recovery matrix；
4. installer/acceptance `--check` 必须证明 persistent writes/live
   commands/provider calls=false；
5. exact artifact set 进入
   `/var/lib/cyberboss/incoming/cb230-<commit>`；
6. 两次 `--apply` 与一次 `--verify`：candidate immutable，第二次幂等，
   不切 `current`、不 enable/start service；
7. 只在 `/var/lib/cyberboss/cb230-staging` 和独立 synthetic runtime root
   使用 ephemeral keys/state、provider fixture 与 virtual clock；
8. 导出脱敏 outbox fault、provider receipt、retry、chunk/restart evidence；
9. 删除 CB-230 staging/env/incoming、synthetic runtime root 与 keys，保留
   inactive candidate；
10. 最终确认 service disabled/inactive、process/listener=0、canonical
    `runtime.db` 仍不存在、`current`/workspace 不变。

## 8. Risks, rollback and stop conditions

- **Duplicate visible result：** 同一 dedupe key/provider client ID 出现第二
  次 visible confirmation，立即停止；
- **False confirmation：** void/throw/nonzero/ambiguous response 可进入
  confirmed，或 job 在所有 final chunks confirmed 前进入 replied，立即停止；
- **Unsafe recovery：** dispatch-started unknown outcome 被 retry，立即停止；
- **Retry drift：** 超过 max attempts、使用真实 sleep、无界 delay/jitter，
  立即停止；
- **Chunk corruption：** index/total 不连续或 reconstruction hash 不同，
  立即停止；
- **Privacy leak：** context token、provider body、完整私人 reply、原始用户
  ID 进入普通日志/evidence，立即停止；
- **Rollback：**关闭 outbox dispatch，保留全部 pending/retry/terminal rows
  供人工恢复；目标机只删除 exact CB-230 staging/env/incoming/synthetic
  runtime，`current`、workspace、历史 candidate 与业务数据不参与回滚。

## 9. Completion rule

只有 `AC-020`、`AC-021`、`AC-022`、`AC-024`、`AC-025`、`AC-062` 的全部
executable evidence、本地完整回归、exact-commit target candidate
install/acceptance 和最终清理都通过，才能把 `CB-230` 标为 `passed`。

`CB-240`–`CB-540` 与 `PG-2`–`PG-5` 保持 `not_started`。本 Run 不 push，
不创建 PR/tag/release；strict
`AGPL-3.0-only AND GPL-3.0-only`、原源码/许可证/冲突记录和
`upstream_clarification_received=false` 必须保持。
