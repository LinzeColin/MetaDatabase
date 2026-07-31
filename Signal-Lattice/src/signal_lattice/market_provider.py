from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings


class MarketProviderError(RuntimeError):
    pass


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_json(path: Path, max_bytes: int = 20_000_000) -> Any:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise MarketProviderError(f"INVALID_MARKET_INPUT:{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketProviderError(f"INVALID_MARKET_JSON:{path}") from exc


def load_universe(path: Path) -> list[dict[str, Any]]:
    raw = _read_json(path, 1_000_000)
    members = raw.get("universe") if isinstance(raw, dict) else raw
    if not isinstance(members, list) or not members:
        raise MarketProviderError("UNIVERSE_EMPTY")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in members:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        market = str(row.get("market", "")).strip().upper()
        if not symbol or not market or (symbol, market) in seen:
            continue
        seen.add((symbol, market))
        result.append({
            "symbol": symbol,
            "market": market,
            "active": bool(row.get("active", True)),
            "priority": int(row.get("priority", 100)),
            "source": str(row.get("source", "CONFIG")),
            "metadata": row.get("metadata", {}) if isinstance(row.get("metadata", {}), dict) else {},
        })
    result = [row for row in result if row["active"]]
    if not result:
        raise MarketProviderError("UNIVERSE_HAS_NO_ACTIVE_MEMBER")
    return sorted(result, key=lambda x: (x["priority"], x["market"], x["symbol"]))


def _merge_optional_evidence(settings: Settings, security: dict[str, Any]) -> dict[str, Any]:
    key = f"{security['market']}.{security['symbol']}"
    evidence_dir = settings.state_dir / "evidence" / "securities"
    path = evidence_dir / f"{key}.json"
    if path.is_file() and not path.is_symlink() and path.stat().st_size <= 2_000_000:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for field in ("fundamentals", "events", "portfolio"):
                    if field in data:
                        security[field] = data[field]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            security.setdefault("evidence_errors", []).append("OPTIONAL_EVIDENCE_INVALID")
    return security


class FixtureProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def snapshot(self, universe: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
        fixture_path = Path(os.environ.get(
            "SIGNAL_LATTICE_MARKET_FIXTURE",
            str(Path(__file__).resolve().parents[2] / "fixtures" / "northstar_market.json"),
        ))
        raw = _read_json(fixture_path)
        rows = raw.get("universe") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            raise MarketProviderError("MARKET_FIXTURE_UNIVERSE_MISSING")
        by_key = {(str(row.get("market", "")).upper(), str(row.get("symbol", "")).upper()): row for row in rows if isinstance(row, dict)}
        selected: list[dict[str, Any]] = []
        for member in universe:
            key = (member["market"], member["symbol"])
            row = by_key.get(key)
            if row is None:
                raise MarketProviderError(f"FIXTURE_SYMBOL_MISSING:{key[0]}:{key[1]}")
            value = {**row, "market": key[0], "symbol": key[1], **member.get("metadata", {})}
            value.setdefault("liquidity_score", 0.8)
            value.setdefault("cost_bps", 8.0)
            value.setdefault("daily_value_traded_usd", 50_000_000.0)
            value.setdefault("capacity_usd", 250_000.0)
            selected.append(_merge_optional_evidence(self.settings, value))
        timestamp = as_of.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        payload = {
            "schema_version": "1.0.0",
            "source": "SEALED_FIXTURE",
            "as_of": timestamp,
            "available_at": timestamp,
            "ingested_at": timestamp,
            "point_in_time_ok": True,
            "license_ok": True,
            "data_quality": 0.90,
            "production_eligible": False,
            "universe": selected,
        }
        payload["source_digest"] = canonical_sha256(payload)
        return payload


class MoomooProvider:
    """Quote-only adapter. It never opens a trade context or places an order."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.host = os.environ.get("MOOMOO_OPEND_HOST", "127.0.0.1")
        self.port = int(os.environ.get("MOOMOO_OPEND_PORT", "11111"))
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise MarketProviderError("MOOMOO_OPEND_MUST_BIND_LOOPBACK")

    @staticmethod
    def _code(member: dict[str, Any]) -> str:
        market = member["market"].upper()
        symbol = member["symbol"].upper()
        aliases = {"USA": "US", "NASDAQ": "US", "NYSE": "US", "HKG": "HK", "AUS": "AU"}
        prefix = aliases.get(market, market)
        return symbol if symbol.startswith(prefix + ".") else f"{prefix}.{symbol}"

    def snapshot(self, universe: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
        try:
            try:
                from moomoo import OpenQuoteContext, RET_OK, KLType, AuType  # type: ignore
            except ImportError:
                from futu import OpenQuoteContext, RET_OK, KLType, AuType  # type: ignore
        except ImportError as exc:
            raise MarketProviderError("MOOMOO_SDK_NOT_INSTALLED") from exc
        quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
        selected: list[dict[str, Any]] = []
        try:
            for member in universe:
                code = self._code(member)
                ret, snapshot_df = quote_ctx.get_market_snapshot([code])
                if ret != RET_OK or snapshot_df is None or len(snapshot_df.index) != 1:
                    raise MarketProviderError(f"MOOMOO_SNAPSHOT_FAILED:{code}:{ret}")
                row = snapshot_df.iloc[0]
                ret, kline_df, _ = quote_ctx.request_history_kline(
                    code,
                    ktype=KLType.K_DAY,
                    autype=AuType.QFQ,
                    max_count=120,
                )
                if ret != RET_OK or kline_df is None or len(kline_df.index) < 25:
                    raise MarketProviderError(f"MOOMOO_HISTORY_FAILED:{code}:{ret}")
                bars = []
                for _, bar in kline_df.iterrows():
                    bars.append({
                        "time": str(bar.get("time_key", "")),
                        "open": float(bar.get("open", 0.0)),
                        "high": float(bar.get("high", 0.0)),
                        "low": float(bar.get("low", 0.0)),
                        "close": float(bar.get("close", 0.0)),
                        "volume": float(bar.get("volume", 0.0)),
                        "turnover": float(bar.get("turnover", 0.0)),
                    })
                price = float(row.get("last_price", bars[-1]["close"]))
                daily_turnover = float(row.get("turnover", bars[-1].get("turnover", 0.0)))
                spread = 0.0
                bid = float(row.get("bid_price", 0.0) or 0.0)
                ask = float(row.get("ask_price", 0.0) or 0.0)
                if bid > 0 and ask >= bid:
                    spread = (ask - bid) / max(price, 1e-9) * 10_000
                liquidity_score = min(1.0, max(0.0, daily_turnover / 10_000_000.0))
                security = {
                    "symbol": member["symbol"],
                    "market": member["market"],
                    "code": code,
                    "price": price,
                    "currency": str(row.get("currency", member.get("metadata", {}).get("currency", "USD"))),
                    "bars": bars,
                    "daily_value_traded_usd": daily_turnover,
                    "capacity_usd": max(0.0, daily_turnover * 0.001),
                    "liquidity_score": liquidity_score,
                    "cost_bps": max(5.0, spread + 3.0),
                    **member.get("metadata", {}),
                }
                selected.append(_merge_optional_evidence(self.settings, security))
        finally:
            quote_ctx.close()
        timestamp = as_of.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        payload = {
            "schema_version": "1.0.0",
            "source": "MOOMOO_OPEND_QUOTE_ONLY",
            "as_of": timestamp,
            "available_at": timestamp,
            "ingested_at": timestamp,
            "point_in_time_ok": True,
            "license_ok": os.environ.get("SIGNAL_LATTICE_MARKET_LICENSE_CONFIRMED", "0") == "1",
            "data_quality": 0.90,
            "production_eligible": True,
            "universe": selected,
        }
        payload["source_digest"] = canonical_sha256(payload)
        return payload


def provider_for(settings: Settings):
    if settings.market_provider == "fixture":
        return FixtureProvider(settings)
    if settings.market_provider == "moomoo":
        return MoomooProvider(settings)
    raise MarketProviderError("UNSUPPORTED_MARKET_PROVIDER")
