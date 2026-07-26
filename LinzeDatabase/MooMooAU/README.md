# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前控制包仍为 `1.0.34`；未创建后继任务包。它保持 v1.0.1 冻结的产品目标、
34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill Criteria 与十条不变量。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成并只读校验。T0705 当前事实：

- exact-main protected `SCHEDULE_REHEARSAL` 已在 attempt 1 PASS，rerun 为 0；
- 公开证据只含桶化聚合：verified 与 recovered 均为非零高位桶，source mutation bucket 为
  `ONE`，远端恢复 100%，collateral/duplicate/unresolved 均为 0；
- Raw 与 Processed 只通过 bounded Contents metadata 定址 canonical Git Blob；immutable
  recovery 的上限覆盖合法 Timeline snapshot，而 current pointer 保留更窄上限；
- 每个确定性 verified source 在 Raw/Processed 远端恢复和第二次验证后，最多一次
  exact-message Trash；不使用 thread Trash、永久删除或 mutation retry；
- Timeline snapshot 已恢复，latest age-encrypted Timeline 恰好一个，encrypted checkpoint
  最后提交并远端恢复，tmpfs plaintext cleanup PASS；
- one-shot rehearsal authority 已删除；已提交 workflow 不再接受 `workflow_dispatch`，只接受
  `04:30 Australia/Sydney` platform schedule，并由 repository enablement variable 控制；
- routine schedule 的安全时钟与 RunPlanner 均使用 live UTC；历史 fixture 只属于已完成且如实
  标注的 rehearsal，不进入日常运行；
- 所有历史失败 head 与两个 pre-Secret 失败 head 继续不可 rerun/redispatch。

T0705/S7AC-005 已闭合，但这不等于 Stage 7、最终 Acceptance、生产健康历史或最终发布。
T0706 及后续任务不在本轮；不使用真实时间 Soak、观察期、墙钟等待、后台空转或 Codex
Automation 作为 routine data-plane 依赖。

Authoritative artifacts:

- `machine/contracts/requirements.json`
- `machine/contracts/acceptance_contract.json`
- `machine/contracts/task_graph.json`
- `machine/contracts/delivery_status_model.json`
- `machine/status/latest.json`
- `machine/stages/S7/reviews/t0705/pointer-blob-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/first-import-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/pointer-fetch-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/processed-plan-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/post-processed-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/label-replay-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/repair-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/canonical-blob-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/canonical-blob-preflight-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/authority-variable-scope-attempt-ledger.json`
- `machine/stages/S7/reviews/t0704/attempt-ledger.json`
- `machine/stages/S7/reviews/t0704/execution-receipt.json`
- `machine/stages/S7/reviews/t0705/schedule-planning-clock-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/authentication-clock-coupling-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/raw-recovery-representation-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/trash-confirmation-attempt-ledger.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.34.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.33.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定顺序逐 run 推进，一次最多解决一个 stage。本轮只推进
Stage 7/T0705，停止在 T0706 前；受控 main launch/closure 交付都不是最终发布。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
