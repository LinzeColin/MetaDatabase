# ABD 开发交接

## 当前目标

在隔离 worktree `codex/abd-v0001-s11-p01` 按冻结 Task Pack 推进 ABD `v0.0.0.1`。S11/P01--P04、整个 S11 的本地独立复审和 GitHub 阶段上传均已完成；PR #174 的 CI 修复仍须以远端结果确认。S12/P01--P03 已在本地完成、签名并复现，下一 run 最多只能推进 S12/P04；S12 未整体复审或上传。仍不得部署或激活生产。

## 当前状态

- S10 的整体复审已通过并经 [PR #173](https://github.com/LinzeColin/MetaDatabase/pull/173) 合并；当前 worktree 从 `origin/main` 的合并提交 `05baf72f29973d04c8d115170c7aef3f95454008` 创建，主工作树及其他项目 worktree 均未触碰。
- S10 整体复审证据为 `machine/evidence/EVD-S10-STAGE-REVIEW.json`（SHA-256 `d0d00ece08b45943715e300a5cc4cc1818041477b575d074049cbc3ba88c0ce5`）。
- S12/P01 已本地签名通过：`machine/evidence/EVD-S12-P01.json`，下一状态为 `S12/P02_READY_NOT_STARTED`。`target_engine.py` 与 `cashflow_adjustment.py` 只重放固定时钟下四条冻结合成月度记录：以 A$300 × 1.3^n 的保守向上分位目标计算，并只按月初/月底已审计合成现金流调整。目标短缺只报告，不放宽任何证据、风险、来源或动作门；不读取真实账户、不生成推荐或订单，也不承诺收益。
- S12/P02 已本地签名通过：`machine/evidence/EVD-S12-P02.json`，下一状态为 `S12/P03_READY_NOT_STARTED`。`capacity_model.py` 仅对 8 条冻结合成候选重放已签名 S11 相关簇、5% 簇上限、平台剩余容量和可执行比例：去重后容量从 7,290 分降至 5,090 分，再受平台限额降至 4,000 分；只有 5 个独立等效信号，明确为 `INSUFFICIENT_INDEPENDENT_EQUIVALENT_SIGNALS_TARGET_UNVERIFIED`，不把容量当作收益、30%覆盖、推荐或订单。
- S12/P03 已本地签名通过：`machine/evidence/EVD-S12-P03.json`（SHA-256 `10ece6229575dc17dfed64e802d734d1ad199df592393b9525552d9f26c04a58`），下一状态为 `S12/P04_READY_NOT_STARTED`。`economics.py` 仅重放 P02 的 4,000 分冻结合成容量和三条固定情景收益带：最高上界为 800 分，仍比月度目标增量 9,000 分短 8,200 分。全部输出同时含区间、置信度与失败概率，但明确为合成敏感性披露，不是市场预测、实际收益、ROI、推荐或订单；新增现金为 A$0，现有资源与机会成本不被重标为零。
- S11/P01 已本地签名通过：`machine/evidence/EVD-S11-P01.json`（SHA-256 `4bf25a1a68e3078f512a7cbf0992285e2890d62b5284de24eefd750390b7e2f8`），下一状态为 `S11/P02_READY_NOT_STARTED`。`friction.py` 只重放冻结合成的价格恶化、拒绝、结算和操作摩擦；滚动 P95 使用保守 upper-nearest-rank，`effective_friction = max(default, rolling_observed_p95)`。正的合成净期望仍只输出 `NO_ORDER_RESEARCH_ONLY`，不生成建议或订单。
- S11/P02 已本地签名通过：`machine/evidence/EVD-S11-P02.json`（SHA-256 `59e814b20d237eff982ff763bb3573ba8c129e6817c4c1cf61e273c366bab065`），下一状态为 `S11/P03_READY_NOT_STARTED`。`decision_gate.py` 以 50 位 `Decimal` 固化 E4/E3/E2/E1/E0 证据分层、共同硬门、`o_min=(1+r_min+c_effective)/p_L` 和向上赔率舍入；4 个稳定候选仍仅为 `CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES`，其余 8 个为 `NO_RECOMMENDATION`，不生成推荐、订单或收益保证。
- S11/P03 已本地签名通过：`machine/evidence/EVD-S11-P03.json`（SHA-256 `c3d0c61870a37e6c8ee3e71650008fdcf23d4bc2da4d1ec9e83e8e846a4b12d4`），下一状态为 `S11/P04_READY_NOT_STARTED`。`platform_router.py` 只对冻结合成 provider ID 以 50 位 `Decimal` 重放 `S_platform = r_L − P_stale − P_settlement − P_minimum_stake − P_action_friction`；仅唯一最高分且全部门通过者才是 `ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES`，并列、来源/结算/动作通道、最低金额、过期、最低赔率和任一不利扰动均失败关闭为 `NO_RECOMMENDATION`。它不生成真实平台、建议、订单或收益保证。
- S11/P04 已本地签名通过：`machine/evidence/EVD-S11-P04.json`（SHA-256 `d9bc525ce3902cdda3ca6ad6253cc77ab69cddb4641b3d4d7e2c207f59c49ed2`），下一状态为 `S11/STAGE_REVIEW_READY_NOT_STARTED`。`risk_engine.py` 以 50 位 `Decimal` 重放完整凯利 `f_K=(p_Lo-1)/(o-1)`，再取阶段系数、单票、赛事、相关簇和总未结暴露可用容量的最小值，并向下舍入至平台步长；Alpha 为零，Beta/GA 分别受 1.5%/2.0% 单票上限约束。日损 3%、策略切片回撤 10%、灾难线 70%、账本差异非零和低于最低金额均停止新增候选；7 日 7.5% 回撤仅诊断/缩小范围，目标短缺仅诊断且绝不放宽门。12 个冻结向量中仅 6 个保持风险门候选，`K11` 在风险阈值收紧 `0.0001` 时稳定地降级为 `NO_RECOMMENDATION`。所有结果仍是合成风险候选，不生成最终建议、真实订单或收益保证。
- S11 整体复审已本地重签通过：`machine/evidence/EVD-S11-STAGE-REVIEW.json`（SHA-256 `4ed6ed2b82875e3e3f3d74f5547ff0b31ea3768bf80e621758dbb2a8dd523900`），`STAGE-REVIEW-S11` 带既有 JUnit、依赖扫描和 Task Pack 报告的验收为 `91/91 PASS`，下一状态为 `S11/GITHUB_STAGE_UPLOAD_READY`。它只核验四份既有 Phase 收据、冻结基线、任务链和四项 S11 控制；9 个冻结快照各单次执行，无 Phase 测试套件重跑、全量回归或真实时间 soak。
- S11 GitHub 阶段上传已完成：`codex/abd-v0001-s11-p01` 已推送到 `origin`，Draft [PR #174](https://github.com/LinzeColin/MetaDatabase/pull/174) 的 base 为 `main`，包含 S11 的 5 个已签名本地提交。上传时即时观察到两项 `ABD continuous validation / verify` 与一项 `Dual-Plane Governance / dual-plane` 仍为 `IN_PROGRESS`；未声称远端 CI 已通过、PR 已合并或生产已部署。
- 首次远端快速 CI 的 `dual-plane` 已 PASS；一个 `ABD continuous validation / verify` 的 Actions 日志以 `2 failed, 65 passed` 结束：S00 全仓路径扫描把 S11 复审源码内的路径防护字面量误判为本机路径，S08 legacy replay 未识别新增的 `INDEX-S11-STAGE-REVIEW`。本地修复改为语义等价的安全拼接，并仅在 S11 index 行、收据哈希、合同、状态、决策和 next 全部精确匹配时接受该 successor；S08 的既有 allow-list、helper、合同与 fixture pins 已同步。未放宽任何数值、风险、证据、安全或来源门，需以新远端 CI 重新验证。
- 复审发现的唯一过程缺口（四个已签名 Phase 未预置整体复审合同）已以独立合同、冻结 fixture、离线判定器和回滚 receipt 闭合；`findings.json` 为 `1 resolved / 0 open`。该闭合不修改任何冻结 Phase 基线或放宽证据、数值、风险、安全和来源门。
- S10/P01 已签名通过：`machine/evidence/EVD-S10-P01.json`，下一状态为 `S10/P02_READY_NOT_STARTED`。其时间交叉验证只使用冻结合成输入，校准结论不构成推荐、下注、订单或收益承诺。
- S10/P02 已签名通过：`machine/evidence/EVD-S10-P02.json`（SHA-256 `1481efc71fcc185c57a06ddee11d3e0015e534b2084cd90b43dda8ef55fcaa69`），下一状态为 `S10/P03_READY_NOT_STARTED`。
- S10/P03 已签名通过：`machine/evidence/EVD-S10-P03.json`（SHA-256 `7b848a4e885b5f1b9b31752b88c8b136e1b66f734ed0cdf30926b325bbc0f55c`），下一状态为 `S10/P04_READY_NOT_STARTED`。
- S10/P04 已签名通过：`machine/evidence/EVD-S10-P04.json`（SHA-256 `0700d4af988731fa39fc9506751b993e509da8afa78d63ef951c3bac842a9ed3`），下一状态为 `S10/STAGE_REVIEW_READY_NOT_STARTED`。`robustness_gate.py` 对 12 个冻结合成向量逐项重放概率、阈值、摩擦、时间、赔率、参数最坏值及其组合；任一不利翻转即为 `NO_RECOMMENDATION`。固定报告 SHA-256 为 `2acc10ff3fa55bb63f7739f179a6d702998d5a4d9d3aa35dd1c78b5a07ab8c30`。
- `uncertainty.py` 以完整时间 block 作为重采样单元，用固定 LCG 的高位映射避免低位取模产生固定置换。运行时精确执行 1,000 次、评测精确执行 2,000 次分块重采样，并按第 10 百分位得到保守概率；结果绝不高于未校正基准概率，且固定 probe 上单调不减。
- 冻结 fixture 的运行时保守概率为 `0.615`、评测保守概率为 `0.615625`；这只是合成 fixture 的可复现输出，不是市场概率、投资/博彩建议或收益预测。
- P02 的 `bootstrap_manifest.json` SHA-256 为 `7db203809f881696db69ff9a0857157e6e87b46d035c0ae1177cbc172584591c`。它绑定 P01 已签名 receipt、冻结 seeds、block digest 与每次重采样分布摘要。
- P03 的 `decimal_math.py` 按 50 位 Decimal 处理金额分、概率 `1e-9`、赔率 `1e-6`，概率/赔率向下、摩擦向上和 stake 向 provider 增量向下舍入；`cross_impl_check.py` 以独立表达式重放六个冻结合成向量。固定报告 SHA-256 为 `038b1e9cae3ae7c50ddfd152e0293c257e688132269f7fca0cf1dcd8349026c4`，最大差异为 `0`，所有动作和整数分 stake 一致。
- `abd_acceptance/budget.py` 只将冻结 Task Pack 的根级本地源码（现含 `friction`、`decision_gate`、`platform_router`、`risk_engine`、`target_engine`、`cashflow_adjustment`、`capacity_model`、`equivalent_signal`、`economics`）加入本地源码白名单；未知第三方导入仍失败关闭。S11/P01--P04 将 dispatcher 与共享依赖扫描器显式排除在 phase-owned receipt 输入哈希之外，避免后续共享运行时演进伪造性地使冻结 phase evidence 失效。
- `financial_target_status` 仍为 `UNVERIFIED_NOT_GUARANTEED`；没有真实资金、账户、订单、TAB/Gmail、OVH、Cloudflare 或生产部署/激活。
- S10 上传前复审修复了两项失败关闭兼容性：S10 可移植性扫描不再包含本机绝对路径字面量；S07 只在 S09 已通过后接受哈希、状态、下一步与发布边界均精确匹配的 S10 整体复审索引。S08 的 legacy successor manifest、helper、合同和 fixture 均重新精确钉住；本次只刷新旧收据已声明为可演进的 `abd_acceptance/__main__.py` 与 `abd_acceptance/evidence_continuity.py` 当前 SHA-256，未扩展 allow-list、来源、风险豁免或旧收据内容。

## 已验证

- 冻结 Task Pack 核心事实文件与原始包逐一一致；Task Pack 静态校验 `49/49 PASS`。
- `tests/S12/P01_test.py` 定向测试：`19 passed`；覆盖 A$300 × 1.3^n 的保守分位、月初/月末现金流调整、目标短缺仅报告、篡改失败关闭、无网络/订单/真实时间能力、回滚，以及签名时仅替换 S12/P01 的 JSONL 索引行后可复现。
- `AC-S12-P01` 带 JUnit、依赖扫描与 Task Pack 报告的签名验收为 `29/29 PASS`；`--verify-existing AC-S12-P01`：PASS。连续证据复核 `49/49 PASS`，S08 旧收据兼容性精确重放 `1 passed`。仅执行 P01 定向测试、静态校验、依赖扫描与一条 S08 兼容性测试；未运行全量测试、完整回归或真实时间 soak。
- `tests/S12/P02_test.py` 定向测试：`17 passed`；覆盖同簇重复不计、跨簇共享平台总额、万分之一可执行比例扰动、P01/相关图/报告篡改失败关闭、回滚及无外部能力边界。`AC-S12-P02` 带 JUnit、依赖扫描与 Task Pack 报告的签名验收为 `25/25 PASS`；`--verify-existing AC-S12-P02`：PASS，连续证据 `49/49 PASS`，S08 旧收据兼容性精确重放 `1 passed`。未运行全量测试、完整回归或真实时间 soak。
- `tests/S12/P03_test.py` 定向测试：`21 passed`；覆盖固定重放、三条收益带及各自置信度/失败概率、A$0 新增现金和机会成本披露、P01/P02/容量/产物篡改失败关闭、`±0.0001` 收益率扰动、回滚及无外部能力边界。`AC-S12-P03` 带 JUnit、依赖扫描与 Task Pack 报告的签名验收为 `30/30 PASS`；`--verify-existing AC-S12-P01`、`AC-S12-P02`、`AC-S12-P03` 均 PASS，连续证据 `49/49 PASS`。只运行 P03 定向测试与 S08 旧收据兼容性定向重放，未运行全量测试、完整回归或真实时间 soak。
- `tests/S11/P01_test.py` 定向测试：`19 passed`；覆盖四类摩擦组成、四个时距段、滚动 P95 / 默认值最大规则、`+0.0001` 摩擦与一档不利赔率、重放哈希、篡改、回滚及无外部能力边界。
- `tests/S11/P02_test.py` 定向测试：`32 passed`；覆盖 E4--E0、最低赔率公式与向上舍入、`±0.0001` 阈值和一档不利赔率、五类不利扰动、固定重放、篡改、回滚及无外部能力边界。
- `AC-S11-P02` 候选预检和带 JUnit、依赖扫描、Task Pack 报告的签名验收：`29/29 PASS`；`--verify-existing AC-S11-P02`：PASS。Task Pack 静态校验 `49/49 PASS`，依赖扫描 PASS；只运行 S11/P02 定向测试和一次 S8 legacy 单测，未运行全量测试、完整回归或真实时间 soak。
- `tests/S11/P03_test.py` 定向测试：`38 passed`；覆盖唯一最高分、并列失败关闭、五个时距段、来源/结算/动作通道/最低金额/P02 候选门、`+0.0001` 回报与惩罚、`+2s` 时效和一档不利赔率、重放哈希、篡改、回滚及无外部能力边界。
- `AC-S11-P03` 候选预检：`26/26 PASS`；带 JUnit、依赖扫描和 Task Pack 报告的签名验收：`30/30 PASS`；`--verify-existing AC-S11-P01`、`AC-S11-P02`、`AC-S11-P03` 均 PASS。仅运行 S11/P03 定向测试、静态包校验和本地依赖扫描；无全量测试、完整回归或真实时间 soak。
- `tests/S11/P04_test.py` 定向测试：`44 passed`；覆盖完整凯利、Alpha/Beta/GA 系数、单票/赛事/相关簇/总暴露容量、最低金额不向上凑单、日损/7日诊断/策略切片/灾难线/账本差异、目标短缺不放宽门、`p−0.0001`、风险阈值收紧 `0.0001`、不利赔率跳动、固定重放、篡改、回滚及无外部能力边界。
- `AC-S11-P04` 候选预检：`26/26 PASS`；带 JUnit、依赖扫描和 Task Pack 报告的签名验收：`30/30 PASS`；`--verify-existing AC-S11-P01`、`AC-S11-P02`、`AC-S11-P03`、`AC-S11-P04` 均 PASS。依赖扫描 PASS、Task Pack 静态校验 `49/49 PASS`；仅运行 S11/P04 定向测试与 S8 兼容性哈希链定向检查，无全量测试、完整回归或真实时间 soak。
- `tests/S11/stage_review_test.py` 定向复审：`22 passed`；JUnit 已规范化。`STAGE-REVIEW-S11` 候选预检 `87/87 PASS`，带报告签名验收 `91/91 PASS`，付费/未知依赖扫描 PASS，Task Pack 静态校验 `49/49 PASS`，工件清单 `674` 文件与 `675` 条 checksum 已重建。为 dispatcher 增加复审入口后，S08 legacy successor 链的最小精确哈希验证 PASS；只刷新既有 allow-list 中的 `abd_acceptance/__main__.py`，未扩展 allow-list 或改写旧收据。
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
- `decision_gate.py`
- `evidence_tiers.json`
- `threshold_vectors.json`
- `platform_router.py`
- `provider_score.json`
- `routing_fixtures.json`
- `risk_engine.py`
- `correlation_graph.json`
- `risk_vectors.json`
- `abd_acceptance/temporal_calibration.py`
- `abd_acceptance/uncertainty.py`
- `abd_acceptance/decimal_math.py`
- `abd_acceptance/robustness_gate.py`
- `abd_acceptance/friction.py`
- `abd_acceptance/decision_gate.py`
- `abd_acceptance/platform_router.py`
- `abd_acceptance/risk_engine.py`
- `abd_acceptance/stage11_review.py`
- `abd_acceptance/stage10_review.py`
- `abd_acceptance/__main__.py`
- `abd_acceptance/budget.py`
- `abd_acceptance/target_curve.py`
- `abd_acceptance/capacity_correlation.py`
- `target_engine.py`
- `cashflow_adjustment.py`
- `capacity_model.py`
- `equivalent_signal.py`
- `capacity_report.json`
- `economics.py`
- `sensitivity_grid.json`
- `opportunity_cost.json`
- `abd_acceptance/economics_sensitivity.py`
- `machine/tests/fixtures/S10_P01.json`
- `machine/tests/fixtures/S10_P02.json`
- `machine/tests/fixtures/S10_P03.json`
- `machine/tests/fixtures/S10_P04.json`
- `machine/tests/fixtures/S11_P01.json`
- `machine/tests/fixtures/S12_P01.json`
- `machine/tests/fixtures/S12_P02.json`
- `machine/tests/fixtures/S12_P03.json`
- `machine/tests/fixtures/S11_P02.json`
- `machine/tests/fixtures/S11_P03.json`
- `machine/tests/fixtures/S11_P04.json`
- `machine/tests/fixtures/S11_STAGE_REVIEW.json`
- `machine/facts/stage10_review_contract.json`
- `machine/facts/stage11_review_contract.json`
- `machine/tests/fixtures/S10_STAGE_REVIEW.json`
- `tests/S10/P01_test.py`
- `tests/S10/P02_test.py`
- `tests/S10/P03_test.py`
- `tests/S10/P04_test.py`
- `tests/S11/P01_test.py`
- `tests/S12/P01_test.py`
- `tests/S12/P02_test.py`
- `tests/S12/P03_test.py`
- `tests/S11/P02_test.py`
- `tests/S11/P03_test.py`
- `tests/S11/P04_test.py`
- `tests/S11/stage_review_test.py`
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
- `machine/evidence/EVD-S12-P01.json`
- `machine/evidence/EVD-S12-P01_rollback.json`
- `machine/evidence/EVD-S12-P02.json`
- `machine/evidence/EVD-S12-P02_rollback.json`
- `machine/evidence/EVD-S12-P03.json`
- `machine/evidence/EVD-S12-P03_rollback.json`
- `machine/evidence/EVD-S11-P02.json`
- `machine/evidence/EVD-S11-P02_rollback.json`
- `machine/evidence/EVD-S11-P03.json`
- `machine/evidence/EVD-S11-P03_rollback.json`
- `machine/evidence/EVD-S11-P04.json`
- `machine/evidence/EVD-S11-P04_rollback.json`
- `machine/evidence/EVD-S11-STAGE-REVIEW.json`
- `machine/evidence/EVD-S11-STAGE-REVIEW_rollback.json`
- `machine/evidence/S11/P04/pytest.xml`
- `machine/evidence/S11/P03/pytest.xml`
- `machine/evidence/S11/P01/pytest.xml`
- `machine/evidence/S11/STAGE_REVIEW/findings.json`
- `machine/evidence/S11/STAGE_REVIEW/pytest.xml`
- `machine/evidence/S10/STAGE_REVIEW/findings.json`
- `machine/evidence/S10/STAGE_REVIEW/pytest.xml`

## 未解决风险

- S11/P01--P04、整体复审和 GitHub 阶段上传均已完成，但当前 CI 修复尚未获得新的远端结果；本地复审与分支上传不代表远程 CI、合并、发布、OVH、Cloudflare 或生产可用。
- S12/P01--P03 仅完成本地冻结合成验收；它们不代表 S12 整体复审、GitHub 上传、远端 CI、合并、发布、OVH、Cloudflare、真实市场、真实账户、TAB/Gmail 归档或生产上线完成。
- 一次 S8 legacy 单测仍因 P02 之外的既有 S03/P04 缺失 `paid_dependency_scan.txt` 期望哈希而失败关闭；该旧阶段缺口未在 P02 中放宽或伪造通过，需在相应 S03/S08 复审范围内单独处理。
- 真实市场、真实账户、TAB/Gmail 证据归档、OVH、Cloudflare 与生产上线均未验证、未部署且不应据此推断完成。

## 下一步

保持 PR #174 的远端 CI 状态与 S12/P01--P03 本地结果彼此独立；不得把 pending 或本地结果外推为 CI、合并、部署、OVH、Cloudflare、真实市场、账户或生产上线完成。下一次 run 最多推进 S12/P04；中间 phase 不上传，待 S12/P01--P04 全部完成后才进行整个 S12 复审、修复并上传。保持零新增现金、无真实时间 soak、无全量测试/完整回归。
