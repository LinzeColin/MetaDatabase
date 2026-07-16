#!/usr/bin/env python3
"""Production-database isolation guard for the live E2E stack.

Usage:
  verify_live_e2e_isolation.py snapshot --out <file>   # before test-e2e-live
  verify_live_e2e_isolation.py compare --against <file> [--report <file>]

`snapshot` records per-table row counts of the PRODUCTION database
(DATABASE_URL from EEI/.env). `compare` re-counts and fails (exit 1) if any
public-table row count changed - proving that a live E2E run touched only the
dedicated eei_e2e database. Born from the 2026-07-16 incident where the live
stack reset the production database.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402


def production_counts() -> dict[str, int]:
    with connect_database() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " ORDER BY tablename"
            ).fetchall()
        ]
        return {
            table: conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--out", type=Path, required=True)
    comp = sub.add_parser("compare")
    comp.add_argument("--against", type=Path, required=True)
    comp.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.command == "snapshot":
        counts = production_counts()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "schema_version": "eei-live-e2e-isolation-guard-v1",
                    "taken_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "tables": counts,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"snapshot": True, "tables": len(counts)}))
        return 0

    before = json.loads(args.against.read_text(encoding="utf-8"))["tables"]
    after = production_counts()
    drifted = {
        table: {"before": before.get(table), "after": after.get(table)}
        for table in sorted(set(before) | set(after))
        if before.get(table) != after.get(table)
    }
    result = {
        "schema_version": "eei-live-e2e-isolation-guard-v1",
        "compared_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "tables_compared": len(set(before) | set(after)),
        "production_untouched": not drifted,
        "drifted_tables": drifted,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({k: result[k] for k in ("tables_compared", "production_untouched")}))
    if drifted:
        print(json.dumps({"drifted_tables": drifted}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
