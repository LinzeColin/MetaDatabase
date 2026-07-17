"""ALPHA-LIVE-010:幂等重放——同一幂等键至多一条券商指令,重启后依旧。"""

import threading
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.app.domain.models import BrokerOrder, OrderIntent
from backend.app.domain.state_machine import OrderState
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import DuplicateIdempotencyKeyError, OrderStore


def make_store(tmp_path, name="idem.sqlite"):
    engine = init_engine(f"sqlite:///{tmp_path / name}")
    factory = create_session_factory(engine)
    return OrderStore(factory), factory


def intent_kwargs(key):
    return dict(
        idempotency_key=key,
        symbol="QQQ",
        side="BUY",
        quantity=3,
        currency="USD",
        strategy_source="S1_MOMENTUM_ROTATION",
        limit_price=Decimal("400.00"),
    )


def test_duplicate_key_rejected_only_one_broker_order(tmp_path):
    store, factory = make_store(tmp_path)
    store.create_intent(**intent_kwargs("dup-1"))
    with pytest.raises(DuplicateIdempotencyKeyError):
        store.create_intent(**intent_kwargs("dup-1"))
    with factory() as session:
        assert session.scalar(select(OrderIntent).where(OrderIntent.idempotency_key == "dup-1")) is not None
        assert len(session.scalars(select(BrokerOrder)).all()) == 1  # 只产生一条券商指令载体


def test_key_reserved_even_after_submit_failed_terminal(tmp_path):
    """SUBMIT_FAILED(终, 幂等键保留):重放不得复用键、不得二次提交。"""
    store, _ = make_store(tmp_path)
    order_id = store.create_intent(**intent_kwargs("failed-key"))
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    store.apply_transition(order_id, OrderState.SUBMIT_FAILED, event_type="GATEWAY_SUBMIT_ERROR")
    assert store.get_state(order_id) is OrderState.SUBMIT_FAILED  # 终态

    assert store.idempotency_key_available("failed-key") is False
    with pytest.raises(DuplicateIdempotencyKeyError):
        store.create_intent(**intent_kwargs("failed-key"))


def test_key_never_reused_even_after_clean_fill(tmp_path):
    """全局永不复用(严于规范下限):FILLED 后同键重放同样拒绝。"""
    store, _ = make_store(tmp_path)
    order_id = store.create_intent(**intent_kwargs("filled-key"))
    store.record_risk_decision(order_id, allowed=True)
    for st, et in [
        (OrderState.SUBMITTING, "GATEWAY_SUBMIT"),
        (OrderState.SUBMITTED, "BROKER_ACK"),
        (OrderState.ACCEPTED, "BROKER_ACCEPT"),
    ]:
        store.apply_transition(order_id, st, event_type=et)
    store.apply_fill_event(order_id, quantity=3, price=Decimal("400.10"))
    with pytest.raises(DuplicateIdempotencyKeyError):
        store.create_intent(**intent_kwargs("filled-key"))


def test_concurrent_same_key_race_yields_single_row(tmp_path):
    store, factory = make_store(tmp_path)
    results: list[str] = []
    errors: list[Exception] = []

    def worker():
        try:
            results.append(store.create_intent(**intent_kwargs("race-key")))
        except DuplicateIdempotencyKeyError as exc:
            errors.append(exc)
        except Exception as exc:  # SQLite 写锁竞争等,如实收集
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with factory() as session:
        rows = session.scalars(select(OrderIntent).where(OrderIntent.idempotency_key == "race-key")).all()
    assert len(rows) == 1  # 竞态下仍只有一条
    assert len(results) <= 1
    assert len(results) + len(errors) == 6


def test_replay_blocked_across_restart(tmp_path):
    """重启恢复:同一 SQLite 文件重开,键占用与状态原样恢复。"""
    db = tmp_path / "replay.sqlite"
    engine = init_engine(f"sqlite:///{db}")
    store = OrderStore(create_session_factory(engine))
    order_id = store.create_intent(**intent_kwargs("restart-key"))
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    engine.dispose()

    engine2 = init_engine(f"sqlite:///{db}")
    store2 = OrderStore(create_session_factory(engine2))
    assert store2.get_state(order_id) is OrderState.SUBMITTING  # 崩溃点状态如实恢复
    with pytest.raises(DuplicateIdempotencyKeyError):
        store2.create_intent(**intent_kwargs("restart-key"))
    assert store2.idempotency_key_available("restart-key") is False
