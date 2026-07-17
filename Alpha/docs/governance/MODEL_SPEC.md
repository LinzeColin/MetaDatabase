# Alpha Model Specification

> 2026-07-17 起本规范为旧治理框架历史存档:产品契约由 `Alpha/AGENTS.md`(Live MVP v1,
> 受控许可模型)与 `Alpha/machine/facts/` 取代;旧 paper-only 定位与禁令废止,默认失败关闭不变。
> 本文件描述的 MOD-001..009 为旧 paper 阶段模型,仅在对应代码仍在役期间作参考。

Project: `Alpha`
Governance spec version: `1.0.0`
Fact discipline: `EXTRACTED`, `RECONSTRUCTED`, `PROPOSED`, `UNKNOWN`, `NOT_APPLICABLE`

Machine counts below are controlled by the registries:

- model_count: 9
- formula_count: 9
- parameter_count: 55

## Canonical Sources

- Models: `docs/governance/model_registry.yaml`
- Formulas: `docs/governance/formula_registry.yaml`
- Parameters: `docs/governance/parameter_registry.csv`
- Delivery tasks: `docs/governance/delivery_tasks.yaml`
- Traceability: `docs/governance/TRACEABILITY_MATRIX.csv`

Legacy files `功能清单`, `开发记录`, and `模型参数文件` are compatibility indexes only.

## A. Model Overview

| ID | Name | Kind | Status | Version | Evidence |
|---|---|---|---|---|---|
| MOD-001 | Momentum strategy tournament ranking | ranking_model | active | strategy-tournament-v0 | `Alpha/backend/app/services/strategy_iteration.py:28` |
| MOD-002 | Research risk score | risk_model | active | risk-score-v0 | `Alpha/backend/app/services/risk.py:22` |
| MOD-003 | Pre-trade owner-review gate | deterministic_rule_engine | active | pre-trade-gate-v0 | `Alpha/backend/app/services/risk.py:40` |
| MOD-004 | Live order policy and fail-closed broker | risk_model | active | live-policy-fail-closed-v0 | `Alpha/backend/app/services/policy.py:38`; `Alpha/backend/app/services/live_broker.py:19` |
| MOD-005 | Paper trading loop | deterministic_workflow_model | active | paper-loop-v0.0.3-shutdown-faults | `Alpha/backend/app/services/paper_trading_loop.py:42`; `Alpha/backend/app/services/paper_trading_loop.py:59`; `Alpha/backend/app/services/agent_runtime.py:58` |
| MOD-006 | Paper broker accounting | business_calculation_model | active | paper-broker-v0.0.1-atomic-storage | `Alpha/backend/app/services/paper_broker.py:44`; `Alpha/backend/app/services/atomic_json_store.py:31` |
| MOD-007 | Approval queue freshness | deterministic_rule_engine | active | approval-freshness-v0.0.1-atomic-storage | `Alpha/backend/app/services/approval_queue.py:19`; `Alpha/backend/app/services/atomic_json_store.py:31` |
| MOD-008 | Strategy DSL safety validation | deterministic_rule_engine | active | strategy-dsl-v0 | `Alpha/backend/app/schemas/strategy_dsl.py:22` |
| MOD-009 | Equal-weight buy-and-hold fixture benchmark | backtest_strategy | active | buy-hold-fixture-v0 | `Alpha/backend/app/services/backtest.py:14` |

Use cases(2026-07-17 修订): 受控实盘交易(唯一执行网关+十一门禁+预签授权)、研究、回测、Paper/Shadow 验证、风控门禁、审计与通知。Non-use cases: 公开买卖建议、外部资金管理、杠杆、保证金、做空、期权、期货、加密实盘(MVP 全部禁止,见 `Alpha/AGENTS.md` 第 4 节);旧「禁止自主实盘下单」条目已由受控许可模型取代。

## B. Assumptions

| ID | Fact level | Assumption | Validation or falsification |
|---|---|---|---|
| ASM-001 | EXTRACTED | Superseded 2026-07-17:仓库默认配置永远 DISABLED(失败关闭);真实下单仅经唯一执行网关在十一门禁+预签授权内自动发生。旧 research/paper-only 定位废止。 | `Alpha/AGENTS.md`; `Alpha/configs/trading_governor_policy.yaml` |
| ASM-002 | EXTRACTED | Current strategy and paper-trading evidence uses fixture prices. | `Alpha/backend/app/services/paper_trading_loop.py:138`; `Alpha/data/sample_prices.csv` |
| ASM-003 | EXTRACTED | Live broker adapter remains fail-closed. | `Alpha/backend/app/services/live_broker.py:27`; `Alpha/tests/test_live_broker_fail_closed.py:6` |
| ASM-004 | UNKNOWN | Production market data, broker paper integration, live execution policy, multi-year validation, slippage model, and cost-model calibration are not fully evidenced in this repository snapshot. | Open task `TASK-ALPHA-B-001` |

## C. Functions And Rules

Formula details live in `formula_registry.yaml`. The active rules include:

- `FORM-001`: deterministic momentum candidate ranking with lookbacks `(5, 10, 20)`, score `total_return + 0.5*oos_return + 0.01*hit_rate - abs(drawdown)`, and decision-priority sort.
- `FORM-002`: risk score starts at 100 and subtracts penalties for drawdown, low trade count, and high turnover.
- `FORM-003`: pre-trade gate rejects kill-switch, missing idempotency, invalid side, non-positive quantity/price/notional, missing max notional, and excessive notional.
- `FORM-004`: live policy rejects unless every required live safety gate passes; `FailClosedLiveBroker` still rejects rather than submitting.
- `FORM-005`: paper loop composes tournament, order intent, risk check, locked ticket queue enqueue, optional locked persisted paper fill, portfolio snapshot, and audit event. S3PBT02 records app-runtime lifecycle truth and S3PBT03 records shutdown fault-injection behavior under MOD-005 without changing trading formula values.
- `FORM-006`: paper broker updates cash and positions deterministically, rejects duplicate or invalid paper orders, and serializes persisted submit/save through locked atomic JSON writes.
- `FORM-007`: approval freshness maps expiry timestamps to fresh/expired/unknown actionability.
- `FORM-008`: strategy DSL validates payload ranges and MVP prohibitions.
- `FORM-009`: buy-and-hold fixture benchmark uses equal-weight returns and one-time cost/slippage.

## D. Parameters

The parameter registry separates default values, prior values, active values, weights, source/rationale, code references, config references, and tests. No live secret, credential, account identifier, or environment value is recorded.

Important safety parameters:

- `PARAM-023 live_trading.enabled`: active value `false`, from `Alpha/configs/trading_governor_policy.yaml:5`.
- `PARAM-030 fail_closed_live_broker`: adapter always returns rejected, from `Alpha/backend/app/services/live_broker.py:27`.
- `PARAM-031 DEFAULT_REFRESH_INTERVAL_SECONDS`: active value `300`, from `Alpha/backend/app/services/paper_trading_loop.py:19`.
- `PARAM-017 max_order_value_aud`: active value `100`, from `Alpha/configs/trading_governor_policy.yaml:33`.

## E. Methodology

Current methodology is deterministic and fixture-based:

- Strategy candidates are simple momentum candidates across fixture symbols and lookbacks.
- Risk scoring is threshold and penalty based.
- Paper trading is deterministic workflow execution over fixture data and a local paper broker; S3PBT01 makes the persisted queue and paper broker files atomic and serialized, S3PBT02 makes app stop/PID lifecycle truth explicit, and S3PBT03 adds disk-error, forced-termination, stale-PID, and write-after-stop fault-injection evidence.
- Live order submission is intentionally not implemented; fail-closed behavior is the active safety design.
- Current validation is unit/fixture testing, not production broker or real-market validation.

Alternative methods such as multi-year walk-forward, cost/slippage calibration, broker paper API integration, or live execution policy remain `UNKNOWN` and are linked to `TASK-ALPHA-B-001`.
S3PBT01 covers persisted queue/broker atomicity; S3PBT02 covers AutoPaperAgent stop truthfulness and dashboard PID cleanup. Disk-error, crash-recovery, stale-PID process-reuse, force-termination corruption, and full write-after-stop fault injection remain S3PBT03 evidence.

## F. Strategy And Safety Logic

Signal formation:

1. Read fixture close prices.
2. For each symbol/lookback, calculate momentum and walk-forward validation.
3. Score and rank candidates.
4. Select a tradable winner whose latest close does not exceed `max_order_value_aud`.

Gate logic:

1. `pre_trade_risk_check` rejects unsafe paper/live candidates.
2. `BrokerReadyOrderTicket` always requires human action.
3. `ApprovalQueue` separates fresh pending tickets from expired tickets.
4. `GovernorPolicy` and `FailClosedLiveBroker` reject live trading by default.

Failure behavior is fail-closed: missing policy raises, disabled live trading rejects, invalid order values reject, duplicate paper idempotency rejects, expired tickets lose owner-actionability.

## G. Verification

Focused verification commands:

- `python -m pytest tests/test_policy.py tests/test_live_broker_fail_closed.py tests/test_strategy_iteration.py tests/test_paper_trading_loop.py -q`
- `python scripts/validate_project_governance.py --project Alpha`

Known uncovered scenarios:

- Production market data.
- Broker paper API.
- ~~Real-money execution policy decision.~~(已裁定:2026-07-17 受控许可模型,见 `docs/decision_log.md`)
- Multi-year out-of-sample validation.
- Cost and slippage calibration beyond fixture benchmark defaults.

Release gate: `DECISION-ALPHA-EXECUTION-POLICY` 已于 2026-07-17 由 owner 显式裁定(受控许可模型,`docs/decision_log.md` 当日条目)。实盘就绪晋级改由 `configs/strategy_promotion.yaml` 四条判定 + 十一项门禁裁决;判定不达标不得宣布实盘就绪。
