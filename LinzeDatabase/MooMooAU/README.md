# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前本地控制包版本为 `1.0.9`。它直接继承不可变 v1.0.8，固化 T0703 首次 protected M3 的零观察
副作用失败，并建立唯一 metadata-remediation Run Contract。v1.0.1 的产品目标、34 条需求、34 个
最终验收、58-task DAG、追踪矩阵、Kill Criteria 与十条不变量均按固定哈希原样继承；v1.0.8 及更早
Manifest 本体保持不可变。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成、由
`machine/tools/validate_delivery_status.py` 只读校验。当前状态为：58/58 任务 evidence 结构与绑定有效，
58/58 本地或合成机制有证据；冻结任务图正式完成 7/58；受保护 Oracle 已执行 3/43，其中 Alpha 与
T0702 Raw-only Beta 通过、T0703 attempt 1 失败；最终验收 0/34；protected Workflow runs 12、
production Workflow 0；生产就绪 `BLOCKED`。九次既有受控 main 交付均不是最终发布。本地机制、
修复授权或 Alpha/Beta PASS 均不等于 T0703 PASS。

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

T0703 首次 exact-main attempt 的 authority 与 identity cleanup 通过，但 M3 job 失败；公开输出未
声称精确根因。只读后验核验观察到 private 新 commit、Processed write、Gmail Trash mutation 与
Timeline effect 均为 0，失败 head 禁止 rerun/redispatch。v1.0.9 将 T0702 已证明安全的逐消息
`MessageMetadataUnverifiable` quarantine 对齐到 M3，并用固定 phase 枚举输出失败；其他错误继续
整次 fail closed。新候选仍只允许一个 verified candidate 和一个 exact source-message Trash；
Raw 与 Processed 必须先经同一 private remote 恢复，并再次验证 sender。

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
- `taskpack/PACKAGE_MANIFEST.v1.0.9.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.8.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.7.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.6.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.4.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.3.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.2.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定顺序逐 run 推进，一次最多解决一个 stage。历史 T0702 Beta 受控 main
交付不是最终发布，失败 lineage 与最终 PASS receipt 均保持不可变。当前 Run Contract 只消费
T0703：一份新受控 main 交付、一次新候选 attempt-1 protected dispatch、源消息 mutation Budget 1；
不得 rerun 失败 head，不得进入 T0704。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
