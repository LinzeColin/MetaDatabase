# Run Contract — P2.3 / CB-220 Scheduler, Resource Gate and Runtime Control

## 1. Goal

本 Run 只执行 Task DAG 节点 `P2.3 / CB-220`：

> Implement scheduler, resource gate, workspace alias and Runtime control.

以已通过的 `P2.2 / CB-210` closure
`e5995d0967e789c99ce06b5b76fa794e5d455f68` 为冻结输入，在 CB-200/CB-210
durable spool 之上交付：

- Runtime jobs 按 `created_at,id` FIFO；
- 全局最多一个 active Runtime lease，含 heartbeat、expiry 与 fencing；
- Runtime readiness、poll freshness、memory/disk/inode/load/queue、
  workspace alias 和 operation class 的 dispatch gate；
- command jobs 与 Runtime jobs 分离，保证 `/stop` 不被 active Runtime
  lease 自锁；
- `/bind`、`/stop`、`/new`、`/status` 的受控行为；
- Runtime completion/failure/cancel 的真实 durable terminal state；
- 进程丢失后的 recovery safety classification，禁止模糊 mutation
  自动重放。

本 Run 不执行 `CB-230`、`CB-240` 或 `PG-2`，不实现 durable outbox/send
retry/confirmation，不激活真实 WeChat/Codex/Private-MetaDatabase，不切目标机
`current` 或 service，不创建新 repo，不 push，不创建 PR/tag/release。

## 2. Authoritative scope

- Task：`04_TASK_DAG_EXECUTION_PACK.yaml / CB-220`；
- dependencies：`CB-200`、`CB-120`，均已 `passed`；
- Acceptance：
  - `AC-012`：同时入队 5 个长任务，max active Runtime lease=1，Runtime
    dispatch 顺序严格 FIFO；
  - `AC-013`：非 allowlisted workspace 不进入 Runtime，且 filesystem
    diff=0；
  - `AC-014`：`/bind cyberboss` 成功，绝对路径、未知 alias 与 symlink
    escape 拒绝；
  - `AC-015`：active job 中 `/stop` 确实调用 Runtime cancel；active job
    durable 终态只按 Runtime 事实记为 cancelled/failed/succeeded；
  - `AC-045`：poll stale、Runtime unhealthy、disk/load/queue fixture 产生
    精确 degraded reason/action；
  - `AC-064`：立即执行 burst/memory/disk/queue pressure ladder，
    guard/protect/recover 正确，无 OOM、无真实时间 soak；
- invariants：
  - `INV-005`：同一时刻只有一个 active Runtime lease；
  - `INV-007`：未通过 workspace alias/realpath guard 的任务不得进入
    Runtime；
  - `INV-008`：job/event/status/evidence 不写 secret、完整 prompt/result、
    原始用户/thread ID 或目标地址；
- release artifact：
  `/opt/cyberboss-cloud/releases/<implementation-commit>/evidence/job-scheduler-acceptance.json`。

## 3. Minimum implementation

### 3.1 Durable scheduler

- additive migration，不 drop/rename 既有表或破坏 CB-200/CB-210 reader；
- Runtime claim 使用 `BEGIN IMMEDIATE`，在同一事务内检查 active row、
  singleton lease 和 FIFO head；
- DB 约束与服务层共同保证 active Runtime lease `<=1`；
- claim、dispatch-start、Runtime binding、approval、cancel request、
  heartbeat、terminal/recovery 都生成脱敏 material event；
- lease heartbeat 只接受当前 job + owner；stale owner 不能延长或结束新
  lease；
- lease expiry：
  - Runtime dispatch 尚未开始时可证明无执行，只能按合法状态转换重新排队；
  - dispatch 已开始而进程丢失时视为 ambiguous；bounded mutation 与无
    幂等证明的操作进入 terminal/hold，绝不自动重放；
  - 只有明确 `read_only`、Runtime 已报告 retryable terminal 且 retry
    budget 未耗尽时才可自动重新排队；
- scheduler flag 可在受控 staging 关闭以回退 manual staging dispatch，
  但 production release/ready 保持 blocked。

### 3.2 Command/control plane

- command jobs 与 Runtime jobs 使用分离 claim 路径；command job 不持有
  Runtime singleton lease；
- command control plane 串行、bounded，不能启动普通 Runtime turn；
- `/stop` 可在 Runtime lease active 时执行：
  1. durable 记录 cancel request；
  2. 调用 exact active thread/turn 的 Runtime cancel；
  3. acknowledgement 只声称“request acknowledged”；
  4. active job 的最终状态由后续 Runtime event 决定；
- `/new` 与 `/bind` 在 active Runtime job 存在时不得改变该 job 的
  workspace/thread binding；
- `/status` 只输出 alias、queue count、active boolean、gate reason/action
  等脱敏事实；
- 其他已注册 channel command 可走同一受控 command dispatcher，但不得
  绕过 workspace/approval/runtime active guards。

### 3.3 Workspace, readiness and resource gate

- job 只能携带 alias，scheduler 每次 dispatch 前重新调用 CB-120 registry
  的 alias lookup、`lstat`、`realpath` 与 exact-root guard；
- absolute path、unknown alias、workspace base/config/root symlink、
  registered-root 外路径全部 fail closed；
- Runtime adapter 必须暴露不含 credential 的 readiness；
- live resource probe 使用当前 host/cgroup 可观测值；测试使用注入 fixture；
- protect threshold 至少覆盖：
  memory available `<512 MiB` 或 used `>=92%`、disk/inode used
  `>=90%`、load1m `>max(3.5,cpu*1.5)`、queue depth profile limit；
- recover threshold 至少覆盖：
  memory available `>=768 MiB` 且 used `<85%`、disk/inode `<80%`、
  load1m `<=75%` limit、queue below recover threshold；
- gate 输出必须是固定 code，不包含自由文本、绝对路径或敏感值；所有 timer
  接受 injectable clock，验收不得固定等待真实分钟/小时。

### 3.4 Runtime truth

- Runtime dispatch 返回的 thread/turn 仅在内存中用于精确关联；DB/event
  只保存不可逆 hash 或 boolean；
- `turn/completed` 必须读取 Runtime status：
  interrupted/cancelled → `cancelled`，completed/succeeded →
  `succeeded`；
- `turn/failed` 分类 retryable、terminal、auth、transport/overload；
- cancel request 与 terminal event 竞态时不假设取消成功：
  completed 仍为 succeeded，failed 仍为 failed；
- late/duplicate/unmatched Runtime event 不能结束另一 job 或释放新 lease。

## 4. Explicit phase boundary

- `CB-230` 才实现 durable accepted/result/error outbox worker、send receipt、
  backoff、chunk confirmation；本 Run 的现有 direct channel response 不得
  声称 durable delivery；
- `CB-240` 才使用 no-clone Private-MetaDatabase client；
- `CB-340` 才完成完整 status/self-heal/retention operational loop；本 Run
  只交付 dispatch gate 与固定 degraded classification；
- `PG-2` 必须等 CB-200–CB-240 全部通过后独立执行；
- candidate-only target acceptance 不 enable/start service，不注入真实
  credential，不修改 canonical runtime DB。

## 5. Allowed repository modifications

- `CyberBoss/app/migrations/003_cb220_scheduler_control.sql`
- `CyberBoss/app/package.json`
- `CyberBoss/app/scripts/job-scheduler-acceptance.js`
- `CyberBoss/app/src/adapters/runtime/codex/events.js`
- `CyberBoss/app/src/adapters/runtime/codex/index.js`
- `CyberBoss/app/src/adapters/runtime/claudecode/events.js`
- `CyberBoss/app/src/adapters/runtime/claudecode/index.js`
- `CyberBoss/app/src/core/app.js`
- `CyberBoss/app/src/core/config.js`
- `CyberBoss/app/src/services/db/database-adapter.js`
- `CyberBoss/app/src/services/inbox/durable-inbox.js`
- `CyberBoss/app/src/services/jobs/job-scheduler.js`
- `CyberBoss/app/src/services/jobs/resource-readiness-gate.js`
- `CyberBoss/app/test/job-scheduler.test.js`
- `CyberBoss/app/test/resource-readiness-gate.test.js`
- `CyberBoss/app/test/runtime-spool.test.js`
- `CyberBoss/app/test/turn-gate-store.test.js`
- `CyberBoss/app/test/workspace-scope.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P2_3_CB_220.md`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-job-scheduler.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-job-scheduler-artifacts.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-job-scheduler.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js`
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb220.py`
- `CyberBoss/tests/job-scheduler.test.js`
- `CyberBoss/docs/evidence/CB-220/**`
- closure 时的 `CyberBoss/machine/facts/task_state.json`、
  `CyberBoss/README.md`、`CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`

其他路径不得修改。尤其冻结 `CyberBoss/vendor/**`、CB-000–CB-210 与
PG-0/PG-1 evidence、Task DAG、PRD、Architecture、Roadmap、source lock、
许可证与母仓其他项目。

## 6. Local validation

```bash
node --test CyberBoss/app/test/job-scheduler.test.js
node --test CyberBoss/app/test/resource-readiness-gate.test.js
node --test CyberBoss/app/test/workspace-scope.test.js
node --test CyberBoss/tests/job-scheduler.test.js
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb220.py --prepare
python3 CyberBoss/scripts/validate_prestage0.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
```

专项测试必须真实执行：

- 5 个 long fixture jobs，active Runtime lease 历史最大值为 1，dispatch
  顺序等于 `created_at,id`；
- 并发 DB claim、stale heartbeat、expiry before/after dispatch、late event
  fencing；
- read-only retry 与 ambiguous bounded mutation no-replay；
- allowlisted/absolute/unknown/symlink workspace matrix + filesystem hash；
- runtime unready、poll stale、memory/disk/inode/load/queue protect/recover；
- active job 中 `/stop`，cancel call count=1，interrupted/failed/completed 三种
  truthful terminal；
- `/bind`、`/new` active guard 与 `/status` privacy；
- immediate bounded pressure fixture、cgroup OOM delta=0、无真实时间 soak。

## 7. Authorized target sequence

1. 从受保护本地部署记录解析既有授权目标并匹配
   `target_id_sha256=7865f743d174`；地址不输出、不落库；
2. fresh read-only preflight：service disabled/inactive、process/listener/
   incoming=0、canonical `runtime.db` 不存在、CB-220 candidate/staging
   无冲突、`current`/workspace 保持冻结值；
3. builder 只能从 clean exact implementation commit 生成 complete
   Corresponding Source、manifest、checksums；
4. installer `--check` 必须证明 persistent writes/live commands=false；
5. exact artifact set 进入
   `/var/lib/cyberboss/incoming/cb220-<commit>`；
6. 两次 `--apply` 与一次 `--verify`：candidate immutable，第二次幂等，
   不切 `current`、不 enable/start service；
7. 只在 `/var/lib/cyberboss/cb220-staging` 和独立 synthetic runtime root
   使用 ephemeral keys/state、simulator 与 fixture；
8. 导出脱敏 scheduler timeline、workspace/resource/stop/recovery evidence；
9. 删除 CB-220 staging/env/incoming、synthetic runtime root 与 keys，保留
   inactive candidate；
10. 最终确认 service disabled/inactive、process/listener=0、canonical
    `runtime.db` 仍不存在、`current`/workspace 不变。

## 8. Risks, rollback and stop conditions

- **Active concurrency：** 任一时刻 active Runtime lease 或 simulator active
  turn 超过 1，立即停止；
- **Unsafe replay：** dispatch-start 后的 bounded mutation/ambiguous job
  被自动重新排队或再次调用 Runtime，立即停止；
- **Lease orphan/fencing：** stale owner 能 heartbeat/finish 新 lease，或
  expired owner 未被精确分类，立即停止；
- **Workspace escape：** absolute/unknown/symlink/nonregistered path 到达
  Runtime 或产生 filesystem change，立即停止；
- **False terminal：** cancel acknowledgement 直接把 active job 标为
  cancelled/succeeded，或 Runtime completed/failed 被改写，立即停止；
- **Resource false green：** unavailable/invalid measurement 被当作 ready，
  或 protect fixture 仍 dispatch mutation，立即停止；
- **Rollback：** staging 可关闭 scheduler 并保留 durable queue 供人工
  inspect；production release/ready blocked。目标机只删除 exact CB-220
  staging/env/incoming/synthetic runtime；`current`、workspace、历史
  candidate 和业务数据不参与回滚。

## 9. Completion rule

只有 AC-012、AC-013、AC-014、AC-015、AC-045、AC-064 的全部 executable
evidence、本地完整回归、exact-commit target candidate install/acceptance
和最终清理都通过，才能把 `CB-220` 标为 `passed`。

`CB-230`–`CB-540` 与 `PG-2`–`PG-5` 保持 `not_started`。本 Run 不 push，
不创建 PR/tag/release；strict
`AGPL-3.0-only AND GPL-3.0-only`、原源码/许可证/冲突记录和
`upstream_clarification_received=false` 必须保持。
