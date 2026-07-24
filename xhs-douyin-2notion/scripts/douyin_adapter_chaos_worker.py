#!/usr/bin/env python3
"""Abrupt-process worker for the public synthetic Douyin adapter chaos lane."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIDECAR_WORKER = PROJECT_ROOT / "scripts/douyin_sidecar_fixture_worker.py"
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.douyin_adapter import DouyinAdapter  # noqa: E402
from x2n_companion.douyin_upstream import (  # noqa: E402
    DouyinBatchRequest,
    PinnedDouyinClient,
    SubprocessDouyinTransport,
    synthetic_attestation,
)
from x2n_companion.runtime import RuntimePaths  # noqa: E402


NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kill-label", required=True)
    parser.add_argument("--mode", choices=("favorites", "likes"), required=True)
    parser.add_argument("--scan-id", required=True)
    args = parser.parse_args()
    parsed = uuid.UUID(args.scan_id)
    if str(parsed) != args.scan_id:
        return 2

    client = PinnedDouyinClient(
        SubprocessDouyinTransport((sys.executable, "-B", str(SIDECAR_WORKER), "--case", "normal")),
        expected_build=synthetic_attestation(),
        allow_synthetic=True,
        timeout_seconds=2.0,
    )
    _health, batch = client.fetch_owner_batch(DouyinBatchRequest(mode=args.mode, sequence=0))
    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)

    def abrupt_exit(label: str) -> None:
        if label == args.kill_label:
            os._exit(79)

    offset = 0 if args.mode == "favorites" else 1
    DouyinAdapter(
        CanonicalStore(paths, busy_timeout_ms=30_000),
        fault_injector=abrupt_exit,
    ).commit_batch(
        args.scan_id,
        batch,
        observed_at=NOW + timedelta(minutes=offset, seconds=1),
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
