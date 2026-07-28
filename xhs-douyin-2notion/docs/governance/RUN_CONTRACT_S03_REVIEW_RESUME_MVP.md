# Run Contract — Stage 3 Review Resume / Direct MVP Policy

## Identity

- Review: `STG.X2N.3.REVIEW.RESUME`
- Run: `RUN-X2N-S03-REVIEW-RESUME-MVP`
- Owner Change Event: `CE-X2N-20260728-S03-REVIEW-RESUME-MVP`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Base: `6b3f5464d1ed645d31c3650b9b51998c9e4fe1ab`
- Parent / child: `LinzeColin/MetaDatabase` / `xhs-douyin-2notion`
- Expected decision: `CONTRACT_VERSIONED / G3_BLOCKED_TECHNICAL`
- Required next task: `TSK.x2n.adapters.010`

本 Run 是不执行新 DAG Task 的 Stage Review Resume。它只把 Owner 已明确给出的能力终态、Acceptance
归属、直接 MVP 发布和数据落地规则写入版本化合同，并验证旧 Review 证据没有被改写。它不得实现
dispatch/fallback、运行真实账号、上传 Stage 3、进入 Stage 4、部署或发布。

## Scope

本 Run 只允许修改：

1. v0.0.0.1 PRFAQ、PRD、Roadmap、Architecture、Acceptance、Task DAG 与 Release Operations；
2. 当前 project/task/path/architecture facts 与 `docs/governance/ARTIFACT_RUNTIME_POLICY.md` 数据路由控制；
3. Resume 专用 schema、fact、报告、验证器、测试和紧凑证据；
4. 项目 `AGENTS.md`、`PURSUING_GOAL.md`、README、HANDOFF、Changelog、功能清单与开发记录的当前状态；
5. 因 44 Tasks / 62 Acceptances 计数和首次 Review 历史兼容所必需的
   `verify_foundation_001.py`、`verify_phase_0_1.py`、`verify_phase_0_5.py` 与
   `verify_stage_3_review.py` 最小更新。

历史 `STG.X2N.3.REVIEW` 的 Run Contract、report、schema、fact、findings、3 份 Review evidence
和 9 份 Task receipt 共 16 个文件保持不可变。旧 Review 验证器必须从
其 final commit 读取旧 Taskpack/Roadmap/Acceptance，不能用新合同重解释历史结果。
Resume verifier 必须把 worktree changed paths 限制在上述精确 allowlist；任何额外文件均 Fail Closed。

## Versioned Decisions

### G3 capability terminals

八个 relation/list scope 只允许以下技术终态：

- `READY_FOR_MVP_ACTIVATION`：合成技术链路已就绪；真实 Policy/Auth/Activation 仍由 Stage 6 判断；
- `DISABLED_EXTERNAL_GATE`：官方 Policy/Auth/Budget/Capability Gate 未满足，Feature Flag 关闭、
  平台调用为 0、不得声称 live support；这是合法的 G3 fail-closed 终态。

G3 不再要求真实账号 Canary。`ACC.x2n.data.002` 在 Stage 3 只记
`PASS_CI_SYNTH_CONTRIBUTION`；完整 `ACC.x2n.rel.006` 和真实激活只属于 Stage 6。

### Remaining technical blocker

`G3` 仍为 `BLOCKED_TECHNICAL`，因为 `TSK.x2n.adapters.010` 尚未执行。该 Task 必须同时闭合：

- 8 个 scope 的严格 Extension → Native → Adapter allowlist dispatch；
- 用严格 `scope_id` 判别的 versioned `START_SYNC`：XHS/Douyin 四个收藏/点赞 scope 与 Weibo
  收藏各绑定唯一 relation；只有 Bilibili/Kuaishou/Taobao 的 selected-collection scope 可在
  `START_SYNC` 使用 `saved_current`，并强制 Owner-selected manifest/source identity/`max_items`；
  `CAPTURE_CURRENT` 继续是不同的单条当前页动作，所有非法交叉组合拒绝；
- versioned typed `GET_CAPABILITIES` 必须向 Side Panel 返回恰好八个 scope 的 terminal、
  fine-grained reason、source registry digests 与 Feature Flag；
- 未登记/禁用 action 的 fail-closed 拒绝；
- SQLite `capability_gate_outcome` 每个固定 scope 最多一行；只有完整有效评估才恰好八行，
  它是唯一 restart-safe runtime derived snapshot；Policy/Capability/Feature registries 只是
  versioned 输入。`BLOCKED_TECHNICAL` 是先于
  所有外部门原因的 global veto；只有 technical=false 后才按
  `UNKNOWN_DISABLED > BLOCKED_POLICY > BLOCKED_AUTH > BLOCKED_BUDGET > BLOCKED_CAPABILITY >
  CI_SYNTH_READY` 选择。最后一项映射 `READY_FOR_MVP_ACTIVATION`，前五项映射
  `DISABLED_EXTERNAL_GATE`；technical 与任一外部门原因并存仍无合法终态、阻止完整八行 snapshot，
  受影响的旧 READY row 立即失效/移除且 `GET_CAPABILITIES` Fail Closed，task010/G3 继续
  Fail Closed；
- `run_record.state=failed` 与脱敏 `run_failure` 是耐久真相；`FALLBACK_AVAILABLE` 只作为
  `fallback_eligible` 的确定性 UI 派生，不新增竞争性的 Run state；
- 失败 `GET_JOB` 的 rejected envelope 必须保留 `job_id`，稳定错误为
  `X2N_ADAPTER_FAILED_FALLBACK_AVAILABLE / next_action=capture_current`；accepted＋error 仍非法；
- 只有第二次独立 Owner 当前页动作才创建带新 `request_id` 与 `fallback_from_job_id` 的
  current-page request；
- Pydantic、error registry、JSON Schema、generated TypeScript、Extension consumer 与 versioned
  SQLite migration 必须同任务同步，并保留原 current-page/Job response compatibility vectors；
- automatic fallback、真实平台调用和误报 live support 均为 0；
- worker/companion restart 后从 SQLite 恢复 Side Panel 状态。

### Direct MVP release

不存在预发布阶段、固定 30 日健康观察或 soak gate。`G0–G5`、
`assurance.001–004/uxops.005` 与 `assurance_005_owned_in_task_acceptance_ids` 精确集合之外的
Blocking Acceptance 通过后，才启动 `TSK.x2n.assurance.005`。该集合固定包含
`capture.001-.006`、`xhs.001/.002`、`dy.001/.002`、`bili/ks/wb/tb.001`、`data.002` 与
`rel.006-.008`，它们不得反向成为启动前置。该任务内部依次完成 80 条 XHS/Douyin Owner MVP
基线，并为每个额外实际启用的能力执行独立、不超过 20 条的激活 Manifest/检查；外部门未满足的
Bilibili/Kuaishou/Weibo/Taobao 能力只能以合法 `PASS_DISABLED_EXTERNAL_GATE`（外部 reason、
flag off、调用 0、live claim 0）结算，`BLOCKED_TECHNICAL` 不能结算。
安全门硬通过、模型能力通过或明确关闭/降级为仅建议模式、回滚演练、Owner 签字、部署、运行和
在线 smoke；安全未知或失败不能降级结算。成功后才签发 `G6 PASS` 并发布唯一
tag `v0.0.0.1`。这些任务内 Oracle 与 `G6 PASS` 都绝不能反向成为任务启动条件。上线后监控是
非阻断信号，只触发修复、降级或回滚，不延迟正常开发。

该发布策略不豁免安全、隐私、证据、幂等、恢复或回滚门禁；任何 Blocking Gate 未通过时仍 Fail
Closed。

### Data routing

- `X2N_DATA_ROOT=${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion` 是下载、执行和活跃 SQLite
  working copy 的本机易失工作区。
- 目标策略是整个 `X2N_DATA_ROOT` 排除于 Time Machine，不允许任何子路径成为长期副本；当前根仍
  是历史逐子目录配置，尚未达到目标。本 Run 不调用 `tmutil`，由 `TSK.x2n.uxops.005` 在 Owner
  明确授权后记录 pre-state、执行 whole-root exclusion 并逐项验证；非 macOS 或任一 included
  子路径均 Fail Closed。本地 backup 只用于当前运行回滚，不能满足 durability receipt 或 Release Gate。
- 活跃 SQLite Canonical Store 是逻辑真相源。
- SQLite 快照、Canonical/Markdown 导出、runtime snapshot 和 receipt 的唯一耐久目的地是
  `LinzeColin/Private-Database` 的 `Private-MetaDatabase` area，项目归属由 manifest
  `domain=xhs-douyin-2notion` 表示。
- 耐久读写只允许
  `KMOS/KMDatabase/machine/tools/private_db_client.py ingest|get|list|verify`；禁止 clone
  Private-Database、直接 Git 写入或绕过客户端。
- 在验证 receipt 前，状态必须是 `durability_pending`。
- 客户端拒绝直接上传 `.sqlite/.db`，单对象上限 95 MiB；一致性 SQLite 快照必须封装为非运行时
  归档、按 ≤90 MiB 分片，并用项目 restore manifest 做 domain 过滤、逐片 SHA-256、重组和 SQLite
  integrity 验证。改名绕过红线不允许。
- 客户端 manifest 的 SHA 幂等与 `verify` 都是全 area 而非 domain-scoped，`verify` 即使发现缺对象
  也不会以非零进程状态表示失败，而且可能枚举其他项目路径。x2n 因此必须使用包含
  domain/index/total/payload SHA 的 domain-bound chunk envelope，先精确筛选
  `domain=xhs-douyin-2notion`，再逐对象 `get`/hash/reassemble/restore。全 area `verify` 只能作为
  不含路径/名称的 redacted advisory，不能作为 x2n Gate；其他 domain 缺失既不能阻断 x2n，也不能
  进入 x2n 日志/证据，而 x2n domain 任一对象缺失必须 Fail Closed。
- `put/delete` 对 x2n 禁用；所以本项目删除只作用于 active SQLite/派生 Sink，并用单调
  `deletion_epoch`＋逻辑 tombstone 约束最新 restore manifest。恢复必须拒绝旧 epoch 并重放 tombstone，
  防止保留的历史快照复活内容；durable hard erase 明确为
  `UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED`，不能用本地 wipe 冒充。所有 object name 必须 opaque，不能含标题、Content ID、账号标识或源
  URL。`get` 临时输出在 hash/重组/恢复后必须删除。
- Stage 5 获明确 Task 授权后，可让现有 Owner-authorized `gh` authenticated session 仅经
  `private_db_client.py` 执行 x2n domain 的 in-scope 操作；不得读取、导出、显示或持久化 Token 值，
  不得修改 auth/config/Credential Helper，也不得删除、撤销或轮换 Token。Stage 5 执行前必须重验
  客户端 digest 与行为；本 Run 只读源码和 `--help`，按过程声明没有调用 authenticated session。

`TSK.x2n.uxops.005` 负责在 MVP 前实现并验收该耐久路径；本 Run 只固化合同，不写入任何运行数据。

### Stage-transition DAG barrier

`TSK.x2n.multimodal.001` 必须显式依赖 `TSK.x2n.adapters.010`，且 Task start policy 要求进入下一
Stage 前上一 Gate 已 PASS。因此仅按依赖调度也不能绕过 task010；即使 task010 完成，`G3` 未经独立
Review 签发 PASS 时仍不得开始 Stage 4。最终 `assurance.005` 的传递依赖闭包必须覆盖其余 43 个 Task。

## Isolation and secret boundary

- 本地 Git 可离线重验只保留一个 x2n worktree 与一个 x2n local branch、其他项目零变更；open PR=0
  是此前只读检查，本离线 verifier 不重新接触远端。
- 本 Resume 对 authenticated session、Token 值与 auth/config/Credential Helper 均零接触；永不
  删除、撤销或轮换现有共享 fine-grained GitHub Token，其外部存在/风险不是本 Gate blocker。未来
  显式授权 Task 可仅经 `private_db_client.py` 使用现有 session，不得读取/显示 Token 值或修改认证。
- Owner Profile、真实账号、平台、真实 Notion、模型、媒体处理均按本 Run 过程声明为 `NOT_RUN` / 0；
  离线 verifier 不把这些外部动作伪装成独立观测。

## Verification

```bash
python3 -B scripts/verify_stage_3_review_resume.py --verify-worktree
python3 -B -m unittest tests.test_stage_3_review_resume
python3 -B -m unittest tests.test_stage_3_review
python3 -B scripts/verify_phase_0_1.py
python3 -B scripts/verify_phase_0_5.py
.venv/bin/python -B scripts/ci/run_lane.py \
  --lane fast --reports-dir build/s03-review-resume-mvp
.venv/bin/python -B scripts/verify_stage_3_review_resume.py \
  --verify-worktree \
  --lane-report build/s03-review-resume-mvp/software-lane.json \
  --write-evidence
```

## Exit and stop conditions

本 Run 完成的必要条件：

- Resume fact 通过严格 schema；
- Task DAG 为 44 Tasks / 62 Acceptances / 0 cycles，G3 只剩 task010；
- 旧 Stage 3 gate fact 与 final commit 字节一致；
- 直接 MVP 和 Private-MetaDatabase 合同可被负向测试证明 fail closed；
- 仓库不含本机绝对路径、Token 值、凭据、平台 CDN URL 或 Runtime Data；
- Stage 3 upload、Stage 4、deployment 均保持 false。

任何一项失败即停止，不能把 G3 记为 PASS。成功后下一独立 Run 只执行
`TSK.x2n.adapters.010` 及 `ACC.x2n.batch.002`。
