#!/usr/bin/env python3
"""Read-only production state probe for the exact deployed JobHuntBot database.

The probe reports counts and invariants only. It never decrypts candidate data or
prints credentials, email addresses, resume text, job descriptions, or Secret
values.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, inspect, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import (
    AIUsage,
    ApplicationEvent,
    ApplicationPack,
    CandidateProfile,
    DiscoveryRun,
    DiscoverySourceStatus,
    Job,
    Recommendation,
    Resume,
    User,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--require-alembic-head", default="0002_delivery_lookup")
    args = parser.parse_args()

    errors: list[str] = []
    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "users", "candidate_profiles", "resumes", "jobs", "recommendations",
        "discovery_runs", "discovery_source_status", "application_packs",
        "application_events", "ai_usage", "alembic_version",
    }
    missing = sorted(required_tables - tables)
    if missing:
        errors.append("missing tables: " + ", ".join(missing))

    forbidden_columns: dict[str, set[str]] = {
        "users": {"email", "api_key", "deepseek_api_key"},
        "candidate_profiles": {"email", "api_key", "deepseek_api_key"},
    }
    for table, forbidden in forbidden_columns.items():
        if table not in tables:
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        leaked = sorted(columns & forbidden)
        if leaked:
            errors.append(f"{table} contains forbidden columns: {leaked}")

    counts: dict[str, int] = {}
    completed_intervals = 0
    invalid_intervals: list[dict[str, object]] = []
    alembic_revision = ""
    with factory() as db:
        model_map = {
            "users": User,
            "profiles": CandidateProfile,
            "resumes": Resume,
            "jobs": Job,
            "recommendations": Recommendation,
            "discovery_runs": DiscoveryRun,
            "source_status_rows": DiscoverySourceStatus,
            "application_packs": ApplicationPack,
            "application_events": ApplicationEvent,
            "ai_usage_rows": AIUsage,
        }
        for name, model in model_map.items():
            try:
                counts[name] = int(db.scalar(select(func.count(model.id))) or 0)
            except Exception as exc:
                errors.append(f"count failed for {name}: {type(exc).__name__}")
        if "alembic_version" in tables:
            alembic_revision = str(db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar() or "")
            if args.require_alembic_head and alembic_revision != args.require_alembic_head:
                errors.append(
                    f"alembic revision {alembic_revision!r} does not equal required head {args.require_alembic_head!r}"
                )
        profiles = db.scalars(
            select(CandidateProfile).where(
                CandidateProfile.last_discovery_at.is_not(None),
                CandidateProfile.next_discovery_at.is_not(None),
            )
        ).all()
        for profile in profiles:
            completed_intervals += 1
            delta = profile.next_discovery_at - profile.last_discovery_at
            if delta != timedelta(hours=6):
                invalid_intervals.append({"user_id": profile.user_id, "seconds": int(delta.total_seconds())})
        if invalid_intervals:
            errors.append("one or more completed discovery intervals are not exactly six hours")

    passed = not errors
    result = {
        "verdict": "PASS" if passed else "FAIL",
        "scope": "read-only schema, aggregate counts, Alembic identity, tenant schema and exact six-hour refresh invariant",
        "production_claimed": settings.app_env == "production" and passed,
        "app_version": settings.app_version,
        "refresh_interval_hours": settings.discovery_refresh_hours,
        "alembic_revision": alembic_revision,
        "counts": counts,
        "completed_refresh_intervals_checked": completed_intervals,
        "invalid_refresh_intervals": invalid_intervals,
        "errors": errors,
        "sensitive_values_read": False,
    }
    text_out = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text_out, encoding="utf-8")
    print(text_out, end="")
    engine.dispose()
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
