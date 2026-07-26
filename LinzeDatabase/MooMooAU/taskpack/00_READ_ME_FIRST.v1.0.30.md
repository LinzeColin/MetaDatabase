# MooMooAU v1.0.30 — T0705 one-shot authority scope recovery

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.29。九个 protected GA
失败 head、一个 pre-Secret candidate-validation 失败 head 和一个 pre-checkout
authority-context 失败 head 均永久禁止 rerun/redispatch；本包不进入 T0706，也不构成最终发布。

v1.0.29 已经正常 PR/main 交付，但 one-shot expected-head 变量被放在
`moomooau-beta` Environment scope。`ga-authority-gate` 按设计在进入该 Environment 前运行，
因此无法读取该变量并在 checkout 前失败。candidate validation、protected Environment、
Secret、Gmail、私有数据仓与全部 mutation 均未到达；两个变量作用域已清理。该失败由独立
ledger/schema 和精确 SHA-256 绑定。

v1.0.30 不修改 canonical Git Blob recovery 或任何数据面行为，只把外部一次性交付约束修正为：
合并后以 repository variable 绑定精确 main SHA，authority 消耗后立即删除。workflow 继续拒绝
全部已冻结 head；Secret 仍只存在于既有 protected Environment。

本地验收使用 Fake Clock、历史回放、Fixture 和故障注入，执行 workflow 同构的 Ruff
format/check、strict mypy、聚焦测试及只读包/状态/组合验证。不设置 Soak、观察期、真实时间等待、
人工审批或全量测试前置。随后只允许一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 并启用已提交的
`04:30 Australia/Sydney` schedule。
