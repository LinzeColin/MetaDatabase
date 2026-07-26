# Run Contract — P2.1 / CB-200 SQLite WAL Spool

## 1. Goal

本 Run 只执行 Task DAG 节点 `P2.1 / CB-200`：

> Implement SQLite WAL spool and strict job state machine.

以已通过的 Stage 1 / PG-1 closure
`c6f5a288aa662591c6e4e21c6294a7966d233fc6` 为冻结输入，交付可供后续
CB-210–CB-240 调用的 SQLite WAL repository/state service、严格 job 状态机、
additive migration 和 active payload 加密/TTL 清除边界。

本 Run 不执行 `CB-210`、`PG-2`、业务 service 激活、真实
Private-MetaDatabase/provider 操作或 GitHub 发布；不创建新 repo。

## 2. Authoritative scope

- Task：`04_TASK_DAG_EXECUTION_PACK.yaml / CB-200`；
- Acceptance：
  - `AC-003`：10,000 条 fixture 的 `source_message_id`、
    `correlation_id`、`job_id` 非空、稳定且无碰撞；
  - `AC-016`：状态转换 property/fuzz，所有非法转换失败；
  - `AC-055`：schema 只 additive/backward-compatible，v1 reader 可读取
    v2 schema，不依赖 destructive downgrade；
  - `AC-063`：每个事务可观测切点 crash 后 committed inbox RPO 0，
    mock canonical outage/recovery 最终 event set diff=0；
- starter schema：
  `implementation-kit/sql/runtime-spool.sql`；
- planned modules：
  `app/src/services/db/database-adapter.js`、
  `app/src/services/jobs/job-state-machine.js`；
- planned tests：
  `app/test/runtime-spool.test.js`、
  `app/test/job-state-machine.test.js`；
- release artifact：
  `/opt/cyberboss-cloud/releases/<implementation-commit>/migrations/` 与
  `schema-manifest.json`。

## 3. Minimum implementation

- 从 starter SQL 形成版本化 `001` migration，并以纯 additive `002`
  migration 增加：
  - payload TTL/redaction metadata；
  - machine-readable legal transition relation；
  - DB-level illegal status transition guard；
  - immutable job-event identity/payload guard；
- 集中数据库入口：
  - file database 启动必须验证 `journal_mode=WAL`、
    `synchronous=FULL`、`foreign_keys=ON`、`busy_timeout=5000` 和
    `integrity_check=ok`；
  - migration 使用 `BEGIN IMMEDIATE`、版本/校验和记录和幂等应用；
  - raw SQL 不分散到 channel/runtime business layer；
- inbound repository：
  - 用 source/account/message identity 确定性派生三个稳定 ID；
  - 同一 source message 并发重放只产生一条 inbox 和一个 executable job；
  - 相同 source ID、不同 payload hash 必须报 integrity conflict；
- job repository：
  - 只允许 PRD 7.1 状态图中的边；
  - 每次转换使用 optimistic `state_version` 并追加 redacted event；
  - DB trigger 直接拒绝绕过 service 的非法状态更新；
- active payload：
  - AES-256-GCM envelope，随机 nonce、AAD 绑定 record identity；
  - key 仅由调用方注入，不写数据库、日志、evidence 或 artifact；
  - inbox/context/outbox plaintext 不得出现在 DB/WAL/SHM、普通事件或错误；
  - TTL hook 以不可解密 sentinel 清除 expired ciphertext，保留 hash；
- outbox、sync spool、service state 提供最小 repository API；本 Run 不启动
  worker 或真实 canonical client；
- migration、runtime DB、WAL、SHM 和测试 payload 全部只在临时目录或授权
  target CB-200 staging，禁止提交。

## 4. Explicit phase boundary

- CB-210 才把 WeChat poll/cursor 接入 durable inbox；本 Run
  **不得修改 channel poll**，也不改
  `app/src/adapters/channel/weixin/**` 或 `app/src/core/app.js`；
- CB-220 才实现 scheduler/global active lease；本 Run 只保存 lease schema
  与 job transition contract；
- CB-230 才实现 outbox retry/send worker；本 Run 只提供 durable outbox
  repository；
- CB-240 才调用 no-clone Private-MetaDatabase client；本 Run 只提供
  sync spool 与 mock reconcile evidence；
- `PG-2` 必须在五个 Stage 2 Task 全部通过后的独立 Run 执行。

## 5. Allowed repository modifications

- `CyberBoss/app/package.json`
- `CyberBoss/app/migrations/001_runtime_spool.sql`
- `CyberBoss/app/migrations/002_cb200_retention_and_transitions.sql`
- `CyberBoss/app/scripts/runtime-spool-acceptance.js`
- `CyberBoss/app/src/services/db/database-adapter.js`
- `CyberBoss/app/src/services/jobs/job-state-machine.js`
- `CyberBoss/app/test/runtime-spool.test.js`
- `CyberBoss/app/test/job-state-machine.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P2_1_CB_200.md`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-runtime-spool-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-spool.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-runtime-spool.sh`
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb200.py`
- `CyberBoss/tests/runtime-spool.test.js`
- `CyberBoss/docs/evidence/CB-200/**`
- closure 时的 `CyberBoss/machine/facts/task_state.json`、
  `CyberBoss/README.md`、`CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`

其他路径不得修改。尤其冻结 `CyberBoss/vendor/**`、CB-000–CB-140 和
PG-0/PG-1 evidence、Task DAG、PRD、Architecture、Roadmap、source lock、
许可证与母仓其他项目。

## 6. Local validation

```bash
node --test CyberBoss/app/test/job-state-machine.test.js
node --test CyberBoss/app/test/runtime-spool.test.js
node --test CyberBoss/tests/runtime-spool.test.js
cd CyberBoss/app && npm run check && npm test
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-spool.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-runtime-spool.sh
python3 CyberBoss/scripts/validate_cb200.py --prepare
python3 CyberBoss/scripts/validate_prestage0.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
```

专项测试必须真实执行：

- clean/existing migration 和 legacy v1 reader；
- 10,000 三 ID DB fixture；
- 完整 legal/illegal transition matrix 与不少于 10,000 次 property sequence；
- 至少 32 个并发 duplicate inserter；
- `after_begin`、`after_inbox_insert`、`after_job_insert`、
  `after_event_insert`、`after_commit` 进程 crash；
- mock canonical outage/recovery set diff；
- TTL redaction 和 DB/WAL/SHM plaintext scan；
- `integrity_check=ok`。

## 7. Authorized target sequence

1. 从受保护本地记录解析既有授权目标并匹配
   `target_id_sha256=7865f743d174`；地址不输出、不落库；
2. fresh read-only preflight：service disabled/inactive、process/listener/
   incoming=0、`runtime.db` 不存在、CB-200 candidate/staging 无冲突、
   `current`/workspace 保持冻结值；
3. builder 只能从 clean exact implementation commit 生成 complete
   Corresponding Source、manifest、checksums；
4. installer `--check` 必须证明 persistent writes/live commands=false；
5. 只把 exact artifact set 送入
   `/var/lib/cyberboss/incoming/cb200-<commit>`；
6. 两次 `--apply` 与一次 `--verify`：candidate immutable，第二次幂等，
   不切 `current`、不 enable/start service；
7. 只在 `/var/lib/cyberboss/cb200-staging` 用 synthetic ephemeral key
   执行 target acceptance；不得读取真实 credential；
8. 导出 schema、migration、property/crash/reconcile 的脱敏 evidence；
9. 删除 CB-200 staging/env/incoming 和 synthetic key，保留 inactive
   candidate；
10. 最终确认 service disabled/inactive、process/listener=0、
    `runtime.db` 仍不存在、`current`/workspace 不变。

## 8. Risks, rollback and stop conditions

- **Destructive migration：** 任一 DROP/RENAME/rebuild、旧列删除/收窄或 v1
  reader 失败立即停止；rollback 只回到前一 release，additive table/column
  可保持 unused；
- **Schema lock：** busy timeout、事务边界、并发 duplicate test 任一失败
  即停止；
- **RPO/uniqueness：** committed inbox 丢失、uncommitted fragment 残留、
  duplicate executable job 或 reconcile set diff 非 0 即停止；
- **State bypass：** service 或 raw SQL 任一非法 transition 成功即停止；
- **Privacy：** plaintext payload/context/target、encryption key、真实
  identity/secret 出现在 DB/WAL/SHM、event、日志或 evidence 即停止；
- **Scope creep：** 需要修改 channel poll、scheduler、send worker 或真实
  canonical adapter 才能通过时停止，不借机做 CB-210+；
- **Target rollback：** 删除 exact CB-200 staging/env/incoming；candidate
  只有在 exact manifest 校验后才可删除。`current`、workspace、历史
  candidate 和现有业务数据不参与回滚；
- **硬停止：** integrity check 失败、migration destructive、目标出现无法
  清理的 process/listener，或必须公开 Runtime/注入真实 credential。

## 9. Completion rule

只有 AC-003、AC-016、AC-055、AC-063 的全部 executable evidence、本地完整
回归、exact-commit target candidate install/acceptance 和最终清理都通过，
才能把 `CB-200` 标为 `passed`。

`CB-210`–`CB-540` 与 `PG-2`–`PG-5` 保持 `not_started`。本 Run 不 push，
不创建 PR/tag/release；strict
`AGPL-3.0-only AND GPL-3.0-only`、原源码/许可证/冲突记录和
`upstream_clarification_received=false` 必须保持。
