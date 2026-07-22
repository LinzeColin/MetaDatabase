"""Fail-closed CLI for the Foundation003 local Store primitives."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode

from .bilibili_selected import build_bilibili_canary_plan
from .canonical_store import CanonicalStore
from .douyin_adapter import build_douyin_canary_plan
from .media_safety import scan_persisted_scopes
from .profile_session import (
    PROFILE_LAUNCH_CONFIRMATION,
    DoctorProbe,
    ProfileLauncher,
    SessionHealth,
    SessionHealthStore,
    build_doctor_report,
    chrome_available,
    ffmpeg_available,
    native_host_registered,
    safe_reference_configured,
)
from .runtime import PROFILE_PLATFORMS, RuntimePaths, X2NRuntimeError
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


def _doctor_probe(paths: RuntimePaths) -> DoctorProbe:
    try:
        database_health = CanonicalStore(paths).health()
        database_state = "ok" if database_health.get("status") == "healthy" else "failed"
    except sqlite3.OperationalError:
        database_state = "busy"
    except Exception:
        database_state = "failed"

    sessions_store = SessionHealthStore(paths)
    try:
        sessions = sessions_store.evaluate_all()
    except X2NRuntimeError:
        sessions = tuple(
            SessionHealth(
                platform,
                "blocked",
                "session_checkpoint_invalid",
                ErrorCode.DATA_INTEGRITY_FAILED,
                "inspect_diagnostics_and_keep_adapter_disabled",
                False,
            )
            for platform in PROFILE_PLATFORMS
        )
    home_value = os.environ.get("HOME")
    host_registered = bool(home_value and Path(home_value).is_absolute() and native_host_registered(Path(home_value)))
    return DoctorProbe(
        extension_reachable=host_registered,
        native_host_registered=host_registered,
        companion_reachable=True,
        canonical_db_state=database_state,
        ffmpeg_available=ffmpeg_available(),
        provider_configured=safe_reference_configured(os.environ, "X2N_PROVIDER_SECRET_REF"),
        notion_authorized=safe_reference_configured(os.environ, "X2N_NOTION_SECRET_REF"),
        chrome_available=chrome_available(),
        sessions=sessions,
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
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
        return _success("store_init", **_store(create=True).initialize())
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
    bilibili = subparsers.add_parser("bilibili")
    bilibili_actions = bilibili.add_subparsers(dest="bilibili_action", required=True)
    bilibili_canary_plan = bilibili_actions.add_parser("canary-plan")
    bilibili_canary_plan.add_argument("--max-items", type=int, default=20)
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
        MEDIA_TASK_ID
        if args.action == "verify"
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
