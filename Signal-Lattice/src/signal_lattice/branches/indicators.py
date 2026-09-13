"""技术指标纯函数。

来源：``Alpha/backend/app/strategies/indicators.py``。
已复制到 Signal-Lattice，避免跨目录 import；输入为时间升序序列，样本不足
时返回 ``None``，不填充数据。
"""

from __future__ import annotations

import math
from typing import Optional, Sequence


def sma(closes: Sequence[float], period: int) -> Optional[float]:
    if period <= 0 or len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def trailing_return(closes: Sequence[float], lookback: int) -> Optional[float]:
    """r_n = P / P_{-n} - 1。"""
    if lookback <= 0 or len(closes) < lookback + 1:
        return None
    past = closes[-lookback - 1]
    if past == 0:
        return None
    return closes[-1] / past - 1.0


def realized_vol_annual_pct(
    closes: Sequence[float], window: int = 20, trading_days: int = 252
) -> Optional[float]:
    """近 ``window`` 日收盘对数收益标准差年化百分比。"""
    if len(closes) < window + 1:
        return None
    returns = [
        math.log(closes[index] / closes[index - 1])
        for index in range(len(closes) - window, len(closes))
        if closes[index - 1] > 0
    ]
    if len(returns) < window:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(trading_days) * 100.0


def rsi_wilder(closes: Sequence[float], period: int = 2) -> Optional[float]:
    """Wilder 平滑 RSI，结果范围为 0 至 100。"""
    if len(closes) < period + 1:
        return None
    ups: list[float] = []
    downs: list[float] = []
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        ups.append(max(delta, 0.0))
        downs.append(max(-delta, 0.0))
    average_up = sum(ups[:period]) / period
    average_down = sum(downs[:period]) / period
    for index in range(period, len(ups)):
        average_up = (average_up * (period - 1) + ups[index]) / period
        average_down = (average_down * (period - 1) + downs[index]) / period
    if average_down == 0:
        return 100.0
    relative_strength = average_up / average_down
    return 100.0 - 100.0 / (1.0 + relative_strength)


def ibs(high: float, low: float, close: float) -> Optional[float]:
    """IBS = (close - low) / (high - low)。"""
    if high == low:
        return None
    return (close - low) / (high - low)


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> Optional[float]:
    """Wilder ATR。"""
    count = len(closes)
    if count < period + 1 or len(highs) != count or len(lows) != count:
        return None
    true_ranges: list[float] = []
    for index in range(1, count):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    value = sum(true_ranges[:period]) / period
    for index in range(period, len(true_ranges)):
        value = (value * (period - 1) + true_ranges[index]) / period
    return value
