from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_db(path: Path) -> dict[str, object]:
    """Read one explicitly named snapshot and return aggregate schema evidence."""
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        table_rows: dict[str, object] = {}
        for table in tables:
            safe = '"' + table.replace('"', '""') + '"'
            count = connection.execute(f"SELECT COUNT(*) FROM {safe}").fetchone()[0]
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({safe})")]
            table_rows[table] = {"row_count": count, "columns": columns}
        digest = sha256(path)
        return {"sha256": digest, "tables": table_rows}
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect an explicitly supplied, owner-authorized legacy SQLite snapshot.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--snapshot", type=Path, help="One owner-authorized SQLite snapshot. Recursive discovery is forbidden.")
    parser.add_argument("--dry-run", action="store_true", help="Read-only aggregate inspection; emits no repository report.")
    parser.add_argument("--run-contract", help="Required for any future migration write; must name the dedicated data-migration Run Contract.")
    args = parser.parse_args()

    if not args.snapshot:
        print(json.dumps({"status": "BLOCKED", "reason": "EXPLICIT_OWNER_AUTHORIZED_SNAPSHOT_REQUIRED"}, ensure_ascii=False))
        return 2
    snapshot = args.snapshot.resolve()
    if not snapshot.is_file() or snapshot.is_symlink():
        print(json.dumps({"status": "BLOCKED", "reason": "SNAPSHOT_MUST_BE_A_REGULAR_FILE"}, ensure_ascii=False))
        return 2
    if not args.dry_run:
        print(json.dumps({"status": "BLOCKED", "reason": "RAW_SQLITE_EXPORT_FORBIDDEN_USE_PRIVATE_DATABASE_RUN_CONTRACT", "run_contract_supplied": bool(args.run_contract)}, ensure_ascii=False))
        return 2

    try:
        report = inspect_db(snapshot)
    except (OSError, sqlite3.DatabaseError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": "SNAPSHOT_UNREADABLE", "error_type": type(exc).__name__}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "READ_ONLY_AGGREGATE", "dry_run": True, "report": report, "repository_write": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
