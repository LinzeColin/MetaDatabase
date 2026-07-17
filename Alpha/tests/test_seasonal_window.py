"""S1 季节窗口轴(in_market_months):默认关闭零行为变化;窗口外动量退现金。"""

from datetime import date, timedelta

from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import S1Params, precompute, simulate_s1
from backend.app.strategies.bars import Bar

FEE = FeeModel(commission_usd_per_order=0.99)


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def series_map(days, base=100.0, slope=0.05):
    closes_a = [base + slope * i for i in range(len(days))]
    closes_b = [base + 0.5 * slope * i for i in range(len(days))]
    cash = [100.0] * len(days)
    def mk(name, cs):
        return precompute(name, [Bar(day=d, open=c, high=c, low=c, close=c)
                                 for d, c in zip(days, cs)])
    return {"AAA": mk("AAA", closes_a), "BBB": mk("BBB", closes_b), "CSH": mk("CSH", cash)}


def run(params, days, s):
    return simulate_s1(s, ["AAA", "BBB", "CSH"], "CSH", params,
                       start=days[0], end=days[-1], sleeve_usd=1980.0,
                       fee=FEE, calendar=days)


def test_all_year_window_equals_default():
    days = weekdays(date(2023, 1, 2), 520)  # 覆盖约 2 年,SMA200 可用
    s = series_map(days)
    base = run(S1Params(top_n=1, target_vol=999.0), days, s)
    allyear = run(S1Params(top_n=1, target_vol=999.0,
                           in_market_months=tuple(range(1, 13))), days, s)
    assert base.equity == allyear.equity
    assert base.orders == allyear.orders


def test_out_of_window_months_hold_cash_proxy():
    days = weekdays(date(2023, 1, 2), 620)
    s = series_map(days)
    r = run(S1Params(top_n=1, target_vol=999.0, in_market_months=(11, 12, 1, 2, 3, 4)),
            days, s)
    base = run(S1Params(top_n=1, target_vol=999.0), days, s)
    # 窗口版在 5-10 月不持动量仓:总订单数少于全年版会重平衡进出 → 订单结构不同,
    # 且 5-10 月(除进出场评估日)净值应等于现金替身持有(合成现金恒价 → 净值平)
    assert r.orders != base.orders
    # 同一年内的出场月份(2024 年 6-9 月)净值纹丝不动 = 确在现金替身里
    flat_stretch = [v for d, v in zip(r.equity_days, r.equity)
                    if d.year == 2024 and d.month in (6, 7, 8, 9)]
    assert len(flat_stretch) > 40
    assert max(flat_stretch) - min(flat_stretch) < 1e-6
