# MooMooAU v1.0.31 — T0705 deterministic historical-clock recovery

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.30。十个 protected GA
失败 head、一个 pre-Secret candidate-validation 失败 head 和一个 pre-checkout
authority-context 失败 head 均永久禁止 rerun/redispatch；本包不进入 T0706，也不构成最终发布。

v1.0.30 已通过 workflow 同构 candidate validation、repository-scope one-shot authority、
protected Environment、精确 GitHub App repository scope、Gmail OAuth 与加密 checkpoint
recovery，随后在 `SCHEDULE_PLANNING` 确定性失败。公开 job 时间戳与已提交 RunPlanner 分支证明：
workflow_dispatch 当时的真实墙钟尚未到同日 `04:30 Australia/Sydney`，因此产生负 delay。
Gmail API 调用、完整 Raw 读取及全部 mutation 均为 0；一次性 repository variable 已删除。
该失败由独立 ledger/schema 与精确 SHA-256 绑定。

v1.0.31 不修改 canonical Git Blob recovery 或任何数据面行为。它只在
`workflow_dispatch` rehearsal 中注入固定历史时钟 `2026-07-26T01:00:00Z`，复用生产
`RunPlanner(SCHEDULE)` 即时验证同一 04:30 分支；已提交 live schedule 保留真实时钟。

本地验收使用 Fake Clock、历史回放、Fixture 和故障注入，执行 workflow 同构 Ruff
format/check、strict mypy、聚焦测试及只读包/状态/组合验证。不设置 Soak、观察期、真实时间等待、
人工审批或全量测试前置。随后只允许一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 并启用已提交的
`04:30 Australia/Sydney` live schedule。
