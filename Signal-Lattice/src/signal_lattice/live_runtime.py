"""V2 真实数据循环与硬编码诚实门。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from .live_config import APP_VERSION, LiveSettings
from .marketdata import DiskCache, EastMoneyFundProvider, HttpClient, MarketDataError, SinaKlineProvider, SinaQuoteProvider, TencentKlineProvider, TencentQuoteProvider
from .marketdata.models import Bar, Instrument, Quote


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


class LiveStore:
    """只保存最新状态；仅市场内容变化时追加决策历史，避免重复观测膨胀。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "history").mkdir(exist_ok=True)

    @property
    def latest_path(self) -> Path:
        return self.root / "latest.json"

    def latest(self) -> dict:
        if not self.latest_path.is_file():
            return {}
        try:
            value = json.loads(self.latest_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def save(self, report: dict) -> None:
        previous = self.latest()
        temporary = self.root / ".latest.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.latest_path)
        current_market = report.get("market_fingerprint")
        if current_market and current_market != previous.get("market_fingerprint"):
            with (self.root / "history" / "market_changes.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")


class MarketGateway:
    def __init__(self, settings: LiveSettings) -> None:
        client = HttpClient()
        cache = DiskCache(settings.state_dir / "cache")
        self.sina = SinaQuoteProvider(client, settings.sina_quote_url)
        self.tencent_quote = TencentQuoteProvider(client, settings.tencent_quote_url)
        self.sina_bars = SinaKlineProvider(client, cache, settings.sina_us_kline_url, settings.sina_cn_kline_url)
        self.tencent_bars = TencentKlineProvider(client, cache, settings.tencent_kline_url)
        self.fund_bars = EastMoneyFundProvider(client, cache, settings.eastmoney_fund_url)

    def fetch(self, instruments: List[Instrument]) -> Tuple[Dict[str, Quote], Dict[str, List[Bar]], List[str]]:
        errors: List[str] = []
        quotes: Dict[str, Quote] = {}
        realtime = [item for item in instruments if item.realtime_quote]
        try:
            quotes.update(self.sina.fetch(realtime))
        except MarketDataError as exc:
            errors.append("SINA_QUOTE:%s" % exc)
        cn_hk_missing = [item for item in realtime if item.market in {"CN", "HK"} and item.symbol not in quotes]
        if cn_hk_missing:
            try:
                quotes.update(self.tencent_quote.fetch(cn_hk_missing))
            except MarketDataError as exc:
                errors.append("TENCENT_QUOTE:%s" % exc)
        bars: Dict[str, List[Bar]] = {}
        for item in instruments:
            try:
                if item.asset_type == "MUTUAL_FUND":
                    bars[item.symbol] = self.fund_bars.fetch(item)
                elif item.market in {"US", "CN"}:
                    try:
                        bars[item.symbol] = self.sina_bars.fetch(item)
                    except MarketDataError:
                        if item.market != "CN":
                            raise
                        bars[item.symbol] = self.tencent_bars.fetch(item)
                else:
                    bars[item.symbol] = self.tencent_bars.fetch(item)
            except MarketDataError as exc:
                errors.append("BARS_%s:%s" % (item.symbol, exc))
        return quotes, bars, errors


class LiveEngine:
    def __init__(self, settings: LiveSettings) -> None:
        self.settings = settings
        self.store = LiveStore(settings.state_dir)
        self.gateway = MarketGateway(settings)

    def _validate(self, now: datetime, quotes: Dict[str, Quote], bars: Dict[str, List[Bar]], errors: List[str]) -> List[str]:
        findings = list(errors)
        for item in self.settings.universe:
            if item.realtime_quote:
                quote = quotes.get(item.symbol)
                if quote is None:
                    findings.append("QUOTE_MISSING:%s" % item.symbol)
                elif (now - quote.observed_at).total_seconds() > self.settings.quote_max_age_seconds:
                    findings.append("QUOTE_STALE:%s" % item.symbol)
                elif quote.source_time and quote.source_time.date() < (now.date() - timedelta(days=self.settings.bar_max_age_days)):
                    findings.append("QUOTE_SOURCE_STALE:%s" % item.symbol)
            series = bars.get(item.symbol)
            if not series:
                findings.append("BAR_MISSING:%s" % item.symbol)
                continue
            latest = series[-1].day
            if latest < now.date() - timedelta(days=self.settings.bar_max_age_days):
                findings.append("BAR_STALE:%s:%s" % (item.symbol, latest.isoformat()))
        return findings

    @staticmethod
    def _market_fingerprint(quotes: Dict[str, Quote], bars: Dict[str, List[Bar]]) -> dict:
        return {
            "quotes": {symbol: round(item.price, 8) for symbol, item in sorted(quotes.items())},
            "bars": {symbol: series[-1].day.isoformat() for symbol, series in sorted(bars.items()) if series},
        }

    def run_once(self) -> dict:
        now = datetime.now(timezone.utc)
        quotes, bars, errors = self.gateway.fetch(self.settings.universe)
        findings = self._validate(now, quotes, bars, errors)
        cutoffs = {symbol: series[-1].day.isoformat() for symbol, series in bars.items() if series}
        quote_observed_at = min((quote.observed_at for quote in quotes.values()), default=None)
        state = "SYSTEM_BLOCKED" if findings else "DATA_READY"
        report = {
            "application_version": APP_VERSION,
            "generated_at": _iso(now),
            "state": state,
            "automatic_trading": False,
            "data_cutoff": min(cutoffs.values()) if cutoffs else None,
            "data_cutoff_by_symbol": cutoffs,
            "quote_observed_at": _iso(quote_observed_at) if quote_observed_at else None,
            "quote_sources": {symbol: quote.source for symbol, quote in sorted(quotes.items())},
            "quotes": {symbol: {"price": quote.price, "currency": quote.currency, "source_time": quote.source_time.isoformat() if quote.source_time else None} for symbol, quote in sorted(quotes.items())},
            "market_fingerprint": self._market_fingerprint(quotes, bars),
            "freshness_findings": findings,
            "message": "数据链路不完整，不出结论" if findings else "真实数据已就绪，等待分支计算",
            "decision": {"state": "SYSTEM_BLOCKED", "action": None} if findings else {"state": "PENDING_BRANCH_CALCULATION", "action": None},
            "branches": [],
            "weight_mode": "COLD_START_EQUAL",
            "profitability_status": "SAMPLE_INSUFFICIENT",
        }
        self.store.save(report)
        return report
