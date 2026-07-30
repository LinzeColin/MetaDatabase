# ABD 开发交接

## 当前目标

在 `codex/abd-v0001-s09-p01` 完成本地 S09/P01；Stage S09 未完成前不上传 GitHub。

## 当前状态

- S09/P01「通用市场残差基线」已本地签名通过：`EVD-S09-P01.json`。
- 二元、多项、让分、大小和期货均有冻结输入；没有可复现领域增量时残差权重严格为 `0`。
- 仅在显式、可复现并带 SHA-256 证据的领域增量存在时，才允许市场锚定融合；通用残差上限为 `0.35`，市场权重不低于 `0.50`。
- `model:generic_residual` 仍是默认关闭的 scoped flag；本阶段未访问网络、市场、账户、Gmail、OVH 或 Cloudflare，也未生成建议或下单。

## 已验证

- `tests/S09/P01_test.py`：24 passed。
- `AC-S09-P01`：38/38 checks PASS；现有证据复验 PASS。
- 付费/未知依赖扫描 PASS；Task Pack 49/49 PASS。
- 万分之一扰动为 10,000 次冻结十进制重放，`real_time_wait_performed=false`。

## 关键文件

- `generic_residual.py`
- `market_family_registry.json`
- `abd_acceptance/generic_residual.py`
- `machine/evidence/EVD-S09-P01.json`

## 下一步

下一轮只推进 S09/P02（网球与对抗项目模型）。保留 S09/P01 的签名证据和市场优先门；不得运行全量测试、完整回归或真实时间 soak。S09/P04 完成后，再进行整个 S09 的复审并上传 GitHub。
