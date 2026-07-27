#!/usr/bin/env python3
"""阅迁账户平台的确定性健康、备份、恢复、事实同步和异地冷备命令。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "v0.0.0.1.8"
BUSINESS_LINES = (
    "identity-access", "account-storage", "cross-device-sync", "provider-imports",
    "weread-wide-sync", "analytics-recommendations", "operations-recovery", "facts-backup",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def database_path() -> Path:
    return Path(os.environ.get("WRP_DATABASE_PATH", "/var/lib/weread-port/platform.sqlite3")).expanduser().resolve()


def state_root() -> Path:
    root = database_path().parent
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_db(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    return sqlite3.connect(path, timeout=10)


def integrity(path: Path) -> str:
    if not path.is_file():
        return "missing"
    with open_db(path, readonly=True) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "unknown")


def health() -> dict:
    port = int(os.environ.get("WRP_SERVICE_PORT", "8788"))
    result: dict[str, object] = {"version": VERSION, "checkedAt": utc_now(), "database": str(database_path())}
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{port}/readyz", headers={"Accept": "application/json", "User-Agent": f"WeReadPort-Health/{VERSION}"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
            result.update({"httpStatus": response.status, "serviceReady": response.status == 200 and payload.get("status") == "ready"})
    except Exception as exc:  # noqa: BLE001 - only safe code is emitted
        result.update({"serviceReady": False, "errorCode": type(exc).__name__.upper()})
    result["databaseIntegrity"] = integrity(database_path())
    result["ok"] = result.get("serviceReady") is True and result["databaseIntegrity"] == "ok"
    status_path = state_root() / "platform-health.json"
    atomic_json(status_path, result)
    if not result["ok"]:
        # One bounded self-heal attempt. The timer retries later; no loop or agent is required.
        subprocess.run(["systemctl", "try-restart", "weread-port-platform.service", "weread-port-import-worker.service"], timeout=20, check=False)
        raise RuntimeError("PLATFORM_NOT_READY")
    return result


def backup() -> dict:
    source = database_path()
    if not source.is_file():
        raise FileNotFoundError(source)
    snapshot_dir = state_root() / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = snapshot_dir / f"platform-{stamp}.sqlite3"
    temp = snapshot_dir / f".{target.name}.tmp"
    with open_db(source) as source_db, open_db(temp) as destination:
        source_db.backup(destination)
    if integrity(temp) != "ok":
        temp.unlink(missing_ok=True)
        raise RuntimeError("SNAPSHOT_INTEGRITY_FAILED")
    os.replace(temp, target)
    target.chmod(0o600)
    manifest = {"version": VERSION, "createdAt": utc_now(), "source": str(source), "snapshot": target.name, "size": target.stat().st_size, "sha256": sha256(target), "integrity": "ok"}
    atomic_json(target.with_suffix(".json"), manifest)
    purge_snapshots(snapshot_dir, keep=14)
    return manifest


def verify_snapshot(snapshot: Path) -> dict:
    snapshot = snapshot.expanduser().resolve()
    manifest_path = snapshot.with_suffix(".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    ok = snapshot.is_file() and integrity(snapshot) == "ok" and (not manifest.get("sha256") or manifest["sha256"] == sha256(snapshot))
    return {"ok": ok, "snapshot": str(snapshot), "integrity": integrity(snapshot), "sha256": sha256(snapshot) if snapshot.is_file() else None}


def restore(snapshot: Path, *, apply: bool) -> dict:
    check = verify_snapshot(snapshot)
    if not check["ok"]:
        raise RuntimeError("SNAPSHOT_INVALID")
    if not apply:
        return {**check, "applied": False}
    destination = database_path()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    subprocess.run(["systemctl", "stop", "weread-port-import-worker.service", "weread-port-platform.service"], check=True, timeout=30)
    previous = destination.with_suffix(f".pre-restore-{int(time.time())}.sqlite3")
    try:
        if destination.exists():
            shutil.copy2(destination, previous)
        temp = destination.with_suffix(".restore.tmp")
        shutil.copy2(Path(snapshot), temp)
        if integrity(temp) != "ok":
            raise RuntimeError("RESTORE_INTEGRITY_FAILED")
        os.replace(temp, destination)
        destination.chmod(0o600)
        subprocess.run(["systemctl", "start", "weread-port-platform.service", "weread-port-import-worker.service"], check=True, timeout=30)
        return {**check, "applied": True, "previous": str(previous) if previous.exists() else None}
    except Exception:
        if previous.exists():
            os.replace(previous, destination)
        subprocess.run(["systemctl", "start", "weread-port-platform.service", "weread-port-import-worker.service"], check=False, timeout=30)
        raise


def fact_snapshot() -> dict:
    source = database_path()
    counts: dict[str, int] = {}
    if source.is_file() and integrity(source) == "ok":
        with open_db(source, readonly=True) as connection:
            for table, name in (("accounts", "accounts"), ("notes", "notes"), ("provider_connections", "providerConnections"), ("import_jobs", "imports"), ("outbox", "outbox")):
                counts[name] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return {
        "schemaVersion": 1,
        "system": "weread-port",
        "version": VERSION,
        "generatedAt": utc_now(),
        "counts": counts,
        "businessLines": list(BUSINESS_LINES),
        "dataBoundary": {"containsUserContent": False, "containsCredentials": False, "objectContentAuthority": "Cloudflare R2", "structuredFactsAuthority": "Private-Database"},
    }


def facts_sync() -> dict:
    worktree_raw = os.environ.get("WRP_PRIVATE_DATABASE_WORKTREE", "").strip()
    if not worktree_raw:
        raise RuntimeError("WRP_PRIVATE_DATABASE_WORKTREE_NOT_CONFIGURED")
    worktree = Path(worktree_raw).expanduser().resolve()
    if not (worktree / ".git").exists() and not (worktree / "HEAD").exists():
        raise RuntimeError("PRIVATE_DATABASE_WORKTREE_INVALID")
    relative = os.environ.get("WRP_PRIVATE_DATABASE_FACTS_PATH", "systems/weread-port").strip("/")
    if not relative or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise RuntimeError("PRIVATE_DATABASE_FACTS_PATH_INVALID")
    payload = fact_snapshot()
    # generatedAt is intentionally excluded from change detection to prevent empty daily commits.
    stable = {key: value for key, value in payload.items() if key != "generatedAt"}
    destination = worktree / relative / "runtime-facts.json"
    existing = None
    if destination.is_file():
        existing_payload = json.loads(destination.read_text(encoding="utf-8"))
        existing = {key: value for key, value in existing_payload.items() if key != "generatedAt"}
    if existing == stable:
        return {"status": "UNCHANGED", "path": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(destination, payload)
    run_git(worktree, ["add", "--", str(destination.relative_to(worktree))])
    run_git(worktree, ["commit", "-m", f"weread-port: sync structured facts {VERSION}"])
    branch = os.environ.get("WRP_PRIVATE_DATABASE_BRANCH", "main")
    run_git(worktree, ["push", "origin", f"HEAD:{branch}"])
    return {"status": "PUSHED", "path": str(destination)}


def r2_to_oci() -> dict:
    source = os.environ.get("WRP_R2_RCLONE_SOURCE", "").strip()
    target = os.environ.get("WRP_OCI_RCLONE_TARGET", "").strip()
    if not source or not target:
        raise RuntimeError("R2_OR_OCI_REMOTE_NOT_CONFIGURED")
    command = ["rclone", "sync", source, target, "--checksum", "--immutable", "--transfers", "4", "--checkers", "8", "--log-level", "NOTICE"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    if completed.returncode != 0:
        raise RuntimeError("R2_OCI_SYNC_FAILED")
    return {"status": "COMPLETE", "checkedAt": utc_now()}


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def purge_snapshots(directory: Path, keep: int) -> None:
    snapshots = sorted(directory.glob("platform-*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
    for snapshot in snapshots[keep:]:
        snapshot.unlink(missing_ok=True)
        snapshot.with_suffix(".json").unlink(missing_ok=True)


def run_git(worktree: Path, args: list[str]) -> None:
    completed = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True, timeout=180)
    if completed.returncode != 0:
        raise RuntimeError(f"GIT_{args[0].upper()}_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("health", "backup", "restore-check", "restore", "facts-snapshot", "facts-sync", "r2-to-oci"))
    parser.add_argument("snapshot", nargs="?", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.command == "health": result = health()
    elif args.command == "backup": result = backup()
    elif args.command == "restore-check":
        if not args.snapshot: parser.error("restore-check 需要 snapshot")
        result = verify_snapshot(args.snapshot)
    elif args.command == "restore":
        if not args.snapshot: parser.error("restore 需要 snapshot")
        result = restore(args.snapshot, apply=args.apply)
    elif args.command == "facts-snapshot": result = fact_snapshot()
    elif args.command == "facts-sync": result = facts_sync()
    else: result = r2_to_oci()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "FAILED", "errorCode": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
