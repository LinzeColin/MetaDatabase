"""Fail-closed CLI for the Foundation003 local Store primitives."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode

from .asr import AsrEvaluator, load_private_asr_gold_dataset
from .bilibili_selected import build_bilibili_canary_plan
from .canonical_store import CanonicalStore
from .douyin_adapter import build_douyin_canary_plan
from .kuaishou_selected import build_kuaishou_canary_plan
from .lifecycle import (
    LIFECYCLE_DELETE_CONFIRMATION,
    PRIVATE_EXPORT_CONFIRMATION,
    PRIVATE_RESTORE_CONFIRMATION,
    RUNTIME_WIPE_CONFIRMATION,
    RUNTIME_WIPE_REQUEST_CONFIRMATION,
    TIME_MACHINE_CONFIRMATION,
    DigestPinnedPrivateDbClient,
    LifecycleService,
)
from .migrations import LATEST_SCHEMA_VERSION
from .media_safety import scan_persisted_scopes
from .mvp_deployment import (
    DEPLOY_CONFIRMATION,
    ONLINE_SMOKE_CONFIRMATION,
    MvpDeploymentManager,
)
from .mvp_release import (
    ARM_CONFIRMATION,
    MATERIALIZE_CONFIRMATION,
    ROLLBACK_CONFIRMATION,
    SIGNOFF_CONFIRMATION,
    MvpReleaseController,
    OwnerMvpManifestEnrollment,
    load_owner_mvp_release_input,
    owner_input_contract_sha256,
    verify_owner_private_douyin_sidecar_bundle,
)
from .douyin_visible_sidecar import (
    PROVISION_CONFIRMATION,
    clean_room_sidecar_build,
    provision_owner_private_visible_sidecar,
)
from .native_host_installer import fresh_install_readiness
from .operations import RECOVERY_CONFIRMATION, OperationsService, build_local_doctor_probe
from .ocr_vision import (
    OcrEvaluator,
    VisionEvaluator,
    load_private_ocr_gold_dataset,
    load_private_vision_gold_dataset,
)
from .profile_session import (
    PROFILE_LAUNCH_CONFIRMATION,
    DoctorProbe,
    ProfileLauncher,
    SessionHealthStore,
    build_doctor_report,
    chrome_available,
)
from .relation_reconciliation import build_owner_mvp_80_manifest_plan
from .runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError
from .taxonomy import (
    ClassificationEvaluator,
    ConstrainedClassifier,
    TaxonomySnapshot,
    load_private_classification_gold_dataset,
)
from .taobao_selected import build_taobao_canary_plan
from .weibo_selected import build_weibo_canary_plan
from .webui import serve_local_webui
from .xiaohongshu_favorites import build_xhs_favorites_canary_plan
from .xiaohongshu_likes import build_xhs_likes_canary_plan


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TASK_ID = "TSK.x2n.foundation.003"
MEDIA_TASK_ID = "TSK.x2n.skeleton.003"
ADAPTER_TASK_ID = "TSK.x2n.adapters.001"
XHS_FAVORITES_TASK_ID = "TSK.x2n.adapters.002"
XHS_LIKES_TASK_ID = "TSK.x2n.adapters.003"
DOUYIN_TASK_ID = "TSK.x2n.adapters.004"
BILIBILI_TASK_ID = "TSK.x2n.adapters.006"
KUAISHOU_TASK_ID = "TSK.x2n.adapters.007"
WEIBO_TASK_ID = "TSK.x2n.adapters.008"
TAOBAO_TASK_ID = "TSK.x2n.adapters.009"
ASR_TASK_ID = "TSK.x2n.multimodal.002"
OCR_VISION_TASK_ID = "TSK.x2n.multimodal.003"
CLASSIFICATION_TASK_ID = "TSK.x2n.multimodal.005"
RECONCILIATION_TASK_ID = "TSK.x2n.adapters.005"
WEBUI_TASK_ID = "TSK.x2n.uxops.003"
OPERATIONS_TASK_ID = "TSK.x2n.uxops.004"
LIFECYCLE_TASK_ID = "TSK.x2n.uxops.005"
MVP_RELEASE_TASK_ID = "TSK.x2n.assurance.005"
FOUNDATION_RECEIPT_DEFAULTS = {"acceptance_scope": "FOUNDATION_003_LOCAL_STORE"}


def _emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _success(
    action: str,
    *,
    acceptance_scope: str = FOUNDATION_RECEIPT_DEFAULTS["acceptance_scope"],
    task_id: str = TASK_ID,
    **details: Any,
) -> dict[str, Any]:
    return {
        "acceptance_scope": acceptance_scope,
        "action": action,
        "private_path_emitted": False,
        "real_account_execution": "NOT_RUN",
        "status": "PASS",
        "task_id": task_id,
        **details,
    }


def _store(*, create: bool) -> CanonicalStore:
    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=create)
    return CanonicalStore(paths)


def _paths() -> RuntimePaths:
    return RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)


def _owner_mvp_preflight(paths: RuntimePaths) -> dict[str, Any]:
    """Return aggregate-only direct-MVP readiness without changing runtime state.

    This intentionally does not create an Owner input, arm a scope, invoke a
    platform, or contact the Private-MetaDatabase client. It only verifies the
    local prerequisites that can be proven without rendering private values.
    """

    if paths.owner_mvp_release_state.exists() or paths.owner_mvp_release_state.is_symlink():
        release_state = "EXISTING"
    else:
        release_state = "NOT_STARTED"
    if (
        paths.owner_mvp_release_input.exists()
        or paths.owner_mvp_release_input.is_symlink()
        or release_state == "EXISTING"
    ):
        owner_mvp_manifest_enrollment = "FROZEN_OR_ARMED"
    else:
        try:
            enrollment = OwnerMvpManifestEnrollment.load(paths, require_state=False)
            if enrollment is None:
                owner_mvp_manifest_enrollment = "NOT_STARTED"
            elif enrollment.safe_summary()["complete_scope_count"] == 4:
                owner_mvp_manifest_enrollment = "READY_TO_FREEZE"
            else:
                owner_mvp_manifest_enrollment = "COLLECTING"
        except X2NRuntimeError:
            owner_mvp_manifest_enrollment = "MISSING_OR_INVALID"
    try:
        verify_owner_private_douyin_sidecar_bundle(paths, clean_room_sidecar_build())
        douyin_sidecar_bundle = "CONFIGURED_CLEAN_ROOM_UNATTESTED"
    except X2NRuntimeError:
        douyin_sidecar_bundle = "MISSING_OR_INVALID"
    try:
        release_input = load_owner_mvp_release_input(paths)
        owner_input = "VALID"
        try:
            verify_owner_private_douyin_sidecar_bundle(paths, release_input.douyin_build)
            douyin_sidecar_bundle = "CONFIGURED_AND_MATCHED"
        except X2NRuntimeError:
            douyin_sidecar_bundle = "MISSING_OR_INVALID"
    except X2NRuntimeError:
        owner_input = "MISSING_OR_INVALID"
    try:
        MvpDeploymentManager.assert_release_source_tagged()
        source_release_tag = "READY"
    except X2NRuntimeError:
        source_release_tag = "NOT_READY"
    try:
        DigestPinnedPrivateDbClient.from_environment()
        private_durability_client = "CONFIGURED_AND_PINNED"
    except X2NRuntimeError:
        private_durability_client = "NOT_READY"
    native_host_fresh_install = fresh_install_readiness(
        browser="chrome",
        home=Path.home(),
        env=os.environ,
    )
    chrome_executable = "AVAILABLE" if chrome_available() else "NOT_READY"
    ready_to_arm = (
        owner_input == "VALID" and douyin_sidecar_bundle == "CONFIGURED_AND_MATCHED" and release_state == "NOT_STARTED"
    )
    return {
        "chrome_executable": chrome_executable,
        "douyin_sidecar_bundle": douyin_sidecar_bundle,
        "native_host_fresh_install": native_host_fresh_install,
        "notion_calls": 0,
        "owner_mvp_manifest_enrollment": owner_mvp_manifest_enrollment,
        "owner_input": owner_input,
        "platform_calls": 0,
        "private_durability_client": private_durability_client,
        "ready_to_arm": ready_to_arm,
        "release_state": release_state,
        "source_release_tag": source_release_tag,
    }


def _doctor_probe(paths: RuntimePaths) -> DoctorProbe:
    return build_local_doctor_probe(paths)


def _owner_mvp_input_template() -> dict[str, Any]:
    """Return a deliberately invalid public shape; this command never writes Runtime input.

    Owner-provided IDs and Sidecar facts must replace the literal placeholders
    before validation can pass. Valid-looking synthetic hashes would create an
    unsafe copy/paste path where an unprepared release input appears authorized.
    """

    owner_contract_sha256 = owner_input_contract_sha256(verify_source=True)
    return {
        "disabled_external_scopes": [
            {
                "flag_off": True,
                "live_support_claim": False,
                "platform_calls": 0,
                "reason_code": "BLOCKED_AUTH",
                "scope_id": scope,
            }
            for scope in (
                "bilibili_selected_collection",
                "kuaishou_selected_collection",
                "weibo_selected_collection",
                "taobao_selected_collection",
            )
        ],
        "douyin_sidecar": {
            "attestation": {
                "executable_sha256": "REPLACE_WITH_OWNER_SIDECAR_EXECUTABLE_SHA256",
                "resolved_lock_sha256": "REPLACE_WITH_OWNER_SIDECAR_LOCK_SHA256",
                "sbom_sha256": "REPLACE_WITH_OWNER_SIDECAR_SBOM_SHA256",
                "scope": "owner_private_build",
                "transitive_license_report_sha256": "REPLACE_WITH_OWNER_SIDECAR_LICENSE_SHA256",
            },
            "port": "REPLACE_WITH_OWNER_LOOPBACK_PORT",
        },
        "enabled_scopes": [
            {
                "max_items": 20,
                "scope_id": "xiaohongshu_current_content",
                "transport": "chrome_current_page_explicit",
            },
            {
                "max_items": 20,
                "scope_id": "xiaohongshu_current_content_second_batch",
                "transport": "chrome_current_page_explicit",
            },
            {
                "max_items": 20,
                "scope_id": "douyin_favorites",
                "transport": "owner_private_loopback_sidecar",
            },
            {"max_items": 20, "scope_id": "douyin_likes", "transport": "owner_private_loopback_sidecar"},
        ],
        "owner_private_manifests": [
            {
                "content_id_sha256": [
                    f"REPLACE_WITH_OWNER_CONTENT_ID_SHA256_{scope.upper()}_{index + 1:02d}" for index in range(20)
                ],
                "scope_id": scope,
            }
            for scope in (
                "xiaohongshu_current_content",
                "xiaohongshu_current_content_second_batch",
                "douyin_favorites",
                "douyin_likes",
            )
        ],
        "model_mode": "disabled",
        "owner_authorization": "owner_authorized_direct_mvp",
        "owner_input_contract_sha256": owner_contract_sha256,
        "project": "xhs-douyin-2notion",
        "release_version": "v0.0.0.1",
        "rollback_target": "previous_stable_or_disable",
        "schema_version": "1.0",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "release":
        if args.release_action == "provision-douyin-visible-sidecar":
            build = provision_owner_private_visible_sidecar(_paths(), confirmation=args.confirm)
            return _success(
                "release_provision_douyin_visible_sidecar",
                acceptance_scope="ASSURANCE_005_DOUYIN_CLEAN_ROOM_SIDECAR",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=PROVISION_CONFIRMATION,
                douyin_sidecar={
                    "artifact_count": 4,
                    "attestation": build.safe_dict(),
                    "paths_emitted": False,
                    "platform_calls": 0,
                    "runtime_kind": "x2n_clean_room_visible_dom",
                    "upstream_executed": False,
                },
            )
        if args.release_action == "input-template":
            return _success(
                "release_input_template",
                acceptance_scope="ASSURANCE_005_PRIVATE_INPUT_TEMPLATE",
                task_id=MVP_RELEASE_TASK_ID,
                template=_owner_mvp_input_template(),
            )
        if args.release_action == "stage-prearm-sidepanel":
            staged = MvpDeploymentManager(_paths()).stage_prearm_sidepanel()
            return _success(
                "release_stage_prearm_sidepanel",
                acceptance_scope="ASSURANCE_005_STABLE_PREARM_SIDEPANEL",
                task_id=MVP_RELEASE_TASK_ID,
                prearm_sidepanel=staged.safe_dict(),
                platform_calls=0,
                real_account_execution="NOT_RUN",
            )
        paths = _paths()
        if args.release_action == "preflight":
            return _success(
                "release_preflight",
                acceptance_scope="ASSURANCE_005_DIRECT_MVP_PREFLIGHT",
                task_id=MVP_RELEASE_TASK_ID,
                preflight=_owner_mvp_preflight(paths),
            )
        if args.release_action == "validate-input":
            release_input = load_owner_mvp_release_input(paths)
            return _success(
                "release_validate_input",
                acceptance_scope="ASSURANCE_005_OWNER_INPUT_GATE",
                task_id=MVP_RELEASE_TASK_ID,
                release_input=release_input.safe_summary(),
            )
        if args.release_action == "arm":
            controller = MvpReleaseController.arm(paths, CanonicalStore(paths), confirmation=args.confirm)
            return _success(
                "release_arm",
                acceptance_scope="ASSURANCE_005_BOUNDED_ACTIVATION_ARM",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=ARM_CONFIRMATION,
                release=controller.safe_status(),
            )
        controller = MvpReleaseController.load(paths)
        assert controller is not None
        store = CanonicalStore(paths)
        if args.release_action == "baseline-verify":
            baseline = controller.verify_baseline(store)
            return _success(
                "release_baseline_verify",
                acceptance_scope="ASSURANCE_005_EXACT_FOUR_SCOPE_80_ITEM_BASELINE",
                task_id=MVP_RELEASE_TASK_ID,
                baseline=baseline,
                real_account_execution=(
                    "OWNER_MVP_BASELINE_RECORDED" if baseline["exact_four_scope_baseline"] else "NOT_RUN"
                ),
            )
        if args.release_action == "materialize-knowledge-assets":
            private_client = None
            if (
                args.confirm == MATERIALIZE_CONFIRMATION
                and controller.state["knowledge_assets"]["materialized"] is not True
                and controller.state["phase"] == "activation_armed"
                and controller.state["baseline"]["passed"] is True
            ):
                private_client = DigestPinnedPrivateDbClient.from_environment()
            knowledge_assets = controller.materialize_knowledge_assets(
                store,
                confirmation=args.confirm,
                private_client=private_client,
            )
            return _success(
                "release_materialize_knowledge_assets",
                acceptance_scope="ASSURANCE_005_MARKDOWN_PRIVATE_DURABILITY",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=MATERIALIZE_CONFIRMATION,
                knowledge_assets=knowledge_assets,
                release=controller.safe_status(),
                real_account_execution="OWNER_MVP_BASELINE_RECORDED",
            )
        if args.release_action == "rollback-rehearse":
            return _success(
                "release_rollback_rehearse",
                acceptance_scope="ASSURANCE_005_ROLLBACK_REHEARSAL",
                task_id=MVP_RELEASE_TASK_ID,
                **controller.rehearse_rollback(store),
            )
        if args.release_action == "signoff":
            controller.owner_signoff(store, confirmation=args.confirm)
            return _success(
                "release_owner_signoff",
                acceptance_scope="ASSURANCE_005_OWNER_SIGNOFF",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=SIGNOFF_CONFIRMATION,
                release=controller.safe_status(),
            )
        if args.release_action == "deploy":
            manager = MvpDeploymentManager(paths)
            deployment = manager.deploy(confirmation=args.confirm, browser=args.browser)
            try:
                controller.mark_deployed(artifact_sha256=deployment["artifact_sha256"], browser=args.browser)
            except Exception as error:
                try:
                    manager.rollback_deployment(browser=args.browser)
                except Exception as cleanup_error:
                    raise X2NRuntimeError(
                        ErrorCode.POLICY_BLOCKED,
                        "MVP deployment state failed and its rollback requires owner recovery",
                    ) from cleanup_error
                if isinstance(error, X2NRuntimeError):
                    raise
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP deployment state could not be recorded") from error
            return _success(
                "release_deploy",
                acceptance_scope="ASSURANCE_005_BLUE_GREEN_DEPLOYMENT",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=DEPLOY_CONFIRMATION,
                deployment=deployment,
                release=controller.safe_status(),
            )
        if args.release_action == "online-smoke":
            manager = MvpDeploymentManager(paths)
            smoke = manager.online_smoke(confirmation=args.confirm, browser=args.browser, controller=controller)
            controller.mark_online_smoke()
            return _success(
                "release_online_smoke",
                acceptance_scope="ASSURANCE_005_DEPLOYED_RUNTIME_ONLINE_SMOKE",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=ONLINE_SMOKE_CONFIRMATION,
                online_smoke=smoke,
                release=controller.safe_status(),
            )
        if args.release_action == "rollback":
            if args.confirm != ROLLBACK_CONFIRMATION:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "MVP rollback confirmation is missing")
            controller.rollback_disable(confirmation=args.confirm)
            rollback = MvpDeploymentManager(paths).rollback_deployment(
                browser=controller.state["deployment"]["browser"]
            )
            return _success(
                "release_rollback_disable",
                acceptance_scope="ASSURANCE_005_ROLLBACK_DISABLE",
                task_id=MVP_RELEASE_TASK_ID,
                confirmation_required=ROLLBACK_CONFIRMATION,
                rollback=rollback,
                release=controller.safe_status(),
            )
        if args.release_action == "status":
            return _success(
                "release_status",
                acceptance_scope="ASSURANCE_005_RELEASE_STATUS",
                task_id=MVP_RELEASE_TASK_ID,
                release=controller.safe_status(),
            )
        if args.release_action == "verify":
            go_live = controller.verify_go_live(store)
            artifact = MvpDeploymentManager(paths).verify_current_artifact()
            MvpDeploymentManager.assert_release_source_tagged()
            return _success(
                "release_verify",
                acceptance_scope="ASSURANCE_005_DIRECT_MVP_GO_LIVE",
                task_id=MVP_RELEASE_TASK_ID,
                artifact=artifact,
                go_live=go_live,
                release=controller.safe_status(),
                real_account_execution="OWNER_MVP_RELEASE_ACTIVE",
            )
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown release action")
    if args.action == "eval":
        if args.eval_action == "asr":
            dataset = load_private_asr_gold_dataset(_paths(), args.dataset)
            report = AsrEvaluator().evaluate(dataset.cases, private_gold=True)
            return {
                "acceptance_scope": "MULTIMODAL_002_ASR_PRIVATE_EVAL",
                "action": "eval_asr",
                "cloud_uploads": 0,
                "dataset": dataset.safe_dict(),
                "evaluation": report.safe_dict(),
                "model_calls": 0,
                "private_path_emitted": False,
                "real_account_execution": "NOT_RUN",
                "status": "PASS" if report.status == "pass" else "LOW_QUALITY",
                "task_id": ASR_TASK_ID,
            }
        if args.eval_action == "ocr":
            dataset = load_private_ocr_gold_dataset(_paths(), args.dataset)
            report = OcrEvaluator().evaluate(dataset.cases, private_gold=True)
            return {
                "acceptance_scope": "MULTIMODAL_003_OCR_PRIVATE_EVAL",
                "action": "eval_ocr",
                "cloud_uploads": 0,
                "dataset": dataset.safe_dict(),
                "evaluation": report.safe_dict(),
                "model_calls": 0,
                "private_path_emitted": False,
                "real_account_execution": "NOT_RUN",
                "status": "PASS" if report.status == "pass" else "LOW_QUALITY",
                "task_id": OCR_VISION_TASK_ID,
            }
        if args.eval_action == "vision":
            dataset = load_private_vision_gold_dataset(_paths(), args.dataset)
            report = VisionEvaluator().evaluate(dataset.cases, private_gold=True)
            return {
                "acceptance_scope": "MULTIMODAL_003_VISION_PRIVATE_EVAL",
                "action": "eval_vision",
                "cloud_uploads": 0,
                "dataset": dataset.safe_dict(),
                "evaluation": report.safe_dict(),
                "model_calls": 0,
                "private_path_emitted": False,
                "real_account_execution": "NOT_RUN",
                "status": "PASS" if report.status == "pass" else "LOW_QUALITY",
                "task_id": OCR_VISION_TASK_ID,
            }
        if args.eval_action == "classify":
            paths = _paths()
            store = CanonicalStore(paths)
            snapshot = TaxonomySnapshot.from_categories(store.list_taxonomy_categories())
            dataset = load_private_classification_gold_dataset(paths, args.dataset)
            if dataset.taxonomy_snapshot_sha256 != snapshot.snapshot_sha256:
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Classification Gold Set taxonomy snapshot is stale"
                )
            classifier = ConstrainedClassifier()
            report = ClassificationEvaluator(classifier=classifier).evaluate(
                dataset.cases,
                snapshot,
                private_gold=True,
                dataset_sha256=dataset.sha256,
                expected_classifier_fingerprint=dataset.classifier_fingerprint,
            )
            return {
                "acceptance_scope": "MULTIMODAL_005_CLASSIFICATION_PRIVATE_EVAL",
                "action": "eval_classify",
                "auto_classify": "ENABLED" if report.auto_classify_allowed else "SUGGESTION_ONLY",
                "cloud_uploads": 0,
                "dataset": dataset.safe_dict(),
                "evaluation": report.safe_dict(),
                "model_calls": 0,
                "private_path_emitted": False,
                "real_account_execution": "NOT_RUN",
                "status": "PASS" if report.status == "pass" else "LOW_QUALITY",
                "task_id": CLASSIFICATION_TASK_ID,
            }
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown model evaluation action")
    if args.action == "operations":
        service = OperationsService(_store(create=False))
        if args.operations_action == "diagnostics":
            diagnostics = service.diagnostic_bundle()
            diagnostics.pop("task_id", None)
            return _success(
                "operations_diagnostics",
                acceptance_scope="UXOPS_004_OPERATIONAL_DIAGNOSTICS",
                task_id=OPERATIONS_TASK_ID,
                **diagnostics,
            )
        if args.operations_action == "doctor":
            return _success(
                "operations_doctor",
                acceptance_scope="UXOPS_004_OPERATIONAL_HEALTH",
                task_id=OPERATIONS_TASK_ID,
                doctor=service.doctor().safe_dict(),
            )
        if args.operations_action == "recovery-plan":
            plan = service.recovery_plan()
            plan.pop("task_id", None)
            return _success(
                "operations_recovery_plan",
                acceptance_scope="UXOPS_004_OPERATIONAL_RECOVERY",
                task_id=OPERATIONS_TASK_ID,
                **plan,
            )
        if args.operations_action == "startup-recovery":
            if args.confirm != RECOVERY_CONFIRMATION:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Operations recovery requires explicit confirmation")
            return _success(
                "operations_startup_recovery",
                acceptance_scope="UXOPS_004_OPERATIONAL_RECOVERY",
                task_id=OPERATIONS_TASK_ID,
                **service.startup_recovery().safe_dict(),
            )
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Operations action")
    if args.action == "lifecycle":
        service = LifecycleService(_store(create=False))
        if args.lifecycle_action == "status":
            return _success(
                "lifecycle_status",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_STATUS",
                task_id=LIFECYCLE_TASK_ID,
                **service.status(),
            )
        if args.lifecycle_action == "recovery-plan":
            return _success(
                "lifecycle_recovery_plan",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_RECOVERY",
                task_id=LIFECYCLE_TASK_ID,
                **service.recovery_plan(),
            )
        if args.lifecycle_action == "delete-preview":
            return _success(
                "lifecycle_delete_preview",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_DELETE",
                task_id=LIFECYCLE_TASK_ID,
                preview=service.delete_preview(target_kind=args.target_kind, target_key_private=args.target_key),
            )
        if args.lifecycle_action == "delete":
            return _success(
                "lifecycle_delete",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_DELETE",
                task_id=LIFECYCLE_TASK_ID,
                **service.confirm_delete(
                    target_kind=args.target_kind,
                    target_key_private=args.target_key,
                    confirmation=args.confirm,
                ),
            )
        if args.lifecycle_action == "runtime-wipe-request":
            return _success(
                "lifecycle_runtime_wipe_request",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_DELETE",
                task_id=LIFECYCLE_TASK_ID,
                **service.request_runtime_wipe(confirmation=args.confirm),
            )
        if args.lifecycle_action == "runtime-wipe-apply":
            return _success(
                "lifecycle_runtime_wipe_apply",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_DELETE",
                task_id=LIFECYCLE_TASK_ID,
                **service.apply_verified_runtime_wipe(confirmation=args.confirm),
            )
        if args.lifecycle_action == "export":
            if args.confirm != PRIVATE_EXPORT_CONFIRMATION:
                raise X2NRuntimeError(
                    ErrorCode.POLICY_BLOCKED, "Private lifecycle export requires explicit confirmation"
                )
            return _success(
                "lifecycle_export_verified",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_EXPORT",
                task_id=LIFECYCLE_TASK_ID,
                **service.export_and_verify(DigestPinnedPrivateDbClient.from_environment()),
            )
        if args.lifecycle_action == "restore":
            return _success(
                "lifecycle_restore_verified",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_RESTORE",
                task_id=LIFECYCLE_TASK_ID,
                **service.restore_latest(
                    DigestPinnedPrivateDbClient.from_environment(),
                    confirmation=args.confirm,
                ),
            )
        if args.lifecycle_action == "cleanup-expired":
            return _success(
                "lifecycle_cleanup_expired_workspaces",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_RETENTION",
                task_id=LIFECYCLE_TASK_ID,
                **service.cleanup_expired_workspaces(),
            )
        if args.lifecycle_action == "time-machine-plan":
            return _success(
                "lifecycle_time_machine_plan",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_BACKUP_EXCLUSION",
                task_id=LIFECYCLE_TASK_ID,
                **service.time_machine_plan(),
            )
        if args.lifecycle_action == "time-machine-exclusion":
            return _success(
                "lifecycle_time_machine_exclusion",
                acceptance_scope="UXOPS_005_DURABLE_LIFECYCLE_BACKUP_EXCLUSION",
                task_id=LIFECYCLE_TASK_ID,
                **service.apply_time_machine_exclusion(confirmation=args.confirm),
            )
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Lifecycle action")
    if args.action == "webui":
        if args.webui_action != "serve":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Local WebUI action")
        return serve_local_webui(_store(create=False), port=args.port)
    if args.action == "reconcile":
        if args.reconcile_action != "owner-mvp-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown reconciliation action")
        return _success(
            "reconciliation_owner_mvp_plan",
            acceptance_scope="ADAPTERS_005_OWNER_MVP_TOOLING",
            task_id=RECONCILIATION_TASK_ID,
            plan=build_owner_mvp_80_manifest_plan(args.items),
        )
    if args.action == "taobao":
        if args.taobao_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Taobao action")
        return _success(
            "taobao_canary_plan",
            acceptance_scope="ADAPTERS_009_CANARY_TOOLING",
            task_id=TAOBAO_TASK_ID,
            plan=build_taobao_canary_plan(args.max_items),
        )
    if args.action == "weibo":
        if args.weibo_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Weibo action")
        return _success(
            "weibo_canary_plan",
            acceptance_scope="ADAPTERS_008_CANARY_TOOLING",
            task_id=WEIBO_TASK_ID,
            plan=build_weibo_canary_plan(args.max_items),
        )
    if args.action == "kuaishou":
        if args.kuaishou_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Kuaishou action")
        return _success(
            "kuaishou_canary_plan",
            acceptance_scope="ADAPTERS_007_CANARY_TOOLING",
            task_id=KUAISHOU_TASK_ID,
            plan=build_kuaishou_canary_plan(args.max_items),
        )
    if args.action == "bilibili":
        if args.bilibili_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Bilibili action")
        return _success(
            "bilibili_canary_plan",
            acceptance_scope="ADAPTERS_006_CANARY_TOOLING",
            task_id=BILIBILI_TASK_ID,
            plan=build_bilibili_canary_plan(args.max_items),
        )
    if args.action == "douyin":
        if args.douyin_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Douyin action")
        return _success(
            "douyin_canary_plan",
            acceptance_scope="ADAPTERS_004_CANARY_TOOLING",
            task_id=DOUYIN_TASK_ID,
            plan=build_douyin_canary_plan(args.mode, args.max_items),
        )
    if args.action == "xhs-likes":
        if args.likes_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Xiaohongshu likes action")
        return _success(
            "xhs_likes_canary_plan",
            acceptance_scope="ADAPTERS_003_CANARY_TOOLING",
            task_id=XHS_LIKES_TASK_ID,
            plan=build_xhs_likes_canary_plan(args.max_items),
        )
    if args.action == "xhs-favorites":
        if args.favorites_action != "canary-plan":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Xiaohongshu favorites action")
        return _success(
            "xhs_favorites_canary_plan",
            acceptance_scope="ADAPTERS_002_CANARY_TOOLING",
            task_id=XHS_FAVORITES_TASK_ID,
            plan=build_xhs_favorites_canary_plan(args.max_items),
        )
    if args.action == "doctor":
        report = build_doctor_report(_doctor_probe(_paths()))
        return _success(
            "doctor",
            acceptance_scope="ADAPTERS_001_HEALTH_DOCTOR",
            task_id=ADAPTER_TASK_ID,
            doctor=report.safe_dict(),
        )
    if args.action == "profile":
        paths = _paths()
        if args.profile_action == "plan":
            details = ProfileLauncher(paths).plan(args.platform)
            action = "profile_launch_plan"
        elif args.profile_action == "launch":
            details = ProfileLauncher(paths).launch(args.platform, confirmation=args.confirm)
            action = "profile_launch"
        elif args.profile_action == "health":
            details = SessionHealthStore(paths).evaluate(args.platform).safe_dict()
            action = "profile_session_health"
        else:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Profile action")
        return _success(
            action,
            acceptance_scope="ADAPTERS_001_PROFILE_SESSION",
            task_id=ADAPTER_TASK_ID,
            **details,
        )
    if args.action == "verify":
        if args.verify_action != "cdn-zero":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown verification action")
        scopes = tuple(item.strip() for item in args.scopes.split(",") if item.strip())
        report = scan_persisted_scopes(_paths(), scopes)
        if report.total_findings:
            raise X2NRuntimeError(
                ErrorCode.CDN_PERSISTENCE_BLOCKED, "Persistent media address findings blocked verification"
            )
        return _success(
            "verify_cdn_zero",
            acceptance_scope="SKELETON_003_MEDIA_ZERO",
            task_id=MEDIA_TASK_ID,
            **report.safe_dict(),
        )
    if args.action == "init":
        return _success(
            "store_init",
            **_store(create=True).initialize(),
            latest_schema_version=LATEST_SCHEMA_VERSION,
        )
    store = _store(create=False)
    if args.action == "health":
        health = store.health()
        health_state = health.pop("status")
        return _success("store_health", **health, health_state=health_state, table_counts=store.counts())
    if args.action == "backup":
        receipt = store.backup(label=args.label)
        return _success(
            "store_backup",
            backup_id=receipt.backup_id,
            database_sha256=receipt.database_sha256,
            logical_sha256=receipt.logical_sha256,
            local_recovery_copy_only=True,
            schema_version=receipt.schema_version,
            table_counts=receipt.table_counts,
        )
    if args.action == "migrate":
        return _success("store_migrate", schema_version=store.migrate_to_latest())
    if args.action == "downgrade":
        if args.confirm != "BACKUP_AND_DOWNGRADE_CANONICAL":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Schema downgrade requires explicit confirmation")
        receipt = store.downgrade_with_backup(args.target_version)
        return _success(
            "store_downgrade",
            backup_id=receipt.backup_id,
            backup_sha256=receipt.database_sha256,
            target_schema_version=args.target_version,
        )
    if args.action == "restore":
        if args.confirm != "RESTORE_CANONICAL_FROM_VERIFIED_BACKUP":
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Store restore requires explicit confirmation")
        receipt = store.restore(args.backup_id, expected_sha256=args.sha256)
        return _success(
            "store_restore",
            backup_id=receipt.backup_id,
            logical_sha256=receipt.logical_sha256,
            schema_version=receipt.schema_version,
            table_counts=receipt.table_counts,
        )
    if args.action == "recover":
        if args.apply:
            if args.confirm != "APPLY_LOCAL_RECOVERY":
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Recovery mutation requires explicit confirmation")
            return _success("store_recovery_apply", **store.apply_recovery().safe_dict())
        return _success("store_recovery_plan", **store.recovery_plan().safe_dict())
    raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown Store action")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="x2n private Canonical Store operations")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("doctor")
    evaluation = subparsers.add_parser("eval")
    evaluation_actions = evaluation.add_subparsers(dest="eval_action", required=True)
    asr = evaluation_actions.add_parser("asr")
    asr.add_argument("--dataset", required=True)
    ocr = evaluation_actions.add_parser("ocr")
    ocr.add_argument("--dataset", required=True)
    vision = evaluation_actions.add_parser("vision")
    vision.add_argument("--dataset", required=True)
    classify = evaluation_actions.add_parser("classify")
    classify.add_argument("--dataset", required=True)
    reconcile = subparsers.add_parser("reconcile")
    reconcile_actions = reconcile.add_subparsers(dest="reconcile_action", required=True)
    owner_mvp_plan = reconcile_actions.add_parser("owner-mvp-plan")
    owner_mvp_plan.add_argument("--items", type=int, default=80)
    release = subparsers.add_parser("release")
    release_actions = release.add_subparsers(dest="release_action", required=True)
    release_sidecar = release_actions.add_parser("provision-douyin-visible-sidecar")
    release_sidecar.add_argument("--confirm", required=True, help=f"Required literal: {PROVISION_CONFIRMATION}")
    release_actions.add_parser("input-template")
    release_actions.add_parser("stage-prearm-sidepanel")
    release_actions.add_parser("preflight")
    release_actions.add_parser("validate-input")
    release_arm = release_actions.add_parser("arm")
    release_arm.add_argument("--confirm", required=True, help=f"Required literal: {ARM_CONFIRMATION}")
    release_actions.add_parser("baseline-verify")
    release_materialize = release_actions.add_parser("materialize-knowledge-assets")
    release_materialize.add_argument("--confirm", required=True, help=f"Required literal: {MATERIALIZE_CONFIRMATION}")
    release_actions.add_parser("rollback-rehearse")
    release_signoff = release_actions.add_parser("signoff")
    release_signoff.add_argument("--confirm", required=True, help=f"Required literal: {SIGNOFF_CONFIRMATION}")
    release_actions.add_parser("status")
    release_actions.add_parser("verify")
    release_deploy = release_actions.add_parser("deploy")
    release_deploy.add_argument("--browser", choices=("chrome", "chrome-for-testing", "chromium"), default="chrome")
    release_deploy.add_argument("--confirm", required=True, help=f"Required literal: {DEPLOY_CONFIRMATION}")
    release_smoke = release_actions.add_parser("online-smoke")
    release_smoke.add_argument("--browser", choices=("chrome", "chrome-for-testing", "chromium"), default="chrome")
    release_smoke.add_argument("--confirm", required=True, help=f"Required literal: {ONLINE_SMOKE_CONFIRMATION}")
    release_rollback = release_actions.add_parser("rollback")
    release_rollback.add_argument("--confirm", required=True, help=f"Required literal: {ROLLBACK_CONFIRMATION}")
    webui = subparsers.add_parser("webui")
    webui_actions = webui.add_subparsers(dest="webui_action", required=True)
    serve = webui_actions.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    operations = subparsers.add_parser("operations")
    operations_actions = operations.add_subparsers(dest="operations_action", required=True)
    operations_actions.add_parser("diagnostics")
    operations_actions.add_parser("doctor")
    operations_actions.add_parser("recovery-plan")
    startup_recovery = operations_actions.add_parser("startup-recovery")
    startup_recovery.add_argument("--confirm", required=True)
    lifecycle = subparsers.add_parser("lifecycle")
    lifecycle_actions = lifecycle.add_subparsers(dest="lifecycle_action", required=True)
    lifecycle_actions.add_parser("status")
    lifecycle_actions.add_parser("recovery-plan")
    delete_preview = lifecycle_actions.add_parser("delete-preview")
    delete_preview.add_argument("--target-kind", required=True, choices=("content", "relation", "sink", "runtime"))
    delete_preview.add_argument("--target-key", required=True)
    delete = lifecycle_actions.add_parser("delete")
    delete.add_argument("--target-kind", required=True, choices=("content", "relation", "sink"))
    delete.add_argument("--target-key", required=True)
    delete.add_argument("--confirm", required=True, help=f"Required literal: {LIFECYCLE_DELETE_CONFIRMATION}")
    wipe_request = lifecycle_actions.add_parser("runtime-wipe-request")
    wipe_request.add_argument("--confirm", required=True, help=f"Required literal: {RUNTIME_WIPE_REQUEST_CONFIRMATION}")
    wipe_apply = lifecycle_actions.add_parser("runtime-wipe-apply")
    wipe_apply.add_argument("--confirm", required=True, help=f"Required literal: {RUNTIME_WIPE_CONFIRMATION}")
    lifecycle_export = lifecycle_actions.add_parser("export")
    lifecycle_export.add_argument("--confirm", required=True, help=f"Required literal: {PRIVATE_EXPORT_CONFIRMATION}")
    lifecycle_restore = lifecycle_actions.add_parser("restore")
    lifecycle_restore.add_argument("--confirm", required=True, help=f"Required literal: {PRIVATE_RESTORE_CONFIRMATION}")
    lifecycle_actions.add_parser("cleanup-expired")
    lifecycle_actions.add_parser("time-machine-plan")
    time_machine = lifecycle_actions.add_parser("time-machine-exclusion")
    time_machine.add_argument("--confirm", required=True, help=f"Required literal: {TIME_MACHINE_CONFIRMATION}")
    bilibili = subparsers.add_parser("bilibili")
    bilibili_actions = bilibili.add_subparsers(dest="bilibili_action", required=True)
    bilibili_canary_plan = bilibili_actions.add_parser("canary-plan")
    bilibili_canary_plan.add_argument("--max-items", type=int, default=20)
    kuaishou = subparsers.add_parser("kuaishou")
    kuaishou_actions = kuaishou.add_subparsers(dest="kuaishou_action", required=True)
    kuaishou_canary_plan = kuaishou_actions.add_parser("canary-plan")
    kuaishou_canary_plan.add_argument("--max-items", type=int, default=20)
    weibo = subparsers.add_parser("weibo")
    weibo_actions = weibo.add_subparsers(dest="weibo_action", required=True)
    weibo_canary_plan = weibo_actions.add_parser("canary-plan")
    weibo_canary_plan.add_argument("--max-items", type=int, default=20)
    taobao = subparsers.add_parser("taobao")
    taobao_actions = taobao.add_subparsers(dest="taobao_action", required=True)
    taobao_canary_plan = taobao_actions.add_parser("canary-plan")
    taobao_canary_plan.add_argument("--max-items", type=int, default=20)
    douyin = subparsers.add_parser("douyin")
    douyin_actions = douyin.add_subparsers(dest="douyin_action", required=True)
    douyin_canary_plan = douyin_actions.add_parser("canary-plan")
    douyin_canary_plan.add_argument("--mode", choices=("favorites", "likes"), required=True)
    douyin_canary_plan.add_argument("--max-items", type=int, default=20)
    favorites = subparsers.add_parser("xhs-favorites")
    favorites_actions = favorites.add_subparsers(dest="favorites_action", required=True)
    canary_plan = favorites_actions.add_parser("canary-plan")
    canary_plan.add_argument("--max-items", type=int, default=20)
    likes = subparsers.add_parser("xhs-likes")
    likes_actions = likes.add_subparsers(dest="likes_action", required=True)
    likes_canary_plan = likes_actions.add_parser("canary-plan")
    likes_canary_plan.add_argument("--max-items", type=int, default=20)
    profile = subparsers.add_parser("profile")
    profile_actions = profile.add_subparsers(dest="profile_action", required=True)
    for action in ("plan", "health"):
        command = profile_actions.add_parser(action)
        command.add_argument("--platform", required=True, choices=PROFILE_PLATFORMS)
    launch = profile_actions.add_parser("launch")
    launch.add_argument("--platform", required=True, choices=PROFILE_PLATFORMS)
    launch.add_argument("--confirm", required=True, help=f"Required literal: {PROFILE_LAUNCH_CONFIRMATION}")
    subparsers.add_parser("init")
    subparsers.add_parser("health")
    backup = subparsers.add_parser("backup")
    backup.add_argument("--label", default="manual")
    subparsers.add_parser("migrate")
    downgrade = subparsers.add_parser("downgrade")
    downgrade.add_argument("--target-version", required=True, type=int)
    downgrade.add_argument("--confirm", required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--sha256", required=True)
    restore.add_argument("--confirm", required=True)
    recover = subparsers.add_parser("recover")
    recover.add_argument("--apply", action="store_true")
    recover.add_argument("--confirm")
    verify = subparsers.add_parser("verify")
    verify_actions = verify.add_subparsers(dest="verify_action", required=True)
    cdn_zero = verify_actions.add_parser("cdn-zero")
    cdn_zero.add_argument(
        "--scopes",
        required=True,
        help="Comma-separated fixed logical scopes: db,markdown,logs,notion-export,artifacts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    task_id = (
        CLASSIFICATION_TASK_ID
        if args.action == "eval" and args.eval_action == "classify"
        else OCR_VISION_TASK_ID
        if args.action == "eval" and args.eval_action in {"ocr", "vision"}
        else ASR_TASK_ID
        if args.action == "eval"
        else MEDIA_TASK_ID
        if args.action == "verify"
        else RECONCILIATION_TASK_ID
        if args.action == "reconcile"
        else MVP_RELEASE_TASK_ID
        if args.action == "release"
        else OPERATIONS_TASK_ID
        if args.action == "operations"
        else LIFECYCLE_TASK_ID
        if args.action == "lifecycle"
        else WEBUI_TASK_ID
        if args.action == "webui"
        else TAOBAO_TASK_ID
        if args.action == "taobao"
        else WEIBO_TASK_ID
        if args.action == "weibo"
        else KUAISHOU_TASK_ID
        if args.action == "kuaishou"
        else BILIBILI_TASK_ID
        if args.action == "bilibili"
        else DOUYIN_TASK_ID
        if args.action == "douyin"
        else XHS_LIKES_TASK_ID
        if args.action == "xhs-likes"
        else XHS_FAVORITES_TASK_ID
        if args.action == "xhs-favorites"
        else ADAPTER_TASK_ID
        if args.action in {"doctor", "profile"}
        else TASK_ID
    )
    try:
        payload = run(args)
    except X2NRuntimeError as error:
        _emit(
            {
                "code": error.code.value,
                "private_path_emitted": False,
                "safe_message": error.safe_message,
                "status": "FAIL_CLOSED",
                "task_id": task_id,
            },
            stream=sys.stderr,
        )
        return 2
    except Exception:
        _emit(
            {
                "code": ErrorCode.UNKNOWN_FAILURE.value,
                "private_path_emitted": False,
                "safe_message": "Store operation failed closed",
                "status": "FAIL_CLOSED",
                "task_id": task_id,
            },
            stream=sys.stderr,
        )
        return 3
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
