# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前控制包为 `1.0.23`。它直接继承不可变 v1.0.22，不改变 v1.0.1 冻结的产品目标、
34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill Criteria 或十条不变量。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成并只读校验。当前事实：

- 58/58 task evidence 结构与绑定有效，58/58 本地或合成机制有证据；
- 冻结任务图正式完成 7/58，最终 Acceptance 0/34，production workflow 4；
- protected Oracle 已执行 5/43：T0701–T0704 PASS，T0705 当前 FAILED；
- T0705 四次失败 run 分别绑定四个不同 exact-main head，均为 attempt 1、rerun 0；
- T0705/S7AC-005 尚未关闭；一个新 closed-enum phase-diagnostic attempt 已授权但未运行；
  Stage 7、生产健康与最终发布均未完成。

T0704 首次 exact-main head 仍由不可变 failed-attempt ledger 固定为失败，未重跑。唯一新修复
head 的 authority、Blue-Green 与 identity cleanup 均 PASS；受保护结果复用并恢复既有
candidate Processed 与 Timeline snapshot，保持 processed-current 不变，以完整 reconciliation
difference 0 收敛到恰好一个可恢复 age-encrypted latest Timeline。

独立聚合核验没有解密私有数据，只确认当前修复新增一个加密 Timeline state commit；
Raw、Processed、candidate、snapshot 与 processed-current 均无新增对象。repair 的 Gmail
mutation 为 0。公开 receipt 不包含私有仓 locator/ID、Gmail ID、精确邮箱数量或金融值。

T0705 四次 launch 都已合入并各执行一次。第四次运行的 authority 与 identity cleanup PASS，
但 protected GA FAILED，live schedule hold SKIPPED。独立后验只确认六个新增、可远端恢复且
具有 age magic 的加密对象，覆盖 Raw、Processed 与 current pointer；Timeline snapshot/manifest、
Timeline state 和 checkpoint 均未改变。active Moomoo candidate 仍在 Trash 外；一次性 authority
和 production enablement 已清除。四个失败 head 永久禁止 rerun/redispatch。

protected 输出没有公开 exact runtime exception，因此精确 root cause 保持 UNKNOWN。唯一可证
边界是运行已越过 Raw/Processed/current persistence、尚未产生 Timeline snapshot 或 checkpoint。
没有 exact pre-dispatch baseline 与 protected mutation trace，因此不声称 Gmail mutation API
是否到达或精确消息级变化。

当前 successor Run Contract 只处理 T0705：总 delivery 最多 6，四个 launch 已消耗 4；总
rehearsal dispatch 最多 5，四个失败 attempt 已消耗 4。只剩一个新 exact-main protected
`SCHEDULE_REHEARSAL`、rerun 0，以及后续 receipt/schedule closure delivery 1。唯一代码变化
是沿既有路径记录最后进入的闭合枚举阶段；公开失败结果禁止异常文本、URL、标识符、计数、邮箱
事实、私仓定位与 Secret。metadata quarantine、Raw/Processed recovery、second verification、
ACTIVE/SAFE_DEFERRED、exact-message Trash、单一 Timeline replacement 与 checkpoint-last
行为不变。入口复用现有 `moomooau-beta` 八个精确
Secret 名称，先用已安装且已连接私有数据仓的 GitHub App 刷新实时容量，再允许 Gmail
credential exchange。只有确定性验证来源可完整读取；Raw 与 Processed 远端恢复和二次验证后，
精确 `messages.trash` budget 最多 1；唯一最新 Timeline 与 checkpoint-last 必须远端恢复。
rehearsal 不声称平台 schedule event。

Stage 7 不设置固定日历等待。T0705 用一次受保护 workflow_dispatch 验证与生产相同的
`RunTrigger.SCHEDULE` 路径及 `04:30 Australia/Sydney` 目标；只有 PASS receipt 绑定后才启用
已提交 live schedule。T0706 与后续阶段仍需新的单任务 Run Contract。

Authoritative artifacts:

- `machine/contracts/requirements.json`
- `machine/contracts/acceptance_contract.json`
- `machine/contracts/task_graph.json`
- `machine/contracts/delivery_status_model.json`
- `machine/status/latest.json`
- `machine/stages/S7/reviews/t0705/post-processed-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/label-replay-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/repair-attempt-ledger.json`
- `machine/stages/S7/reviews/t0705/attempt-ledger.json`
- `machine/stages/S7/reviews/t0704/attempt-ledger.json`
- `machine/stages/S7/reviews/t0704/execution-receipt.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.23.json`
- `taskpack/PACKAGE_MANIFEST.v1.0.22.json`（不可变直接前序）
- `taskpack/PACKAGE_MANIFEST.v1.0.1.json`（不可变历史基线）

Codex 开发线程必须按既定顺序逐 run 推进，一次最多解决一个 stage。本轮只推进
Stage 7/T0705，停止在 T0706 前；受控 main launch/closure 交付都不是最终发布。

Pursuing goal: Build MooMooAU Archive as a zero-collateral, cloud-only deterministic system that at 04:30 Australia/Sydney archives every deterministically verified inbound Moomoo-related Gmail message into the single private GitHub database with age-encrypted Raw and Processed data, replaces exactly one encrypted latest timeline, moves only that verified source message to Trash after remote recovery verification, and remains fully maintainable through the Codex development thread without local persistence, special Codex Automation behavior, or manual routine work.
