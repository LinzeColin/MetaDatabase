from __future__ import annotations

import copy
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .clock import next_formal_review, next_slot, sydney_date, slot_start, utc_now
from .config import Settings
from .decision import decide
from .discovery import discover_candidates
from .market import MarketProviderError, provider_for
from .metrics import build_metrics
from .models import Candidate, SkillResult
from .report import finalize_report, render_report
from .skills import run_six_skills
from .storage import RuntimeStorage, read_json
from .whitebox import WhiteboxLedger


class V19Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage = RuntimeStorage(settings.state_dir)
        self.provider = provider_for(settings.market_provider, settings.fixture_dir)
        self.whitebox = WhiteboxLedger(self.storage.whitebox_db_file)

    def _merge_evidence(self, candidates: list[Candidate]) -> None:
        paths = self.settings.runtime.get("source_refresh_paths", {})
        evidence_dir = Path(str(paths.get("security_evidence_dir", "")))
        if evidence_dir.is_dir():
            for candidate in candidates:
                variants = [
                    evidence_dir / f"{candidate.provider_code}.json",
                    evidence_dir / f"{candidate.market}.{candidate.public_code}.json",
                ]
                for path in variants:
                    payload = read_json(path)
                    if not isinstance(payload, dict):
                        continue
                    if isinstance(payload.get("fundamentals"), dict):
                        candidate.fundamentals.update(payload["fundamentals"])
                    if isinstance(payload.get("events"), list):
                        candidate.events.extend([item for item in payload["events"] if isinstance(item, dict)])
                    if isinstance(payload.get("metadata"), dict):
                        candidate.metadata.update(payload["metadata"])
                    candidate.path_dependency_verified = bool(
                        payload.get("path_dependency_verified", candidate.path_dependency_verified)
                    )
                    break
        nav_file = Path(str(paths.get("official_nav_file", "")))
        nav_payload = read_json(nav_file)
        if isinstance(nav_payload, dict):
            rows = nav_payload.get("items", [])
            if isinstance(rows, list):
                by_code = {
                    str(row.get("provider_code", "")).upper(): row
                    for row in rows if isinstance(row, dict)
                }
                for candidate in candidates:
                    row = by_code.get(candidate.provider_code.upper())
                    if row and float(row.get("nav", 0.0) or 0.0) > 0:
                        candidate.price = float(row["nav"])
                        candidate.quote_time = str(row.get("as_of") or candidate.quote_time)

    def _macro_events(self) -> list[dict[str, Any]]:
        path = Path(str(self.settings.runtime.get("source_refresh_paths", {}).get("macro_events_file", "")))
        payload = read_json(path)
        if not isinstance(payload, dict):
            fallback = (
                read_json(self.settings.fixture_dir / "events.json", {})
                if self.settings.market_provider == "fixture" else {}
            )
            payload = fallback if isinstance(fallback, dict) else {}
        rows = payload.get("items", [])
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _incumbent_fallback(self, state: dict[str, Any]) -> Candidate:
        return Candidate(
            provider_code=str(state["provider_code"]),
            public_code=str(state["code"]),
            name=str(state["name"]),
            market="AU" if str(state.get("channel")) == "ASX" else str(state.get("channel", "AU")),
            currency=str(state.get("currency", "AUD")),
            bucket_id="us_broad",
            bucket_name="美国宽基",
            risk_tier=1,
            platform_verified=False,
            price=float(state.get("last_price") or state.get("reference_price") or 0.0),
            quote_time=str(state.get("last_updated") or state.get("established_at") or ""),
            discovery_source="canonical_state",
        )

    @staticmethod
    def _frontier(candidates: list[Candidate], incumbent_code: str, maximum: int) -> list[Candidate]:
        by_bucket: dict[str, list[Candidate]] = {}
        for candidate in candidates:
            by_bucket.setdefault(candidate.bucket_id, []).append(candidate)
        selected: list[Candidate] = []
        incumbent = next((item for item in candidates if item.provider_code == incumbent_code), None)
        if incumbent:
            selected.append(incumbent)
        selected_codes = {item.provider_code for item in selected}
        for bucket_id in sorted(by_bucket):
            rows = sorted(
                by_bucket[bucket_id],
                key=lambda item: (0 if item.platform_verified else 1, -item.liquidity_score, item.provider_code),
            )
            for row in rows[:2]:
                if row.provider_code not in selected_codes:
                    selected.append(row)
                    selected_codes.add(row.provider_code)
                if len(selected) >= maximum:
                    return selected
        return selected

    @staticmethod
    def _merge_incremental(cached: list[Candidate], updates: list[Candidate]) -> list[Candidate]:
        by_code = {item.provider_code: item for item in cached}
        for update in updates:
            previous = by_code.get(update.provider_code)
            if previous and not update.bars:
                update.bars = previous.bars
            if previous:
                if not update.fundamentals:
                    update.fundamentals = previous.fundamentals
                if not update.events:
                    update.events = previous.events
                if not update.metadata:
                    update.metadata = previous.metadata
                update.path_dependency_verified = (
                    update.path_dependency_verified or previous.path_dependency_verified
                )
            by_code[update.provider_code] = update
        return list(by_code.values())

    @staticmethod
    def _coverage_after_snapshot(candidates: list[Candidate], total_buckets: int) -> tuple[str, int]:
        verified_buckets = {
            item.bucket_id for item in candidates
            if item.platform_verified and item.price is not None and bool(item.bars)
        }
        count = len(verified_buckets)
        if total_buckets and count == total_buckets:
            return "平台精确", count
        if count >= max(1, total_buckets // 2):
            return "公共广泛", count
        if candidates:
            return "最低可行", count
        return "阻断", count

    def _full_scan(self, now: datetime, state: dict[str, Any]) -> tuple[list[Candidate], str, dict[str, Any]]:
        catalog = self.provider.catalog()
        candidates, coverage, discovery_meta = discover_candidates(catalog, self.settings.bucket_config)
        if not any(item.provider_code == state["provider_code"] for item in candidates):
            candidates.insert(0, self._incumbent_fallback(state))
        candidates = self.provider.snapshot(candidates, now, include_history=True)
        if not any(item.provider_code == state["provider_code"] for item in candidates):
            candidates.insert(0, self._incumbent_fallback(state))
        self._merge_evidence(candidates)
        coverage, verified_count = self._coverage_after_snapshot(
            candidates, int(discovery_meta.get("total_bucket_count", 9))
        )
        discovery_meta["verified_bucket_count"] = verified_count
        return candidates, coverage, discovery_meta

    def _incremental_scan(
        self, now: datetime, state: dict[str, Any], cached_payload: dict[str, Any]
    ) -> tuple[list[Candidate], str, dict[str, Any]]:
        cached = [
            Candidate.from_dict(row)
            for row in cached_payload.get("candidates", []) if isinstance(row, dict)
        ]
        frontier = self._frontier(
            cached,
            str(state["provider_code"]),
            int(self.settings.runtime.get("max_incremental_candidates", 18)),
        )
        updates = self.provider.snapshot(frontier, now, include_history=False)
        candidates = self._merge_incremental(cached, updates)
        self._merge_evidence(candidates)
        discovery = dict(cached_payload.get("discovery", {}))
        coverage, verified_count = self._coverage_after_snapshot(
            candidates, int(discovery.get("total_bucket_count", 9))
        )
        discovery["verified_bucket_count"] = verified_count
        return candidates, coverage, discovery

    def _full_scan_payload(self, now: datetime, state: dict[str, Any]) -> dict[str, Any]:
        candidates, coverage, discovery = self._full_scan(now, state)
        return {
            "as_of": now.isoformat(),
            "coverage": coverage,
            "discovery": discovery,
            "candidates": [item.to_dict() for item in candidates],
        }

    def run_once(self, now: datetime | None = None, defer_full_scan: bool = False) -> dict[str, Any]:
        started = time.monotonic()
        now = (now or utc_now()).astimezone(timezone.utc)
        existed = self.storage.state_file.is_file()
        state = self.storage.load_state(self.settings.canonical_state)
        scan_state = self.storage.load_scan_state()
        date_key = sydney_date(now)
        full_scan_due = scan_state.get("last_full_scan_date") != date_key
        provider_state = "live"
        provider_error: str | None = None
        discovery_meta: dict[str, Any] = {}
        coverage = "最低可行"
        candidates: list[Candidate] = []

        try:
            cached = self.storage.load_universe()
            if full_scan_due and not (defer_full_scan and cached):
                candidates, coverage, discovery_meta = self._full_scan(now, state)
                scan_state["last_full_scan_date"] = date_key
                scan_state["last_full_scan_at"] = now.isoformat()
            elif cached:
                candidates, coverage, discovery_meta = self._incremental_scan(now, state, cached)
                if full_scan_due:
                    provider_state = "full_scan_pending"
            else:
                candidates, coverage, discovery_meta = self._full_scan(now, state)
                scan_state["last_full_scan_date"] = date_key
                scan_state["last_full_scan_at"] = now.isoformat()
        except (MarketProviderError, OSError, ValueError, TypeError) as exc:
            provider_state = "last_snapshot"
            provider_error = str(exc)
            cached_market = self.storage.load_market() or self.storage.load_universe()
            if cached_market:
                candidates = [
                    Candidate.from_dict(row)
                    for row in cached_market.get("candidates", []) if isinstance(row, dict)
                ]
                coverage = "最低可行"
                discovery_meta = dict(cached_market.get("discovery", {}))
            else:
                candidates = [self._incumbent_fallback(state)]
                coverage = "最低可行"
                discovery_meta = {"dynamic_bucket_count": 0, "total_bucket_count": 9}

        if not any(item.provider_code == state["provider_code"] for item in candidates):
            candidates.insert(0, self._incumbent_fallback(state))
        self._merge_evidence(candidates)
        metrics = build_metrics(candidates, str(state["provider_code"]))
        macro_events = self._macro_events()
        us_times = [
            item.quote_time for item in candidates
            if item.quote_time and item.bucket_id != "china_assets"
        ]
        china_times = [
            item.quote_time for item in candidates
            if item.quote_time and item.bucket_id == "china_assets"
        ]
        event_times = [
            str(row.get("published_at")) for row in macro_events
            if str(row.get("published_at", "")).strip()
        ]
        market_context = {
            "provider_state": provider_state,
            "provider_error": provider_error,
            "coverage": coverage,
            "full_scan": not full_scan_due or scan_state.get("last_full_scan_date") == date_key,
            "full_scan_pending": full_scan_due and provider_state == "full_scan_pending",
            "discovery": discovery_meta,
            "macro_events": macro_events,
            "state_loaded": existed,
            "state_conflict": False,
            "us_cutoff": max(us_times) if us_times else "最近有效常规收盘",
            "china_cutoff": max(china_times) if china_times else "最近可定位正式净值",
            "fx_cutoff": f"现金利率配置截至{self.settings.runtime.get('cash_rate_as_of', '最近正式值')}",
            "event_cutoff": max(event_times) if event_times else "截至本轮已公开事件",
        }

        # Six outputs are completed and frozen before central adjudication sees them.
        skills = run_six_skills(self.settings, candidates, metrics, state, market_context)
        outcome = decide(self.settings, now, candidates, metrics, state, skills, market_context)
        next_review = next_formal_review(now)
        report = finalize_report(outcome.public, now, next_review)
        rendered = render_report(report)
        self.storage.save_state(outcome.updated_state)
        cache_payload = {
            "as_of": now.isoformat(),
            "coverage": coverage,
            "discovery": discovery_meta,
            "candidates": [item.to_dict() for item in candidates],
        }
        self.storage.save_universe(cache_payload)
        self.storage.save_market(cache_payload)
        self.storage.save_scan_state(scan_state)
        slot_key = slot_start(now, self.settings.refresh_seconds).strftime("%Y%m%dT%H%M%SZ")
        internal = dict(outcome.internal)
        internal["market_context"] = market_context
        whitebox = self.whitebox.record_cycle(
            observed_at=now,
            app_version=self.settings.app_version,
            prompt_version=self.settings.prompt_version,
            report=report,
            internal=internal,
            skills=skills,
            candidates=candidates,
            winner_provider_code=str(outcome.updated_state.get("provider_code", state["provider_code"])),
            provider_state=provider_state,
        )
        internal["whitebox"] = whitebox
        envelope = {
            "schema_version": "1.1.0",
            "app_version": self.settings.app_version,
            "prompt_version": self.settings.prompt_version,
            "refresh_seconds": self.settings.refresh_seconds,
            "ui_heartbeat_seconds": 1,
            "generated_at": now.isoformat(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "report": report,
            "rendered": rendered,
            "internal": internal,
        }
        self.storage.save_cycle(
            envelope, rendered, date_key, slot_key,
            decision_id=str(whitebox["decision_id"]),
            decision_changed=bool(whitebox["decision_changed"]),
        )
        return envelope

    def publish_failure(self, now: datetime, exc: Exception) -> dict[str, Any]:
        latest = self.storage.latest()
        next_review = next_formal_review(now)
        if latest and isinstance(latest.get("report"), dict):
            report = copy.deepcopy(latest["report"])
            report["运行状态"] = "降级持有"
            report["市场覆盖"] = "最低可行"
            report["状态连续性"] = "部分状态"
            report["裁决完整性"] = "最低可行"
            first = report.get("第一板块", {})
            first["唯一操作"] = "持有"
            first["现在怎么做"] = "仅在影子账本维持上一条完整状态，不产生任何真实交易副作用。"
            first["核心依据"] = (
                f"截至{sydney_date(now)}，本轮运行输入未完整，系统保留上一条唯一影子状态并拒绝切换"
                "【上一完整报告】【V19状态账本】。"
            )
            report["数据截止"] = f"{report.get('数据截止', '上一完整报告')}；运行异常={type(exc).__name__}"
        else:
            rows = []
            for route in self.settings.skill_routes.get("skills", []):
                rows.append({
                    "技能": route["display_name"],
                    "适用状态": "适用",
                    "运行方式": "弃权",
                    "弃权主原因": "缺少必要数据",
                    "方法家族": route["family"],
                    "原始权重": 0.0,
                    "家族内权重": "0.0%",
                    "总体权重": "0.0%",
                    "结论": "无结论",
                    "独立性": f"本轮未形成最低输入；运行异常={type(exc).__name__}。",
                })
            state = self.storage.load_state(self.settings.canonical_state)
            report = {
                "运行时间": "",
                "提示词版本": self.settings.prompt_version,
                "运行状态": "阻断",
                "市场覆盖": "阻断",
                "数据截止": f"本轮未形成有效数据；运行异常={type(exc).__name__}",
                "状态连续性": "部分状态",
                "裁决完整性": "阻断",
                "技能适用覆盖率": "0.0%",
                "第一板块": {
                    "唯一操作": "持有",
                    "唯一平台": str(state.get("platform", "MooMooAU")),
                    "唯一标的": str(state.get("name", "无")),
                    "代码": str(state.get("code", "无")),
                    "唯一方向": str(state.get("direction", "看涨")),
                    "可观察回撤": f"{float(state.get('observable_drawdown_pct', 0.0)):.1f}%",
                    "风险调整回撤": f"{float(state.get('risk_adjusted_drawdown_pct', 0.0)):.1f}%",
                    "剩余回撤预算": f"{max(0.0, self.settings.hard_failure_drawdown_pct - float(state.get('risk_adjusted_drawdown_pct', 0.0))):.1f}%",
                    "预期研究窗口": "60交易日主窗；20交易日战术复核",
                    "相对宽基": "未通过",
                    "相对现金": "未通过",
                    "现在怎么做": "仅在影子账本保留冻结状态，不产生任何真实交易副作用。",
                    "核心依据": "本轮完整链路未形成，禁止用空数据改变唯一影子状态【V19状态账本】。",
                    "最大反证": "恢复最低数据输入后，新的完整裁决可能推翻当前冻结状态。",
                    "失效条件": "风险调整回撤达到20.0%即硬失效。",
                    "下一正式复核": "",
                },
                "第二板块": {
                    "矩阵": rows,
                    "适用技能": "6/6",
                    "实际参与": "0/6",
                    "适用覆盖率": "0.0%",
                    "原生参与": "0/6",
                    "原生覆盖率": "0.0%",
                    "中央定量审查": "未运行；本轮关键字段未形成，禁止伪造价格、概率或收益结论。",
                    "权重说明": "总体权重合计100.0%仅表示实际参与方法内部权重，不代表六技能覆盖率、共识率或收益概率。",
                },
            }
        report = finalize_report(report, now, next_review)
        rendered = render_report(report)
        internal = {"operational_error": type(exc).__name__, "market_context": {"provider_state": "error"}}
        failure_skills: list[SkillResult] = []
        for route in self.settings.skill_routes.get("skills", []):
            failure_skills.append(SkillResult(
                skill_id=str(route["skill_id"]),
                display_name=str(route["display_name"]),
                applicable=True,
                run_mode="弃权",
                abstention_reason="缺少必要数据",
                family=str(route["family"]),
                raw_weight=0.0,
                family_weight_pct=0.0,
                overall_weight_pct=0.0,
                conclusion="无结论",
                independence="本轮运行异常，未形成最低输入",
                contribution="",
                source_state="运行异常",
            ))
        fallback_candidate = self._incumbent_fallback(self.storage.load_state(self.settings.canonical_state))
        whitebox = self.whitebox.record_cycle(
            observed_at=now,
            app_version=self.settings.app_version,
            prompt_version=self.settings.prompt_version,
            report=report,
            internal=internal,
            skills=failure_skills,
            candidates=[fallback_candidate],
            winner_provider_code=fallback_candidate.provider_code,
            provider_state="error",
        )
        internal["whitebox"] = whitebox
        envelope = {
            "schema_version": "1.1.0",
            "app_version": self.settings.app_version,
            "prompt_version": self.settings.prompt_version,
            "refresh_seconds": self.settings.refresh_seconds,
            "ui_heartbeat_seconds": 1,
            "generated_at": now.isoformat(),
            "duration_seconds": 0.0,
            "report": report,
            "rendered": rendered,
            "internal": internal,
        }
        self.storage.save_cycle(
            envelope,
            rendered,
            sydney_date(now),
            slot_start(now, self.settings.refresh_seconds).strftime("%Y%m%dT%H%M%SZ"),
            decision_id=str(whitebox["decision_id"]),
            decision_changed=bool(whitebox["decision_changed"]),
        )
        return envelope

    def run_loop(self) -> None:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sl19-daily-scan")
        pending: Future[dict[str, Any]] | None = None
        retry_after: datetime | None = None
        try:
            while True:
                now = utc_now()
                state = self.storage.load_state(self.settings.canonical_state)
                scan_state = self.storage.load_scan_state()
                date_key = sydney_date(now)
                cached = self.storage.load_universe()
                full_scan_due = scan_state.get("last_full_scan_date") != date_key

                if pending is not None and pending.done():
                    try:
                        payload = pending.result()
                        self.storage.save_universe(payload)
                        self.storage.save_market(payload)
                        scan_state = self.storage.load_scan_state()
                        scan_state["last_full_scan_date"] = date_key
                        scan_state["last_full_scan_at"] = str(payload.get("as_of", now.isoformat()))
                        scan_state.pop("last_full_scan_error", None)
                        self.storage.save_scan_state(scan_state)
                        retry_after = None
                    except Exception as exc:
                        scan_state = self.storage.load_scan_state()
                        scan_state["last_full_scan_error"] = type(exc).__name__
                        scan_state["last_full_scan_error_at"] = now.isoformat()
                        self.storage.save_scan_state(scan_state)
                        retry_after = now + timedelta(seconds=300)
                    pending = None
                    full_scan_due = self.storage.load_scan_state().get("last_full_scan_date") != date_key

                if (
                    full_scan_due
                    and cached
                    and pending is None
                    and (retry_after is None or now >= retry_after)
                ):
                    pending = executor.submit(self._full_scan_payload, now, state)

                try:
                    self.run_once(now, defer_full_scan=bool(full_scan_due and cached))
                except Exception as exc:
                    self.publish_failure(now, exc)

                target = next_slot(utc_now(), self.settings.refresh_seconds)
                time.sleep(max(0.1, (target - utc_now()).total_seconds()))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
