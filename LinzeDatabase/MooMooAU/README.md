# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前控制包为 `1.0.15`。它直接继承不可变 v1.0.14，不改变 v1.0.1 冻结的产品目标、
34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill Criteria 或十条不变量。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成并由
`machine/tools/validate_delivery_status.py` 只读校验。当前事实：

- 58/58 task evidence 结构与绑定有效，58/58 本地或合成机制有证据；
- 冻结任务图正式完成 7/58，最终 Acceptance 0/34，production workflow 0；
- protected Oracle 已执行 3/43：T0701 Alpha、T0702 Raw-only Beta、T0703 M3 均 PASS；
- protected workflow runs 18，GitHub rerun 0；
- T0703/S7AC-003 已关闭，但 T0704、Stage 7、生产健康与最终发布均未完成。

T0702 的完整串行账本区分一次 Secret 前 context 拒绝与十一次 protected attempt 1；最终
Raw-only Beta 证明 Raw remote recovery 100%、Gmail mutation 0 与 identity cleanup PASS。

T0703 的六个失败 exact-main head 保持不可变且不得 rerun/redispatch。第五次留下一个可恢复
Processed lineage 与当时未精确归因的 Gmail Trash 聚合变化；第六次在 `PROCESSED_PLAN`
零新增效果停止。第七个不同 exact-main head 的 attempt 1 已通过 authority、加密历史 Gmail
label 零写入 reconciliation 与 identity cleanup。受保护聚合回执证明 Raw+Processed remote
recovery 100%、第二次验证、既有未知 mutation 已调和、当前运行 source/collateral mutation 0
与 Timeline publish 0。独立运行前后核验确认 private repository head、tree、路径计数和 Gmail
Trash 聚合不变，且不披露 private locator 或精确邮箱数量。

当前 Run Contract 只允许一份 v1.0.15 代码与证据闭合交付。M3 dispatch、rerun、Secret 读取、
完整 Raw 读取、Gmail/private repository/Processed/Timeline/schedule 数据面预算均为 0。
任何 T0703 head 都不得再次运行。进入 T0704 必须建立新的显式 Run Contract。

Stage 7 不设置 M3 七天或 Blue-Green 十四天固定日历等待；后续阶段仍必须逐个满足真实受保护
确定性证据、前序、安全与容量门。GA 仍须真实观察一次 04:30 Australia/Sydney 调度。

Authoritative artifacts:

- `machine/contracts/requirements.json`
- `machine/contracts/acceptance_contract.json`
- `machine/contracts/task_graph.json`
- `machine/contracts/delivery_status_model.json`
- `machine/status/latest.json`
- `machine/stages/S7/reviews/t0703/attempt-ledger.json`
- `machine/stages/S7/reviews/t0703/execution-receipt.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.15.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.14.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定顺序逐 run 推进，一次最多解决一个 stage。本轮只关闭
Stage 7/T0703，停止在 T0704 前；受控 main 证据交付不是最终发布。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
