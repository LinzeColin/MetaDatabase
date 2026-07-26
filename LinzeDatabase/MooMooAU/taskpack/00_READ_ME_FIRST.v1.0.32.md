# MooMooAU v1.0.32 — T0705 security-clock decoupling recovery

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.31。十一个 protected GA
失败 head、一个 pre-Secret candidate-validation 失败 head 和一个 pre-checkout
authority-context 失败 head 均永久禁止 rerun/redispatch；本包不进入 T0706，也不构成最终发布。

v1.0.31 已通过 workflow 同构 candidate validation、repository-scope one-shot authority 与
protected Environment，随后在 `GITHUB_APP_TOKEN` 被 GitHub 拒绝。固定历史 planning clock 被
错误复用为 `ProductionBootstrap` 安全时钟，使 App JWT 相对真实 job 时间已过期。该运行没有进入
repository resolution、Gmail OAuth、私有仓/Gmail 调用或数据面 mutation；cleanup PASS，
one-shot authority 已删除。失败由独立 ledger/schema 和精确 SHA-256 绑定。

v1.0.32 不修改 canonical Git Blob recovery 或数据面行为。GitHub App JWT、installation token、
Gmail OAuth、容量和证据时间全部使用 live UTC；只有 workflow_dispatch rehearsal 的生产
`RunPlanner(SCHEDULE)` 接收 `2026-07-26T13:00:00Z` 历史 fixture。fixture 晚于已知数据效果
上界并位于 Sydney 当日 04:30 之后；live schedule 不注入 fixture。

本地验收使用 Fake Clock、历史回放、Fixture 和故障注入，直接解码 JWT claims 验证安全时钟隔离，
再执行 workflow 同构 Ruff format/check、strict mypy、聚焦测试及只读包/状态/组合验证。不设置
Soak、观察期、真实时间等待、人工审批或全量测试前置。随后只允许一个新 exact-main attempt-1
`SCHEDULE_REHEARSAL`，rerun 0。protected PASS 后才允许 receipt/schedule closure 并启用已提交的
`04:30 Australia/Sydney` live schedule。
