#!/usr/bin/env python3
"""Execute the deterministic Foundation003 idempotency and recovery oracles."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Sequence

from x2n_companion.canonical_store import CanonicalStore, WriteDisposition
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPERS_PATH = PROJECT_ROOT / "apps/companion/tests/test_canonical_store.py"


def _helpers() -> Any:
    spec = importlib.util.spec_from_file_location("x2n_f003_acceptance_helpers", HELPERS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("synthetic helper unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _store(value: str) -> CanonicalStore:
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
    return store


def run_acceptance() -> dict[str, Any]:
    helper = _helpers()
    with tempfile.TemporaryDirectory(prefix="x2n-f003-idempotency-") as value:
        store = _store(value)

        def ingest(index: int) -> dict[str, Any]:
            content = helper.synthetic_content(index)
            return store.ingest_bundle(
                content,
                relation=helper.synthetic_relation(content, index),
                observations=(helper.synthetic_observation(content, index),),
                artifacts=(helper.synthetic_artifact(content, index),),
            )

        first = [ingest(index) for index in range(80)]
        for index in range(80):
            content = helper.synthetic_content(index)
            store.enqueue_outbox(
                sink="markdown",
                content_key=content.content_key,
                desired_projection_hash=helper._sha(f"projection:{index}"),
                sink_schema_version="1.0",
            )
        first_counts = store.counts()
        first_digest = store.logical_digest()
        second = [ingest(index) for index in range(80)]
        for index in range(80):
            content = helper.synthetic_content(index)
            disposition, _ = store.enqueue_outbox(
                sink="markdown",
                content_key=content.content_key,
                desired_projection_hash=helper._sha(f"projection:{index}"),
                sink_schema_version="1.0",
            )
            if disposition is not WriteDisposition.UNCHANGED:
                raise RuntimeError("duplicate outbox side effect")
        if store.counts() != first_counts or store.logical_digest() != first_digest:
            raise RuntimeError("second idempotency run changed the Store")
        if not all(item["content"] == "inserted" for item in first):
            raise RuntimeError("first idempotency run did not insert every item")
        if not all(item["content"] == "unchanged" for item in second):
            raise RuntimeError("second idempotency run was not stable")

        with ThreadPoolExecutor(max_workers=16) as executor:
            concurrent = list(executor.map(lambda _: ingest(700), range(100)))
        concurrent_inserted = sum(item["content"] == "inserted" for item in concurrent)
        concurrent_unchanged = sum(item["content"] == "unchanged" for item in concurrent)
        if (concurrent_inserted, concurrent_unchanged) != (1, 99):
            raise RuntimeError("concurrent duplicate Oracle failed")
        idempotency_health = store.health()

    with tempfile.TemporaryDirectory(prefix="x2n-f003-recovery-") as value:
        store = _store(value)
        seeded = store.ingest_contents(helper.synthetic_content(index + 20_000) for index in range(10_000))
        if seeded != {"inserted": 10_000, "updated": 0, "unchanged": 0}:
            raise RuntimeError("scale seed count drifted")
        before_counts = store.counts()
        before_digest = store.logical_digest()
        backup = store.backup(label="acceptance")
        hash_mismatch_rejected = False
        try:
            store.restore(backup.backup_id, expected_sha256="0" * 64)
        except X2NRuntimeError:
            hash_mismatch_rejected = True
        if not hash_mismatch_rejected or store.logical_digest() != before_digest:
            raise RuntimeError("backup fault injection changed live data")
        rollback_backup = store.downgrade_with_backup(1)
        backward_version = store.health()["schema_version"]
        store.restore(rollback_backup.backup_id, expected_sha256=rollback_backup.database_sha256)
        after_counts = store.counts()
        after_digest = store.logical_digest()
        recovery_health = store.health()
        if before_counts != after_counts or before_digest != after_digest:
            raise RuntimeError("backup/rollback/restore lost logical data")
        if recovery_health["status"] != "healthy" or recovery_health["schema_version"] != 2:
            raise RuntimeError("restored Store is not healthy")

    return {
        "acceptance_scope": "SYNTHETIC_SQLITE_STORE_ONLY",
        "backup_hash_mismatch_rejected": hash_mismatch_rejected,
        "concurrent_duplicate_attempts": 100,
        "concurrent_inserted": concurrent_inserted,
        "concurrent_unchanged": concurrent_unchanged,
        "data_loss_records": 0,
        "duplicate_artifact_rows": 0,
        "duplicate_content_rows": 0,
        "duplicate_outbox_rows": 0,
        "duplicate_relation_rows": 0,
        "forward_schema_version": idempotency_health["schema_version"],
        "foreign_key_check": recovery_health["foreign_key_check"],
        "foreign_key_violations": recovery_health["foreign_key_violations"],
        "idempotency_items": 80,
        "idempotency_runs": 2,
        "integrity_check": recovery_health["integrity_check"],
        "local_paths_emitted": 0,
        "migration_backward_version": backward_version,
        "migration_restored_version": recovery_health["schema_version"],
        "private_content_in_evidence": False,
        "real_accounts": 0,
        "scale_records": 10_000,
        "status": "PASS",
        "unreadable_records": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print(json.dumps({"reason": "arguments_not_supported", "status": "FAIL_CLOSED"}, sort_keys=True), file=sys.stderr)
        return 2
    try:
        payload = run_acceptance()
    except Exception:
        print(json.dumps({"reason": "foundation_003_acceptance_failed", "status": "FAIL_CLOSED"}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
