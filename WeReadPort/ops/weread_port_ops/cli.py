from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .backup import check_snapshot, purge_local_snapshots, restore_local_snapshot, run_backup
from .config import Settings
from .db import RuntimeDB, iso
from .monitor import (
    APP_VERSION,
    EXPECTED_SOURCE_SKILL_VERSION,
    check_official_source,
    check_site,
    combine_monitor,
    write_atomic_json,
)
from .private_db import sync_pending
from .sanitize import sanitize_public


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="weread-port-ops", description="微信读书笔记迁移自运行运维平面")
    root.add_argument("--now", help="用于即时假时钟验证的 UTC ISO 时间")
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("init", "monitor", "reconcile", "diagnose", "purge", "sync-private", "backup", "rollback-plan", "selfheal"):
        sub.add_parser(name)
    restore_check = sub.add_parser("restore-check")
    restore_check.add_argument("snapshot")
    restore = sub.add_parser("restore")
    restore.add_argument("snapshot")
    restore.add_argument("--apply", action="store_true", help="验证后实际替换可重建的运行数据库")
    release = sub.add_parser("record-release")
    release.add_argument("--commit", required=True)
    release.add_argument("--saved-version", required=True)
    release.add_argument("--production-version", required=True)
    release.add_argument("--production-origin", required=True)
    inject = sub.add_parser("inject-failure")
    inject.add_argument("kind", choices=["site-down", "version-drift", "private-db-unavailable", "r2-unavailable", "oci-unavailable", "sqlite-corrupt-copy"])
    return root


def parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def open_runtime(settings: Settings) -> RuntimeDB:
    settings.ensure_state_dirs()
    db = RuntimeDB(settings.db_path)
    db.migrate()
    return db


def _quarantine_runtime_files(settings: Settings, *, at: datetime | None = None) -> list[str]:
    stamp = (at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    quarantine = settings.state_dir / "quarantine" / stamp
    quarantine.mkdir(parents=True, exist_ok=True, mode=0o700)
    moved: list[str] = []
    for suffix in ("", "-wal", "-shm"):
        source = Path(f"{settings.db_path}{suffix}")
        if not source.exists():
            continue
        destination = quarantine / source.name
        source.replace(destination)
        moved.append(str(destination))
    return moved


def selfheal_runtime(settings: Settings, *, at: datetime | None = None) -> tuple[RuntimeDB, dict[str, Any]]:
    """Repair only the rebuildable operational journal; never touches user data."""
    settings.ensure_state_dirs()
    db = RuntimeDB(settings.db_path)
    if not settings.db_path.exists():
        db.migrate()
        return db, {"status": "ok", "actions": ["initialized_runtime_database"], "integrity": "ok"}
    try:
        db.migrate()
        integrity = db.integrity_check()
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"integrity={integrity}")
        actions: list[str] = []
        if not settings.status_path.is_file():
            site = check_site(settings, at=at)
            source = check_official_source(settings, at=at)
            payload = combine_monitor(site, source)
            db.record_health(payload)
            write_atomic_json(settings.status_path, payload)
            actions.append("recreated_status_adapter")
        return db, {"status": "ok", "actions": actions, "integrity": "ok"}
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as error:
        moved = _quarantine_runtime_files(settings, at=at)
        db = RuntimeDB(settings.db_path)
        db.migrate()
        occurred = at or datetime.now(timezone.utc)
        event_id = hashlib.sha256(f"runtime-recovered:{iso(occurred)}".encode()).hexdigest()
        payload = {"reason": "RUNTIME_DATABASE_CORRUPTION", "quarantinedFileCount": len(moved), "recoveredAt": iso(occurred)}
        db.record_event("runtime.recovered", "ok", payload, occurred_at=occurred, event_id=event_id)
        db.enqueue("runtime.recovered", payload, outbox_id=event_id)
        sync = _safe_sync(settings, db, at=at)
        return db, {
            "status": "recovered",
            "reason": "RUNTIME_DATABASE_CORRUPTION",
            "actions": ["quarantined_corrupt_runtime", "initialized_clean_runtime"],
            "quarantined": moved,
            "integrity": db.integrity_check(),
            "factSync": sync,
            "errorClass": type(error).__name__,
        }


def _safe_sync(settings: Settings, db: RuntimeDB, *, at: datetime | None = None) -> dict[str, Any]:
    try:
        return sync_pending(settings, db, at=at)
    except Exception as error:  # A facts sink must not take the product or monitor offline.
        return {"status": "failed", "reason": "PRIVATE_DB_SYNC_EXCEPTION", "errorClass": type(error).__name__}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    moment = parse_now(args.now)
    settings = Settings.from_env()

    if args.command in {"selfheal", "reconcile"}:
        db, healing = selfheal_runtime(settings, at=moment)
        if args.command == "selfheal":
            result = healing
        else:
            monitoring = monitor_once(settings, db, at=moment)
            result = {"status": monitoring.get("status", "unknown"), "selfheal": healing, "monitor": monitoring}
        print(json.dumps(sanitize_public(result), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    db = open_runtime(settings)
    if args.command == "init":
        result = {"status": "initialized", "database": str(settings.db_path), "integrity": db.integrity_check(), "version": APP_VERSION}
    elif args.command == "monitor":
        result = monitor_once(settings, db, at=moment)
    elif args.command == "diagnose":
        result = diagnose(settings, db)
    elif args.command == "purge":
        now = moment or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=settings.retention_hours)
        result = {"status": "purged", "cutoff": iso(cutoff), "deleted": {**db.purge_before(cutoff), "localSnapshots": purge_local_snapshots(settings, cutoff)}}
    elif args.command == "sync-private":
        result = sync_pending(settings, db, at=moment)
    elif args.command == "backup":
        result = run_backup(settings, db, at=moment)
    elif args.command == "restore-check":
        result = check_snapshot(Path(args.snapshot))
    elif args.command == "restore":
        result = restore_local_snapshot(settings, db, Path(args.snapshot), apply=bool(args.apply))
        if result.get("status") == "restored":
            restored_at = moment or datetime.now(timezone.utc)
            event_id = hashlib.sha256(f"runtime-restored:{result.get('sha256')}".encode()).hexdigest()
            payload = {"snapshotSha256": result.get("sha256"), "restoredAt": iso(restored_at)}
            db.enqueue("runtime.restored", payload, outbox_id=event_id)
            result["factSync"] = _safe_sync(settings, db, at=restored_at)
    elif args.command == "record-release":
        db.set_release(
            commit=args.commit,
            saved_version=args.saved_version,
            production_version=args.production_version,
            production_origin=args.production_origin,
            at=moment,
        )
        release_id = hashlib.sha256(f"release:{args.commit}:{args.production_version}".encode()).hexdigest()
        db.enqueue(
            "release.deployed",
            {"commit": args.commit, "savedVersion": args.saved_version, "productionVersion": args.production_version, "productionOrigin": args.production_origin},
            outbox_id=release_id,
        )
        result = {"status": "recorded", "release": db.release(), "factSync": _safe_sync(settings, db, at=moment)}
    elif args.command == "rollback-plan":
        result = rollback_plan(db)
    elif args.command == "inject-failure":
        result = inject_failure(args.kind, settings, db, at=moment)
    else:
        raise AssertionError(args.command)
    print(json.dumps(sanitize_public(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def monitor_once(settings: Settings, db: RuntimeDB, *, at: datetime | None = None) -> dict[str, Any]:
    site = check_site(settings, at=at)
    source = check_official_source(settings, at=at)
    result = combine_monitor(site, source)
    db.record_health(result)
    previous = db.get_cursor("last_service_status")
    current = str(result["status"])
    if previous != current:
        transition_id = hashlib.sha256(f"status:{previous}->{current}:{result['checkedAt']}".encode()).hexdigest()
        db.enqueue(
            "service.status.changed",
            {"from": previous, "to": current, "checkedAt": result["checkedAt"], "errorCode": result["productPlane"].get("errorCode")},
            outbox_id=transition_id,
        )
        db.set_cursor("last_service_status", current, at=at)
        result["factSync"] = _safe_sync(settings, db, at=at)
    write_atomic_json(settings.status_path, result)
    return result


def diagnose(settings: Settings, db: RuntimeDB) -> dict[str, Any]:
    stat = shutil.disk_usage(settings.state_dir)
    commands = {name: shutil.which(name) is not None for name in ("python3", "git", "gh", "restic", "rclone", "systemctl")}
    return {
        "status": "ok" if db.integrity_check() == "ok" else "degraded",
        "version": APP_VERSION,
        "expectedSourceSkillVersion": EXPECTED_SOURCE_SKILL_VERSION,
        "platform": {"system": platform.system(), "release": platform.release(), "python": platform.python_version()},
        "paths": {"stateDir": str(settings.state_dir), "database": str(settings.db_path), "publicStatus": str(settings.status_path)},
        "configuration": {
            "siteConfigured": bool(settings.site_url),
            "privateDatabaseClientConfigured": bool(settings.private_db_client and settings.private_db_client.is_file()),
            "r2Configured": bool(settings.restic_repository or settings.r2_remote),
            "ociConfigured": bool(settings.oci_remote),
            "retentionHours": settings.retention_hours,
        },
        "disk": {"total": stat.total, "used": stat.used, "free": stat.free},
        "commands": commands,
        "runtime": db.summary(),
    }


def rollback_plan(db: RuntimeDB) -> dict[str, Any]:
    release = db.release()
    if not release:
        return {"status": "unavailable", "reason": "NO_RELEASE_STATE"}
    if not release.get("previous_production_version"):
        return {"status": "unavailable", "reason": "NO_PREVIOUS_PRODUCTION_VERSION", "current": release}
    return {
        "status": "ready",
        "previousCommit": release.get("previous_commit"),
        "previousSavedVersion": release.get("previous_saved_version"),
        "previousProductionVersion": release.get("previous_production_version"),
        "instruction": "部署已记录的上一版 ChatGPT Sites 生产版本，然后立即运行有界生产冒烟检查。",
    }


def inject_failure(kind: str, settings: Settings, db: RuntimeDB, *, at: datetime | None = None) -> dict[str, Any]:
    if kind == "site-down":
        fake = Settings(**{**settings.__dict__, "site_url": "https://127.0.0.1.invalid"})
        return check_site(fake, at=at)
    if kind == "version-drift":
        def fetcher(url: str, timeout: float):
            del timeout
            if url.endswith("/healthz"):
                return 200, {"ok": True, "status": "ALIVE"}, 1.0
            if url.endswith("/readyz"):
                return 200, {"ok": True, "status": "READY"}, 1.0
            if url.endswith("/api/status"):
                return 200, {
                    "ok": True,
                    "status": "OPERATIONAL",
                    "runtimeMode": "production",
                    "dataBoundary": {
                        "serverSideUserNotePersistence": False,
                        "serverSideUserKeyPersistence": False,
                        "statusContainsUserContent": False,
                    },
                }, 1.0
            return 200, {"appVersion": "0.0.0.0", "sourceSkillVersion": "0.0.0"}, 1.0
        configured = settings if settings.site_url else Settings(**{**settings.__dict__, "site_url": "https://weread.invalid"})
        return check_site(configured, fetcher=fetcher, at=at)
    if kind == "private-db-unavailable":
        fake = Settings(**{**settings.__dict__, "private_db_client": Path("/nonexistent/private_db_client.py")})
        return sync_pending(fake, db, at=at)
    if kind == "r2-unavailable":
        return {"status": "injected", "component": "r2", "expectedBehavior": "备份降级；产品导出保持在线"}
    if kind == "oci-unavailable":
        return {"status": "injected", "component": "oci", "expectedBehavior": "异地副本降级；R2 与产品导出保持在线"}
    if kind == "sqlite-corrupt-copy":
        target = settings.state_dir / "failure-fixtures" / "corrupt.sqlite3"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not-a-sqlite-database")
        return {"status": "injected", "component": "sqlite", "fixture": str(target), "expectedBehavior": "恢复流程拒绝损坏快照，且不得替换在线数据库"}
    raise ValueError(kind)


if __name__ == "__main__":
    raise SystemExit(main())
