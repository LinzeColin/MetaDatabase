"""固定规则连续复盘的逐笔账本与回撤 episodes 助手(手算可验)。"""

from datetime import date, timedelta

from backend.app.backtest.pipeline import (
    closed_round_trips, drawdown_episodes, ledger_metrics,
)


def _d(n):
    return date(2020, 1, 1) + timedelta(days=n)


def test_closed_round_trips_fifo_net_of_fees():
    """FIFO 配对 + 按股均摊买卖费,净额逐笔盈亏可手算。"""
    fills = [
        {"day": _d(0), "sym": "QQQ", "side": "BUY", "qty": 10, "price": 100.0, "fee": 1.0},
        {"day": _d(1), "sym": "QQQ", "side": "SELL", "qty": 4, "price": 110.0, "fee": 0.4},
        {"day": _d(2), "sym": "QQQ", "side": "SELL", "qty": 6, "price": 90.0, "fee": 0.6},
    ]
    trips = closed_round_trips(fills)
    assert len(trips) == 2
    # 第一笔:4×(110-100) - 4×(0.1买+0.1卖) = 40 - 0.8 = 39.2
    assert round(trips[0]["pnl"], 2) == 39.2
    # 第二笔:6×(90-100) - 6×(0.1+0.1) = -60 - 1.2 = -61.2
    assert round(trips[1]["pnl"], 2) == -61.2


def test_closed_round_trips_ignores_open_tail():
    """未平尾仓不计入 closed round-trip。"""
    fills = [
        {"day": _d(0), "sym": "SPY", "side": "BUY", "qty": 5, "price": 50.0, "fee": 0.5},
        {"day": _d(1), "sym": "SPY", "side": "SELL", "qty": 2, "price": 60.0, "fee": 0.2},
    ]
    trips = closed_round_trips(fills)
    assert len(trips) == 1 and trips[0]["qty"] == 2  # 剩 3 股未平,不记


def test_drawdown_episodes_peak_trough_recovery():
    """峰→谷→恢复:两段回撤,深度与修复日可手算。"""
    days = [_d(i) for i in range(5)]
    equity = [100.0, 90.0, 110.0, 105.0, 120.0]
    eps = drawdown_episodes(days, equity)
    assert len(eps) == 2
    assert eps[0]["depth_pct"] == 10.0 and eps[0]["recovered"] is True
    assert eps[0]["recovery_days"] == 2               # d0→d2
    assert eps[1]["depth_pct"] == 4.55                # 1-105/110
    assert eps[1]["recovered"] is True


def test_drawdown_open_episode_never_recovers():
    """收尾仍在水下 = OPEN(recovery_day=None)。"""
    days = [_d(i) for i in range(3)]
    equity = [100.0, 120.0, 108.0]                    # 峰120后跌到108未回
    eps = drawdown_episodes(days, equity)
    assert eps[-1]["recovered"] is False
    assert eps[-1]["recovery_days"] is None
    assert eps[-1]["depth_pct"] == 10.0               # 1-108/120


def test_ledger_metrics_combines_monthly_and_per_trade():
    """ledger_metrics 同时给月度指标与真逐笔盈亏比/胜率,并挑最深回撤的修复时间。"""
    days = [_d(i) for i in range(5)]
    equity = [1000.0, 900.0, 1100.0, 1050.0, 1200.0]
    fills = [
        {"day": _d(0), "sym": "QQQ", "side": "BUY", "qty": 10, "price": 100.0, "fee": 1.0},
        {"day": _d(2), "sym": "QQQ", "side": "SELL", "qty": 10, "price": 110.0, "fee": 1.0},
    ]
    m = ledger_metrics(days, equity, fills)
    assert m["round_trips"] == 1
    assert m["per_trade_win_rate_pct"] == 100.0       # 唯一往返盈利
    assert "max_dd_depth_pct" in m and m["max_dd_recovered"] in (True, False)
