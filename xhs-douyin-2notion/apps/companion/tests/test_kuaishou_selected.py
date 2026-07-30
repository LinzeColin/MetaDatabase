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
from x2n_companion.kuaishou_selected import (
    KuaishouCapabilityReceipt,
    KuaishouSelectedAdapter,
    KuaishouSelectedBatch,
    KuaishouSelectedBatchCoordinator,
    KuaishouSelectedItem,
    KuaishouSelectedIterator,
    build_kuaishou_canary_plan,
    evaluate_kuaishou_capability,
)
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64
AUTH_HASH = "b" * 64
MANIFEST_HASH = "c" * 64
SELECTION_ID = "x2nsel_0123456789abcdef0123456789abcdef"


class InjectedKill(BaseException):
    pass


def _scan_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters007:{label}"))


def _capability(environment: str = "ci_synthetic", **overrides: object) -> KuaishouCapabilityReceipt:
    values: dict[str, object] = {
        "environment": environment,
        "source_kind": "authorized_user_published_videos",
        "policy_revision": "2026-07-23",
        "authorization_ref_sha256": AUTH_HASH,
        "application_approved": False,
        "owner_consent_active": False,
        "user_video_info_granted": False,
        "sanitized_transport_attested": False,
        "canonical_route_attested": False,
        "retention_delete_route_ready": False,
        "consent_revoked": False,
        "credential_material_present": False,
    }
    values.update(overrides)
    return KuaishouCapabilityReceipt(**values)  # type: ignore[arg-type]


def _item(index: int, *, title: str | None = None, published: bool = True) -> dict[str, object]:
    photo_id = f"synthetic-ks-selected-{index:03d}"
    return {
        "photo_id": photo_id,
        "canonical_page_url": f"https://www.kuaishou.com/short-video/{photo_id}",
        "content_type": "video",
        "published_at": f"2026-07-23T00:{index % 60:02d}:00Z" if published else None,
        "title": title or f"合成授权作品 {index:03d}",
    }


def _manifest(
    *,
    status: str = "ready",
    items: list[dict[str, object]] | None = None,
    count: int | None = None,
    errors: list[str] | None = None,
    selection_id: str = SELECTION_ID,
    manifest_hash: str = MANIFEST_HASH,
) -> dict[str, object]:
    actual_items = items if items is not None else [_item(index) for index in range(20)]
    actual_errors = errors or []
    return {
        "automatic_pagination": False,
        "automatic_scroll": False,
        "error_codes": actual_errors,
        "explicit_owner_action": True,
        "has_more": True,
        "items": actual_items,
        "owner_selection_id": selection_id,
        "page_number": 1,
        "page_size": 20,
        "platform": "kuaishou",
        "policy_revision": "2026-07-23",
        "schema_version": "1.0",
        "selected_manifest_count": len(actual_items) + len(actual_errors) if count is None else count,
        "selection_manifest_sha256": manifest_hash,
        "source_kind": "authorized_user_published_videos",
        "status": status,
    }


def _batch(**kwargs: object) -> KuaishouSelectedBatch:
    return KuaishouSelectedIterator(_capability()).one_explicit_batch(_manifest(**kwargs), observed_at=NOW)


class KuaishouSelectedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-adapters007-")
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

    def _begin(
        self,
        label: str,
        *,
        selection_id: str = SELECTION_ID,
        manifest_hash: str = MANIFEST_HASH,
        capability: KuaishouCapabilityReceipt | None = None,
        started_at: datetime = NOW,
    ) -> tuple[str, KuaishouSelectedAdapter]:
        scan_id = _scan_id(label)
        adapter = KuaishouSelectedAdapter(self.store)
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            owner_selection_id=selection_id,
            selection_manifest_sha256=manifest_hash,
            capability=capability or _capability(),
            started_at=started_at,
        )
        return scan_id, adapter

    def test_capability_is_credential_free_and_real_runtime_remains_disabled(self) -> None:
        synthetic = _capability()
        decision = evaluate_kuaishou_capability(synthetic)
        self.assertTrue(decision.offline_mapping_permitted)
        self.assertFalse(decision.platform_requests_permitted)
        self.assertEqual(decision.status, "PASS_CI_SYNTHETIC")
        self.assertNotIn("https://", json.dumps(decision.safe_dict(), sort_keys=True))

        missing = evaluate_kuaishou_capability(_capability("owner_runtime"))
        self.assertEqual(missing.status, "BLOCKED_MISSING_AUTHORIZATION")
        self.assertEqual(len(missing.missing_requirements), 6)
        eligible = evaluate_kuaishou_capability(
            _capability(
                "owner_runtime",
                application_approved=True,
                owner_consent_active=True,
                user_video_info_granted=True,
                sanitized_transport_attested=True,
                canonical_route_attested=True,
                retention_delete_route_ready=True,
            )
        )
        self.assertEqual(eligible.status, "BLOCKED_FEATURE_DISABLED")
        self.assertFalse(eligible.offline_mapping_permitted)
        revoked = evaluate_kuaishou_capability(_capability("owner_runtime", consent_revoked=True))
        self.assertEqual(revoked.status, "BLOCKED_CONSENT_REVOKED")
        self.assertTrue(revoked.retention_action_required)
        self.assertFalse(revoked.platform_requests_permitted)
        with self.assertRaises(X2NRuntimeError) as blocked:
            KuaishouSelectedAdapter(self.store).begin_scan(
                _scan_id("real-blocked"),
                account_ref_hash=ACCOUNT_HASH,
                owner_selection_id=SELECTION_ID,
                selection_manifest_sha256=MANIFEST_HASH,
                capability=_capability("owner_runtime"),
                started_at=NOW,
            )
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_capability_mapping_rejects_unknown_fields_claims_and_non_booleans(self) -> None:
        mapping = {
            "application_approved": False,
            "authorization_ref_sha256": AUTH_HASH,
            "canonical_route_attested": False,
            "consent_revoked": False,
            "credential_material_present": False,
            "environment": "ci_synthetic",
            "owner_consent_active": False,
            "policy_revision": "2026-07-23",
            "retention_delete_route_ready": False,
            "sanitized_transport_attested": False,
            "source_kind": "authorized_user_published_videos",
            "user_video_info_granted": False,
        }
        self.assertEqual(KuaishouCapabilityReceipt.from_mapping(mapping).environment, "ci_synthetic")
        mapping["token"] = "forbidden"
        with self.assertRaises(X2NRuntimeError) as unknown:
            KuaishouCapabilityReceipt.from_mapping(mapping)
        self.assertEqual(unknown.exception.code, ErrorCode.UNKNOWN_FIELD)
        del mapping["token"]
        mapping["application_approved"] = 0
        with self.assertRaises(X2NRuntimeError) as invalid_bool:
            KuaishouCapabilityReceipt.from_mapping(mapping)
        self.assertEqual(invalid_bool.exception.code, ErrorCode.SECURITY_INJECTION_BLOCKED)
        with self.assertRaises(X2NRuntimeError) as false_claim:
            _capability(application_approved=True)
        self.assertEqual(false_claim.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_iterator_accepts_one_sanitized_page_but_has_no_pagination_transport(self) -> None:
        iterator = KuaishouSelectedIterator(_capability())
        batch = iterator.one_explicit_batch(_manifest(), observed_at=NOW)
        self.assertEqual(batch.sequence, 0)
        self.assertEqual(len(batch.items), 20)
        self.assertFalse(batch.automatic_pagination)
        self.assertFalse(batch.automatic_scroll)
        self.assertEqual(batch.source_kind, "authorized_user_published_videos")
        self.assertFalse(hasattr(iterator, "next_page"))
        self.assertFalse(hasattr(iterator, "transport"))

    def test_iterator_rejects_raw_api_fields_urls_page_two_and_unsafe_title(self) -> None:
        iterator = KuaishouSelectedIterator(_capability())
        for raw_field in ("cover", "play_url", "like_count", "cursor"):
            raw = _manifest()
            raw[raw_field] = "forbidden-raw-value"
            with self.assertRaises(X2NRuntimeError) as unknown:
                iterator.one_explicit_batch(raw, observed_at=NOW)
            self.assertEqual(unknown.exception.code, ErrorCode.UNKNOWN_FIELD)

        real_identity = _manifest(items=[_item(0)], count=1)
        real_identity["items"][0]["photo_id"] = "3x-real-shaped-photo"  # type: ignore[index]
        real_identity["items"][0]["canonical_page_url"] = (  # type: ignore[index]
            "https://www.kuaishou.com/short-video/3x-real-shaped-photo"
        )
        with self.assertRaises(X2NRuntimeError) as real_id:
            iterator.one_explicit_batch(real_identity, observed_at=NOW)
        self.assertEqual(real_id.exception.code, ErrorCode.POLICY_BLOCKED)

        page_two = _manifest()
        page_two["page_number"] = 2
        with self.assertRaises(X2NRuntimeError) as page:
            iterator.one_explicit_batch(page_two, observed_at=NOW)
        self.assertEqual(page.exception.code, ErrorCode.POLICY_BLOCKED)

        bad_url = _manifest(items=[_item(0)], count=1)
        bad_url["items"][0]["canonical_page_url"] += "?tracking=1"  # type: ignore[index,operator]
        with self.assertRaises(X2NRuntimeError) as url:
            iterator.one_explicit_batch(bad_url, observed_at=NOW)
        self.assertEqual(url.exception.code, ErrorCode.URL_REJECTED)

        bad_title = _manifest(items=[_item(0, title="https://unsafe.example")], count=1)
        with self.assertRaises(X2NRuntimeError) as title:
            iterator.one_explicit_batch(bad_title, observed_at=NOW)
        self.assertEqual(title.exception.code, ErrorCode.INVALID_INPUT)

        wrong_kind = _manifest(items=[_item(0)], count=1)
        wrong_kind["items"][0]["content_type"] = "text"  # type: ignore[index]
        with self.assertRaises(X2NRuntimeError) as kind:
            iterator.one_explicit_batch(wrong_kind, observed_at=NOW)
        self.assertEqual(kind.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_batch_contract_rejects_duplicates_unknown_errors_and_boolean_counts(self) -> None:
        duplicate = _manifest(items=[_item(0), _item(0)], count=2)
        with self.assertRaises(X2NRuntimeError) as duplicate_error:
            KuaishouSelectedIterator(_capability()).one_explicit_batch(duplicate, observed_at=NOW)
        self.assertEqual(duplicate_error.exception.code, ErrorCode.INVALID_INPUT)
        bad_error = _manifest(status="partial", items=[_item(0)], count=2, errors=["NOT_REGISTERED"])
        with self.assertRaises(X2NRuntimeError) as error_code:
            KuaishouSelectedIterator(_capability()).one_explicit_batch(bad_error, observed_at=NOW)
        self.assertEqual(error_code.exception.code, ErrorCode.INVALID_INPUT)
        bool_count = _manifest(items=[_item(0)], count=1)
        bool_count["selected_manifest_count"] = True
        with self.assertRaises(X2NRuntimeError) as count:
            KuaishouSelectedIterator(_capability()).one_explicit_batch(bool_count, observed_at=NOW)
        self.assertEqual(count.exception.code, ErrorCode.INVALID_INPUT)
        with self.assertRaises(X2NRuntimeError) as sequence:
            KuaishouSelectedBatch(
                sequence=1,
                status="ready",
                selected_manifest_count=1,
                items=(KuaishouSelectedItem.from_mapping(_item(0)),),
                error_codes=(),
                observed_at=NOW,
                owner_selection_id=SELECTION_ID,
                selection_manifest_sha256=MANIFEST_HASH,
            )
        self.assertEqual(sequence.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_twenty_items_map_to_owner_saved_current_without_fake_platform_relation(self) -> None:
        scan_id, adapter = self._begin("success")
        receipt = adapter.commit_batch(scan_id, _batch())
        self.assertEqual(receipt.checkpoint_state, "complete")
        self.assertEqual(receipt.cursor_kind, "bounded_selection_complete")
        self.assertEqual(receipt.identified_percent, 100.0)
        self.assertEqual(receipt.relation_count, 20)
        self.assertEqual(receipt.observation_count, 20)
        self.assertEqual(receipt.next_sequence, 1)
        self.assertFalse(receipt.platform_killed)
        relations = self._rows("SELECT relation_type, confirmed_by, source_collection_id, status FROM user_relation")
        self.assertEqual({row["relation_type"] for row in relations}, {"saved_current"})
        self.assertEqual({row["confirmed_by"] for row in relations}, {"owner"})
        self.assertEqual({row["source_collection_id"] for row in relations}, {SELECTION_ID})
        self.assertEqual({row["status"] for row in relations}, {"active"})
        self.assertEqual(
            {row["source_method"] for row in self._rows("SELECT source_method FROM source_observation")},
            {"selected_collection"},
        )
        self.assertEqual({row["platform"] for row in self._rows("SELECT platform FROM content")}, {"kuaishou"})
        self.assertEqual(len(self._rows("SELECT * FROM classification")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM taxonomy_category")), 0)
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status != 'active'")), 0)

    def test_exact_replay_has_no_duplicate_side_effects(self) -> None:
        scan_id, adapter = self._begin("replay")
        batch = _batch()
        first = adapter.commit_batch(scan_id, batch)
        second = adapter.commit_batch(scan_id, batch)
        self.assertEqual(first.disposition, "applied")
        self.assertEqual(second.disposition, "replayed")
        self.assertEqual(self.store.counts()["content"], 20)
        self.assertEqual(self.store.counts()["user_relation"], 20)
        self.assertEqual(self.store.counts()["source_observation"], 20)
        with self.assertRaises(X2NRuntimeError) as conflict:
            adapter.commit_batch(scan_id, _batch(items=[_item(99)], count=1))
        self.assertEqual(conflict.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_partial_is_evidenced_without_writes_then_corrected_same_sequence(self) -> None:
        scan_id, adapter = self._begin("partial")
        partial = _batch(
            status="partial",
            items=[_item(0)],
            count=2,
            errors=[ErrorCode.PROVENANCE_INCOMPLETE.value],
        )
        receipt = adapter.commit_batch(scan_id, partial)
        self.assertEqual(receipt.checkpoint_state, "active")
        self.assertEqual(receipt.next_sequence, 0)
        self.assertEqual(receipt.manifest_items, 2)
        self.assertEqual(receipt.identified_items, 1)
        self.assertEqual(receipt.identified_percent, 50.0)
        self.assertEqual(receipt.error_evidence_count, 1)
        self.assertEqual(self.store.counts()["content"], 0)
        self.assertEqual(adapter.commit_batch(scan_id, partial).disposition, "replayed")
        corrected = _batch(items=[_item(0), _item(1)], count=2)
        completed = adapter.commit_batch(scan_id, corrected)
        self.assertEqual(completed.checkpoint_state, "complete")
        self.assertEqual(completed.identified_percent, 100.0)
        self.assertEqual(self.store.counts()["content"], 2)

    def test_policy_auth_scope_revocation_and_captcha_each_kill_only_the_kuaishou_scan(self) -> None:
        stable_scan, stable = self._begin("historical")
        stable.commit_batch(stable_scan, _batch(items=[_item(0)], count=1))
        baseline = self.store.counts()
        cases = (
            ("auth_required", ErrorCode.ADAPTER_AUTH_EXPIRED.value),
            ("scope_revoked", ErrorCode.POLICY_BLOCKED.value),
            ("policy_blocked", ErrorCode.POLICY_BLOCKED.value),
            ("captcha_required", ErrorCode.POLICY_BLOCKED.value),
        )
        for index, (status, error) in enumerate(cases):
            selection = f"x2nsel_{index + 1:032x}"
            manifest_hash = f"{index + 1:064x}"
            scan_id, adapter = self._begin(
                f"kill-{status}",
                selection_id=selection,
                manifest_hash=manifest_hash,
            )
            batch = _batch(
                status=status,
                items=[],
                count=0,
                errors=[error],
                selection_id=selection,
                manifest_hash=manifest_hash,
            )
            receipt = adapter.commit_batch(scan_id, batch)
            self.assertEqual(receipt.checkpoint_state, "invalidated")
            self.assertTrue(receipt.platform_killed)
            self.assertEqual(receipt.next_sequence, 0)
            self.assertEqual(receipt.retention_delete_required, status == "scope_revoked")
            self.assertEqual(
                receipt.cursor_kind,
                "consent_revoked_retention_required" if status == "scope_revoked" else "platform_policy_killed",
            )
            self.assertEqual(adapter.commit_batch(scan_id, batch).disposition, "replayed")
        self.assertEqual(self.store.counts()["content"], baseline["content"])
        self.assertEqual(self.store.counts()["user_relation"], baseline["user_relation"])
        self.assertEqual(self.store.counts()["source_observation"], baseline["source_observation"])
        self.assertEqual(len(self._rows("SELECT * FROM user_relation WHERE status = 'removed'")), 0)

    def test_empty_and_platform_changed_stay_active_without_deletion(self) -> None:
        for index, (status, error) in enumerate(
            (
                ("empty_unverified", ErrorCode.PROVENANCE_INCOMPLETE.value),
                ("platform_changed", ErrorCode.PLATFORM_CHANGED.value),
            )
        ):
            selection = f"x2nsel_{index + 10:032x}"
            manifest_hash = f"{index + 10:064x}"
            scan_id, adapter = self._begin(
                f"non-authoritative-{status}", selection_id=selection, manifest_hash=manifest_hash
            )
            receipt = adapter.commit_batch(
                scan_id,
                _batch(
                    status=status,
                    items=[],
                    count=0,
                    errors=[error],
                    selection_id=selection,
                    manifest_hash=manifest_hash,
                ),
            )
            self.assertEqual(receipt.checkpoint_state, "active")
            self.assertFalse(receipt.platform_killed)
            self.assertEqual(receipt.relation_count, 0)
        self.assertEqual(self.store.counts()["content"], 0)

    def test_injected_kill_rolls_back_items_relations_observations_and_checkpoint(self) -> None:
        scan_id, stable = self._begin("injected-kill")

        def kill(label: str) -> None:
            if label == "before_checkpoint":
                raise InjectedKill()

        with self.assertRaises(InjectedKill):
            KuaishouSelectedAdapter(self.store, fault_injector=kill).commit_batch(scan_id, _batch())
        recovered = stable.checkpoint(scan_id)
        self.assertEqual(recovered.next_sequence, 0)
        self.assertEqual(recovered.manifest_items, 0)
        self.assertEqual(self.store.counts()["content"], 0)
        completed = stable.commit_batch(scan_id, _batch())
        self.assertEqual(completed.next_sequence, 1)
        self.assertEqual(completed.relation_count, 20)

    def test_cursor_boolean_corruption_and_graph_mismatch_fail_closed(self) -> None:
        scan_id, adapter = self._begin("cursor-corrupt")
        identity_suffix = uuid.UUID(scan_id).hex
        checkpoint_id = f"checkpoint_kssel_{identity_suffix}"
        with self.store._transaction() as connection:
            row = connection.execute(
                "SELECT cursor_value_private FROM checkpoint WHERE checkpoint_id = ?", (checkpoint_id,)
            ).fetchone()
            cursor = json.loads(row["cursor_value_private"])
            cursor["next_sequence"] = True
            connection.execute(
                "UPDATE checkpoint SET cursor_value_private = ? WHERE checkpoint_id = ?",
                (json.dumps(cursor, sort_keys=True), checkpoint_id),
            )
        with self.assertRaises(X2NRuntimeError) as corrupt:
            adapter.checkpoint(scan_id)
        self.assertEqual(corrupt.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

        other_scan, other = self._begin("graph-corrupt")
        run_id = f"run_kssel_{uuid.UUID(other_scan).hex}"
        with self.store._transaction() as connection:
            connection.execute(
                "UPDATE run_record SET state = 'failed', finished_at = ? WHERE run_id = ?",
                ("2026-07-23T00:00:00Z", run_id),
            )
        with self.assertRaises(X2NRuntimeError) as graph:
            other.checkpoint(other_scan)
        self.assertEqual(graph.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_scan_identity_conflicts_and_backwards_time_fail_closed(self) -> None:
        scan_id, adapter = self._begin("identity")
        with self.assertRaises(X2NRuntimeError) as selection:
            adapter.begin_scan(
                scan_id,
                account_ref_hash=ACCOUNT_HASH,
                owner_selection_id="x2nsel_ffffffffffffffffffffffffffffffff",
                selection_manifest_sha256=MANIFEST_HASH,
                capability=_capability(),
                started_at=NOW,
            )
        self.assertEqual(selection.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        older = KuaishouSelectedIterator(_capability()).one_explicit_batch(
            _manifest(items=[_item(0)], count=1), observed_at=NOW - timedelta(seconds=1)
        )
        with self.assertRaises(X2NRuntimeError) as time_error:
            adapter.commit_batch(scan_id, older)
        self.assertEqual(time_error.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_same_content_in_two_owner_selections_reuses_content_but_keeps_relations(self) -> None:
        first_scan, first = self._begin("selection-one")
        first.commit_batch(first_scan, _batch(items=[_item(0)], count=1))
        second_selection = "x2nsel_ffffffffffffffffffffffffffffffff"
        second_hash = "d" * 64
        second_scan, second = self._begin(
            "selection-two",
            selection_id=second_selection,
            manifest_hash=second_hash,
            started_at=NOW + timedelta(minutes=1),
        )
        second.commit_batch(
            second_scan,
            KuaishouSelectedIterator(_capability()).one_explicit_batch(
                _manifest(
                    items=[_item(0, title="合成授权作品 更新")],
                    count=1,
                    selection_id=second_selection,
                    manifest_hash=second_hash,
                ),
                observed_at=NOW + timedelta(minutes=1),
            ),
        )
        self.assertEqual(self.store.counts()["content"], 1)
        self.assertEqual(self.store.counts()["user_relation"], 2)
        self.assertEqual(self.store.counts()["source_observation"], 2)
        self.assertEqual(
            {row["source_collection_id"] for row in self._rows("SELECT source_collection_id FROM user_relation")},
            {SELECTION_ID, second_selection},
        )

    def test_coordinator_uses_global_guard_for_one_owner_action(self) -> None:
        scan_id, adapter = self._begin("coordinator")
        coordinator = KuaishouSelectedBatchCoordinator(adapter, AdapterExecutionGate(self.paths))
        receipt = coordinator.apply_owner_action(
            scan_id,
            _batch(items=[_item(0)], count=1),
            monotonic_batch_time=100.0,
            monotonic_observation_time=100.0,
        )
        self.assertEqual(receipt.next_sequence, 1)
        self.assertEqual(receipt.safe_dict()["automatic_pagination"], 0)

    def test_public_receipt_contains_only_counts_hashes_and_states(self) -> None:
        scan_id, adapter = self._begin("safe-receipt")
        receipt = adapter.commit_batch(scan_id, _batch(items=[_item(0)], count=1)).safe_dict()
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(scan_id, rendered)
        self.assertNotIn(SELECTION_ID, rendered)
        self.assertNotIn("synthetic-ks-selected-000", rendered)
        self.assertNotIn("合成授权作品", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("https://", rendered)
        self.assertEqual(receipt["silent_losses"], 0)
        self.assertEqual(receipt["removed_relations"], 0)
        self.assertEqual(receipt["physical_deletes"], 0)
        self.assertFalse(receipt["retention_delete_required"])
        self.assertFalse(receipt["source_list_complete"])

    def test_canary_plan_and_cli_are_nonexecuting_and_fixed_to_twenty(self) -> None:
        plan = build_kuaishou_canary_plan()
        self.assertEqual(plan["max_items"], 20)
        self.assertEqual(plan["execution"], "NOT_RUN")
        self.assertFalse(plan["production_enabled"])
        self.assertFalse(plan["automatic_pagination"])
        self.assertEqual(plan["official_scope"], "user_video_info")
        self.assertEqual(plan["transport"], "NONE_IN_ADAPTERS_007")
        self.assertEqual(plan["canonical_public_route"], "UNVERIFIED_DISABLED")
        self.assertTrue(plan["data_delete_on_revocation_required"])
        with self.assertRaises(X2NRuntimeError) as blocked:
            build_kuaishou_canary_plan(19)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        args = runtime_cli.build_parser().parse_args(["kuaishou", "canary-plan", "--max-items", "20"])
        receipt = runtime_cli.run(args)
        self.assertEqual(receipt["task_id"], "TSK.x2n.adapters.007")
        self.assertEqual(receipt["plan"]["execution"], "NOT_RUN")
        self.assertEqual(receipt["real_account_execution"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
