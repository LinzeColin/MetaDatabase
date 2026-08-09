# ABD 开发交接

## 当前目标

在隔离 worktree `codex/abd-v0001-s11-p01` 按冻结 Task Pack 推进 ABD `v0.0.0.1` 的 S11。当前仅完成并固化 S11/P01；不得在本轮继续 P02，亦不得上传、部署或激活生产。

## 当前状态

- S10 的整体复审已通过并经 [PR #173](https://github.com/LinzeColin/MetaDatabase/pull/173) 合并；当前 worktree 从 `origin/main` 的合并提交 `05baf72f29973d04c8d115170c7aef3f95454008` 创建，主工作树及其他项目 worktree 均未触碰。
- S10 整体复审证据为 `machine/evidence/EVD-S10-STAGE-REVIEW.json`（SHA-256 `d0d00ece08b45943715e300a5cc4cc1818041477b575d074049cbc3ba88c0ce5`）。
- S11/P01 已本地签名通过：`machine/evidence/EVD-S11-P01.json`（SHA-256 `4bf25a1a68e3078f512a7cbf0992285e2890d62b5284de24eefd750390b7e2f8`），下一状态为 `S11/P02_READY_NOT_STARTED`。`friction.py` 只重放冻结合成的价格恶化、拒绝、结算和操作摩擦；滚动 P95 使用保守 upper-nearest-rank，`effective_friction = max(default, rolling_observed_p95)`。正的合成净期望仍只输出 `NO_ORDER_RESEARCH_ONLY`，不生成建议或订单。
- 复审发现的唯一过程缺口（四个已签名 Phase 未预置整体复审合同）已以独立合同、冻结 fixture、离线判定器和回滚 receipt 闭合；`findings.json` 为 `1 resolved / 0 open`。该闭合不修改任何冻结 Phase 基线或放宽证据、数值、风险、安全和来源门。
- S10/P01 已签名通过：`machine/evidence/EVD-S10-P01.json`，下一状态为 `S10/P02_READY_NOT_STARTED`。其时间交叉验证只使用冻结合成输入，校准结论不构成推荐、下注、订单或收益承诺。
- S10/P02 已签名通过：`machine/evidence/EVD-S10-P02.json`（SHA-256 `1481efc71fcc185c57a06ddee11d3e0015e534b2084cd90b43dda8ef55fcaa69`），下一状态为 `S10/P03_READY_NOT_STARTED`。
- S10/P03 已签名通过：`machine/evidence/EVD-S10-P03.json`（SHA-256 `7b848a4e885b5f1b9b31752b88c8b136e1b66f734ed0cdf30926b325bbc0f55c`），下一状态为 `S10/P04_READY_NOT_STARTED`。
- S10/P04 已签名通过：`machine/evidence/EVD-S10-P04.json`（SHA-256 `0700d4af988731fa39fc9506751b993e509da8afa78d63ef951c3bac842a9ed3`），下一状态为 `S10/STAGE_REVIEW_READY_NOT_STARTED`。`robustness_gate.py` 对 12 个冻结合成向量逐项重放概率、阈值、摩擦、时间、赔率、参数最坏值及其组合；任一不利翻转即为 `NO_RECOMMENDATION`。固定报告 SHA-256 为 `2acc10ff3fa55bb63f7739f179a6d702998d5a4d9d3aa35dd1c78b5a07ab8c30`。
- `uncertainty.py` 以完整时间 block 作为重采样单元，用固定 LCG 的高位映射避免低位取模产生固定置换。运行时精确执行 1,000 次、评测精确执行 2,000 次分块重采样，并按第 10 百分位得到保守概率；结果绝不高于未校正基准概率，且固定 probe 上单调不减。
- 冻结 fixture 的运行时保守概率为 `0.615`、评测保守概率为 `0.615625`；这只是合成 fixture 的可复现输出，不是市场概率、投资/博彩建议或收益预测。
- P02 的 `bootstrap_manifest.json` SHA-256 为 `7db203809f881696db69ff9a0857157e6e87b46d035c0ae1177cbc172584591c`。它绑定 P01 已签名 receipt、冻结 seeds、block digest 与每次重采样分布摘要。
- P03 的 `decimal_math.py` 按 50 位 Decimal 处理金额分、概率 `1e-9`、赔率 `1e-6`，概率/赔率向下、摩擦向上和 stake 向 provider 增量向下舍入；`cross_impl_check.py` 以独立表达式重放六个冻结合成向量。固定报告 SHA-256 为 `038b1e9cae3ae7c50ddfd152e0293c257e688132269f7fca0cf1dcd8349026c4`，最大差异为 `0`，所有动作和整数分 stake 一致。
- `abd_acceptance/budget.py` 只将冻结 Task Pack 的根级本地源码（现含 `friction`）加入本地源码白名单；未知第三方导入仍失败关闭。S11/P01 将 dispatcher 与共享依赖扫描器显式排除在 phase-owned receipt 输入哈希之外，避免后续共享运行时演进伪造性地使冻结 phase evidence 失效。
- `financial_target_status` 仍为 `UNVERIFIED_NOT_GUARANTEED`；没有真实资金、账户、订单、TAB/Gmail、OVH、Cloudflare 或生产部署/激活。
- S10 上传前复审修复了两项失败关闭兼容性：S10 可移植性扫描不再包含本机绝对路径字面量；S07 只在 S09 已通过后接受哈希、状态、下一步与发布边界均精确匹配的 S10 整体复审索引。S08 的 legacy successor manifest、helper、合同和 fixture 均重新精确钉住；没有扩展任何来源或风险豁免。

## 已验证

- 冻结 Task Pack 核心事实文件与原始包逐一一致；Task Pack 静态校验 `49/49 PASS`。
- `tests/S11/P01_test.py` 定向测试：`19 passed`；覆盖四类摩擦组成、四个时距段、滚动 P95 / 默认值最大规则、`+0.0001` 摩擦与一档不利赔率、重放哈希、篡改、回滚及无外部能力边界。
- S11/P01 候选预检：`28/28 PASS`；带测试、扫描和 Task Pack 报告的验收：`32/32 PASS`；`--verify-existing AC-S11-P01`：PASS。依赖扫描 PASS、零新增现金；仅执行 S11/P01 定向测试与 S08 legacy compatibility 定向重放，没有全量测试、完整回归或真实时间 soak。
- `tests/S10/P02_test.py` 定向测试：`22 passed`。覆盖固定重放、非退化 block 分布、1,000/2,000 次数、10% 分位、保守不抬升、单调性、±0.0001 边界、输入/manifest/P01 receipt/evidence-index 篡改、回滚与无外部能力边界。
- 付费/未知依赖扫描 PASS；无外部访问或账单操作。
- `AC-S10-P02` 候选预检：`30/30 PASS`；写入签名证据后的带报告验证：`34/34 PASS`；`--verify-existing AC-S10-P02`：PASS，且严格要求 evidence index 的 artifact SHA 与 receipt 一致。
- `tests/S10/P03_test.py` 定向测试：`22 passed`。覆盖固定重放、50 位 Decimal/分/概率/赔率与保守舍入、双实现 `≤1e-12` 与动作/分 stake 精确一致、±`0.0001` 输入、输入/向量/P02 receipt/evidence-index 篡改、回滚与无外部能力边界。
- `AC-S10-P03` 候选预检：`26/26 PASS`；带报告验收：`30/30 PASS`；`--verify-existing AC-S10-P03`：PASS，且严格要求 evidence index 的 artifact SHA 与 receipt 一致。P02 复验仍 PASS。
- `tests/S10/P04_test.py` 定向测试：`28 passed`。覆盖 12 个冻结重放、每一不利维度、组合翻转、边界稳定、基线不建议不可被有利诊断启用、输入/报告/P03 receipt/evidence-index 篡改、回滚与无外部能力边界。
- `AC-S10-P04` 带报告验收：`30/30 PASS`；`--verify-existing AC-S10-P04`：PASS，且严格要求 evidence index 的 artifact SHA 与 receipt 一致。P03 复验仍 PASS。
- 未执行全量测试、完整回归或真实时间 soak；上述 1,000/2,000 次是 Task Pack 所要求的本地 CPU 分块重采样，P03 则是六个冻结向量的本地确定性计算，均不依赖真实时间或外部服务。
- `tests/S10/stage_review_test.py` 定向复审：`44 passed`；写入证据的带报告复审：`87/87 PASS`。报告包含 `49/49` Task Pack 静态校验、付费/未知依赖扫描 PASS、100 次确定性重放及 10,000 次不利快照重放；这些是有限本地 CPU 重放，不是实时 soak。
- 远端 CI 同款 S00/S08 定向门：`67 passed`；S08 候选预检 `67/67 PASS`，S07 legacy receipt 回放 `7/7 PASS`。JUnit 已规范化，工件清单与 `SHA256SUMS` 已重建。
- S10 复审回滚 receipt 为 `machine/evidence/EVD-S10-STAGE-REVIEW_rollback.json`；其动作只关闭复审候选并保留 P01--P04 已签名证据，未改变外部或生产状态。

## 关键文件

- `calibration.py`
- `temporal_cv.py`
- `calibration_report.json`
- `uncertainty.py`
- `bootstrap_manifest.json`
- `decimal_math.py`
- `numeric_vectors.json`
- `cross_impl_check.py`
- `robustness_gate.py`
- `boundary_vectors.json`
- `robustness_report.json`
- `friction.py`
- `friction_model.json`
- `friction_backtest.json`
- `abd_acceptance/temporal_calibration.py`
- `abd_acceptance/uncertainty.py`
- `abd_acceptance/decimal_math.py`
- `abd_acceptance/robustness_gate.py`
- `abd_acceptance/friction.py`
- `abd_acceptance/stage10_review.py`
- `abd_acceptance/__main__.py`
- `abd_acceptance/budget.py`
- `machine/tests/fixtures/S10_P01.json`
- `machine/tests/fixtures/S10_P02.json`
- `machine/tests/fixtures/S10_P03.json`
- `machine/tests/fixtures/S10_P04.json`
- `machine/tests/fixtures/S11_P01.json`
- `machine/facts/stage10_review_contract.json`
- `machine/tests/fixtures/S10_STAGE_REVIEW.json`
- `tests/S10/P01_test.py`
- `tests/S10/P02_test.py`
- `tests/S10/P03_test.py`
- `tests/S10/P04_test.py`
- `tests/S11/P01_test.py`
- `tests/S10/stage_review_test.py`
- `machine/evidence/EVD-S10-P01.json`
- `machine/evidence/EVD-S10-P02.json`
- `machine/evidence/EVD-S10-P02_rollback.json`
- `machine/evidence/EVD-S10-P03.json`
- `machine/evidence/EVD-S10-P03_rollback.json`
- `machine/evidence/EVD-S10-P04.json`
- `machine/evidence/EVD-S10-P04_rollback.json`
- `machine/evidence/EVD-S10-STAGE-REVIEW.json`
- `machine/evidence/EVD-S10-STAGE-REVIEW_rollback.json`
- `machine/evidence/EVD-S11-P01.json`
- `machine/evidence/EVD-S11-P01_rollback.json`
- `machine/evidence/S11/P01/pytest.xml`
- `machine/evidence/S10/STAGE_REVIEW/findings.json`
- `machine/evidence/S10/STAGE_REVIEW/pytest.xml`

## 未解决风险

- S11/P02--P04、S11 整体复审和阶段上传均未开始；S11/P01 的本地 PASS 不代表整个 S11、远程 CI 或发布可用。
- 真实市场、真实账户、TAB/Gmail 证据归档、OVH、Cloudflare 与生产上线均未验证、未部署且不应据此推断完成。

## 下一步

保留当前本地 worktree/branch 作为 S11/P01 已签名检查点；下一次 run 仅可从冻结 Task Pack 的 `S11/P02` 开始。完成 S11/P01--P04 后才进行整个 S11 复审；复审问题闭合后才上传 GitHub。保持零新增现金、无真实时间 soak、无全量测试/完整回归。不得把本地结果外推为真实市场、账户、OVH、Cloudflare 或生产上线完成。
