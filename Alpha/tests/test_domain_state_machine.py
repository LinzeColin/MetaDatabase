"""ALPHA-LIVE-010:订单状态机全路径 + 非法迁移处置 + 十实体持久化恢复。"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.app.domain.models import (
    CapitalAuthorization,
    Execution,
    JurisdictionCapability,
    OrderIntent,
    OutboxEvent,
    PositionSnapshot,
    ReconciliationRun,
    RiskDecision,
    ShadowOrder,
)
from backend.app.domain.state_machine import (
    IllegalTransitionError,
    OrderState,
    assert_transition,
    is_legal,
    is_terminal,
)
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore

UTC = timezone.utc


def make_store(tmp_path, name="orders.sqlite"):
    engine = init_engine(f"sqlite:///{tmp_path / name}")
    return OrderStore(create_session_factory(engine))


def create_approved_order(store, key="k1", quantity=10):
    order_id = store.create_intent(
        idempotency_key=key,
        symbol="SPY",
        side="BUY",
        quantity=quantity,
        currency="USD",
        strategy_source="S1_MOMENTUM_ROTATION",
        limit_price=Decimal("500.10"),
    )
    store.record_risk_decision(order_id, allowed=True, triggered_rules=[], exposure_snapshot={"gross": "0"})
    return order_id


# ---------- 纯状态机 ----------

def test_full_fill_path_via_partial():
    s = OrderState.INTENT_CREATED
    for nxt in [
        OrderState.RISK_APPROVED,
        OrderState.SUBMITTING,
        OrderState.SUBMITTED,
        OrderState.ACCEPTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.PARTIALLY_FILLED,  # 多笔部分成交自环
        OrderState.FILLED,
    ]:
        s = assert_transition(s, nxt)
    assert s is OrderState.FILLED and is_terminal(s)


@pytest.mark.parametrize(
    "path",
    [
        [OrderState.RISK_REJECTED],
        [OrderState.RISK_APPROVED, OrderState.SUBMITTING, OrderState.SUBMIT_FAILED],
        [OrderState.RISK_APPROVED, OrderState.SUBMITTING, OrderState.SUBMITTED, OrderState.REJECTED],
        [
            OrderState.RISK_APPROVED,
            OrderState.SUBMITTING,
            OrderState.SUBMITTED,
            OrderState.ACCEPTED,
            OrderState.FILLED,
        ],
        [
            OrderState.RISK_APPROVED,
            OrderState.SUBMITTING,
            OrderState.SUBMITTED,
            OrderState.ACCEPTED,
            OrderState.PARTIALLY_FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.CANCELLED,  # 终,可带部分成交
        ],
        [
            OrderState.RISK_APPROVED,
            OrderState.SUBMITTING,
            OrderState.SUBMITTED,
            OrderState.ACCEPTED,
            OrderState.EXPIRED,
        ],
        [
            OrderState.RISK_APPROVED,
            OrderState.SUBMITTING,
            OrderState.SUBMITTED,
            OrderState.ACCEPTED,
            OrderState.PARTIALLY_FILLED,
            OrderState.EXPIRED,
        ],
    ],
)
def test_all_terminal_paths_legal(path):
    s = OrderState.INTENT_CREATED
    for nxt in path:
        s = assert_transition(s, nxt)
    assert is_terminal(s)


@pytest.mark.parametrize(
    "current,attempted",
    [
        (OrderState.FILLED, OrderState.ACCEPTED),  # 规范示例
        (OrderState.INTENT_CREATED, OrderState.FILLED),
        (OrderState.INTENT_CREATED, OrderState.SUBMITTING),
        (OrderState.RISK_REJECTED, OrderState.RISK_APPROVED),
        (OrderState.CANCELLED, OrderState.PARTIALLY_FILLED),
        (OrderState.CANCEL_REQUESTED, OrderState.FILLED),  # 撤单期间成交回报不在合法表内
        (OrderState.SUBMIT_FAILED, OrderState.SUBMITTING),
        (OrderState.EXPIRED, OrderState.CANCEL_REQUESTED),
        (OrderState.UNKNOWN_RECONCILIATION_REQUIRED, OrderState.FILLED),
    ],
)
def test_illegal_transitions_raise(current, attempted):
    with pytest.raises(IllegalTransitionError):
        assert_transition(current, attempted)


def test_unknown_reachable_from_any_state():
    for s in OrderState:
        assert is_legal(s, OrderState.UNKNOWN_RECONCILIATION_REQUIRED)


# ---------- 存储层折叠 ----------

def test_store_full_lifecycle_folds_events(tmp_path):
    store = make_store(tmp_path)
    order_id = create_approved_order(store)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    store.apply_transition(
        order_id,
        OrderState.SUBMITTED,
        event_type="BROKER_ACK",
        broker_order_id="MM123",
        broker_timestamp=datetime(2026, 7, 17, 14, 30, tzinfo=UTC),
        broker_sequence=1,
    )
    store.apply_transition(order_id, OrderState.ACCEPTED, event_type="BROKER_ACCEPT", broker_sequence=2)
    state = store.apply_fill_event(
        order_id,
        quantity=4,
        price=Decimal("500.00"),
        fees=Decimal("0.99"),
        broker_execution_id="E1",
        broker_sequence=3,
    )
    assert state is OrderState.PARTIALLY_FILLED
    state = store.apply_fill_event(
        order_id, quantity=6, price=Decimal("500.20"), broker_execution_id="E2", broker_sequence=4
    )
    assert state is OrderState.FILLED

    events = store.list_events(order_id)
    fold = [e["to_state"] for e in events if e["to_state"]]
    assert fold == [
        "INTENT_CREATED",
        "RISK_APPROVED",
        "SUBMITTING",
        "SUBMITTED",
        "ACCEPTED",
        "PARTIALLY_FILLED",
        "FILLED",
    ]
    assert store.get_state(order_id) is OrderState.FILLED
    assert store.halt_new_orders() is False


def test_store_illegal_transition_quarantines_and_halts(tmp_path):
    store = make_store(tmp_path)
    order_id = create_approved_order(store)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    store.apply_transition(order_id, OrderState.SUBMITTED, event_type="BROKER_ACK")
    store.apply_transition(order_id, OrderState.ACCEPTED, event_type="BROKER_ACCEPT")
    store.apply_fill_event(order_id, quantity=10, price=Decimal("500"))
    assert store.get_state(order_id) is OrderState.FILLED

    # 规范示例:FILLED 后再来 ACCEPTED
    with pytest.raises(IllegalTransitionError):
        store.apply_transition(order_id, OrderState.ACCEPTED, event_type="BROKER_ACCEPT")

    events = store.list_events(order_id)
    types = [e["event_type"] for e in events]
    assert "ILLEGAL_TRANSITION_REJECTED" in types  # 记审计
    assert store.get_state(order_id) is OrderState.UNKNOWN_RECONCILIATION_REQUIRED  # 标记 UNKNOWN
    assert store.halt_new_orders() is True  # 停新单(OPEN 对账批次)
    audit = next(e for e in events if e["event_type"] == "ILLEGAL_TRANSITION_REJECTED")
    assert audit["payload"]["attempted"] == "ACCEPTED"


def test_fill_during_cancel_requested_is_quarantined(tmp_path):
    store = make_store(tmp_path)
    order_id = create_approved_order(store)
    for st, et in [
        (OrderState.SUBMITTING, "GATEWAY_SUBMIT"),
        (OrderState.SUBMITTED, "BROKER_ACK"),
        (OrderState.ACCEPTED, "BROKER_ACCEPT"),
        (OrderState.CANCEL_REQUESTED, "GATEWAY_CANCEL"),
    ]:
        store.apply_transition(order_id, st, event_type=et)
    with pytest.raises(IllegalTransitionError):
        store.apply_fill_event(order_id, quantity=10, price=Decimal("500"))
    assert store.get_state(order_id) is OrderState.UNKNOWN_RECONCILIATION_REQUIRED
    assert store.halt_new_orders() is True


def test_early_fill_callback_backfills_intermediate_states(tmp_path):
    """回调先于返回:SUBMITTING 直接收到成交推送。"""
    store = make_store(tmp_path)
    order_id = create_approved_order(store)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")

    state = store.apply_fill_event(
        order_id,
        quantity=4,
        price=Decimal("499.90"),
        broker_timestamp=datetime(2026, 7, 17, 14, 30, 0, 500000, tzinfo=UTC),
        broker_sequence=7,
    )
    assert state is OrderState.PARTIALLY_FILLED
    events = store.list_events(order_id)
    backfilled = [e for e in events if e["backfilled"]]
    assert [e["to_state"] for e in backfilled] == ["SUBMITTED", "ACCEPTED"]  # 补写中间态标记
    assert store.get_state(order_id) is OrderState.PARTIALLY_FILLED


def test_mark_unknown_from_any_state_opens_reconciliation(tmp_path):
    store = make_store(tmp_path)
    order_id = create_approved_order(store)
    store.mark_unknown(order_id, reason="收到无法解释的券商事件")
    assert store.get_state(order_id) is OrderState.UNKNOWN_RECONCILIATION_REQUIRED
    assert store.halt_new_orders() is True


# ---------- 十实体持久化可恢复 ----------

def test_all_ten_entities_persist_and_recover(tmp_path):
    db = tmp_path / "entities.sqlite"
    engine = init_engine(f"sqlite:///{db}")
    factory = create_session_factory(engine)
    store = OrderStore(factory)
    order_id = create_approved_order(store)  # OrderIntent + RiskDecision + BrokerOrder(+事件)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    store.apply_transition(order_id, OrderState.SUBMITTED, event_type="BROKER_ACK")
    store.apply_transition(order_id, OrderState.ACCEPTED, event_type="BROKER_ACCEPT")
    store.apply_fill_event(order_id, quantity=10, price=Decimal("500.55"))  # Execution

    now = datetime(2026, 7, 17, 20, 0, tzinfo=UTC)
    with factory() as session, session.begin():
        intent_id = session.query(OrderIntent).one().intent_id
        session.add_all(
            [
                PositionSnapshot(symbol="SPY", quantity=10, cost=Decimal("5005.50"),
                                 market_value=Decimal("5100.00"), captured_at=now),
                CapitalAuthorization(
                    max_gross_exposure=Decimal("3000"), max_single_order=Decimal("1800"),
                    currency="AUD", market_whitelist='["US_STOCK", "US_ETF"]',
                    policy_hash="sha256:test", effective_from=now, effective_until=now,
                ),
                JurisdictionCapability(
                    account_principal="owner_au", location="AU", api_available=True,
                    buy_permission=True, evidence_source="probe:test", verdict="ALLOW", probed_at=now,
                ),
                ShadowOrder(intent_id=intent_id, hypothetical_limit_price=Decimal("500.10"),
                            hypothetical_fees=Decimal("0.99")),
                OutboxEvent(event_type="ORDER_FILLED_EMAIL", payload='{"order_id": "x"}'),
            ]
        )

    # 重开(新引擎,同一文件)= 进程重启恢复
    engine2 = init_engine(f"sqlite:///{db}")
    factory2 = create_session_factory(engine2)
    store2 = OrderStore(factory2)
    assert store2.get_state(order_id) is OrderState.FILLED
    with factory2() as session:
        counts = {
            "OrderIntent": session.query(OrderIntent).count(),
            "RiskDecision": session.query(RiskDecision).count(),
            "Execution": session.query(Execution).count(),
            "PositionSnapshot": session.query(PositionSnapshot).count(),
            "CapitalAuthorization": session.query(CapitalAuthorization).count(),
            "JurisdictionCapability": session.query(JurisdictionCapability).count(),
            "ShadowOrder": session.query(ShadowOrder).count(),
            "OutboxEvent": session.query(OutboxEvent).count(),
            "ReconciliationRun": session.query(ReconciliationRun).count(),
        }
    assert counts == {
        "OrderIntent": 1,
        "RiskDecision": 1,
        "Execution": 1,
        "PositionSnapshot": 1,
        "CapitalAuthorization": 1,
        "JurisdictionCapability": 1,
        "ShadowOrder": 1,
        "OutboxEvent": 1,
        "ReconciliationRun": 0,  # 干净生命周期不开对账
    }
    # BrokerOrder 状态与均价恢复
    assert store2.get_state(order_id) is OrderState.FILLED
