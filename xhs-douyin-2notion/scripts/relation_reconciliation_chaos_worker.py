#!/usr/bin/env python3
"""One-shot process-kill worker for relation reconciliation acceptance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.relation_reconciliation import ReconciliationManifest, RelationReconciler
from x2n_companion.runtime import RuntimePaths


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Kill one synthetic reconciliation transaction")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--kill-label", required=True)
    args = parser.parse_args()
    manifest = ReconciliationManifest.from_mapping(json.loads(args.manifest.read_text(encoding="utf-8")))
    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)

    def kill(label: str) -> None:
        if label == args.kill_label:
            os._exit(79)

    RelationReconciler(CanonicalStore(paths, busy_timeout_ms=30_000), fault_injector=kill).process(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
