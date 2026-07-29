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
    MVP_SCOPE_IDS,
    MvpActivationExecutor,
    MvpReleaseController,
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
from x2n_companion.native_host_installer import create_plan
from x2n_companion.runtime import DOWNLOAD_ENV, ROOT_ENV, RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OWNER_MVP_STATE_SCHEMA = PROJECT_ROOT / "machine/schemas/owner_mvp_release_state.schema.json"
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
    owner_contract = hashlib.sha256(
        (PROJECT_ROOT / "docs/governance/OWNER_INPUT_CONTRACT.md").read_bytes()
    ).hexdigest()
    return {
        "schema_version": "1.0",
        "project": "xhs-douyin-2notion",
        "release_version": "v0.0.0.1",
        "owner_authorization": "owner_authorized_direct_mvp",
        "owner_input_contract_sha256": owner_contract,
        "enabled_scopes": [
            {"scope_id": "xiaohongshu_favorites", "max_items": 20, "transport": "chrome_visible_dom"},
            {"scope_id": "xiaohongshu_likes", "max_items": 20, "transport": "chrome_visible_dom"},
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
                ("xiaohongshu_favorites", "mvp-favorite"),
                ("xiaohongshu_likes", "mvp-like"),
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


def _favorite_batch() -> dict[str, object]:
    items = [
        {
            "collection_id": None,
            "collection_name_private": None,
            "content_id": f"mvp-favorite-{index:02d}",
            "content_type": "video",
            "page_url": f"https://www.xiaohongshu.com/explore/mvp-favorite-{index:02d}",
            "title": f"Owner item {index:02d}",
        }
        for index in range(20)
    ]
    return {
        "batch": {
            "automatic_scroll": False,
            "completion_signal": "bounded_limit_reached",
            "explicit_owner_action": True,
            "visible_card_count": 20,
        },
        "code": None,
        "collection": {"id": None, "name_private": None, "status": "unavailable"},
        "errors": [],
        "items": items,
        "platform": "xiaohongshu",
        "schema_version": "1.0",
        "status": "ready",
    }


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
            {"content_id": f"{prefix}-{index:02d}", "content_type": "video", "title": None}
            for index in range(20)
        ],
        "platform": "douyin",
        "schema_version": "1.0",
        "status": "ready",
    }


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class MvpReleaseTests(unittest.TestCase):
    def test_owner_mvp_state_schema_tracks_runtime_knowledge_asset_gate(self) -> None:
        schema = json.loads(OWNER_MVP_STATE_SCHEMA.read_text(encoding="utf-8"))
        rendered = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        self.assertEqual(schema["$id"], "urn:x2n:owner-mvp-release-state:1.1")
        self.assertEqual(schema["properties"]["schema_version"], {"const": "1.1"})
        self.assertIn("knowledge_assets", schema["required"])
        self.assertEqual(
            schema["properties"]["knowledge_assets"]["properties"]["notion_mode"],
            {"const": "DISABLED_OWNER_INPUT"},
        )
        self.assertEqual(
            schema["properties"]["knowledge_assets"]["properties"]["notion_platform_calls"], {"const": 0}
        )
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
        self.assertEqual(template["douyin_sidecar"]["port"], "REPLACE_WITH_OWNER_LOOPBACK_PORT")
        for manifest in template["owner_private_manifests"]:
            self.assertEqual(len(manifest["content_id_sha256"]), 20)
            self.assertTrue(
                all(value.startswith("REPLACE_WITH_OWNER_CONTENT_ID_SHA256_") for value in manifest["content_id_sha256"])
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
        enabled = [item for item in outcomes if item.scope_id in set(SyncScopeId) and item.scope_id.value.startswith(("xiaohongshu", "douyin"))]
        self.assertEqual(len(enabled), 4)
        self.assertTrue(all(item.feature_flag is CapabilityFeatureFlag.MVP_ACTIVATION_CANDIDATE for item in enabled))
        self.assertTrue(all(item.terminal is CapabilityTerminal.READY_FOR_MVP_ACTIVATION for item in enabled))
        self.assertTrue(
            all(item.feature_flag is CapabilityFeatureFlag.DISABLED for item in outcomes if item not in enabled)
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

    def test_native_host_commits_only_one_sanitized_twenty_item_xhs_action(self) -> None:
        MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        payload: dict[str, object] = {
            "auto_scroll": False,
            "bounded_batch": True,
            "change_account_state": False,
            "dispatch_version": "1.0",
            "max_items": 20,
            "platform": "xiaohongshu",
            "relation": "favorited",
            "scope_id": "xiaohongshu_favorites",
            "source_collection_id": None,
            "user_gesture": True,
            "visible_batch": _favorite_batch(),
        }
        response = dispatch_wire(_wire(payload), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertTrue(response.accepted)
        self.assertEqual(response.status.value, "completed")
        self.assertEqual(self.store.counts()["content"], 20)
        self.assertEqual(self.store.counts()["user_relation"], 20)
        controller = MvpReleaseController.load(self.paths)
        assert controller is not None
        self.assertEqual(set(controller.state["scope_jobs"]), {"xiaohongshu_favorites"})
        snapshot = self.store.owner_mvp_baseline_snapshot(
            scope_scan_ids={scope: controller.scope_scan_id(scope) for scope in MVP_SCOPE_IDS}
        )
        self.assertFalse(snapshot["exact_four_scope_baseline"])
        self.assertTrue(snapshot["scopes"]["xiaohongshu_favorites"]["scan_complete"])
        second_action = dispatch_wire(_wire(payload), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertFalse(second_action.accepted)
        self.assertEqual(self.store.counts()["content"], 20)
        self.assertEqual(self.store.counts()["user_relation"], 20)
        self.assertEqual(self.store.counts()["source_observation"], 20)
        connection = self.store._open(writable=False)
        try:
            checkpoint = connection.execute(
                "SELECT cursor_value_private FROM checkpoint WHERE checkpoint_id LIKE 'checkpoint_xhsfav_%'"
            ).fetchone()
        finally:
            connection.close()
        assert checkpoint is not None
        self.assertEqual(json.loads(str(checkpoint["cursor_value_private"]))["scope_mode"], "owner_mvp_20")

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
        malformed = _favorite_batch()
        item = malformed["items"][0]
        assert isinstance(item, dict)
        item["content_id"] = "unselected-favorite-00"
        item["page_url"] = "https://www.xiaohongshu.com/explore/unselected-favorite-00"
        payload: dict[str, object] = {
            "auto_scroll": False,
            "bounded_batch": True,
            "change_account_state": False,
            "dispatch_version": "1.0",
            "max_items": 20,
            "platform": "xiaohongshu",
            "relation": "favorited",
            "scope_id": "xiaohongshu_favorites",
            "source_collection_id": None,
            "user_gesture": True,
            "visible_batch": malformed,
        }
        response = dispatch_wire(_wire(payload), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
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
                DouyinItem(content_id=f"unselected-douyin-{index:02d}", content_type="video", title=None, collection=None)
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
        reloaded.state["deployment"]["online_smoke"] = True
        reloaded.state["phase"] = "active"
        reloaded._persist()
        refreshed = dispatch_wire(_health_wire(), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store)
        self.assertTrue(refreshed.accepted)

    def test_materialize_knowledge_assets_rebuilds_markdown_idempotently_and_requires_durability(self) -> None:
        controller = MvpReleaseController.arm(self.paths, self.store, confirmation=ARM_CONFIRMATION)
        payload: dict[str, object] = {
            "auto_scroll": False,
            "bounded_batch": True,
            "change_account_state": False,
            "dispatch_version": "1.0",
            "max_items": 20,
            "platform": "xiaohongshu",
            "relation": "favorited",
            "scope_id": "xiaohongshu_favorites",
            "source_collection_id": None,
            "user_gesture": True,
            "visible_batch": _favorite_batch(),
        }
        self.assertTrue(dispatch_wire(_wire(payload), origin=DEVELOPMENT_EXTENSION_ORIGIN, store=self.store).accepted)
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
        self.assertEqual(assets["markdown_content_count"], 20)
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
