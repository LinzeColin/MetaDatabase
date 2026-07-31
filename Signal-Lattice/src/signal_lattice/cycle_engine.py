from __future__ import annotations

import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .coordinator import coordinate_unique_recommendation
from .db import RuntimeDB
from .market_provider import load_universe, provider_for, MarketProviderError
from .skill_registry import reconcile_runtime_registry, RegistryError
from .skill_runtime import run_isolated_skill
from .self_balance import queue_current_signals, score_matured_outcomes


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _scheduled_minute(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()


def _policy(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        raise ValueError("DECISION_POLICY_INVALID")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("DECISION_POLICY_OBJECT_REQUIRED")
    return value


def run_minute_cycle(db: RuntimeDB, settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    now = (now or db.clock.now()).astimezone(timezone.utc)
    scheduled_for = _scheduled_minute(now)
    cycle_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"signal-lattice:{scheduled_for}"))
    db.fail_stale_cycles(max_age_seconds=max(180, settings.cycle_interval_seconds * 3))
    errors: list[dict[str, Any]] = []
    try:
        source = reconcile_runtime_registry(db, settings, now=now.isoformat())
    except RegistryError as exc:
        source = {"state": "FAILED", "source_commit": "UNAVAILABLE", "active_skill_count": 0, "git_error": str(exc)}
        errors.append({"stage": "source", "code": str(exc)})
    active_skills = db.active_runtime_skills()
    try:
        universe = load_universe(settings.universe_path)
        db.replace_universe(universe)
        universe_sha = canonical_sha256(universe)
    except (MarketProviderError, ValueError, OSError) as exc:
        universe = []
        universe_sha = None
        errors.append({"stage": "universe", "code": str(exc)})
    if not db.begin_minute_cycle(
        cycle_id, scheduled_for, str(source.get("source_commit", "UNAVAILABLE")),
        universe_sha, len(active_skills),
    ):
        latest = db.latest_minute_cycle()
        return latest or {"cycle_id": cycle_id, "state": "SKIPPED_OVERLAP"}
    started = time.monotonic()
    if not universe:
        recommendation = coordinate_unique_recommendation(
            cycle_id, scheduled_for,
            {"universe": [], "as_of": now.isoformat(), "source_digest": "0" * 64},
            [], _policy(settings.decision_policy_path), {}, settings.recommendation_enabled,
            settings.minimum_active_skills, settings.minimum_completed_skills, now=now,
        )
        db.complete_minute_cycle(cycle_id, "FAILED", 0, len(active_skills), recommendation, recommendation["receipt_sha256"], errors)
        return db.latest_minute_cycle() or recommendation
    try:
        snapshot = provider_for(settings).snapshot(universe, now)
        snapshot["runtime_source_state"] = str(source.get("state", "UNKNOWN"))
        snapshot["upstream_seal_pass"] = bool(
            len(active_skills) >= settings.minimum_active_skills
            and all(str(item.get("source_sha256", "")) for item in active_skills)
        )
        snapshot["active_runtime_manifest_digest"] = canonical_sha256([
            {"skill_id": item.get("skill_id"), "manifest_sha256": item.get("manifest_sha256")}
            for item in sorted(active_skills, key=lambda row: str(row.get("skill_id", "")))
        ])
        snapshot["source_digest"] = canonical_sha256({k: v for k, v in snapshot.items() if k != "source_digest"})
        db.save_cycle_market_snapshot(cycle_id, snapshot)
        score_matured_outcomes(db, snapshot)
    except (MarketProviderError, ValueError, OSError) as exc:
        errors.append({"stage": "market", "code": str(exc)})
        recommendation = coordinate_unique_recommendation(
            cycle_id, scheduled_for,
            {"universe": [], "as_of": now.isoformat(), "source_digest": "0" * 64},
            [], _policy(settings.decision_policy_path), {}, settings.recommendation_enabled,
            settings.minimum_active_skills, settings.minimum_completed_skills, now=now,
        )
        db.complete_minute_cycle(cycle_id, "FAILED", 0, len(active_skills), recommendation, recommendation["receipt_sha256"], errors)
        return db.latest_minute_cycle() or recommendation

    skill_results: list[dict[str, Any]] = []
    deadline = started + settings.cycle_deadline_seconds
    max_workers = max(1, min(4, len(active_skills)))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sl-skill") as pool:
        futures = {}
        for skill in active_skills:
            manifest = skill.get("manifest") or {}
            input_sha = canonical_sha256({"manifest": manifest, "snapshot": snapshot})
            db.start_minute_skill_run(cycle_id, skill, input_sha, settings.isolation_backend)
            remaining = max(0.5, deadline - time.monotonic())
            futures[pool.submit(run_isolated_skill, skill, snapshot, settings, remaining)] = skill
        for future in as_completed(futures):
            skill = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # execution boundary; do not crash whole cycle
                result = {
                    "state": "FAILED", "skill_id": skill["skill_id"], "input_sha256": "",
                    "duration_ms": 0, "error_code": type(exc).__name__, "output": None,
                    "output_sha256": None,
                }
            db.finish_minute_skill_run(
                cycle_id, skill["skill_id"], result["state"], int(result.get("duration_ms", 0)),
                result.get("output"), result.get("output_sha256"), result.get("error_code"),
            )
            skill_results.append(result)
    queue_current_signals(db, cycle_id, snapshot, skill_results)
    reliability = db.reliability_weights()
    recommendation = coordinate_unique_recommendation(
        cycle_id, scheduled_for, snapshot, skill_results, _policy(settings.decision_policy_path),
        reliability, settings.recommendation_enabled, settings.minimum_active_skills,
        settings.minimum_completed_skills, now=now,
    )
    completed_count = len([x for x in skill_results if x.get("state") in {"PASS", "ABSTAIN"}])
    failed_count = len(skill_results) - completed_count
    if recommendation["state"] == "SYSTEM_BLOCKED":
        cycle_state = "FAILED"
    elif failed_count:
        cycle_state = "DEGRADED"
    else:
        cycle_state = "COMPLETED"
    db.complete_minute_cycle(
        cycle_id, cycle_state, completed_count, failed_count, recommendation,
        recommendation["receipt_sha256"], errors,
    )
    return db.latest_minute_cycle() or recommendation
