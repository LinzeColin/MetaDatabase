"""天天基金场外基金历史净值。仅日频，不伪装为实时成交报价。"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import List

from .base import DiskCache, HttpClient, MarketDataError, decode_text, fetch_validated_cached, utc_now
from .models import Bar, Instrument


EASTMONEY_FUND_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
_NET_WORTH = re.compile(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", re.S)


class EastMoneyFundProvider:
    source = "eastmoney_fund_nav"

    def __init__(self, client: HttpClient, cache: DiskCache, endpoint: str = EASTMONEY_FUND_URL) -> None:
        self.client = client
        self.cache = cache
        self.endpoint = endpoint

    @staticmethod
    def parse(payload: bytes, instrument: Instrument, observed_at=None) -> List[Bar]:
        observed_at = observed_at or utc_now()
        text = decode_text(payload, "utf-8", "EASTMONEY_FUND")
        matched = _NET_WORTH.search(text)
        if not matched:
            raise MarketDataError("EASTMONEY_FUND_NAV_MISSING")
        try:
            rows = json.loads(matched.group(1))
        except json.JSONDecodeError as exc:
            raise MarketDataError("EASTMONEY_FUND_NAV_INVALID") from exc
        bars: List[Bar] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                close = float(row["y"])
                day = datetime.fromtimestamp(float(row["x"]) / 1000.0, tz=timezone.utc).date()
            except (KeyError, TypeError, ValueError, OSError, OverflowError):
                continue
            bar = Bar(instrument.symbol, day, close, close, close, close, None,
                      instrument.timezone, "eastmoney_fund_nav", observed_at)
            if bar.has_finite_ohlcv() and close > 0:
                bars.append(bar)
        unique = {bar.day: bar for bar in bars}
        ordered = [unique[day_key] for day_key in sorted(unique)]
        if len(ordered) < 2:
            raise MarketDataError("EASTMONEY_FUND_INSUFFICIENT:%s" % instrument.symbol)
        return ordered

    def fetch(self, instrument: Instrument) -> List[Bar]:
        if not instrument.eastmoney_fund_code:
            raise MarketDataError("EASTMONEY_FUND_UNSUPPORTED:%s" % instrument.symbol)
        key = "fund_" + instrument.symbol.lower()
        return fetch_validated_cached(
            self.cache,
            key,
            12 * 60 * 60,
            lambda: self.client.get(self.endpoint.format(code=instrument.eastmoney_fund_code)),
            lambda payload: self.parse(payload, instrument),
        )
