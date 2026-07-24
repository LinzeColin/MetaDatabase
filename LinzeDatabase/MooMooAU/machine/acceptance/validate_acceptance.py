#!/usr/bin/env python3
"""Validate final Acceptance evidence structurally or require every pass gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT_FROM_SCRIPT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FROM_SCRIPT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FROM_SCRIPT))

from machine.acceptance.evidence import (  # noqa: E402
    EXPECTED_ACCEPTANCE_IDS,
    PROJECT_ROOT,
    AcceptanceEvidenceError,
    evaluate_acceptance,
    evaluate_all,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--acceptance-id", choices=EXPECTED_ACCEPTANCE_IDS)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    try:
        results = (
            (evaluate_acceptance(args.acceptance_id, args.root),)
            if args.acceptance_id is not None
            else evaluate_all(args.root)
        )
    except (AcceptanceEvidenceError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "moomooau.acceptance-validation-result.v1",
                    "status": "INVALID",
                    "errors": [f"{type(exc).__name__}:{exc}"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    invalid = [item for item in results if not item.valid]
    blocked = [item for item in results if not item.passed]
    status = "INVALID" if invalid else ("PASS" if not blocked else "BLOCKED")
    payload = {
        "schema_version": "moomooau.acceptance-validation-result.v1",
        "status": status,
        "structurally_valid": len(results) - len(invalid),
        "passed": len(results) - len(blocked),
        "blocked": len(blocked),
        "invalid": len(invalid),
        "results": [
            {
                "acceptance_id": item.acceptance_id,
                "valid": item.valid,
                "passed": item.passed,
                "acceptance_status": item.acceptance_status,
                "oracle_status": item.oracle_status,
                "blockers": list(item.blockers),
                "errors": list(item.errors),
                "evidence_path": item.evidence_path,
            }
            for item in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if invalid:
        return 2
    if args.require_pass and blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
