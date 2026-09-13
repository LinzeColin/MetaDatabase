"""新浪实时报价与美股、A 股日线。新浪要求 Referer。"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Dict, Iterable, List

from .base import DiskCache, HttpClient, MarketDataError, utc_now
from .models import Bar, Instrument, Quote


SINA_REFERER = "https://finance.sina.com.cn/"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_US_KLINE_URL = "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20_=/US_MinKService.getDailyK?symbol={symbol}"
SINA_CN_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=3000"
_ASSIGNMENT = re.compile(r'(?:var\s+)?hq_str_([^=]+)="([^"]*)";?')
_TIMESTAMP = re.compile(r"(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})")
_QUOTE_PRICE_INDEX = {"US": 1, "CN": 3, "HK": 6}


class SinaQuoteProvider:
    source = "sina_quote"

    def __init__(self, client: HttpClient, endpoint: str = SINA_QUOTE_URL) -> None:
        self.client = client
        self.endpoint = endpoint

    @staticmethod
    def parse(payload: bytes, instruments: Iterable[Instrument], observed_at=None) -> Dict[str, Quote]:
        observed_at = observed_at or utc_now()
        try:
            text = payload.decode("gbk")
        except UnicodeDecodeError as exc:
            raise MarketDataError("SINA_GBK_DECODE_FAILED") from exc
        requested = {item.sina_symbol: item for item in instruments if item.sina_symbol}
        result: Dict[str, Quote] = {}
        for source_symbol, raw in _ASSIGNMENT.findall(text):
            instrument = requested.get(source_symbol)
            if not instrument or not raw.strip():
                continue
            parts = [part.strip() for part in raw.split(",")]
            if len(parts) < 2:
                continue
            price_index = _QUOTE_PRICE_INDEX.get(instrument.market)
            if price_index is None:
                continue
            try:
                # 新浪字段随市场变化：US[1]、CN[3]、HK[6] 才是现价。
                price = float(parts[price_index])
            except (IndexError, ValueError):
                continue
            if price <= 0:
                continue
            source_time = None
            match = _TIMESTAMP.search(raw)
            if match:
                try:
                    source_time = datetime.fromisoformat(match.group(1) + "T" + match.group(2))
                except ValueError:
                    source_time = None
            currency = {"US": "USD", "CN": "CNY", "HK": "HKD"}.get(instrument.market, "UNKNOWN")
            result[instrument.symbol] = Quote(
                symbol=instrument.symbol,
                price=price,
                currency=currency,
                exchange_timezone=instrument.timezone,
                source="sina_quote",
                source_time=source_time,
                observed_at=observed_at,
            )
        return result

    def fetch(self, instruments: Iterable[Instrument]) -> Dict[str, Quote]:
        instruments = list(instruments)
        identifiers = [item.sina_symbol for item in instruments if item.sina_symbol]
        if not identifiers:
            return {}
        payload = self.client.get(self.endpoint + ",".join(identifiers), {"Referer": SINA_REFERER})
        return self.parse(payload, instruments)


class SinaKlineProvider:
    """新浪美股/A 股日线；美股 JSONP 与 A 股 JSON 都返回完整历史。"""

    source = "sina_daily"

    def __init__(
        self,
        client: HttpClient,
        cache: DiskCache,
        us_endpoint: str = SINA_US_KLINE_URL,
        cn_endpoint: str = SINA_CN_KLINE_URL,
    ) -> None:
        self.client = client
        self.cache = cache
        self.us_endpoint = us_endpoint
        self.cn_endpoint = cn_endpoint

    @staticmethod
    def _decode_rows(payload: bytes, market: str) -> list:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MarketDataError("SINA_KLINE_DECODE_FAILED") from exc
        if market == "US":
            marker = "=("
            start = text.find(marker)
            end = text.rfind(")")
            if start < 0 or end <= start + len(marker):
                raise MarketDataError("SINA_US_KLINE_JSONP_INVALID")
            text = text[start + len(marker):end]
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MarketDataError("SINA_KLINE_JSON_INVALID") from exc
        if not isinstance(rows, list):
            raise MarketDataError("SINA_KLINE_LIST_REQUIRED")
        return rows

    @classmethod
    def parse(cls, payload: bytes, instrument: Instrument, observed_at=None) -> List[Bar]:
        if instrument.market not in {"US", "CN"}:
            raise MarketDataError("SINA_KLINE_UNSUPPORTED:%s" % instrument.symbol)
        observed_at = observed_at or utc_now()
        rows = cls._decode_rows(payload, instrument.market)
        source = "sina_us_daily" if instrument.market == "US" else "sina_cn_daily"
        bars: List[Bar] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                bars.append(Bar(
                    symbol=instrument.symbol,
                    day=date.fromisoformat(str(row["d"] if instrument.market == "US" else row["day"])),
                    open=float(row["o"] if instrument.market == "US" else row["open"]),
                    high=float(row["h"] if instrument.market == "US" else row["high"]),
                    low=float(row["l"] if instrument.market == "US" else row["low"]),
                    close=float(row["c"] if instrument.market == "US" else row["close"]),
                    volume=float(row["v"] if instrument.market == "US" else row["volume"]),
                    exchange_timezone=instrument.timezone,
                    source=source,
                    observed_at=observed_at,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        unique = {bar.day: bar for bar in bars if bar.close > 0 and bar.high > 0 and bar.low > 0}
        ordered = [unique[day_key] for day_key in sorted(unique)]
        if len(ordered) < 2:
            raise MarketDataError("SINA_KLINE_INSUFFICIENT:%s" % instrument.symbol)
        return ordered

    def fetch(self, instrument: Instrument) -> List[Bar]:
        kline_symbol = instrument.sina_kline_symbol or instrument.sina_symbol
        if not kline_symbol or instrument.market not in {"US", "CN"}:
            raise MarketDataError("SINA_KLINE_UNSUPPORTED:%s" % instrument.symbol)
        key = "sina_%s_bars_%s" % (instrument.market.lower(), instrument.symbol.lower())
        payload = self.cache.load(key, 6 * 60 * 60)
        if payload is None:
            endpoint = self.us_endpoint if instrument.market == "US" else self.cn_endpoint
            payload = self.client.get(endpoint.format(symbol=kline_symbol), {"Referer": SINA_REFERER})
            self.cache.save(key, payload)
        return self.parse(payload, instrument)
