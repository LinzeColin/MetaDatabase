#!/usr/bin/env python3
"""Generate/check the deterministic public Canonical Store schema snapshot."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Sequence

from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.runtime import RuntimePaths


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "machine/schemas/canonical_store_v1.json"


def build_snapshot() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-f003-schema-") as value:
        destination = Path(value) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        root = destination / "xhs-douyin-2notion"
        paths = RuntimePaths.from_values(
            str(root),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        store = CanonicalStore(paths)
        store.initialize()
        snapshot = store.snapshot_schema()
    object_counts = {
        kind: sum(item["type"] == kind for item in snapshot["objects"])
        for kind in ("index", "table", "trigger")
    }
    return {
        "contract_version": "1.0",
        "database_schema_version": snapshot["schema_version"],
        "forbidden_persistent_fields": [
            "cookie",
            "credentials",
            "media_cdn_url",
            "raw_media",
            "token",
        ],
        "migration_set_sha256": snapshot["migration_set_sha256"],
        "object_counts": object_counts,
        "objects": snapshot["objects"],
        "schema_sha256": snapshot["schema_sha256"],
        "schema_version": "1.0",
        "sqlite_mode": {
            "busy_timeout_required": True,
            "foreign_keys": True,
            "integrity_check": "required",
            "journal_mode": "wal",
            "synchronous": "full",
        },
        "truth_source": "local_sqlite_canonical_store",
    }


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render(build_snapshot())
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print(json.dumps({"reason": "schema_snapshot_drift", "status": "FAIL_CLOSED"}, sort_keys=True))
            return 1
        payload = json.loads(expected)
        print(
            json.dumps(
                {
                    "database_schema_version": payload["database_schema_version"],
                    "objects": sum(payload["object_counts"].values()),
                    "status": "PASS",
                },
                sort_keys=True,
            )
        )
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    payload = json.loads(expected)
    print(json.dumps({"objects": sum(payload["object_counts"].values()), "status": "WRITTEN"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
