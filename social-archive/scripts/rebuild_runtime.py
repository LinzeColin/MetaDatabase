from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from social_archive.recovery import RecoveryBundleError, load_recovery_bundle, rebuild_runtime_projection


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild a fresh Social Archive Runtime SQLite projection from a verified recovery bundle")
    parser.add_argument("recovery_root", help="directory containing verified snapshot.json and facts.ndjson")
    parser.add_argument("--target", required=True, help="new SQLite path; an existing path is never overwritten")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    recovery_root = Path(args.recovery_root).resolve()
    target = Path(args.target).resolve()
    try:
        if args.verify_only:
            facts = load_recovery_bundle(recovery_root)
            print(json.dumps({"status": "PASS", "mode": "verify_only", "fact_count": len(facts)}, ensure_ascii=False))
            return 0
        report = rebuild_runtime_projection(recovery_root, target)
    except (OSError, RecoveryBundleError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"status": "FAIL", "error_code": "RUNTIME_REBUILD_REJECTED", "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "mode": "rebuild", "target": str(target), **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
