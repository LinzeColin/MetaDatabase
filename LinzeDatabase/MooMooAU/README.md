# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前本地控制包版本为 `1.0.7`。它在不可变 v1.0.6 T0702 protected PASS 闭包之上，只补齐独立
protected M3 Budget-1 bootstrap、main-only workflow、T0702 receipt/Run Contract binding 与合成
端到端清理证据。v1.0.1 的产品目标、34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill
Criteria 与十条不变量均按固定哈希原样继承；v1.0.6 及更早 Manifest 本体保持不可变。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成、由
`machine/tools/validate_delivery_status.py` 只读校验。当前状态为：58/58 任务 evidence 结构与绑定有效，
58/58 本地或合成机制有证据；冻结任务图正式完成 7/58；受保护 Oracle 执行并通过 2/43
（Alpha、T0702 Raw-only Beta）；最终验收 0/34；protected Workflow runs 11、production
Workflow 0；生产就绪 `BLOCKED`；发布状态为八次受控 Beta/诊断 main 交付、非最终发布。本地机制、
Alpha/Beta PASS 均不等于 T0703、最终验收或生产就绪。

RMD-05 已以 immutable same-tree Git anchor 固定 19-command 本地 gate receipt，并保留两个模型家族各
18 次、共 36 个互异 Codex task ID 的完整独立复审历史；最终两份 schema-valid PASS 回复关闭全部已知
finding。Stage 6 v2、Acceptance、唯一状态与 Governance 均从已审候选和固定输入确定性物化。
RMD-05 闭包时真实 Gmail、私有仓、Secret、受保护 Oracle、生产 Workflow 与远端发布均为
0/NOT_RUN；该历史闭包不等于最终验收、生产健康、部署或上线完成。

RMD-06 GitHub-hosted 非生产预检已 9/9 成功。完整 v2 账本精确区分一次 Secret 前 context 拒绝与
十一次 protected first attempt，GitHub rerun 始终为 0。最终 exact-main attempt 通过同树 Alpha、
Raw-only Beta 与 identity cleanup；公开安全结果只声明 verified-within-budget、Raw remote recovery
100%、非零 age-ciphertext-only private namespace，以及 Gmail mutation/M3/Processed/Timeline/
schedule 为 0。T0702/S7AC-002 已通过。

v1.0.7 新增的 protected M3 入口只允许一个 verified candidate 和一个 exact source-message Trash；
Raw 与 Processed 必须先经同一私有仓远端解密/摘要恢复，并再次验证 sender。workflow 固定
owner/actor、main、exact SHA、GitHub-hosted attempt 1 与八项 Secret allowlist，且首个无 Secret job
必须验证 T0702 PASS receipt 和当前 Run Contract。当前 `m3_authorized=false`，所以入口默认关闭，
真实 M3、Processed、Gmail mutation 与远端发布仍为 0。

Stage 7 不再设置 M3 七天或 Blue-Green 十四天的固定日历等待。Beta PASS 后，M3 与 Blue-Green
分别用一次有界受保护运行中的确定性恢复、Mutation、Parser 比较、Full Reconcile 与单一 Timeline
证据判定；前序和安全门不变。GA 仍须真实观察一次 04:30 Australia/Sydney 调度。

Authoritative artifacts:

- `machine/contracts/requirements.json` and `machine/contracts/acceptance_contract.json`
- `machine/contracts/task_graph.json`（只裁定正式任务完成度）
- `machine/contracts/delivery_status_model.json`
- `machine/status/latest.json`（唯一当前跨维度状态）
- `machine/contracts/workflow_command_matrix.json`
- `machine/contracts/production_composition.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.7.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.6.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.4.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.3.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.2.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定顺序逐 run 推进，一次最多解决一个 stage。历史 T0702 Beta 受控 main
交付不是最终发布，失败 lineage 与最终 PASS receipt 均保持不可变。当前 Owner 范围停在 M3 前；
v1.0.7 只使未来 T0703 可维护、可验证、默认关闭，不授权 dispatch、Secret 读取或真实 mutation。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
