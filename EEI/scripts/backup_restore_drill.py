#!/usr/bin/env python3
"""S7PDT03: data preservation - automated backup, restore drill, capacity report.

The stop condition for S7PD is explicit: "备份未演练即宣称可恢复" is forbidden.
So this script never claims restorability without proving it in the same run:

1. pg_dump (custom format) of the production EEI database to a timestamped
   file outside the repository.
2. Restore drill into a throwaway database (dropped and recreated every run),
   then row-count parity verification across every public table.
3. Capacity report: per-table row counts and on-disk sizes, database total,
   backup file size, and the raw-snapshot dedupe policy facts (dual UNIQUE
   constraints) that bound growth.

Exit code is non-zero unless the restore drill parity check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database, database_url  # noqa: E402

SCHEMA_VERSION = "eei-backup-restore-drill-v1"
TASK_ID = "S7PDT03"
ACCEPTANCE_IDS = ["ACC-S7PDT03"]
DRILL_DB_NAME = "eei_restore_drill"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def replace_db(url: str, db_name: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{db_name}"))


PG_CONTAINER_SERVICE = "postgres"


def run_pg(args: list[str], *, stdout_path: Path | None = None,
           stdin_path: Path | None = None) -> subprocess.CompletedProcess:
    """Run a postgres client tool inside the compose postgres container."""
    cmd = ["docker", "compose", "exec", "-T", PG_CONTAINER_SERVICE, *args]
    stdout_handle = stdout_path.open("wb") if stdout_path else subprocess.PIPE
    stdin_handle = stdin_path.open("rb") if stdin_path else None
    try:
        return subprocess.run(
            cmd,
            stdout=stdout_handle,
            stderr=subprocess.PIPE,
            stdin=stdin_handle,
            text=stdout_path is None,
            cwd=str(ROOT),
        )
    finally:
        if stdout_path:
            stdout_handle.close()
        if stdin_handle:
            stdin_handle.close()


def table_row_counts(url: str) -> dict[str, int]:
    import psycopg  # noqa: PLC0415

    with psycopg.connect(url, connect_timeout=5) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            ).fetchall()
        ]
        counts = {}
        for table in tables:
            counts[table] = conn.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0]
        return counts


def capacity_snapshot() -> dict[str, object]:
    with connect_database() as conn:
        db_size = conn.execute(
            "SELECT pg_database_size(current_database())"
        ).fetchone()[0]
        tables = conn.execute(
            """
            SELECT c.relname,
                   pg_total_relation_size(c.oid) AS bytes,
                   COALESCE(s.n_live_tup, 0) AS approx_rows
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 15
            """
        ).fetchall()
    return {
        "database_bytes": int(db_size),
        "database_pretty_mb": round(int(db_size) / 1024 / 1024, 2),
        "largest_tables": [
            {"table": r[0], "bytes": int(r[1]), "approx_rows": int(r[2])}
            for r in tables
        ],
        "growth_controls": {
            "raw_snapshot_dedupe": "UNIQUE (anchor_id, content_hash) on raw_source_snapshots",
            "document_dedupe": "UNIQUE (source_id, external_id, content_hash) on source_documents",
            "job_idempotency": "UNIQUE (job_type, idempotency_key) on background_jobs",
            "raw_full_text_policy": (
                "Full source texts and JSON archives stay outside the repository "
                "and outside the database (runtime_evidence), hash-pinned; the DB "
                "stores index metadata, hashes and excerpts only."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    url = database_url()
    parts = urlparse(url)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = args.backup_dir / f"eei-backup-{stamp}.dump"

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now_iso(),
        "backup_path": str(backup_path),
    }

    container_db = urlparse(url).path.lstrip("/") or "eei"
    container_user = urlparse(url).username or "eei"
    dump = run_pg(
        ["pg_dump", "--format=custom", "--no-owner", "-U", container_user,
         "-d", container_db],
        stdout_path=backup_path,
    )
    if dump.returncode != 0:
        report["status"] = "backup_failed"
        report["error"] = dump.stderr[-400:]
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": "backup_failed"}, indent=2))
        return 1
    report["backup_bytes"] = backup_path.stat().st_size

    drill_url = replace_db(url, DRILL_DB_NAME)
    drop = run_pg(["psql", "-U", container_user, "-d", "postgres",
                   "-v", "ON_ERROR_STOP=1", "-c",
                   f'DROP DATABASE IF EXISTS "{DRILL_DB_NAME}" WITH (FORCE)'])
    create = run_pg(["psql", "-U", container_user, "-d", "postgres",
                     "-v", "ON_ERROR_STOP=1", "-c",
                     f'CREATE DATABASE "{DRILL_DB_NAME}"'])
    if drop.returncode != 0 or create.returncode != 0:
        report["status"] = "drill_db_setup_failed"
        report["error"] = (drop.stderr + create.stderr)[-400:]
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": "drill_db_setup_failed"}, indent=2))
        return 1

    restore = run_pg(
        ["pg_restore", "--no-owner", "-U", container_user, "-d", DRILL_DB_NAME],
        stdin_path=backup_path,
    )
    restore_warnings = restore.stderr[-400:] if restore.stderr else ""

    source_counts = table_row_counts(url)
    drill_counts = table_row_counts(drill_url)
    mismatches = {
        table: {"source": source_counts[table], "restored": drill_counts.get(table)}
        for table in source_counts
        if drill_counts.get(table) != source_counts[table]
    }
    parity = not mismatches and set(drill_counts) == set(source_counts)

    run_pg(["psql", "-U", container_user, "-d", "postgres", "-c",
            f'DROP DATABASE IF EXISTS "{DRILL_DB_NAME}" WITH (FORCE)'])

    report.update(
        {
            "status": "restore_drill_passed" if parity else "restore_drill_failed",
            "restore_returncode": restore.returncode,
            "restore_stderr_tail": restore_warnings,
            "tables_compared": len(source_counts),
            "rows_total_source": sum(source_counts.values()),
            "rows_total_restored": sum(drill_counts.values()),
            "count_mismatches": mismatches,
            "row_count_parity": parity,
            "capacity": capacity_snapshot(),
            "restore_claim": (
                "Restorability PROVEN in this run via full pg_restore into a "
                "throwaway database with row-count parity across all public tables."
                if parity
                else "Restore drill FAILED - restorability must not be claimed."
            ),
        }
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "backup_mb": round(report["backup_bytes"] / 1024 / 1024, 2),
                "tables_compared": report["tables_compared"],
                "rows_total_source": report["rows_total_source"],
                "row_count_parity": parity,
            },
            indent=2,
        )
    )
    return 0 if parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
