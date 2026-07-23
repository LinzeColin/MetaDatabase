# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前控制包版本为 `1.0.6`，是完成 RMD-05 后用于 RMD-06 云前置闭包、T0702 protected Raw-only
入口与唯一失败执行回执的基线保真继任版本。v1.0.1 的产品目标、
34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill Criteria 与十条不变量均按固定哈希原样继承；
v1.0.5 直接前序、v1.0.4/v1.0.3/v1.0.2 控制前序与 v1.0.1 历史 Manifest 本体保持不可变。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成、由
`machine/tools/validate_delivery_status.py` 只读校验。当前状态为：58/58 任务 evidence 结构与绑定有效，
58/58 本地或合成机制有证据；冻结任务图正式完成 7/58；受保护 Oracle 执行 2/43（Alpha 通过 1、
Beta 失败 1）；最终验收 0/34；protected Workflow 1、production Workflow 0；生产就绪
`BLOCKED`；发布状态为一次受控 Beta main 交付、非最终发布。本地机制或 Alpha PASS 均不等于
T0702、最终验收或生产就绪。

RMD-05 已以 immutable same-tree Git anchor 固定 19-command 本地 gate receipt，并保留两个模型家族各
18 次、共 36 个互异 Codex task ID 的完整独立复审历史；最终两份 schema-valid PASS 回复关闭全部已知
finding。Stage 6 v2、Acceptance、唯一状态与 Governance 均从已审候选和固定输入确定性物化。
RMD-05 闭包时真实 Gmail、私有仓、Secret、受保护 Oracle、生产 Workflow 与远端发布均为
0/NOT_RUN；该历史闭包不等于最终验收、生产健康、部署或上线完成。

RMD-06 第五轮 GitHub-hosted 非生产预检已 9/9 成功。Owner 授权的一次受控 PR/merge 与一次
budget-one dispatch 已用尽：同树 Alpha 成功，protected Beta 在首个远端 Raw commit 前失败，
identity tmpfs cleanup 成功；私有数据仓仍是 64-byte 单文件基线，Gmail mutation、M3、Processed、
Timeline、schedule 与最终发布均为 0。公开 aggregate-only 日志无法确定内部根因，因此 T0702/
S7AC-002 仍 `BLOCKED`，本轮禁止第二次交付、dispatch、rerun 或进入 M3。

后续纯本地 Stage 7 repair 已增加 19 项封闭的 public-safe failure phase taxonomy，并将每个 phase
与唯一固定 reason code 通过 JSON Schema 精确耦合。渲染器不接收异常对象、动态文本、Secret、
邮件字段、私有仓标识或精确计数；合成 phase probe 覆盖 context、bootstrap、Raw runtime、remote
recovery、aggregate gate 与 cleanup。该修复尚未交付或 dispatch，不能反推历史失败根因，也不改变
T0702 `BLOCKED` 或 M3 禁止状态。

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
- `taskpack/PACKAGE_MANIFEST.v1.0.6.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.4.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.3.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.2.json`（不可变控制前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定顺序逐 run 推进，一次最多解决一个 stage。历史 T0702 Beta 受控 main
交付不是最终发布，且其失败 receipt 保持不可变。Owner 现已明确授权受控完成 Stage 7：先交付已验证
diagnostic repair，再按 exact main SHA 串行执行新的 first-attempt Beta；禁止 GitHub rerun，Beta
保持零 Gmail mutation，真实 Beta PASS 前不得进入 M3，M3/Blue-Green 不等待自然日。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
