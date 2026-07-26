# MooMooAU v1.0.27 — T0705 App-scope activation 恢复候选

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.26。八个 protected GA
失败 head 均固定为 attempt 1、rerun 0，永久禁止 rerun/redispatch；不进入 T0706，也不构成
最终发布。

第八次运行通过 authority 与 plaintext cleanup，但仍在固定
`FIRST_IMPORT_POINTER_FETCH` 子阶段失败。独立后验确认运行窗口 private commit 0、Gmail
mutation 0，因此没有新增 Processed、Timeline 或 checkpoint。protected exception 未被读取，
精确线上根因保持 `UNKNOWN`。

Owner 在该次运行结束后确认现有 GitHub App 已链接唯一 private 数据仓。这是新的外部状态，不
倒推解释第八次失败。v1.0.26 的 pointer raw-media 绑定已经交付并随失败 head 冻结；本候选不再
改变数据路径。

唯一恢复动作是执行既有 fail-closed bootstrap：installation token 必须在 Gmail credential
exchange 前证明精确 repository scope 只包含配置中的唯一 private 数据仓，并刷新实时容量。
任何 scope 缺失、额外仓库、ID 不匹配、非 private 或容量验证失败都在 Gmail 前停止。

剩余授权严格为一个受控 main 交付和一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 交付并启用
已提交的 `04:30 Australia/Sydney` schedule。rehearsal 不伪称平台 schedule event。
