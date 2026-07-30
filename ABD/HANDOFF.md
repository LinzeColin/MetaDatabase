# ABD 开发交接

## 当前目标

在 `codex/abd-v0001-s09-p01` 按 Phase 继续完成 S09；S09/P02 已完成本地签名，S09/P04 与整个 S09 复审前不得上传 GitHub。

## 当前状态

- S09/P01「通用市场残差基线」保持已签名通过：`machine/evidence/EVD-S09-P01.json`。无可复现领域增量时残差权重严格为 `0`；市场权重不低于 `0.50`。
- S09/P02「网球与对抗项目模型」已签名通过：`machine/evidence/EVD-S09-P02.json`。`tennis_model.py` 仅使用场地动态评级、发/接发、休息/旅行和已确认参赛状态；`combat_model.py` 仅使用动态评级、防守指标、休息/旅行和已确认参赛状态。
- 两个模型均只选择 `known_at <= decision_at` 的最新特征；缺失、未来或未确认参赛状态都会回退到原始市场向量，残差权重为 `0`。
- 本 Phase 仅使用冻结合成输入。未访问网络、真实市场、账户、Gmail、OVH 或 Cloudflare；未生成建议或订单，未部署或激活生产，现金新增支出为 `A$0.00`。

## 已验证

- `tests/S09/P02_test.py`：31 passed（仅此 Phase 的定向测试）。
- `AC-S09-P02`：39/39 checks PASS；现有证据复验 PASS。
- 付费/未知依赖扫描 PASS；Task Pack 49/49 PASS。
- 100 次冻结重放与 10,000 次冻结十进制不利扰动均通过；`real_time_wait_performed=false`，未进行真实时间 soak。

## 关键文件

- `tennis_model.py`
- `combat_model.py`
- `feature_availability.json`
- `abd_acceptance/tennis_combat_models.py`
- `machine/tests/fixtures/S09_P02.json`
- `machine/evidence/EVD-S09-P02.json`

## 下一步

下一轮只推进 S09/P03（足球与分布测试）。保持 S09/P01/P02 的已签名证据、市场强先验、时间边界和零残差回退门；不得运行全量测试、完整回归或真实时间 soak。S09/P04 完成后，再执行整个 S09 复审并上传 GitHub。
