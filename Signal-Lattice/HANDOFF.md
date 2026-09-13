# Signal Lattice V2 重建交接

更新时间：2026-09-13 Australia/Sydney

## 当前目标

Stage 2：在 Stage 1 已由具备网络出口的验收方完成真实行情验收后，用真实日线产出可复算的分支结论，并由汇总中枢合成为唯一投资建议；不开展 Stage 3 贡献度权重、Stage 4 回测或 Stage 5 部署。

## 当前状态

`STAGE_2_AGGREGATION_IMPLEMENTED_LOCAL_VALIDATION_COMPLETE`。Stage 1 commit 为 `034e1ad2b`，外部真实行情验收已确认 `DATA_READY`、数据源与截止日；新本地 sandbox 不联网、不 SSH，只做确定性代码与本地测试。

## 关键决定

- `src/signal_lattice/branches/` 是 Stage 2 唯一的实时分支入口。`BranchVerdict` 始终包含方向、公式置信度、数值证据、最大反证、可判定失效条件、实际窗口、实现状态和权重。
- `indicators.py`、`bars.py`、`s1_momentum.py`、`s2_meanrev.py` 均从 `Alpha/backend/app/strategies/` 复制并在文件头注明来源；不跨目录 import。S1/S2 参数逐值来自 Alpha 的 `s1_momentum.yaml` / `s2_meanrev.yaml`，以显式默认字典和可选覆盖替代 YAML 路径读取。
- S1 是完整八标的资产池排名策略。实时宇宙现已包含并能获取 `SPY/QQQ/IWM/EFA/EEM/GLD/TLT/BIL` 的日线；S1 对这八个标的正常计算，其他观察标的仍明确为 `OUT_OF_STRATEGY_UNIVERSE`、权重 0。
- S2 仍可复算 RSI(2)+IBS+趋势+ATR 的研究信号。Alpha 原始配置 `enabled_pending_backtest: true`，而 Stage 2 不计算回测或 Alpha，因此 `backtest_promotion_passed=null`、`EXCLUDED_PENDING_BACKTEST`、权重 0；它不会进入最终方向汇总。
- 汇总模式固定为 `COLD_START_EQUAL`，`weight_sample_count=0`。每个标的仅使用 `weight>0` 的 verdict：方向按权重投票，最高票平票统一裁决为中性；置信度为 `sum(confidence_i * weight_i) / sum(weight_i)`。标的 conviction 为 `confidence * direction_vote_share`；方向性标的按 conviction、confidence、symbol 的固定顺序选出 `primary_symbol`。中性组合的 conviction 使用所有参与 verdict 的同一加权平均。
- 中性观望阈值是命名常量 `NEUTRAL_WATCH_CONFIDENCE_THRESHOLD=0.60`：低于阈值为 `NEUTRAL_LOW_CONVICTION/action=观望`，达到阈值为 `NEUTRAL_CONSENSUS/action=观望`。0.60 表示参与结论平均至少提供六成公式置信度才解读为较强中性一致性；两种情况都不伪造方向。
- 状态机：数据不新鲜直接为 `SYSTEM_BLOCKED/action=null` 且不执行分支；数据就绪但无正权重 verdict 为 `NO_ELIGIBLE_BRANCH/action=null`，逐个列出排除分支及原因；有方向性标的时为 `DIRECTIONAL_CONCLUSION`。
- `profitability_status=NOT_PRODUCED_STAGE_2_NO_BACKTEST`；本轮不填收益率或 Alpha 数字。

## 六个技能分支的实现判断

| 分支 | 判断 | Stage 2 依据 | 运行时状态 |
|---|---|---|---|
| `stock-commercial-opportunities` | 未实现 | `SKILL.md` 要求已打开的一手商业、敞口、估值与催化剂证据；实时日线不含这些输入。 | `UNIMPLEMENTED`，权重 0 |
| `bottleneck-serenity-skill` | 未实现 | `02_ARCHITECTURE_DATA_API.md` 定义任务包和审计结构，未给出可由当前 Bar 序列运行的确定性结论公式。 | `UNIMPLEMENTED`，权重 0 |
| `equity-foresight-signal` | 未实现 | `SKILL.md` 要求冻结的点时数据集、训练配置与宿主信任上下文，当前网关仅提供日线。 | `UNIMPLEMENTED`，权重 0 |
| `global-equity-lead-lag-atlas` | 未实现 | `SKILL.md` 要求带交易会话和收盘时点的多市场现金指数；当前观察宇宙不具备该输入合同。 | `UNIMPLEMENTED`，权重 0 |
| `equity-event-atlas` | 未实现 | `SKILL.md` 要求交易所、监管、发行人事件证据和市场能力门；当前网关未采集事件证据。 | `UNIMPLEMENTED`，权重 0 |
| `serenity-skill` | 未实现 | 本仓不存在 `Stock_Skill/serenity-skill/task-pack/` 的 `SKILL.md` / 架构契约；运行清单只指向外部 source-only 路径。 | `UNIMPLEMENTED`，权重 0 |

上述六项都保留逐标的 verdict，明确显示“未实现，不参与加权”，没有非零占位权重。

## 已改文件

- `src/signal_lattice/aggregate.py`：唯一汇总中枢；生成逐标的加权结论、所有排除原因、组合 `decision`、平票规则、0.60 中性观望阈值与阻断态决策合同。
- `src/signal_lattice/branches/runtime.py`：只生成分支 verdict，再交给汇总中枢；不再在分支运行时内实现第二套汇总逻辑。
- `src/signal_lattice/live_runtime.py`、`src/signal_lattice/live_api.py`：数据就绪时消费中枢的 `aggregate` 与 `decision`；运行时阻断态和 API 无 latest report 回退均复用完整 `SYSTEM_BLOCKED` 决策，不再各自硬编码窄 `decision`。
- `web/app.js`：最终投资建议与内部协调真实渲染 `decision`；明确区分“有数据但没有可用分支”和“数据链路不完整”。
- `tests/test_aggregate.py`：固定 verdict 夹具验证加权投票、加权置信度、平票、严格阈值边界、`NO_ELIGIBLE_BRANCH`、`SYSTEM_BLOCKED` 与方向性 `primary_symbol`。

## 已验证

```bash
PYTHONPATH=src python3 -m pytest tests/test_aggregate.py tests/test_branch_verdicts.py tests/test_marketdata_providers.py tests/test_live_api.py -q
```

结果：`16 passed in 0.11s`。

- 覆盖汇总加权投票、平票中性裁决、0.60 严格阈值、无可用分支、数据阻断、S1/S2 的固定序列方向与 confidence 公式、S2 回测门权重 0、六个技能分支权重 0、Stage 1 新鲜度阻断/可用状态和 live API 阻断响应。
- `node --check web/app.js` 与 `git diff --check` 已通过。

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
```

结果：`111 passed, 1 skipped, 18 failed in 10.72s`。18 项失败均为本次改动外的既有 11 项（wheel count 1、formal lifecycle canonical version 4、Python 3.9 缺少 `tomllib` 2、根目录交付清单 1、state machine 2、taskpack seal 1）和本 sandbox 禁止 `127.0.0.1` 监听的 7 项（`test_api.py` 5、`test_public_release.py` 2）。新增汇总测试没有引入失败。

## 未解决风险

- S2 的自建回测推广门没有结果，保持不参与汇总。Stage 4 才能产生该证据。
- 六个技能分支均缺少与当前实时输入兼容的确定性实现，保持未实现。
- 本 sandbox 禁止 TCP 监听，因此 `tests/test_api.py::T::test_ui` 在 `setUp` 前即失败；具备 TCP 的验收环境可运行原测试，确认动态页面。

## 下一步

具备 TCP 监听权限的验收环境可重跑 `tests/test_api.py::T::test_ui`；真实行情验收与部署继续由 Claude Code 侧负责。S2 要进入汇总需先完成 Stage 4 自建回测推广门；六个未实现技能需先具备与当前实时输入一致的确定性方法和输入合同。
