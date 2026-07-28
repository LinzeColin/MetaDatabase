from __future__ import annotations

import json
import unittest
import uuid

from pydantic import ValidationError

from x2n_contracts import ErrorCode, canonical_json_sha256
from x2n_contracts.models import NativeMessageRequest, NativeMessageResponse


def _request(action: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "action": action,
        "payload": payload,
        "payload_hash": canonical_json_sha256(payload),
        "request_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "sent_at": "2026-07-28T00:00:00Z",
    }


def _relation_scope(scope_id: str, platform: str, relation: str) -> dict[str, object]:
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


def _selected_scope(scope_id: str, platform: str, relation: str) -> dict[str, object]:
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
    _relation_scope("xiaohongshu_favorites", "xiaohongshu", "favorited"),
    _relation_scope("xiaohongshu_likes", "xiaohongshu", "liked"),
    _relation_scope("douyin_favorites", "douyin", "favorited"),
    _relation_scope("douyin_likes", "douyin", "liked"),
    _selected_scope("bilibili_selected_collection", "bilibili", "saved_current"),
    _selected_scope("kuaishou_selected_collection", "kuaishou", "saved_current"),
    _selected_scope("weibo_selected_collection", "weibo", "favorited"),
    _selected_scope("taobao_selected_collection", "taobao", "saved_current"),
)


class AdapterDispatchContractTests(unittest.TestCase):
    def test_all_eight_start_sync_scope_payloads_are_discriminated(self) -> None:
        parsed = []
        for payload in SCOPE_PAYLOADS:
            request = NativeMessageRequest.model_validate_json(json.dumps(_request("start_sync", payload))).root
            parsed.append(
                (request.payload.scope_id.value, request.payload.platform.value, request.payload.relation.value)
            )
        self.assertEqual(
            parsed,
            [
                ("xiaohongshu_favorites", "xiaohongshu", "favorited"),
                ("xiaohongshu_likes", "xiaohongshu", "liked"),
                ("douyin_favorites", "douyin", "favorited"),
                ("douyin_likes", "douyin", "liked"),
                ("bilibili_selected_collection", "bilibili", "saved_current"),
                ("kuaishou_selected_collection", "kuaishou", "saved_current"),
                ("weibo_selected_collection", "weibo", "favorited"),
                ("taobao_selected_collection", "taobao", "saved_current"),
            ],
        )

    def test_cross_product_and_selected_collection_binding_are_strict(self) -> None:
        cross_product = dict(SCOPE_PAYLOADS[0])
        cross_product["relation"] = "liked"
        with self.assertRaises(ValidationError):
            NativeMessageRequest.model_validate_json(json.dumps(_request("start_sync", cross_product)))

        missing_owner_manifest = dict(SCOPE_PAYLOADS[4])
        del missing_owner_manifest["owner_selection_manifest_sha256"]
        with self.assertRaises(ValidationError):
            NativeMessageRequest.model_validate_json(json.dumps(_request("start_sync", missing_owner_manifest)))

        wrong_saved_current = dict(SCOPE_PAYLOADS[6])
        wrong_saved_current["relation"] = "saved_current"
        with self.assertRaises(ValidationError):
            NativeMessageRequest.model_validate_json(json.dumps(_request("start_sync", wrong_saved_current)))

        too_many_selected = dict(SCOPE_PAYLOADS[4])
        too_many_selected["max_items"] = 21
        with self.assertRaises(ValidationError):
            NativeMessageRequest.model_validate_json(json.dumps(_request("start_sync", too_many_selected)))

    def test_capture_current_legacy_hash_stays_compatible_and_optional_fallback_is_typed(self) -> None:
        legacy = {
            "auto_scroll": False,
            "category_id": None,
            "change_account_state": False,
            "page_context": {"content_id": "synthetic-001", "content_type": "video", "title": "Synthetic"},
            "page_url": "https://www.xiaohongshu.com/explore/synthetic-001",
            "platform": "xiaohongshu",
            "relation": "saved_current",
            "user_gesture": True,
        }
        first = NativeMessageRequest.model_validate_json(json.dumps(_request("capture_current", legacy))).root
        rendered = json.loads(first.model_dump_json(by_alias=True))
        self.assertEqual(rendered["payload_hash"], canonical_json_sha256(legacy))
        NativeMessageRequest.model_validate_json(json.dumps(rendered))

        fallback = dict(legacy)
        fallback["fallback_from_job_id"] = "00000000-0000-4000-8000-000000000002"
        request = NativeMessageRequest.model_validate_json(json.dumps(_request("capture_current", fallback))).root
        self.assertEqual(str(request.payload.fallback_from_job_id), fallback["fallback_from_job_id"])

    def test_get_capabilities_is_additive_and_failed_job_error_must_preserve_job_id(self) -> None:
        legacy = NativeMessageRequest.model_validate_json(json.dumps(_request("get_capabilities", {}))).root
        self.assertEqual(legacy.payload.capability_contract_version, "1.0")
        versioned = NativeMessageRequest.model_validate_json(
            json.dumps(_request("get_capabilities", {"capability_contract_version": "1.0"}))
        ).root
        self.assertEqual(versioned.payload.capability_contract_version, "1.0")

        error = {
            "schema_version": "1.0",
            "code": ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE.value,
            "class": "provider",
            "retryable": False,
            "safe_message": "Synthetic adapter failed.",
            "internal_ref": "evt_synthetic_adapter_failure",
            "data_effect": "canonical_unchanged",
            "next_action": "capture_current",
        }
        valid = {
            "schema_version": "1.0",
            "request_id": "00000000-0000-4000-8000-000000000001",
            "accepted": False,
            "job_id": "00000000-0000-4000-8000-000000000002",
            "status": "rejected",
            "error": error,
            "capabilities": None,
        }
        NativeMessageResponse.model_validate_json(json.dumps(valid))
        invalid = dict(valid)
        invalid["job_id"] = None
        with self.assertRaises(ValidationError):
            NativeMessageResponse.model_validate_json(json.dumps(invalid))

    def test_sidepanel_health_handshake_requires_the_staged_release_identity(self) -> None:
        payload = {"mvp_browser_handshake": True, "mvp_release_artifact_sha256": "a" * 64}
        request = NativeMessageRequest.model_validate_json(json.dumps(_request("health", payload))).root
        self.assertEqual(request.payload.mvp_release_artifact_sha256, "a" * 64)

        for invalid_payload in (
            {"mvp_browser_handshake": True},
            {"mvp_release_artifact_sha256": "a" * 64},
            {"mvp_browser_handshake": True, "mvp_release_artifact_sha256": "not-a-digest"},
        ):
            with self.subTest(payload=invalid_payload):
                with self.assertRaises(ValidationError):
                    NativeMessageRequest.model_validate_json(json.dumps(_request("health", invalid_payload)))

    def test_pre_task_native_response_vector_omits_additive_capabilities_field(self) -> None:
        legacy = {
            "schema_version": "1.0",
            "request_id": "00000000-0000-4000-8000-000000000001",
            "accepted": True,
            "job_id": "00000000-0000-4000-8000-000000000002",
            "status": "queued",
            "error": None,
        }
        rendered = json.loads(
            NativeMessageResponse.model_validate_json(json.dumps(legacy)).model_dump_json(by_alias=True)
        )
        self.assertEqual(rendered, legacy)


if __name__ == "__main__":
    unittest.main()
