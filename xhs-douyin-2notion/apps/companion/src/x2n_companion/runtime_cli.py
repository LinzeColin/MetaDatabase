"""Fail-closed CLI for the Foundation003 local Store primitives."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode

from .canonical_store import CanonicalStore
from .media_safety import scan_persisted_scopes
from .runtime import RuntimePaths, X2NRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TASK_ID = "TSK.x2n.foundation.003"
MEDIA_TASK_ID = "TSK.x2n.skeleton.003"
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


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "verify":
        if args.verify_action != "cdn-zero":
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Unknown verification action")
        scopes = tuple(item.strip() for item in args.scopes.split(",") if item.strip())
        report = scan_persisted_scopes(_paths(), scopes)
        if report.total_findings:
            raise X2NRuntimeError(ErrorCode.CDN_PERSISTENCE_BLOCKED, "Persistent media address findings blocked verification")
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
    task_id = MEDIA_TASK_ID if args.action == "verify" else TASK_ID
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
