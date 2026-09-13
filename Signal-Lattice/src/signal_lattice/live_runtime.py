"""V2 真实数据循环与硬编码诚实门。"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from .aggregate import blocked_aggregate_report
from .backtest import run_backtest
from .branches import build_branch_report
from .live_config import APP_VERSION, LiveSettings
from .marketdata import DiskCache, EastMoneyFundProvider, HttpClient, MarketDataError, SinaKlineProvider, SinaQuoteProvider, TencentKlineProvider, TencentQuoteProvider
from .marketdata.models import Bar, Instrument, Quote
from .serialization import JsonSerializationConstraintError, strict_json_dumps


# 默认 60 秒循环在一个完整美股交易月最多产生约 390 × 21 = 8,190 次候选变化。
# 历史只保留紧凑报价/决策变更：每天 240 条且 64 KiB，31 天运行期占用最多
# 31 × 64 KiB = 1.94 MiB；历史不再随循环次数无界增长。
HISTORY_RETENTION_DAYS = 31
HISTORY_MAX_RECORDS_PER_DAY = 240
HISTORY_MAX_BYTES_PER_DAY = 64 * 1024
# 系统与持久化状态的正常时钟微偏移可在一个请求/写盘窗口内出现；60 秒已经覆盖
# 该偏移，却远小于默认 270 秒就绪 TTL。超出它的时间戳不能作为实时性证据。
MAX_FUTURE_CLOCK_SKEW_SECONDS = 60


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def apply_profitability_disclosure(branch_report: dict, backtest: dict) -> None:
    """收益证据不足时保留方向性研究结论，并在决策层显式标记其边界。"""
    branch_report["sample_sufficiency"] = backtest.get("sample_sufficiency")
    branch_report["sample_sufficiency_message"] = backtest.get("sample_sufficiency_message")
    if str(backtest.get("sample_sufficiency", "")).startswith("OOS_HISTORY_INSUFFICIENT:"):
        branch_report["decision"]["sample_sufficiency"] = backtest["sample_sufficiency"]
        branch_report["decision"]["sample_sufficiency_message"] = backtest["sample_sufficiency_message"]


class LiveStore:
    """保存最新报告、循环心跳和有界的紧凑市场变更历史。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "history").mkdir(exist_ok=True)

    @property
    def latest_path(self) -> Path:
        return self.root / "latest.json"

    @property
    def heartbeat_path(self) -> Path:
        return self.root / "heartbeat.json"

    @property
    def history_dir(self) -> Path:
        return self.root / "history"

    def latest(self) -> dict:
        if not self.latest_path.is_file():
            return {}
        try:
            value = json.loads(self.latest_path.read_text(encoding="utf-8"))
            strict_json_dumps(value)
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, JsonSerializationConstraintError):
            return {}

    def heartbeat(self) -> dict:
        if not self.heartbeat_path.is_file():
            return {}
        try:
            value = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
            strict_json_dumps(value)
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, JsonSerializationConstraintError):
            return {}

    def write_heartbeat(self, observed_at: datetime) -> None:
        self._write_json(self.heartbeat_path, {"observed_at": _iso(observed_at)})

    def liveness(self, *, max_age_seconds: int, now: datetime | None = None) -> dict:
        """同时要求最新报告和循环心跳处于同一明确时效窗口内。"""
        checked_at = now or datetime.now(timezone.utc)
        latest = self.latest()
        heartbeat = self.heartbeat()
        generated_at = self._parse_timestamp(latest.get("generated_at"))
        observed_at = self._parse_timestamp(heartbeat.get("observed_at"))
        stale_parts = []
        if generated_at is None:
            stale_parts.append("REPORT_STALE")
        else:
            report_age = (checked_at - generated_at).total_seconds()
            if report_age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
                stale_parts.append("REPORT_CLOCK_AHEAD")
            elif report_age > max_age_seconds:
                stale_parts.append("REPORT_STALE")
        if observed_at is None:
            stale_parts.append("HEARTBEAT_STALE")
        else:
            heartbeat_age = (checked_at - observed_at).total_seconds()
            if heartbeat_age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
                stale_parts.append("HEARTBEAT_CLOCK_AHEAD")
            elif heartbeat_age > max_age_seconds:
                stale_parts.append("HEARTBEAT_STALE")
        return {
            "latest": latest,
            "fresh": bool(latest) and not stale_parts,
            "reason": ",".join(stale_parts) if stale_parts else None,
            "generated_at": _iso(generated_at) if generated_at else None,
            "heartbeat_at": _iso(observed_at) if observed_at else None,
            "max_age_seconds": max_age_seconds,
        }

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None

    def _write_json(self, path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            strict_json_dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _history_path(self, observed_at: datetime) -> Path:
        return self.history_dir / f"market_changes-{observed_at.astimezone(timezone.utc).date().isoformat()}.jsonl"

    def _history_files(self) -> list[Path]:
        return sorted(self.history_dir.glob("market_changes-????-??-??.jsonl"))

    def _prune_history(self, observed_at: datetime) -> None:
        legacy = self.history_dir / "market_changes.jsonl"
        if legacy.is_file():
            legacy.unlink()
        oldest_kept = observed_at.astimezone(timezone.utc).date() - timedelta(days=HISTORY_RETENTION_DAYS - 1)
        for path in self._history_files():
            day = datetime.strptime(path.stem.removeprefix("market_changes-"), "%Y-%m-%d").date()
            if day < oldest_kept:
                path.unlink()

    @staticmethod
    def _compact_market_change(report: dict, previous: dict) -> dict:
        current = report.get("market_fingerprint", {})
        old = previous.get("market_fingerprint", {})
        current_quotes = current.get("quotes", {}) if isinstance(current, dict) else {}
        old_quotes = old.get("quotes", {}) if isinstance(old, dict) else {}
        current_bars = current.get("bars", {}) if isinstance(current, dict) else {}
        old_bars = old.get("bars", {}) if isinstance(old, dict) else {}
        quote_changes = [
            {"symbol": symbol, "price": price, "previous_price": old_quotes.get(symbol)}
            for symbol, price in sorted(current_quotes.items())
            if old_quotes.get(symbol) != price
        ]
        bar_changes = [
            {"symbol": symbol, "latest_day": day, "previous_day": old_bars.get(symbol)}
            for symbol, day in sorted(current_bars.items())
            if old_bars.get(symbol) != day
        ]
        decision = report.get("decision", {})
        return {
            "generated_at": report.get("generated_at"),
            "state": report.get("state"),
            "decision": {
                key: decision.get(key)
                for key in ("state", "action", "primary_symbol", "conviction")
                if key in decision
            },
            "market_delta": {"quotes": quote_changes, "bars": bar_changes},
        }

    def _trim_history_day(self, path: Path) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()
        while lines and (
            len(lines) > HISTORY_MAX_RECORDS_PER_DAY
            or len(("\n".join(lines) + "\n").encode("utf-8")) > HISTORY_MAX_BYTES_PER_DAY
        ):
            lines.pop(0)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        os.replace(temporary, path)

    def history_storage(self) -> dict:
        files = self._history_files()
        return {
            "storage": "state_dir/history/market_changes-YYYY-MM-DD.jsonl",
            "retention_days": HISTORY_RETENTION_DAYS,
            "max_records_per_day": HISTORY_MAX_RECORDS_PER_DAY,
            "max_bytes_per_day": HISTORY_MAX_BYTES_PER_DAY,
            "max_total_bytes": HISTORY_RETENTION_DAYS * HISTORY_MAX_BYTES_PER_DAY,
            "file_count": len(files),
            "record_count": sum(len(path.read_text(encoding="utf-8").splitlines()) for path in files),
            "bytes_used": sum(path.stat().st_size for path in files),
        }

    def _append_market_change(self, report: dict, previous: dict) -> dict:
        observed_at = self._parse_timestamp(report.get("generated_at")) or datetime.now(timezone.utc)
        path = self._history_path(observed_at)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(strict_json_dumps(self._compact_market_change(report, previous), ensure_ascii=False, separators=(",", ":")) + "\n")
        self._trim_history_day(path)
        return self.history_storage()

    def save(self, report: dict) -> None:
        previous = self.latest()
        observed_at = self._parse_timestamp(report.get("generated_at")) or datetime.now(timezone.utc)
        self._prune_history(observed_at)
        current_market = report.get("market_fingerprint")
        if current_market and current_market != previous.get("market_fingerprint"):
            report["history_storage"] = self._append_market_change(report, previous)
        else:
            report["history_storage"] = self.history_storage()
        self._write_json(self.latest_path, report)


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
                elif not math.isfinite(quote.price):
                    findings.append("QUOTE_NONFINITE:%s" % item.symbol)
                else:
                    quote_age = (now - quote.observed_at).total_seconds()
                    if quote_age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
                        findings.append("QUOTE_CLOCK_AHEAD:%s" % item.symbol)
                    elif quote_age > self.settings.quote_max_age_seconds:
                        findings.append("QUOTE_STALE:%s" % item.symbol)
                    if quote.source_time and quote.source_time.date() < (now.date() - timedelta(days=self.settings.bar_max_age_days)):
                        findings.append("QUOTE_SOURCE_STALE:%s" % item.symbol)
            series = bars.get(item.symbol)
            if not series:
                findings.append("BAR_MISSING:%s" % item.symbol)
                continue
            if any(not bar.has_finite_ohlcv() for bar in series):
                findings.append("BAR_NONFINITE:%s" % item.symbol)
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

    def _serialization_blocked_report(self, now: datetime, findings: List[str]) -> dict:
        """严格 JSON 边界发现非有限数值时，保留阻断事实而不写出坏报告。"""
        return {
            "application_version": APP_VERSION,
            "generated_at": _iso(now),
            "state": "SYSTEM_BLOCKED",
            "automatic_trading": False,
            "data_cutoff": None,
            "data_cutoff_by_symbol": {},
            "instruments": {
                item.symbol: {"name": item.name, "market": item.market, "asset_type": item.asset_type}
                for item in self.settings.universe
            },
            "bar_sources": {},
            "quote_observed_at": None,
            "quote_sources": {},
            "quotes": {},
            "market_fingerprint": {"quotes": {}, "bars": {}},
            "freshness_findings": [*findings, "SERIALIZATION_NONFINITE_VALUE"],
            "message": "报告包含非有限数值，已阻断结论。",
            "backtest": {
                "status": "SYSTEM_BLOCKED",
                "message": "报告包含非有限数值，未运行或发布回测结论。",
                "profitability_status": "SYSTEM_BLOCKED",
            },
            **blocked_aggregate_report(),
        }

    def _runtime_failure_blocked_report(self, now: datetime, exc: Exception) -> dict:
        """任何未预期运行期异常都用新报告覆盖旧的就绪结论。"""
        failure_type = type(exc).__name__
        return {
            "application_version": APP_VERSION,
            "generated_at": _iso(now),
            "state": "SYSTEM_BLOCKED",
            "blocked_reason": "UNEXPECTED_RUNTIME_FAILURE",
            "runtime_failure_type": failure_type,
            "automatic_trading": False,
            "data_cutoff": None,
            "data_cutoff_by_symbol": {},
            "instruments": {
                item.symbol: {"name": item.name, "market": item.market, "asset_type": item.asset_type}
                for item in self.settings.universe
            },
            "bar_sources": {},
            "quote_observed_at": None,
            "quote_sources": {},
            "quotes": {},
            "market_fingerprint": {"quotes": {}, "bars": {}},
            "freshness_findings": [f"UNEXPECTED_RUNTIME_FAILURE:{failure_type}"],
            "message": "采集或计算发生未预期运行期异常，已阻断结论。",
            "backtest": {
                "status": "SYSTEM_BLOCKED",
                "message": "运行期异常，未发布回测结论。",
                "profitability_status": "SYSTEM_BLOCKED",
            },
            **blocked_aggregate_report(),
        }

    def run_once(self) -> dict:
        now = datetime.now(timezone.utc)
        try:
            self.store.write_heartbeat(now)
            quotes, bars, errors = self.gateway.fetch(self.settings.universe)
            findings = self._validate(now, quotes, bars, errors)
            reportable_quotes = {
                symbol: quote for symbol, quote in quotes.items() if math.isfinite(quote.price)
            }
            cutoffs = {symbol: series[-1].day.isoformat() for symbol, series in bars.items() if series}
            bar_sources = {
                symbol: {
                    "source": series[-1].source,
                    "bar_count": len(series),
                    "earliest_day": series[0].day.isoformat(),
                    "latest_day": series[-1].day.isoformat(),
                }
                for symbol, series in sorted(bars.items())
                if series
            }
            quote_observed_at = min((quote.observed_at for quote in reportable_quotes.values()), default=None)
            state = "SYSTEM_BLOCKED" if findings else "DATA_READY"
            if state == "DATA_READY":
                backtest = run_backtest(self.settings.universe, bars, state_dir=self.settings.state_dir)
                branch_report = build_branch_report(
                    self.settings.universe,
                    bars,
                    backtest,
                    state_dir=self.settings.state_dir,
                )
                apply_profitability_disclosure(branch_report, backtest)
            else:
                backtest = {
                    "status": "SYSTEM_BLOCKED",
                    "message": "数据不新鲜或数据链路不完整，未运行回测。",
                    "profitability_status": "SYSTEM_BLOCKED",
                }
                branch_report = {
                    "branches": [],
                    "profitability_status": "SYSTEM_BLOCKED",
                    **blocked_aggregate_report(),
                }
            report = {
                "application_version": APP_VERSION,
                "generated_at": _iso(now),
                "state": state,
                "automatic_trading": False,
                "data_cutoff": min(cutoffs.values()) if cutoffs else None,
                "data_cutoff_by_symbol": cutoffs,
                "instruments": {
                    item.symbol: {"name": item.name, "market": item.market, "asset_type": item.asset_type}
                    for item in self.settings.universe
                },
                "bar_sources": bar_sources,
                "quote_observed_at": _iso(quote_observed_at) if quote_observed_at else None,
                "quote_sources": {symbol: quote.source for symbol, quote in sorted(reportable_quotes.items())},
                "quotes": {symbol: {"price": quote.price, "currency": quote.currency, "source_time": quote.source_time.isoformat() if quote.source_time else None} for symbol, quote in sorted(reportable_quotes.items())},
                "market_fingerprint": self._market_fingerprint(reportable_quotes, bars),
                "freshness_findings": findings,
                "message": "数据链路不完整，不出结论" if findings else "真实数据已就绪，已完成独立分支计算",
                "backtest": backtest,
                **branch_report,
            }
            self.store.save(report)
        except JsonSerializationConstraintError:
            report = self._serialization_blocked_report(now, findings)
            self.store.save(report)
        except Exception as exc:
            report = self._runtime_failure_blocked_report(now, exc)
            self.store.save(report)
        return report
