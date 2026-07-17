"""技术指标纯函数——每个都能按白盒规范手工复算。

输入统一为按时间升序的收盘/高/低序列(list[float]);不依赖 pandas,
消除隐式索引对齐带来的不确定性。数据不足一律返回 None(宁缺毋滥,不填充)。
"""

from __future__ import annotations

import math
from typing import Optional, Sequence


def sma(closes: Sequence[float], period: int) -> Optional[float]:
    if period <= 0 or len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def trailing_return(closes: Sequence[float], lookback: int) -> Optional[float]:
    """r_n = P / P_{-n} - 1(白盒:score 的 r63/r126/r252)。"""
    if lookback <= 0 or len(closes) < lookback + 1:
        return None
    past = closes[-lookback - 1]
    if past == 0:
        return None
    return closes[-1] / past - 1.0


def realized_vol_annual_pct(closes: Sequence[float], window: int = 20, trading_days: int = 252) -> Optional[float]:
    """近 window 日收盘对数收益标准差年化(%)——S1 波动率调节分母。"""
    if len(closes) < window + 1:
        return None
    rets = [
        math.log(closes[i] / closes[i - 1])
        for i in range(len(closes) - window, len(closes))
        if closes[i - 1] > 0
    ]
    if len(rets) < window:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(trading_days) * 100.0


def rsi_wilder(closes: Sequence[float], period: int = 2) -> Optional[float]:
    """Wilder 平滑 RSI:U/D 各取 Wilder 递推平均,映射 0-100。

    手工复算口径(白盒规范第四节):首均值 = 前 period 根涨/跌幅简单平均,
    此后 avg = (前 avg*(period-1) + 当日值)/period;RSI = 100 - 100/(1+RS)。
    """
    if len(closes) < period + 1:
        return None
    ups: list[float] = []
    downs: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        ups.append(max(delta, 0.0))
        downs.append(max(-delta, 0.0))
    avg_u = sum(ups[:period]) / period
    avg_d = sum(downs[:period]) / period
    for i in range(period, len(ups)):
        avg_u = (avg_u * (period - 1) + ups[i]) / period
        avg_d = (avg_d * (period - 1) + downs[i]) / period
    if avg_d == 0:
        return 100.0
    rs = avg_u / avg_d
    return 100.0 - 100.0 / (1.0 + rs)


def ibs(high: float, low: float, close: float) -> Optional[float]:
    """IBS = (收盘 - 最低) / (最高 - 最低);最高==最低时无定义。"""
    if high == low:
        return None
    return (close - low) / (high - low)


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> Optional[float]:
    """ATR(Wilder):TR = max(H-L, |H-前收|, |L-前收|);首均值简单平均后递推。"""
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    value = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        value = (value * (period - 1) + trs[i]) / period
    return value
