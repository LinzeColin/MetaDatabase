from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Candidate


class MarketProviderError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MarketProviderError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _market_from_code(code: str) -> str:
    return code.split(".", 1)[0].upper() if "." in code else "AU"


def _public_from_code(code: str) -> str:
    return code.split(".")[-1].upper()


def _source_as_of(row: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    for source in (row, payload or {}):
        for key in ("quote_time", "as_of", "update_time", "data_time", "last_updated", "timestamp"):
            value = str(source.get(key, "")).strip()
            if value:
                return value
    return None


def _record_source_times(
    candidate: Candidate, row: dict[str, Any], now: datetime, payload: dict[str, Any] | None = None
) -> None:
    source_as_of = _source_as_of(row, payload)
    candidate.quote_time = source_as_of
    candidate.metadata["source_as_of"] = source_as_of
    candidate.metadata["observed_at"] = now.astimezone(timezone.utc).replace(microsecond=0).isoformat()


class FixtureProvider:
    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir

    def catalog(self) -> list[dict[str, Any]]:
        payload = _read_json(self.fixture_dir / "catalog.json")
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            raise MarketProviderError("FIXTURE_CATALOG_INVALID")
        return [row for row in rows if isinstance(row, dict)]

    def snapshot(self, candidates: list[Candidate], now: datetime, include_history: bool) -> list[Candidate]:
        payload = _read_json(self.fixture_dir / "market_snapshot.json")
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            raise MarketProviderError("FIXTURE_MARKET_INVALID")
        by_code = {str(row.get("provider_code", "")).upper(): row for row in rows if isinstance(row, dict)}
        result: list[Candidate] = []
        for candidate in candidates:
            row = by_code.get(candidate.provider_code.upper())
            if row is None:
                continue
            candidate.platform_verified = True
            candidate.price = float(row.get("price", 0.0) or 0.0) or None
            _record_source_times(candidate, row, now, payload)
            if include_history or not candidate.bars:
                candidate.bars = list(row.get("bars", []))
            candidate.fundamentals = dict(row.get("fundamentals", {}))
            candidate.events = list(row.get("events", []))
            candidate.liquidity_score = float(row.get("liquidity_score", 0.9))
            candidate.cost_bps = float(row.get("cost_bps", 10.0))
            result.append(candidate)
        return result


class MoomooReadOnlyProvider:
    """Read-only quote/catalog adapter. It never imports or opens a trade context."""

    def __init__(self):
        self.host = os.environ.get("MOOMOO_OPEND_HOST", "127.0.0.1")
        self.port = int(os.environ.get("MOOMOO_OPEND_PORT", "11111"))
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise MarketProviderError("MOOMOO_OPEND_MUST_BE_LOCAL")

    @staticmethod
    def _sdk():
        try:
            from moomoo import (  # type: ignore
                AuType,
                KLType,
                Market,
                OpenQuoteContext,
                RET_OK,
                SecurityType,
            )
        except ImportError:
            try:
                from futu import (  # type: ignore
                    AuType,
                    KLType,
                    Market,
                    OpenQuoteContext,
                    RET_OK,
                    SecurityType,
                )
            except ImportError as exc:
                raise MarketProviderError("MOOMOO_QUOTE_SDK_NOT_INSTALLED") from exc
        return OpenQuoteContext, RET_OK, KLType, AuType, Market, SecurityType

    def catalog(self) -> list[dict[str, Any]]:
        OpenQuoteContext, RET_OK, _, _, Market, SecurityType = self._sdk()
        quote = OpenQuoteContext(host=self.host, port=self.port)
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            for market_name in ("AU", "US", "HK"):
                market = getattr(Market, market_name, None)
                if market is None:
                    continue
                for asset_class in ("ETF", "STOCK"):
                    security_type = getattr(SecurityType, asset_class, None)
                    if security_type is None:
                        continue
                    try:
                        ret, frame = quote.get_stock_basicinfo(market, stock_type=security_type)
                    except TypeError:
                        ret, frame = quote.get_stock_basicinfo(market, security_type)
                    if ret != RET_OK or frame is None:
                        continue
                    for _, row in frame.iterrows():
                        code = str(row.get("code", "")).upper()
                        if not code or code in seen:
                            continue
                        seen.add(code)
                        result.append({
                            "provider_code": code,
                            "public_code": _public_from_code(code),
                            "name": str(row.get("name", _public_from_code(code))),
                            "market": _market_from_code(code),
                            "currency": "AUD" if market_name == "AU" else "HKD" if market_name == "HK" else "USD",
                            "metadata": {"asset_class": asset_class},
                        })
        finally:
            quote.close()
        if not result:
            raise MarketProviderError("MOOMOO_CATALOG_EMPTY")
        return result

    def snapshot(self, candidates: list[Candidate], now: datetime, include_history: bool) -> list[Candidate]:
        OpenQuoteContext, RET_OK, KLType, AuType, _, _ = self._sdk()
        quote = OpenQuoteContext(host=self.host, port=self.port)
        codes = [candidate.provider_code for candidate in candidates]
        try:
            ret, frame = quote.get_market_snapshot(codes)
            if ret != RET_OK or frame is None:
                raise MarketProviderError("MOOMOO_SNAPSHOT_FAILED")
            by_code = {str(row.get("code", "")).upper(): row for _, row in frame.iterrows()}
            result: list[Candidate] = []
            for candidate in candidates:
                row = by_code.get(candidate.provider_code.upper())
                if row is None:
                    continue
                price = float(row.get("last_price", 0.0) or 0.0)
                bid = float(row.get("bid_price", 0.0) or 0.0)
                ask = float(row.get("ask_price", 0.0) or 0.0)
                turnover = float(row.get("turnover", 0.0) or 0.0)
                spread_bps = ((ask - bid) / price * 10000.0) if price > 0 and ask >= bid > 0 else 7.0
                candidate.price = price or candidate.price
                _record_source_times(candidate, row, now)
                candidate.platform_verified = True
                candidate.liquidity_score = min(1.0, max(0.0, turnover / 10_000_000.0))
                candidate.cost_bps = max(5.0, spread_bps + 3.0)
                if include_history or not candidate.bars:
                    ret_h, history, _ = quote.request_history_kline(
                        candidate.provider_code,
                        ktype=KLType.K_DAY,
                        autype=AuType.QFQ,
                        max_count=140,
                    )
                    if ret_h == RET_OK and history is not None:
                        candidate.bars = [
                            {
                                "time": str(bar.get("time_key", ""))[:10],
                                "open": float(bar.get("open", 0.0) or 0.0),
                                "high": float(bar.get("high", 0.0) or 0.0),
                                "low": float(bar.get("low", 0.0) or 0.0),
                                "close": float(bar.get("close", 0.0) or 0.0),
                                "volume": float(bar.get("volume", 0.0) or 0.0),
                            }
                            for _, bar in history.iterrows()
                        ]
                result.append(candidate)
            if not result:
                raise MarketProviderError("MOOMOO_NO_CANDIDATE_SNAPSHOT")
            return result
        finally:
            quote.close()


def provider_for(name: str, fixture_dir: Path):
    if name == "fixture":
        return FixtureProvider(fixture_dir)
    if name == "moomoo":
        return MoomooReadOnlyProvider()
    raise MarketProviderError("UNSUPPORTED_MARKET_PROVIDER")
