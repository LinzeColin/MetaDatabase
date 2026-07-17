"""ALPHA-LIVE-035:影子记录器——一一对应、保守假想成交、差异登记。"""

from decimal import Decimal

import pytest

from backend.app.shadow.recorder import ShadowRecorder
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore


def setup(tmp_path):
    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'shadow.sqlite'}"))
    return ShadowRecorder(f), OrderStore(f), f


def make_intent(store, key="s1"):
    order_id = store.create_intent(
        idempotency_key=key, symbol="SPY", side="BUY", quantity=3,
        currency="USD", strategy_source="S1_MOMENTUM_ROTATION", limit_price=Decimal("100"),
    )
    with store._sessions() as session:  # noqa: SLF001
        from backend.app.domain.models import BrokerOrder

        return session.get(BrokerOrder, order_id).intent_id


def test_one_to_one_with_paper_decisions(tmp_path):
    rec, store, _ = setup(tmp_path)
    intents = [make_intent(store, f"k{i}") for i in range(3)]
    for intent_id in intents:
        rec.record_decision(intent_id=intent_id, hypothetical_limit_price=Decimal("99.90"),
                            estimated_fees=Decimal("0.99"))
    assert rec.count() == 3                                   # 每个决策恰一条影子
    with pytest.raises(ValueError):
        rec.record_decision(intent_id=intents[0], hypothetical_limit_price=Decimal("99.90"),
                            estimated_fees=Decimal("0.99"))   # 重复 = 违规


def test_conservative_hypothetical_fill(tmp_path):
    rec, store, _ = setup(tmp_path)
    intent_id = make_intent(store)
    rec.record_decision(intent_id=intent_id, hypothetical_limit_price=Decimal("99.90"),
                        estimated_fees=Decimal("0.99"))
    # 日内最低 99.95 > 限价 99.90:保守规则 = 未成交
    assert rec.settle_hypothetical(intent_id=intent_id, day_low=Decimal("99.95"),
                                   day_high=Decimal("101.00")) is None
    # 日内最低 99.50 <= 限价:成交价 = 限价(不占便宜)
    assert rec.settle_hypothetical(intent_id=intent_id, day_low=Decimal("99.50"),
                                   day_high=Decimal("101.00")) == Decimal("99.90")


def test_paper_divergence_recorded(tmp_path):
    rec, store, _ = setup(tmp_path)
    intent_id = make_intent(store)
    rec.record_decision(intent_id=intent_id, hypothetical_limit_price=Decimal("99.90"),
                        estimated_fees=Decimal("0.99"))
    rec.settle_hypothetical(intent_id=intent_id, day_low=Decimal("99.00"), day_high=Decimal("101"))
    div = rec.record_paper_divergence(intent_id=intent_id,
                                      paper_fill_price=Decimal("99.95"), paper_filled_quantity=3)
    assert div["both_filled"] is True
    assert div["price_gap"] == "0.05"                         # Paper 比影子贵 5 分
    snap = rec.by_intent(intent_id)
    assert snap["divergence"]["paper_divergence"]["price_gap"] == "0.05"


def test_shadow_never_touches_state_machine(tmp_path):
    from backend.app.domain.state_machine import OrderState

    rec, store, _ = setup(tmp_path)
    intent_id = make_intent(store, "sm")
    rec.record_decision(intent_id=intent_id, hypothetical_limit_price=Decimal("99.90"),
                        estimated_fees=Decimal("0.99"))
    order_id = store.find_order_by_idempotency_key("sm")
    assert store.get_state(order_id) is OrderState.INTENT_CREATED  # 状态纹丝不动
