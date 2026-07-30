#!/usr/bin/env python3
"""Deterministic, offline shadow comparator; it cannot promote a candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_companion.douyin_upstream import (  # noqa: E402
    PROTOCOL_VERSION,
    UPSTREAM_COMMIT,
    UPSTREAM_LICENSE,
    UPSTREAM_TREE,
    UPSTREAM_VERSION,
    evaluate_shadow_candidate,
)


OBSERVED_SHADOW_COMMIT = "2e373df6fe474368804909f337fd26ee5139ce5d"
OBSERVED_SHADOW_TREE = "faa5b5c700b1eb39a2318cb8867f4ac8898c6fbf"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate(name: str) -> dict[str, object]:
    if name == "approved-pin":
        return {
            "commit": UPSTREAM_COMMIT,
            "critical_files_match": True,
            "license": UPSTREAM_LICENSE,
            "protocol_version": PROTOCOL_VERSION,
            "resolved_lock_sha256": _digest("x2n-a004-approved-pin-synthetic-shadow-lock"),
            "sbom_sha256": _digest("x2n-a004-approved-pin-synthetic-shadow-sbom"),
            "transitive_licenses_compatible": True,
            "tree": UPSTREAM_TREE,
            "version": UPSTREAM_VERSION,
        }
    return {
        "commit": OBSERVED_SHADOW_COMMIT,
        "critical_files_match": False,
        "license": UPSTREAM_LICENSE,
        "protocol_version": PROTOCOL_VERSION,
        "resolved_lock_sha256": _digest("x2n-a004-shadow-lock-not-produced"),
        "sbom_sha256": _digest("x2n-a004-shadow-sbom-not-produced"),
        "transitive_licenses_compatible": False,
        "tree": OBSERVED_SHADOW_TREE,
        "version": UPSTREAM_VERSION,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Douyin pin shadow comparator")
    parser.add_argument("--fixture", choices=("approved-pin", "observed-current"), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    decision = evaluate_shadow_candidate(_candidate(args.fixture)).safe_dict()
    payload = {
        "fixture": args.fixture,
        "network_calls": 0,
        "owner_authorization": "NOT_RUN",
        "platform_calls": 0,
        "private_path_emitted": False,
        "schema_version": "1.0",
        "shadow": decision,
        "status": "PASS",
        "task_id": "TSK.x2n.adapters.004",
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
