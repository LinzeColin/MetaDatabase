"""真实市场数据的统一模型。

所有时间同时保留交易所时间、来源时间和本机抓取时间，调用方不能把抓取成功
误解成行情新鲜。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Optional


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    market: str
    asset_type: str
    timezone: str
    sina_symbol: Optional[str]
    tencent_symbol: Optional[str]
    tencent_kline_symbol: Optional[str]
    eastmoney_fund_code: Optional[str]
    benchmark: Optional[str]
    realtime_quote: bool = True
    # 新浪日线接口的代码与实时报价代码不同：美股要裸代码 SPY，传 gb_spy 会返回 null。
    sina_kline_symbol: Optional[str] = None


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    currency: str
    exchange_timezone: str
    source: str
    source_time: Optional[datetime]
    observed_at: datetime


@dataclass(frozen=True)
class Bar:
    symbol: str
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]
    exchange_timezone: str
    source: str
    observed_at: datetime

    def has_finite_ohlcv(self) -> bool:
        """OHLC 与已提供的成交量都必须是有限数值。"""
        values = (self.open, self.high, self.low, self.close)
        if self.volume is not None:
            values += (self.volume,)
        return all(math.isfinite(value) for value in values)
