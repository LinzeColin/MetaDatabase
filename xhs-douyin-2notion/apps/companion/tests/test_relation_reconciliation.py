from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode, UserRelation
from x2n_contracts.models import ConfirmationSource, Platform, RelationStatus, RelationType

from x2n_companion import runtime_cli
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.relation_reconciliation import (
    ReconciliationManifest,
    RelationReconciler,
    build_owner_alpha_80_manifest_plan,
)
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError
from x2n_companion.xiaohongshu_favorites import XhsFavoriteItem, XhsFavoritesAdapter, XhsFavoritesBatch
from x2n_companion.xiaohongshu_likes import XhsLikeItem, XhsLikesAdapter, XhsLikesBatch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 23, 0, 0, 0, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64


class InjectedKill(BaseException):
    pass


def _uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters005:{label}"))


def _favorite(index: int, *, collection_name: str | None = None) -> XhsFavoriteItem:
    collection = index % 2
    return XhsFavoriteItem(
        content_id=f"synth_reconcile_favorite_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成 reconciliation 收藏 {index:03d}",
        collection_id=f"collection_{collection}",
        collection_name_private=collection_name or f"合成收藏夹 {collection}",
    )


def _like(index: int) -> XhsLikeItem:
    return XhsLikeItem(
        content_id=f"synth_reconcile_like_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成 reconciliation 点赞 {index:03d}",
    )


class RelationReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-adapters005-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths, busy_timeout_ms=30_000)
        self.store.initialize()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _rows(self, sql: str, values: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        connection = self.store._open(writable=False)
        try:
            return connection.execute(sql, values).fetchall()
        finally:
            connection.close()

    @staticmethod
    def _identity(scan_id: str, *, kind: str) -> tuple[str, str]:
        suffix = uuid.UUID(scan_id).hex
        if kind == "favorites":
            return f"checkpoint_xhsfav_{suffix}", f"receipt_xhsfav_{suffix}"
        return f"checkpoint_xhslike_{suffix}", f"receipt_xhslike_{suffix}"

    def _full_favorites(
        self,
        label: str,
        indices: tuple[int, ...],
        *,
        started_at: datetime,
        collection_name: str | None = None,
    ) -> tuple[str, str, tuple[str, ...], datetime]:
        scan_id = _uuid(f"favorite-scan:{label}")
        adapter = XhsFavoritesAdapter(self.store)
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            scope_mode="full_scan",
            started_at=started_at,
        )
        chunks = [indices[index : index + 20] for index in range(0, len(indices), 20)]
        self.assertTrue(chunks)
        for sequence, chunk in enumerate(chunks):
            observed_at = started_at + timedelta(seconds=sequence)
            adapter.commit_batch(
                scan_id,
                XhsFavoritesBatch(
                    sequence=sequence,
                    status="ready",
                    completion_signal="authoritative_end" if sequence == len(chunks) - 1 else "more_available",
                    visible_card_count=len(chunk),
                    items=tuple(_favorite(index, collection_name=collection_name) for index in chunk),
                    error_codes=(),
                    observed_at=observed_at,
                ),
            )
        checkpoint_id, receipt_id = self._identity(scan_id, kind="favorites")
        keys = tuple(
            str(row["relation_key"])
            for row in self._rows(
                "SELECT relation_key FROM user_relation WHERE scan_receipt_id = ? ORDER BY relation_key",
                (receipt_id,),
            )
        )
        return checkpoint_id, receipt_id, keys, started_at + timedelta(seconds=len(chunks) - 1)

    def _full_likes(
        self,
        label: str,
        indices: tuple[int, ...],
        *,
        started_at: datetime,
    ) -> tuple[str, str, tuple[str, ...], datetime]:
        scan_id = _uuid(f"like-scan:{label}")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            scope_mode="full_scan",
            started_at=started_at,
        )
        chunks = [indices[index : index + 20] for index in range(0, len(indices), 20)]
        self.assertTrue(chunks)
        for sequence, chunk in enumerate(chunks):
            observed_at = started_at + timedelta(seconds=sequence)
            adapter.commit_batch(
                scan_id,
                XhsLikesBatch(
                    sequence=sequence,
                    status="ready",
                    completion_signal="authoritative_end" if sequence == len(chunks) - 1 else "more_available",
                    visible_card_count=len(chunk),
                    items=tuple(_like(index) for index in chunk),
                    error_codes=(),
                    observed_at=observed_at,
                ),
            )
        checkpoint_id, receipt_id = self._identity(scan_id, kind="likes")
        keys = tuple(
            str(row["relation_key"])
            for row in self._rows(
                "SELECT relation_key FROM user_relation WHERE scan_receipt_id = ? ORDER BY relation_key",
                (receipt_id,),
            )
        )
        return checkpoint_id, receipt_id, keys, started_at + timedelta(seconds=len(chunks) - 1)

    @staticmethod
    def _complete_manifest(
        label: str,
        *,
        source_adapter: str,
        relation_type: RelationType,
        checkpoint_id: str,
        receipt_id: str,
        keys: tuple[str, ...],
        source_observed_content_count: int,
        observed_at: datetime,
    ) -> ReconciliationManifest:
        return ReconciliationManifest(
            event_id=_uuid(f"event:{label}"),
            source_adapter=source_adapter,
            platform=Platform.XIAOHONGSHU,
            account_ref_hash=ACCOUNT_HASH,
            relation_type=relation_type,
            outcome="complete_success",
            observed_relation_keys=keys,
            source_checkpoint_id=checkpoint_id,
            source_scan_receipt_id=receipt_id,
            source_observed_content_count=source_observed_content_count,
            observed_at=observed_at,
        )

    @staticmethod
    def _non_authoritative(label: str, outcome: str, observed_at: datetime) -> ReconciliationManifest:
        return ReconciliationManifest(
            event_id=_uuid(f"event:{label}"),
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

    def test_two_distinct_complete_missing_scans_only_create_candidates(self) -> None:
        self._full_favorites("baseline", tuple(range(40)), started_at=NOW)
        first = self._full_favorites("missing-one", tuple(range(30)), started_at=NOW + timedelta(minutes=1))
        first_receipt = RelationReconciler(self.store).process(
            self._complete_manifest(
                "missing-one",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=first[0],
                receipt_id=first[1],
                keys=first[2],
                source_observed_content_count=30,
                observed_at=first[3] + timedelta(seconds=1),
            )
        )
        self.assertEqual(first_receipt.unknown_transition_count, 10)
        self.assertEqual(first_receipt.tombstone_candidate_transition_count, 0)
        self.assertEqual(first_receipt.pending_missing_count, 10)

        second = self._full_favorites("missing-two", tuple(range(30)), started_at=NOW + timedelta(minutes=2))
        second_receipt = RelationReconciler(self.store).process(
            self._complete_manifest(
                "missing-two",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=second[0],
                receipt_id=second[1],
                keys=second[2],
                source_observed_content_count=30,
                observed_at=second[3] + timedelta(seconds=1),
            )
        )
        self.assertEqual(second_receipt.tombstone_candidate_transition_count, 10)
        self.assertEqual(second_receipt.tombstone_candidate_total, 10)
        self.assertEqual(second_receipt.pending_missing_count, 0)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'removed'")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM content WHERE status != 'active'")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM content")), 40)

    def test_same_source_full_scan_cannot_be_relabelled_as_a_second_scan(self) -> None:
        self._full_favorites("baseline-relabel", tuple(range(4)), started_at=NOW)
        source = self._full_favorites("relabel", tuple(range(3)), started_at=NOW + timedelta(minutes=1))
        first = self._complete_manifest(
            "relabel-one",
            source_adapter="xhs_favorites",
            relation_type=RelationType.FAVORITED,
            checkpoint_id=source[0],
            receipt_id=source[1],
            keys=source[2],
            source_observed_content_count=3,
            observed_at=source[3] + timedelta(seconds=1),
        )
        RelationReconciler(self.store).process(first)
        relabelled = self._complete_manifest(
            "relabel-two",
            source_adapter="xhs_favorites",
            relation_type=RelationType.FAVORITED,
            checkpoint_id=source[0],
            receipt_id=source[1],
            keys=source[2],
            source_observed_content_count=3,
            observed_at=source[3] + timedelta(seconds=2),
        )
        with self.assertRaises(X2NRuntimeError) as blocked:
            RelationReconciler(self.store).process(relabelled)
        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'unknown'")), 1)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'tombstone_candidate'")), 0)

    def test_five_non_authoritative_outcomes_clear_pending_without_relation_writes(self) -> None:
        self._full_favorites("baseline-errors", tuple(range(4)), started_at=NOW)
        source = self._full_favorites("before-errors", tuple(range(3)), started_at=NOW + timedelta(minutes=1))
        RelationReconciler(self.store).process(
            self._complete_manifest(
                "before-errors",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=source[0],
                receipt_id=source[1],
                keys=source[2],
                source_observed_content_count=3,
                observed_at=source[3] + timedelta(seconds=1),
            )
        )
        before = [(row["relation_key"], row["status"]) for row in self._rows("SELECT * FROM user_relation ORDER BY 1")]
        outcomes = ("auth_expired", "http_error", "platform_changed", "empty_response", "partial_scan")
        for index, outcome in enumerate(outcomes):
            receipt = RelationReconciler(self.store).process(
                self._non_authoritative(
                    f"non-authoritative:{outcome}",
                    outcome,
                    NOW + timedelta(minutes=2, seconds=index),
                )
            )
            self.assertFalse(receipt.full_scan_verified)
            self.assertEqual(receipt.pending_missing_count, 0)
            self.assertEqual(receipt.missing_relation_count, 0)
        after = [(row["relation_key"], row["status"]) for row in self._rows("SELECT * FROM user_relation ORDER BY 1")]
        self.assertEqual(before, after)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'removed'")), 0)

        newer = self._full_favorites("after-errors", tuple(range(3)), started_at=NOW + timedelta(minutes=3))
        receipt = RelationReconciler(self.store).process(
            self._complete_manifest(
                "after-errors",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=newer[0],
                receipt_id=newer[1],
                keys=newer[2],
                source_observed_content_count=3,
                observed_at=newer[3] + timedelta(seconds=1),
            )
        )
        self.assertEqual(receipt.tombstone_candidate_transition_count, 0)
        self.assertEqual(receipt.pending_missing_count, 1)

        restored = self._full_favorites("after-errors-restored", tuple(range(4)), started_at=NOW + timedelta(minutes=4))
        restored_receipt = RelationReconciler(self.store).process(
            self._complete_manifest(
                "after-errors-restored",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=restored[0],
                receipt_id=restored[1],
                keys=restored[2],
                source_observed_content_count=4,
                observed_at=restored[3] + timedelta(seconds=1),
            )
        )
        self.assertEqual(restored_receipt.pending_missing_count, 0)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status != 'active'")), 0)

    def test_incomplete_or_bounded_source_cannot_claim_full_scan(self) -> None:
        scan_id = _uuid("favorite-canary")
        adapter = XhsFavoritesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="canary_20", started_at=NOW)
        adapter.commit_batch(
            scan_id,
            XhsFavoritesBatch(
                sequence=0,
                status="ready",
                completion_signal="bounded_limit_reached",
                visible_card_count=20,
                items=tuple(_favorite(index) for index in range(20)),
                error_codes=(),
                observed_at=NOW,
            ),
        )
        checkpoint_id, receipt_id = self._identity(scan_id, kind="favorites")
        keys = tuple(
            str(row["relation_key"])
            for row in self._rows(
                "SELECT relation_key FROM user_relation WHERE scan_receipt_id = ? ORDER BY relation_key",
                (receipt_id,),
            )
        )
        manifest = self._complete_manifest(
            "bounded",
            source_adapter="xhs_favorites",
            relation_type=RelationType.FAVORITED,
            checkpoint_id=checkpoint_id,
            receipt_id=receipt_id,
            keys=keys,
            source_observed_content_count=20,
            observed_at=NOW + timedelta(seconds=1),
        )
        with self.assertRaises(X2NRuntimeError) as blocked:
            RelationReconciler(self.store).process(manifest)
        self.assertEqual(blocked.exception.code, ErrorCode.PROVENANCE_INCOMPLETE)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status != 'active'")), 0)

    def test_exact_relation_and_observation_graph_is_required(self) -> None:
        source = self._full_favorites("graph", tuple(range(3)), started_at=NOW)
        manifest = self._complete_manifest(
            "graph",
            source_adapter="xhs_favorites",
            relation_type=RelationType.FAVORITED,
            checkpoint_id=source[0],
            receipt_id=source[1],
            keys=source[2][:-1],
            source_observed_content_count=3,
            observed_at=source[3] + timedelta(seconds=1),
        )
        with self.assertRaises(X2NRuntimeError) as blocked:
            RelationReconciler(self.store).process(manifest)
        self.assertEqual(blocked.exception.code, ErrorCode.PROVENANCE_INCOMPLETE)

    def test_exact_event_replay_and_one_hundred_concurrent_duplicates_are_idempotent(self) -> None:
        source = self._full_favorites("concurrency", tuple(range(40)), started_at=NOW)
        manifest = self._complete_manifest(
            "concurrency",
            source_adapter="xhs_favorites",
            relation_type=RelationType.FAVORITED,
            checkpoint_id=source[0],
            receipt_id=source[1],
            keys=source[2],
            source_observed_content_count=40,
            observed_at=source[3] + timedelta(seconds=1),
        )

        def reconcile(_: int) -> Any:
            return RelationReconciler(CanonicalStore(self.paths, busy_timeout_ms=30_000)).process(manifest)

        with ThreadPoolExecutor(max_workers=20) as executor:
            receipts = list(executor.map(reconcile, range(100)))
        dispositions = [receipt.disposition for receipt in receipts]
        self.assertEqual(dispositions.count("applied"), 1)
        self.assertEqual(dispositions.count("replayed"), 99)
        applied = next(receipt for receipt in receipts if receipt.disposition == "applied")
        replay = RelationReconciler(self.store).process(manifest)
        self.assertEqual(replay.disposition, "replayed")
        self.assertEqual(replay.source_full_scan_ref_sha256, applied.source_full_scan_ref_sha256)
        self.assertEqual(replay.source_scan_receipt_ref_sha256, applied.source_scan_receipt_ref_sha256)
        self.assertEqual(len(self._rows("SELECT * FROM content")), 40)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation")), 40)
        self.assertEqual(len(self._rows("SELECT * FROM source_observation")), 40)
        self.assertEqual(len(self._rows("SELECT * FROM run_record WHERE run_kind = 'relation_reconciliation_v1'")), 1)

    def test_same_event_with_different_input_fails_closed(self) -> None:
        self._full_favorites("event-conflict-base", (0,), started_at=NOW)
        original = self._non_authoritative("event-conflict", "http_error", NOW + timedelta(minutes=1))
        RelationReconciler(self.store).process(original)
        conflict = ReconciliationManifest(
            **{
                **original.__dict__,
                "outcome": "partial_scan",
            }
        )
        with self.assertRaises(X2NRuntimeError) as blocked:
            RelationReconciler(self.store).process(conflict)
        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_fault_rolls_back_relation_run_and_checkpoint_atomically(self) -> None:
        self._full_favorites("kill-base", tuple(range(4)), started_at=NOW)
        source = self._full_favorites("kill-source", tuple(range(3)), started_at=NOW + timedelta(minutes=1))
        manifest = self._complete_manifest(
            "kill",
            source_adapter="xhs_favorites",
            relation_type=RelationType.FAVORITED,
            checkpoint_id=source[0],
            receipt_id=source[1],
            keys=source[2],
            source_observed_content_count=3,
            observed_at=source[3] + timedelta(seconds=1),
        )

        def kill(label: str) -> None:
            if label == "after_missing_0":
                raise InjectedKill()

        with self.assertRaises(InjectedKill):
            RelationReconciler(self.store, fault_injector=kill).process(manifest)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status != 'active'")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM run_record WHERE run_kind = 'relation_reconciliation_v1'")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM checkpoint WHERE adapter_name = 'relation_reconciliation'")), 0)

        recovered = RelationReconciler(self.store).process(manifest)
        self.assertEqual(recovered.unknown_transition_count, 1)

    def test_corrupt_private_cursor_blocks_without_relation_change(self) -> None:
        self._full_favorites("corrupt-base", (0,), started_at=NOW)
        first = self._non_authoritative("corrupt-first", "http_error", NOW + timedelta(minutes=1))
        RelationReconciler(self.store).process(first)
        checkpoint = self._rows(
            "SELECT checkpoint_id, cursor_value_private FROM checkpoint WHERE adapter_name = 'relation_reconciliation'"
        )[0]
        with self.store._transaction() as connection:
            connection.execute(
                'UPDATE checkpoint SET cursor_value_private = \'{"schema_version":"corrupt"}\' '
                "WHERE adapter_name = 'relation_reconciliation'"
            )
        with self.assertRaises(X2NRuntimeError) as blocked:
            RelationReconciler(self.store).process(
                self._non_authoritative("corrupt-second", "http_error", NOW + timedelta(minutes=2))
            )
        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status != 'active'")), 0)

        with self.store._transaction() as connection:
            connection.execute(
                "UPDATE checkpoint SET cursor_value_private = ? WHERE checkpoint_id = ?",
                (checkpoint["cursor_value_private"], checkpoint["checkpoint_id"]),
            )
            connection.execute("DELETE FROM checkpoint WHERE checkpoint_id = ?", (checkpoint["checkpoint_id"],))
        with self.assertRaises(X2NRuntimeError) as missing:
            RelationReconciler(self.store).process(first)
        self.assertEqual(missing.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        self.assertEqual(
            len(self._rows("SELECT * FROM checkpoint WHERE adapter_name = 'relation_reconciliation'")),
            0,
        )

    def test_collection_rename_keeps_stable_relation_identity(self) -> None:
        first = self._full_favorites("rename-one", (0,), started_at=NOW, collection_name="旧合成收藏夹")
        first_key = first[2][0]
        second = self._full_favorites(
            "rename-two",
            (0,),
            started_at=NOW + timedelta(minutes=1),
            collection_name="新合成收藏夹",
        )
        self.assertEqual(second[2], (first_key,))
        rows = self._rows("SELECT relation_key, source_collection_name_private FROM user_relation")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["relation_key"], first_key)
        self.assertEqual(rows[0]["source_collection_name_private"], "新合成收藏夹")

    def test_relation_type_scopes_are_independent(self) -> None:
        self._full_favorites("scope-favorite-base", (0, 1), started_at=NOW)
        self._full_likes("scope-like-base", (0, 1), started_at=NOW)
        source = self._full_favorites("scope-favorite-missing", (0,), started_at=NOW + timedelta(minutes=1))
        RelationReconciler(self.store).process(
            self._complete_manifest(
                "scope-favorite-missing",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=source[0],
                receipt_id=source[1],
                keys=source[2],
                source_observed_content_count=1,
                observed_at=source[3] + timedelta(seconds=1),
            )
        )
        self.assertEqual(
            len(self._rows("SELECT * FROM user_relation WHERE relation_type = 'favorited' AND status = 'unknown'")),
            1,
        )
        self.assertEqual(
            {row["status"] for row in self._rows("SELECT status FROM user_relation WHERE relation_type = 'liked'")},
            {"active"},
        )

    def test_removed_relation_is_preserved_and_never_rewritten(self) -> None:
        baseline = self._full_favorites("removed-base", (0, 1), started_at=NOW)
        removed_key = baseline[2][1]
        with self.store._transaction() as connection:
            row = connection.execute(
                "SELECT payload_json FROM user_relation WHERE relation_key = ?", (removed_key,)
            ).fetchone()
            self.assertIsNotNone(row)
            relation = UserRelation.model_validate_json(row["payload_json"])
            removed = relation.model_copy(
                update={
                    "confirmed_by": ConfirmationSource.OWNER,
                    "scan_receipt_id": "receipt_owner_removed_synthetic",
                    "status": RelationStatus.REMOVED,
                }
            )
            self.store._upsert_relation(connection, removed, Platform.XIAOHONGSHU.value, "2026-07-23T00:00:30Z")
        source = self._full_favorites("removed-source", (0,), started_at=NOW + timedelta(minutes=1))
        receipt = RelationReconciler(self.store).process(
            self._complete_manifest(
                "removed",
                source_adapter="xhs_favorites",
                relation_type=RelationType.FAVORITED,
                checkpoint_id=source[0],
                receipt_id=source[1],
                keys=source[2],
                source_observed_content_count=1,
                observed_at=source[3] + timedelta(seconds=1),
            )
        )
        self.assertEqual(receipt.removed_preserved_count, 1)
        row = self._rows(
            "SELECT status, confirmed_by, scan_receipt_id FROM user_relation WHERE relation_key = ?", (removed_key,)
        )[0]
        self.assertEqual((row["status"], row["confirmed_by"]), ("removed", "owner"))
        self.assertEqual(row["scan_receipt_id"], "receipt_owner_removed_synthetic")

        with self.store._transaction() as connection:
            stored = connection.execute(
                "SELECT payload_json FROM user_relation WHERE relation_key = ?", (removed_key,)
            ).fetchone()
            self.assertIsNotNone(stored)
            unauthorized = UserRelation.model_validate_json(stored["payload_json"]).model_copy(
                update={"confirmed_by": ConfirmationSource.SCAN}
            )
            self.store._upsert_relation(
                connection,
                unauthorized,
                Platform.XIAOHONGSHU.value,
                "2026-07-23T00:01:30Z",
            )
        with self.assertRaises(X2NRuntimeError) as blocked:
            RelationReconciler(self.store).process(
                self._non_authoritative("removed-without-owner", "http_error", NOW + timedelta(minutes=2))
            )
        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_owner_alpha_plan_and_cli_are_fixed_nonexecuting_tooling(self) -> None:
        plan = build_owner_alpha_80_manifest_plan()
        self.assertEqual(plan["item_count"], 80)
        self.assertEqual(plan["execution"], "NOT_RUN")
        self.assertEqual(sum(scope["count"] for scope in plan["scopes"]), 80)
        self.assertEqual(plan["platform_calls"], 0)
        self.assertEqual(plan["relation_keys_in_plan"], 0)
        with self.assertRaises(X2NRuntimeError) as blocked:
            build_owner_alpha_80_manifest_plan(79)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

        args = runtime_cli.build_parser().parse_args(["reconcile", "owner-alpha-plan", "--items", "80"])
        receipt = runtime_cli.run(args)
        self.assertEqual(receipt["task_id"], "TSK.x2n.adapters.005")
        self.assertEqual(receipt["real_account_execution"], "NOT_RUN")
        self.assertEqual(receipt["plan"], plan)

    def test_manifest_parser_and_receipt_are_public_safe(self) -> None:
        self._full_favorites("safe-base", (0,), started_at=NOW)
        manifest = self._non_authoritative("safe", "http_error", NOW + timedelta(minutes=1))
        mapped: dict[str, Any] = {
            "account_ref_hash": manifest.account_ref_hash,
            "event_id": manifest.event_id,
            "observed_at": "2026-07-23T00:01:00Z",
            "observed_relation_keys": [],
            "outcome": manifest.outcome,
            "platform": manifest.platform.value,
            "policy_revision": manifest.policy_revision,
            "relation_type": manifest.relation_type.value,
            "source_adapter": manifest.source_adapter,
            "source_checkpoint_id": None,
            "source_observed_content_count": 0,
            "source_scan_receipt_id": None,
        }
        parsed = ReconciliationManifest.from_mapping(mapped)
        receipt = RelationReconciler(self.store).process(parsed).safe_dict()
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        relation_key = str(self._rows("SELECT relation_key FROM user_relation")[0]["relation_key"])
        self.assertNotIn(ACCOUNT_HASH, rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(relation_key, rendered)
        self.assertFalse(receipt["private_path_emitted"])
        self.assertEqual(receipt["physical_deletes"], 0)
        self.assertEqual(receipt["removed_writes"], 0)
        with self.assertRaises(X2NRuntimeError) as blocked:
            ReconciliationManifest.from_mapping({**mapped, "unexpected": True})
        self.assertEqual(blocked.exception.code, ErrorCode.UNKNOWN_FIELD)
        for invalid in (
            {**mapped, "source_adapter": []},
            {**mapped, "outcome": {}},
        ):
            with self.subTest(invalid_field=next(key for key in invalid if invalid[key] != mapped.get(key))):
                with self.assertRaises(X2NRuntimeError) as malformed:
                    ReconciliationManifest.from_mapping(invalid)
                self.assertEqual(malformed.exception.code, ErrorCode.INVALID_INPUT)

    def test_database_integrity_and_physical_delete_guards_remain_active(self) -> None:
        self._full_favorites("integrity", tuple(range(4)), started_at=NOW)
        health = self.store.health()
        self.assertEqual(health["integrity_check"], "ok")
        self.assertEqual(health["foreign_key_violations"], 0)
        with self.assertRaises(X2NRuntimeError) as relation_delete:
            with self.store._transaction() as connection:
                connection.execute("DELETE FROM user_relation")
        self.assertEqual(relation_delete.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        with self.assertRaises(X2NRuntimeError) as content_delete:
            with self.store._transaction() as connection:
                connection.execute("DELETE FROM content")
        self.assertEqual(content_delete.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)


if __name__ == "__main__":
    unittest.main()
