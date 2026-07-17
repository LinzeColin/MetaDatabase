"""ALPHA-LIVE-030:S1 动量轮动纯函数测试(同输入同输出+白盒复算)。"""

from datetime import date, timedelta

import pytest

from backend.app.strategies.bars import Bar
from backend.app.strategies.s1_momentum import evaluate_s1, load_s1_config

AS_OF = date(2026, 7, 16)


def make_bars(daily_ret: float, n: int = 300, start: float = 100.0, spread: float = 0.005):
    bars, price, day = [], start, AS_OF - timedelta(days=n * 2)
    made = 0
    while made < n:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        price *= 1.0 + daily_ret
        bars.append(Bar(day=day, open=price, high=price * (1 + spread), low=price * (1 - spread), close=price))
        made += 1
    return bars


def make_alternating(up: float, down: float, n: int = 300, start: float = 100.0):
    bars, price, day, made = [], start, AS_OF - timedelta(days=n * 2), 0
    while made < n:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        price *= (1.0 + up) if made % 2 == 0 else (1.0 - down)
        bars.append(Bar(day=day, open=price, high=price * 1.001, low=price * 0.999, close=price))
        made += 1
    return bars


MINI_CFG = {
    "strategy_id": "S1_MOMENTUM_ROTATION",
    "universe": ["AAA", "BBB", "CCC", "CASH"],
    "cash_proxy": "CASH",
    "score": {"lookbacks_trading_days": [63, 126, 252], "weights": [0.4, 0.3, 0.3]},
    "absolute_momentum_filter": {"rule": "close > SMA200", "sma_period": 200},
    "selection": {"top_n": 2, "weight_each": 0.5},
    "volatility_targeting": {"target_annual_vol_pct": 12, "realized_vol_window_days": 20},
}


def test_top2_selection_and_scores_hand_checkable():
    data = {
        "AAA": make_bars(0.0015),   # 最强
        "BBB": make_bars(0.0008),   # 次强
        "CCC": make_bars(0.0002),   # 弱但仍在均线上
        "CASH": make_bars(0.0001),
    }
    r = evaluate_s1(data, MINI_CFG, AS_OF)
    assert r.selected == ("AAA", "BBB")
    assert set(r.target_weights) == {"AAA", "BBB"}
    # 白盒复算:恒定日收益 g 下 score = 0.4*(g^63 型)……只验单调性与公式一致性
    d = r.diagnostics["AAA"]
    expect = 0.4 * d["returns"]["r63"] + 0.3 * d["returns"]["r126"] + 0.3 * d["returns"]["r252"]
    assert d["score"] == pytest.approx(expect)
    assert r.scores["AAA"] > r.scores["BBB"] > r.scores["CCC"]


def test_all_below_sma200_goes_full_cash():
    data = {s: make_bars(-0.001) for s in MINI_CFG["universe"]}
    r = evaluate_s1(data, MINI_CFG, AS_OF)
    assert r.selected == ()
    assert r.target_weights == {"CASH": 1.0}  # 无人合格 -> 现金替身


def test_volatility_targeting_scales_down_when_turbulent():
    calm = {"AAA": make_bars(0.0015), "BBB": make_bars(0.0008),
            "CCC": make_bars(0.0002), "CASH": make_bars(0.0001)}
    r_calm = evaluate_s1(calm, MINI_CFG, AS_OF)
    assert r_calm.position_scalar == pytest.approx(1.0)  # 平静市不减仓

    wild = {"AAA": make_alternating(0.06, 0.04), "BBB": make_alternating(0.05, 0.035),
            "CCC": make_bars(0.0002), "CASH": make_bars(0.0001)}
    r_wild = evaluate_s1(wild, MINI_CFG, AS_OF)
    assert r_wild.position_scalar < 0.5   # 剧烈震荡显著减仓
    for w in r_wild.target_weights.values():
        assert w == pytest.approx(0.5 * r_wild.position_scalar)


def test_insufficient_data_symbol_not_eligible():
    data = {
        "AAA": make_bars(0.0015),
        "BBB": make_bars(0.0008)[-100:],   # 只有 100 根,不足 252+1
        "CCC": make_bars(0.0002),
        "CASH": make_bars(0.0001),
    }
    r = evaluate_s1(data, MINI_CFG, AS_OF)
    assert r.eligible["BBB"] is False
    assert "BBB" not in r.target_weights


def test_deterministic_same_input_same_output():
    data = {s: make_bars(0.001 + i * 0.0001) for i, s in enumerate(MINI_CFG["universe"])}
    r1 = evaluate_s1(data, MINI_CFG, AS_OF)
    r2 = evaluate_s1(data, MINI_CFG, AS_OF)
    assert r1.target_weights == r2.target_weights
    assert r1.scores == r2.scores
    assert r1.position_scalar == r2.position_scalar


def test_real_config_loads_and_runs():
    cfg = load_s1_config()
    data = {s: make_bars(0.0005) for s in cfg["universe"]}
    r = evaluate_s1(data, cfg, AS_OF)
    assert len(r.selected) == cfg["selection"]["top_n"]
    assert cfg["review_grid"]  # 网格必须存在(月度评审纪律)


# ---------- 黄金叠加生产配置(选乙) ----------

def test_gold_blend_config_loads_and_targets_include_overlay():
    from backend.app.strategies.s1_momentum import load_s1_config

    cfg = load_s1_config("configs/strategies/s1_gold_blend.yaml")
    assert cfg["strategy_id"] == "S1_GOLD_BLEND"
    data = {s: make_bars(0.0008 + i * 0.0002) for i, s in enumerate(cfg["universe"])}
    r = evaluate_s1(data, cfg, AS_OF)
    # 恒持黄金 2 成;冠军拿 8 成(波动调节已关)
    assert r.target_weights.get("GLD", 0) >= 0.2 - 1e-9
    total = sum(r.target_weights.values())
    assert abs(total - 1.0) < 1e-9
    assert len(r.selected) == 1                      # top1 集中
    assert r.position_scalar == 1.0                  # 波动率调节关闭


def test_gold_blend_high_proximity_blocks_fallen_symbol():
    from backend.app.strategies.s1_momentum import load_s1_config

    cfg = load_s1_config("configs/strategies/s1_gold_blend.yaml")
    data = {s: make_bars(0.0005) for s in cfg["universe"]}
    # 把 QQQ 改造成「仍在均线上但离 252 日高点 >10%」:先涨后落 12% 横盘
    bars = make_bars(0.0015, n=300)
    fallen = bars[:260]
    p = fallen[-1].close * 0.88
    day = fallen[-1].day
    from datetime import timedelta as _td
    out = list(fallen)
    while len(out) < 300:
        day += _td(days=1)
        if day.weekday() >= 5:
            continue
        out.append(Bar(day=day, open=p, high=p * 1.001, low=p * 0.999, close=p))
    data["QQQ"] = out
    r = evaluate_s1(data, cfg, AS_OF)
    assert r.eligible.get("QQQ") is False            # 新高线拦截
    assert r.diagnostics["QQQ"]["near_high"] is False


def test_gold_blend_all_ineligible_puts_risk_budget_to_cash():
    from backend.app.strategies.s1_momentum import load_s1_config

    cfg = load_s1_config("configs/strategies/s1_gold_blend.yaml")
    data = {s: make_bars(-0.001) for s in cfg["universe"]}   # 全体跌破均线
    r = evaluate_s1(data, cfg, AS_OF)
    assert r.target_weights.get("GLD", 0) >= 0.2 - 1e-9      # 黄金恒持不动摇
    assert r.target_weights.get(cfg["cash_proxy"], 0) >= 0.8 - 1e-9
