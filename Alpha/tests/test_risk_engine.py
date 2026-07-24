"""ALPHA-LIVE-030:硬风控边界值 + 断路器 + 新鲜度守卫 + 审计落库。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.marketdata.guard import FreshnessGuard
from backend.app.risk.engine import (
    BreakerLevel,
    BreakerThresholds,
    RiskContext,
    evaluate,
    evaluate_breakers,
    order_notional_aud,
)
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore

UTC = timezone.utc
NOW = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


def ctx(**over):
    kw = dict(
        side="BUY",
        symbol="SPY",
        market="US_ETF",
        quantity=1,
        price_usd=Decimal("100"),
        fx_usd_aud=Decimal("1"),
        now=NOW,
        quote_age_seconds=1.0,
        jurisdiction_verdict="ALLOW",
    )
    kw.update(over)
    return RiskContext(**kw)


# ---- 总敞口边界:等于线放行,超一分拒 ----

@pytest.mark.parametrize(
    "notional,allowed",
    [(Decimal("2999"), True), (Decimal("3000"), True), (Decimal("3001"), False)],
)
def test_gross_exposure_boundary(notional, allowed):
    c = ctx(quantity=1, price_usd=notional, fat_finger_ratio=Decimal("2"))  # 隔离胖手指规则
    v = evaluate(c)
    assert v.allowed is allowed
    if not allowed:
        assert "RULE_GROSS_EXPOSURE_CAP" in v.triggered_rules


def test_gross_exposure_counts_existing_and_pending():
    c = ctx(
        quantity=1, price_usd=Decimal("500"), fat_finger_ratio=Decimal("2"),
        current_gross_exposure_aud=Decimal("2000"), pending_buy_reserved_aud=Decimal("501"),
    )
    v = evaluate(c)  # 2000+501+500 = 3001 > 3000
    assert "RULE_GROSS_EXPOSURE_CAP" in v.triggered_rules
    assert v.snapshot["exposure_after_aud"] == "3001.00"


# ---- 胖手指边界:2700 放行,2700.01 拒;买卖都防(owner 2026-07-24 放宽至 90%) ----

@pytest.mark.parametrize(
    "notional,allowed",
    [(Decimal("2699"), True), (Decimal("2700"), True), (Decimal("2700.01"), False)],
)
def test_fat_finger_boundary(notional, allowed):
    # 缺省授权 3000:保险丝 = 3000×0.90 = 2700;这些名义额都不触总敞口线
    c = ctx(quantity=1, price_usd=notional)
    v = evaluate(c)
    assert v.allowed is allowed, v.triggered_rules
    if not allowed:
        assert v.triggered_rules == ("RULE_FAT_FINGER_SINGLE_ORDER",)
    c_sell = ctx(side="SELL", quantity=1, price_usd=notional)
    assert ("RULE_FAT_FINGER_SINGLE_ORDER" in evaluate(c_sell).triggered_rules) is (not allowed)


# ---- 频控:滚动 60 分钟第 5 笔放行、第 6 笔拒;老订单滑出窗口 ----

def test_rate_limit_rolling_window():
    four = tuple(NOW - timedelta(minutes=m) for m in (5, 15, 30, 55))
    assert evaluate(ctx(recent_order_times=four)).allowed is True         # 本单是第 5 笔
    five = four + (NOW - timedelta(minutes=59),)
    v = evaluate(ctx(recent_order_times=five))                            # 本单是第 6 笔
    assert "RULE_BUSINESS_RATE_LIMIT" in v.triggered_rules
    slid = four + (NOW - timedelta(minutes=61),)                          # 第 5 笔已出窗
    assert evaluate(ctx(recent_order_times=slid)).allowed is True


# ---- 市场白名单与辖区:只锁 BUY,SELL(减仓)永远可行 ----

def test_market_whitelist_blocks_buy_not_sell():
    assert "RULE_MARKET_WHITELIST" in evaluate(ctx(market="HK_STOCK")).triggered_rules
    assert "RULE_MARKET_WHITELIST" in evaluate(ctx(market="CN_A_SHARE")).triggered_rules
    assert evaluate(ctx(side="SELL", market="HK_STOCK")).allowed is True


def test_jurisdiction_default_deny_blocks_buy():
    v = evaluate(RiskContext(
        side="BUY", symbol="SPY", market="US_ETF", quantity=1,
        price_usd=Decimal("100"), fx_usd_aud=Decimal("1"), now=NOW, quote_age_seconds=1.0,
    ))  # 未显式给 ALLOW -> 缺省 DENY
    assert "RULE_JURISDICTION_DENY" in v.triggered_rules
    assert evaluate(ctx(side="SELL", jurisdiction_verdict="DENY")).allowed is True


# ---- 新鲜度:5.0s 放行、5.01s 拒;缺行情拒;未来时间戳拒 ----

@pytest.mark.parametrize(
    "age,rule",
    [(5.0, None), (5.01, "RULE_MARKET_DATA_STALE"), (None, "RULE_MARKET_DATA_MISSING"),
     (-0.5, "RULE_MARKET_DATA_STALE")],
)
def test_freshness_rules(age, rule):
    v = evaluate(ctx(quote_age_seconds=age))
    if rule is None:
        assert v.allowed is True
    else:
        assert rule in v.triggered_rules


def test_freshness_guard_object():
    g = FreshnessGuard(5.0)
    fresh = g.check(symbol="SPY", exchange_ts=NOW - timedelta(seconds=3), now=NOW)
    stale = g.check(symbol="SPY", exchange_ts=NOW - timedelta(seconds=6), now=NOW)
    future = g.check(symbol="SPY", exchange_ts=NOW + timedelta(seconds=2), now=NOW)
    assert fresh.fresh and not stale.fresh and not future.fresh


# ---- 杀开关 / 对账未清:全拒 ----

def test_kill_switch_and_open_reconciliation_block_everything():
    for side in ("BUY", "SELL"):
        assert "RULE_KILL_SWITCH_ACTIVE" in evaluate(ctx(side=side, kill_switch_active=True)).triggered_rules
        assert "RULE_RECONCILIATION_OPEN" in evaluate(ctx(side=side, reconciliation_open=True)).triggered_rules


# ---- 三层断路器 ----

def test_breaker_levels_exact_thresholds():
    kw = dict(three_day_cum_pnl_pct=0.0, month_drawdown_pct=0.0, last_flatten_at=None, now=NOW)
    assert evaluate_breakers(daily_pnl_pct=-1.99, **kw) is BreakerLevel.NONE
    assert evaluate_breakers(daily_pnl_pct=-2.0, **kw) is BreakerLevel.STOP_NEW
    assert evaluate_breakers(
        daily_pnl_pct=0.0, three_day_cum_pnl_pct=-4.0, month_drawdown_pct=0.0,
        last_flatten_at=None, now=NOW,
    ) is BreakerLevel.FLATTEN_COOLDOWN
    assert evaluate_breakers(
        daily_pnl_pct=0.0, three_day_cum_pnl_pct=0.0, month_drawdown_pct=8.0,
        last_flatten_at=None, now=NOW,
    ) is BreakerLevel.DEMOTED_PAPER


def test_breaker_cooldown_48h_window():
    kw = dict(daily_pnl_pct=0.0, three_day_cum_pnl_pct=0.0, month_drawdown_pct=0.0, now=NOW)
    assert evaluate_breakers(last_flatten_at=NOW - timedelta(hours=47), **kw) is BreakerLevel.FLATTEN_COOLDOWN
    assert evaluate_breakers(last_flatten_at=NOW - timedelta(hours=49), **kw) is BreakerLevel.NONE
    assert BreakerThresholds().cooldown_hours == 48


def test_breaker_blocks_buy_allows_sell_flatten():
    v_buy = evaluate(ctx(breaker_level=BreakerLevel.STOP_NEW))
    assert "RULE_BREAKER_STOP_NEW" in v_buy.triggered_rules
    assert evaluate(ctx(side="SELL", breaker_level=BreakerLevel.FLATTEN_COOLDOWN)).allowed is True
    for side in ("BUY", "SELL"):
        assert "RULE_BREAKER_DEMOTED_PAPER" in evaluate(
            ctx(side=side, breaker_level=BreakerLevel.DEMOTED_PAPER)
        ).triggered_rules


# ---- 不短路 + 确定性 + 审计落库 ----

def test_all_violations_reported_no_short_circuit():
    v = evaluate(ctx(
        market="CN_A_SHARE", jurisdiction_verdict="DENY", kill_switch_active=True,
        reconciliation_open=True, quote_age_seconds=None,
        quantity=1, price_usd=Decimal("2000"), max_gross_exposure_aud=Decimal("1000"),
        breaker_level=BreakerLevel.STOP_NEW,
        recent_order_times=tuple(NOW - timedelta(minutes=m) for m in (1, 2, 3, 4, 5)),
    ))
    assert set(v.triggered_rules) >= {
        "RULE_KILL_SWITCH_ACTIVE", "RULE_RECONCILIATION_OPEN", "RULE_MARKET_DATA_MISSING",
        "RULE_BUSINESS_RATE_LIMIT", "RULE_FAT_FINGER_SINGLE_ORDER", "RULE_MARKET_WHITELIST",
        "RULE_JURISDICTION_DENY", "RULE_GROSS_EXPOSURE_CAP", "RULE_BREAKER_STOP_NEW",
    }


def test_deterministic_same_context_same_verdict():
    c = ctx(quantity=3, price_usd=Decimal("123.45"))
    assert evaluate(c) == evaluate(c)


def test_notional_rounds_up_to_cent():
    c = ctx(quantity=3, price_usd=Decimal("33.3333"), fx_usd_aud=Decimal("1.5"))
    assert order_notional_aud(c) == Decimal("150.00")  # 149.99985 -> 150.00 向上


def test_rejection_audit_persisted_via_store(tmp_path):
    """风控拒绝路径全部有审计记录:triggered_rules 原样落库。"""
    engine = init_engine(f"sqlite:///{tmp_path / 'audit.sqlite'}")
    store = OrderStore(create_session_factory(engine))
    order_id = store.create_intent(
        idempotency_key="risk-audit-1", symbol="SPY", side="BUY", quantity=31,
        currency="USD", strategy_source="S1_MOMENTUM_ROTATION", limit_price=Decimal("100"),
    )
    v = evaluate(ctx(quantity=31, price_usd=Decimal("100")))  # 3100 > 3000(胖手指也触发)
    assert v.allowed is False
    store.record_risk_decision(
        order_id, allowed=False, triggered_rules=list(v.triggered_rules), exposure_snapshot=v.snapshot
    )
    from backend.app.domain.state_machine import OrderState

    assert store.get_state(order_id) is OrderState.RISK_REJECTED
    events = store.list_events(order_id)
    assert events[-1]["to_state"] == "RISK_REJECTED"
