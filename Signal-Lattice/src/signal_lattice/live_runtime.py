"""V2 真实数据循环与硬编码诚实门。"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Tuple
from zoneinfo import ZoneInfo

from .aggregate import blocked_aggregate_report
from .backtest import run_backtest
from .backtest.pipeline import walk_forward_windows
from .backtest.runner import MIN_COMPLETE_WINDOWS
from .branches import build_branch_report
from .live_config import APP_VERSION, LiveSettings
from .marketdata import CollectionBudgetExceeded, DiskCache, EastMoneyFundProvider, HttpClient, MarketDataError, SinaKlineProvider, SinaQuoteProvider, TencentKlineProvider, TencentQuoteProvider
from .marketdata.models import Bar, BarQualityIssue, Instrument, Quote
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
# S1 的最长价格回看是 r252；任一异常落在这 252 个交易日内会影响当前决策，必须阻断。
RECENT_DECISION_BAR_LOOKBACK_TRADING_DAYS = 252
# 三条以内且占输入日线不超过 0.5% 才符合“孤立历史坏点”定义；任一上限越界说明
# 上游质量已经不是可审计的个例，不能继续使用该标的。
MAX_DROPPED_INVALID_BARS_PER_SYMBOL = 3
MAX_DROPPED_INVALID_BAR_RATIO = 0.005
MAX_REPORTED_INVALID_BAR_SAMPLES = 5
# 质量拒绝行沿用既有最近一个决策交易月的审计窗口；该窗口与历史可用段裁剪分开。
RECENT_QUALITY_ISSUE_WINDOW_TRADING_DAYS = RECENT_DECISION_BAR_LOOKBACK_TRADING_DAYS // 12
# 连续性决定可用历史段，而不是整段历史的通过资格。2026-09-14 实测：QQQ 在
# 2004-12-31 至 2011-04-26 之间缺 1,646 个工作日，AAPL 在 2004-12-31 至
# 2007-03-19 之间缺 575 个工作日；两者 2016 年后均为 2,688 条、最大缺口 4 天。
# SPY 的 2001-09-10 至 2001-09-17 缺口是 911 停市，缺 4 个工作日；sh600000 的
# 18 个工作日缺口是个股停牌。阈值 10 覆盖春节 6 天、短期停牌和 911 停市，遇到更长
# 缺口时从最新端裁剪到该缺口之后的连续可用段，保证回测与指标不会跨越断档。
MAX_USABLE_GAP_BUSINESS_DAYS = 10
# 不接入交易日历时，4 个自然日覆盖周五收盘至周二开市前的周末/单日假期；更长停市
# 必须等待可验证的新来源时间，不能把停市近似无限延长。
CLOSED_MARKET_SOURCE_MAX_AGE_DAYS = 4
# 2026-09-14 港股开市后 8 个每 90 秒采样里，来源时间最长连续约 6 分钟未变，随后继续
# 推进。取其两倍为 12 分钟：覆盖正常分块更新，又在绝对时延仍合格时识别真正卡住的源。
QUOTE_ADVANCE_STALL_MINUTES = 12
# 预算按实际发起的 HTTP 请求计数，重试也会逐次计入。正常上限是每分钟 1 次报价批量请求
# 加每 6 小时 15 次日线刷新，即 1,500 次/日；1,600 次/日只为来源切换和有限重试留余量。
MAX_PROVIDER_REQUESTS_PER_ROUND = 48
MAX_PROVIDER_REQUESTS_PER_DAY = 1_600
COLLECTION_FAILURES_BEFORE_BACKOFF = 3
COLLECTION_BACKOFF_INITIAL_SECONDS = 60
COLLECTION_BACKOFF_MAX_SECONDS = 60 * 60
MARKET_OPEN_SESSIONS = {
    "US": ((time(9, 30), time(16, 0)),),
    "CN": ((time(9, 30), time(11, 30)), (time(13, 0), time(15, 0))),
    "HK": ((time(9, 30), time(12, 0)), (time(13, 0), time(16, 0))),
}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _market_is_open(instrument: Instrument, exchange_now: datetime) -> bool:
    """按交易所当地时区和常规时段判断；法定假日由休市的有限自然日近似处理。"""
    if exchange_now.weekday() >= 5:
        return False
    return any(start <= exchange_now.time() < end for start, end in MARKET_OPEN_SESSIONS.get(instrument.market, ()))


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

    @property
    def quote_progress_path(self) -> Path:
        """每个标的最后一次来源时间推进的私有运行时状态。"""
        return self.root / "quote_progress.json"

    @property
    def collection_accounting_path(self) -> Path:
        """采集请求的逐 provider、逐日与累计账本。"""
        return self.root / "collection_accounting.json"

    @staticmethod
    def _new_collection_accounting(now: datetime) -> dict:
        return {
            "schema_version": "1.0.0",
            "accounting_day": now.astimezone(timezone.utc).date().isoformat(),
            "total_round_count": 0,
            "daily_round_count": 0,
            "total_provider_request_count": 0,
            "daily_provider_request_count": 0,
            "active_round_request_count": 0,
            "provider_request_counts": {},
            "consecutive_failure_count": 0,
            "next_attempt_at": None,
            "status": "READY",
            "stop_reason": None,
        }

    def _load_collection_accounting(self, now: datetime) -> dict:
        if not self.collection_accounting_path.is_file():
            return self._new_collection_accounting(now)
        try:
            control = json.loads(self.collection_accounting_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectionBudgetExceeded("COLLECTION_ACCOUNTING_STATE_INVALID") from exc
        required_counts = (
            "total_round_count",
            "daily_round_count",
            "total_provider_request_count",
            "daily_provider_request_count",
            "active_round_request_count",
            "consecutive_failure_count",
        )
        if (
            not isinstance(control, dict)
            or control.get("schema_version") != "1.0.0"
            or not isinstance(control.get("provider_request_counts"), dict)
            or any(not isinstance(control.get(key), int) or control[key] < 0 for key in required_counts)
        ):
            raise CollectionBudgetExceeded("COLLECTION_ACCOUNTING_STATE_INVALID")
        today = now.astimezone(timezone.utc).date().isoformat()
        if control.get("accounting_day") != today:
            control["accounting_day"] = today
            control["daily_round_count"] = 0
            control["daily_provider_request_count"] = 0
            control["active_round_request_count"] = 0
            control["consecutive_failure_count"] = 0
            control["next_attempt_at"] = None
            control["status"] = "READY"
            control["stop_reason"] = None
            for counts in control["provider_request_counts"].values():
                if not isinstance(counts, dict) or not isinstance(counts.get("total"), int) or counts["total"] < 0:
                    raise CollectionBudgetExceeded("COLLECTION_ACCOUNTING_STATE_INVALID")
                counts["daily"] = 0
        return control

    def _save_collection_accounting(self, control: dict, now: datetime) -> None:
        control["updated_at"] = _iso(now)
        self._write_json(self.collection_accounting_path, control)

    def begin_collection_round(self, now: datetime) -> dict:
        """在任何 provider 请求前检查每日预算与失败退避，并落盘本轮起点。"""
        control = self._load_collection_accounting(now)
        next_attempt_at = self._parse_timestamp(control.get("next_attempt_at"))
        if next_attempt_at is not None and now < next_attempt_at:
            control["status"] = "BACKING_OFF"
            control["stop_reason"] = "CONSECUTIVE_COLLECTION_FAILURES"
            self._save_collection_accounting(control, now)
            return {"allowed": False, "reason": "COLLECTION_BACKING_OFF", "accounting": control}
        if control["daily_provider_request_count"] >= MAX_PROVIDER_REQUESTS_PER_DAY:
            next_day = datetime.combine(
                now.astimezone(timezone.utc).date() + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
            control["status"] = "DAILY_REQUEST_BUDGET_EXHAUSTED"
            control["stop_reason"] = "DAILY_PROVIDER_REQUEST_BUDGET"
            control["next_attempt_at"] = _iso(next_day)
            self._save_collection_accounting(control, now)
            return {"allowed": False, "reason": "COLLECTION_DAILY_BUDGET_EXHAUSTED", "accounting": control}
        control["total_round_count"] += 1
        control["daily_round_count"] += 1
        control["active_round_request_count"] = 0
        control["status"] = "COLLECTING"
        control["stop_reason"] = None
        self._save_collection_accounting(control, now)
        return {"allowed": True, "reason": None, "accounting": control}

    def record_provider_request(self, provider: str, now: datetime | None = None) -> None:
        """在每一次真实 HTTP 请求发出前计数；超限请求不会离开本机。"""
        now = now or datetime.now(timezone.utc)
        control = self._load_collection_accounting(now)
        if control.get("status") != "COLLECTING":
            raise CollectionBudgetExceeded("COLLECTION_ROUND_NOT_ACTIVE")
        if control["active_round_request_count"] >= MAX_PROVIDER_REQUESTS_PER_ROUND:
            control["status"] = "ROUND_REQUEST_BUDGET_EXHAUSTED"
            control["stop_reason"] = "ROUND_PROVIDER_REQUEST_BUDGET"
            self._save_collection_accounting(control, now)
            raise CollectionBudgetExceeded("COLLECTION_ROUND_REQUEST_BUDGET_EXHAUSTED")
        if control["daily_provider_request_count"] >= MAX_PROVIDER_REQUESTS_PER_DAY:
            control["status"] = "DAILY_REQUEST_BUDGET_EXHAUSTED"
            control["stop_reason"] = "DAILY_PROVIDER_REQUEST_BUDGET"
            self._save_collection_accounting(control, now)
            raise CollectionBudgetExceeded("COLLECTION_DAILY_REQUEST_BUDGET_EXHAUSTED")
        counts = control["provider_request_counts"].setdefault(provider, {"total": 0, "daily": 0})
        if (
            not isinstance(counts, dict)
            or not isinstance(counts.get("total"), int)
            or not isinstance(counts.get("daily"), int)
            or counts["total"] < 0
            or counts["daily"] < 0
        ):
            raise CollectionBudgetExceeded("COLLECTION_ACCOUNTING_STATE_INVALID")
        control["active_round_request_count"] += 1
        control["total_provider_request_count"] += 1
        control["daily_provider_request_count"] += 1
        counts["total"] += 1
        counts["daily"] += 1
        self._save_collection_accounting(control, now)

    def finish_collection_round(self, now: datetime, *, succeeded: bool) -> dict:
        """记录本轮结果；连续失败从第三次起按指数退避，成功立即清零。"""
        control = self._load_collection_accounting(now)
        control["active_round_request_count"] = 0
        if control.get("status") in {"ROUND_REQUEST_BUDGET_EXHAUSTED", "DAILY_REQUEST_BUDGET_EXHAUSTED"}:
            self._save_collection_accounting(control, now)
            return control
        if succeeded:
            control["consecutive_failure_count"] = 0
            control["next_attempt_at"] = None
            control["status"] = "READY"
            control["stop_reason"] = None
        else:
            control["consecutive_failure_count"] += 1
            failures = control["consecutive_failure_count"]
            if failures >= COLLECTION_FAILURES_BEFORE_BACKOFF:
                delay_seconds = min(
                    COLLECTION_BACKOFF_INITIAL_SECONDS * 2 ** (failures - COLLECTION_FAILURES_BEFORE_BACKOFF),
                    COLLECTION_BACKOFF_MAX_SECONDS,
                )
                control["next_attempt_at"] = _iso(now + timedelta(seconds=delay_seconds))
                control["status"] = "BACKING_OFF"
                control["stop_reason"] = "CONSECUTIVE_COLLECTION_FAILURES"
            else:
                control["next_attempt_at"] = None
                control["status"] = "READY"
                control["stop_reason"] = None
        self._save_collection_accounting(control, now)
        return control

    def collection_accounting(self, now: datetime) -> dict:
        """向报告暴露预算、退避和逐 provider 的实际请求账本。"""
        control = self._load_collection_accounting(now)
        return {
            "accounting_day": control["accounting_day"],
            "status": control["status"],
            "stop_reason": control["stop_reason"],
            "next_attempt_at": control["next_attempt_at"],
            "total_round_count": control["total_round_count"],
            "daily_round_count": control["daily_round_count"],
            "active_round_request_count": control["active_round_request_count"],
            "total_provider_request_count": control["total_provider_request_count"],
            "daily_provider_request_count": control["daily_provider_request_count"],
            "provider_request_counts": control["provider_request_counts"],
            "consecutive_failure_count": control["consecutive_failure_count"],
            "maximum_provider_requests_per_round": MAX_PROVIDER_REQUESTS_PER_ROUND,
            "maximum_provider_requests_per_day": MAX_PROVIDER_REQUESTS_PER_DAY,
            "failure_backoff_threshold": COLLECTION_FAILURES_BEFORE_BACKOFF,
            "backoff_initial_seconds": COLLECTION_BACKOFF_INITIAL_SECONDS,
            "backoff_max_seconds": COLLECTION_BACKOFF_MAX_SECONDS,
        }

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

    def _quote_progress_entries(self) -> dict[str, dict]:
        if not self.quote_progress_path.is_file():
            return {}
        try:
            value = json.loads(self.quote_progress_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {
            symbol: entry
            for symbol, entry in value.items()
            if isinstance(symbol, str) and isinstance(entry, dict)
        }

    def quote_progress(self, symbol: str) -> dict:
        """读取标的的最近推进事实；该状态只属于 state_dir，不进入代码仓。"""
        entry = self._quote_progress_entries().get(symbol, {})
        last_advance_at = self._parse_timestamp(entry.get("last_advance_at"))
        last_source_time = self._parse_timestamp(entry.get("last_source_time"))
        return {
            "last_advance_at": _iso(last_advance_at) if last_advance_at else None,
            "last_source_time": _iso(last_source_time) if last_source_time else None,
        }

    def record_quote_source_progress(
        self,
        symbol: str,
        source_at: datetime,
        observed_at: datetime,
    ) -> dict:
        """仅在来源时间前进时更新卡住检测的起点。"""
        entries = self._quote_progress_entries()
        previous = self._parse_timestamp(entries.get(symbol, {}).get("last_source_time"))
        source_at_utc = source_at.astimezone(timezone.utc)
        if previous is None or source_at_utc > previous:
            entries[symbol] = {
                "last_source_time": _iso(source_at_utc),
                "last_advance_at": _iso(observed_at),
            }
            self._write_json(self.quote_progress_path, entries)
        return self.quote_progress(symbol)

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
    def __init__(self, settings: LiveSettings, store: LiveStore | None = None) -> None:
        client = HttpClient(
            on_request=store.record_provider_request if store is not None else None,
        )
        cache = DiskCache(settings.state_dir / "cache")
        self.sina = SinaQuoteProvider(client, settings.sina_quote_url)
        self.tencent_quote = TencentQuoteProvider(client, settings.tencent_quote_url)
        self.sina_bars = SinaKlineProvider(client, cache, settings.sina_us_kline_url, settings.sina_cn_kline_url)
        self.tencent_bars = TencentKlineProvider(client, cache, settings.tencent_kline_url)
        self.fund_bars = EastMoneyFundProvider(client, cache, settings.eastmoney_fund_url)
        self.last_bar_quality: Dict[str, list[BarQualityIssue]] = {}

    def fetch(self, instruments: List[Instrument]) -> Tuple[Dict[str, Quote], Dict[str, List[Bar]], List[str]]:
        errors: List[str] = []
        quotes: Dict[str, Quote] = {}
        self.last_bar_quality = {}
        realtime = [item for item in instruments if item.realtime_quote]
        try:
            sina_quotes = self.sina.fetch(realtime)
            # 只有可验证来源时间的新浪主源才完成 DATA_READY 候选资格。若主源没有
            # 可验证时间，A/H 备用源可以补位；两个来源都没有时保留实际选中的报价，
            # 由后续来源时间门明确阻断，而不是伪造本机观察时间。
            quotes.update({symbol: quote for symbol, quote in sina_quotes.items() if quote.source_time is not None})
        except MarketDataError as exc:
            sina_quotes = {}
            errors.append("SINA_QUOTE:%s" % exc)
        cn_hk_missing = [item for item in realtime if item.market in {"CN", "HK"} and item.symbol not in quotes]
        if cn_hk_missing:
            try:
                tencent_quotes = self.tencent_quote.fetch(cn_hk_missing)
                for item in cn_hk_missing:
                    fallback = tencent_quotes.get(item.symbol)
                    primary = sina_quotes.get(item.symbol)
                    if fallback is not None and fallback.source_time is not None:
                        quotes[item.symbol] = fallback
                    elif primary is not None:
                        quotes[item.symbol] = primary
                    elif fallback is not None:
                        quotes[item.symbol] = fallback
            except MarketDataError as exc:
                errors.append("TENCENT_QUOTE:%s" % exc)
        for item in realtime:
            primary = sina_quotes.get(item.symbol)
            if item.symbol not in quotes and primary is not None:
                quotes[item.symbol] = primary
        bars: Dict[str, List[Bar]] = {}
        for item in instruments:
            try:
                if item.asset_type == "MUTUAL_FUND":
                    bars[item.symbol] = self.fund_bars.fetch(item)
                    selected_provider = self.fund_bars
                elif item.market in {"US", "CN"}:
                    try:
                        bars[item.symbol] = self.sina_bars.fetch(item)
                        selected_provider = self.sina_bars
                    except MarketDataError:
                        if item.market != "CN":
                            raise
                        bars[item.symbol] = self.tencent_bars.fetch(item)
                        selected_provider = self.tencent_bars
                else:
                    bars[item.symbol] = self.tencent_bars.fetch(item)
                    selected_provider = self.tencent_bars
                self.last_bar_quality[item.symbol] = list(getattr(selected_provider, "last_quality_issues", ()))
            except MarketDataError as exc:
                errors.append("BARS_%s:%s" % (item.symbol, exc))
        return quotes, bars, errors


class LiveEngine:
    def __init__(self, settings: LiveSettings) -> None:
        self.settings = settings
        self.store = LiveStore(settings.state_dir)
        self.gateway = MarketGateway(settings, self.store)

    def _quote_freshness(self, item: Instrument, quote: Quote | None, now: datetime) -> dict:
        """按交易所当地开休市口径验证来源时间，返回可公开的判定依据。"""
        exchange_timezone = ZoneInfo(item.timezone)
        exchange_now = now.astimezone(exchange_timezone)
        market_open = _market_is_open(item, exchange_now)
        report = {
            "market_state": "OPEN" if market_open else "CLOSED",
            "basis": "MARKET_OPEN_DECLARED_FEED_DELAY_PLUS_TTL" if market_open else "MARKET_CLOSED_RECENT_TRADING_DAY_APPROXIMATION",
            "exchange_timezone": item.timezone,
            "exchange_now": exchange_now.isoformat(),
            "declared_feed_delay_minutes": item.declared_feed_delay_minutes,
            "last_advance_at": None,
            "stalled_minutes": None,
        }
        if quote is None:
            return {
                **report,
                "status": "QUOTE_MISSING",
                "source_time": None,
                "observed_lag_minutes": None,
            }
        if quote.source_time is None:
            return {
                **report,
                "status": "SOURCE_TIME_MISSING",
                "source_time": None,
                "observed_lag_minutes": None,
            }
        source_at = (
            quote.source_time.astimezone(exchange_timezone)
            if quote.source_time.tzinfo is not None
            else quote.source_time.replace(tzinfo=exchange_timezone)
        )
        source_age_seconds = (exchange_now - source_at).total_seconds()
        report.update({
            "source_time": source_at.isoformat(),
            "observed_lag_minutes": source_age_seconds / 60,
        })
        if source_at > exchange_now + timedelta(seconds=MAX_FUTURE_CLOCK_SKEW_SECONDS):
            return {**report, "status": "SOURCE_TIME_CLOCK_AHEAD"}
        if market_open:
            allowed_source_age_seconds = (
                item.declared_feed_delay_minutes * 60 + self.settings.quote_max_age_seconds
            )
            progress = self.store.record_quote_source_progress(item.symbol, source_at, now)
            last_advance_at = self.store._parse_timestamp(progress["last_advance_at"])
            stalled_minutes = (
                max(0.0, (now - last_advance_at).total_seconds() / 60)
                if last_advance_at is not None
                else None
            )
            source_time_stale = source_age_seconds > allowed_source_age_seconds
            feed_stalled = (
                stalled_minutes is not None
                and stalled_minutes >= QUOTE_ADVANCE_STALL_MINUTES
            )
            return {
                **report,
                "status": (
                    "SOURCE_TIME_STALE"
                    if source_time_stale
                    else "FEED_STALLED"
                    if feed_stalled
                    else "FRESH"
                ),
                "source_age_seconds": source_age_seconds,
                "allowed_source_age_seconds": allowed_source_age_seconds,
                "last_advance_at": progress["last_advance_at"],
                "stalled_minutes": stalled_minutes,
                "advance_status": "FEED_STALLED" if feed_stalled else "ADVANCING_OR_WITHIN_GRACE",
            }
        progress = self.store.quote_progress(item.symbol)
        source_age_days = (exchange_now.date() - source_at.date()).days
        return {
            **report,
            "status": "FRESH" if source_age_days <= CLOSED_MARKET_SOURCE_MAX_AGE_DAYS else "SOURCE_TIME_STALE",
            "source_age_calendar_days": source_age_days,
            "allowed_source_age_calendar_days": CLOSED_MARKET_SOURCE_MAX_AGE_DAYS,
            "last_advance_at": progress["last_advance_at"],
            "stalled_minutes": None,
            "advance_status": "NOT_APPLICABLE_MARKET_CLOSED",
        }

    @staticmethod
    def _weekday_range(start, end) -> list:
        days = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

    @staticmethod
    def _latest_weekdays(end, count: int) -> list:
        days = []
        cursor = end
        while len(days) < count:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor -= timedelta(days=1)
        return list(reversed(days))

    @classmethod
    def _latest_usable_segment(cls, series: List[Bar]) -> tuple[List[Bar], dict]:
        """从最新 Bar 向早期扫描，在长缺口后保留最近的连续可用段。"""
        ordered = sorted(series, key=lambda bar: bar.day)
        for index in range(len(ordered) - 1, 0, -1):
            previous_day = ordered[index - 1].day
            following_day = ordered[index].day
            gap_business_day_count = len(cls._weekday_range(
                previous_day + timedelta(days=1),
                following_day - timedelta(days=1),
            ))
            if gap_business_day_count > MAX_USABLE_GAP_BUSINESS_DAYS:
                usable = ordered[index:]
                return usable, {
                    "previous_day": previous_day.isoformat(),
                    "following_day": following_day.isoformat(),
                    "business_day_count": gap_business_day_count,
                    "reason": "HISTORICAL_GAP_%s_TO_%s" % (
                        previous_day.isoformat(),
                        following_day.isoformat(),
                    ),
                }
        return ordered, {
            "previous_day": None,
            "following_day": None,
            "business_day_count": 0,
            "reason": None,
        }

    @staticmethod
    def _usable_bars(
        bars: Mapping[str, List[Bar]],
        bar_quality: Mapping[str, dict],
    ) -> Dict[str, List[Bar]]:
        """按已公开的 effective_start_day 裁剪，供所有后续指标和回测共用。"""
        usable: Dict[str, List[Bar]] = {}
        for symbol, series in bars.items():
            effective_start = bar_quality.get(symbol, {}).get("effective_start_day")
            usable[symbol] = [
                bar for bar in sorted(series, key=lambda item: item.day)
                if effective_start is None or bar.day >= datetime.fromisoformat(effective_start).date()
            ]
        return usable

    def _completed_daily_bars(
        self,
        bars: Mapping[str, List[Bar]],
        now: datetime,
    ) -> tuple[Dict[str, List[Bar]], dict]:
        """盘中日线先移除交易所当天的未收盘 bar，再交给指标和回测。"""
        completed: Dict[str, List[Bar]] = {}
        report: dict[str, dict] = {}
        for item in self.settings.universe:
            series = list(bars.get(item.symbol, ()))
            exchange_now = now.astimezone(ZoneInfo(item.timezone))
            exchange_today = exchange_now.date()
            market_open = _market_is_open(item, exchange_now)
            excluded = [bar for bar in series if market_open and bar.day == exchange_today]
            usable = [bar for bar in series if not (market_open and bar.day == exchange_today)]
            completed[item.symbol] = usable
            latest = max((bar.day for bar in usable), default=None)
            report[item.symbol] = {
                "market_state": "OPEN" if market_open else "CLOSED",
                "exchange_timezone": item.timezone,
                "exchange_today": exchange_today.isoformat(),
                "last_used_day": latest.isoformat() if latest else None,
                "session_complete": bool(
                    latest is not None and (not market_open or latest < exchange_today)
                ),
                "excluded_intraday_bar_count": len(excluded),
                "excluded_current_session_bar_count": len(excluded),
                "last_used_bar_date": latest.isoformat() if latest else None,
                "last_used_bar_is_closed": bool(
                    latest is not None and (not market_open or latest < exchange_today)
                ),
                "basis": (
                    "MARKET_OPEN_EXCLUDE_EXCHANGE_TODAY"
                    if market_open
                    else "MARKET_CLOSED_LATEST_AVAILABLE_BAR_COMPLETE"
                ),
            }
        return completed, report

    def _bar_quality_report(
        self,
        bars: Mapping[str, List[Bar]],
        issues_by_symbol: Mapping[str, list[BarQualityIssue]],
    ) -> dict:
        """把拒绝分类、历史裁剪和可用段长度写入报告。"""
        report: dict[str, dict] = {}
        for item in self.settings.universe:
            issues = list(issues_by_symbol.get(item.symbol, ()))
            series = list(bars.get(item.symbol, ()))
            if not series:
                if issues:
                    report[item.symbol] = {
                        "status": "BLOCKED",
                        "source": issues[0].source,
                        "input_bar_count": len(issues),
                        "accepted_bar_count": 0,
                        "dropped_invalid_bar_count": len(issues),
                        "dropped_invalid_bar_ratio": 1.0,
                        "recent_decision_window_trading_days": RECENT_DECISION_BAR_LOOKBACK_TRADING_DAYS,
                        "recent_window_start": None,
                        "recent_invalid_bar_count": len(issues),
                        "maximum_dropped_invalid_bars": MAX_DROPPED_INVALID_BARS_PER_SYMBOL,
                        "maximum_dropped_invalid_bar_ratio": MAX_DROPPED_INVALID_BAR_RATIO,
                        "maximum_usable_gap_business_days": MAX_USABLE_GAP_BUSINESS_DAYS,
                        "effective_start_day": None,
                        "effective_end_day": None,
                        "effective_bar_count": 0,
                        "trimmed_bar_count": 0,
                        "trim_reason": None,
                        "trim_gap_business_days": None,
                        "available_complete_walk_forward_windows": 0,
                        "required_complete_walk_forward_windows": MIN_COMPLETE_WINDOWS,
                        "blocking_reasons": ["NO_ACCEPTED_BARS", "RATIO_THRESHOLD"],
                        "issue_counts_by_type": {
                            issue_type: sum(1 for issue in issues if issue.issue_type == issue_type)
                            for issue_type in sorted({issue.issue_type for issue in issues})
                        },
                        "samples": [
                            {
                                "day": issue.day.isoformat() if issue.day else None,
                                "source": issue.source,
                                "issue_type": issue.issue_type,
                                "violations": list(issue.violations),
                            }
                            for issue in issues[:MAX_REPORTED_INVALID_BAR_SAMPLES]
                        ],
                    }
                continue
            accepted_count = len(series)
            input_count = accepted_count + len(issues)
            invalid_ratio = len(issues) / input_count if input_count else 1.0
            ordered_series = sorted(series, key=lambda bar: bar.day)
            usable_series, trim = self._latest_usable_segment(ordered_series)
            latest_day = ordered_series[-1].day
            history_start = ordered_series[0].day
            recent_days = self._latest_weekdays(latest_day, RECENT_QUALITY_ISSUE_WINDOW_TRADING_DAYS)
            recent_window_start = max(recent_days[0], history_start)
            window_start = recent_window_start
            recent_issues = [issue for issue in issues if issue.day is None or issue.day >= window_start]
            available_windows = len(walk_forward_windows([bar.day for bar in usable_series]))
            blocking_reasons: list[str] = []
            if recent_issues:
                blocking_reasons.append("RECENT_DECISION_WINDOW")
            if len(issues) > MAX_DROPPED_INVALID_BARS_PER_SYMBOL:
                blocking_reasons.append("COUNT_THRESHOLD")
            if invalid_ratio > MAX_DROPPED_INVALID_BAR_RATIO:
                blocking_reasons.append("RATIO_THRESHOLD")
            if trim["reason"] and available_windows < MIN_COMPLETE_WINDOWS:
                blocking_reasons.append("USABLE_SEGMENT_WALK_FORWARD_INSUFFICIENT")
            report[item.symbol] = {
                "status": (
                    "BLOCKED" if blocking_reasons
                    else "TRIMMED_HISTORICAL_SEGMENT" if trim["reason"]
                    else "DROPPED_INVALID_BARS" if issues
                    else "ACCEPTED"
                ),
                "source": ordered_series[-1].source,
                "input_bar_count": input_count,
                "accepted_bar_count": accepted_count,
                "dropped_invalid_bar_count": len(issues),
                "dropped_invalid_bar_ratio": invalid_ratio,
                "recent_decision_window_trading_days": RECENT_DECISION_BAR_LOOKBACK_TRADING_DAYS,
                "recent_window_start": window_start.isoformat(),
                "recent_invalid_bar_count": len(recent_issues),
                "maximum_dropped_invalid_bars": MAX_DROPPED_INVALID_BARS_PER_SYMBOL,
                "maximum_dropped_invalid_bar_ratio": MAX_DROPPED_INVALID_BAR_RATIO,
                "gap_scan_start": history_start.isoformat(),
                "gap_scan_end": latest_day.isoformat(),
                "maximum_usable_gap_business_days": MAX_USABLE_GAP_BUSINESS_DAYS,
                "effective_start_day": usable_series[0].day.isoformat(),
                "effective_end_day": usable_series[-1].day.isoformat(),
                "effective_bar_count": len(usable_series),
                "trimmed_bar_count": accepted_count - len(usable_series),
                "trim_reason": trim["reason"],
                "trim_gap_business_days": trim["business_day_count"] if trim["reason"] else None,
                "available_complete_walk_forward_windows": available_windows,
                "required_complete_walk_forward_windows": MIN_COMPLETE_WINDOWS,
                "blocking_reasons": blocking_reasons,
                "issue_counts_by_type": {
                    issue_type: sum(1 for issue in issues if issue.issue_type == issue_type)
                    for issue_type in sorted({issue.issue_type for issue in issues})
                },
                "samples": [
                    {
                        "day": issue.day.isoformat() if issue.day else None,
                        "source": issue.source,
                        "issue_type": issue.issue_type,
                        "violations": list(issue.violations),
                    }
                    for issue in issues[:MAX_REPORTED_INVALID_BAR_SAMPLES]
                ],
            }
        return report

    def _validate(
        self,
        now: datetime,
        quotes: Dict[str, Quote],
        bars: Dict[str, List[Bar]],
        errors: List[str],
        bar_quality: Mapping[str, dict] | None = None,
        quote_freshness: Mapping[str, dict] | None = None,
    ) -> List[str]:
        findings = list(errors)
        for item in self.settings.universe:
            exchange_timezone = ZoneInfo(item.timezone)
            exchange_now = now.astimezone(exchange_timezone)
            exchange_today = exchange_now.date()
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
                    freshness = (
                        quote_freshness.get(item.symbol)
                        if quote_freshness is not None
                        else self._quote_freshness(item, quote, now)
                    )
                    if freshness["status"] == "SOURCE_TIME_MISSING":
                        findings.append("QUOTE_SOURCE_TIME_MISSING:%s:%s" % (item.symbol, quote.source))
                    elif freshness["status"] == "SOURCE_TIME_CLOCK_AHEAD":
                        findings.append(
                            "QUOTE_SOURCE_CLOCK_AHEAD:%s:%s:%s"
                            % (item.symbol, freshness["source_time"], exchange_now.isoformat())
                        )
                    if freshness.get("status") == "SOURCE_TIME_STALE":
                        findings.append("QUOTE_SOURCE_STALE:%s" % item.symbol)
                    if freshness.get("advance_status") == "FEED_STALLED":
                        findings.append("QUOTE_FEED_STALLED:%s" % item.symbol)
            series = bars.get(item.symbol)
            if not series:
                findings.append("BAR_MISSING:%s" % item.symbol)
                continue
            if any(not bar.has_finite_ohlcv() for bar in series):
                findings.append("BAR_NONFINITE:%s" % item.symbol)
                continue
            if any(not bar.has_valid_ohlcv() for bar in series):
                findings.append("BAR_INVALID_OHLCV:%s" % item.symbol)
                continue
            future_days = sorted({bar.day for bar in series if bar.day > exchange_today})
            if future_days:
                findings.extend(
                    "BAR_FUTURE_DATE:%s:%s:%s"
                    % (item.symbol, future_day.isoformat(), exchange_today.isoformat())
                    for future_day in future_days
                )
                continue
            latest = max(bar.day for bar in series)
            if latest < exchange_today - timedelta(days=self.settings.bar_max_age_days):
                findings.append("BAR_STALE:%s:%s" % (item.symbol, latest.isoformat()))
        for symbol, quality in (bar_quality or {}).items():
            for reason in quality.get("blocking_reasons", []):
                if reason == "USABLE_SEGMENT_WALK_FORWARD_INSUFFICIENT":
                    findings.append(
                        "BAR_USABLE_SEGMENT_WALK_FORWARD_INSUFFICIENT:%s:可用段 %s 条 / 需要 %s 个完整 walk-forward 窗口（当前 %s）"
                        % (
                            symbol,
                            quality["effective_bar_count"],
                            quality["required_complete_walk_forward_windows"],
                            quality["available_complete_walk_forward_windows"],
                        )
                    )
                else:
                    findings.append("BAR_INVALID_OHLCV_%s:%s" % (reason, symbol))
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

    def _collection_control_blocked_report(
        self,
        now: datetime,
        reason: str,
        accounting: dict,
    ) -> dict:
        return {
            "application_version": APP_VERSION,
            "generated_at": _iso(now),
            "state": "SYSTEM_BLOCKED",
            "blocked_reason": reason,
            "automatic_trading": False,
            "data_cutoff": None,
            "data_cutoff_by_symbol": {},
            "instruments": {
                item.symbol: {"name": item.name, "market": item.market, "asset_type": item.asset_type}
                for item in self.settings.universe
            },
            "bar_sources": {},
            "bar_completion": {},
            "bar_quality": {},
            "data_quality_findings": [],
            "quote_observed_at": None,
            "quote_sources": {},
            "quotes": {},
            "market_fingerprint": {"quotes": {}, "bars": {}},
            "collection_request_accounting": accounting,
            "freshness_findings": [reason],
            "message": "采集请求预算或退避门处于阻断状态，未向上游发起新请求。",
            "backtest": {
                "status": "SYSTEM_BLOCKED",
                "message": "采集请求未执行，未运行回测结论。",
                "profitability_status": "SYSTEM_BLOCKED",
            },
            **blocked_aggregate_report(),
        }

    def run_once(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        findings: List[str] = []
        try:
            control = self.store.begin_collection_round(now)
            self.store.write_heartbeat(now)
            if not control["allowed"]:
                report = self._collection_control_blocked_report(
                    now,
                    control["reason"],
                    self.store.collection_accounting(now),
                )
                self.store.save(report)
                return report
            quotes, fetched_bars, errors = self.gateway.fetch(self.settings.universe)
            bars, bar_completion = self._completed_daily_bars(fetched_bars, now)
            errors.extend(
                "BAR_NO_COMPLETED_SESSION:%s" % symbol
                for symbol, completion in bar_completion.items()
                if completion["excluded_current_session_bar_count"] and completion["last_used_bar_date"] is None
            )
            bar_quality = self._bar_quality_report(
                bars,
                getattr(self.gateway, "last_bar_quality", {}),
            )
            bars = self._usable_bars(bars, bar_quality)
            quote_freshness = {
                item.symbol: self._quote_freshness(item, quotes.get(item.symbol), now)
                for item in self.settings.universe
                if item.realtime_quote
            }
            findings = self._validate(now, quotes, bars, errors, bar_quality, quote_freshness)
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
                    item.symbol: {
                        "name": item.name,
                        "market": item.market,
                        "asset_type": item.asset_type,
                        "declared_feed_delay_minutes": item.declared_feed_delay_minutes,
                    }
                    for item in self.settings.universe
                },
                "bar_sources": bar_sources,
                "bar_completion": bar_completion,
                "bar_quality": bar_quality,
                "data_quality_findings": [
                    "BAR_QUALITY_%s:%s:%s:%s"
                    % (
                        sample["issue_type"],
                        symbol,
                        sample["day"] or "UNKNOWN_DATE",
                        ",".join(sample["violations"]),
                    )
                    for symbol, quality in sorted(bar_quality.items())
                    for sample in quality["samples"]
                ],
                "quote_observed_at": _iso(quote_observed_at) if quote_observed_at else None,
                "quote_sources": {symbol: quote.source for symbol, quote in sorted(reportable_quotes.items())},
                "quotes": {symbol: {"price": quote.price, "currency": quote.currency, "source_time": quote.source_time.isoformat() if quote.source_time else None} for symbol, quote in sorted(reportable_quotes.items())},
                "quote_freshness": quote_freshness,
                "market_fingerprint": self._market_fingerprint(reportable_quotes, bars),
                "freshness_findings": findings,
                "message": "数据链路不完整，不出结论" if findings else "真实数据已就绪，已完成独立分支计算",
                "backtest": backtest,
                **branch_report,
            }
            self.store.finish_collection_round(now, succeeded=state == "DATA_READY")
            report["collection_request_accounting"] = self.store.collection_accounting(now)
            self.store.save(report)
        except CollectionBudgetExceeded as exc:
            try:
                self.store.finish_collection_round(now, succeeded=False)
                accounting = self.store.collection_accounting(now)
            except CollectionBudgetExceeded:
                accounting = {
                    "status": "ACCOUNTING_STATE_INVALID",
                    "stop_reason": "COLLECTION_ACCOUNTING_STATE_INVALID",
                }
            report = self._collection_control_blocked_report(now, str(exc), accounting)
            self.store.save(report)
        except JsonSerializationConstraintError:
            self.store.finish_collection_round(now, succeeded=False)
            report = self._serialization_blocked_report(now, findings)
            report["collection_request_accounting"] = self.store.collection_accounting(now)
            self.store.save(report)
        except Exception as exc:
            self.store.finish_collection_round(now, succeeded=False)
            report = self._runtime_failure_blocked_report(now, exc)
            report["collection_request_accounting"] = self.store.collection_accounting(now)
            self.store.save(report)
        return report
