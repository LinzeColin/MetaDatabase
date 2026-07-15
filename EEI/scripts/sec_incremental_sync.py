#!/usr/bin/env python3
"""S7PDT02: scheduled incremental SEC collection (production-ized).

Job handler `sec_incremental_sync` for the background worker:

- Guards on `sources.active` - a disabled source is skipped, never fetched.
- Fetches the EDGAR submissions recent block for every mapped universe CIK,
  filters filings inside the lookback window and persists them with the same
  idempotent source_documents/raw_source_snapshots discipline as the 2016+
  backfill (dual UNIQUE constraints; index metadata + hashes only).
- Records one ingestion_run per execution: that history IS the run_log for
  the 7-day continuous-collection evidence window.
- Self-reschedules the next daily occurrence on success (idempotency-keyed
  by date, so replays never double-book).
- Source circuit breaker: after three consecutive failed runs for the same
  source+connector the source is auto-disabled (sources.active=false) with a
  system operation_log entry. Drill mode (`drill_force_failure`) exercises the
  full path against a dedicated drill source so production is never touched.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

SCHEMA_VERSION = "sec-incremental-sync-v1"
CONNECTOR_VERSION = "sec-incremental-sync-v1"
DEFAULT_LOOKBACK_DAYS = 3
AUTO_DISABLE_AFTER_CONSECUTIVE_FAILURES = 3
DRILL_SOURCE_CODE = "sec_edgar_drill"


class SecIncrementalSyncError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def consecutive_leading_failures(statuses: list[str]) -> int:
    """Count consecutive 'failed' entries from the most recent run backwards."""
    count = 0
    for status in statuses:
        if status == "failed":
            count += 1
        else:
            break
    return count


def next_occurrence_key(source_code: str, after: datetime) -> tuple[str, datetime]:
    next_at = after + timedelta(days=1)
    return f"sec-incremental-sync:{source_code}:{next_at.date().isoformat()}", next_at


def ensure_source(connection: Any, code: str, name: str, tier: int) -> str:
    row = connection.execute(
        "SELECT id::text FROM sources WHERE code = %s", (code,)
    ).fetchone()
    if row:
        return row[0]
    return connection.execute(
        """
        INSERT INTO sources(code, name, base_url, source_tier, active)
        VALUES (%s, %s, %s, %s, true)
        RETURNING id::text
        """,
        (code, name, "https://www.sec.gov/", tier),
    ).fetchone()[0]


def source_state(connection: Any, code: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT id::text, active FROM sources WHERE code = %s", (code,)
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "active": bool(row[1])}


def recent_run_statuses(connection: Any, source_id: str, limit: int = 10) -> list[str]:
    rows = connection.execute(
        """
        SELECT status FROM ingestion_runs
        WHERE source_id = %s AND connector_version = %s
        ORDER BY started_at DESC, id DESC
        LIMIT %s
        """,
        (source_id, CONNECTOR_VERSION, limit),
    ).fetchall()
    return [r[0] for r in rows]


def auto_disable_source(
    connection: Any, *, source_id: str, source_code: str, run_id: str, streak: int
) -> None:
    from psycopg.types.json import Jsonb  # noqa: PLC0415

    connection.execute(
        "UPDATE sources SET active = false WHERE id = %s", (source_id,)
    )
    connection.execute(
        """
        INSERT INTO operation_logs(
          actor, action_type, object_type, object_id, old_value, new_value,
          diff, reason, request_id, result_status
        )
        VALUES ('system', 'source_auto_disabled', 'source', %s, %s, %s, %s, %s, %s,
                'success')
        ON CONFLICT DO NOTHING
        """,
        (
            source_id,
            Jsonb({"active": True}),
            Jsonb({"active": False}),
            Jsonb(
                {
                    "source_code": source_code,
                    "connector_version": CONNECTOR_VERSION,
                    "consecutive_failures": streak,
                    "threshold": AUTO_DISABLE_AFTER_CONSECUTIVE_FAILURES,
                    "triggering_ingestion_run_id": run_id,
                }
            ),
            (
                "Source circuit breaker: three consecutive failed scheduled "
                "collection runs; re-enable requires operator action."
            ),
            f"source-auto-disable:{source_code}:{run_id}",
        ),
    )


async def collect_incremental(
    *, since: str, user_agent: str
) -> tuple[list[tuple[str, int, list[dict[str, Any]]]], int]:
    from app.ingest.sec_client import SecEdgarClient  # noqa: PLC0415

    from scripts.backfill_sec_history import (  # noqa: PLC0415
        filter_filing_entries,
        recent_block_entries,
    )
    from scripts.load_official_ticker_identifiers import RESEARCH_CIK_MAP  # noqa: PLC0415

    per_company: list[tuple[str, int, list[dict[str, Any]]]] = []
    total = 0
    async with SecEdgarClient(user_agent=user_agent) as client:
        for research_id, cik in sorted(RESEARCH_CIK_MAP.items()):
            response = await client.get_submissions(cik)
            entries = recent_block_entries(
                (response.payload.get("filings") or {}).get("recent") or {}
            )
            selected = filter_filing_entries(entries, since=since)
            per_company.append((research_id, cik, selected))
            total += len(selected)
    return per_company, total


def handle_sec_incremental_sync_job(job: dict[str, Any]) -> dict[str, Any]:
    from psycopg.types.json import Jsonb  # noqa: PLC0415

    from scripts.backfill_sec_history import (  # noqa: PLC0415
        PARSER_VERSION as BACKFILL_PARSER_VERSION,
    )
    from scripts.backfill_sec_history import (  # noqa: PLC0415
        build_primary_document_url,
        entry_content_hash,
    )
    from scripts.db_tools import connect_database  # noqa: PLC0415
    from scripts.job_scheduler import enqueue_job  # noqa: PLC0415

    payload = job.get("payload") or {}
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SecIncrementalSyncError(
            f"sec_incremental_sync payload schema_version must be {SCHEMA_VERSION}"
        )
    if payload.get("allow_live_network") is not True:
        raise SecIncrementalSyncError(
            "sec_incremental_sync requires allow_live_network=true in the payload"
        )
    source_code = str(payload.get("source_code") or "sec_edgar")
    drill = bool(payload.get("drill_force_failure"))
    lookback_days = int(payload.get("lookback_days") or DEFAULT_LOOKBACK_DAYS)
    reschedule = payload.get("reschedule_next", True) is True
    started = utc_now()
    since = (started - timedelta(days=lookback_days)).date().isoformat()

    with connect_database() as connection:
        if drill:
            source_id = ensure_source(
                connection, DRILL_SOURCE_CODE, "SEC EDGAR circuit-breaker drill", 5
            )
            source_code = DRILL_SOURCE_CODE
        else:
            state = source_state(connection, source_code)
            if state is None:
                raise SecIncrementalSyncError(f"unknown source: {source_code}")
            source_id = state["id"]
            if not state["active"]:
                return {
                    "handler": "sec_incremental_sync",
                    "status": "source_disabled_skip",
                    "source_code": source_code,
                    "fetch_performed": False,
                }
        state = source_state(connection, source_code)
        if drill and state and not state["active"]:
            return {
                "handler": "sec_incremental_sync",
                "status": "source_disabled_skip",
                "source_code": source_code,
                "fetch_performed": False,
            }
        run_id = connection.execute(
            """
            INSERT INTO ingestion_runs(
              source_id, connector_version, mode, checkpoint, started_at, status, counts
            )
            VALUES (%s, %s, 'live', %s, %s, 'running', %s)
            RETURNING id::text
            """,
            (
                source_id,
                CONNECTOR_VERSION,
                Jsonb({"since": since, "drill": drill, "job_id": str(job.get("id"))}),
                started,
                Jsonb({}),
            ),
        ).fetchone()[0]

    try:
        if drill:
            raise SecIncrementalSyncError("drill_force_failure requested by payload")
        user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
        if not user_agent:
            raise SecIncrementalSyncError("SEC_USER_AGENT is required for live sync")
        per_company, total_selected = asyncio.run(
            collect_incremental(since=since, user_agent=user_agent)
        )
        inserted_documents = 0
        skipped_documents = 0
        inserted_snapshots = 0
        with connect_database() as connection:
            for research_id, cik, selected in per_company:
                for entry in selected:
                    accession = entry["accessionNumber"]
                    content_hash = entry_content_hash(cik, entry)
                    url = build_primary_document_url(
                        cik, accession, entry.get("primaryDocument")
                    )
                    title = f"{research_id} {entry.get('form')} {entry.get('filingDate')} ({accession})"
                    doc_row = connection.execute(
                        """
                        INSERT INTO source_documents(
                          source_id, external_id, url, title, publisher, document_date,
                          observed_at, retrieved_at, content_hash, media_type,
                          parser_version
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'text/html', %s)
                        ON CONFLICT (source_id, external_id, content_hash) DO NOTHING
                        RETURNING id::text
                        """,
                        (
                            source_id,
                            accession,
                            url,
                            title,
                            "U.S. Securities and Exchange Commission (EDGAR)",
                            entry.get("filingDate"),
                            entry.get("filingDate"),
                            started,
                            content_hash,
                            BACKFILL_PARSER_VERSION,
                        ),
                    ).fetchone()
                    if doc_row:
                        document_id = doc_row[0]
                        inserted_documents += 1
                    else:
                        document_id = connection.execute(
                            """
                            SELECT id::text FROM source_documents
                            WHERE source_id = %s AND external_id = %s
                              AND content_hash = %s
                            """,
                            (source_id, accession, content_hash),
                        ).fetchone()[0]
                        skipped_documents += 1
                    snapshot_row = connection.execute(
                        """
                        INSERT INTO raw_source_snapshots(
                          ingestion_run_id, source_document_id, anchor_id, source_url,
                          source_date, publisher, title, evidence_scope, record_mode,
                          validation_status, parser_version, content_hash, raw_payload,
                          retrieved_at, review_status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s,
                                'sec incremental sync (scheduled collection)', 'live',
                                'verified_official_index', %s, %s, %s, %s,
                                'machine_verified')
                        ON CONFLICT (anchor_id, content_hash) DO NOTHING
                        RETURNING id
                        """,
                        (
                            run_id,
                            document_id,
                            f"SEC-SYNC-{cik}-{accession}",
                            url,
                            entry.get("filingDate"),
                            "U.S. Securities and Exchange Commission (EDGAR)",
                            title,
                            BACKFILL_PARSER_VERSION,
                            content_hash,
                            Jsonb({"cik": cik, "research_id": research_id, **entry}),
                            started,
                        ),
                    ).fetchone()
                    if snapshot_row:
                        inserted_snapshots += 1
            counts = {
                "since": since,
                "filings_in_window": total_selected,
                "documents_inserted": inserted_documents,
                "documents_skipped_existing": skipped_documents,
                "snapshots_inserted": inserted_snapshots,
            }
            connection.execute(
                """
                UPDATE ingestion_runs
                SET status = 'succeeded', finished_at = %s, counts = %s
                WHERE id = %s
                """,
                (utc_now(), Jsonb(counts), run_id),
            )
        next_key = None
        if reschedule:
            next_key, next_at = next_occurrence_key(source_code, started)
            queued = enqueue_job(
                job_type="sec_incremental_sync",
                idempotency_key=next_key,
                payload=dict(payload),
                scheduled_for=next_at,
                metadata={"self_rescheduled_from": str(job.get("id"))},
            )
            if queued.get("status") in {"dead_letter", "failed", "succeeded", "cancelled"}:
                # Idempotency key collided with a terminal job (e.g. an operator-
                # enqueued run that dead-lettered). The daily chain must never die
                # on a collision: enqueue under a rescue key instead.
                next_key = f"{next_key}:{started.strftime('%H%M%S')}"
                enqueue_job(
                    job_type="sec_incremental_sync",
                    idempotency_key=next_key,
                    payload=dict(payload),
                    scheduled_for=next_at,
                    metadata={
                        "self_rescheduled_from": str(job.get("id")),
                        "rescue_key_reason": f"collision with terminal job {queued.get('id')}",
                    },
                )
        return {
            "handler": "sec_incremental_sync",
            "status": "succeeded",
            "source_code": source_code,
            "ingestion_run_id": run_id,
            "next_occurrence_key": next_key,
            **counts,
        }
    except Exception as exc:
        with connect_database() as connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET status = 'failed', finished_at = %s,
                    error_class = %s, error_message = %s
                WHERE id = %s
                """,
                (utc_now(), type(exc).__name__, str(exc)[:400], run_id),
            )
            statuses = recent_run_statuses(connection, source_id)
            streak = consecutive_leading_failures(statuses)
            if streak >= AUTO_DISABLE_AFTER_CONSECUTIVE_FAILURES:
                auto_disable_source(
                    connection,
                    source_id=source_id,
                    source_code=source_code,
                    run_id=run_id,
                    streak=streak,
                )
        raise
