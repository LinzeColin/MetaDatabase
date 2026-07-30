# Stage 6 Assurance002 — Model Gate Decision

`TSK.x2n.assurance.002 / PH.X2N.6.2` 采用明确的模型功能降级路径完成，而非伪造私有 Gold 质量结果。

| 能力 | 当前 Gate | 公开结论 |
|---|---|---|
| ASR | private Gold 未运行 | disabled |
| OCR | private Gold 未运行 | disabled |
| Vision | private Gold 未运行 | disabled |
| Fusion | 合成 schema/red-team 通过，模型未运行 | disabled |
| Classification | private Gold/calibration 未运行 | suggestion-only，`auto_classify=false` |

当前 Assurance runner 对四种私有 eval 入口都在空隔离运行时验证 Fail Closed；它不会探测或读取 Owner
数据。现有 38 个 ASR/OCR/Vision/Fusion/Taxonomy 合成测试覆盖质量门边界、prompt injection、provenance、
预算、缓存、Owner taxonomy 与 review。该 Run 的聚合回执不含 Gold 内容、路径、凭据、媒体 URL 或模型输出。

下一独立 Task 是 `TSK.x2n.assurance.003 / PH.X2N.6.3`。直接 MVP 部署、运行与 online smoke 仍严格在
`TSK.x2n.assurance.005`；不插入 Alpha、Beta、固定观察期或 soak。
