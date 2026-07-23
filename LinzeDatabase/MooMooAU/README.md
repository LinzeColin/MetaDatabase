# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前控制包版本为 `1.0.5`，是按 v1.0.4 已冻结修复顺序完成 RMD-05 后的基线保真继任版本。v1.0.1 的产品目标、
34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill Criteria 与十条不变量均按固定哈希原样继承；
v1.0.4 直接前序、v1.0.3 控制前序、v1.0.2 基础前序与 v1.0.1 历史 Manifest 本体保持不可变。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成、由
`machine/tools/validate_delivery_status.py` 只读校验。当前状态为：58/58 任务 evidence 结构与绑定有效，
58/58 本地或合成机制有证据；冻结任务图正式完成 7/58；受保护 Oracle 执行 0/43；最终验收
0/34；生产运行 0；生产就绪 `BLOCKED`；发布状态 `LOCAL_ONLY_NOT_PUBLISHED`。本地机制证据不等于
正式完成、最终验收或生产就绪。

RMD-05 已以 immutable same-tree Git anchor 固定 19-command 本地 gate receipt，并保留两个模型家族各
18 次、共 36 个互异 Codex task ID 的完整独立复审历史；最终两份 schema-valid PASS 回复关闭全部已知
finding。Stage 6 v2、Acceptance、唯一状态与 Governance 均从已审候选和固定输入确定性物化。真实 Gmail、
私有仓、Secret、受保护 Oracle、生产 Workflow 与远端发布仍均为 0/NOT_RUN；RMD-05 关闭不等于最终验收、
生产健康、部署或上线完成。

Authoritative artifacts:

- `machine/contracts/requirements.json` and `machine/contracts/acceptance_contract.json`
- `machine/contracts/task_graph.json`（只裁定正式任务完成度）
- `machine/contracts/delivery_status_model.json`
- `machine/status/latest.json`（唯一当前跨维度状态）
- `machine/contracts/workflow_command_matrix.json`
- `machine/contracts/production_composition.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.4.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.3.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.2.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定修复顺序逐 run 推进，一次最多解决一个 task group。S0–S7、整体复审修复、
受保护验收与最终干净快照全部完成前，只做本地提交，不上传 GitHub。下一 run 只允许进入 RMD-06。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
