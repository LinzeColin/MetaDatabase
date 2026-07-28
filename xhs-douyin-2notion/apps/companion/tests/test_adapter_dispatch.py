from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from x2n_contracts import ErrorCode, canonical_json_sha256
from x2n_contracts.models import CapabilityFeatureFlag, CapabilityReasonCode, CapabilityTerminal, SyncScopeId

from x2n_companion.adapter_dispatch import AdapterDispatcher, CapabilityRegistry
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion.migrations import LATEST_SCHEMA_VERSION
from x2n_companion.native_host import DEVELOPMENT_EXTENSION_ORIGIN, dispatch_wire
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _wire(action: str, payload: dict[str, object], *, request_id: str | None = None) -> bytes:
    return json.dumps(
        {
            "action": action,
            "payload": payload,
            "payload_hash": canonical_json_sha256(payload),
            "request_id": request_id or str(uuid.uuid4()),
            "schema_version": "1.0",
            "sent_at": "2026-07-28T00:00:00Z",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _list_payload(scope_id: str, platform: str, relation: str) -> dict[str, object]:
    return {
        "auto_scroll": False,
        "bounded_batch": True,
        "change_account_state": False,
        "dispatch_version": "1.0",
        "max_items": 20,
        "platform": platform,
        "relation": relation,
        "scope_id": scope_id,
        "source_collection_id": None,
        "user_gesture": True,
    }


def _selected_payload(scope_id: str, platform: str, relation: str) -> dict[str, object]:
    return {
        "auto_scroll": False,
        "bounded_batch": True,
        "change_account_state": False,
        "dispatch_version": "1.0",
        "max_items": 20,
        "owner_selection_id": "x2nsel_0123456789abcdef0123456789abcdef",
        "owner_selection_manifest_sha256": "a" * 64,
        "platform": platform,
        "relation": relation,
        "scope_id": scope_id,
        "source_identity": "synthetic_owner_selected_source",
        "user_gesture": True,
    }


SCOPE_PAYLOADS = (
    _list_payload("xiaohongshu_favorites", "xiaohongshu", "favorited"),
    _list_payload("xiaohongshu_likes", "xiaohongshu", "liked"),
    _list_payload("douyin_favorites", "douyin", "favorited"),
    _list_payload("douyin_likes", "douyin", "liked"),
    _selected_payload("bilibili_selected_collection", "bilibili", "saved_current"),
    _selected_payload("kuaishou_selected_collection", "kuaishou", "saved_current"),
    _selected_payload("weibo_selected_collection", "weibo", "favorited"),
    _selected_payload("taobao_selected_collection", "taobao", "saved_current"),
)


def _capture_payload(*, fallback_from_job_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "auto_scroll": False,
        "category_id": None,
        "change_account_state": False,
        "page_context": {"content_id": "synthetic-fallback-001", "content_type": "video", "title": "Synthetic"},
        "page_url": "https://www.xiaohongshu.com/explore/synthetic-fallback-001",
        "platform": "xiaohongshu",
        "relation": "saved_current",
        "user_gesture": True,
    }
    if fallback_from_job_id is not None:
        payload["fallback_from_job_id"] = fallback_from_job_id
    return payload


class AdapterDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-a010-")
        self.destination = Path(self.temporary.name) / "MediaCrawler"
        self.destination.mkdir(mode=0o700)
        self.destination.chmod(0o700)
        self.root = self.destination / "xhs-douyin-2notion"
        self.paths = RuntimePaths.from_values(
            str(self.root),
            str(self.destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _dispatch(
        self,
        action: str,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        registry: CapabilityRegistry | None = None,
        dispatcher: AdapterDispatcher | None = None,
    ):
        return dispatch_wire(
            _wire(action, payload, request_id=request_id),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
            capability_registry=registry,
            adapter_dispatcher=dispatcher,
        )

    def test_exact_eight_scope_matrix_routes_to_verified_zero_platform_adapters(self) -> None:
        capabilities = self._dispatch("get_capabilities", {"capability_contract_version": "1.0"})
        self.assertTrue(capabilities.accepted)
        self.assertEqual(tuple(item.scope_id for item in capabilities.capabilities.outcomes), tuple(SyncScopeId))
        self.assertTrue(
            all(item.terminal is CapabilityTerminal.READY_FOR_MVP_ACTIVATION for item in capabilities.capabilities.outcomes)
        )
        self.assertTrue(
            all(item.reason_code is CapabilityReasonCode.CI_SYNTH_READY for item in capabilities.capabilities.outcomes)
        )
        self.assertEqual(self.store.counts()["capability_gate_outcome"], 8)

        jobs: list[str] = []
        for payload in SCOPE_PAYLOADS:
            response = self._dispatch("start_sync", payload)
            self.assertTrue(response.accepted, payload["scope_id"])
            self.assertEqual(response.status.value, "completed")
            self.assertIsNotNone(response.job_id)
            jobs.append(str(response.job_id))
        self.assertEqual(len(set(jobs)), 8)
        self.assertEqual(self.store.counts()["native_dispatch_job"], 8)
        self.assertEqual(self.store.counts()["run_failure"], 0)
        self.assertEqual(self.store.counts()["request_ledger"], 8)
        self.assertEqual(self.store.counts()["run_record"], 8)

        for job_id in jobs:
            state = self._dispatch("get_job", {"job_id": job_id})
            self.assertTrue(state.accepted)
            self.assertEqual(str(state.job_id), job_id)
            self.assertEqual(state.status.value, "completed")

    def test_invalid_cross_products_unknown_scope_and_selected_binding_fail_closed(self) -> None:
        invalid = dict(SCOPE_PAYLOADS[0])
        invalid["relation"] = "liked"
        response = self._dispatch("start_sync", invalid)
        self.assertFalse(response.accepted)
        self.assertEqual(response.error.code, ErrorCode.INVALID_INPUT)

        unknown = dict(SCOPE_PAYLOADS[0])
        unknown["scope_id"] = "unknown_scope"
        response = self._dispatch("start_sync", unknown)
        self.assertFalse(response.accepted)
        self.assertEqual(response.error.code, ErrorCode.INVALID_INPUT)

        missing_selection = dict(SCOPE_PAYLOADS[4])
        del missing_selection["owner_selection_manifest_sha256"]
        response = self._dispatch("start_sync", missing_selection)
        self.assertFalse(response.accepted)
        self.assertEqual(response.error.code, ErrorCode.INVALID_INPUT)

        coerced = dict(SCOPE_PAYLOADS[4])
        coerced["relation"] = "favorited"
        response = self._dispatch("start_sync", coerced)
        self.assertFalse(response.accepted)
        self.assertEqual(response.error.code, ErrorCode.INVALID_INPUT)

        live_claim = CapabilityRegistry().with_override(
            SyncScopeId.XIAOHONGSHU_FAVORITES,
            feature_flag=CapabilityFeatureFlag.MVP_ACTIVATION_CANDIDATE,
        )
        response = self._dispatch("start_sync", SCOPE_PAYLOADS[0], registry=live_claim)
        self.assertFalse(response.accepted)
        self.assertEqual(response.error.code, ErrorCode.POLICY_BLOCKED)
        self.assertEqual(self.store.counts()["native_dispatch_job"], 0)

    def test_capability_precedence_technical_veto_stale_invalidation_and_restart_authority(self) -> None:
        initial = self._dispatch("get_capabilities", {"capability_contract_version": "1.0"})
        self.assertTrue(initial.accepted)
        self.assertEqual(self.store.counts()["capability_gate_outcome"], 8)

        for external_reason in (
            "unknown_disabled",
            "blocked_policy",
            "blocked_auth",
            "blocked_budget",
            "blocked_capability",
        ):
            with self.subTest(external_reason=external_reason):
                self._dispatch("get_capabilities", {"capability_contract_version": "1.0"})
                technical = CapabilityRegistry().with_override(
                    SyncScopeId.XIAOHONGSHU_FAVORITES,
                    technical_blocked=True,
                    **{external_reason: True},
                )
                veto = self._dispatch(
                    "get_capabilities",
                    {"capability_contract_version": "1.0"},
                    registry=technical,
                )
                self.assertFalse(veto.accepted)
                self.assertEqual(veto.error.code, ErrorCode.CAPABILITY_TECHNICAL_BLOCKED)
                self.assertEqual(self.store.counts()["capability_gate_outcome"], 7)
                with self.assertRaises(X2NRuntimeError) as incomplete:
                    self.store.capability_snapshot()
                self.assertEqual(incomplete.exception.code, ErrorCode.CAPABILITY_TECHNICAL_BLOCKED)

        external = CapabilityRegistry().with_override(
            SyncScopeId.XIAOHONGSHU_FAVORITES,
            unknown_disabled=True,
            blocked_policy=True,
            blocked_auth=True,
            blocked_budget=True,
            blocked_capability=True,
        )
        settled = self._dispatch(
            "get_capabilities",
            {"capability_contract_version": "1.0"},
            registry=external,
        )
        self.assertTrue(settled.accepted)
        outcome = next(item for item in settled.capabilities.outcomes if item.scope_id is SyncScopeId.XIAOHONGSHU_FAVORITES)
        self.assertIs(outcome.terminal, CapabilityTerminal.DISABLED_EXTERNAL_GATE)
        self.assertIs(outcome.reason_code, CapabilityReasonCode.UNKNOWN_DISABLED)
        self.assertEqual(self.store.counts()["capability_gate_outcome"], 8)

        restarted = CanonicalStore(self.paths)
        snapshot = restarted.capability_snapshot()
        restored = next(item for item in snapshot.outcomes if item.scope_id is SyncScopeId.XIAOHONGSHU_FAVORITES)
        self.assertIs(restored.reason_code, CapabilityReasonCode.UNKNOWN_DISABLED)

    def test_failed_job_preserves_job_id_and_requires_second_owner_current_page_action(self) -> None:
        failing_scope = SyncScopeId.XIAOHONGSHU_FAVORITES
        dispatcher = AdapterDispatcher(failure_predicate=lambda binding: binding.scope_id is failing_scope)
        failed = self._dispatch("start_sync", SCOPE_PAYLOADS[0], dispatcher=dispatcher)
        self.assertFalse(failed.accepted)
        self.assertEqual(failed.status.value, "rejected")
        self.assertEqual(failed.error.code, ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE)
        self.assertEqual(failed.error.next_action.value, "capture_current")
        self.assertIsNotNone(failed.job_id)
        failed_job_id = str(failed.job_id)
        self.assertEqual(self.store.counts()["run_failure"], 1)
        self.assertEqual(self.store.counts()["content"], 0)

        recovered = self._dispatch("get_job", {"job_id": failed_job_id})
        self.assertFalse(recovered.accepted)
        self.assertEqual(str(recovered.job_id), failed_job_id)
        self.assertEqual(recovered.error.code, ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE)
        self.assertEqual(self.store.counts()["request_ledger"], 1)

        new_request_id = str(uuid.uuid4())
        fallback = self._dispatch(
            "capture_current",
            _capture_payload(fallback_from_job_id=failed_job_id),
            request_id=new_request_id,
        )
        self.assertTrue(fallback.accepted)
        self.assertEqual(fallback.status.value, "completed")
        self.assertEqual(self.store.counts()["current_page_fallback"], 1)
        self.assertEqual(self.store.counts()["request_ledger"], 2)

        replay = self._dispatch(
            "capture_current",
            _capture_payload(fallback_from_job_id=failed_job_id),
            request_id=new_request_id,
        )
        self.assertTrue(replay.accepted)
        self.assertEqual(replay.job_id, fallback.job_id)
        self.assertEqual(self.store.counts()["request_ledger"], 2)

    def test_scope_migration_down_requires_verified_backup_and_restores_later_schema_and_v3_tables(self) -> None:
        self._dispatch("get_capabilities", {"capability_contract_version": "1.0"})
        before = self.store.backup(label="before_scope_dispatch_downgrade")
        receipt = self.store.downgrade_with_backup(2)
        self.assertEqual(self.store.health()["schema_version"], 2)
        self.assertNotIn("capability_gate_outcome", self.store.counts())
        self.store.restore(receipt.backup_id, expected_sha256=receipt.database_sha256)
        self.assertEqual(self.store.health()["schema_version"], LATEST_SCHEMA_VERSION)
        self.assertEqual(self.store.counts()["capability_gate_outcome"], 8)
        self.assertNotEqual(before.database_sha256, "")


if __name__ == "__main__":
    unittest.main()
