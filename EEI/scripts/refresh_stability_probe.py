#!/usr/bin/env python3
"""S11PAT01 / ACC-A204: 4h/24h refresh-stability probe.

Self-rescheduling background job (docker worker executes it) that proves
the data/scoring pointer refresh stays transactional over a 24h window:

- every cycle it VERIFIES the previous cycle's enqueued jobs completed and
  the active analysis context invariants held (exactly one active global
  context; refresh_generation monotonic; refresh_token rotated after a
  completed refresh), then ENQUEUES a fresh data_snapshot_refresh +
  score_recompute pair using the CURRENT refresh token (exercising the
  stale-client guard on purpose), writes an operation_logs heartbeat, and
  reschedules itself +interval until the window is complete.
- conflicts and failures are recorded honestly in the heartbeat; the probe
  never repairs state.

CLI (host side):
  python scripts/refresh_stability_probe.py --seed        # start a window
  python scripts/refresh_stability_probe.py --status      # window progress
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

SCHEMA_VERSION = "refresh-stability-probe-v1"
JOB_TYPE = "refresh_stability_probe"
DEFAULT_INTERVAL_HOURS = 4
DEFAULT_TOTAL_PROBES = 7  # 0h..24h inclusive at 4h cadence
PROBE_ACTOR = "system"


def utc_now() -> datetime:
    return datetime.now(UTC)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required for the refresh stability probe")
    return url


def connect() -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(database_url(), connect_timeout=5, row_factory=dict_row)


def load_active_context(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT context_key, refresh_token::text AS refresh_token, refresh_generation,
               active_scoring_profile_version_id, active_data_snapshot_id, status
        FROM active_analysis_contexts
        WHERE context_key = 'global'
        """
    ).fetchall()
    return {
        "row_count": len(rows),
        "context": rows[0] if rows else None,
    }


def job_status(
    connection: psycopg.Connection[dict[str, Any]], job_id: str | None
) -> dict[str, Any] | None:
    if not job_id:
        return None
    row = connection.execute(
        "SELECT id, job_type, status, attempt_count, last_error_class"
        " FROM background_jobs WHERE id = %s",
        (job_id,),
    ).fetchone()
    if row is None:
        return {"id": job_id, "status": "missing"}
    return {k: (str(v) if k == "id" else v) for k, v in row.items()}


def verify_previous_cycle(
    connection: psycopg.Connection[dict[str, Any]],
    previous: dict[str, Any] | None,
    context_now: dict[str, Any],
) -> dict[str, Any]:
    if not previous:
        return {"checked": False, "reason": "first_probe"}
    checks: dict[str, Any] = {"checked": True, "violations": []}
    refresh_job = job_status(connection, previous.get("refresh_job_id"))
    recompute_job = job_status(connection, previous.get("recompute_job_id"))
    checks["previous_refresh_job"] = refresh_job
    checks["previous_recompute_job"] = recompute_job
    for label, job in (("data_snapshot_refresh", refresh_job), ("score_recompute", recompute_job)):
        if job is None:
            continue  # previous cycle hit a conflict and enqueued nothing
        if job.get("status") != "completed":
            checks["violations"].append(f"previous_{label}_not_completed:{job.get('status')}")
    row = context_now["context"]
    if context_now["row_count"] != 1:
        checks["violations"].append(f"active_global_context_count:{context_now['row_count']}")
    previous_generation = previous.get("refresh_generation")
    if row is not None and previous_generation is not None:
        if int(row["refresh_generation"]) < int(previous_generation):
            checks["violations"].append(
                f"refresh_generation_regressed:{previous_generation}->{row['refresh_generation']}"
            )
        if (
            refresh_job is not None
            and refresh_job.get("status") == "completed"
            and int(row["refresh_generation"]) == int(previous_generation)
            and previous.get("refresh_token") == row["refresh_token"]
        ):
            checks["violations"].append("completed_refresh_left_pointer_unchanged")
    checks["ok"] = not checks["violations"]
    return checks


def write_heartbeat(
    connection: psycopg.Connection[dict[str, Any]],
    *,
    window_id: str,
    probe_no: int,
    detail: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO operation_logs(
          actor, action_type, object_type, object_id,
          old_value, new_value, diff, reason, result_status
        ) VALUES (
          %s, 'refresh_stability_probe', 'active_analysis_context',
          NULL, NULL, NULL, %s, %s, %s
        )
        """,
        (
            PROBE_ACTOR,
            Jsonb(detail),
            f"A204 refresh stability probe {probe_no} window {window_id}",
            "success" if detail.get("verification", {}).get("ok", True) else "violation",
        ),
    )


def enqueue_probe_job(
    *,
    window_id: str,
    probe_no: int,
    run_at: datetime,
    payload_extra: dict[str, Any],
) -> dict[str, Any]:
    from scripts.job_scheduler import enqueue_job

    idempotency_key = f"refresh-stability:{window_id}:{probe_no}"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "window_id": window_id,
        "probe_no": probe_no,
        **payload_extra,
    }
    queued = enqueue_job(
        job_type=JOB_TYPE,
        idempotency_key=idempotency_key,
        payload=payload,
        scheduled_for=run_at,
        metadata={"probe_window": window_id},
    )
    if queued.get("status") in {"dead_letter", "failed", "succeeded", "cancelled", "completed"}:
        # Terminal-key collision must never kill the probe chain (same
        # rescue doctrine as sec_incremental_sync).
        rescue_key = f"{idempotency_key}:rescue:{uuid.uuid4().hex[:8]}"
        queued = enqueue_job(
            job_type=JOB_TYPE,
            idempotency_key=rescue_key,
            payload=payload,
            scheduled_for=run_at,
            metadata={"probe_window": window_id, "rescue_key_reason": "terminal collision"},
        )
        queued["rescued"] = True
    return {
        "job_id": str(queued.get("id")),
        "status": queued.get("status"),
        "scheduled_for": str(queued.get("scheduled_for")),
        "rescued": queued.get("rescued", False),
    }


def handle_refresh_stability_probe_job(job: dict[str, Any]) -> dict[str, Any]:
    from app.domain_repository import DomainRepository

    payload = job.get("payload") or {}
    window_id = str(payload.get("window_id"))
    probe_no = int(payload.get("probe_no", 0))
    interval_hours = int(payload.get("interval_hours", DEFAULT_INTERVAL_HOURS))
    total_probes = int(payload.get("total_probes", DEFAULT_TOTAL_PROBES))
    previous = payload.get("previous") or None

    repository = DomainRepository(database_url=database_url())
    started = utc_now()

    with connect() as connection:
        context_now = load_active_context(connection)
        verification = verify_previous_cycle(connection, previous, context_now)
        connection.commit()

    current = context_now["context"]
    current_token = str(current["refresh_token"]) if current else None
    current_generation = int(current["refresh_generation"]) if current else None

    refresh_receipt: dict[str, Any] | None = None
    recompute_receipt: dict[str, Any] | None = None
    enqueue_status = "enqueued"
    try:
        refresh_response = repository.enqueue_data_snapshot_refresh(
            expected_active_profile_version_id=None,
            client_refresh_token=current_token,
            scope="global",
            record_mode="live",
            reason=f"A204 stability probe {probe_no} window {window_id}",
            actor=PROBE_ACTOR,
        )
        refresh_receipt = {
            "status": refresh_response.get("status"),
            "job_id": (refresh_response.get("job") or {}).get("id"),
        }
        recompute_response = repository.enqueue_score_recompute(
            expected_active_profile_version_id=None,
            client_refresh_token=current_token,
            scope="global",
            reason=f"A204 stability probe {probe_no} window {window_id}",
            actor=PROBE_ACTOR,
        )
        recompute_receipt = {
            "status": recompute_response.get("status"),
            "job_id": (recompute_response.get("job") or {}).get("id"),
        }
        conflicted = "conflict" in {
            refresh_response.get("status"),
            recompute_response.get("status"),
        }
        if conflicted:
            enqueue_status = "conflict_observed"
    except Exception as exc:  # noqa: BLE001 - recorded honestly, probe must not crash the chain
        enqueue_status = f"enqueue_error:{exc.__class__.__name__}"

    heartbeat = {
        "schema_version": SCHEMA_VERSION,
        "window_id": window_id,
        "probe_no": probe_no,
        "started_at": started.isoformat(),
        "context_now": {
            "row_count": context_now["row_count"],
            "refresh_token": current_token,
            "refresh_generation": current_generation,
        },
        "verification": verification,
        "enqueue_status": enqueue_status,
        "refresh_receipt": refresh_receipt,
        "recompute_receipt": recompute_receipt,
    }

    next_probe: dict[str, Any] | None = None
    window_complete = probe_no + 1 >= total_probes
    with connect() as connection:
        write_heartbeat(connection, window_id=window_id, probe_no=probe_no, detail=heartbeat)
        connection.commit()
    if not window_complete:
        next_probe = enqueue_probe_job(
            window_id=window_id,
            probe_no=probe_no + 1,
            run_at=started + timedelta(hours=interval_hours),
            payload_extra={
                "interval_hours": interval_hours,
                "total_probes": total_probes,
                "previous": {
                    "refresh_job_id": (refresh_receipt or {}).get("job_id"),
                    "recompute_job_id": (recompute_receipt or {}).get("job_id"),
                    "refresh_token": current_token,
                    "refresh_generation": current_generation,
                },
            },
        )

    return {
        "handler_contract": SCHEMA_VERSION,
        "window_id": window_id,
        "probe_no": probe_no,
        "verification_ok": verification.get("ok", True),
        "violations": verification.get("violations", []),
        "enqueue_status": enqueue_status,
        "window_complete": window_complete,
        "next_probe": next_probe,
    }


def seed_window(interval_hours: int, total_probes: int) -> dict[str, Any]:
    window_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    receipt = enqueue_probe_job(
        window_id=window_id,
        probe_no=0,
        run_at=utc_now(),
        payload_extra={"interval_hours": interval_hours, "total_probes": total_probes},
    )
    return {"window_id": window_id, "first_job": receipt}


def window_status() -> dict[str, Any]:
    with connect() as connection:
        jobs = connection.execute(
            """
            SELECT payload->>'window_id' AS window_id, payload->>'probe_no' AS probe_no,
                   status, scheduled_for, finished_at
            FROM background_jobs
            WHERE job_type = %s
            ORDER BY scheduled_for
            """,
            (JOB_TYPE,),
        ).fetchall()
        heartbeats = connection.execute(
            """
            SELECT diff->>'probe_no' AS probe_no, diff->'verification'->>'ok' AS verification_ok,
                   diff->>'enqueue_status' AS enqueue_status, occurred_at
            FROM operation_logs
            WHERE action_type = 'refresh_stability_probe'
            ORDER BY occurred_at
            """
        ).fetchall()
    return {
        "jobs": [
            {
                **row,
                "scheduled_for": row["scheduled_for"].isoformat(),
                "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
            }
            for row in jobs
        ],
        "heartbeats": [
            {**row, "occurred_at": row["occurred_at"].isoformat()} for row in heartbeats
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="seed a new 24h probe window")
    parser.add_argument("--status", action="store_true", help="show probe window progress")
    parser.add_argument("--interval-hours", type=int, default=DEFAULT_INTERVAL_HOURS)
    parser.add_argument("--total-probes", type=int, default=DEFAULT_TOTAL_PROBES)
    args = parser.parse_args()
    if args.seed:
        seeded = seed_window(args.interval_hours, args.total_probes)
        print(json.dumps(seeded, ensure_ascii=False, indent=1))
        return 0
    if args.status:
        print(json.dumps(window_status(), ensure_ascii=False, indent=1, default=str))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
