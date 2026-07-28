# Model System Card — Stage 6 Assurance002

## Current decision

本卡描述 `RUN-X2N-S06-A002` 的 feature-gate 决策。它不声称任何真实模型、私有 Gold 或模型质量已经
通过。当前所有 model/provider execution 均为 `NOT_RUN`，不会读取私有 Gold Set。

| Capability | Private quality evaluation | Runtime state | Release treatment |
|---|---|---|---|
| ASR | `NOT_RUN` | disabled | 保留文本/任务恢复，不生成转录 |
| OCR | `NOT_RUN` | disabled | 不生成 OCR 文本 |
| Vision | `NOT_RUN` | disabled | 不生成视觉描述 |
| Fusion | model `NOT_RUN`; synthetic red team passes | disabled | 不生成融合摘要 |
| Classification | `NOT_RUN`; calibration absent | suggestion-only | `auto_classify=false`，Owner review 才可写入 |

## Provenance, safety and limits

- Provider/Model/Snapshot/Prompt/Input provenance、cache identity、预算与 cloud-zero 合同已在合成范围复验；
  这不构成真实 provider 可用性或质量证明。
- Fusion 无工具、文件、网络、Secret 或配置 mutation 能力；恶意正文、OCR、字幕、Unicode/Bidi 和
  secret-shaped 输入均按合成 red team Fail Closed。
- AI 不能创建、启用、删除或合并一级分类；未知或 disabled category 不可被接受。没有 matching private Gold
  calibration 时，automatic classification 永远不能启用。
- Cross-model disagreement 为 `NOT_RUN_FEATURES_DISABLED`，因为没有授权的真实模型可比较。

## Private Gold upgrade path

未来 Owner 可在私有 runtime 提供经审阅、分层并具有 provider/input provenance 的 Gold Set，并显式调用
受限 `x2n eval asr|ocr|vision|classify`。只有独立 Gate 证明质量并留下脱敏聚合回执后，相关 Feature Flag
才可在后续授权 Run 中变更。私有样本、模型输入/输出、媒体、路径和凭据永远不进入公共仓库。

## Release boundary

MVP 可以在 `TSK.x2n.assurance.005` 采用上述 disabled/suggestion-only 功能集直接部署；无需 Alpha、Beta、
固定健康观察或 soak。此 Card 不授予部署、真实模型调用或自动分类权限。
