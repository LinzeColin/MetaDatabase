# Stage 6 Assurance002 Run Contract

## Identity

- Task: `TSK.x2n.assurance.002`
- Phase: `PH.X2N.6.2`
- Run: `RUN-X2N-S06-A002`
- Base: `bc9bd26d425bcee524981d74fa89d2315d966ec8`

## Single-task scope

本 Run 只完成模型能力、安全和 System Card 的可复验 gate decision。现有 ASR、OCR、Vision、
Fusion 与 Classification 的私有评测入口、合成红队、provenance、缓存和预算合同会被复验；
不会读取 Owner 私有 Gold Set、模型、媒体、Profile、凭据或运行时数据。

Owner 私有 Gold 未在本 Run 执行时，ASR/OCR/Vision 必须保持禁用，Fusion 必须保持 model-not-run，
Classification 必须保持 suggestion-only，automatic classification 必须为 false。该禁用决策是可发布的
功能降级记录，不是模型质量通过声明。

## Acceptance mapping

| Acceptance | 本 Run 的可复验证据 |
|---|---|
| `ACC.x2n.ai.001–003` | 私有 Gold 缺失的 ASR/OCR/Vision eval 均 Fail Closed；对应 Flag 为 disabled |
| `ACC.x2n.ai.004` | Fusion schema、grounding、prompt injection 和 side-effect red team 合同通过；model call 为 0 |
| `ACC.x2n.ai.005` | Owner-only taxonomy 与 suggestion-only guard 通过；AI 一级分类 mutation 为 0 |
| `ACC.x2n.ai.006` | 分类 calibration/quality 未运行时 `auto_classify=false`，仅 Owner review 的 suggestion 可用 |
| `ACC.x2n.ai.007` | Provider/provenance/cache/budget/cloud-zero 合同通过 |
| `ACC.x2n.rel.002` | Dataset contract、全部显式 capability 状态、red team 和 System Card 汇总一致 |

## Stop conditions

任一模型能访问工具、Secret、配置、网络或平台；任一缺失 Gold 输入未 Fail Closed；任一模型 Feature Flag
提前开启；或自动分类精度未通过而 Flag 仍开启，全部 Fail Closed。

## Boundary and rollback

本 Run 的模型、平台、外网、云上传、Notion、账号、真实媒体、Private-Database client、`tmutil` 与物理删除
均为 0/`NOT_RUN`。不存在 Alpha、Beta、固定 30 日健康观察或 soak。实际 MVP deploy/run/online smoke
只属于 `TSK.x2n.assurance.005`。

回滚只需保持所有 model feature flag 为 false，并保留 Classification 的 suggestion-only 与 Owner review；
本 Run 不创建外部状态或私有数据。
