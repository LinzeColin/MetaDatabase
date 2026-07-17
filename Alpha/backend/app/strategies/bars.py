"""策略输入的统一数据形状:日线 Bar 序列(升序),前视偏差防护在此强制。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float


def closes(bars: Sequence[Bar]) -> list[float]:
    return [b.close for b in bars]


def highs(bars: Sequence[Bar]) -> list[float]:
    return [b.high for b in bars]


def lows(bars: Sequence[Bar]) -> list[float]:
    return [b.low for b in bars]


def assert_ascending(bars: Sequence[Bar]) -> None:
    for i in range(1, len(bars)):
        if bars[i].day <= bars[i - 1].day:
            raise ValueError(f"Bar 序列必须严格升序: {bars[i - 1].day} -> {bars[i].day}")


def slice_until(bars: Sequence[Bar], as_of: date) -> list[Bar]:
    """只允许用 as_of 及更早的数据(信号只用 T-1 及更早由调用方把 as_of 设为 T-1)。"""
    return [b for b in bars if b.day <= as_of]
