"""日历效应(TOM)模拟器:合成数据下的确定性行为。"""

from datetime import date, timedelta

from backend.app.backtest.calendar_effects import TomParams, simulate_tom
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import precompute
from backend.app.strategies.bars import Bar

FEE = FeeModel(commission_usd_per_order=0.99)


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def make_series(days: list[date], closes: list[float]):
    bars = [Bar(day=d, open=c, high=c, low=c, close=c) for d, c in zip(days, closes)]
    return precompute("TST", bars)


def test_flat_prices_only_fee_drag():
    # 3 个完整月、价格恒定:净值只被费用磨损,每月一个来回
    days = weekdays(date(2025, 3, 3), 64)  # 覆盖 2025-03 至 2025-05
    ss = make_series(days, [100.0] * len(days))
    r = simulate_tom(ss, TomParams(entry_days_before=4, exit_days_after=3),
                     start=days[0], end=days[-1], sleeve_usd=1980.0, fee=FEE)
    assert r.trades >= 2 and r.orders == r.trades * 2
    assert r.fees_usd > 0
    assert abs(r.equity[-1] - (1980.0 - r.fees_usd)) < 1e-9


def test_entry_exit_land_on_correct_days():
    days = weekdays(date(2025, 3, 3), 64)
    ss = make_series(days, [100.0] * len(days))
    r = simulate_tom(ss, TomParams(entry_days_before=2, exit_days_after=2),
                     start=days[0], end=days[-1], sleeve_usd=1980.0, fee=FEE)
    march = [d for d in days if d.month == 3]
    april = [d for d in days if d.month == 4]
    entry_1, exit_1 = march[-2], april[1]
    # 入场日起持仓(净值仍计市值),离场日后回到现金
    i_entry = r.equity_days.index(entry_1)
    i_exit = r.equity_days.index(exit_1)
    assert r.equity[i_entry] < 1980.0  # 已付买入费
    assert r.equity[i_exit] < r.equity[i_entry]  # 平价离场再付卖出费
    assert r.trades >= 1


def test_trend_filter_blocks_when_no_uptrend():
    # 价格恒定:收盘从不「高于」SMA200(相等),且前 200 日 SMA 为 None → 全程不入场
    days = weekdays(date(2024, 1, 1), 280)
    ss = make_series(days, [100.0] * len(days))
    r = simulate_tom(ss, TomParams(use_trend_filter=True),
                     start=days[0], end=days[-1], sleeve_usd=1980.0, fee=FEE)
    assert r.orders == 0 and r.trades == 0
    assert r.equity[-1] == 1980.0


def test_trend_filter_allows_uptrend_and_wins_counted():
    # 线性上涨:T-1 收盘恒在 SMA200 上方 → 正常入场;卖价>买价 → 全胜
    days = weekdays(date(2024, 1, 1), 280)
    closes = [100.0 + 0.1 * i for i in range(len(days))]
    ss = make_series(days, closes)
    r = simulate_tom(ss, TomParams(use_trend_filter=True),
                     start=days[0], end=days[-1], sleeve_usd=1980.0, fee=FEE)
    assert r.trades >= 1
    assert r.wins == r.trades


def test_integer_share_infeasibility_counted():
    days = weekdays(date(2025, 3, 3), 64)
    ss = make_series(days, [10000.0] * len(days))  # 一股都买不起
    r = simulate_tom(ss, TomParams(), start=days[0], end=days[-1],
                     sleeve_usd=1980.0, fee=FEE)
    assert r.orders == 0
    assert r.skipped_infeasible >= 2
    assert r.equity[-1] == 1980.0
