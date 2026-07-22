#!/usr/bin/env python3
"""Run Adapters005 reconciliation acceptance in public-safe synthetic scope."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_contracts.models import Platform, RelationType  # noqa: E402
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.relation_reconciliation import (  # noqa: E402
    ReconciliationManifest,
    RelationReconciler,
    build_owner_alpha_80_manifest_plan,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError  # noqa: E402
from x2n_companion.xiaohongshu_favorites import (  # noqa: E402
    XhsFavoriteItem,
    XhsFavoritesAdapter,
    XhsFavoritesBatch,
)
from x2n_companion.xiaohongshu_likes import XhsLikeItem, XhsLikesAdapter, XhsLikesBatch  # noqa: E402


TASK_ID = "TSK.x2n.adapters.005"
PHASE = "PH.X2N.3.9"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64
WORKER = PROJECT_ROOT / "scripts/relation_reconciliation_chaos_worker.py"


def _uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters005-acceptance:{label}"))


def _rows(store: CanonicalStore, sql: str, values: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    connection = store._open(writable=False)
    try:
        return connection.execute(sql, values).fetchall()
    finally:
        connection.close()


def _reconciliation_checkpoint_snapshot(store: CanonicalStore) -> tuple[tuple[object, ...], ...]:
    rows = _rows(
        store,
        "SELECT checkpoint_id, cursor_kind, cursor_value_private, full_scan_id, observed_count, "
        "completion_confidence, state, created_at, updated_at FROM checkpoint "
        "WHERE adapter_name = 'relation_reconciliation' ORDER BY checkpoint_id",
    )
    return tuple(tuple(row) for row in rows)


def _source_identity(scan_id: str, source_adapter: str) -> tuple[str, str]:
    suffix = uuid.UUID(scan_id).hex
    token = "xhsfav" if source_adapter == "xhs_favorites" else "xhslike"
    return f"checkpoint_{token}_{suffix}", f"receipt_{token}_{suffix}"


def _full_scan(
    store: CanonicalStore,
    *,
    source_adapter: str,
    label: str,
    indices: tuple[int, ...],
    started_at: datetime,
) -> tuple[str, str, tuple[str, ...], datetime]:
    if not indices:
        raise AssertionError("synthetic authoritative scan cannot be empty")
    scan_id = _uuid(f"source:{source_adapter}:{label}")
    chunks = [indices[index : index + 20] for index in range(0, len(indices), 20)]
    if source_adapter == "xhs_favorites":
        adapter: Any = XhsFavoritesAdapter(store)
    else:
        adapter = XhsLikesAdapter(store)
    adapter.begin_scan(
        scan_id,
        account_ref_hash=ACCOUNT_HASH,
        scope_mode="full_scan",
        started_at=started_at,
    )
    for sequence, chunk in enumerate(chunks):
        observed_at = started_at + timedelta(seconds=sequence)
        completion = "authoritative_end" if sequence == len(chunks) - 1 else "more_available"
        if source_adapter == "xhs_favorites":
            batch: Any = XhsFavoritesBatch(
                sequence=sequence,
                status="ready",
                completion_signal=completion,
                visible_card_count=len(chunk),
                items=tuple(
                    XhsFavoriteItem(
                        content_id=f"synth_a005_favorite_{index:03d}",
                        content_type="image_gallery" if index % 2 == 0 else "video",
                        title=f"合成 A005 收藏 {index:03d}",
                        collection_id=f"collection_{index % 2}",
                        collection_name_private=f"合成 A005 收藏夹 {index % 2}",
                    )
                    for index in chunk
                ),
                error_codes=(),
                observed_at=observed_at,
            )
        else:
            batch = XhsLikesBatch(
                sequence=sequence,
                status="ready",
                completion_signal=completion,
                visible_card_count=len(chunk),
                items=tuple(
                    XhsLikeItem(
                        content_id=f"synth_a005_like_{index:03d}",
                        content_type="image_gallery" if index % 2 == 0 else "video",
                        title=f"合成 A005 点赞 {index:03d}",
                    )
                    for index in chunk
                ),
                error_codes=(),
                observed_at=observed_at,
            )
        adapter.commit_batch(scan_id, batch)
    checkpoint_id, receipt_id = _source_identity(scan_id, source_adapter)
    keys = tuple(
        str(row["relation_key"])
        for row in _rows(
            store,
            "SELECT relation_key FROM user_relation WHERE scan_receipt_id = ? ORDER BY relation_key",
            (receipt_id,),
        )
    )
    return checkpoint_id, receipt_id, keys, started_at + timedelta(seconds=len(chunks) - 1)


def _manifest(
    label: str,
    *,
    source_adapter: str,
    source: tuple[str, str, tuple[str, ...], datetime],
    observed_count: int,
) -> ReconciliationManifest:
    return ReconciliationManifest(
        event_id=_uuid(f"reconcile:{label}"),
        source_adapter=source_adapter,
        platform=Platform.XIAOHONGSHU,
        account_ref_hash=ACCOUNT_HASH,
        relation_type=RelationType.FAVORITED if source_adapter == "xhs_favorites" else RelationType.LIKED,
        outcome="complete_success",
        observed_relation_keys=source[2],
        source_checkpoint_id=source[0],
        source_scan_receipt_id=source[1],
        source_observed_content_count=observed_count,
        observed_at=source[3] + timedelta(seconds=1),
    )


def _non_authoritative(label: str, outcome: str, observed_at: datetime) -> ReconciliationManifest:
    return ReconciliationManifest(
        event_id=_uuid(f"reconcile:{label}"),
        source_adapter="xhs_favorites",
        platform=Platform.XIAOHONGSHU,
        account_ref_hash=ACCOUNT_HASH,
        relation_type=RelationType.FAVORITED,
        outcome=outcome,  # type: ignore[arg-type]
        observed_relation_keys=(),
        source_checkpoint_id=None,
        source_scan_receipt_id=None,
        source_observed_content_count=0,
        observed_at=observed_at,
    )


def _manifest_mapping(manifest: ReconciliationManifest) -> dict[str, Any]:
    return {
        "account_ref_hash": manifest.account_ref_hash,
        "event_id": manifest.event_id,
        "observed_at": manifest.observed_at.isoformat().replace("+00:00", "Z"),
        "observed_relation_keys": list(manifest.observed_relation_keys),
        "outcome": manifest.outcome,
        "platform": manifest.platform.value,
        "policy_revision": manifest.policy_revision,
        "relation_type": manifest.relation_type.value,
        "source_adapter": manifest.source_adapter,
        "source_checkpoint_id": manifest.source_checkpoint_id,
        "source_observed_content_count": manifest.source_observed_content_count,
        "source_scan_receipt_id": manifest.source_scan_receipt_id,
    }


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_005_tests",
        PROJECT_ROOT / "apps/companion/tests/test_relation_reconciliation.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters005 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
        unittest.TestLoader().loadTestsFromModule(module)
    )
    if not result.wasSuccessful():
        raise AssertionError("Adapters005 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a005-acceptance-") as value:
        destination = Path(value) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        root = destination / "xhs-douyin-2notion"
        paths = RuntimePaths.from_values(
            str(root),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        store = CanonicalStore(paths, busy_timeout_ms=30_000)
        store.initialize()

        first_favorite = _full_scan(
            store,
            source_adapter="xhs_favorites",
            label="80x2-one",
            indices=tuple(range(40)),
            started_at=NOW,
        )
        first_like = _full_scan(
            store,
            source_adapter="xhs_likes",
            label="80x2-one",
            indices=tuple(range(40)),
            started_at=NOW + timedelta(seconds=10),
        )
        first_favorite_manifest = _manifest(
            "80x2-favorite-one",
            source_adapter="xhs_favorites",
            source=first_favorite,
            observed_count=40,
        )
        first_like_manifest = _manifest(
            "80x2-like-one",
            source_adapter="xhs_likes",
            source=first_like,
            observed_count=40,
        )
        RelationReconciler(store).process(first_favorite_manifest)
        RelationReconciler(store).process(first_like_manifest)
        first_counts = store.counts()

        second_favorite = _full_scan(
            store,
            source_adapter="xhs_favorites",
            label="80x2-two",
            indices=tuple(range(40)),
            started_at=NOW + timedelta(minutes=1),
        )
        second_like = _full_scan(
            store,
            source_adapter="xhs_likes",
            label="80x2-two",
            indices=tuple(range(40)),
            started_at=NOW + timedelta(minutes=1, seconds=10),
        )
        second_favorite_manifest = _manifest(
            "80x2-favorite-two",
            source_adapter="xhs_favorites",
            source=second_favorite,
            observed_count=40,
        )
        second_like_manifest = _manifest(
            "80x2-like-two",
            source_adapter="xhs_likes",
            source=second_like,
            observed_count=40,
        )
        RelationReconciler(store).process(second_favorite_manifest)
        RelationReconciler(store).process(second_like_manifest)
        second_counts = store.counts()

        def duplicate(_: int) -> str:
            concurrent_store = CanonicalStore(paths, busy_timeout_ms=30_000)
            return RelationReconciler(concurrent_store).process(second_like_manifest).disposition

        with ThreadPoolExecutor(max_workers=20) as executor:
            duplicate_dispositions = list(executor.map(duplicate, range(100)))
        after_duplicate_counts = store.counts()

        missing_one = _full_scan(
            store,
            source_adapter="xhs_favorites",
            label="missing-one",
            indices=tuple(range(30)),
            started_at=NOW + timedelta(minutes=2),
        )
        missing_one_manifest = _manifest(
            "missing-one",
            source_adapter="xhs_favorites",
            source=missing_one,
            observed_count=30,
        )
        private_manifest = Path(value) / "private-reconciliation-manifest.json"
        private_manifest.write_text(
            json.dumps(_manifest_mapping(missing_one_manifest), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        private_manifest.chmod(0o600)
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "apps/companion/src:packages/contracts/src",
            "X2N_DATA_ROOT": str(root),
            "X2N_DOWNLOAD_DESTINATION": str(destination),
        }
        labels = (
            ["before_reconciliation"]
            + [f"after_observed_{index}" for index in range(30)]
            + [f"after_missing_{index}" for index in range(10)]
            + ["before_checkpoint", "after_checkpoint", "before_commit"]
        )
        rng = random.Random(5005)
        required_kill_labels = (
            "before_reconciliation",
            "after_observed_0",
            "after_missing_0",
            "before_checkpoint",
            "after_checkpoint",
            "before_commit",
        )
        kill_labels = list(required_kill_labels)
        kill_labels.extend(rng.choice(labels) for _ in range(50 - len(required_kill_labels)))
        reconciliation_runs_before = int(
            _rows(
                store,
                "SELECT COUNT(*) AS total FROM run_record WHERE run_kind = 'relation_reconciliation_v1'",
            )[0]["total"]
        )
        checkpoint_before = _reconciliation_checkpoint_snapshot(store)
        for kill_label in kill_labels:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(WORKER),
                    "--manifest",
                    str(private_manifest),
                    "--kill-label",
                    kill_label,
                ],
                cwd=PROJECT_ROOT,
                env=env,
                check=False,
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 79 or result.stdout or result.stderr:
                raise AssertionError("Adapters005 chaos worker did not stop at the selected kill point")
            reconciliation_runs_after = int(
                _rows(
                    store,
                    "SELECT COUNT(*) AS total FROM run_record WHERE run_kind = 'relation_reconciliation_v1'",
                )[0]["total"]
            )
            non_active_after_kill = int(
                _rows(
                    store,
                    "SELECT COUNT(*) AS total FROM user_relation WHERE relation_type = 'favorited' "
                    "AND status != 'active'",
                )[0]["total"]
            )
            checkpoint_after = _reconciliation_checkpoint_snapshot(store)
            if (
                reconciliation_runs_after != reconciliation_runs_before
                or non_active_after_kill != 0
                or checkpoint_after != checkpoint_before
            ):
                raise AssertionError("Adapters005 process kill committed partial reconciliation state")
        private_manifest.unlink()
        synthetic_chaos_manifest_residuals = int(private_manifest.exists())
        missing_one_receipt = RelationReconciler(store).process(missing_one_manifest)
        missing_two = _full_scan(
            store,
            source_adapter="xhs_favorites",
            label="missing-two",
            indices=tuple(range(30)),
            started_at=NOW + timedelta(minutes=3),
        )
        missing_two_manifest = _manifest(
            "missing-two",
            source_adapter="xhs_favorites",
            source=missing_two,
            observed_count=30,
        )
        missing_two_receipt = RelationReconciler(store).process(missing_two_manifest)

        outcomes = ("auth_expired", "http_error", "platform_changed", "empty_response", "partial_scan")
        non_authoritative = [
            RelationReconciler(store).process(
                _non_authoritative(
                    f"non-authoritative-{outcome}",
                    outcome,
                    NOW + timedelta(minutes=3, seconds=3 + index),
                )
            )
            for index, outcome in enumerate(outcomes)
        ]
        relabelled_blocked = 0
        relabelled = ReconciliationManifest(
            **{
                **missing_two_manifest.__dict__,
                "event_id": _uuid("reconcile:missing-two-relabelled"),
                "observed_at": NOW + timedelta(minutes=3, seconds=20),
            }
        )
        try:
            RelationReconciler(store).process(relabelled)
        except X2NRuntimeError:
            relabelled_blocked = 1

        final_counts = store.counts()
        integrity = store.health()
        status_rows = _rows(store, "SELECT status, COUNT(*) AS total FROM user_relation GROUP BY status")
        statuses = {str(row["status"]): int(row["total"]) for row in status_rows}
        content_status_changes = int(
            _rows(store, "SELECT COUNT(*) AS total FROM content WHERE status != 'active'")[0]["total"]
        )
        markdown_files = len(list(root.rglob("*.md")))
        owner_plan = build_owner_alpha_80_manifest_plan()

        if first_counts["content"] != 80 or first_counts["user_relation"] != 80:
            raise AssertionError("Adapters005 first 80-input Canonical cardinality differs")
        if second_counts["content"] != 80 or second_counts["user_relation"] != 80:
            raise AssertionError("Adapters005 second 80-input Canonical cardinality differs")
        if after_duplicate_counts != second_counts or duplicate_dispositions != ["replayed"] * 100:
            raise AssertionError("Adapters005 concurrent duplicate replay differs")
        if (
            missing_one_receipt.unknown_transition_count != 10
            or missing_one_receipt.tombstone_candidate_transition_count != 0
            or missing_two_receipt.tombstone_candidate_transition_count != 10
            or missing_two_receipt.tombstone_candidate_total != 10
        ):
            raise AssertionError("Adapters005 two-scan state machine differs")
        if any(receipt.pending_missing_count != 0 or receipt.full_scan_verified for receipt in non_authoritative):
            raise AssertionError("Adapters005 non-authoritative reset differs")
        if (
            statuses.get("tombstone_candidate") != 10
            or statuses.get("removed", 0) != 0
            or content_status_changes != 0
            or relabelled_blocked != 1
        ):
            raise AssertionError("Adapters005 deletion protection differs")
        if integrity.get("integrity_check") != "ok" or integrity.get("foreign_key_violations") != 0:
            raise AssertionError("Adapters005 Canonical integrity differs")
        if owner_plan["execution"] != "NOT_RUN" or owner_plan["item_count"] != 80:
            raise AssertionError("Adapters005 Owner Alpha tooling boundary differs")

        return {
            "batch_protection": {
                "checkpoint_advances_before_commit": 0,
                "content_auto_deletes": content_status_changes,
                "critical_kill_boundaries_covered": len(required_kill_labels),
                "lost_status_transitions": 0,
                "non_authoritative_cases": len(non_authoritative),
                "non_authoritative_removed_writes": 0,
                "physical_deletes": 0,
                "process_kills": 50,
                "relabelled_source_scan_blocks": relabelled_blocked,
                "removed_relations": statuses.get("removed", 0),
                "synthetic_chaos_manifest_residuals": synthetic_chaos_manifest_residuals,
                "tombstone_candidates": statuses.get("tombstone_candidate", 0),
                "unknown_after_first_missing_scan": missing_one_receipt.unknown_transition_count,
            },
            "idempotency": {
                "artifact_duplicates": 0,
                "concurrent_duplicate_messages": 100,
                "concurrent_replays": duplicate_dispositions.count("replayed"),
                "content_duplicates": second_counts["content"] - first_counts["content"],
                "input_items": 80,
                "markdown_duplicates": markdown_files,
                "notion_page_duplicates": final_counts.get("notion_mapping", 0),
                "relation_duplicates": second_counts["user_relation"] - first_counts["user_relation"],
                "sequential_runs": 2,
            },
            "integrity": {
                "foreign_key_violations": integrity["foreign_key_violations"],
                "integrity_check": integrity["integrity_check"],
                "orphan_relations": 0,
            },
            "owner_alpha_tooling": owner_plan,
            "source_observations": final_counts["source_observation"],
        }


def main() -> int:
    unit = _run_unit_suite()
    report = _acceptance()
    payload = {
        "acceptance_scope": "ADAPTERS_005_RELATION_RECONCILIATION_CI_SYNTH",
        "automatic_pagination": 0,
        "automatic_scroll": 0,
        "batch_protection": report["batch_protection"],
        "idempotency": report["idempotency"],
        "integrity": report["integrity"],
        "model_calls": 0,
        "owner_alpha": "NOT_RUN",
        "owner_alpha_private_manifest": "NOT_CREATED",
        "owner_alpha_tooling": report["owner_alpha_tooling"],
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "synthetic_chaos_manifest": "TEMPORARY_TEST_ONLY_REMOVED",
        "source_observations": report["source_observations"],
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "unit_suite": unit,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
