# Signal Lattice V2 重建交接

更新时间：2026-09-13 Australia/Sydney

## 当前目标

Stage 2：在 Stage 1 已由具备网络出口的验收方完成真实行情验收后，用真实日线产出可复算的分支结论，重建只读页面契约；不开展 Stage 3 贡献度权重、Stage 4 回测或 Stage 5 部署。

## 当前状态

`STAGE_2_CODE_COMPLETE_LOCAL_VALIDATION_COMPLETE`。Stage 1 commit 为 `034e1ad2b`，外部真实行情验收已确认 `DATA_READY`、数据源与截止日；新本地 sandbox 不联网、不 SSH，只做确定性代码与本地测试。

## 关键决定

- `src/signal_lattice/branches/` 是 Stage 2 唯一的实时分支入口。`BranchVerdict` 始终包含方向、公式置信度、数值证据、最大反证、可判定失效条件、实际窗口、实现状态和权重。
- `indicators.py`、`bars.py`、`s1_momentum.py`、`s2_meanrev.py` 均从 `Alpha/backend/app/strategies/` 复制并在文件头注明来源；不跨目录 import。S1/S2 参数逐值来自 Alpha 的 `s1_momentum.yaml` / `s2_meanrev.yaml`，以显式默认字典和可选覆盖替代 YAML 路径读取。
- S1 是完整八标的资产池排名策略。当前实时宇宙只具备 `SPY` 与 `QQQ`，缺少 `IWM/EFA/EEM/GLD/TLT/BIL`；这会改变 `top_n` 排名。因此 S1 在真实实时报告中输出 `CONFIGURED_UNIVERSE_INCOMPLETE`、方向 `不适用`、权重 0，不以两个标的的部分排名代替完整策略。
- S2 仍可复算 RSI(2)+IBS+趋势+ATR 的研究信号。Alpha 原始配置 `enabled_pending_backtest: true`，而 Stage 2 不计算回测或 Alpha，因此 `backtest_promotion_passed=null`、`EXCLUDED_PENDING_BACKTEST`、权重 0；它不会进入最终方向汇总。
- 汇总模式固定为 `COLD_START_EQUAL`：只对 `implemented=true`、`weight>0` 且 `COLD_START_ELIGIBLE` 的分支归一化。当前没有满足条件的贡献分支，故每个标的的汇总为 `不适用`、`action=null`。`accumulated_samples=0`，`profitability_status=NOT_PRODUCED_STAGE_2_NO_BACKTEST`。
- 数据不新鲜仍由 Stage 1 新鲜度门直接返回 `SYSTEM_BLOCKED`。阻断态不计算分支，页面整页只显示“数据链路不完整，不出结论”。

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

- `src/signal_lattice/branches/`：Stage 2 数据合同、Alpha 指标/Bar 适配、S1/S2 纯函数、逐标的 verdict 和冷启动汇总。
- `src/signal_lattice/live_runtime.py`：在 `DATA_READY` 后计算分支；报告补充 `bar_sources`、标的元数据、`aggregate`、协调与盈利状态。阻断态保持无动作。
- `web/index.html`、`web/app.js`、`web/styles.css`：恢复 `skip-link`、44px 触控目标和减少动画支持；展示数据来源/条数、独立分支、最终投资建议及内部协调。阻断态只渲染指定阻断语句。
- `tests/test_branch_verdicts.py`：固定日线夹具验证 S1/S2 方向与从 evidence 重算出的 confidence，并验证六个未实现分支恒为权重 0。

## 已验证

```bash
PYTHONPATH=src python3 -m pytest tests/test_branch_verdicts.py tests/test_marketdata_providers.py tests/test_live_api.py tests/test_project_files.py::T::test_ui_accessibility_contract -q
```

结果：`12 passed in 0.09s`。

- 覆盖 S1/S2 的固定序列方向与 confidence 公式、S2 回测门权重 0、六个技能分支权重 0、Stage 1 新鲜度阻断/可用状态、live API 阻断响应和 UI 无障碍静态契约。
- `py_compile` 在通过上述 pytest 后尝试写入 macOS 全局 Python 缓存目录，受 sandbox 拒绝；pytest 已成功导入和执行新增模块。该拒绝不代表源码语法失败。

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
```

结果：`106 passed, 1 skipped, 18 failed in 8.48s`。其中 11 个是接手前既有基线：wheel count 1、formal lifecycle canonical version 4、Python 3.9 缺少 `tomllib` 2、根目录交付清单 1、state machine 2、taskpack seal 1。另有 7 个是本 sandbox 禁止 `127.0.0.1` 监听：`test_api.py` 5 和 `test_public_release.py` 2。新增的无障碍 UI 测试已通过；页面文字契约使用同一静态文件直接校验，包含“最终投资建议”“内部协调”“skip-link”、`prefers-reduced-motion` 和 `min-height:44px`。

## 未解决风险

- 当前 S1 原始配置资产池与 Stage 1 观察宇宙不一致，真实报告不会给 S1 加权结论；要启用需在未来经版本化决策补齐完整资产池，而不是缩小配置。
- S2 的自建回测推广门没有结果，保持不参与汇总。Stage 4 才能产生该证据。
- 六个技能分支均缺少与当前实时输入兼容的确定性实现，保持未实现。
- 本 sandbox 禁止 TCP 监听，因此 `tests/test_api.py::T::test_ui` 在 `setUp` 前即失败，无法通过其 HTTP 路径再次命中页面文字断言；静态文字契约已直接验证，具备 TCP 的验收环境可运行原测试。

## 下一步

具备 TCP 监听权限的验收环境可重跑 `tests/test_api.py::T::test_ui`；真实行情验收与部署继续由 Claude Code 侧负责。S1 要进入汇总需先完成完整八标的资产池接入的版本化决策，S2 要进入汇总需先完成 Stage 4 自建回测推广门。
