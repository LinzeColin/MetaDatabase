# Signal Lattice V2 重建交接

更新时间：2026-09-14 Australia/Sydney

## 当前目标

Stage 4 已完成代码接入：对当前行情层已取得的日线执行含费用的滚动前推回测，
生成严格样本外 Alpha 度量、逐期贡献度样本，并以 PROMO-1 结果控制 S2 是否参与
Stage 2 的静态冷启动汇总。Stage 3 动态贡献度权重与 Stage 5 部署保持原状。

## 当前状态

STAGE_4_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE；当前工作区没有可用于实际运行的
行情历史缓存，真实 S2 裁定状态为 UNKNOWN，S2 继续处于 EXCLUDED_PENDING_BACKTEST。

本机核查结果：

- /var/lib/signal-lattice-v2 不存在。
- Alpha/data 只有 sample_prices.csv，包含 SPY、QQQ、TLT 各 30 个交易日。
- S1 缺少 IWM、EFA、EEM、GLD、BIL；S2 的 SPY/QQQ 也无法满足至少两个完整
  24 个月训练加 6 个月测试窗口。
- 本任务禁止联网，因此没有用短窗、全样本或 Alpha 历史报告替代当前真实回测。

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
- 未实现分支的权重仍恒为 0。aggregate 的 WEIGHT_MODE 仍是 COLD_START_EQUAL，
  动态贡献度加权为 false。

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
- src/signal_lattice/branches/runtime.py
- src/signal_lattice/live_runtime.py
- web/app.js
- tests/test_backtest.py
- tests/test_branch_verdicts.py

## 已验证

局部回测与现有分支测试：

    PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src python3 -m pytest tests/test_backtest.py tests/test_branch_verdicts.py tests/test_aggregate.py tests/test_live_api.py -q

结果：15 passed in 1.95s。

新增 tests/test_backtest.py 的固定序列夹具覆盖：

- 严格完整滚动窗口与 train/test 无交集。
- 费用被实际扣减，含费用净值低于无费用净值。
- 样本不足退出路径输出 样本不足 0/2 且贡献样本数为 0。
- PROMO-1 的 3 年、0.6%、30% 边界与月均收益低于门槛的失败判定。

同时已通过 node --check web/app.js、python 编译检查和 git diff --check。

## 未解决风险

- 当前真实日线原始数据未落在可访问 state_dir，无法在离线约束下产出本轮实时
  S2 PROMO-1 数字、各市场样本不足清单或任何真实 Alpha 数值。
- Alpha/reports/backtest/2026-07-16/report.json 是旧策略/旧门槛上下文的历史报告，
  不作为本轮真实回测或 S2 解禁证据。
- 完整测试仍须在当前工作区最后执行；历史基线为 11 个既有红灯，sandbox 的 TCP
  限制会额外触发 test_api.py 等 PermissionError。

## 下一步

在具有本轮真实日线缓存的目标机运行一次 Signal Lattice 的 once 命令。确认
state_dir/backtest/latest.json 中每个分支至少有两个完整窗口后，读取 S2 promotion
的 passed 与 reason：通过则 S2 参与静态冷启动汇总；未通过则按报告数值维持排除。
