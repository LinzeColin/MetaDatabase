"""腾讯报价备份与港股/A 股备份日线。"""

from __future__ import annotations

from datetime import date, datetime
import math
import re
from typing import Dict, Iterable, List, Optional

from .base import DiskCache, HttpClient, MarketDataError, decode_text, fetch_validated_cached, read_json, utc_now
from .models import Bar, BarQualityIssue, Instrument, Quote


TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/{kind}/get?param={symbol},day,,,2000,qfq"
_QUOTE_TIMESTAMP = re.compile(r"20\d{12}\Z")


class TencentQuoteProvider:
    source = "tencent_quote"

    def __init__(self, client: HttpClient, endpoint: str = TENCENT_QUOTE_URL) -> None:
        self.client = client
        self.endpoint = endpoint

    @staticmethod
    def parse(payload: bytes, instruments: Iterable[Instrument], observed_at=None) -> Dict[str, Quote]:
        observed_at = observed_at or utc_now()
        text = decode_text(payload, "gbk", "TENCENT_QUOTE")
        lookup = {item.tencent_symbol: item for item in instruments if item.tencent_symbol}
        result: Dict[str, Quote] = {}
        for line in text.split(";"):
            line = line.strip()
            if "=\"" not in line:
                continue
            prefix, raw = line.split("=\"", 1)
            source_symbol = prefix.removeprefix("v_")
            instrument = lookup.get(source_symbol)
            fields = raw.rstrip('"').split("~")
            if not instrument or len(fields) < 4:
                continue
            try:
                price = float(fields[3])
            except ValueError:
                continue
            if not math.isfinite(price) or price <= 0:
                continue
            currency = {"CN": "CNY", "HK": "HKD"}.get(instrument.market, "UNKNOWN")
            result[instrument.symbol] = Quote(
                symbol=instrument.symbol,
                price=price,
                currency=currency,
                exchange_timezone=instrument.timezone,
                source="tencent_quote",
                source_time=_parse_source_time(fields),
                observed_at=observed_at,
            )
        return result

    def fetch(self, instruments: Iterable[Instrument]) -> Dict[str, Quote]:
        items = [item for item in instruments if item.tencent_symbol]
        if not items:
            return {}
        payload = self.client.get(
            self.endpoint + ",".join(item.tencent_symbol for item in items),
            provider=self.source,
        )
        return self.parse(payload, items)


class TencentKlineProvider:
    source = "tencent_daily"

    def __init__(self, client: HttpClient, cache: DiskCache, endpoint: str = TENCENT_KLINE_URL) -> None:
        self.client = client
        self.cache = cache
        self.endpoint = endpoint
        self.last_quality_issues: list[BarQualityIssue] = []

    @staticmethod
    def parse(
        payload: bytes,
        instrument: Instrument,
        observed_at=None,
        quality_issues: Optional[list[BarQualityIssue]] = None,
    ) -> List[Bar]:
        observed_at = observed_at or utc_now()
        root = read_json(payload, "TENCENT_KLINE")
        if root.get("code") != 0:
            raise MarketDataError("TENCENT_KLINE_CODE_%s" % root.get("code"))
        data = root.get("data")
        if not isinstance(data, dict):
            raise MarketDataError("TENCENT_KLINE_DATA_MISSING")
        key = instrument.tencent_kline_symbol
        envelope = data.get(key) if key else None
        if not isinstance(envelope, dict):
            raise MarketDataError("TENCENT_KLINE_SYMBOL_MISSING:%s" % instrument.symbol)
        # 个股/ETF 通常给 qfqday；指数没有复权，腾讯仅给 day。
        rows = envelope.get("qfqday")
        if not isinstance(rows, list):
            rows = envelope.get("day")
        if not isinstance(rows, list):
            raise MarketDataError("TENCENT_KLINE_SERIES_MISSING:%s" % instrument.symbol)
        bars: List[Bar] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                if quality_issues is not None:
                    quality_issues.append(BarQualityIssue(
                        instrument.symbol, None, "tencent_daily", ("ROW_SHAPE_INVALID",), "STRUCTURAL",
                    ))
                continue
            try:
                bar = Bar(
                    symbol=instrument.symbol,
                    day=date.fromisoformat(str(row[0])),
                    open=float(row[1]),
                    close=float(row[2]),
                    high=float(row[3]),
                    low=float(row[4]),
                    volume=float(row[5]) if row[5] not in (None, "") else None,
                    exchange_timezone=instrument.timezone,
                    source="tencent_daily",
                    observed_at=observed_at,
                )
            except (TypeError, ValueError, OverflowError):
                if quality_issues is not None:
                    quality_issues.append(BarQualityIssue(
                        instrument.symbol, None, "tencent_daily", ("FIELD_CONVERSION_FAILED",), "CONVERSION",
                    ))
                continue
            if not bar.has_valid_ohlcv():
                if quality_issues is not None:
                    quality_issues.append(BarQualityIssue(
                        instrument.symbol, bar.day, "tencent_daily", bar.ohlcv_violations(), "OHLCV_VIOLATION",
                    ))
                continue
            bars.append(bar)
        unique = {bar.day: bar for bar in bars}
        ordered = [unique[day_key] for day_key in sorted(unique)]
        if len(ordered) < 2:
            raise MarketDataError("TENCENT_KLINE_INSUFFICIENT:%s" % instrument.symbol)
        return ordered

    def fetch(self, instrument: Instrument) -> List[Bar]:
        if not instrument.tencent_kline_symbol:
            raise MarketDataError("TENCENT_KLINE_UNSUPPORTED:%s" % instrument.symbol)
        key = "bars_" + instrument.symbol.lower()
        kind = "usfqkline" if instrument.market == "US" else "hkfqkline" if instrument.market == "HK" else "fqkline"
        self.last_quality_issues = []
        return fetch_validated_cached(
            self.cache,
            key,
            6 * 60 * 60,
            lambda: self.client.get(
                self.endpoint.format(kind=kind, symbol=instrument.tencent_kline_symbol),
                provider=self.source,
            ),
            lambda payload: self.parse(payload, instrument, quality_issues=self.last_quality_issues),
        )


def _parse_source_time(fields: list[str]) -> datetime | None:
    """仅在 qt.gtimg.cn 实际返回 YYYYMMDDhhmmss 时解析；观察时间绝不替代来源时间。"""
    for field in reversed(fields):
        candidate = field.strip()
        if not _QUOTE_TIMESTAMP.fullmatch(candidate):
            continue
        try:
            return datetime.strptime(candidate, "%Y%m%d%H%M%S")
        except ValueError:
            return None
    return None
