# MooMooAU Archive

Implementation target: `LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`.

当前控制包为 `1.0.34`。它直接继承不可变 v1.0.33，不改变 v1.0.1 冻结的产品目标、
34 条需求、34 个最终验收、58-task DAG、追踪矩阵、Kill Criteria 或十条不变量。

唯一当前跨维度状态入口是 `machine/status/latest.json`，由
`machine/tools/build_delivery_status.py` 确定性生成并只读校验。当前事实：

- 58/58 task evidence 结构与绑定有效，58/58 本地或合成机制有证据；
- 冻结任务图正式完成 7/58，最终 Acceptance 0/34，production workflow 15；
- protected Oracle 已执行 5/43：T0701–T0704 PASS，T0705 当前 FAILED；
- T0705 十三次失败 run 分别绑定十三个不同 exact-main head，均为 attempt 1、rerun 0；
- T0705/S7AC-005 尚未关闭；十三个 protected 失败 head 与两个独立 pre-Secret
  失败 head 均已冻结；只授权一个 Trash-confirmation successor；
  Stage 7、生产健康与最终发布均未完成。

T0704 首次 exact-main head 仍由不可变 failed-attempt ledger 固定为失败，未重跑。唯一新修复
head 的 authority、Blue-Green 与 identity cleanup 均 PASS；受保护结果复用并恢复既有
candidate Processed 与 Timeline snapshot，保持 processed-current 不变，以完整 reconciliation
difference 0 收敛到恰好一个可恢复 age-encrypted latest Timeline。

独立聚合核验没有解密私有数据，只确认当前修复新增一个加密 Timeline state commit；
Raw、Processed、candidate、snapshot 与 processed-current 均无新增对象。repair 的 Gmail
mutation 为 0。公开 receipt 不包含私有仓 locator/ID、Gmail ID、精确邮箱数量或金融值。

T0705 九次 launch 都已合入并各执行一次。第九次运行的 authority 与 identity cleanup PASS，
protected GA 仍在 coarse `FIRST_IMPORT_POINTER_FETCH` 失败，live schedule hold SKIPPED。只读
核验确认第九次没有新增 private commit 或 Gmail mutation。随后对相同 pointer 的只读 live A/B
回放证明：Contents metadata 的 path/size/blob SHA 有效，但 Contents raw-media 表示可返回
非 age、非 canonical body；同一 metadata SHA 定址的 Git Blobs API 则返回与 size、age envelope
和 canonical Git blob SHA 全部一致的 ciphertext。该表示层漂移是本次 recovery 的直接证据，
不依赖受保护 exception。一次性 authority 和 production enablement 已清除，九个失败 head
永久禁止 rerun/redispatch。

v1.0.28 exact-main 候选已通过 authority context，但 workflow 同构的 Ruff format gate 在进入
protected Environment 前拒绝一个未格式化文件。v1.0.29 formatter successor 随后因 one-shot
expected-head 变量位于 Environment scope、而 pre-Environment authority job 无法读取而在
checkout 前失败。两次 pre-Secret failure 的 Secret、Gmail、私库与 mutation 均为 0，两个 head
均已冻结且变量已清理。v1.0.30 将 authority 修复为 repository scope后，candidate validation、
authority consumption、protected Environment、精确 App scope、Gmail OAuth 与 checkpoint
recovery 均通过；随后因 workflow_dispatch 的真实墙钟早于同日 04:30，在
`SCHEDULE_PLANNING` 确定性失败。Gmail API、完整 Raw 读取和全部 mutation 均为 0，变量已删除，
该第十个 protected head 已冻结。

v1.0.31 的第十一个 exact-main attempt 已通过 candidate validation、repository-scope authority
和 protected Environment，但在 `GITHUB_APP_TOKEN` 阶段被拒绝。固定历史 planning clock 被误用
为 `ProductionBootstrap` 的安全时钟，因而签出相对真实 job 时间已过期的 App JWT。该 attempt
没有进入 repository resolution、Gmail OAuth、私有仓或 Gmail 调用，全部 mutation 为 0；
一次性变量已删除，失败 head 永久冻结。

v1.0.32 的 split-clock attempt 已通过 authority、candidate validation、live-clock authentication、
精确 App repository scope 与 Gmail OAuth；首个 verified candidate 完成 Raw/Processed 恢复和
二次验证并取得确定 Trash 结果。下一 candidate 写入 Raw 后在 `RAW_RECOVERY` 失败，Timeline 与
checkpoint 均未提交。只读 A/B 证明 Contents raw-media 表示与 metadata size/canonical SHA
不一致，而 metadata SHA 定址的 Git Blob 同时通过 response SHA、size、age 与 canonical SHA。

v1.0.33 已把 Raw recovery 切换到 Contents metadata 定址的精确 Git Blob，并通过 authority、
candidate validation、live-clock authentication、精确 App repository scope、Gmail OAuth 以及
canonical Raw/Processed recovery；随后在 `TRASH_MUTATION` 阶段失败。远端只观察到加密
Raw、Processed 与 current-pointer 写入，Timeline 与 checkpoint 均未提交。公开失败阶段、远端
拓扑和有界只读 Gmail representation probe 不足以证明精确线上根因，因此保持 unclaimed；该
第十三个 protected head 已冻结，禁止 rerun/redispatch。

v1.0.34 只把 Gmail label confirmation 固定为 content-excluding
`fields=id,labelIds`；若 exact-message Trash 返回异常或非 200，mutation retry 为 0，只允许一次
只读 label 确认，只有明确包含 `TRASH` 才收敛为已 Trash，否则保持 UNKNOWN 并 fail closed。
当前 Run Contract 只处理 T0705：总 delivery 最多 17，十五次 launch 已消耗 15；总 protected
rehearsal dispatch 最多 14，十三个失败 attempt 已消耗 13；candidate-preflight dispatch 最多
6，已消耗 5；只剩一个新 exact-main Trash-confirmation `SCHEDULE_REHEARSAL` 和后续
receipt/schedule closure delivery。Raw/Processed Git Blob recovery、metadata quarantine、
second verification、ACTIVE/SAFE_DEFERRED、exact-message Trash budget 1、单一 Timeline
replacement 与 checkpoint-last 顺序不变。rehearsal 不声称平台 schedule event。

Stage 7 不设置固定日历等待、Soak 或观察窗口。T0705 用 Fake Clock、历史回放、Fixture 与故障
注入即时覆盖时间、认证时钟隔离和表示层分支，再用一次受保护 workflow_dispatch 验证与生产相同的
`RunTrigger.SCHEDULE` 路径及 `04:30 Australia/Sydney` 目标；只有 PASS receipt 绑定后才启用
已提交 live schedule。T0706 与后续阶段仍需新的单任务 Run Contract。

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
