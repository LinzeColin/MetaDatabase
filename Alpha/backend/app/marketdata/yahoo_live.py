"""Yahoo v8 实时行情源(影子盘用;不连券商、不登录)。

纪律:
- 报价**不缓存**,每次都是新请求(模拟成交必须用当次新取的行情);
- 时间戳如实用交易所 regularMarketTime,新鲜度由风控/模拟券商按同一常量判;
- 日线走 YahooDailySource(短超时、少重试),不走 fetch_verified,不读写回测缓存;
- 实时报价/快照:取不到的标的直接省略(快照)或抛 QuoteUnavailable(单只),绝不编造。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Iterator, Optional
from zoneinfo import ZoneInfo

from backend.app.backtest import data_sources

ET = ZoneInfo("America/New_York")
SYD = ZoneInfo("Australia/Sydney")
QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1m"
#: 实盘日线抓取上限:6 个标的最坏 6×10 秒,远低于 WatchdogSec=300
DAILY_TIMEOUT_SECONDS = 10
DAILY_RETRIES = 1
#: 一次取多只报价的总预算(秒):超时后不再开新请求,没取到的标的按缺失处理(调用方不落评估标记)。
#: 单只最坏 8×2+4.5=20.5 秒,6 只可达 123 秒,会超过守护的心跳陈旧阈值,所以必须封顶。
SNAPSHOT_BUDGET_SECONDS = 40.0


class QuoteUnavailable(Exception):
    """取不到可信报价(网络失败、价格非正、代码不符等)。"""


@dataclass(frozen=True)
class LiveQuote:
    symbol: str
    price: float
    ts_utc: datetime


class YahooQuoteSource:
    def __init__(self, *, fetch_json: Optional[Callable[..., dict]] = None,
                 timeout: int = 8, retries: int = 2,
                 budget_seconds: float = SNAPSHOT_BUDGET_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch = fetch_json or data_sources._http_json
        self._timeout = timeout
        self._retries = retries
        self._budget = budget_seconds
        self._clock = clock

    def _within_budget(self, symbols: list[str]) -> Iterator[str]:
        """逐只产出标的;总预算用完就停,不再开新请求。"""
        deadline = self._clock() + self._budget
        for sym in symbols:
            if self._clock() > deadline:
                return
            yield sym

    # ---------- 交易循环协议 ----------

    def get_quote(self, sym: str) -> LiveQuote:
        try:
            data = self._fetch(QUOTE_URL.format(sym=sym),
                               timeout=self._timeout, retries=self._retries)
            meta = data["chart"]["result"][0]["meta"]
            price = float(meta["regularMarketPrice"])
            t = int(meta["regularMarketTime"])
            got = str(meta.get("symbol", ""))
        except Exception as exc:
            raise QuoteUnavailable(f"{sym}: {type(exc).__name__}: {exc}") from exc
        if got.upper() != sym.upper():
            raise QuoteUnavailable(f"{sym}: 返回代码不符 {got!r}")
        if price <= 0:
            raise QuoteUnavailable(f"{sym}: 价格非正 {price}")
        return LiveQuote(symbol=sym, price=price,
                         ts_utc=datetime.fromtimestamp(t, tz=timezone.utc))

    def get_snapshot(self, symbols: list[str]) -> dict[str, dict]:
        """symbol -> {price, update_time};update_time 为美东无时区字符串(与 quote_age_seconds 约定一致)。"""
        out: dict[str, dict] = {}
        for sym in self._within_budget(symbols):
            try:
                q = self.get_quote(sym)
            except QuoteUnavailable:
                continue
            out[sym] = {"price": q.price,
                        "update_time": q.ts_utc.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S")}
        return out

    def get_daily_bars(self, sym: str, start: str, end: str) -> list[dict]:
        """复权日线;失败抛异常,由调用方决定(交易循环按数据不完整处理,不落标记)。"""
        src = data_sources.YahooDailySource(timeout=DAILY_TIMEOUT_SECONDS, retries=DAILY_RETRIES)
        rows = src.fetch(sym, date.fromisoformat(start), date.fromisoformat(end))
        return [{"day": b.day.isoformat(), "open": b.open, "high": b.high,
                 "low": b.low, "close": b.close}
                for b in data_sources.to_adjusted_bars(rows)]

    # ---------- 看盘页协议(失败降级为空,页面如实显示取不到) ----------

    def snapshots(self, symbols: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for sym in self._within_budget(symbols):
            try:
                q = self.get_quote(sym)
            except QuoteUnavailable:
                continue
            out[sym] = {"price": q.price,
                        "at": q.ts_utc.astimezone(SYD).strftime("%Y-%m-%d %H:%M:%S")}
        return out

    def daily_closes(self, sym: str, start: str, end: str) -> list[tuple[str, float]]:
        try:
            return [(r["day"], r["close"]) for r in self.get_daily_bars(sym, start, end)]
        except Exception:
            return []
