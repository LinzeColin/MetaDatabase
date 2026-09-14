# Signal Lattice V2 重建交接

更新时间：2026-09-14 Australia/Sydney

## 当前状态：0.0.0.3.3 已上生产并通过公网复验

`STAGE_5_DEPLOYED_AND_PUBLICLY_VERIFIED`。生产 `/opt/signal-lattice-v2/current`
指向 `0.0.0.3.3`，previous 为 `0.0.0.2.3-r6`。采集由
`signal-lattice-v2-loop.timer`（`OnUnitInactiveSec=60`）驱动 `Type=oneshot` 的
`signal-lattice once`；连续观察 4 轮，间隔约 70 秒，全部 `DATA_READY`，0 失败。

公网当前输出（2026-09-14 04:45 UTC）：

| 项 | 值 |
| --- | --- |
| 投资结论 | 看涨 `usEEM`，conviction 0.6708 |
| 失效条件 | 收盘不高于 SMA200=62.0316，或下次复算跌出 top 2 |
| 收益披露 | `OOS_HISTORY_INSUFFICIENT: 4/6`（系统级不发收益主张） |
| 权重模式 | `COLD_START_EQUAL`（贡献样本 4 < 门槛 8） |
| 参与分支 | `s1_momentum`；`s2_meanrev` 因 PROMO-1 未过被排除；6 个 v19 登记分支 `UNIMPLEMENTED`、权重 0 |

样本外数字（walk-forward，严格 OOS，费用已计）：

| 分支 | 超额 | IR | 窗口 | 证据 | 是否公开数字 |
| --- | --- | --- | --- | --- | --- |
| `s1_momentum` | +4.7096% | 0.1084 | 4 | INSUFFICIENT | 否，公开面扣住 |
| `s2_meanrev` | −49.6752% | −1.0487 | 6 | SUFFICIENT | 是，同响应带 PROMO-1 排除理由 |

`s2_meanrev` 的数字此前是 −78.5628% / IR −1.1618，那是跨着 `usQQQ` 2004→2011
数据洞算出来的；裁剪到可用段后才是上表的值。`s1_momentum` 的窗口起于 2016-02，
不受裁剪影响。

### 公网反向断言（每次发布必须重跑）

对 9 条路由的原始响应串直接断言，不看解析后的字段：

- 证据不足分支的收益数字（`4.7096`）不得出现在任何一条响应里 —— 通过
- 证据达标分支的数字（`-49.6752`）必须出现且同响应带 `PROMO-1` 排除理由 —— 通过
- 不得出现 `Infinity` / `NaN` —— 通过
- 不得出现 v19 冻结持仓痕迹（`1095.34` / `MooMoo`）—— 通过
- 午休必须标为 `INTRADAY_BREAK` 而非 `CLOSED` —— 通过
- 港股当日半场 bar 不得被使用 —— 通过

### 裁剪结果（真实数据，本机与目标机一致）

| 标的 | 可用起点 | 裁掉 | 原因 |
| --- | --- | --- | --- |
| `usQQQ` | 2011-04-26 | 1002 | 2004-12-31→2011-04-26 缺 1646 个工作日 |
| `usAAPL` | 2007-03-19 | 5128 | 2004-12-31→2007-03-19 缺 575 个工作日 |
| `sh600000` | 2016-03-11 | 445 | 2016-02-15→2016-03-11 停牌 18 个工作日 |
| `usSPY` | 2001-01-02 | 0 | 911 停市只有 4 个工作日，未触发阈值 |

阈值 `MAX_USABLE_GAP_BUSINESS_DAYS = 10`：春节 6 个工作日、A 股停牌与 911 的 4 个
工作日都在阈值内，不做基于假日历的判别（该路线已失败两次）。

### 下一个人接手时最该知道的三件事

1. **不要用 `_market_is_open` 判断当日 K 线是否定稿。** 港股 12:00-13:00、
   A 股 11:30-13:00 的午休不在任何时段内，但交易日远未结束。用
   `_trading_day_is_complete`。2026-09-14 灰度实测就撞到过：午休时当日半场 bar
   被当成收盘日线喂进了全部指标与回测。
2. **收益披露是逐分支的，不是系统级一刀切。** 系统级样本不足只压住系统级主张；
   一个证据达标的分支即使亏损也必须公开——防夸大的门不能反过来掩盖亏损。
3. **公网验证必须对原始响应串做反向断言。** 解析后再看字段会让人把"数字还在里面"
   解释成"那是研究数据"。第 3 轮审查证明那样的门是装饰性的。

---


## 2026-09-14 生产故障复盘：午休复盘时刻的双重误报

0.0.0.2.5 上线后约 20 分钟，公网翻 SYSTEM_BLOCKED，持续约 25 分钟。
时间点是 13:03 HKT——港股午休结束、下午时段刚开始的那一刻。

两条独立的门在同一个时刻同时误报，必须分开修：

**第一条：陈旧度按墙钟算。** 港股申报延迟 25 分钟，13:00 复盘那一刻能拿到的最新
来源时间必然还是午休前的 11:35，墙钟差 85 分钟，远超「延迟 25 分 + TTL 180 秒」。
修法是 `_trading_seconds_between`：只累加落在交易时段内的秒数。复盘瞬间交易时间差
恰好等于申报延迟 → 新鲜；复盘 5 分钟后仍不推进 → 交易时间累计超限 → 过期。

**第二条：停滞检测在申报延迟窗口内必然误报。** 修好第一条后生产仍然阻断，换成了
`QUOTE_FEED_STALLED`。13:18 时 `trading_age` 1151 秒已通过陈旧度门，但
`last_advance_at` 停在 13:00:15、墙钟停滞 17.95 分钟。原因同源：13:18 时行情
"应该"显示的 12:53 落在午休里根本没有成交，最新可得的仍是 12:00 收盘那条——
不推进是正常的。修法是在「当前时段已开时长 < 申报延迟」的窗口内不做停滞判定，
陈旧度仍照判；窗口之外停滞检测照常激活，早期预警不受影响。

**这条教训要记住的形状**：凡是给「有申报延迟的行情源」设的门，都不能用墙钟量。
市场有午休、有收市、有周末，行情在这些时间里合法地不推进。用墙钟量会在每个
时段边界上误报一次——而且是每个交易日都会重复发生，不是偶发。

**过程上我做错的地方**：0.0.0.2.5 我在灰度上验过、公网也反向断言过，全部通过，
然后才上的生产——但灰度和公网验证都发生在午休期间（12:2x HKT），没有覆盖到
13:00 这个状态切换点。**状态机有边界的系统，验证必须跨过边界，不能只在一个状态里取样。**

## 历史记录

## 2026-09-14 日线可用段裁剪根因修复

### 当前状态

`STAGE_4_DAILY_BAR_USABLE_SEGMENT_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE`。日线从最新端向早期
扫描，遇到长缺口即形成缺口之后的连续可用段；Claude Code 仍需在目标机用真实行情复跑，
因此真实 `DATA_READY`、S1 指标和 `bar_completion` 实例值保持 `UNKNOWN`。

### 关键决策与改动

- 真机全量证据：`usQQQ` 有 4,868 条（2001-01-02 至 2026-09-11），在
  2004-12-31 至 2011-04-26 有 2,307 个自然日、1,646 个工作日的真实历史空洞；`usAAPL`
  有 10,030 条（1984-09-07 至 2026-09-11），在 2004-12-31 至 2007-03-19 有 808 个
  自然日、575 个工作日的真实历史空洞。两者 2016 年后均有 2,688 条，最大缺口 4 个工作日；
  当前 walk-forward 的 WF-01 训练期从 2016-02-01 开始。
- `usSPY` 的 2001-09-10 至 2001-09-17 空洞对应 911 停市，只有 4 个工作日；
  `sh600000` 的 18 个工作日空洞对应个股停牌。缺口本身无法可靠区分节假日、停市与数据
  空洞，系统因此按可用段处理这些事实。
- `MAX_USABLE_GAP_BUSINESS_DAYS = 10` 覆盖春节 6 天、短期停牌和 911 的 4 个工作日。
  长缺口触发 `HISTORICAL_GAP_<previous>_TO_<following>`，可用段从 `following` 开始；报告
  公开 `effective_start_day`、`effective_end_day`、`effective_bar_count`、
  `trimmed_bar_count`、`trim_reason`、`trim_gap_business_days` 和完整 walk-forward 窗口数。
  指标、分支计算、市场指纹和回测都消费同一裁剪段。
- 裁剪段不足两组完整 walk-forward 窗口时，标的生成
  `BAR_USABLE_SEGMENT_WALK_FORWARD_INSUFFICIENT`，finding 同时写入可用段条数与
  当前/所需完整窗口数。`STRUCTURAL`、`CONVERSION`、`OHLCV_VIOLATION` 的条数、比例和
  近期质量门，以及 `bar_completion` 的未收盘 Bar 排除口径保持原值。

### 本机验证

- 定向集：`tests/test_marketdata_providers.py tests/test_backtest.py tests/test_live_runtime.py
  tests/test_live_api.py` 为 `63 passed in 2.84s`。回归覆盖 1,646 工作日远古缺口裁剪放行、
  裁剪段不足两组窗口阻断、4 个工作日 911 口径不裁剪、18 个工作日停牌口径裁剪可见，及
  `run_backtest()` 的输入首日与 `effective_start_day` 一致。
- 完整命令 `PYTHONPATH=src python3 -m pytest tests/ -q`：`14 failed, 187 passed, 1 skipped
  in 34.42s`。7 项为 sandbox 禁止本地 TCP bind 的 `PermissionError`；其余 7 项是既有
  Python 3.9 `tomllib`、formal lifecycle、根目录 allowlist、state-machine/taskpack-seal
  基线。本轮没有新增非 sandbox 红灯。
- Python 3.12：已清理测试生成的 `.pytest_cache`、`build/` 与
  `src/signal_lattice.egg-info/`，重建 `MANIFEST.json` 后
  `scripts/verify_package.py --root . --manifest MANIFEST.json` 为
  `{"finding_count": 0, "findings": [], "state": "PASS"}`。真实行情与 S1
  `+4.7096% / IR 0.1084` 的新值由 Claude Code 目标机复跑确认。

## 2026-09-14 第十轮对抗性审查：发布、预算、日线质量与收盘门

### 当前目标与状态

第七轮确认的 3 条 high 与 1 条 medium 已在本 worktree 修复，当前状态为
`STAGE_4_TENTH_ADVERSARIAL_REMEDIATION_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE`。
本机没有生产行情 `state_dir`，因此没有声称新的 `DATA_READY` 或更新 S1 的收益数字；需要
Claude Code 在目标机以真实行情重跑后确认。

### 安装与回滚迁移

- `deploy/V2_RELEASE_CONTRACT.json` 是 V2 的安装根目录 `/opt/signal-lattice-v2`、运行时目录
  `/var/lib/signal-lattice-v2` 与 unit 名称的单一发布契约；`pyproject.toml [project].version` 是唯一
  版本源。安装和回滚脚本都从这两处读取，不再使用 v19 的根目录或版本常量。
- CLI 新增 `verify-runtime`：它只核验已安装版本、state_dir 存在和 web/index.html 存在，不请求行情
  也不写 state_dir。安装和回滚在切换 `current` 前执行它，避免调用不存在的命令。
- 安装切换会把原 `current` 的已验证 release 原子写入 `previous`，默认 `rollback.sh` 因而总是回到
  实际上一版 V2，而不依赖运维人员手工创建链接。
- `tests/test_deployment_northstar.py` 已覆盖 V2 wheel 构建、隔离安装、已安装 CLI 自检、构造的独立
  上一 V2 release 与回滚切换；回滚收据写入 state_dir。macOS 路径由 Python `Path.resolve()` 与
  `os.replace()` 处理，避免 `/var` 到 `/private/var` 和 GNU `mv -T` 差异。

### 采集预算、停止与月操作量

- `signal-lattice-v2-loop.service` 改为有界 `once`，由
  `signal-lattice-v2-loop.timer` 每 60 秒调度；采集 service 没有 `Restart=always`。因此每次采集
  进程自行结束，timer 只在下一调度点发起新的有限运行。API service 的 `Restart=always` 只服务已落盘
  报告，不调用 provider。
- `state_dir/collection_accounting.json` 持久化 total/daily/active-round 请求数、每 provider 的
  total/daily 数、轮数、连续失败数、下一允许时间和停止原因。每一个物理 HTTP 请求（包含重试）在发出
  前先记账；预算或账本状态不允许时请求不会离开本机，报告公开同一份
  `collection_request_accounting`。
- 正常预算推导：报价每 60 秒 1 个合并请求，`1 × 1,440 = 1,440` 次/日；15 个日线在 6 小时缓存
  下为 `15 × 4 = 60` 次/日；合计 `1,500 × 31 = 46,500` 次/月。硬上限是 48 次/轮
  （16 个正常逻辑请求各最多 3 次 HTTP 尝试），1,600 次/日，即 `49,600` 次/月；正常值与硬上限均已
  明确，超过预算写 `COLLECTION_*_BUDGET_EXHAUSTED` 并停止向上游请求。
- 连续 3 次未得到 `DATA_READY` 后，下一请求按 60 秒、120 秒、240 秒指数退避，最高 3,600 秒；timer
  在退避窗口仅写清楚的阻断报告，不向 provider 重试。每日 UTC 边界重置每日预算与失败计数，累计计数保留。

### 日线质量、连续性与未收盘日线

- Sina、Tencent 与 EastMoney 的每条拒绝都以 `STRUCTURAL`、`CONVERSION` 或
  `OHLCV_VIOLATION` 记录；未知日期的结构/转换拒绝按最近决策窗口处理，不能被当作可证明的远期孤点。
  三类都进入条数、比例、样例和公开 `data_quality_findings`；即使一个标的没有任何可接受行，
  也保留 `accepted_bar_count=0`、拒绝分类和 100% 拒绝比例，不会因空序列失去审计记录。
- 日线连续性以最新连续可用段消费。`sh000300` 最近 252 个工作日为 233/252（92.5%）、
  最大连续缺口 6 个工作日，`hk00700` 为 236/252（93.7%）、最大连续缺口 3 个工作日；
  法定假日进入工作日覆盖率分母，覆盖率不承担数据完整性判定。
- `MAX_USABLE_GAP_BUSINESS_DAYS = 10` 定义可用段边界。报告和门的当前语义以上方
  “日线可用段裁剪根因修复”为准：长缺口公开裁剪原因与有效开始日，只有裁剪段无法形成两组
  完整 walk-forward 窗口时阻断标的。
- `bar_completion` 在正常 `DATA_READY` 路径填写 `last_used_day`、`session_complete` 与
  `excluded_intraday_bar_count`；兼容字段同步保留。盘中交易所当天的日线继续排除在
  `data_cutoff`、market fingerprint、回测和分支裁决之外。
- 开市期间按每个 Instrument 的交易所时区剔除 `exchange_today` 的日线 bar；仅最近已收盘 bar 进入
  `data_cutoff`、`bar_sources`、market fingerprint、回测和分支裁决。报告新增 `bar_completion`，公开
  `last_used_bar_date`、`last_used_bar_is_closed`、被剔除数量和判定依据。

### 本机验证

- 定向回归：`tests/test_marketdata_providers.py`、`tests/test_collection_control.py`、
  `tests/test_deployment_northstar.py`、`tests/test_live_runtime.py`、`tests/test_live_api.py` 为
  `56 passed in 16.82s`。覆盖所有四条审查场景和 V2 timer 契约。
- 用户指定完整命令 `PYTHONPATH=src python3 -m pytest tests/ -q` 为
  `14 failed, 182 passed, 1 skipped in 28.91s`：7 条是本 sandbox 禁止 TCP bind 的
  `PermissionError`；其余 7 条为既有 formal lifecycle、Python 3.9 缺少 `tomllib`、根目录
  allowlist 与 state-machine/taskpack seal 基线。本轮没有增加失败，且安装/回滚 wheel 路径已由
  定向集成测试通过。
- 尚未运行目标机真实行情，因此当前 S1 `+4.7096% / IR 0.1084` 是否因已收盘日线口径变动而变化为
  `UNKNOWN`；不得以本机夹具编造复跑数字。

## 2026-09-14 第九轮报价新鲜度双重判定

### 当前目标与状态

报价新鲜度由单一绝对时延门改为“绝对上限 + 来源时间推进”双重判定，当前状态为
`STAGE_4_NINTH_QUOTE_ADVANCE_DETECTION_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE`。
跨轮状态只写入目标机 `state_dir/quote_progress.json`，不进入 Git；本 worktree 没有真实
行情 `state_dir`，所以 `DATA_READY` 和真实行情复跑仍须由 Claude Code 在目标机确认。

### 2026-09-14 港股开市 12 分钟实测采样

每 90 秒采样一次：09:49:34 来源 09:20、滞后 29.6 分钟；09:51:04 来源 09:31、20.1；
09:52:35 仍为 09:31、21.6；09:54:06 推进至 09:35、19.1；09:55:37 仍为 09:35、20.6；
09:57:08 仍为 09:35、22.1；09:58:38 仍为 09:35、23.6；10:00:09 推进至 09:39、21.2。
结论是来源持续推进、稳态滞后为 19–24 分钟、正常分块更新中的最长连续未变约 6 分钟；
09:49 的 29.6 分钟属于开市追赶尖峰。A 股对照滞后 0.0 分钟，美股休市沿用休市口径。

### 两个独立门与披露

- `HK_FREE_QUOTE_DECLARED_FEED_DELAY_MINUTES = 25`：依据上述 19–24 分钟稳态采样取值，
  加既有 180 秒 TTL 后开市绝对上限为 28 分钟。29.6 分钟开市尖峰仍短暂写
  `QUOTE_SOURCE_STALE`，等待来源追上；不把上限提高到 30 分钟或以上。CN/US 继续为 0。
- `QUOTE_ADVANCE_STALL_MINUTES = 12`：正常最长平台约 6 分钟，取两倍余量。开市时每标的
  只在 `source_time` 前进后更新 `last_advance_at`；连续 12 分钟不推进，即使绝对滞后仍在
  28 分钟内，也写 `QUOTE_FEED_STALLED`。休市不写入推进状态，也不适用该检测。
- `quote_freshness` 公开 `declared_feed_delay_minutes`、`observed_lag_minutes`、
  `last_advance_at` 与 `stalled_minutes`。绝对上限超出为 `QUOTE_SOURCE_STALE`，来源不推进为
  `QUOTE_FEED_STALLED`；同一轮若两项都成立会同时记录两条独立事实。网页港股声明同步为
  “约 25 分钟，非实时”，报价表展示最后推进与连续未推进分钟数。

### 本机验证

- 真实采样回归覆盖：开市 29.6 分钟尖峰阻断且下一采样恢复；6 分钟正常平台后推进不阻断；
  12 分钟未推进且实际滞后低于 28 分钟时阻断 `QUOTE_FEED_STALLED`；35 分钟绝对滞后阻断
  `QUOTE_SOURCE_STALE`；港股午休不应用推进检测；A 股 5 分钟无声明延迟仍阻断。
  `tests/test_marketdata_providers.py` 与 `tests/test_live_api.py` 为 `40 passed in 0.54s`。
- 用户指定完整命令 `PYTHONPATH=src python3 -m pytest tests/ -q`：
  `15 failed, 171 passed, 1 skipped in 19.07s`。7 条为 sandbox 禁止 TCP bind 的
  `PermissionError`；其余 8 条为既有 wheel、formal lifecycle、Python 3.9 `tomllib`、
  根目录 allowlist 与 state-machine/taskpack-seal 基线。新增回归没有增加失败数。
- Python 3.12 已重建 `MANIFEST.json`；
  `scripts/verify_package.py --root . --manifest MANIFEST.json` 输出
  `{"finding_count": 0, "findings": [], "state": "PASS"}`。`node --check web/app.js`
  与 `git diff --check` 通过。清理的唯一暂态产物为本轮 pytest 创建的 `.pytest_cache`。
- Claude Code 真实行情复跑尚未执行，不能以本机夹具代替。

## 2026-09-14 第八轮市场声明行情时延

### 当前目标与状态

本轮把免费源的已知市场时延写入 `Instrument.declared_feed_delay_minutes`，并保持
来源时间、观察时间和开休市三个门各自独立。当前状态为
`STAGE_4_EIGHTH_DECLARED_FEED_DELAY_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE`；
本 worktree 不含真实行情 `state_dir`，所以 `DATA_READY` 仍须由 Claude Code 在目标机
复跑确认。

### 市场声明、依据与判定

| 市场 | 声明值 | 依据 | 开市来源时间上限 |
| --- | ---: | --- | --- |
| HK | 20 分钟 | 港交所免费行情具有固有延迟；20 分钟表示常规公开时延，原有 180 秒 TTL 承接短时刷新抖动，因此不把 15 分钟误作严格实时上限。 | 20 分钟 + 180 秒 |
| CN | 0 分钟 | 当前实测 A 股报价为实时来源时间。 | 180 秒 |
| US | 0 分钟 | 当前实测美股来源未显示声明延迟；开市后的实际滞后持续记录，未来可按实测改配置。 | 180 秒 |

- 盘中仅当 `source_time` 的滞后不超过“声明延迟 + TTL”时才为 `FRESH`；超出仍写
  `QUOTE_SOURCE_STALE` 并阻断。`quote.observed_at` 的既有 TTL 继续独立执行。
- 休市继续使用 `MARKET_CLOSED_RECENT_TRADING_DAY_APPROXIMATION`；无来源时间继续写
  `QUOTE_SOURCE_TIME_MISSING`，腾讯备用源没有可验证来源时间时不具备 `DATA_READY` 资格。
- `quote_freshness` 对每个实时报价标的公开 `declared_feed_delay_minutes` 与
  `observed_lag_minutes`；无报价或无来源时间时后者为 `null`，字段始终存在。

### Owner 可见披露

- `web/app.js` 的“市场行情时效声明”紧邻“最终投资建议”，并在投资建议卡重复显示：
  “港股行情为交易所规定的延迟数据（约 20 分钟），非实时。”
- 同页“报价来源时间”表展示声明延迟、实测滞后、来源时间与允许上限；页眉、加载页与
  metadata 改为“按市场声明时效”，不再作整体实时声明。
- `/api/v1/report/latest` 继续由公共报告视图公开上述 `quote_freshness` 字段。

### 本机验证

- 指定完整命令 `PYTHONPATH=src python3 -m pytest tests/ -q`：
  `15 failed, 167 passed, 1 skipped in 20.08s`。7 条为 sandbox 禁止 TCP bind；其余
  8 条为既有 wheel、formal lifecycle、Python 3.9 `tomllib`、根目录 allowlist、state
  machine 与 taskpack seal 基线。新增港股 22 分钟通过、港股 60 分钟阻断、A 股 5 分钟
  阻断、API 字段公开和网页文案定位回归全部通过，未增加失败数。
- `node --check web/app.js` 与 `git diff --check` 通过。
- 清理 pytest 生成的 `.pytest_cache` 后，Python 3.12 重建 `MANIFEST.json`，
  `scripts/verify_package.py --root . --manifest MANIFEST.json` 输出
  `{"finding_count": 0, "findings": [], "state": "PASS"}`。
- Claude Code 尚未在真实行情环境复跑；该确认仍为下一步，不能由本机回归替代。

## 2026-09-14 第七轮真实行情标定修复

### 当前目标与状态

第六轮三条 high 的语义门、来源时间门和严格 as-of 参数选择继续保留；本轮只修复真实
行情复跑暴露的门槛标定与新浪港股时间解析。当前状态为
`STAGE_4_SEVENTH_LIVE_CALIBRATION_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE`。本 worktree
没有目标机真实行情 `state_dir`，所以尚未声称 `DATA_READY`；仍需 Claude Code 在真实行情
环境复跑确认。

### OHLCV 语义质量：剔除、记账与阻断

- `Bar.ohlcv_violations()` 现在输出精确违规规则，例如
  `LOW_ABOVE_OPEN_OR_CLOSE`、`VOLUME_NEGATIVE`、`OPEN_NONFINITE`。Sina、Tencent、
  EastMoney 日线 provider 均从计算序列剔除单条语义错误 Bar，并记录标的、日期、来源与
  规则；结构损坏/可用 Bar 少于两条仍按既有 `MarketDataError` 阻断。
- `RECENT_DECISION_BAR_LOOKBACK_TRADING_DAYS = 252`：该值是 S1 的最长价格回看
  `r252`，也大于 S1/S2 的 SMA200；异常日期落在已接纳序列最近 252 个交易日窗口内，
  写 `BAR_INVALID_OHLCV_RECENT_DECISION_WINDOW:<symbol>` 并阻断该标的。
- `MAX_DROPPED_INVALID_BARS_PER_SYMBOL = 3` 与
  `MAX_DROPPED_INVALID_BAR_RATIO = 0.005`：最多三个且不超过输入 Bar 的 0.5% 才可称为
  孤立历史坏点；任一超过就写相应 `COUNT_THRESHOLD` / `RATIO_THRESHOLD` 阻断。这样
  1/6460 的 2015 年个例可继续用于今日判断，4 条历史异常或小样本中的高比例异常不能被
  掩盖。
- report 的 `bar_quality` 与 `data_quality_findings` 公开剔除/输入数、比例、近期窗口、
  阈值、阻断原因和最多五条样例；网页的“日线质量记账”在 `DATA_READY` 与阻断页都可见。

### 报价时效：交易所本地开休市口径

- 使用每个 `Instrument.timezone` 与常规交易时段：US 09:30–16:00、CN
  09:30–11:30 / 13:00–15:00、HK 09:30–12:00 / 13:00–16:00（均为当地时间，周末必为
  休市）。开市按现有 `quote_max_age_seconds` 分钟级 TTL；三倍 TTL 卡住仍为
  `QUOTE_SOURCE_STALE`。
- 休市不使用无限放宽 TTL，而是
  `CLOSED_MARKET_SOURCE_MAX_AGE_DAYS = 4` 的最近交易日近似。四天覆盖周五收盘到周二
  开市前的周末/单日假期；超过四天必须等可验证的新来源时间。法定长假尚未接入精确交易日历，
  这是明确的近似边界。
- report 的 `quote_freshness` 逐标的公开 `OPEN` / `CLOSED`、
  `MARKET_OPEN_TTL` / `MARKET_CLOSED_RECENT_TRADING_DAY_APPROXIMATION`、来源时间、年龄
  与允许上限；网页“报价来源时间”在两种报告状态均可见。

### 新浪/腾讯报价来源时间与选源

| 市场 | 新浪代码与实测字段 | 解析格式 | 解释时区 |
| --- | --- | --- | --- |
| 美股 | `gb_*`，单字段内日期时间 | `YYYY-MM-DD HH:MM:SS` | `America/New_York` |
| A 股 | `sh*` / `sz*`，独立日期、时间字段 | `YYYY-MM-DD`, `HH:MM:SS` | `Asia/Shanghai` |
| 港股 | `hk*`，独立日期、时间字段 | `YYYY/MM/DD`, `HH:MM` 或 `HH:MM:SS` | `Asia/Hong_Kong` |

- 新浪时间正则已接受港股的斜杠日期与无秒独立分钟字段，例如
  `2026/09/11,16:09`。三个市场的真实格式片段均有回归断言。
- `qt.gtimg.cn` 本轮实测片段没有可解析日期时间；`TencentQuoteProvider` 将
  `source_time=None` 原样保留，绝不以 `observed_at` 补造。它不具备 `DATA_READY` 资格。
- 选源顺序是带可验证来源时间的新浪主源优先；仅当新浪的合格来源时间缺失时才尝试 A/H
  腾讯备用。若腾讯也不能给来源时间，报告保留实际来源并写
  `QUOTE_SOURCE_TIME_MISSING`，不产生结论。回归确认已有时间戳的新浪港股不会请求或覆盖为
  腾讯备用结果。

### 第七轮定向验证

```text
PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src \\
  python3 -m pytest tests/test_marketdata_providers.py tests/test_live_runtime.py \\
  tests/test_live_api.py tests/test_backtest.py -q
47 passed
node --check web/app.js
git diff --check
```

新增回归包括：远期单条坏 Bar 记账且不阻断、近期坏 Bar 阻断、超数量阈值阻断、周末周五
来源时间通过、开市三倍 TTL 卡住阻断、三市场新浪时间解析、腾讯无时间不具备资格、以及
新浪主源带时间时不调用腾讯覆盖。

用户指定完整命令的本轮输出为 `15 failed, 164 passed, 1 skipped in 20.62s`：5 条
`test_api.py` 与 2 条 `test_public_release.py` 是本 sandbox 禁止 TCP bind 的
`PermissionError`；其余 8 条仍是既有 wheel/formal lifecycle/Python 3.9 `tomllib`/
根目录 allowlist/state machine/taskpack seal 基线。本轮没有增加非 sandbox 红灯。

`/Users/linzezhang/.local/bin/python3.12 scripts/verify_package.py --root . --manifest
MANIFEST.json` 在重建 Manifest 后为 `PASS, finding_count=0`。完整测试产生的
`.pytest_cache` 已由 `scripts/clean_transients.py` 移除；没有清理源码、业务数据或
受跟踪的 `v19_release/dist` 证据。

## 当前目标

修复第六轮对抗性审查确认的三条 high：语义错误的 OHLCV 不得进入缓存、指标或实时
结论；报价必须具备可验证的 provider 来源时间；实盘 S1/S2 verdict 必须使用严格 as-of
训练窗选出的同一组参数。现有数据新鲜度阻断、未实现分支权重为 0 与 S2 的 PROMO-1
排除保持原状；Stage 5 部署不在本轮范围内。

## 当前状态

STAGE_4_SIXTH_ADVERSARIAL_REMEDIATION_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE。第六轮
定向回归为 `45 passed in 2.18s`；用户指定完整命令为
`15 failed, 158 passed, 1 skipped in 15.36s`。其中 7 条是 sandbox 禁止 TCP bind
（`test_api.py` 5 条、`test_public_release.py` 2 条），其余 8 条是既有
deployment/formal lifecycle/Python 3.9 `tomllib`/root allowlist/state machine/taskpack seal
基线；本轮未增加红灯。Python 3.12 `scripts/verify_package.py --root . --manifest
MANIFEST.json` 为 `PASS, finding_count=0`，最终 Manifest 已重建。没有本机真实行情
state_dir，本轮不声明新的 S1 样本外数字；需 Claude Code 在其真实行情环境复跑。

STAGE_4_FIFTH_ADVERSARIAL_REMEDIATION_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE。当前 worktree 没有目标机的运行期
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

## 2026-09-14 第六轮对抗性审查修复

- `marketdata.models.has_valid_ohlcv()` 是 provider 解析、缓存命中重解析和
  `LiveEngine._validate()` 共同使用的唯一 Bar 语义门。它要求所有已提供数值有限，
  `open/close/high/low > 0`，`volume is None or volume >= 0`，并且
  `low <= min(open, close)`、`high >= max(open, close)`、`low <= high`。任一新响应
  出现形状错误不写缓存；缓存命中有错误只删除该键并受限重拉一次；运行时拿到形状错误
  Bar 写 `BAR_INVALID_OHLCV:<symbol>` 并形成 `SYSTEM_BLOCKED`。
- 腾讯报价解析 `qt.gtimg.cn` 负载中的 `YYYYMMDDhhmmss` provider 时间；新浪的 US、A、H
  日期/时间字段支持空格、逗号或 `T` 分隔。`observed_at` 只记录本机观察时刻，绝不替代
  来源时间。任何实时报价没有 provider 时间写
  `QUOTE_SOURCE_TIME_MISSING:<symbol>:<source>`；来源时间早于
  `quote_max_age_seconds` 写 `QUOTE_SOURCE_STALE:<symbol>`，两者均阻断为
  `SYSTEM_BLOCKED`。
- 回测每个 walk-forward 窗口现同时保存 `chosen_parameters` 与可被 runtime 直接消费的
  `active_config`。`select_active_config()` 只从 `test_evaluable=true` 的窗口中选择
  `train_end <= config_as_of` 的最新项，输出 `active_config`、`config_as_of`、
  `config_source_window` 和 `config_status`。`train_end == config_as_of` 允许：当日收盘后
  训练样本完整，选择未读取 as-of 之后的 Bar；同一选择过程从不读取 test 指标。
  没有合格窗口时两条分支都是 `BACKTEST_CONFIG_UNAVAILABLE`、权重为 0，不能回退到默认
  参数。
- `build_branch_report()` 将上述 S1/S2 配置注入实际 verdict，逐标的 `evidence`、顶层
  `active_strategy_configs`、私有运行期报告和公开 API 都显示同一套
  `active_config/config_as_of/config_source_window`。S2 仍按 PROMO-1 决定是否参与权重，
  其配置注入路径与 S1 相同。
- 定向回归覆盖：三家日线 provider 的新响应和缓存命中、倒挂/收盘越界/open 非正/负成交量、
  运行时语义 Bar 阻断、腾讯/新浪来源时间、来源时间缺失和过期、实盘 verdict 参数与
  产生证据的窗口参数相等，以及未来训练窗即使指标更优也不能越过 as-of 选择。

## 2026-09-14 第五轮对抗性审查修复

- `openapi.yaml` 现在是 `0.0.0.3.3` 的 V2 只读契约，只声明 `/`、`/health/live`、
  `/health/ready`、`/api/v1/{metadata,heartbeat,system/status,report/latest}` 与
  `/api/v1/whitebox/{summary,skills,backtest/latest}` 十条真实 GET 路由。
  `v2_get_route_responses()` 是 handler 的实际具名路由表；回归测试从该表取得实际集合，
  与 OpenAPI `paths` 双向精确比对，并断言每条都是 GET。
- 契约的 `x-removed-legacy-interfaces` 保留了全部已移除的旧接口记录。特别是
  `POST /api/v1/inputs/market-snapshot` 与
  `POST /api/v1/inputs/skill-signal` 标为 `REMOVED_NOT_PROVIDED`：V2 只从
  marketdata provider 读取行情，不再接受外部快照或 Skill signal 写入，冻结 fixture
  不能经旧写接口伪装为实时行情。
- 公开收益样本不足时，`ProfitabilityLimitedBacktest` 明确只包含状态、
  `OOS_HISTORY_INSUFFICIENT: N/6`、门槛和非数值说明；公开路由不输出窗口收益、
  指标、贡献样本或权重轨迹。
- `LiveEngine._validate()` 按每个 `Instrument.timezone` 计算当地时间与当地交易日。
  日线序列中任一日期晚于当地日期写入
  `BAR_FUTURE_DATE:<symbol>:<bar_day>:<exchange_today>`，使整轮为 `SYSTEM_BLOCKED`；
  该状态不运行回测或分支决策。Sina、Tencent、EastMoney 三家日线 provider 的新响应
  和缓存命中均由相同运行时门覆盖。
- 时间复查结论：`LiveStore.liveness()` 的报告与心跳均检查未来偏移和过期；报价
  `observed_at` 检查未来偏移和过期；`source_time` 现按交易所本地完整时间检查未来
  偏移和过期；日线 `bar.day` 现按交易所当地交易日检查未来与过期。provider 解析、
  缓存、`data_cutoff`、回测和公开响应不另行放宽这些门。历史文件命名只用于存储，
  API 的 `server_time` 只由服务端即时生成。未发现 V2 活跃路径中的另一处单向时间
  校验；未由 V2 handler 调用的旧 V1 模块不属于此 V2 契约与决策链。
- 定向回归：

      PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/test_live_api.py tests/test_marketdata_providers.py tests/test_live_runtime.py -q

  结果：`26 passed in 0.20s`。其中覆盖 OpenAPI 路由集合双向比对、已移除写接口记录、
  交易所时区差异、未来来源时间、未来日线导致 `SYSTEM_BLOCKED`，以及三家 provider
  的新响应和缓存命中路径。

- 用户指定完整测试：

      PYTHONPATH=src python3 -m pytest tests/ -q

  结果：`15 failed, 152 passed, 1 skipped in 35.32s`。7 条失败是 sandbox 禁止 TCP
  bind（`test_api.py` 5 条、`test_public_release.py` 2 条）；其余 8 条是既有
  deployment/formal lifecycle/Python 3.9 `tomllib`/root allowlist/state machine/taskpack
  seal 基线。第五轮新增夹具全部通过，未增加非 sandbox 红灯。
- `scripts/clean_transients.py` 现精确保留受跟踪的 `v19_release/dist` 历史 wheel
  证据，只清理可再生缓存；专用回归为 `1 passed`。本轮曾由旧的泛化 `dist` 规则误删
  该目录，四个 wheel 已从当前 HEAD 完整恢复，未遗留删除。
- `/Users/linzezhang/.local/bin/python3.12 scripts/verify_version_lock.py --root .` 为
  `PASS, version=0.0.0.3.3`；重建 `MANIFEST.json` 后，同一 Python 3.12 的
  `scripts/verify_package.py --root . --manifest MANIFEST.json` 为
  `PASS, finding_count=0`。

## 2026-09-14 第四轮对抗性审查修复

- 发布身份的唯一手写源是 `pyproject.toml [project].version = 0.0.0.3.3`。
  `signal_lattice.version` 在源码树读取该文件，在 wheel 内读取安装包元数据；
  `constants.VERSION`、`__version__` 与 `live_config.APP_VERSION` 全部消费这一个解析结果。
  发布脚本也从同一 `pyproject.toml` 生成 Manifest/Subject Lock/版本锁，避免运行代码、
  任务执行合同和制品清单分别声明版本。
- S1 调仓改为 SELL、BUY 两个确定性阶段。全部卖单先以完整卖出费用更新现金，随后才按
  `quantity × price + order_cost_usd(BUY)` 二分求可买的最大整股数；同一逻辑同时用于
  consensus 调仓。目标标的 AAA 排在旧仓 ZZZ 前的夹具断言：同一交易日先卖 ZZZ 再买 AAA，
  `skipped_infeasible = 0`，不再由 ticker 排序产生延迟换仓。
- `MAX_FUTURE_CLOCK_SKEW_SECONDS = 60`：60 秒覆盖写盘/请求级时钟微偏移，远低于默认
  270 秒就绪 TTL。报告或心跳领先当前时间超过该值分别产生
  `REPORT_CLOCK_AHEAD` / `HEARTBEAT_CLOCK_AHEAD`，API 一律回退
  `SYSTEM_BLOCKED/COLLECTION_LOOP_UNREACHABLE`。唯一的 `latest_for_api` 读取门已覆盖
  所有读取运行期报告的公开路由；`/health/live` 不读取报告。运行期报价也使用同一界限，
  防止未来观察时间形成新的 DATA_READY。
- 历史 v19 wheel 位于受跟踪的 `v19_release/dist/`，是旧制品证据而非当前候选源码。
  Package Guard 现在与 Manifest 采用一致排除口径；本地 `.pytest_cache` 已可恢复地移至
  `/private/tmp/signal-lattice-pytest-cache-preexisting-20260914`，未删除源码或业务数据。
- 定向回归：`tests/test_backtest.py tests/test_live_api.py tests/test_live_runtime.py
  tests/test_task_execution.py` 为 `21 passed`。用户指定完整命令在本 sandbox 的 Python 3.9
  下为 `15 failed, 146 passed, 1 skipped`：7 条是禁止 TCP bind 的 `PermissionError`；其余
  8 条仅属于既有 deployment/formal lifecycle/Python 3.9 `tomllib`/root allowlist/state machine/
  taskpack seal 类别。完整测试随后生成的缓存已可恢复地移至
  `/private/tmp/signal-lattice-pytest-cache-full-20260914`。
- `/Users/linzezhang/.local/bin/python3.12 scripts/verify_version_lock.py --root .` 输出
  `PASS, version=0.0.0.3.3`；同一 Python 3.12 下 `scripts/verify_package.py` 为
  `PASS, finding_count=0`。`MANIFEST.json`、`SUBJECT_LOCK.json` 和任务执行合同已重建并
  全部绑定 `0.0.0.3.3`。

## 2026-09-14 第三轮对抗性审查修复

- `live_api.py` 在每个公开 GET 路由取得 `latest` 后先构造深拷贝的公共视图；私有
  `state_dir/latest.json` 与 `state_dir/backtest/latest.json` 继续完整保存内部回测输入。
  当 `sample_sufficiency` 为 `OOS_HISTORY_INSUFFICIENT: N/6` 时，公共视图只保留状态、
  门槛、N/M 与非数值说明，移除 `stitched`、所有回测窗口、`test_metrics`、贡献样本、
  贡献汇总、累计贡献数值和逐期权重轨迹。
- 覆盖的公开路由为 `/api/v1/report/latest`、`/api/v1/whitebox/backtest/latest`、
  `/api/v1/whitebox/summary`、`/api/v1/whitebox/skills`、`/api/v1/heartbeat`、
  `/api/v1/metadata`、`/api/v1/system/status` 与 `/health/ready`。静态文件和
  `/health/live` 不读取运行期报告。
- Sina 报价/日线、Tencent 报价/日线、EastMoney 日线的字节解码统一经
  `marketdata.base.decode_text` 转换为 `MarketDataError`；JSON 协议解析继续以
  `MarketDataError` 返回给 `MarketGateway` 的既有阻断链。
- `LiveEngine.run_once()` 现覆盖从心跳写入、采集、校验、回测、构造到落盘的完整
  运行期；未预期 `Exception` 写入带
  `blocked_reason=UNEXPECTED_RUNTIME_FAILURE` 的新 `SYSTEM_BLOCKED` 报告，阻止旧
  `DATA_READY` 在就绪 TTL 内继续对外可用。严格 JSON 非有限数值仍使用专属阻断报告。
- 新增夹具：逐个公共 API 响应序列化后断言不含真实收益数值 `5.4753`、`-78.5628`
  及收益结构键，同时确认私有 latest 仍保留完整数据；非 GBK Tencent 备用响应经
  `MarketGateway` 后立即覆盖旧 DATA_READY，`/health/ready` 返回 503；未知运行期
  异常同样覆盖旧 DATA_READY。
- 定向回归：

      PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src python3 -m pytest tests/test_live_api.py tests/test_marketdata_providers.py tests/test_live_runtime.py -q

  结果：`20 passed in 0.42s`。

- 用户指定完整测试：

      PYTHONPATH=src python3 -m pytest tests/ -q

  结果：`18 failed, 140 passed, 1 skipped in 14.59s`。7 条失败是 sandbox 禁止 TCP
  bind 的 `PermissionError`（`test_api.py` 5 条、`test_public_release.py` 2 条）；其余
  11 条为既有部署、正式生命周期、Python 3.9 缺少 `tomllib`、交付文件清单和状态机
  基线失败。本轮新增夹具全部通过。

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
- src/signal_lattice/version.py
- web/app.js
- tests/test_backtest.py
- tests/test_branch_verdicts.py
- tests/test_weighting.py
- tests/test_marketdata_providers.py
- tests/test_live_api.py

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

## 2026-09-14 第二轮对抗性审查修复

- 就绪 TTL：`READY_TTL_LOOP_MULTIPLIER = 3` 与 `READY_TTL_FETCH_ALLOWANCE_SECONDS = 90`；
  `TTL = 3 × loop_seconds + 90 秒`，默认 60 秒循环为 270 秒。循环每轮开始写
  `state_dir/heartbeat.json`；API 同时检查 `latest.generated_at` 与心跳。任一超过 TTL 时，
  `/health/ready` 返回 503，`/api/v1/report/latest` 返回
  `SYSTEM_BLOCKED/COLLECTION_LOOP_UNREACHABLE` 和“采集循环失联，结论已过期”，与
  “数据链路不完整，不出结论”保持不同原因与文案。
- History 预算：默认 60 秒循环的完整美股交易月最多约 `390 分钟 × 21 日 = 8,190`
  次候选变化。仅记录报价增量与四字段决策摘要，按
  `market_changes-YYYY-MM-DD.jsonl` 分日；每日至多 240 条且 64 KiB，保留 31 天，
  运行期硬上限 `31 × 64 KiB = 1.94 MiB`。每次 `save()` 自动清理过期分日文件及
  旧的全量 `market_changes.jsonl`；`history_storage` 在 latest report 中公开当前条数、
  字节数和预算，回测/分支全量结果不再写入 history。
- 收益证据门：保留 `MIN_COMPLETE_WINDOWS = 2` 作为“结构上可计算”门，新增
  `MIN_OOS_WINDOWS_FOR_PROFITABILITY = 6`。6 个 6 个月窗口等于 3 年，精确对齐
  PROMO-1 的 `min_years = 3.0`，对 S1/S2 同等适用；不降低 S2 的 PROMO-1。低于
  此门时，顶层 `profitability_status` 为
  `OOS_HISTORY_INSUFFICIENT: N/6` 且不输出任何超额收益数字。方向性结论继续保留，
  但 `decision.sample_sufficiency` 与页面显著说明“样本外历史不足，仅供研究参考，
  不构成收益证据”；页面同时隐藏收益和逐窗口业绩数字。
- 本轮新增夹具：过期报告/心跳的无 TCP endpoint 测试、history 条数/容量/全量负载回归、
  收益门与方向性标记回归。定向命令
  `PYTHONPYCACHEPREFIX=/private/tmp/signal-lattice-pycache PYTHONPATH=src python3 -m pytest tests/test_live_api.py tests/test_live_runtime.py tests/test_backtest.py -q`
  结果 `11 passed in 2.02s`；`py_compile` 与 `node --check web/app.js` 通过。用户指定完整命令
  `PYTHONPATH=src python3 -m pytest tests/ -q` 结果为 `18 failed, 136 passed, 1 skipped in 17.27s`：
  7 条为 sandbox 禁止 TCP bind 的 `PermissionError`（`test_api.py` 5 条、
  `test_public_release.py` 2 条），其余 11 条为既有 deployment/formal lifecycle/
  Python 3.9 缺 `tomllib`/交付清单/状态机基线，新增夹具没有失败。

## 下一步

Claude Code 侧用真实行情与当前目标机 `state_dir` 复跑 S1/S2；本 worktree 没有完整
行情输入，不能诚实地产生修复后超额收益、最大回撤或参数选择的新数字。S1 还需 4 条
可用样本达到 8/8；S2 继续以 PROMO-1 的实际结果维持排除。只有至少两个已资格分支
各自满足样本门时，Hedge 才会形成有比较意义的相对动态权重。Stage 5 部署不在本轮范围内。
