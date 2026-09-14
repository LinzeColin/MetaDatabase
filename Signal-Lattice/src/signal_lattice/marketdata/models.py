"""真实市场数据的统一模型。

所有时间同时保留交易所时间、来源时间和本机抓取时间，调用方不能把抓取成功
误解成行情新鲜。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Optional


# 各市场的免费报价源声明时延。港股取 25 分钟：2026-09-14 开市后每 90 秒一次的
# 8 个采样显示稳态滞后为 19–24 分钟，25 分钟覆盖该正常区间并保留余量；开市追赶
# 尖峰 29.6 分钟仍应短暂阻断。现有 180 秒 TTL 只吸收短时刷新抖动，来源连续不推进
# 另由运行时的 12 分钟卡住门处理。A 股实测实时，美股实测实时；美股休市另走最近收盘口径。
US_DECLARED_FEED_DELAY_MINUTES = 0
CN_DECLARED_FEED_DELAY_MINUTES = 0
HK_FREE_QUOTE_DECLARED_FEED_DELAY_MINUTES = 25


def ohlcv_violations(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: Optional[float],
) -> tuple[str, ...]:
    """返回 OHLCV 违反的可报告规则，不把上游脏数据静默混入序列。"""
    violations: list[str] = []
    values = {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }
    if volume is not None:
        values["volume"] = volume
    try:
        for name, value in values.items():
            if not math.isfinite(value):
                violations.append("%s_NONFINITE" % name.upper())
    except TypeError:
        return ("OHLCV_NON_NUMERIC",)
    if violations:
        return tuple(violations)
    if open_price <= 0:
        violations.append("OPEN_NOT_POSITIVE")
    if high <= 0:
        violations.append("HIGH_NOT_POSITIVE")
    if low <= 0:
        violations.append("LOW_NOT_POSITIVE")
    if close <= 0:
        violations.append("CLOSE_NOT_POSITIVE")
    if volume is not None and volume < 0:
        violations.append("VOLUME_NEGATIVE")
    if low > high:
        violations.append("LOW_ABOVE_HIGH")
    if low > min(open_price, close):
        violations.append("LOW_ABOVE_OPEN_OR_CLOSE")
    if high < max(open_price, close):
        violations.append("HIGH_BELOW_OPEN_OR_CLOSE")
    return tuple(violations)


def has_valid_ohlcv(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: Optional[float],
) -> bool:
    """判断一根 Bar 是否既有限又符合 OHLCV 的基本市场语义。"""
    return not ohlcv_violations(open_price, high, low, close, volume)


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
    # 这是来源时间与交易所当前时间之间允许的已声明时延，不代表实时行情。
    declared_feed_delay_minutes: int = 0


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
        try:
            return all(math.isfinite(value) for value in values)
        except TypeError:
            return False

    def has_valid_ohlcv(self) -> bool:
        """统一的 OHLCV 完整性门，供 provider、缓存读取与运行时共同调用。"""
        return has_valid_ohlcv(self.open, self.high, self.low, self.close, self.volume)

    def ohlcv_violations(self) -> tuple[str, ...]:
        """提供被剔除 Bar 的精确语义违规说明。"""
        return ohlcv_violations(self.open, self.high, self.low, self.close, self.volume)


@dataclass(frozen=True)
class BarQualityIssue:
    """日线 provider 拒绝的单行及其可审计分类。"""

    symbol: str
    day: Optional[date]
    source: str
    violations: tuple[str, ...]
    issue_type: str = "OHLCV_VIOLATION"
