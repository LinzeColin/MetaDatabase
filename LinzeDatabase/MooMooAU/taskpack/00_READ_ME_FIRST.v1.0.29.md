# MooMooAU v1.0.29 — T0705 format-preflight recovery successor

本包只处理 Stage 7 / T0705 与 S7AC-005，直接继承不可变 v1.0.28。九个 protected GA
失败 head 和一个 pre-Secret candidate-validation 失败 head 均永久禁止 rerun/redispatch；
本包不进入 T0706，也不构成最终发布。

v1.0.28 已完成正常 PR/main 交付，其 exact-main authority context 通过，但确定性的
`ruff format --check` 在进入 `moomooau-beta` protected Environment 前拒绝
`processed_commit.py`。因此该运行没有注入 protected Secret，没有访问 Gmail 或私有数据仓，
也没有产生任何数据面 mutation。失败证据由独立 ledger/schema 与精确 SHA-256 绑定。

唯一运行时代码差异是 Ruff formatter 对 `processed_commit.py` 的规范化输出，不改变
canonical Git Blob recovery 的行为、端点、权限、预算或顺序。其余变更仅限必要的 evidence、
status、schema、hash、package 与 composition 绑定。

canonical recovery 继续只把 Contents 响应用作有界 path/size/blob SHA metadata；Processed
密文必须来自精确 metadata-addressed Git Blobs API base64 body，并在解密前验证 response
SHA、声明与解码 size、age envelope 和 canonical Git blob SHA。Contents inline/raw-media
body 不是密文真源。

本地验收使用 Fake Clock、历史回放、Fixture 和 revision-drift 故障注入，并执行与 workflow
相同的 Ruff format/check、strict mypy 与聚焦测试，不设置 Soak、观察期、真实时间等待或全量
测试前置。随后只允许一个新 exact-main attempt-1 `SCHEDULE_REHEARSAL`，rerun 0。protected
PASS 后才允许 receipt/schedule closure 并启用已提交的 `04:30 Australia/Sydney` schedule。
