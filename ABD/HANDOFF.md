# ABD 开发交接

## 当前目标

在隔离 worktree `codex/abd-v0001-s10-p01` 按冻结 Task Pack 推进 ABD `v0.0.0.1` 的 S10。S10/P01 与 S10/P02 均已完成本地签名证据；下一轮只能推进 S10/P03，不能开始 S10/P04、S10 整体复审或 GitHub 阶段上传。

## 当前状态

- S09 已完成整体复审并合并；当前 S10 worktree 保持隔离，主工作树及其他项目 worktree 均未触碰。
- S10/P01 已签名通过：`machine/evidence/EVD-S10-P01.json`，下一状态为 `S10/P02_READY_NOT_STARTED`。其时间交叉验证只使用冻结合成输入，校准结论不构成推荐、下注、订单或收益承诺。
- S10/P02 已签名通过：`machine/evidence/EVD-S10-P02.json`（SHA-256 `1481efc71fcc185c57a06ddee11d3e0015e534b2084cd90b43dda8ef55fcaa69`），下一状态为 `S10/P03_READY_NOT_STARTED`。
- `uncertainty.py` 以完整时间 block 作为重采样单元，用固定 LCG 的高位映射避免低位取模产生固定置换。运行时精确执行 1,000 次、评测精确执行 2,000 次分块重采样，并按第 10 百分位得到保守概率；结果绝不高于未校正基准概率，且固定 probe 上单调不减。
- 冻结 fixture 的运行时保守概率为 `0.615`、评测保守概率为 `0.615625`；这只是合成 fixture 的可复现输出，不是市场概率、投资/博彩建议或收益预测。
- P02 的 `bootstrap_manifest.json` SHA-256 为 `7db203809f881696db69ff9a0857157e6e87b46d035c0ae1177cbc172584591c`。它绑定 P01 已签名 receipt、冻结 seeds、block digest 与每次重采样分布摘要。
- `abd_acceptance/budget.py` 仅将 `uncertainty` 加入任务包根级本地源码白名单；未知第三方导入仍失败关闭。P01 现有证据已在该共享扫描器变更后复核 PASS。
- `financial_target_status` 仍为 `UNVERIFIED_NOT_GUARANTEED`；没有真实资金、账户、订单、TAB/Gmail、OVH、Cloudflare 或生产部署/激活。

## 已验证

- 冻结 Task Pack 核心事实文件与原始包逐一一致；Task Pack 静态校验 `49/49 PASS`。
- `tests/S10/P02_test.py` 定向测试：`22 passed`。覆盖固定重放、非退化 block 分布、1,000/2,000 次数、10% 分位、保守不抬升、单调性、±0.0001 边界、输入/manifest/P01 receipt/evidence-index 篡改、回滚与无外部能力边界。
- 付费/未知依赖扫描 PASS；无外部访问或账单操作。
- `AC-S10-P02` 候选预检：`30/30 PASS`；写入签名证据后的带报告验证：`34/34 PASS`；`--verify-existing AC-S10-P02`：PASS，且严格要求 evidence index 的 artifact SHA 与 receipt 一致。
- 未执行全量测试、完整回归或真实时间 soak；上述 1,000/2,000 次是 Task Pack 所要求的本地 CPU 分块重采样，不依赖真实时间或外部服务。

## 关键文件

- `calibration.py`
- `temporal_cv.py`
- `calibration_report.json`
- `uncertainty.py`
- `bootstrap_manifest.json`
- `abd_acceptance/temporal_calibration.py`
- `abd_acceptance/uncertainty.py`
- `abd_acceptance/__main__.py`
- `abd_acceptance/budget.py`
- `machine/tests/fixtures/S10_P01.json`
- `machine/tests/fixtures/S10_P02.json`
- `tests/S10/P01_test.py`
- `tests/S10/P02_test.py`
- `machine/evidence/EVD-S10-P01.json`
- `machine/evidence/EVD-S10-P02.json`
- `machine/evidence/EVD-S10-P02_rollback.json`

## 未解决风险

- S10/P03、S10/P04、S10 整体复审及 GitHub 阶段上传尚未开始，不能被 P01/P02 的 PASS 替代。
- 真实市场、真实账户、TAB/Gmail 证据归档、OVH、Cloudflare 与生产上线均未验证、未部署且不应据此推断完成。

## 下一步

下一次 run 严格只处理 S10/P03「十进制定点权威计算」的任务包输出、定向验收和连续证据。保持零新增现金、无真实时间 soak、无全量测试/完整回归；在四个 S10 phase 全部完成并通过整体复审前不得上传 GitHub 或宣称上线。
