"""换帅(2026-07-24 owner 书面选定):五腿双动量精调生产配置的装载与行为。"""

from datetime import date, timedelta

from backend.app.strategies.s1_momentum import evaluate_s1, load_s1_config
from backend.app.strategies.bars import Bar


def _bars(px_path):
    """由日收盘序列造 Bar 序列(仅评估所需字段)。"""
    start = date(2024, 1, 1)
    out = []
    d = start
    for px in px_path:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(Bar(day=d, open=px, high=px, low=px, close=px))
        d += timedelta(days=1)
    return out


def test_production_config_loads_and_matches_research_params():
    cfg = load_s1_config("configs/strategies/s1_gem_plus.yaml")
    assert cfg["strategy_id"] == "S1_GEM_PLUS_FINE"
    assert cfg["universe"] == ["SPY", "EFA", "QQQ", "GLD", "IEF"]
    assert cfg["cash_proxy"] == "BIL"
    assert cfg["score"]["weights"] == [0.2, 0.4, 0.4]          # 最后训练窗选中
    assert cfg["selection"]["top_n"] == 1
    assert cfg["volatility_targeting"]["enabled"] is False
    assert cfg.get("high_proximity_filter") is None            # 精调轮:新高过滤未被选中
    assert cfg.get("defensive_overlay") is None                # 五腿轮动本身即防御


def test_evaluate_picks_strongest_leg_and_cash_when_all_weak():
    cfg = load_s1_config("configs/strategies/s1_gem_plus.yaml")
    n = 320
    up = [100 * (1.002 ** i) for i in range(n)]        # 强趋势腿
    flat = [100.0] * n                                  # 平腿
    down = [100 * (0.998 ** i) for i in range(n)]      # 走弱腿(跌破 SMA200)
    bars = {"QQQ": _bars(up), "SPY": _bars(flat), "EFA": _bars(flat),
            "GLD": _bars(flat), "IEF": _bars(flat), "BIL": _bars(flat)}
    r = evaluate_s1(bars, cfg, bars["QQQ"][-1].day)
    assert r.selected == ("QQQ",)
    assert r.target_weights.get("QQQ", 0) > 0.99       # 单腿满仓

    bars_all_down = {s: _bars(down) for s in ["QQQ", "SPY", "EFA", "GLD", "IEF"]}
    bars_all_down["BIL"] = _bars(flat)
    r2 = evaluate_s1(bars_all_down, cfg, bars_all_down["QQQ"][-1].day)
    risk_weight = sum(w for s, w in r2.target_weights.items() if s != "BIL")
    assert risk_weight < 0.01                          # 全部跌破守门线 -> 风险腿清零,钱在现金腿
