"""每轮运行前的公开数据刷新：基金净值、申赎状态、上证综指、标普 500。

写入的都是 state 目录里的 data/manual 副本（种子取自仓库 data/manual），从不改仓库文件。
任何一个源失败都记进 DataHealth，报告里如实写出；不用旧数据冒充本次抓取。
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from app.adapters.manual_sources import Candidate, PricePoint, load_candidates
from app.config import Settings
from app.core.candidate_universe_expander import expand_candidate_universe
from app.core.fund_rule_autofill import autofill_fund_rules
from app.headless import sources as src

PRICE_FIELDS = ["asset_code", "date", "close", "source_name", "source_type", "source_priority", "url_or_path", "evidence_level", "as_of"]
SEED_FILES = ("candidates.csv", "fund_rules.csv", "price_history.csv", "benchmark_price_history.csv")
ALLOWED_BENCHMARK_SOURCES = {"000001.SH": src.SOURCE_SSE, "SPX": src.SOURCE_FRED}
FUND_HISTORY_KEEP_DAYS = 1100
STALE_TRADING_DAYS = 2
SP500_STALE_CALENDAR_DAYS = 6


@dataclass
class SourceStatus:
    key: str
    label: str
    ok: bool
    latest_date: str | None
    rows: int
    detail: str
    url: str
    used_cache: bool = False
    fetched_at: str = ""


@dataclass
class DataHealth:
    generated_at: str
    sources: list[SourceStatus] = field(default_factory=list)
    trading_dates: list[date] = field(default_factory=list)
    base_fund_total: int = 0
    base_fund_failed: int = 0
    addition_total: int = 0
    addition_failed: int = 0
    latest_nav_date: str | None = None
    status: str = "ok"
    notes: list[str] = field(default_factory=list)
    status_changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "latest_nav_date": self.latest_nav_date,
            "base_fund_total": self.base_fund_total,
            "base_fund_failed": self.base_fund_failed,
            "addition_total": self.addition_total,
            "addition_failed": self.addition_failed,
            "trading_dates_tail": [d.isoformat() for d in self.trading_dates[-10:]],
            "notes": list(self.notes),
            "status_changes": list(self.status_changes),
            "sources": [source.__dict__ for source in self.sources],
        }


def bootstrap_state(settings: Settings, seed_dir: Path | None = None) -> list[str]:
    """state 目录里缺哪份种子文件就从仓库 data/manual 拷一份；已有的绝不覆盖。"""
    seed = seed_dir or (settings.root_dir / "data" / "manual")
    settings.ensure_dirs()
    copied: list[str] = []
    for name in SEED_FILES:
        target = settings.manual_dir / name
        source = seed / name
        if not target.exists() and source.exists() and source.resolve() != target.resolve():
            target.write_bytes(source.read_bytes())
            copied.append(name)
    return copied


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _price_row(code: str, point: src.NavPoint, *, source_name: str, source_type: str, priority: int, url: str, level: str, as_of: str) -> dict[str, str]:
    return {
        "asset_code": code,
        "date": point.date.isoformat(),
        "close": repr(point.close),
        "source_name": source_name,
        "source_type": source_type,
        "source_priority": str(priority),
        "url_or_path": url,
        "evidence_level": level,
        "as_of": as_of,
    }


def _state_file(settings: Settings) -> Path:
    return settings.data_dir / "refresh_state.json"


def _load_state(settings: Settings) -> dict[str, object]:
    path = _state_file(settings)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(settings: Settings, state: dict[str, object]) -> None:
    _state_file(settings).write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _universe_cache_age_hours(settings: Settings, now: datetime) -> float | None:
    path = settings.data_dir / "cache" / "fund_universe_eastmoney_latest.json"
    if not path.exists():
        return None
    return (now.timestamp() - path.stat().st_mtime) / 3600.0


def _scope_codes(settings: Settings, candidates_path: Path) -> list[str]:
    codes: list[str] = []
    for candidate in load_candidates(candidates_path):
        if candidate.is_excluded or not candidate.asset_code.isdigit():
            continue
        codes.append(candidate.asset_code)
    return codes


def _stub_candidate(code: str, name: str) -> Candidate:
    return Candidate(
        asset_id=code, asset_code=code, asset_name=name, asset_type="off_platform_fund", market="", fund_company="",
        risk_level="high", theme="", is_off_platform_fund=True, is_excluded=False, exclusion_reason="",
        official_source_count=0, fallback_aggregated=True, evidence_level="Medium", source_name="", source_type="",
        source_url="", missing_nav_days=0, missing_holding_days=0, conflict_flag=False, as_of="",
    )


def _refresh_benchmark(
    client: src.HttpClient,
    code: str,
    existing: list[dict[str, str]],
    fetch,
    *,
    today: date,
    source_name: str,
    source_type: str,
    priority: int,
    url: str,
    label: str,
    now_iso: str,
) -> tuple[list[dict[str, str]], SourceStatus]:
    try:
        points = fetch()
        rows = [
            _price_row(code, p, source_name=source_name, source_type=source_type, priority=priority, url=url, level="Strong" if source_type == "official" else "Medium", as_of=today.isoformat())
            for p in points
        ]
        return rows, SourceStatus(code, label, True, points[-1].date.isoformat(), len(rows), "抓取成功", url, False, now_iso)
    except src.SourceError as exc:
        kept = [row for row in existing if row.get("source_name") == source_name]
        latest = kept[-1]["date"] if kept else None
        detail = f"抓取失败：{exc}"
        detail += "；沿用上次成功抓取的数据（见最新日期，非本轮数据）" if kept else "；无可用旧数据，相关对比标为缺失"
        return kept, SourceStatus(code, label, False, latest, len(kept), detail, url, bool(kept), now_iso)


def _merge_rows(existing: list[dict[str, str]], new_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_date = {row["date"]: row for row in existing}
    for row in new_rows:
        by_date[row["date"]] = row
    return [by_date[key] for key in sorted(by_date)]


def refresh_public_data(
    settings: Settings,
    *,
    client: src.HttpClient | None = None,
    now: datetime | None = None,
    seed_dir: Path | None = None,
    universe_max_age_hours: float = 20.0,
) -> DataHealth:
    client = client or src.HttpClient()
    now = now or datetime.now(src.CST)
    today = now.astimezone(src.CST).date()
    now_iso = now.isoformat(timespec="seconds")
    bootstrap_state(settings, seed_dir)
    health = DataHealth(generated_at=now_iso)
    state = _load_state(settings)
    full_pulls: dict[str, str] = dict(state.get("full_pull_date", {}))  # type: ignore[arg-type]
    checked: dict[str, str] = dict(state.get("nav_checked", {}))  # type: ignore[arg-type]

    candidates_path = settings.manual_dir / "candidates.csv"
    base_codes = _scope_codes(settings, candidates_path)

    # 1) 全市场候选池扩容清单（每天最多联网取一次全市场基金清单，其余用缓存）
    additions: list[str] = []
    addition_names: dict[str, str] = {}
    if settings.candidate_universe_auto_expand_enabled:
        age = _universe_cache_age_hours(settings, now)
        live = settings.candidate_universe_live_fetch_enabled and (age is None or age >= universe_max_age_hours)
        try:
            expansion = expand_candidate_universe(
                replace(settings, candidate_universe_live_fetch_enabled=live),
                base_candidates_path=candidates_path,
                live_fetch=live,
                backfill_nav=False,
                write_output=False,
            )
            additions = [str(item["code"]) for item in expansion.get("additions", [])]
            addition_names = {str(item["code"]): str(item.get("name", "")) for item in expansion.get("additions", [])}
            if expansion.get("status") != "pass":
                health.notes.append(f"候选池扩容：{expansion.get('message')}")
        except Exception as exc:  # 扩容只是加观察范围，失败不影响基础候选
            health.notes.append(f"候选池扩容失败（只用基础候选）：{exc}")
    additions = [code for code in additions if code not in base_codes]

    # 2) 基金净值 + 申赎状态
    price_path = settings.manual_dir / "price_history.csv"
    _, price_rows = _read_rows(price_path)
    rows_by_code: dict[str, list[dict[str, str]]] = {}
    for row in price_rows:
        rows_by_code.setdefault(row["asset_code"], []).append(row)
    for code in rows_by_code:
        rows_by_code[code].sort(key=lambda r: r["date"])

    rules_path = settings.manual_dir / "fund_rules.csv"
    rule_fields, rule_rows = _read_rows(rules_path)
    rules_by_code = {row["asset_code"]: row for row in rule_rows}
    min_span = settings.min_candidate_nav_history_span_days

    scope = [(code, True) for code in base_codes] + [(code, False) for code in additions]
    health.base_fund_total = len(base_codes)
    health.addition_total = len(additions)
    latest_dates: list[date] = []
    for code, is_base in scope:
        existing = rows_by_code.get(code, [])
        last = date.fromisoformat(existing[-1]["date"]) if existing else None
        first = date.fromisoformat(existing[0]["date"]) if existing else None
        history_short = bool(existing) and (last - first).days < min_span + 10  # type: ignore[operator]
        stale = last is None or (today - last).days > 20
        already_full_today = full_pulls.get(code) == today.isoformat()
        need_full = stale or (history_short and not already_full_today)
        # 基金净值晚上才出：同一天 19:00 前已经查过就不重复查（申赎状态照常每轮刷新）。
        skip_nav = (not need_full) and bool(existing) and checked.get(code) == today.isoformat() and now.astimezone(src.CST).hour < 19
        try:
            if skip_nav:
                rows_by_code[code] = existing
                merged = existing
            elif need_full:
                points = src.fetch_fund_nav_full(client, code, keep_days=FUND_HISTORY_KEEP_DAYS, today=today)
                merged = [
                    _price_row(code, p, source_name=src.SOURCE_NAV_FULL, source_type="public_aggregation", priority=5, url=src.PINGZHONG_URL.format(code=code), level="Medium", as_of=today.isoformat())
                    for p in points
                ]
                full_pulls[code] = today.isoformat()
            else:
                points = src.fetch_fund_nav_incremental(client, code, last - timedelta(days=3), today)  # type: ignore[operator]
                new_rows = [
                    _price_row(code, p, source_name=src.SOURCE_NAV_INCREMENTAL, source_type="public_aggregation", priority=5, url=src.LSJZ_URL, level="Medium", as_of=today.isoformat())
                    for p in points
                ]
                merged = _merge_rows(existing, new_rows)
            cutoff = (today - timedelta(days=FUND_HISTORY_KEEP_DAYS)).isoformat()
            rows_by_code[code] = [row for row in merged if row["date"] >= cutoff]
            checked[code] = today.isoformat()
            latest = date.fromisoformat(rows_by_code[code][-1]["date"])
            latest_dates.append(latest)
            if is_base and code in rules_by_code:
                try:
                    status = src.fetch_fund_status(client, code)
                    rule = rules_by_code[code]
                    for key, mapped, text, label in (
                        ("subscription_status", status.subscription, status.subscription_text, "申购"),
                        ("redemption_status", status.redemption, status.redemption_text, "赎回"),
                    ):
                        if mapped and rule.get(key) != mapped:
                            health.status_changes.append(f"{code} {label}状态 {rule.get(key) or '空'} → {mapped}（{text}）")
                            rule[key] = mapped
                        if mapped:
                            rule["as_of"] = today.isoformat()
                except src.SourceError as exc:
                    health.notes.append(f"{code} 申赎状态未刷新：{exc}")
        except src.SourceError as exc:
            if is_base:
                health.base_fund_failed += 1
                health.notes.append(f"{code} 净值抓取失败，沿用旧数据（最新 {existing[-1]['date'] if existing else '无'}）：{exc}")
            else:
                health.addition_failed += 1
            if existing:
                latest_dates.append(date.fromisoformat(existing[-1]["date"]))

    # 自动扩容候选的费率/申赎规则：带重试取一次并落盘，后面每轮直接用（不再每轮重取、也不再因偶发失败而漂移）。
    if additions and settings.candidate_universe_rule_autofill_enabled:
        missing = [code for code in additions if code not in rules_by_code and code in rows_by_code]
        if missing:
            stubs = [_stub_candidate(code, addition_names.get(code, "")) for code in missing]
            filled, autofill = autofill_fund_rules(
                settings,
                stubs,
                {},
                max_fetches=len(stubs),
                write_output=False,
                fetcher=lambda url: client.get(url, {"Referer": "https://fundf10.eastmoney.com/"}).decode("utf-8", errors="ignore"),
            )
            if not rule_fields:
                rule_fields = list(next(iter(filled.values())).__dict__.keys()) if filled else []
            for code, rule in filled.items():
                row = {key: ("" if value is None else ("true" if value is True else "false" if value is False else str(value))) for key, value in asdict(rule).items()}
                rule_rows.append(row)
                rules_by_code[code] = row
            failed = [r for r in autofill.get("rows", []) if r["status"] == "warn"]
            if failed:
                health.notes.append(f"{len(failed)} 只自动扩容候选的费率页未取到，下一轮重试")

    all_rows: list[dict[str, str]] = []
    for code in sorted(rows_by_code):
        all_rows.extend(rows_by_code[code])
    _write_rows(price_path, PRICE_FIELDS, all_rows)
    if rule_rows:
        _write_rows(rules_path, rule_fields, rule_rows)
    health.latest_nav_date = max(latest_dates).isoformat() if latest_dates else None
    health.sources.append(
        SourceStatus(
            "fund_nav",
            "基金净值（天天基金公开接口）",
            health.base_fund_failed == 0 and bool(latest_dates),
            health.latest_nav_date,
            len(all_rows),
            f"基础候选 {health.base_fund_total - health.base_fund_failed}/{health.base_fund_total} 只成功；自动扩容 {health.addition_total - health.addition_failed}/{health.addition_total} 只成功",
            src.PINGZHONG_URL.format(code="{基金代码}"),
            False,
            now_iso,
        )
    )

    # 3) 基准指数：上证综指（上交所官方）+ 标普 500（FRED）
    bench_path = settings.manual_dir / "benchmark_price_history.csv"
    _, bench_rows = _read_rows(bench_path)
    bench_by_code: dict[str, list[dict[str, str]]] = {}
    for row in bench_rows:
        bench_by_code.setdefault(row["asset_code"], []).append(row)
    sse_rows, sse_status = _refresh_benchmark(
        client, "000001.SH", bench_by_code.get("000001.SH", []),
        lambda: src.fetch_sse_index(client, count=900),
        today=today, source_name=src.SOURCE_SSE, source_type="official", priority=1,
        url=src.SSE_KLINE_URL, label="上证综指（上交所官方行情）", now_iso=now_iso,
    )
    spx_rows, spx_status = _refresh_benchmark(
        client, "SPX", bench_by_code.get("SPX", []),
        lambda: src.fetch_fred_sp500(client, start=today - timedelta(days=FUND_HISTORY_KEEP_DAYS)),
        today=today, source_name=src.SOURCE_FRED, source_type="public_aggregation", priority=4,
        url=src.FRED_SP500_URL + "?id=SP500", label="标普 500（FRED）", now_iso=now_iso,
    )
    _write_rows(bench_path, PRICE_FIELDS, sse_rows + spx_rows)
    health.sources.extend([sse_status, spx_status])
    health.trading_dates = [date.fromisoformat(row["date"]) for row in sse_rows] if sse_status.ok else []

    # 4) 汇总健康度
    problems: list[str] = []
    if health.base_fund_failed:
        problems.append(f"{health.base_fund_failed} 只基础候选净值未能刷新")
    if not sse_status.ok:
        problems.append("上证综指抓取失败")
    if not spx_status.ok:
        problems.append("标普 500 抓取失败")
    if health.latest_nav_date:
        latest_nav = date.fromisoformat(health.latest_nav_date)
        if health.trading_dates:
            lag = sum(1 for d in health.trading_dates if latest_nav < d <= today)
            if lag > STALE_TRADING_DAYS:
                problems.append(f"净值最新日期 {health.latest_nav_date} 落后上交所交易日 {lag} 个，数据源可能停更")
        elif (today - latest_nav).days > 4:
            problems.append(f"净值最新日期 {health.latest_nav_date}，距今超过 4 天（无交易日历可对照，可能休市或停更）")
    else:
        problems.append("没有任何可用的基金净值")
    if spx_status.ok and spx_status.latest_date and (today - date.fromisoformat(spx_status.latest_date)).days > SP500_STALE_CALENDAR_DAYS:
        problems.append(f"标普 500 最新日期 {spx_status.latest_date}，距今超过 {SP500_STALE_CALENDAR_DAYS} 天")
    health.notes = problems + health.notes
    health.status = "degraded" if problems else "ok"

    state["full_pull_date"] = full_pulls
    state["nav_checked"] = checked
    state["last_refresh"] = now_iso
    _save_state(settings, state)
    return health


def apply_nav_freshness(
    candidates: list[Candidate],
    price_history: dict[str, list[PricePoint]],
    trading_dates: list[date],
    today: date,
) -> list[Candidate]:
    """按真实净值日期重算每只基金落后了几个交易日（取代候选表里写死的 missing_nav_days）。"""
    result: list[Candidate] = []
    for candidate in candidates:
        points = price_history.get(candidate.asset_code)
        if not points:
            result.append(candidate)
            continue
        last = points[-1].date
        if trading_dates:
            missing = sum(1 for d in trading_dates if last < d <= today)
        else:
            missing = sum(1 for offset in range(1, (today - last).days) if (last + timedelta(days=offset)).weekday() < 5)
        result.append(replace(candidate, missing_nav_days=missing))
    return result
