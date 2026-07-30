# ABD 开发交接

## 当前目标

在 `codex/abd-v0001-s09-p01` 按 Phase 继续完成 S09；S09/P03 已完成本地签名，S09/P04 与整个 S09 复审前不得上传 GitHub。

## 当前状态

- S09/P01「通用市场残差基线」保持已签名通过：`machine/evidence/EVD-S09-P01.json`。无可复现领域增量时残差权重严格为 `0`；市场权重不低于 `0.50`。
- S09/P02「网球与对抗项目模型」保持已签名通过：`machine/evidence/EVD-S09-P02.json`。特征只选择 `known_at <= decision_at` 的最新值；缺失、未来或未确认参赛状态回退为市场基线。
- S09/P03「足球与得分项目模型」已签名通过：`machine/evidence/EVD-S09-P03.json`。`score_models.py` 提供 Poisson、Dixon--Coles、Skellam 与负二项分布的 50 位十进制概率质量及显式尾部；`football_model.py` 使用冻结的联赛层和球队层残差生成得分输入。
- 足球模型只在全部特征于建议时已知、参赛状态确认且所有有限支持尾部不高于 `1e-12` 时融合残差；未来、缺失、未确认或高尾部均回退为原始市场向量，残差权重为 `0`。
- 本 Phase 仅使用冻结合成输入。未访问网络、真实市场、账户、Gmail、OVH 或 Cloudflare；未生成建议或订单，未部署或激活生产，现金新增支出为 `A$0.00`。

## 已验证

- `tests/S09/P03_test.py`：35 passed（仅此 Phase 的定向测试）。
- `AC-S09-P03`：39/39 checks PASS；现有证据复验 PASS。
- 付费/未知依赖扫描 PASS；Task Pack 49/49 PASS。
- 100 次冻结重放与 10,000 次冻结十进制不利扰动均通过；`real_time_wait_performed=false`，未进行真实时间 soak。

## 关键文件

- `score_models.py`
- `football_model.py`
- `distribution_tests.json`
- `abd_acceptance/score_football_models.py`
- `machine/tests/fixtures/S09_P03.json`
- `machine/evidence/EVD-S09-P03.json`

## 下一步

下一轮只推进 S09/P04（赛马、篮球、棒球及小众回退）。保持 S09/P01/P02/P03 的已签名证据、市场强先验、时间边界、尾部阈值和零残差回退门；不得运行全量测试、完整回归或真实时间 soak。S09/P04 完成后，再执行整个 S09 复审并上传 GitHub。
