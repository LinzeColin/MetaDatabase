"""ALPHA-LIVE-030:S2 超卖反弹测试——进场三条件逐一违反、三出口先到先执行。"""

from datetime import date, timedelta

import pytest

from backend.app.strategies.bars import Bar
from backend.app.strategies.s2_meanrev import (
    S2Exit,
    S2OpenTrade,
    evaluate_s2_entries,
    evaluate_s2_exits,
    load_s2_config,
    s2_enabled,
)

AS_OF = date(2026, 7, 16)
CFG = load_s2_config()


def uptrend_bars(n=220, start=100.0, daily=0.003, band=0.006):
    bars, price, day, made = [], start, AS_OF - timedelta(days=n * 2), 0
    while made < n:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        price *= 1.0 + daily
        bars.append(Bar(day=day, open=price / (1 + daily / 2), high=price * (1 + band),
                        low=price * (1 - band), close=price))
        made += 1
    return bars


def crash_two_days(bars, d1=0.03, d2=0.045, close_pos=0.05):
    """末两日重挫;最后一日收盘贴近全天最低(IBS = close_pos)。"""
    out = list(bars[:-2])
    prev_close = out[-1].close
    c1 = prev_close * (1 - d1)
    b1 = bars[-2]
    out.append(Bar(day=b1.day, open=prev_close, high=prev_close * 1.002, low=c1 * 0.998, close=c1))
    c2_low, c2_high = c1 * (1 - d2 - 0.01), c1 * 0.999
    close2 = c2_low + (c2_high - c2_low) * close_pos
    out.append(Bar(day=bars[-1].day, open=c1, high=c2_high, low=c2_low, close=close2))
    return out


def happy_universe():
    return {"SPY": crash_two_days(uptrend_bars()), "QQQ": uptrend_bars()}


def test_entry_all_conditions_met_emits_limit_signal():
    signals = evaluate_s2_entries(happy_universe(), CFG, AS_OF)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.symbol == "SPY"
    assert sig.order_type == "LIMIT" and sig.time_in_force == "DAY"
    last_close = happy_universe()["SPY"][-1].close
    assert sig.limit_price == pytest.approx(round(last_close * 0.995, 2))  # 前收 × 0.995
    d = sig.diagnostics
    assert d["close"] > d["sma200"] and d["rsi2"] < 8 and d["ibs"] < 0.2 and d["atr_ratio"] > 0.015


def test_entry_blocked_when_trend_broken():
    # 负漂移序列(收盘在 SMA200 下方)再砸两天:超卖但无趋势 -> 不出手
    bars, price, day, made = [], 200.0, AS_OF - timedelta(days=440), 0
    while made < 220:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        price *= 0.999
        bars.append(Bar(day=day, open=price, high=price * 1.006, low=price * 0.994, close=price))
        made += 1
    data = {"SPY": crash_two_days(bars), "QQQ": uptrend_bars()}
    signals = evaluate_s2_entries(data, CFG, AS_OF)
    assert all(s.symbol != "SPY" for s in signals)


def test_entry_blocked_when_rsi_not_extreme():
    data = {"SPY": uptrend_bars(), "QQQ": uptrend_bars()}  # 无砸坑,RSI 高
    assert evaluate_s2_entries(data, CFG, AS_OF) == []


def test_entry_blocked_when_ibs_high():
    data = {"SPY": crash_two_days(uptrend_bars(), close_pos=0.85), "QQQ": uptrend_bars()}
    assert evaluate_s2_entries(data, CFG, AS_OF) == []  # 收盘反弹到区间上沿


def test_entry_blocked_when_volatility_floor_unmet():
    calm = uptrend_bars(band=0.002)  # 日常波幅极小
    data = {"SPY": crash_two_days(calm, d1=0.006, d2=0.008), "QQQ": uptrend_bars(band=0.002)}
    signals = evaluate_s2_entries(data, CFG, AS_OF)
    assert all(s.diagnostics["atr_ratio"] > 0.015 for s in signals)


def test_max_open_trades_blocks_new_entries():
    open_trades = [
        S2OpenTrade("AAA", 100.0, AS_OF - timedelta(days=3), 2),
        S2OpenTrade("BBB", 50.0, AS_OF - timedelta(days=2), 1),
    ]
    assert evaluate_s2_entries(happy_universe(), CFG, AS_OF, open_trades) == []


def test_exits_priority_stop_loss_first_and_market_only_for_stop():
    bars = uptrend_bars()
    last = bars[-1].close
    trades = [
        S2OpenTrade("SPY", entry_price=last / 0.955, entry_day=AS_OF - timedelta(days=2), trading_days_held=11),
    ]  # 同时满足止损(-4.5%)与超时(11>=10):止损优先且用市价
    exits = evaluate_s2_exits({"SPY": bars}, CFG, AS_OF, trades)
    assert exits == [S2Exit("SPY", "STOP_LOSS", "MARKET")]


def test_exit_time_stop_uses_limit():
    bars = uptrend_bars()
    last = bars[-1].close
    trades = [S2OpenTrade("SPY", entry_price=last * 1.001, entry_day=AS_OF - timedelta(days=15), trading_days_held=10)]
    exits = evaluate_s2_exits({"SPY": bars}, CFG, AS_OF, trades)
    assert [(e.reason, e.order_type) for e in exits] == [("TIME_STOP", "LIMIT")]


def test_exit_take_profit_when_above_sma5():
    bars = uptrend_bars()  # 上升序列,收盘必在 SMA5 上方
    last = bars[-1].close
    trades = [S2OpenTrade("SPY", entry_price=last * 0.99, entry_day=AS_OF - timedelta(days=3), trading_days_held=2)]
    exits = evaluate_s2_exits({"SPY": bars}, CFG, AS_OF, trades)
    assert [(e.reason, e.order_type) for e in exits] == [("TAKE_PROFIT_SMA5", "LIMIT")]


def test_s2_enabled_requires_own_backtest_pass():
    assert s2_enabled(CFG, backtest_promo_passed=None) is False   # 没跑回测 = 不启用
    assert s2_enabled(CFG, backtest_promo_passed=False) is False
    assert s2_enabled(CFG, backtest_promo_passed=True) is True


def test_deterministic():
    a = evaluate_s2_entries(happy_universe(), CFG, AS_OF)
    b = evaluate_s2_entries(happy_universe(), CFG, AS_OF)
    assert [(s.symbol, s.limit_price) for s in a] == [(s.symbol, s.limit_price) for s in b]
