#!/usr/bin/env python3
"""Post-release 7x24 continuity monitor for the v0.1.0 monitoring obligations.

CURRENT.yaml `post_release_monitoring` converts the three evidence windows
into standing obligations; this tool is the single command a monitoring
cycle runs to check all of them and report gaps HONESTLY (a missing hour is
reported as a gap, never papered over):

- cloud hourly heartbeat (S10PBT02 adjunct): every UTC hour from the anchor
  (first heartbeat 2026-07-16T07:00Z) must have a completed
  `health_heartbeat` row in GET /v1/cloud/runs.
- cloud daily SEC cron (S10PBT02): one `cron:0 18 * * *` row per UTC day
  from 2026-07-16; `failed` is a violation, `partial` a warning.
- local A204 probe chain (S11PAT01): `refresh_stability_probe` jobs advance
  through the window; a queued probe past grace is a stall; heartbeat
  verification_ok=false is a violation.
- local daily collection chain (S7PDT02): `sec_incremental_sync` must keep a
  queued next occurrence (self-reschedule alive, not overdue) and the latest
  non-drill ingestion_run must not be failed.

Exit 0 = HEALTHY (warnings allowed), 2 = VIOLATIONS. `--evidence-dir DIR`
writes the JSON report into DIR/monitoring/ for the runtime evidence store.

Usage:
  python scripts/monitor_release_continuity.py
  python scripts/monitor_release_continuity.py --evidence-dir ~/Documents/Codex/runtime_evidence/EEI
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

SCHEMA_VERSION = "release-continuity-monitor-v1"
DEFAULT_BASE_URL = "https://eei.linzezhang.com"
# Zone bot protection 403s unlabeled clients; monitoring declares itself.
USER_AGENT = "EEI-continuity-monitor/0.1 (linzezhang35@gmail.com)"

HEARTBEAT_ANCHOR = datetime(2026, 7, 16, 7, 0, tzinfo=UTC)
DAILY_CLOUD_CRON_FIRST_DAY = datetime(2026, 7, 16, 18, 0, tzinfo=UTC)
HEARTBEAT_GRACE = timedelta(minutes=10)
DAILY_CRON_GRACE = timedelta(minutes=45)
PROBE_GRACE = timedelta(minutes=30)
LOCAL_DAILY_GRACE = timedelta(hours=2)
DRILL_SOURCE_CODE = "sec_edgar_drill"


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_cloud_runs(base_url: str, since: datetime, limit: int = 500) -> list[dict[str, Any]]:
    url = f"{base_url}/v1/cloud/runs?limit={limit}&since={since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def check_cloud_heartbeats(runs: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    completed_hours: set[str] = set()
    failed_rows: list[dict[str, Any]] = []
    for run in runs:
        if (run.get("scope") or {}).get("kind") != "health_heartbeat":
            continue
        hour_key = parse_ts(run["started_at"]).strftime("%Y-%m-%dT%H:00Z")
        if run.get("status") == "completed":
            completed_hours.add(hour_key)
        else:
            failed_rows.append({"hour": hour_key, "status": run.get("status")})
    expected: list[str] = []
    cursor = HEARTBEAT_ANCHOR
    while cursor + HEARTBEAT_GRACE <= now:
        expected.append(cursor.strftime("%Y-%m-%dT%H:00Z"))
        cursor += timedelta(hours=1)
    missing = [hour for hour in expected if hour not in completed_hours]
    return {
        "anchor": HEARTBEAT_ANCHOR.strftime("%Y-%m-%dT%H:%MZ"),
        "expected_hours": len(expected),
        "completed_hours": len([hour for hour in expected if hour in completed_hours]),
        "missing_hours": missing,
        "failed_rows": failed_rows,
    }


def check_cloud_daily_cron(runs: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    rows: dict[str, str] = {}
    for run in runs:
        if run.get("trigger") != "cron:0 18 * * *":
            continue
        day_key = parse_ts(run["started_at"]).strftime("%Y-%m-%d")
        # Keep the best status seen for the day (completed > partial > failed).
        rank = {"completed": 3, "partial": 2, "failed": 1}
        if rank.get(run.get("status"), 0) >= rank.get(rows.get(day_key), 0):
            rows[day_key] = run.get("status")
    expected_days: list[str] = []
    cursor = DAILY_CLOUD_CRON_FIRST_DAY
    while cursor + DAILY_CRON_GRACE <= now:
        expected_days.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    missing = [day for day in expected_days if day not in rows]
    return {
        "expected_days": expected_days,
        "day_statuses": rows,
        "missing_days": missing,
        "failed_days": [d for d, s in rows.items() if s == "failed"],
        "partial_days": [d for d, s in rows.items() if s == "partial"],
    }


def check_probe_chain(
    connection: psycopg.Connection[dict[str, Any]], now: datetime
) -> dict[str, Any]:
    jobs = connection.execute(
        """
        SELECT payload->>'window_id' AS window_id, payload->>'probe_no' AS probe_no,
               status, scheduled_for, finished_at, last_error_class
        FROM background_jobs
        WHERE job_type = 'refresh_stability_probe'
        ORDER BY scheduled_for
        """
    ).fetchall()
    heartbeats = connection.execute(
        """
        SELECT diff->>'probe_no' AS probe_no,
               diff->'verification'->>'ok' AS verification_ok,
               occurred_at
        FROM operation_logs
        WHERE action_type = 'refresh_stability_probe'
        ORDER BY occurred_at
        """
    ).fetchall()
    stalled: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    succeeded = 0
    for job in jobs:
        if job["status"] == "succeeded":
            succeeded += 1
        elif job["status"] == "queued" and job["scheduled_for"] + PROBE_GRACE < now:
            stalled.append(
                {
                    "probe_no": job["probe_no"],
                    "scheduled_for": job["scheduled_for"].isoformat(),
                    "overdue_minutes": round((now - job["scheduled_for"]).total_seconds() / 60),
                }
            )
        elif job["status"] in {"failed", "dead_letter"}:
            failed.append(
                {
                    "probe_no": job["probe_no"],
                    "status": job["status"],
                    "error_class": job["last_error_class"],
                }
            )
    bad_verifications = [
        {"probe_no": hb["probe_no"], "occurred_at": hb["occurred_at"].isoformat()}
        for hb in heartbeats
        if hb["verification_ok"] == "false"
    ]
    return {
        "window_id": jobs[-1]["window_id"] if jobs else None,
        "jobs_total": len(jobs),
        "succeeded": succeeded,
        "queued": len([j for j in jobs if j["status"] == "queued"]),
        "stalled": stalled,
        "failed": failed,
        "bad_verifications": bad_verifications,
    }


def check_local_daily_chain(
    connection: psycopg.Connection[dict[str, Any]], now: datetime
) -> dict[str, Any]:
    runs = connection.execute(
        """
        SELECT ir.started_at, ir.status, ir.error_class, s.code AS source_code
        FROM ingestion_runs ir JOIN sources s ON s.id = ir.source_id
        WHERE ir.connector_version LIKE 'sec-incremental%%'
        ORDER BY ir.started_at DESC LIMIT 30
        """
    ).fetchall()
    production_runs = [r for r in runs if r["source_code"] != DRILL_SOURCE_CODE]
    latest = production_runs[0] if production_runs else None
    next_jobs = connection.execute(
        """
        SELECT scheduled_for, status FROM background_jobs
        WHERE job_type = 'sec_incremental_sync' AND status = 'queued'
        ORDER BY scheduled_for LIMIT 1
        """
    ).fetchall()
    next_job = next_jobs[0] if next_jobs else None
    return {
        "latest_production_run": (
            {
                "started_at": latest["started_at"].isoformat(),
                "status": latest["status"],
                "error_class": latest["error_class"],
            }
            if latest
            else None
        ),
        "production_runs_seen": len(production_runs),
        "next_queued_for": next_job["scheduled_for"].isoformat() if next_job else None,
        "next_overdue": bool(next_job and next_job["scheduled_for"] + LOCAL_DAILY_GRACE < now),
        "reschedule_chain_alive": next_job is not None,
    }


def build_report(base_url: str) -> dict[str, Any]:
    now = utc_now()
    violations: list[str] = []
    warnings: list[str] = []

    cloud_error: str | None = None
    heartbeat: dict[str, Any] = {}
    daily_cloud: dict[str, Any] = {}
    try:
        runs = fetch_cloud_runs(base_url, since=HEARTBEAT_ANCHOR - timedelta(hours=1))
        heartbeat = check_cloud_heartbeats(runs, now)
        daily_cloud = check_cloud_daily_cron(runs, now)
    except Exception as exc:  # noqa: BLE001 - the failure itself is the finding
        cloud_error = f"{type(exc).__name__}: {exc}"
        violations.append(f"cloud_runs_unreachable: {cloud_error}")

    if heartbeat.get("missing_hours"):
        violations.append(f"heartbeat_gap: missing hours {heartbeat['missing_hours']}")
    if heartbeat.get("failed_rows"):
        violations.append(f"heartbeat_failed_rows: {heartbeat['failed_rows']}")
    if daily_cloud.get("missing_days"):
        violations.append(f"cloud_daily_cron_missing: {daily_cloud['missing_days']}")
    if daily_cloud.get("failed_days"):
        violations.append(f"cloud_daily_cron_failed: {daily_cloud['failed_days']}")
    if daily_cloud.get("partial_days"):
        warnings.append(f"cloud_daily_cron_partial: {daily_cloud['partial_days']}")

    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as connection:
        probe = check_probe_chain(connection, now)
        local_daily = check_local_daily_chain(connection, now)

    if probe["stalled"]:
        violations.append(f"probe_stalled: {probe['stalled']}")
    if probe["failed"]:
        violations.append(f"probe_failed: {probe['failed']}")
    if probe["bad_verifications"]:
        violations.append(f"probe_verification_failed: {probe['bad_verifications']}")
    if latest := local_daily.get("latest_production_run"):
        if latest["status"] == "failed":
            violations.append(f"local_daily_latest_failed: {latest}")
    if not local_daily["reschedule_chain_alive"]:
        violations.append("local_daily_chain_dead: no queued sec_incremental_sync job")
    elif local_daily["next_overdue"]:
        violations.append(
            f"local_daily_overdue: queued for {local_daily['next_queued_for']} not picked up"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now.isoformat(),
        "base_url": base_url,
        "cloud": {
            "fetch_error": cloud_error,
            "hourly_heartbeat": heartbeat,
            "daily_sec_cron": daily_cloud,
        },
        "local": {"probe_chain_s11pat01": probe, "daily_collection_s7pdt02": local_daily},
        "warnings": warnings,
        "violations": violations,
        "verdict": "VIOLATIONS" if violations else "HEALTHY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--evidence-dir",
        help="runtime evidence root (e.g. ~/Documents/Codex/runtime_evidence/EEI); "
        "writes monitoring/continuity_<UTC>.json when given",
    )
    args = parser.parse_args()

    report = build_report(args.base_url)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if args.evidence_dir:
        out_dir = Path(args.evidence_dir).expanduser() / "monitoring"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = parse_ts(report["checked_at"]).strftime("%Y%m%dT%H%M%SZ")
        out_path = out_dir / f"continuity_{stamp}.json"
        out_path.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
        print(f"[monitor] report written: {out_path}", file=sys.stderr)
    return 0 if report["verdict"] == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
