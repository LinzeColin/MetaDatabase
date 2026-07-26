# MooMooAU v1.0.33 — T0705 Raw canonical Git Blob recovery

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.32。十二个 protected GA
失败 head、一个 pre-Secret candidate-validation 失败 head 和一个 pre-checkout
authority-context 失败 head 均永久禁止 rerun/redispatch；本包不进入 T0706，也不构成最终发布。

v1.0.32 已通过 workflow 同构 candidate validation、repository-scope one-shot authority、
live-clock GitHub App authentication、精确 repository scope 和 Gmail OAuth。首个 verified
candidate 完成 Raw/Processed 远端恢复与二次验证并取得确定 Trash 结果；下一 candidate 在
Raw 写入后于 `RAW_RECOVERY` 失败，Timeline 与 checkpoint 均未提交。只读 A/B 证明 Contents
raw-media 表示与元数据声明的 size 和 canonical Git SHA 不一致，而元数据 SHA 定址的 Git
Blob 同时通过 response SHA、size、age envelope 与 canonical Git SHA 校验。

v1.0.33 只把新 Raw 对象的恢复改为 Contents 元数据校验后读取精确 Git Blob bytes；它不信任
Contents inline 或 raw-media body，并对 revision drift、编码、size、age 与 canonical SHA
全部 fail closed。workflow_dispatch rehearsal 的 `RunPlanner(SCHEDULE)` fixture 调整为
`2026-07-26T19:00:00Z`，晚于全部已知数据效果；安全、认证、OAuth、容量与证据时间仍使用
live UTC，live schedule 不注入 fixture。

本地验收使用 Fake Clock、历史回放、Fixture 和故障注入即时验证，再执行 workflow 同构 Ruff
format/check、strict mypy、聚焦测试及只读包/状态/组合验证。不设置 Soak、观察期、真实时间
等待、人工审批或全量测试前置。随后只允许一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 并启用已
提交的 `04:30 Australia/Sydney` live schedule。
