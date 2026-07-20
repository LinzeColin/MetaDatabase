"""070 取数器:对种子库聚合出正确漏斗/收益/可靠性,并能产出四件套。"""

from datetime import datetime, timezone
from decimal import Decimal

from backend.app.domain.state_machine import OrderState
from backend.app.reporting.three_day_report import generate
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore

import scripts.export_paper_run as ex


def seed(tmp_path):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path/'run.sqlite'}"))
    store = OrderStore(factory)
    oid = store.create_intent(idempotency_key="S1-2026-07-21-SPY-BUY-3", symbol="SPY",
                              side="BUY", quantity=3, currency="USD",
                              strategy_source="S1_GOLD_BLEND", order_type="LIMIT",
                              limit_price=Decimal("500.50"))
    store.record_risk_decision(oid, allowed=True, triggered_rules=[], exposure_snapshot={})
    store.apply_transition(oid, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    store.apply_transition(oid, OrderState.SUBMITTED, event_type="BROKER_SYNC_ACK",
                           broker_order_id="SIM1")
    store.apply_fill_event(oid, quantity=3, price=Decimal("500.10"),
                           broker_execution_id="SIMFILL-1")
    return factory


def test_collect_aggregates_funnel_and_pnl(tmp_path):
    factory = seed(tmp_path)
    today = datetime.now(timezone.utc).date().isoformat()
    inputs, pnl = ex.collect(factory, [today], mark_prices={"SPY": 501.0})
    assert inputs.signals == 1 and inputs.risk_passed == 1
    assert inputs.submitted == 1 and inputs.filled == 1
    assert pnl["open_positions"] == {"SPY": 3}
    # 现金流 -1500.30,持仓估值 1503.00 → 净 +2.70(费 0)
    assert abs(pnl["net_pnl_usd"] - 2.70) < 0.01
    assert inputs.unknown_orders == 0 and inputs.illegal_transitions == 0
    assert inputs.raw_events and inputs.raw_events[0]["type"]


def test_collect_unpriced_positions_declared(tmp_path):
    factory = seed(tmp_path)
    today = datetime.now(timezone.utc).date().isoformat()
    _, pnl = ex.collect(factory, [today], mark_prices={})
    assert pnl["unpriced_symbols"] == ["SPY"]    # 缺价如实声明,不编造估值
    assert pnl["mark_value_usd"] == 0.0


def test_end_to_end_generates_four_artifacts(tmp_path):
    factory = seed(tmp_path)
    today = datetime.now(timezone.utc).date().isoformat()
    inputs, pnl = ex.collect(factory, [today], mark_prices={"SPY": 501.0})
    inputs.uptime_pct = 99.9
    inputs.net_pnl_aud = round(pnl["net_pnl_usd"] / 0.65, 2)
    report = generate(inputs, capital_aud=3000.0, out_dir=tmp_path / "rep",
                      generated_at="2026-07-22T21:00:00Z")
    for name in ("report.md", "report.json", "evidence_hashes.txt", "events.jsonl"):
        assert (tmp_path / "rep" / name).exists()
    assert report["promotion"]["days_qualified"] == 1
    assert report["promotion"]["auto_promote"] is False   # 样本不足绝不晋级
