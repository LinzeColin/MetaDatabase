# Run Contract — P2.5 / CB-240 Canonical Sync and Rebuild

## 1. Goal

本 Run 只执行 Task DAG 节点 `P2.5 / CB-240`：

> Implement redacted append-only Private-MetaDatabase canonical sync.

以已通过的 `P2.4 / CB-230` closure
`8793e186f4baa2767dc3da0378492ffa17984d4d` 为冻结输入，并应用 Owner 提供的
`CyberBoss_v0.0.0.5_TASKPACK.zip`（SHA-256
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`）中的
v0.0.0.7 closure amendment。产品版本固定为 `v0.0.0.5`，设计基线保持
`v0.0.0.4`；本 Run 不修改版本。在 schema v4、durable inbox/job/outbox 与
delivery truth 之上交付：

- terminal job/material event 到严格 allowlist canonical event 的稳定映射；
- 最多 50 条、262144 bytes 的本地 deterministic compressed
  content-addressed object；普通事实即时写入 SQLite/redacted spool，60 秒 age
  不得触发远端提交；
- ordinary 远端同步只由 `daily` timer/operator `sync` 触发，默认
  `03:20 UTC`；`release_completed`、`incident_declared`、
  `recovery_completed` 三类 material event 走有界即时 invocation，目标
  `<=60s`；无新事实返回 `noop_no_commit`；
- code identity 只生成脱敏 spool、消费 hash-only receipt；
  `cyberboss-data` identity 才能调用 no-clone
  `private_db_client.py ingest|get|list|verify`；
- manifest 409、403/429、连接故障和 partial-success 后的幂等重取、重试与
  event-ID set verification；
- same event ID/different record hash 的 P0 integrity quarantine；
- pending count、oldest age（观测，不作为普通事实保护条件）、last object、last
  verification 与仅 integrity/resource/material-retry 触发的 mutation-stop 状态；
- 不依赖原 SQLite 的 terminal index 与 canonical Timeline source 重建。

本 Run 不执行 `PG-2` 或 `CB-300`，不交付 Timeline Web/build/search，不激活
真实 WeChat/Codex/Private-MetaDatabase/R2/Cloudflare/OCI，不切目标机
`current` 或 service，不创建新 repo，不 push，不创建 PR/tag/release。

## 2. Authoritative scope

- Task：`04_TASK_DAG_EXECUTION_PACK.yaml / CB-240`；
- Owner amendment：TaskPack v0.0.0.7 / product v0.0.0.5 的
  `patch_specs/CB-240_OWNER_AMENDMENT.md`；每个边界已运行该包 local Skill
  Router，CB-240 只使用 `output-skill` 对应的轻量输出完整性约束；
- dependencies：`CB-120`、`CB-200`、`CB-230`，均已 `passed`；
- Acceptance：
  - `AC-030`：删除隔离 SQLite 后，只用 no-clone canonical objects 与
    deterministic R2 recovery-pointer fixture 重建 terminal index/Timeline
    source，event/index hashes 一致；
  - `AC-031`：1,000 个 terminal events 覆盖 record/byte object boundary；
    普通事实仅日频提交、三类 material event 虚拟时钟即时 flush
    P95 `<=60s`、无空提交、普通 age 不阻断 bounded mutation；失败显式 pending，
    恢复后 set diff=0；
  - `AC-032`：50 组并发 sync、manifest 409、403/429、outage 与 partial
    success 均不覆盖、不丢失，event ID/hash 集合一致并尊重 retry hint；
  - `AC-033`：canonical object、spool、receipt、rebuild output、DB/WAL/SHM
    与 evidence 不含完整 prompt/result、token、原始用户/thread/target；
- invariants：
  - `Private-MetaDatabase`、`domain=CyberBoss`、`main`、no-clone 和
    `ingest|get|list|verify` 是唯一允许的数据范围；
  - object 由 deterministic uncompressed event set 唯一决定，manifest
    冲突绝不 last-write-wins；
  - code identity 不得执行 data client，data identity 不得读取 active
    prompt/result 或写 code workspace；
  - short outage 不阻塞 durable inbox/outbox；达到 count/byte resource 预算、
    integrity incident 或 material retry 后才阻断新的 bounded mutation；普通
    backlog age 仅记录为 degraded observation，不单独阻断 mutation；
- release artifact：
  `/opt/cyberboss-cloud/releases/<implementation-commit>/evidence/canonical-sync-report.json`。

`AC-030` 在本 phase 只验收 canonical terminal index/Timeline source 与
R2 recovery pointer 的 deterministic fixture。真实 R2 snapshot/restore、
Timeline Web/build/search 与完整恢复推广分别仍属于 `CB-400`、`CB-300` 和
后续 pass gate，不得在本 Run 冒充已完成。

## 3. Minimum implementation

### 3.1 Strict canonical mapping and additive spool

- schema v5 只能 add column/index/trigger，不 drop/rename/vacuum 既有对象；
  v1 reader 继续可读既有列；
- canonical event 至少包含 schema version、stable event/job/correlation
  ID、occurred/recorded time、source、event type/status、workspace alias、
  runtime、input/output SHA-256、fixed redacted summary、evidence refs、
  deployed commit 与 independently verifiable record SHA-256；
- event mapper 使用字段 allowlist；raw prompt/result、provider body、
  account/user/thread/target/context/secret 和绝对路径没有序列化入口；
- same local event ID + different canonical record hash 立即
  `integrity_error`；
- sync spool identity/payload immutable；retry/receipt/object verification
  metadata 可追加更新，未验证记录不得删除。

### 3.2 Deterministic batching and identity-separated worker

- local object 同时受 `max_records=50`、`max_bytes=262144` 约束；旧
  `max_age=60s` 变量仅 parse-compatible，绝不触发远端提交。ordinary 由
  `daily` / `03:20 UTC` dispatch，material allowlist 由显式 `material`
  invocation dispatch；clock/timer 可注入且测试无真实等待；
- events 先按 stable event ID 排序，写 deterministic NDJSON header +
  records，再用 deterministic gzip 压缩；object SHA-256、event-set SHA-256、
  first/last event ID 和 logical type 可复算；
- code plane 只原子写入 group-readable redacted outgoing object，并保留
  SQLite sync spool；不得调用 data client；
- data plane 以 `cyberboss-data` 读取 outgoing object、调用 fail-closed
  safe wrapper，并原子写入不含正文的 receipt；
- code plane 只有在 receipt、object hash、manifest record、remote
  event-ID/hash set 全部验证后才标记 synced；
- one local data worker lease 防止双主；crash/unknown outcome 先 remote
  reconcile，再决定 idempotent retry。

### 3.3 Conflict, retry, status and mutation protection

- successful ingest 后必须执行 list/get/verify 并校验 object、manifest 和
  event set；
- manifest 409 或 unknown/partial success：先 refetch；remote 已有同 hash
  event set 则成功，否则同一 content-addressed object 安全重试；
- 429 尊重 provider retry hint；403 标记 auth/scope pending；连接故障使用
  bounded retry，验收全部用虚拟时钟、无真实等待；
- remote same ID/different record hash 进入 quarantine/integrity incident，
  停止新的 mutation，不覆盖、不删除源 event/object；
- status 至少暴露 state、pending events/bytes、oldest age、last object
  SHA-256、last verified time、last error class、mutation allowed；
- pending count/bytes 超配置预算、integrity incident 或 material retry 时，
  scheduler 拒绝新的 `bounded_mutation`，仍允许 read-only、status 和既有
  durable drain；普通 normal lag `>900s` 只暴露 observation，不改变该决定。

### 3.4 Rebuild

- rebuild CLI 只能通过 safe wrapper 的 `list/get/verify` 读取
  `Private-MetaDatabase`，禁止 clone、put、delete；
- 每个 manifest/object hash、batch header、record hash 和 duplicate event
  set 都须验证；
- clean output 产生 deterministic `terminal-index.json`、
  `timeline-source.ndjson` 与 `rebuild-report.json`；
- Timeline source 是供既有 `timeline-for-agent` 在 `CB-300` 消费的
  canonical projection，不新建第二套 Timeline 内核，也不声称本 Run 已完成
  Web/build/search；
- isolated SQLite 删除后的 rebuild fixture 同时校验 R2
  recovery-pointer object hash，但不执行真实 R2 写入。

## 4. Explicit phase boundary

- `PG-2` 必须在本 Run closure 后独立执行；
- `CB-300` 才适配既有 Timeline writer/build/read-only Web；
- `CB-310/CB-340` 才完成全局 status exporter、自愈和 operational loop；
- `CB-400` 才完成真实 R2 snapshot、backup/restore 和推广门；
- real Private-MetaDatabase credential/scope 未 attested，保持
  `activation_pending`；simulator/target synthetic evidence 不得报告为真实
  canonical write；
- candidate-only target acceptance 不 enable/start business service、不切
  `current`、不移动 workspace、不读取 credential 内容。

## 5. Allowed repository modifications

- `CyberBoss/app/migrations/005_cb240_canonical_sync.sql`
- `CyberBoss/app/package.json`
- `CyberBoss/app/scripts/canonical-rebuild.js`
- `CyberBoss/app/scripts/canonical-sync-acceptance.js`
- `CyberBoss/app/scripts/canonical-sync-data.js`
- `CyberBoss/app/src/core/app.js`
- `CyberBoss/app/src/core/config.js`
- `CyberBoss/app/src/services/canonical/canonical-sync.js`
- `CyberBoss/app/src/services/db/database-adapter.js`
- `CyberBoss/app/src/services/jobs/job-scheduler.js`
- `CyberBoss/app/test/canonical-sync.test.js`
- `CyberBoss/app/test/job-scheduler.test.js`
- `CyberBoss/app/test/runtime-spool.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P2_5_CB_240.md`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-canonical-sync.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-canonical-sync-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-canonical-sync.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/private_db_client_safe.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/private-db-simulator.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.service`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.timer`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync-material.service`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync-material.path`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/simulator-contract.test.mjs`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js`
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb240.py`
- `CyberBoss/tests/canonical-sync.test.js`
- `CyberBoss/docs/evidence/CB-240/**`
- closure 时的 `CyberBoss/machine/facts/task_state.json`、
  `CyberBoss/README.md`、`CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`

其他路径不得修改。尤其冻结 `CyberBoss/vendor/**`、CB-000–CB-230 与
PG-0/PG-1 evidence、Task DAG、PRD、Architecture、Roadmap、source lock、
许可证与母仓其他项目。

## 6. Local validation

```bash
node --test CyberBoss/app/test/canonical-sync.test.js
node --test CyberBoss/app/test/job-scheduler.test.js
node --test CyberBoss/tests/canonical-sync.test.js
cd CyberBoss/app && npm run check && npm test
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py
python3 CyberBoss/scripts/validate_cb240.py --prepare
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
```

`validate_prestage0.py` 的冻结断言止于 `P2.4 / CB-230`（包括当时的
`taskpack_version` 和 `CB-240=not_started`），因此不是 P2.5 的可执行验收。
本 Run 以同路径的 merge-safe `validate_cb240.py --prepare` 替代；不得把
前一阶段的预检失败误报为 CB-240 实现失败。

专项测试必须真实执行：

- 50 ordinary facts 在 material mode 下远端提交数为 0，daily mode 于
  `03:20 UTC` 语义下提交；三类 material event 的虚拟 P95 `<=60s`；
- 1,000 terminal events，record/byte batching、集合完整、set diff=0；普通
  age 不生成远端提交且不单独阻断 bounded mutation；
- fake-clock Private-Database outage 10 分钟后完整 catch-up；
- 50 concurrent sync sets、manifest 409、403、429 retry hint、transient 与
  partial-success；
- same ID/different hash quarantine + bounded-mutation stop；
- code/data identity negative matrix、no-clone/put/delete rejection；
- 删除 isolated SQLite 后，仅用 canonical objects + R2 pointer fixture
  重建 terminal index/Timeline source；
- object/spool/receipt/rebuild/evidence 与 DB/WAL/SHM privacy/secret scan；
- 全量 App regression，无真实 credential/provider/Private-Database call。

## 7. Authorized target sequence

1. 从受保护本地部署记录解析既有授权目标并匹配
   `target_id_sha256=7865f743d174`；地址不输出、不落库；
2. fresh read-only preflight：service/unit disabled/inactive、process/listener/
   incoming=0、canonical `runtime.db` 不存在、CB-240 candidate/staging
   无冲突、`current`/workspace 保持冻结值；
3. builder 只能从 clean exact implementation commit 生成 complete
   Corresponding Source、manifest、checksums 与 canonical sync report；
4. installer/acceptance `--check` 必须证明 persistent writes/live
   commands/credential reads/real data operations=false；
5. exact artifact set 进入
   `/var/lib/cyberboss/incoming/cb240-<commit>`；
6. 两次 `--apply` 与一次 `--verify`：candidate immutable，第二次幂等，
   canonical worker/timer 保持 disabled/inactive，不切 `current`、不启动
   business service；
7. 只在 exact CB-240 staging/synthetic roots 使用 ephemeral keys、Private-DB
   simulator、object-store simulator 和 virtual clock；
8. 以 synthetic code/data identity 运行 batch、conflict、outage、rebuild 与
   privacy acceptance，导出脱敏 evidence；
9. 删除 exact staging/env/incoming/synthetic runtime/data/R2 roots 与 keys，
   保留 inactive candidate；
10. 最终确认 service/worker/timer disabled/inactive、process/listener=0、
    `current`/workspace 不变、无 Private-Database clone/real operation。

## 8. Risks, rollback and stop conditions

- **Event loss/overwrite：** local expected set 与 verified remote set 不同且
  不能由 pending 解释，立即停止；
- **Integrity conflict：** same event ID/different record hash，立即 quarantine
  并停止 mutation；
- **Privacy leak：**完整 prompt/result、secret、原始 identity/thread/target
  进入 object/spool/receipt/rebuild/evidence，立即停止；
- **Lag/commit storm：**material retry 未保护、batch 超 50/byte budget、普通
  事实在 daily/operator 之外远端提交或出现空 commit，立即停止；普通 lag age
  本身不是停止条件。
- **Identity escape：** code identity 可执行 data client、data identity 可写
  code workspace、出现 clone/put/delete，立即停止；
- **Rollback：** disable canonical data worker/timer，保留 SQLite sync spool、
  outgoing objects 和 receipts；坏 object/manifest 只隔离不删除源 events。
  目标机只删除 exact CB-240 staging/env/incoming/synthetic roots，
  `current`、workspace、历史 candidates、credentials 与业务数据不参与回滚。

## 9. Completion rule

只有 `AC-030`、`AC-031`、`AC-032`、`AC-033` 与 Owner amendment
`FA-AC-001`–`FA-AC-006` 的全部可执行证据、本地完整回归、exact Subject
digest 和原子 current-truth metadata 都通过，才能把 `CB-240` 标为 `passed`。
真实 target candidate install/activation 不在本次 closure 中伪造；无真实
Private-Database credential 的 provider 状态必须保持 `activation_pending`。

真实 Private-MetaDatabase operation 保持 `activation_pending`，不妨碍
simulator/no-clone adapter contract 通过，但不得报告为真实验证。
`CB-300`–`CB-540` 与 `PG-2`–`PG-5` 保持 `not_started`。本 Run 不 push，
不创建 PR/tag/release；strict
`AGPL-3.0-only AND GPL-3.0-only`、原源码/许可证/冲突记录和
`upstream_clarification_received=false` 必须保持。
