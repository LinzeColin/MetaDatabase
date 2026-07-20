# Model System Card — Foundation005 executable baseline

## 当前结论

本文件只登记模型 Assurance runner 的可执行骨架，不登记任何模型能力已经实现。
`x2n-synthetic-model-contract-v1@1.0.0` 是公共合成 Dataset Contract；它不含真实账号、
私人正文、凭据、媒体 URL、本机路径或模型输入输出。

| 能力 | Foundation005 状态 | Feature Flag | 启用前门禁 | 失败降级 |
|---|---|---:|---|---|
| Dataset Contract | `PASS` | n/a | Schema/version/synthetic boundary | 阻断模型流水线 |
| ASR | `NOT_RUN_FEATURE_DISABLED` | off | 后续 ASR Task Acceptance | 禁用 ASR，保留原任务可恢复状态 |
| OCR | `NOT_RUN_FEATURE_DISABLED` | off | 后续 OCR Task Acceptance | 禁用 OCR，不生成伪证据 |
| Fusion | `NOT_RUN_FEATURE_DISABLED` | off | 后续 Fusion Task Acceptance | 仅保留已验证的单项证据 |
| Classification | `NOT_RUN_FEATURE_DISABLED` | off | 分类质量与安全 Acceptance | 转人工 Review |
| Automatic classification | `DISABLED_PENDING_ACC.x2n.ai.006` | off | `ACC.x2n.ai.006=PASS` | 不自动落一级或二级分类 |
| Red Team | `CONTRACT_PASS_MODEL_NOT_RUN` | off | 后续真实模型 Red Team | 阻断受影响能力 |

## 不变安全边界

- AI 永远不得创建一级分类；一级分类只能来自 Owner 已存在 Taxonomy。
- Dataset Contract 通过不代表 ASR/OCR/Fusion/Classify 的质量、延迟、成本或安全通过。
- Runner 不读取模型 Key，不访问模型 Endpoint，不持久化 Prompt、媒体或私人正文。
- 任一能力状态缺失、Dataset 漂移、Feature Flag 提前开启或 Red Team 未明确时 Fail Closed。

## 本轮证据

- Dataset：`packages/test-fixtures/ci/v1/model_eval_dataset.json`
- Policy：`machine/policy/ci_gate_manifest.json`
- Runner：`scripts/ci/ci_baseline.py model`
- Task receipt：`evidence/ci/TSK.x2n.foundation.005.json`
- 模型调用 0；远端 CI、真实模型和 `G1`：全部 `NOT_RUN`
