# Signal Lattice V2 重建交接

更新时间：2026-09-14 Australia/Sydney

## 当前目标

修复对抗性审查确认的三个 no-ship 根因：日线坏响应缓存、Hedge 极端有限输入和
NaN/Infinity 行情值。Stage 4 的严格样本外回测、贡献度落盘和 PROMO-1 判定保持
原状；Stage 5 部署保持原状。

## 当前状态

STAGE_3_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE。当前 worktree 没有目标机的运行期
`state_dir`，因此本机没有重放真实行情。目标机已产出的真实贡献度输入表明：S1 有
4 条可用样本，S2 有 10 条样本但 PROMO-1 未通过并保持
`EXCLUDED_PENDING_BACKTEST`。据此，本轮实际权重模式为 `COLD_START_EQUAL`：
S1 显示 `INSUFFICIENT_CONTRIBUTION_SAMPLES: 4/8`，S2 权重保持 0。

本机核查结果：

- /var/lib/signal-lattice-v2 不存在。
- Alpha/data 只有 sample_prices.csv，包含 SPY、QQQ、TLT 各 30 个交易日。
- S1 缺少 IWM、EFA、EEM、GLD、BIL；S2 的 SPY/QQQ 也无法满足至少两个完整
  24 个月训练加 6 个月测试窗口。
- 本任务禁止联网，因此没有用短窗、全样本或 Alpha 历史报告替代当前真实回测。

## 2026-09-14 对抗性审查修复

- 日线缓存：`fetch_validated_cached` 成为 Sina、Tencent、EastMoney 三个日线 provider
  的共享路径。缓存与新响应都先解析；解析成功后才落盘。命中坏缓存会只删除该键，
  当前调用内只重新拉取一次；重拉失败把 `MarketDataError` 交给既有阻断链路。
- 动态权重：`weighting.py` 改为对数权重加 log-sum-exp 归一化。新增
  `MAX_STANDARDIZED_CONTRIBUTION = 20.0`：`risk_adjusted_excess` 的单位是 active
  volatility 标准化单位，截断后的单期对数更新为 ±2（`eta=0.10`），单期倍率处于
  `e^-2` 至 `e^2`，足以保留极端贡献差异，同时隔离极小非零波动率导致的有限异常值。
  分支输出 `contribution_input_truncation` 和每期 `input_truncated`；不可计算的开始权重、
  期间输入、log 归一化或边界状态统一返回 `COLD_START_EQUAL_WEIGHTING_DEGRADED:<原因>`，
  并显示明确降级原因。
- 有限数值边界：Sina/Tencent 报价在 `math.isfinite` 后才接纳；全部日线 provider
  对 OHLC 与已提供 volume 检查有限性。`LiveEngine` 对 quote 和 bar 再检查一次，
  `QUOTE_NONFINITE` / `BAR_NONFINITE` 直接使报告为 `SYSTEM_BLOCKED`。运行期报告、
  回测落盘、V2 API 与 CLI 通过 `strict_json_dumps(..., allow_nan=False)` 写出；严格 JSON
  边界若发现非有限数值，替换为带 `SERIALIZATION_NONFINITE_VALUE` 的清洁阻断报告。
- 新增夹具：三家日线 provider 分别覆盖缓存 HTML 命中后的单次重拉与新 HTML 响应不入缓存；
  报价 NaN/Infinity、OHLCV 非有限值和运行时 NaN 报价均覆盖；`1e300` 与 `-1e300`
  的有限贡献度覆盖有界权重和截断披露；log 归一化不可计算覆盖显式冷启动降级。

### MIN_COMPLETE_WINDOWS 核实结论

确认存在表述层矛盾，当前轮未修改它以保持“只修三条 no-ship”的范围：

- `MIN_COMPLETE_WINDOWS = 2` 允许约一年样本外后 S1/S2 branch 进入 `OOS_READY`，
  `run_backtest` 也会在任一分支达到该状态时返回 `OOS_READY`。
- `profitability_status` 会直接展示该分支的样本外超额收益，没有补充样本外历史少于
  3 年的限制。S2 的 PROMO-1 自己检查 `min_years = 3.0`，因此 S2 仍保持推广排除；
  S1 没有同等的就绪表述门。
- 建议后续作为独立批准变更：保留 `OOS_READY` 表示“结构上可计算”，新增面向收益结论
  的 `OOS_HISTORY_INSUFFICIENT` / `profitability_readiness` 门，并让
  `profitability_status` 在严格样本外历史未达 3 年时明确显示不足而非直接展示为就绪。

## Stage 3 实现与关键决定

- 新增 `src/signal_lattice/weighting.py`，只读取
  `state_dir/backtest/contribution_samples.json` 中 Stage 4 已落盘的严格样本外样本。
  它不调整行情新鲜度门、分支实现状态或 S2 的 PROMO-1。
- `MIN_CONTRIBUTION_SAMPLES = 8`：八个完整六个月样本外窗口约覆盖四年实际在场期，
  降低单一市场阶段支配权重的风险。当前 S1 仍差 4 条可用样本；继续既有 24/6
  walk-forward 即可积累，不能为凑数修改窗口参数。
- `HEDGE_LEARNING_RATE = 0.10`：风险调整超额可显著大于 1；当单期为 2.5 时倍率为
  `exp(0.10 × 2.5) ≈ 1.28`，既反映贡献差异，也避免一窗决定后续全部权重。
- `WEIGHT_FLOOR = 0.05`、`WEIGHT_CAP = 0.60`：floor 保留后续恢复空间，cap 留出
  至少 40% 的比较空间。单一已资格分支处于冷启动时为结构性 100%，不存在可比较
  的其他参与者。
- 每条分支记录样本数、可用样本数、累计风险调整超额、累计实际更新值、风险调整
  超额与 `excess_return` 回退来源、每期起止权重和未约束乘数。动态更新使用经过
  截断的贡献度、对数权重与 log-sum-exp 归一化，轨迹保存 raw/applied 输入和截断标记。
- 样本不足的已资格分支保持自己的冷启动等权份额；样本充足分支在剩余份额内动态
  更新。全部已资格分支样本不足时，模式为 `COLD_START_EQUAL`。推广门排除的分支
  保持 0 权重，不进入样本充足性或 Hedge 计算。
- 持续负贡献且触及 floor 时输出
  `PERSISTENT_NEGATIVE_CONTRIBUTION_AT_FLOOR` 与“持续负贡献，已压至下限。”；
  本轮不自动淘汰任何分支。
- `build_branch_report` 先应用权重结果，再调用 `aggregate.py`。聚合、
  `/api/v1/whitebox/summary` 和网页均返回 `contribution_weights`，其中包含每个
  分支的当前权重、N/M、累计贡献、来源和轨迹。

## Stage 4 实现与关键决定

- 新增 src/signal_lattice/backtest/，移植并本地化 Alpha/backend/app/backtest/
  pipeline.py、fees.py、calendar_effects.py、runner.py。每个文件头保留来源与原路径；
  不跨目录 import。
- pipeline 的 walk_forward_windows 只生成 train 与 test 严格不重叠的完整窗口。
  默认 train=24 月、test=6 月；尾部不完整测试窗直接排除。
- runner 只以当前 MarketGateway 已取得的 marketdata 日线为输入。每个 test 窗口先在
  对应 train 窗口的既定网格中选参，再单独模拟 test；最终收益曲线由所有 test 窗口
  费后结果拼接而成。
- 每个 S1/S2 样本外 test 窗口都生成 ContributionSample，字段为 branch_id、
  period_start、period_end、symbol、branch_return、benchmark_return、
  excess_return、risk_adjusted_excess、window_label。
- benchmark 严格从 Instrument.benchmark 读取。当前两个可运行策略均对 usSPY
  基准计算；代码仍通过 Instrument 字段解析，未写死基准价格序列。
- Alpha 口径包括策略收益、基准收益、超额收益、IR、最大回撤、逐笔胜率、换手率。
  risk_adjusted_excess = excess_return / active_daily_volatility；零波动时为 null。
  负超额收益以负值原样输出。
- 费用模型已接入每次买卖：佣金 0.99 USD/单、卖出 SEC 费率 0.00004、
  CAT 0.0001 USD/股。值来自 Alpha/configs/fees.yaml；SEC/CAT 估计属性保留。
- PROMO-1 默认值显式写在本仓：至少 3 年、月均净收益至少 0.6%、最大回撤至多
  30%。值来自 Alpha/configs/strategy_promotion.yaml；调用方可传受审计的映射覆盖，
  运行时不读取 Alpha 配置路径。
- S1 review_grid 完整取自 Alpha/configs/strategies/s1_momentum.yaml；S2 review_grid
  完整取自 Alpha/configs/strategies/s2_meanrev.yaml。当前未改门槛。
- S2 推广门通过时才取得 COLD_START_ELIGIBLE 与 weight=1.0；失败和样本不足时保持
  EXCLUDED_PENDING_BACKTEST，excluded_branches reason 会携带具体 PROMO-1 差距或
  样本不足 N/M。
- 未实现分支的权重仍恒为 0。动态贡献度权重由 Stage 3 聚合层消费；回测层继续
  只负责产生严格样本外输入。

## 运行期落盘与 API/页面

- 回测总览：state_dir/backtest/latest.json。
- 贡献度样本：state_dir/backtest/contribution_samples.json，JSON 对象包含
  sample_count、samples、storage；不进入 Git。
- LiveEngine 仅在 DATA_READY 时调用 run_backtest。数据不新鲜或数据链路不完整时，
  report 与 backtest 均为 SYSTEM_BLOCKED，原有阻断行为保持。
- GET /api/v1/whitebox/backtest/latest 返回 latest report 中的真实 backtest 结构：
  每个窗口、拼接总览、费用模型、S2 推广门与贡献度汇总。
- web/app.js 增加“回测与超额收益”区块，展示严格样本外口径、费用、各分支拼接指标、
  逐窗口结果和贡献样本数。

## 已改文件

- src/signal_lattice/backtest/__init__.py
- src/signal_lattice/backtest/pipeline.py
- src/signal_lattice/backtest/fees.py
- src/signal_lattice/backtest/calendar_effects.py
- src/signal_lattice/backtest/runner.py
- src/signal_lattice/serialization.py
- src/signal_lattice/branches/runtime.py
- src/signal_lattice/weighting.py
- src/signal_lattice/aggregate.py
- src/signal_lattice/live_runtime.py
- src/signal_lattice/live_api.py
- web/app.js
- tests/test_backtest.py
- tests/test_branch_verdicts.py
- tests/test_weighting.py
- tests/test_marketdata_providers.py

## 已验证

Stage 3 定向测试：

    PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src python3 -m pytest tests/test_weighting.py tests/test_aggregate.py tests/test_branch_verdicts.py tests/test_backtest.py tests/test_live_api.py -q

结果：23 passed in 2.02s。

`tests/test_weighting.py` 的固定贡献度夹具覆盖：

- Hedge 指数更新的手工复算值和逐期轨迹。
- 5% floor、60% cap、负贡献压低但保持正权重、持续负贡献触及下限标记。
- 风险调整超额缺失时回退 `excess_return` 并公开来源。
- 单个样本不足分支保留冷启动等权份额，全部不足保持 `COLD_START_EQUAL`。
- 当前真实输入形状：S1 为 4/8，S2 由 `EXCLUDED_PENDING_BACKTEST` 排除，模式保持
  `COLD_START_EQUAL`。
- 状态文件 `state_dir/backtest/contribution_samples.json` 是唯一权重输入。

完整测试：

    PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src python3 -m pytest tests/ -q

实际输出：`18 failed, 125 passed, 1 skipped in 11.43s`。其中 7 个失败来自 sandbox
禁止 TCP bind（`test_api.py` 5 项、`test_public_release.py` 2 项）；剩余 11 个为既有
部署、正式生命周期、Python 3.9 缺少 `tomllib`、交付文件清单和状态机基线失败。Stage 3
定向测试、Python 编译、`node --check web/app.js` 和 `git diff --check` 全部通过。

Stage 4 已有的固定序列夹具继续覆盖：

- 严格完整滚动窗口与 train/test 无交集。
- 费用被实际扣减，含费用净值低于无费用净值。
- 样本不足退出路径输出 样本不足 0/2 且贡献样本数为 0。
- PROMO-1 的 3 年、0.6%、30% 边界与月均收益低于门槛的失败判定。

同时已通过 node --check web/app.js、python 编译检查和 git diff --check。

对抗性审查修复定向测试：

    PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src python3 -m pytest tests/test_marketdata_providers.py tests/test_weighting.py tests/test_backtest.py tests/test_aggregate.py tests/test_branch_verdicts.py tests/test_live_api.py -q

结果：`37 passed in 2.23s`。

用户指定完整测试：

    PYTHONPATH=src python3 -m pytest tests/ -q

结果：`18 failed, 132 passed, 1 skipped in 18.97s`。18 个失败完全由既有 11 个
发布/正式生命周期/Python 3.9/交付清单/状态机基线失败和 sandbox 的 7 个 TCP bind
`PermissionError` 组成；本轮新增测试未增加失败项。

## 未解决风险

- 当前真实日线原始数据和 `state_dir` 没有落在本 worktree；本轮使用用户提供的真实
  S1/S2 样本计数和 PROMO-1 裁定解释实际模式，没有离线重放或更改回测参数。
- Alpha/reports/backtest/2026-07-16/report.json 是旧策略/旧门槛上下文的历史报告，
  不作为本轮真实回测或 S2 解禁证据。
- 完整测试已在当前工作区执行；上述输出保留 11 个既有非 TCP 红灯，并如实区分了
  sandbox 的 7 个 TCP `PermissionError`。

## 下一步

在目标机按既有运行流程继续积累完整的 24/6 样本外窗口。S1 还需 4 条可用样本达到
8/8；S2 继续以 PROMO-1 的实际结果维持排除。只有至少两个已资格分支各自满足样本门时，
Hedge 才会形成有比较意义的相对动态权重。Stage 5 部署不在本轮范围内。
