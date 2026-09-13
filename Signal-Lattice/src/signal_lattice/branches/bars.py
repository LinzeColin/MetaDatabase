"""策略输入的 Bar 适配层。

来源：``Alpha/backend/app/strategies/bars.py``。Signal-Lattice 的真实行情
``marketdata.models.Bar`` 已包含相同的 ``day/open/high/low/close/volume`` 字段，
所以本模块直接在该模型上工作，不复制第二个 Bar 类型。
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from ..marketdata.models import Bar


def closes(bars: Sequence[Bar]) -> list[float]:
    return [bar.close for bar in bars]


def highs(bars: Sequence[Bar]) -> list[float]:
    return [bar.high for bar in bars]


def lows(bars: Sequence[Bar]) -> list[float]:
    return [bar.low for bar in bars]


def assert_ascending(bars: Sequence[Bar]) -> None:
    for index in range(1, len(bars)):
        if bars[index].day <= bars[index - 1].day:
            raise ValueError(f"Bar 序列必须严格升序: {bars[index - 1].day} -> {bars[index].day}")


def slice_until(bars: Sequence[Bar], as_of: date) -> list[Bar]:
    """只使用 ``as_of`` 及更早的数据。"""
    return [bar for bar in bars if bar.day <= as_of]
