"""ALPHA-LIVE-030:组合引擎——净冲突、现金缓冲、阈值、整股、保守换汇。"""

from decimal import Decimal

from backend.app.portfolio.engine import synthesize

ALLOC = {"S1_MOMENTUM_ROTATION": 0.80, "S2_OVERSOLD_REBOUND": 0.20}


def base_kwargs(**over):
    kw = dict(
        s1_weights={"SPY": 0.5, "QQQ": 0.5},
        s2_symbols=[],
        allocation=ALLOC,
        s2_max_open_trades=2,
        equity_aud=Decimal("3000"),
        prices_usd={"SPY": Decimal("100"), "QQQ": Decimal("100")},
        fx_usd_aud=Decimal("1"),
        current_quantities={},
        rebalance_threshold_pct=5.0,
    )
    kw.update(over)
    return kw


def test_80_20_allocation_and_net_conflict_same_symbol():
    """SPY 同时被 S1(1200)与 S2(300)持有 -> 净目标 1500 = 15 股。"""
    r = synthesize(**base_kwargs(s2_symbols=["SPY"]))
    assert r.target_quantities == {"SPY": 15, "QQQ": 12}
    assert sorted((d.symbol, d.side, d.quantity) for d in r.drafts) == [
        ("QQQ", "BUY", 12),
        ("SPY", "BUY", 15),
    ]
    spy = r.diagnostics["SPY"]
    assert spy["sources"] == ["S1_MOMENTUM_ROTATION", "S2_OVERSOLD_REBOUND"]


def test_cash_buffer_never_negative_scales_down():
    """人为放大权重使目标总额 3600 > 权益 3000 -> 等比缩水,总市值 ≤ 权益。"""
    r = synthesize(**base_kwargs(s1_weights={"SPY": 0.75, "QQQ": 0.75}))
    assert r.scaled_down is True
    total_aud = sum(qty * 100 for qty in r.target_quantities.values())
    assert total_aud <= 3000


def test_rebalance_threshold_skips_small_diff():
    """现仓 14 股,目标 15 股:差 100 AUD < 150(5%×3000) -> 不动。"""
    r = synthesize(**base_kwargs(s2_symbols=["SPY"], current_quantities={"SPY": 14, "QQQ": 12}))
    assert r.drafts == ()
    assert "skipped_below_threshold_aud" in r.diagnostics["SPY"]


def test_sell_draft_when_target_below_current():
    r = synthesize(**base_kwargs(current_quantities={"SPY": 30, "QQQ": 12}))
    assert ("SPY", "SELL", 18) in [(d.symbol, d.side, d.quantity) for d in r.drafts]


def test_whole_share_flooring_never_rounds_up():
    """目标 1199.99 AUD / 单价 100 -> 11 股(向下),绝不凑 12。"""
    r = synthesize(**base_kwargs(
        s1_weights={"SPY": 0.5},
        equity_aud=Decimal("2999.99"),
        prices_usd={"SPY": Decimal("100")},
    ))
    assert r.target_quantities["SPY"] == 11


def test_fx_conservative_rounds_exposure_up():
    """100 USD × 1.53333 = 153.333 -> 价格按分向上取整 153.34。"""
    r = synthesize(**base_kwargs(
        s1_weights={"SPY": 1.0},
        fx_usd_aud=Decimal("1.53333"),
        prices_usd={"SPY": Decimal("100")},
    ))
    assert r.diagnostics["SPY"]["price_aud"] == "153.34"


def test_full_cash_target_sells_everything_material():
    """S1 全退现金(权重空)+ 无 S2:现仓全列卖出草案(超过阈值部分)。"""
    r = synthesize(**base_kwargs(s1_weights={}, current_quantities={"SPY": 10}))
    assert [(d.symbol, d.side, d.quantity) for d in r.drafts] == [("SPY", "SELL", 10)]
