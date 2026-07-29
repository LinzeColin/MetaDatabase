from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from x2n_contracts import ErrorCode, canonical_json_sha256
from x2n_contracts.models import CapabilityFeatureFlag, CapabilityTerminal, Platform, RelationType, SyncScopeId

from x2n_companion import runtime_cli
from x2n_companion.adapter_dispatch import AdapterDispatcher
from x2n_companion.canonical_store import CanonicalStore
from x2n_companion import mvp_deployment
from x2n_companion.mvp_deployment import MvpDeploymentManager
from x2n_companion.mvp_release import (
    ARM_CONFIRMATION,
    MATERIALIZE_CONFIRMATION,
    MVP_CURRENT_SCOPE_ID,
    MVP_CURRENT_SECONDARY_SCOPE_ID,
    MVP_CURRENT_SCOPE_IDS,
    MvpActivationExecutor,
    MvpReleaseController,
    OwnerMvpManifestEnrollment,
    OwnerMvpReleaseInput,
    verify_owner_private_douyin_sidecar_bundle,
)
from x2n_companion.douyin_upstream import DouyinBatch, DouyinItem
from x2n_companion.douyin_visible_sidecar import (
    PROVISION_CONFIRMATION,
    clean_room_sidecar_build,
    provision_owner_private_visible_sidecar,
)
from x2n_companion.native_host import DEVELOPMENT_EXTENSION_ORIGIN, dispatch_wire
from x2n_companion.native_host_installer import UNINSTALL_CONFIRMATION, create_plan, execute_plan
from x2n_companion.runtime import DOWNLOAD_ENV, ROOT_ENV, RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OWNER_MVP_STATE_SCHEMA = PROJECT_ROOT / "machine/schemas/owner_mvp_release_state.schema.json"
A005_SCOPE_CHANGE_EVENT = "CE-X2N-20260729-S06-A005-XHS-TWO-CURRENT-BATCHES"


def _write_private(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def _owner_input() -> dict[str, object]:
    platform = {"login_state": "not_run", "real_execution_authorized": False}
    return {
        "schema_version": "1.0",
        "project": "x2n",
        "input_state": "owner_confirmed",
        "environment": {
            "os_strategy": "auto_detect",
            "hardware_strategy": "auto_detect",
            "detected_snapshot": "private_runtime_only",
        },
        "platforms": {
            "xiaohongshu": {"login_state": "owner_managed_profile", "real_execution_authorized": True},
            "douyin": {"login_state": "owner_managed_profile", "real_execution_authorized": True},
            "bilibili": dict(platform),
            "kuaishou": dict(platform),
            "weibo": dict(platform),
            "taobao": dict(platform),
        },
        "data_scale": "owner_manifested",
        "first_sync": "owner_authorized_direct_mvp",
        "taxonomy": {"top_level_categories": ["Unclassified"], "ai_may_create_top_level": False},
        "notion": {"enabled": False, "credential_reference": "unset", "parent_reference": "unset"},
        "models": {"cloud_enabled": False, "monthly_budget": 0, "currency": "AUD"},
        "gold_set": "synthetic_only",
        "media_retention": {
            "success": "delete_immediately",
            "failure_max_hours": 24,
            "persist_platform_cdn_urls": False,
            "persist_raw_media": False,
        },
    }


def _owner_sidecar_digests() -> dict[str, str]:
    return clean_room_sidecar_build().safe_dict()


def _write_owner_sidecar_bundle(paths: RuntimePaths) -> Path:
    provision_owner_private_visible_sidecar(paths, confirmation=PROVISION_CONFIRMATION)
    return paths.douyin_sidecar_bundle_directory


def _release_input() -> dict[str, object]:
    sidecar_digests = _owner_sidecar_digests()
    owner_contract = hashlib.sha256((PROJECT_ROOT / "docs/governance/OWNER_INPUT_CONTRACT.md").read_bytes()).hexdigest()
    return {
        "schema_version": "1.0",
        "project": "xhs-douyin-2notion",
        "release_version": "v0.0.0.1",
        "owner_authorization": "owner_authorized_direct_mvp",
        "owner_input_contract_sha256": owner_contract,
        "enabled_scopes": [
            {"scope_id": MVP_CURRENT_SCOPE_ID, "max_items": 20, "transport": "chrome_current_page_explicit"},
            {
                "scope_id": MVP_CURRENT_SECONDARY_SCOPE_ID,
                "max_items": 20,
                "transport": "chrome_current_page_explicit",
            },
            {
                "scope_id": "douyin_favorites",
                "max_items": 20,
                "transport": "owner_private_loopback_sidecar",
            },
            {"scope_id": "douyin_likes", "max_items": 20, "transport": "owner_private_loopback_sidecar"},
        ],
        "owner_private_manifests": [
            {
                "scope_id": scope,
                "content_id_sha256": [
                    hashlib.sha256(f"{prefix}-{index:02d}".encode("utf-8")).hexdigest() for index in range(20)
                ],
            }
            for scope, prefix in (
                (MVP_CURRENT_SCOPE_ID, "mvp-current-primary"),
                (MVP_CURRENT_SECONDARY_SCOPE_ID, "mvp-current-secondary"),
                ("douyin_favorites", "mvp-douyin-favorite"),
                ("douyin_likes", "mvp-douyin-like"),
            )
        ],
        "disabled_external_scopes": [
            {
                "scope_id": scope,
                "reason_code": "BLOCKED_AUTH",
                "flag_off": True,
                "platform_calls": 0,
                "live_support_claim": False,
            }
            for scope in (
                "bilibili_selected_collection",
                "kuaishou_selected_collection",
                "weibo_selected_collection",
                "taobao_selected_collection",
            )
        ],
        "douyin_sidecar": {
            "port": 1,
            "attestation": {
                "scope": "owner_private_build",
                **sidecar_digests,
            },
        },
        "model_mode": "disabled",
        "rollback_target": "previous_stable_or_disable",
    }


def _wire(payload: dict[str, object], *, request_id: str | None = None) -> bytes:
    return json.dumps(
        {
            "action": "start_sync",
            "payload": payload,
            "payload_hash": canonical_json_sha256(payload),
            "request_id": request_id or str(uuid.uuid4()),
            "schema_version": "1.0",
            "sent_at": "2026-07-29T00:00:00Z",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _capture_wire(payload: dict[str, object], *, request_id: str | None = None) -> bytes:
    return json.dumps(
        {
            "action": "capture_current",
            "payload": payload,
            "payload_hash": canonical_json_sha256(payload),
            "request_id": request_id or str(uuid.uuid4()),
            "schema_version": "1.0",
            "sent_at": "2026-07-29T00:00:00Z",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _current_content_payload(
    index: int,
    *,
    content_id: str | None = None,
    scope_id: str = MVP_CURRENT_SCOPE_ID,
) -> dict[str, object]:
    prefix = "mvp-current-primary" if scope_id == MVP_CURRENT_SCOPE_ID else "mvp-current-secondary"
    resolved_id = content_id or f"{prefix}-{index:02d}"
    return {
        "auto_scroll": False,
        "category_id": None,
        "change_account_state": False,
        "owner_mvp_scope": scope_id,
        "page_context": {"content_id": resolved_id, "content_type": "video", "title": f"Current {index}"},
        "page_url": f"https://www.xiaohongshu.com/explore/{resolved_id}",
        "platform": "xiaohongshu",
        "relation": "saved_current",
        "user_gesture": True,
    }


def _health_wire(artifact_sha256: str = "c" * 64) -> bytes:
    payload = {"mvp_browser_handshake": True, "mvp_release_artifact_sha256": artifact_sha256}
    return json.dumps(
        {
            "action": "health",
            "payload": payload,
            "payload_hash": canonical_json_sha256(payload),
            "request_id": str(uuid.uuid4()),
            "schema_version": "1.0",
            "sent_at": "2026-07-29T00:00:00Z",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _douyin_visible_batch(prefix: str = "mvp-douyin-favorite") -> dict[str, object]:
    return {
        "batch": {
            "automatic_scroll": False,
            "completion_signal": "bounded_limit_reached",
            "explicit_owner_action": True,
            "visible_card_count": 20,
        },
        "code": None,
        "errors": [],
        "items": [
            {"content_id": f"{prefix}-{index:02d}", "content_type": "video", "title": None} for index in range(20)
        ],
        "platform": "douyin",
        "schema_version": "1.0",
        "status": "ready",
    }


def _manifest_enrollment_payload(scope_id: str) -> dict[str, object]:
    platform = "douyin"
    relation = "favorited" if scope_id != "douyin_likes" else "liked"
    visible_batch: dict[str, object]
    if scope_id == "douyin_favorites":
        visible_batch = _douyin_visible_batch("mvp-douyin-favorite")
    elif scope_id == "douyin_likes":
        visible_batch = _douyin_visible_batch("mvp-douyin-like")
    else:
        raise AssertionError("unsupported manifest enrollment scope")
    return {
        "auto_scroll": False,
        "bounded_batch": True,
        "change_account_state": False,
        "dispatch_version": "1.0",
        "max_items": 20,
        "owner_mvp_manifest_enrollment": True,
        "platform": platform,
        "relation": relation,
        "scope_id": scope_id,
        "source_collection_id": None,
        "user_gesture": True,
        "visible_batch": visible_batch,
    }


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class MvpReleaseTests(unittest.TestCase):
    def test_a005_scope_amendment_is_bound_to_the_current_content_contract(self) -> None:
        change_event = (
            PROJECT_ROOT / "docs/governance/CHANGE_EVENT_S06_A005_XHS_TWO_CURRENT_CONTENT_BATCHES.md"
        ).read_text(encoding="utf-8")
        run_contract = (PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S06_ASSURANCE_005.md").read_text(encoding="utf-8")
        taskpack = (PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml").read_text(
            encoding="utf-8"
        )
        task = taskpack.split("- id: TSK.x2n.assurance.005", maxsplit=1)[1].split("stage_gates:", maxsplit=1)[0]
        for rendered in (change_event, run_contract):
            self.assertIn(A005_SCOPE_CHANGE_EVENT, rendered)
            self.assertIn("xiaohongshu_current_content", rendered)
            self.assertIn(MVP_CURRENT_SECONDARY_SCOPE_ID, rendered)
            self.assertIn("saved_current", rendered)
        self.assertIn(A005_SCOPE_CHANGE_EVENT, task)
        self.assertIn("xiaohongshu_current_content", taskpack)
        self.assertIn(MVP_CURRENT_SECONDARY_SCOPE_ID, taskpack)
        self.assertIn("saved_current", task)
        self.assertNotIn("ACC.x2n.xhs.002", task)

    def test_owner_mvp_state_schema_tracks_runtime_knowledge_asset_gate(self) -> None:
        schema = json.loads(OWNER_MVP_STATE_SCHEMA.read_text(encoding="utf-8"))
        rendered = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        self.assertEqual(schema["$id"], "urn:x2n:owner-mvp-release-state:1.3")
        self.assertEqual(schema["properties"]["schema_version"], {"const": "1.3"})
        self.assertIn("knowledge_assets", schema["required"])
        self.assertIn("current_content_captures", schema["required"])
        self.assertEqual(
            schema["properties"]["knowledge_assets"]["properties"]["notion_mode"],
            {"const": "DISABLED_OWNER_INPUT"},
        )
        self.assertEqual(schema["properties"]["knowledge_assets"]["properties"]["notion_platform_calls"], {"const": 0})
        self.assertNotIn("/" + "Users/", rendered)

    def test_release_preflight_is_aggregate_only_and_never_arms(self) -> None:
        self.paths.owner_mvp_release_input.unlink()
        args = runtime_cli.build_parser().parse_args(["release", "preflight"])
        with (
            mock.patch.dict(
                os.environ,
                {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
                clear=True,
            ),
            mock.patch.object(MvpDeploymentManager, "assert_release_source_tagged"),
            mock.patch(
                "x2n_companion.runtime_cli.DigestPinnedPrivateDbClient.from_environment",
                side_effect=X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "private client unavailable"),
            ),
            mock.patch(
                "x2n_companion.runtime_cli.fresh_install_readiness",
                return_value="READY_FOR_FRESH_INSTALL",
            ),
            mock.patch("x2n_companion.runtime_cli.chrome_available", return_value=True),
            mock.patch.object(MvpReleaseController, "arm") as arm,
        ):
            payload = runtime_cli.run(args)
        self.assertEqual(payload["action"], "release_preflight")
        self.assertEqual(payload["acceptance_scope"], "ASSURANCE_005_DIRECT_MVP_PREFLIGHT")
        self.assertEqual(payload["task_id"], "TSK.x2n.assurance.005")
        self.assertEqual(
            payload["preflight"],
            {
                "chrome_executable": "AVAILABLE",
                "douyin_sidecar_bundle": "CONFIGURED_CLEAN_ROOM_UNATTESTED",
                "native_host_fresh_install": "READY_FOR_FRESH_INSTALL",
                "notion_calls": 0,
                "owner_mvp_manifest_enrollment": "NOT_STARTED",
                "owner_input": "MISSING_OR_INVALID",
                "platform_calls": 0,
                "private_durability_client": "NOT_READY",
                "ready_to_arm": False,
                "release_state": "NOT_STARTED",
                "source_release_tag": "READY",
            },
        )
        self.assertNotIn(str(self.paths.data_root), json.dumps(payload, ensure_ascii=False, sort_keys=True))
        arm.assert_not_called()

    def test_release_preflight_recognizes_a_valid_input_without_disclosing_it(self) -> None:
        args = runtime_cli.build_parser().parse_args(["release", "preflight"])
        with (
            mock.patch.dict(
                os.environ,
                {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
                clear=True,
            ),
            mock.patch.object(MvpDeploymentManager, "assert_release_source_tagged"),
            mock.patch(
                "x2n_companion.runtime_cli.DigestPinnedPrivateDbClient.from_environment",
                return_value=SimpleNamespace(),
            ),
            mock.patch(
                "x2n_companion.runtime_cli.fresh_install_readiness",
                return_value="READY_FOR_FRESH_INSTALL",
            ),
            mock.patch("x2n_companion.runtime_cli.chrome_available", return_value=True),
        ):
            payload = runtime_cli.run(args)
        preflight = payload["preflight"]
        self.assertEqual(preflight["owner_input"], "VALID")
        self.assertEqual(preflight["douyin_sidecar_bundle"], "CONFIGURED_AND_MATCHED")
        self.assertTrue(preflight["ready_to_arm"])
        self.assertEqual(preflight["private_durability_client"], "CONFIGURED_AND_PINNED")
        self.assertEqual(preflight["native_host_fresh_install"], "READY_FOR_FRESH_INSTALL")
        self.assertEqual(preflight["chrome_executable"], "AVAILABLE")
        self.assertNotIn("input_sha256", json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def test_release_preflight_reports_missing_chrome_without_opening_it(self) -> None:
        self.paths.owner_mvp_release_input.unlink()
        args = runtime_cli.build_parser().parse_args(["release", "preflight"])
        with (
            mock.patch.dict(
                os.environ,
                {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
                clear=True,
            ),
            mock.patch.object(MvpDeploymentManager, "assert_release_source_tagged"),
            mock.patch(
                "x2n_companion.runtime_cli.DigestPinnedPrivateDbClient.from_environment",
                side_effect=X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "private client unavailable"),
            ),
            mock.patch(
                "x2n_companion.runtime_cli.fresh_install_readiness",
                return_value="READY_FOR_FRESH_INSTALL",
            ),
            mock.patch("x2n_companion.runtime_cli.chrome_available", return_value=False),
            mock.patch.object(MvpReleaseController, "arm") as arm,
        ):
            payload = runtime_cli.run(args)
        self.assertEqual(payload["preflight"]["chrome_executable"], "NOT_READY")
        self.assertEqual(
            payload["preflight"]["douyin_sidecar_bundle"],
            "CONFIGURED_CLEAN_ROOM_UNATTESTED",
        )
        self.assertFalse(payload["preflight"]["ready_to_arm"])
        arm.assert_not_called()

    def test_release_preflight_rejects_missing_clean_room_bundle_without_owner_input(self) -> None:
        self.paths.owner_mvp_release_input.unlink()
        (self.sidecar_bundle / "sidecar").unlink()
        args = runtime_cli.build_parser().parse_args(["release", "preflight"])
        with (
            mock.patch.dict(
                os.environ,
                {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
                clear=True,
            ),
            mock.patch.object(MvpDeploymentManager, "assert_release_source_tagged"),
            mock.patch(
                "x2n_companion.runtime_cli.DigestPinnedPrivateDbClient.from_environment",
                side_effect=X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "private client unavailable"),
            ),
            mock.patch(
                "x2n_companion.runtime_cli.fresh_install_readiness",
                return_value="READY_FOR_FRESH_INSTALL",
            ),
            mock.patch("x2n_companion.runtime_cli.chrome_available", return_value=True),
        ):
            payload = runtime_cli.run(args)
        self.assertEqual(payload["preflight"]["owner_input"], "MISSING_OR_INVALID")
        self.assertEqual(payload["preflight"]["douyin_sidecar_bundle"], "MISSING_OR_INVALID")
        self.assertFalse(payload["preflight"]["ready_to_arm"])

    def test_input_template_requires_real_owner_facts_before_validation(self) -> None:
        args = runtime_cli.build_parser().parse_args(["release", "input-template"])
        payload = runtime_cli.run(args)
        template = payload["template"]
        self.assertEqual(payload["task_id"], "TSK.x2n.assurance.005")
        self.assertEqual(payload["real_account_execution"], "NOT_RUN")
        self.assertEqual(len(template["owner_private_manifests"]), 4)
        self.assertEqual(
            [scope["scope_id"] for scope in template["enabled_scopes"]],
            [
                MVP_CURRENT_SCOPE_ID,
                MVP_CURRENT_SECONDARY_SCOPE_ID,
                SyncScopeId.DOUYIN_FAVORITES.value,
                SyncScopeId.DOUYIN_LIKES.value,
            ],
        )
        self.assertEqual(
            [manifest["scope_id"] for manifest in template["owner_private_manifests"]],
            [
                MVP_CURRENT_SCOPE_ID,
                MVP_CURRENT_SECONDARY_SCOPE_ID,
                SyncScopeId.DOUYIN_FAVORITES.value,
                SyncScopeId.DOUYIN_LIKES.value,
            ],
        )
        self.assertEqual(template["douyin_sidecar"]["port"], "REPLACE_WITH_OWNER_LOOPBACK_PORT")
        for manifest in template["owner_private_manifests"]:
            self.assertEqual(len(manifest["content_id_sha256"]), 20)
            self.assertTrue(
                all(
                    value.startswith("REPLACE_WITH_OWNER_CONTENT_ID_SHA256_") for value in manifest["content_id_sha256"]
                )
            )
        with self.assertRaises(X2NRuntimeError):
            OwnerMvpReleaseInput.from_mapping(template)
        rendered = json.dumps(template, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("https://", rendered)
        self.assertNotIn("/" + "Users/", rendered)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="x2n-mvp-release-")
        destination = Path(self.temporary.name) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        destination.chmod(0o700)
        self.paths = RuntimePaths.from_values(
            str(destination / "xhs-douyin-2notion"),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        self.store = CanonicalStore(self.paths)
        self.store.initialize()
        _write_private(self.paths.data_root / "runtime/owner_input_contract.local.json", _owner_input())
        self.paths.ensure_private_directory("runtime/release")
        self.sidecar_bundle = _write_owner_sidecar_bundle(self.paths)
        _write_private(self.paths.owner_mvp_release_input, _release_input())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_arm_exposes_exact_four_candidate_scopes_and_external_gates(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        outcomes = controller.capability_registry().evaluate(evaluated_at="2026-07-29T00:00:00Z").outcomes
        enabled = [item for item in outcomes if item.feature_flag is CapabilityFeatureFlag.MVP_ACTIVATION_CANDIDATE]
        self.assertEqual(len(enabled), 2)
        self.assertTrue(all(item.feature_flag is CapabilityFeatureFlag.MVP_ACTIVATION_CANDIDATE for item in enabled))
        self.assertTrue(all(item.terminal is CapabilityTerminal.READY_FOR_MVP_ACTIVATION for item in enabled))
        deferred_xhs = [
            item
            for item in outcomes
            if item.scope_id in {SyncScopeId.XIAOHONGSHU_FAVORITES, SyncScopeId.XIAOHONGSHU_LIKES}
        ]
        self.assertEqual(len(deferred_xhs), 2)
        self.assertTrue(all(item.feature_flag is CapabilityFeatureFlag.CI_SYNTHETIC_ONLY for item in deferred_xhs))
        self.assertTrue(
            all(
                item.feature_flag is CapabilityFeatureFlag.DISABLED
                for item in outcomes
                if item not in enabled and item not in deferred_xhs
            )
        )
        external_gates = controller.external_gate_settlements()
        self.assertEqual(
            [row["scope_id"] for row in external_gates],
            [
                "bilibili_selected_collection",
                "kuaishou_selected_collection",
                "weibo_selected_collection",
                "taobao_selected_collection",
            ],
        )
        self.assertTrue(
            all(
                row["status"] == "PASS_DISABLED_EXTERNAL_GATE"
                and row["feature_flag"] == "disabled"
                and row["platform_calls"] == 0
                and row["live_support_claim"] is False
                for row in external_gates
            )
        )
        self.store.persist_capability_snapshot(controller.capability_registry().evaluate())
        self.assertEqual(controller.external_gate_settlements(store=self.store), external_gates)
        self.assertTrue(self.paths._validate_marker()["product_execution_authorized"])

    def test_owner_private_sidecar_bundle_is_aggregate_only_and_digest_bound(self) -> None:
        release_input = OwnerMvpReleaseInput.from_mapping(_release_input())
        self.assertEqual(
            verify_owner_private_douyin_sidecar_bundle(self.paths, release_input.douyin_build),
            {"artifact_count": 4, "paths_emitted": False, "status": "VERIFIED"},
        )
        sidecar = self.sidecar_bundle / "sidecar"
        sidecar.write_bytes(b"drifted-owner-sidecar\n")
        sidecar.chmod(0o700)
        with self.assertRaises(X2NRuntimeError) as blocked:
            verify_owner_private_douyin_sidecar_bundle(self.paths, release_input.douyin_build)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertNotIn(str(self.paths.data_root), str(blocked.exception))

    def test_arm_requires_matched_owner_private_sidecar_before_backup(self) -> None:
        sidecar = self.sidecar_bundle / "sidecar"
        sidecar.write_bytes(b"drifted-owner-sidecar\n")
        sidecar.chmod(0o700)
        with mock.patch.object(self.store, "backup") as backup:
            with self.assertRaises(X2NRuntimeError) as blocked:
                MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        backup.assert_not_called()
        self.assertFalse(self.paths.owner_mvp_release_state.exists())
        self.assertFalse(self.paths._validate_marker()["product_execution_authorized"])

    def test_arm_rejects_a_dangling_release_state_link_before_backup(self) -> None:
        self.paths.owner_mvp_release_state.symlink_to("missing-owner-mvp-release-state")
        with mock.patch.object(self.store, "backup") as backup:
            with self.assertRaises(X2NRuntimeError) as blocked:
                MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        backup.assert_not_called()
        self.assertTrue(self.paths.owner_mvp_release_state.is_symlink())

    def test_load_rejects_dangling_owner_private_release_links(self) -> None:
        self.paths.owner_mvp_release_input.unlink()
        self.paths.owner_mvp_release_input.symlink_to("missing-owner-mvp-release-input")
        with self.assertRaises(X2NRuntimeError) as blocked_input:
            MvpReleaseController.load(self.paths, require_state=False)
        self.assertEqual(blocked_input.exception.code, ErrorCode.POLICY_BLOCKED)

        self.paths.owner_mvp_release_input.unlink()
        _write_private(self.paths.owner_mvp_release_input, _release_input())
        self.paths.owner_mvp_release_state.symlink_to("missing-owner-mvp-release-state")
        with self.assertRaises(X2NRuntimeError) as blocked_state:
            MvpReleaseController.load(self.paths, require_state=False)
        self.assertEqual(blocked_state.exception.code, ErrorCode.POLICY_BLOCKED)

    def test_persist_rejects_a_dangling_release_state_link(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        self.paths.owner_mvp_release_state.unlink()
        self.paths.owner_mvp_release_state.symlink_to("missing-owner-mvp-release-state")
        with self.assertRaises(X2NRuntimeError) as blocked:
            controller._persist()
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertTrue(self.paths.owner_mvp_release_state.is_symlink())

    def test_douyin_execution_rechecks_sidecar_bundle_before_any_loopback_call(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        sidecar = self.sidecar_bundle / "sidecar"
        sidecar.write_bytes(b"drifted-owner-sidecar\n")
        sidecar.chmod(0o700)
        binding = AdapterDispatcher.binding_for(
            SyncScopeId.DOUYIN_FAVORITES,
            platform=Platform.DOUYIN,
            relation=RelationType.FAVORITED,
        )
        with mock.patch("x2n_companion.mvp_release.OwnerPrivateVisibleSidecarClient") as sidecar_client:
            with self.assertRaises(X2NRuntimeError) as blocked:
                MvpActivationExecutor(controller, self.store)._execute_douyin(
                    binding=binding,
                    payload=SimpleNamespace(max_items=20),
                    scan_id=controller.scope_scan_id(SyncScopeId.DOUYIN_FAVORITES),
                )
        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        sidecar_client.assert_not_called()
        self.assertEqual(self.store.counts()["content"], 0)
        self.assertEqual(self.store.counts()["user_relation"], 0)

    def test_current_content_batches_record_two_disjoint_twenty_item_detail_sets(self) -> None:
        MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        for scope_id in MVP_CURRENT_SCOPE_IDS:
            for index in range(20):
                response = dispatch_wire(
                    _capture_wire(_current_content_payload(index, scope_id=scope_id)),
                    origin=DEVELOPMENT_EXTENSION_ORIGIN,
                    store=self.store,
                )
                self.assertTrue(response.accepted)
                self.assertEqual(response.status.value, "completed")
        controller = MvpReleaseController.load(self.paths)
        assert controller is not None
        self.assertEqual(set(controller.state["current_content_captures"]), set(MVP_CURRENT_SCOPE_IDS))
        self.assertTrue(
            all(len(controller.state["current_content_captures"][scope_id]) == 20 for scope_id in MVP_CURRENT_SCOPE_IDS)
        )
        self.assertTrue(all(scope_id in controller.state["scope_jobs"] for scope_id in MVP_CURRENT_SCOPE_IDS))
        for scope_id in MVP_CURRENT_SCOPE_IDS:
            snapshot = self.store.owner_mvp_current_content_snapshot(
                capture_job_ids=controller.state["current_content_captures"][scope_id],
                expected_content_id_hashes=controller.release_input.scope_manifest_hashes[scope_id],
            )
            self.assertEqual(snapshot["active_count"], 20)
            self.assertEqual(snapshot["content_count"], 20)
            self.assertEqual(snapshot["observation_count"], 20)
            self.assertEqual(snapshot["relation_count"], 20)
            self.assertTrue(snapshot["scan_complete"])

        duplicate = dispatch_wire(
            _capture_wire(_current_content_payload(0)),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertFalse(duplicate.accepted)
        self.assertEqual(self.store.counts()["content"], 40)
        self.assertEqual(self.store.counts()["user_relation"], 40)

        controller.state["current_content_captures"][MVP_CURRENT_SCOPE_ID].pop(
            next(iter(controller.state["current_content_captures"][MVP_CURRENT_SCOPE_ID]))
        )
        with self.assertRaises(X2NRuntimeError):
            controller._persist()

    def test_hash_only_prearm_enrollment_freezes_exact_four_manifests_without_canonical_writes(self) -> None:
        self.paths.owner_mvp_release_input.unlink()
        for scope_id in ("douyin_favorites", "douyin_likes"):
            response = dispatch_wire(
                _wire(_manifest_enrollment_payload(scope_id)),
                origin=DEVELOPMENT_EXTENSION_ORIGIN,
                store=self.store,
            )
            self.assertTrue(response.accepted)
            self.assertEqual(response.status.value, "completed")
            self.assertIsNone(response.job_id)
        for scope_id in MVP_CURRENT_SCOPE_IDS:
            for index in range(19):
                response = dispatch_wire(
                    _capture_wire(_current_content_payload(index, scope_id=scope_id)),
                    origin=DEVELOPMENT_EXTENSION_ORIGIN,
                    store=self.store,
                )
                self.assertTrue(response.accepted)
                self.assertEqual(response.status.value, "completed")
                self.assertIsNone(response.job_id)

        enrollment = OwnerMvpManifestEnrollment.load_or_create(self.paths)
        self.assertEqual(
            enrollment.safe_summary(),
            {
                "canonical_writes": 0,
                "complete_scope_count": 2,
                "manifest_item_count": 78,
                "manifest_scope_count": 4,
                "notion_calls": 0,
                "platform_calls": 0,
                "private_hashes_only": True,
                "release_input_created": False,
            },
        )
        first_final_response = dispatch_wire(
            _capture_wire(_current_content_payload(19, scope_id=MVP_CURRENT_SCOPE_ID)),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertTrue(first_final_response.accepted)
        self.assertFalse(self.paths.owner_mvp_release_input.exists())
        final_response = dispatch_wire(
            _capture_wire(_current_content_payload(19, scope_id=MVP_CURRENT_SECONDARY_SCOPE_ID)),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertTrue(final_response.accepted)
        self.assertEqual(final_response.status.value, "completed")
        self.assertIsNone(final_response.job_id)

        counts = self.store.counts()
        for table in (
            "artifact",
            "checkpoint",
            "content",
            "request_ledger",
            "run_record",
            "source_observation",
            "user_relation",
        ):
            self.assertEqual(counts[table], 0)
        self.assertTrue(self.paths.owner_mvp_release_input.exists())
        release_input = OwnerMvpReleaseInput.from_mapping(
            json.loads(self.paths.owner_mvp_release_input.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            set(release_input.scope_manifest_hashes),
            {MVP_CURRENT_SCOPE_ID, MVP_CURRENT_SECONDARY_SCOPE_ID, "douyin_favorites", "douyin_likes"},
        )
        rendered_private = self.paths.owner_mvp_manifest_enrollment.read_text(
            encoding="utf-8"
        ) + self.paths.owner_mvp_release_input.read_text(encoding="utf-8")
        self.assertNotIn("mvp-current-primary-00", rendered_private)
        self.assertNotIn("mvp-current-secondary-00", rendered_private)
        self.assertNotIn("mvp-douyin-like-00", rendered_private)
        self.assertNotIn("https://", rendered_private)

        after_frozen = dispatch_wire(
            _wire(_manifest_enrollment_payload("douyin_favorites")),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertFalse(after_frozen.accepted)
        self.assertEqual(self.store.counts()["content"], 0)

    def test_current_content_manifest_mismatch_blocks_before_a_canonical_write(self) -> None:
        MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        response = dispatch_wire(
            _capture_wire(_current_content_payload(0, content_id="not-owner-selected")),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertFalse(response.accepted)
        self.assertEqual(self.store.counts()["content"], 0)
        self.assertEqual(self.store.counts()["user_relation"], 0)

    def test_native_host_commits_one_clean_room_douyin_visible_sidecar_action(self) -> None:
        release_input = _release_input()
        sidecar = release_input["douyin_sidecar"]
        assert isinstance(sidecar, dict)
        sidecar["port"] = _available_loopback_port()
        _write_private(self.paths.owner_mvp_release_input, release_input)
        MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        payload: dict[str, object] = {
            "auto_scroll": False,
            "bounded_batch": True,
            "change_account_state": False,
            "dispatch_version": "1.0",
            "max_items": 20,
            "platform": "douyin",
            "relation": "favorited",
            "scope_id": "douyin_favorites",
            "source_collection_id": None,
            "user_gesture": True,
            "visible_batch": _douyin_visible_batch(),
        }
        response = dispatch_wire(_wire(payload), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertTrue(response.accepted)
        self.assertEqual(response.status.value, "completed")
        self.assertEqual(self.store.counts()["content"], 20)
        self.assertEqual(self.store.counts()["user_relation"], 20)
        controller = MvpReleaseController.load(self.paths)
        assert controller is not None
        self.assertEqual(set(controller.state["scope_jobs"]), {"douyin_favorites"})

    def test_private_manifest_mismatch_blocks_before_any_canonical_write(self) -> None:
        MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        response = dispatch_wire(
            _capture_wire(_current_content_payload(0, content_id="unselected-current-content")),
            origin=DEVELOPMENT_EXTENSION_ORIGIN,
            store=self.store,
        )
        self.assertFalse(response.accepted)
        self.assertEqual(self.store.counts()["content"], 0)
        self.assertEqual(self.store.counts()["user_relation"], 0)

    def test_douyin_manifest_mismatch_stops_before_the_adapter_scan_is_initialized(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        binding = AdapterDispatcher.binding_for(
            SyncScopeId.DOUYIN_FAVORITES,
            platform=Platform.DOUYIN,
            relation=RelationType.FAVORITED,
        )
        batch = DouyinBatch(
            mode="favorites",
            sequence=0,
            status="ready",
            completion_signal="bounded_limit_reached",
            items=tuple(
                DouyinItem(
                    content_id=f"unselected-douyin-{index:02d}", content_type="video", title=None, collection=None
                )
                for index in range(20)
            ),
            error_codes=(),
            upstream_error_count=0,
        )

        def deliver_mismatched_batch(*_args: object, **kwargs: object) -> object:
            validator = kwargs["batch_validator"]
            assert callable(validator)
            return validator(batch)

        with mock.patch("x2n_companion.mvp_release.DouyinAdapter.begin_scan") as begin_scan:
            with mock.patch(
                "x2n_companion.mvp_release.DouyinBatchCoordinator.apply_owner_action",
                side_effect=deliver_mismatched_batch,
            ):
                with self.assertRaises(X2NRuntimeError):
                    MvpActivationExecutor(controller, self.store)._execute_douyin(
                        binding=binding,
                        payload=SimpleNamespace(
                            max_items=20,
                            visible_batch=SimpleNamespace(
                                model_dump=lambda **_kwargs: _douyin_visible_batch(),
                            ),
                        ),
                        scan_id=controller.scope_scan_id(SyncScopeId.DOUYIN_FAVORITES),
                    )
        begin_scan.assert_not_called()
        self.assertEqual(self.store.counts()["content"], 0)
        self.assertEqual(self.store.counts()["user_relation"], 0)
        self.assertEqual(self.store.counts()["source_observation"], 0)

    def test_secret_or_extra_release_input_field_is_rejected(self) -> None:
        invalid = _release_input()
        invalid["token"] = "not-allowed"
        with self.assertRaises(X2NRuntimeError):
            OwnerMvpReleaseInput.from_mapping(invalid)

    def test_installed_native_host_uses_the_pinned_owner_contract_digest_without_repo_docs(self) -> None:
        with mock.patch(
            "x2n_companion.mvp_release.OWNER_INPUT_CONTRACT",
            Path(self.temporary.name) / "not-present-in-native-host-runtime.md",
        ):
            release_input = OwnerMvpReleaseInput.from_mapping(_release_input())
        self.assertEqual(release_input.input_sha256, canonical_json_sha256(_release_input()))

    def test_blue_green_stage_does_not_switch_before_explicit_activation_and_rolls_back_to_disabled(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage()
        current = self.paths.ensure_private_directory("runtime/install") / "current"
        self.assertFalse(current.exists() or current.is_symlink())
        switched = manager.switch(staged)
        self.assertEqual(switched.current_version, "v0.0.0.1")
        rollback = manager.rollback_pointer()
        self.assertEqual(rollback["current_version"], "disabled")

    def test_deploy_discards_staged_release_when_native_host_install_fails(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = mvp_deployment.StagedRelease(artifact_sha256="a" * 64)
        install_error = X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "synthetic Native Host install failure")
        with (
            mock.patch.object(manager, "assert_release_source_tagged") as source_tagged,
            mock.patch.object(manager, "stage", return_value=staged) as stage,
            mock.patch.object(manager, "install_native_host", side_effect=install_error) as install_native_host,
            mock.patch.object(manager, "switch") as switch,
            mock.patch.object(manager, "uninstall_native_host") as uninstall_native_host,
            mock.patch.object(manager, "discard_staged") as discard_staged,
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                manager.deploy(confirmation=mvp_deployment.DEPLOY_CONFIRMATION, browser="chrome")

        self.assertEqual(blocked.exception.code, ErrorCode.DEPENDENCY_MISSING)
        source_tagged.assert_called_once_with()
        stage.assert_called_once_with()
        install_native_host.assert_called_once_with(
            confirmation=mvp_deployment.DEPLOY_CONFIRMATION,
            browser="chrome",
            staged=staged,
        )
        switch.assert_not_called()
        uninstall_native_host.assert_not_called()
        discard_staged.assert_called_once_with()

    def test_deploy_uninstalls_native_host_and_discards_stage_when_switch_fails(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = mvp_deployment.StagedRelease(artifact_sha256="b" * 64)
        switch_error = X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "synthetic pointer switch failure")
        with (
            mock.patch.object(manager, "assert_release_source_tagged"),
            mock.patch.object(manager, "stage", return_value=staged),
            mock.patch.object(
                manager,
                "install_native_host",
                return_value={"native_host_installed": True, "paths_emitted": False},
            ) as install_native_host,
            mock.patch.object(manager, "switch", side_effect=switch_error) as switch,
            mock.patch.object(
                manager,
                "uninstall_native_host",
                return_value={"native_host_uninstalled": True, "paths_emitted": False},
            ) as uninstall_native_host,
            mock.patch.object(manager, "rollback_pointer") as rollback_pointer,
            mock.patch.object(manager, "discard_staged") as discard_staged,
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                manager.deploy(confirmation=mvp_deployment.DEPLOY_CONFIRMATION, browser="chrome")

        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        install_native_host.assert_called_once_with(
            confirmation=mvp_deployment.DEPLOY_CONFIRMATION,
            browser="chrome",
            staged=staged,
        )
        switch.assert_called_once_with(staged)
        uninstall_native_host.assert_called_once_with(browser="chrome")
        rollback_pointer.assert_not_called()
        discard_staged.assert_called_once_with()

    def test_deploy_fails_closed_when_staged_release_cleanup_fails(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = mvp_deployment.StagedRelease(artifact_sha256="c" * 64)
        install_error = X2NRuntimeError(ErrorCode.DEPENDENCY_MISSING, "synthetic Native Host install failure")
        cleanup_error = X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "synthetic staged cleanup failure")
        with (
            mock.patch.object(manager, "assert_release_source_tagged"),
            mock.patch.object(manager, "stage", return_value=staged),
            mock.patch.object(manager, "install_native_host", side_effect=install_error),
            mock.patch.object(manager, "switch") as switch,
            mock.patch.object(manager, "uninstall_native_host") as uninstall_native_host,
            mock.patch.object(manager, "discard_staged", side_effect=cleanup_error) as discard_staged,
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                manager.deploy(confirmation=mvp_deployment.DEPLOY_CONFIRMATION, browser="chrome")

        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        switch.assert_not_called()
        uninstall_native_host.assert_not_called()
        discard_staged.assert_called_once_with()

    def test_cli_deploy_rolls_back_when_deployment_state_cannot_be_recorded(self) -> None:
        controller = SimpleNamespace(
            mark_deployed=mock.Mock(
                side_effect=X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "synthetic deployment state failure")
            )
        )
        manager = mock.Mock()
        manager.deploy.return_value = {"artifact_sha256": "d" * 64}
        args = runtime_cli.build_parser().parse_args(
            ["release", "deploy", "--browser", "chrome", "--confirm", mvp_deployment.DEPLOY_CONFIRMATION]
        )
        with (
            mock.patch.object(runtime_cli, "_paths", return_value=self.paths),
            mock.patch.object(MvpReleaseController, "load", return_value=controller),
            mock.patch.object(runtime_cli, "MvpDeploymentManager", return_value=manager),
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                runtime_cli.run(args)

        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        manager.deploy.assert_called_once_with(confirmation=mvp_deployment.DEPLOY_CONFIRMATION, browser="chrome")
        controller.mark_deployed.assert_called_once_with(artifact_sha256="d" * 64, browser="chrome")
        manager.rollback_deployment.assert_called_once_with(browser="chrome")

    def test_cli_deploy_normalizes_generic_state_persistence_failure_after_rollback(self) -> None:
        controller = SimpleNamespace(mark_deployed=mock.Mock(side_effect=OSError("synthetic deployment state failure")))
        manager = mock.Mock()
        manager.deploy.return_value = {"artifact_sha256": "e" * 64}
        args = runtime_cli.build_parser().parse_args(
            ["release", "deploy", "--browser", "chrome", "--confirm", mvp_deployment.DEPLOY_CONFIRMATION]
        )
        with (
            mock.patch.object(runtime_cli, "_paths", return_value=self.paths),
            mock.patch.object(MvpReleaseController, "load", return_value=controller),
            mock.patch.object(runtime_cli, "MvpDeploymentManager", return_value=manager),
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                runtime_cli.run(args)

        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertNotIn("synthetic deployment state failure", blocked.exception.safe_message)
        manager.rollback_deployment.assert_called_once_with(browser="chrome")

    def test_cli_deploy_normalizes_any_rollback_cleanup_failure(self) -> None:
        controller = SimpleNamespace(
            mark_deployed=mock.Mock(
                side_effect=X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "synthetic deployment state failure")
            )
        )
        manager = mock.Mock()
        manager.deploy.return_value = {"artifact_sha256": "f" * 64}
        manager.rollback_deployment.side_effect = OSError("synthetic private rollback I/O failure")
        args = runtime_cli.build_parser().parse_args(
            ["release", "deploy", "--browser", "chrome", "--confirm", mvp_deployment.DEPLOY_CONFIRMATION]
        )
        with (
            mock.patch.object(runtime_cli, "_paths", return_value=self.paths),
            mock.patch.object(MvpReleaseController, "load", return_value=controller),
            mock.patch.object(runtime_cli, "MvpDeploymentManager", return_value=manager),
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                runtime_cli.run(args)

        self.assertEqual(blocked.exception.code, ErrorCode.POLICY_BLOCKED)
        self.assertNotIn("synthetic private rollback I/O failure", blocked.exception.safe_message)
        manager.rollback_deployment.assert_called_once_with(browser="chrome")

    def test_rollback_deployment_disables_native_host_before_switching_the_pointer(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        calls: list[str] = []

        def uninstall_native_host(*, browser: str | None) -> dict[str, object]:
            calls.append("uninstall_native_host")
            self.assertEqual(browser, "chrome")
            return {"native_host_uninstalled": True, "paths_emitted": False, "rollback_target": "disabled"}

        def rollback_pointer() -> dict[str, object]:
            calls.append("rollback_pointer")
            return {
                "current_version": "disabled",
                "paths_emitted": False,
                "release_version": "v0.0.0.1",
                "rollback_pointer_switched": False,
            }

        with (
            mock.patch.object(manager, "uninstall_native_host", side_effect=uninstall_native_host),
            mock.patch.object(manager, "rollback_pointer", side_effect=rollback_pointer),
        ):
            receipt = manager.rollback_deployment(browser="chrome")

        self.assertEqual(calls, ["uninstall_native_host", "rollback_pointer"])
        self.assertEqual(receipt["native_host"]["rollback_target"], "disabled")
        self.assertEqual(receipt["pointer"]["current_version"], "disabled")
        self.assertFalse(receipt["paths_emitted"])

    def test_rollback_deployment_does_not_switch_pointer_when_native_host_disable_fails(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        disable_error = X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "synthetic Native Host disable failure")
        with (
            mock.patch.object(manager, "uninstall_native_host", side_effect=disable_error) as uninstall_native_host,
            mock.patch.object(manager, "rollback_pointer") as rollback_pointer,
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                manager.rollback_deployment(browser="chrome")

        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        uninstall_native_host.assert_called_once_with(browser="chrome")
        rollback_pointer.assert_not_called()

    def test_rollback_deployment_preserves_pointer_failure_after_native_host_is_disabled(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        pointer_error = X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "synthetic pointer rollback failure")
        with (
            mock.patch.object(
                manager,
                "uninstall_native_host",
                return_value={"native_host_uninstalled": True, "paths_emitted": False, "rollback_target": "disabled"},
            ) as uninstall_native_host,
            mock.patch.object(manager, "rollback_pointer", side_effect=pointer_error) as rollback_pointer,
        ):
            with self.assertRaises(X2NRuntimeError) as blocked:
                manager.rollback_deployment(browser="chrome")

        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)
        uninstall_native_host.assert_called_once_with(browser="chrome")
        rollback_pointer.assert_called_once_with()

    def test_blue_green_switch_restores_both_pointers_after_a_partial_failure(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage()
        install = self.paths.ensure_private_directory("runtime/install")
        current = install / "current"
        previous = install / "previous"
        real_replace = mvp_deployment._replace_link

        def fail_current(path: Path, *, target_name: str | None) -> None:
            if path == current and target_name == "v0.0.0.1":
                raise OSError("synthetic current pointer failure")
            real_replace(path, target_name=target_name)

        with mock.patch("x2n_companion.mvp_deployment._replace_link", side_effect=fail_current):
            with self.assertRaises(X2NRuntimeError):
                manager.switch(staged)
        self.assertFalse(current.exists() or current.is_symlink())
        self.assertFalse(previous.exists() or previous.is_symlink())
        manager.discard_staged()

    def test_rollback_pointer_restores_the_release_pair_after_a_partial_failure(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        manager.stage()
        install = self.paths.ensure_private_directory("runtime/install")
        versions = install / "versions"
        previous_version = "v0.0.0.0"
        (versions / previous_version).mkdir(mode=0o700)
        current = install / "current"
        previous = install / "previous"
        mvp_deployment._replace_link(current, target_name="v0.0.0.1")
        mvp_deployment._replace_link(previous, target_name=previous_version)
        real_replace = mvp_deployment._replace_link

        def fail_previous(path: Path, *, target_name: str | None) -> None:
            if path == previous and target_name == "v0.0.0.1":
                raise OSError("synthetic previous pointer failure")
            real_replace(path, target_name=target_name)

        with mock.patch("x2n_companion.mvp_deployment._replace_link", side_effect=fail_previous):
            with self.assertRaises(X2NRuntimeError):
                manager.rollback_pointer()
        self.assertEqual(mvp_deployment._controlled_link(current, versions=versions), "v0.0.0.1")
        self.assertEqual(mvp_deployment._controlled_link(previous, versions=versions), previous_version)

    def test_prearm_sidepanel_is_private_digest_addressed_and_not_a_release(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage_prearm_sidepanel()
        repeated = manager.stage_prearm_sidepanel()
        self.assertEqual(repeated, staged)
        bundle = manager._prearm_target(staged)
        extension = manager.prearm_extension_directory(staged)
        manifest = json.loads((bundle / "prearm_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_kind"], "owner_prearm_sidepanel")
        self.assertEqual(manifest["artifact_sha256"], staged.artifact_sha256)
        self.assertEqual(extension, bundle / "extension")
        self.assertTrue((extension / "sidepanel.html").is_file())
        self.assertFalse((extension / "release_identity.json").exists())
        install = self.paths.ensure_private_directory("runtime/install")
        self.assertFalse((install / "current").exists() or (install / "current").is_symlink())
        plan = manager.prearm_native_host_plan(
            browser="chromium",
            home=Path(self.temporary.name) / "prearm-home",
            env={ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
            staged=staged,
        )
        self.assertEqual(plan.release_artifact_sha256, staged.artifact_sha256)
        self.assertEqual(plan.companion_source, bundle / "companion/x2n_companion")
        self.assertEqual(plan.contracts_source, bundle / "contracts/x2n_contracts")

    def test_release_prearm_sidepanel_command_emits_no_private_path(self) -> None:
        args = runtime_cli.build_parser().parse_args(["release", "stage-prearm-sidepanel"])
        with mock.patch.dict(
            os.environ,
            {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
            clear=True,
        ):
            payload = runtime_cli.run(args)
        self.assertEqual(payload["action"], "release_stage_prearm_sidepanel")
        self.assertEqual(payload["prearm_sidepanel"]["artifact_kind"], "owner_prearm_sidepanel")
        self.assertFalse(payload["prearm_sidepanel"]["paths_emitted"])
        self.assertFalse(payload["prearm_sidepanel"]["release_pointer_changed"])
        self.assertNotIn(str(self.paths.data_root), json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def test_prearm_native_host_install_is_confirmation_bound_and_source_bound(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage_prearm_sidepanel()
        with self.assertRaises(X2NRuntimeError):
            manager.install_prearm_native_host(confirmation="wrong", browser="chromium", staged=staged)

        plan = manager.prearm_native_host_plan(
            browser="chromium",
            home=Path.home(),
            env={ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
            staged=staged,
        )
        with (
            mock.patch.object(manager, "prearm_native_host_plan", return_value=plan),
            mock.patch("x2n_companion.mvp_deployment.execute_plan", return_value={"status": "INSTALLED"}) as execute,
            mock.patch(
                "x2n_companion.mvp_deployment.verify_release_installation",
                return_value={"native_host_release_bound": True},
            ) as verify,
        ):
            receipt = manager.install_prearm_native_host(
                confirmation=mvp_deployment.PREARM_HOST_CONFIRMATION,
                browser="chromium",
                staged=staged,
            )
        self.assertTrue(receipt["native_host_prearm_installed"])
        self.assertTrue(receipt["native_host_prearm_bound"])
        self.assertFalse(receipt["release_pointer_changed"])
        execute.assert_called_once_with(plan, confirmation=mvp_deployment.INSTALL_CONFIRMATION)
        verify.assert_called_once_with(plan, release_artifact_sha256=staged.artifact_sha256)

    def test_prearm_native_host_install_refuses_existing_target(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage_prearm_sidepanel()
        plan = manager.prearm_native_host_plan(
            browser="chromium",
            home=Path(self.temporary.name) / "prearm-host-home",
            env={ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
            staged=staged,
        )
        plan.runtime_path.parent.mkdir(parents=True)
        plan.runtime_path.mkdir()
        with (
            mock.patch.object(manager, "prearm_native_host_plan", return_value=plan),
            self.assertRaises(X2NRuntimeError),
        ):
            manager.install_prearm_native_host(
                confirmation=mvp_deployment.PREARM_HOST_CONFIRMATION,
                browser="chromium",
                staged=staged,
            )

    def test_prearm_native_host_install_executes_from_the_stable_bundle(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage_prearm_sidepanel()
        home = Path(self.temporary.name) / "prearm-real-host-home"
        environment = {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)}
        with (
            mock.patch.object(mvp_deployment.Path, "home", return_value=home),
            mock.patch.dict(os.environ, environment),
        ):
            receipt = manager.install_prearm_native_host(
                confirmation=mvp_deployment.PREARM_HOST_CONFIRMATION,
                browser="chromium",
                staged=staged,
            )
        self.assertTrue(receipt["native_host_prearm_installed"])
        self.assertTrue(receipt["native_host_prearm_bound"])
        bundle = manager._prearm_target(staged)
        uninstall = create_plan(
            action="uninstall",
            browser="chromium",
            home=home,
            env={},
            release_source_root=bundle,
            release_artifact_sha256=staged.artifact_sha256,
        )
        self.assertEqual(execute_plan(uninstall, confirmation=UNINSTALL_CONFIRMATION)["status"], "UNINSTALLED")

    def test_release_prearm_host_command_never_emits_private_path(self) -> None:
        args = runtime_cli.build_parser().parse_args(
            [
                "release",
                "install-prearm-sidepanel-host",
                "--browser",
                "chromium",
                "--confirm",
                mvp_deployment.PREARM_HOST_CONFIRMATION,
            ]
        )
        with (
            mock.patch.dict(
                os.environ,
                {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
                clear=True,
            ),
            mock.patch.object(
                MvpDeploymentManager,
                "install_prearm_native_host",
                return_value={
                    "native_host_prearm_bound": True,
                    "native_host_prearm_installed": True,
                    "native_host_transaction": "atomic_or_rolled_back",
                    "paths_emitted": False,
                    "release_pointer_changed": False,
                },
            ),
        ):
            payload = runtime_cli.run(args)
        self.assertEqual(payload["action"], "release_install_prearm_sidepanel_host")
        self.assertTrue(payload["native_host_prearm_installed"])
        self.assertFalse(payload["prearm_sidepanel"]["paths_emitted"])
        self.assertNotIn(str(self.paths.data_root), json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def test_release_prearm_host_command_rejects_bad_confirmation_before_staging(self) -> None:
        args = runtime_cli.build_parser().parse_args(["release", "install-prearm-sidepanel-host", "--confirm", "wrong"])
        with (
            mock.patch.dict(
                os.environ,
                {ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
                clear=True,
            ),
            mock.patch.object(MvpDeploymentManager, "stage_prearm_sidepanel") as stage_prearm,
            self.assertRaises(X2NRuntimeError),
        ):
            runtime_cli.run(args)
        stage_prearm.assert_not_called()

    def test_staged_native_host_plan_binds_private_artifact_sources(self) -> None:
        manager = MvpDeploymentManager(self.paths)
        staged = manager.stage()
        release_root = manager._staged_target(staged)
        plan = create_plan(
            action="uninstall",
            browser="chromium",
            home=Path(self.temporary.name) / "home",
            env={ROOT_ENV: str(self.paths.data_root), DOWNLOAD_ENV: str(self.paths.download_destination)},
            release_source_root=release_root,
            release_artifact_sha256=staged.artifact_sha256,
        )
        self.assertEqual(plan.release_artifact_sha256, staged.artifact_sha256)
        self.assertEqual(plan.companion_source, release_root / "companion/x2n_companion")
        self.assertEqual(plan.contracts_source, release_root / "contracts/x2n_contracts")
        self.assertTrue(plan.companion_source.is_dir())
        self.assertTrue(plan.contracts_source.is_dir())
        identity = json.loads((release_root / "extension/release_identity.json").read_text(encoding="utf-8"))
        self.assertEqual(identity, {"artifact_sha256": staged.artifact_sha256, "schema_version": "1.0"})

    def test_sidepanel_handshake_requires_deployment_and_is_bound_to_the_artifact(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        self.assertFalse(controller.record_browser_handshake(artifact_sha256="c" * 64))
        controller.state["baseline"] = {"baseline_hash": "b" * 64, "passed": True, "total_relations": 80}
        controller.state["knowledge_assets"] = {
            "markdown_content_count": 1,
            "markdown_library_sha256": "d" * 64,
            "markdown_renderer_version": "1.1.0",
            "materialized": True,
            "notion_mode": "DISABLED_OWNER_INPUT",
            "notion_platform_calls": 0,
            "private_durability_manifest_sha256": "e" * 64,
        }
        controller.state["rollback"]["rehearsed"] = True
        controller.state["owner_signoff"] = True
        controller.state["phase"] = "pre_switch_ready"
        controller._persist()
        controller.mark_deployed(artifact_sha256="c" * 64, browser="chrome")
        mismatched = dispatch_wire(_health_wire("d" * 64), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertFalse(mismatched.accepted)
        self.assertFalse(self.paths.owner_mvp_browser_handshake.exists())
        self.paths.owner_mvp_browser_handshake.symlink_to("missing-owner-mvp-browser-handshake")
        with self.assertRaises(X2NRuntimeError):
            controller.record_browser_handshake(artifact_sha256="c" * 64)
        self.assertTrue(self.paths.owner_mvp_browser_handshake.is_symlink())
        self.paths.owner_mvp_browser_handshake.unlink()
        response = dispatch_wire(_health_wire(), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertTrue(response.accepted)
        reloaded = MvpReleaseController.load(self.paths)
        assert reloaded is not None
        self.assertEqual(reloaded.verify_browser_handshake()["browser_sidepanel_handshake"], "PASS")
        reloaded.mark_online_smoke()
        self.assertEqual(self.paths._validate_marker()["real_data_state"], "stage_6_mvp_active")
        refreshed = dispatch_wire(_health_wire(), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertTrue(refreshed.accepted)

    def test_load_rejects_active_release_when_runtime_marker_update_fails(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        controller.state["baseline"] = {"baseline_hash": "b" * 64, "passed": True, "total_relations": 80}
        controller.state["knowledge_assets"] = {
            "markdown_content_count": 1,
            "markdown_library_sha256": "d" * 64,
            "markdown_renderer_version": "1.1.0",
            "materialized": True,
            "notion_mode": "DISABLED_OWNER_INPUT",
            "notion_platform_calls": 0,
            "private_durability_manifest_sha256": "e" * 64,
        }
        controller.state["rollback"]["rehearsed"] = True
        controller.state["owner_signoff"] = True
        controller.state["phase"] = "pre_switch_ready"
        controller._persist()
        controller.mark_deployed(artifact_sha256="c" * 64, browser="chrome")
        self.assertTrue(dispatch_wire(_health_wire(), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store).accepted)

        with mock.patch.object(
            RuntimePaths, "set_mvp_execution_authorized", side_effect=OSError("synthetic marker failure")
        ):
            with self.assertRaises(OSError):
                controller.mark_online_smoke()

        self.assertEqual(controller.state["phase"], "active")
        self.assertEqual(self.paths._validate_marker()["real_data_state"], "stage_6_mvp_activation_armed")
        with self.assertRaises(X2NRuntimeError) as blocked:
            MvpReleaseController.load(self.paths)
        self.assertEqual(blocked.exception.code, ErrorCode.DATA_INTEGRITY_FAILED)

    def test_materialize_knowledge_assets_rebuilds_markdown_idempotently_and_requires_durability(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        payload = _current_content_payload(0)
        payload.pop("owner_mvp_scope")
        self.assertTrue(
            dispatch_wire(_capture_wire(payload), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store).accepted
        )
        controller = MvpReleaseController.load(self.paths)
        assert controller is not None
        controller.state["baseline"] = {"baseline_hash": "b" * 64, "passed": True, "total_relations": 80}
        controller._persist()
        self.store.mark_durability_verified("d" * 64)
        durable_receipt = {
            "attestation": {"auth_mutations": 0, "client_digest_verified": True, "token_value_contact": 0},
            "durability": {"durability_state": "durability_verified", "latest_manifest_sha256": "d" * 64},
            "execution": {"platform_calls": 0, "real_notion_calls": 0, "token_value_contact": 0},
        }
        baseline = {"baseline_hash": "b" * 64, "exact_four_scope_baseline": True, "total_relations": 80}
        with mock.patch.object(controller, "verify_baseline_snapshot", return_value=baseline):
            with mock.patch(
                "x2n_companion.mvp_release.LifecycleService.export_and_verify",
                return_value=durable_receipt,
            ) as export:
                assets = controller.materialize_knowledge_assets(
                    self.store,
                    confirmation=MATERIALIZE_CONFIRMATION,
                    private_client=SimpleNamespace(),
                )
                repeated = controller.materialize_knowledge_assets(
                    self.store,
                    confirmation=MATERIALIZE_CONFIRMATION,
                    private_client=SimpleNamespace(),
                )
        self.assertEqual(export.call_count, 1)
        self.assertEqual(assets, repeated)
        self.assertEqual(assets["markdown_content_count"], 1)
        self.assertEqual(assets["notion_mode"], "DISABLED_OWNER_INPUT")
        self.assertEqual(assets["notion_platform_calls"], 0)
        self.assertEqual(assets["private_durability_manifest_sha256"], "d" * 64)

    def test_passing_release_state_cannot_replace_the_exact_eighty_item_baseline(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        controller.state["baseline"] = {"baseline_hash": "b" * 64, "passed": True, "total_relations": 79}
        with self.assertRaises(X2NRuntimeError):
            controller._persist()


if __name__ == "__main__":
    unittest.main()
