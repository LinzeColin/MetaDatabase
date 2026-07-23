#!/usr/bin/env python3
"""Build or check the deterministic final Acceptance evidence bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT_FROM_SCRIPT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FROM_SCRIPT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FROM_SCRIPT))

from machine.acceptance.evidence import PROJECT_ROOT, build_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--observed-at-utc", required=True)
    parser.add_argument("--remediation-base-commit", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    bundle = build_bundle(
        root,
        observed_at_utc=args.observed_at_utc,
        remediation_base_commit=args.remediation_base_commit,
    )
    mismatches: list[str] = []
    for relative, rendered in bundle.items():
        path = root / relative
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif (
            not path.is_file() or path.is_symlink() or path.read_text(encoding="utf-8") != rendered
        ):
            mismatches.append(relative.as_posix())
    output = {
        "schema_version": "moomooau.acceptance-build-result.v1",
        "mode": "write" if args.write else "check",
        "status": "PASS" if not mismatches else "FAIL",
        "records": len(bundle) - 1,
        "summary": "evidence/acceptance/latest.json",
        "mismatches": mismatches,
        "external_effects": 0,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
