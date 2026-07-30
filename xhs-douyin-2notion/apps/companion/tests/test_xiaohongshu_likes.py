from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from x2n_contracts import ErrorCode

from x2n_companion import runtime_cli
from x2n_companion.adapter_guard import AdapterExecutionGate
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError
from x2n_companion.xiaohongshu_favorites import XhsFavoriteItem, XhsFavoritesAdapter, XhsFavoritesBatch
from x2n_companion.xiaohongshu_likes import (
    XhsLikeItem,
    XhsLikesAdapter,
    XhsLikesBatch,
    XhsLikesBatchCoordinator,
    build_xhs_likes_canary_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 23, 0, 0, 0, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64


class InjectedKill(BaseException):
    pass


def _scan_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters003:{label}"))


def _item(index: int) -> XhsLikeItem:
    return XhsLikeItem(
        content_id=f"synth_xhs_like_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成点赞条目 {index:03d}",
    )


def _batch(
    sequence: int,
    items: tuple[XhsLikeItem, ...],
    *,
    status: str = "ready",
    completion: str = "more_available",
    errors: tuple[str, ...] = (),
    observed_at: datetime | None = None,
    visible: int | None = None,
) -> XhsLikesBatch:
    return XhsLikesBatch(
        sequence=sequence,
        status=status,  # type: ignore[arg-type]
        completion_signal=completion,  # type: ignore[arg-type]
        visible_card_count=len(items) + len(errors) if visible is None else visible,
        items=items,
        error_codes=errors,
        observed_at=observed_at or NOW + timedelta(minutes=sequence),
    )


class XiaohongshuLikesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-adapters003-")
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

    def test_canary_plan_is_fixed_to_twenty_and_does_not_execute(self) -> None:
        plan = build_xhs_likes_canary_plan()
        rendered = json.dumps(plan, ensure_ascii=False, sort_keys=True)
        self.assertEqual(plan["max_items"], 20)
        self.assertEqual(plan["execution"], "NOT_RUN")
        self.assertFalse(plan["production_enabled"])
        self.assertFalse(plan["automatic_scroll"])
        self.assertFalse(plan["automatic_filing"])
        self.assertFalse(plan["taxonomy_mutation"])
        self.assertEqual(plan["default_inbox_disposition"], "unclassified")
        self.assertNotIn(str(self.root), rendered)
        with self.assertRaises(X2NRuntimeError) as blocked:
            build_xhs_likes_canary_plan(21)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_cli_only_emits_a_nonexecuting_canary_plan(self) -> None:
        args = runtime_cli.build_parser().parse_args(["xhs-likes", "canary-plan", "--max-items", "20"])
        receipt = runtime_cli.run(args)
        self.assertEqual(receipt["task_id"], "TSK.x2n.adapters.003")
        self.assertEqual(receipt["plan"]["execution"], "NOT_RUN")
        self.assertEqual(receipt["real_account_execution"], "NOT_RUN")

    def test_one_hundred_items_enter_inbox_and_finish_at_authoritative_end(self) -> None:
        scan_id = _scan_id("hundred")
        adapter = XhsLikesAdapter(self.store)
        started = adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            scope_mode="full_scan",
            started_at=NOW,
        )
        self.assertEqual(started.next_sequence, 0)
        for sequence in range(5):
            items = tuple(_item(index) for index in range(sequence * 20, sequence * 20 + 20))
            receipt = adapter.commit_batch(
                scan_id,
                _batch(
                    sequence,
                    items,
                    completion="authoritative_end" if sequence == 4 else "more_available",
                ),
            )
        self.assertEqual(receipt.checkpoint_state, "complete")
        self.assertTrue(receipt.full_scan_completed)
        self.assertEqual(receipt.observed_unique_items, 100)
        self.assertEqual(receipt.relation_count, 100)
        self.assertEqual(receipt.observation_count, 100)
        self.assertEqual(len(self._rows("SELECT content_key FROM content")), 100)
        self.assertEqual(
            {row["source_collection_id"] for row in self._rows("SELECT source_collection_id FROM user_relation")},
            {None},
        )
        self.assertEqual(
            {row["relation_type"] for row in self._rows("SELECT relation_type FROM user_relation")}, {"liked"}
        )
        self.assertEqual({row["status"] for row in self._rows("SELECT status FROM user_relation")}, {"active"})
        self.assertEqual(len(self._rows("SELECT * FROM classification")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM taxonomy_category")), 0)

    def test_existing_favorite_content_is_reused_with_an_independent_liked_relation(self) -> None:
        content_id = _item(0).content_id
        favorite = XhsFavoriteItem(
            content_id=content_id,
            content_type="image_gallery",
            title="合成点赞条目 000",
            collection_id="collection_overlap",
            collection_name_private="合成重叠收藏夹",
        )
        favorite_scan = _scan_id("favorite-overlap")
        favorites = XhsFavoritesAdapter(self.store)
        favorites.begin_scan(
            favorite_scan,
            account_ref_hash=ACCOUNT_HASH,
            scope_mode="full_scan",
            started_at=NOW,
        )
        favorites.commit_batch(
            favorite_scan,
            XhsFavoritesBatch(
                sequence=0,
                status="ready",
                completion_signal="authoritative_end",
                visible_card_count=1,
                items=(favorite,),
                error_codes=(),
                observed_at=NOW,
            ),
        )

        likes_scan = _scan_id("likes-overlap")
        likes = XhsLikesAdapter(self.store)
        likes.begin_scan(
            likes_scan,
            account_ref_hash=ACCOUNT_HASH,
            scope_mode="full_scan",
            started_at=NOW + timedelta(minutes=1),
        )
        likes.commit_batch(
            likes_scan,
            _batch(
                0,
                (_item(0),),
                completion="authoritative_end",
                observed_at=NOW + timedelta(minutes=1),
            ),
        )

        self.assertEqual(len(self._rows("SELECT * FROM content")), 1)
        self.assertEqual(
            {row["relation_type"] for row in self._rows("SELECT relation_type FROM user_relation")},
            {"favorited", "liked"},
        )
        self.assertEqual(len(self._rows("SELECT * FROM user_relation")), 2)
        self.assertEqual(len(self._rows("SELECT * FROM source_observation")), 2)
        self.assertEqual(len(self._rows("SELECT * FROM classification")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM taxonomy_category")), 0)

    def test_exact_last_batch_replay_has_no_duplicate_side_effects(self) -> None:
        scan_id = _scan_id("replay")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="canary_20", started_at=NOW)
        batch = _batch(0, tuple(_item(index) for index in range(20)), completion="bounded_limit_reached")
        first = adapter.commit_batch(scan_id, batch)
        second = adapter.commit_batch(scan_id, batch)
        self.assertEqual(first.disposition, "applied")
        self.assertEqual(second.disposition, "replayed")
        self.assertEqual(self.store.counts()["content"], 20)
        self.assertEqual(self.store.counts()["user_relation"], 20)
        self.assertEqual(self.store.counts()["source_observation"], 20)

    def test_partial_observations_are_preserved_without_advancing_or_completing(self) -> None:
        scan_id = _scan_id("partial")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        partial = _batch(
            0,
            (_item(0),),
            status="partial",
            completion="unknown",
            errors=(ErrorCode.PROVENANCE_INCOMPLETE.value,),
            visible=2,
        )
        receipt = adapter.commit_batch(scan_id, partial)
        self.assertEqual(receipt.next_sequence, 0)
        self.assertEqual(receipt.checkpoint_state, "active")
        self.assertEqual(receipt.observed_unique_items, 1)
        self.assertEqual(receipt.error_evidence_count, 1)
        replay = adapter.commit_batch(scan_id, partial)
        self.assertEqual(replay.disposition, "replayed")
        ready = _batch(0, (_item(0), _item(1)), observed_at=NOW + timedelta(minutes=1))
        advanced = adapter.commit_batch(scan_id, ready)
        self.assertEqual(advanced.next_sequence, 1)
        self.assertEqual(advanced.observed_unique_items, 2)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'removed'")), 0)

    def test_five_non_authoritative_outcomes_never_remove_or_complete(self) -> None:
        scan_id = _scan_id("non-authoritative")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        cases = (
            ("auth_required", ErrorCode.ADAPTER_AUTH_EXPIRED.value),
            ("platform_changed", ErrorCode.PLATFORM_CHANGED.value),
            ("empty_unverified", ErrorCode.PROVENANCE_INCOMPLETE.value),
            ("partial", ErrorCode.PROVENANCE_INCOMPLETE.value),
            ("verification_required", ErrorCode.POLICY_BLOCKED.value),
        )
        for index, (status, code) in enumerate(cases):
            items = (_item(50),) if status == "partial" else ()
            receipt = adapter.commit_batch(
                scan_id,
                _batch(
                    0,
                    items,
                    status=status,
                    completion="unknown",
                    errors=(code,),
                    observed_at=NOW + timedelta(minutes=index),
                    visible=2 if status == "partial" else 0,
                ),
            )
            self.assertEqual(receipt.next_sequence, 0)
            self.assertEqual(receipt.checkpoint_state, "active")
            self.assertFalse(receipt.full_scan_completed)
        statuses = [row["status"] for row in self._rows("SELECT status FROM user_relation")]
        self.assertNotIn("removed", statuses)
        self.assertNotIn("tombstone_candidate", statuses)
        self.assertEqual(len(self._rows("SELECT * FROM content WHERE status != 'active'")), 0)

    def test_unknown_end_advances_but_never_claims_full_scan(self) -> None:
        scan_id = _scan_id("unknown-end")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        receipt = adapter.commit_batch(scan_id, _batch(0, (_item(1),), completion="unknown"))
        self.assertEqual(receipt.checkpoint_state, "active")
        self.assertFalse(receipt.full_scan_completed)
        self.assertEqual(receipt.next_sequence, 1)

    def test_canary_completion_is_scope_complete_but_not_a_full_scan(self) -> None:
        scan_id = _scan_id("canary")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="canary_20", started_at=NOW)
        receipt = adapter.commit_batch(
            scan_id,
            _batch(0, tuple(_item(index) for index in range(20)), completion="bounded_limit_reached"),
        )
        self.assertEqual(receipt.checkpoint_state, "complete")
        self.assertEqual(receipt.cursor_kind, "bounded_scope_complete")
        self.assertFalse(receipt.full_scan_completed)

    def test_out_of_order_or_conflicting_replay_fails_closed(self) -> None:
        scan_id = _scan_id("order")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        with self.assertRaises(X2NRuntimeError) as skipped:
            adapter.commit_batch(scan_id, _batch(1, (_item(1),)))
        self.assertEqual(skipped.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        adapter.commit_batch(scan_id, _batch(0, (_item(0),)))
        with self.assertRaises(X2NRuntimeError) as conflict:
            adapter.commit_batch(scan_id, _batch(0, (_item(9),)))
        self.assertEqual(conflict.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_injected_kill_rolls_back_batch_and_checkpoint_atomically(self) -> None:
        scan_id = _scan_id("kill")
        stable = XhsLikesAdapter(self.store)
        stable.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)

        def kill(label: str) -> None:
            if label == "before_checkpoint":
                raise InjectedKill()

        with self.assertRaises(InjectedKill):
            XhsLikesAdapter(self.store, fault_injector=kill).commit_batch(scan_id, _batch(0, (_item(0), _item(1))))
        checkpoint = stable.checkpoint(scan_id)
        self.assertEqual(checkpoint.next_sequence, 0)
        self.assertEqual(checkpoint.observed_unique_items, 0)
        self.assertEqual(self.store.counts()["content"], 0)
        recovered = stable.commit_batch(scan_id, _batch(0, (_item(0), _item(1))))
        self.assertEqual(recovered.next_sequence, 1)
        self.assertEqual(recovered.observed_unique_items, 2)

    def test_extension_mapping_enforces_inbox_and_rejects_unknown_fields(self) -> None:
        result = {
            "batch": {
                "automatic_scroll": False,
                "completion_signal": "unknown",
                "explicit_owner_action": True,
                "visible_card_count": 1,
            },
            "code": None,
            "errors": [],
            "inbox": {
                "automatic_filing": False,
                "disposition": "unclassified",
                "taxonomy_mutation": False,
            },
            "items": [
                {
                    "content_id": "synth_xhs_like_000",
                    "content_type": "image_gallery",
                    "inbox_disposition": "unclassified",
                    "page_url": "https://www.xiaohongshu.com/explore/synth_xhs_like_000",
                    "title": "合成点赞条目",
                }
            ],
            "platform": "xiaohongshu",
            "schema_version": "1.0",
            "status": "ready",
        }
        batch = XhsLikesBatch.from_extension_result(result, sequence=0, observed_at=NOW)
        self.assertEqual(batch.items[0].content_id, "synth_xhs_like_000")
        result["unexpected"] = True
        with self.assertRaises(X2NRuntimeError) as unknown:
            XhsLikesBatch.from_extension_result(result, sequence=0, observed_at=NOW)
        self.assertEqual(unknown.exception.code, ErrorCode.UNKNOWN_FIELD)
        del result["unexpected"]
        result["inbox"]["automatic_filing"] = True
        with self.assertRaises(X2NRuntimeError) as policy:
            XhsLikesBatch.from_extension_result(result, sequence=0, observed_at=NOW)
        self.assertEqual(policy.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_extension_mapping_rejects_untrusted_error_envelopes(self) -> None:
        base = {
            "batch": {
                "automatic_scroll": False,
                "completion_signal": "unknown",
                "explicit_owner_action": True,
                "visible_card_count": 2,
            },
            "code": ErrorCode.PROVENANCE_INCOMPLETE.value,
            "errors": [{"card_index": 1, "code": ErrorCode.PROVENANCE_INCOMPLETE.value}],
            "inbox": {
                "automatic_filing": False,
                "disposition": "unclassified",
                "taxonomy_mutation": False,
            },
            "items": [
                {
                    "content_id": "synth_xhs_like_000",
                    "content_type": "image_gallery",
                    "inbox_disposition": "unclassified",
                    "page_url": "https://www.xiaohongshu.com/explore/synth_xhs_like_000",
                    "title": "合成点赞条目",
                }
            ],
            "platform": "xiaohongshu",
            "schema_version": "1.0",
            "status": "partial",
        }
        XhsLikesBatch.from_extension_result(base, sequence=0, observed_at=NOW)

        cases = {
            "invalid_top_code": lambda value: value.update({"code": "X2N_NOT_AN_ERROR"}),
            "mismatched_top_code": lambda value: value.update({"code": ErrorCode.PLATFORM_CHANGED.value}),
            "index_at_visible_bound": lambda value: value["errors"][0].update({"card_index": 2}),
            "boolean_index": lambda value: value["errors"][0].update({"card_index": True}),
            "null_partial_index": lambda value: value["errors"][0].update({"card_index": None}),
            "duplicate_index": lambda value: value["errors"].append(
                {"card_index": 1, "code": ErrorCode.PROVENANCE_INCOMPLETE.value}
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(base, ensure_ascii=False))
                mutate(candidate)
                with self.assertRaises(X2NRuntimeError):
                    XhsLikesBatch.from_extension_result(candidate, sequence=0, observed_at=NOW)

    def test_global_gate_wraps_one_explicit_batch_without_wait_or_scroll(self) -> None:
        scan_id = _scan_id("gate")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        coordinator = XhsLikesBatchCoordinator(adapter, AdapterExecutionGate(self.paths))
        receipt = coordinator.apply_owner_action(
            scan_id,
            _batch(0, (_item(0),)),
            monotonic_batch_time=100.0,
            monotonic_observation_time=100.0,
        )
        self.assertEqual(receipt.next_sequence, 1)
        self.assertEqual(receipt.safe_dict()["automatic_scrolls"], 0)

    def test_public_receipt_contains_only_hashes_counts_and_states(self) -> None:
        scan_id = _scan_id("receipt")
        adapter = XhsLikesAdapter(self.store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        receipt = adapter.commit_batch(scan_id, _batch(0, (_item(0),))).safe_dict()
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(scan_id, rendered)
        self.assertNotIn("synth_xhs_like", rendered)
        self.assertNotIn("合成点赞", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("https://", rendered)
        self.assertEqual(receipt["removed_relations"], 0)
        self.assertEqual(receipt["physical_deletes"], 0)
        self.assertEqual(receipt["automatic_classification_writes"], 0)
        self.assertEqual(receipt["taxonomy_mutations"], 0)


if __name__ == "__main__":
    unittest.main()
