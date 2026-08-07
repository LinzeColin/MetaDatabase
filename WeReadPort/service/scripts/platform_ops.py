#!/usr/bin/env python3
"""阅迁账户平台的确定性健康、备份、恢复、事实同步和异地冷备命令。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "v0.0.0.1.9"
BUSINESS_LINES = (
    "identity-access", "account-storage", "cross-device-sync", "provider-imports",
    "weread-wide-sync", "analytics-recommendations", "operations-recovery", "facts-backup",
)
SELF_HEAL_UNITS = ("weread-port-platform.service", "weread-port-import-worker.service")
SELF_HEAL_COOLDOWN_SECONDS = 5 * 60
SYSTEMCTL_TIMEOUT_SECONDS = 35


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


def open_db(path: Path, *, readonly: bool = False, immutable: bool = False) -> sqlite3.Connection:
    if readonly:
        suffix = "&immutable=1" if immutable else ""
        return sqlite3.connect(f"file:{path}?mode=ro{suffix}", uri=True, timeout=10)
    return sqlite3.connect(path, timeout=10)


def integrity(path: Path, *, immutable: bool = False) -> str:
    if not path.is_file():
        return "missing"
    connection = open_db(path, readonly=True, immutable=immutable)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    return str(row[0] if row else "unknown")


def safe_integrity(path: Path) -> str:
    try:
        return integrity(path)
    except (OSError, sqlite3.Error):
        return "unavailable"


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def self_heal(previous: dict, *, now: float | None = None, runner=None) -> dict:
    current = int(time.time() if now is None else now)
    recovery = previous.get("recovery") if isinstance(previous.get("recovery"), dict) else {}
    attempted_at = recovery.get("attemptedAtUnix")
    if isinstance(attempted_at, int):
        elapsed = max(0, current - attempted_at)
        if elapsed < SELF_HEAL_COOLDOWN_SECONDS:
            return {
                "status": "COOLDOWN",
                "attemptedAtUnix": attempted_at,
                "remainingSeconds": SELF_HEAL_COOLDOWN_SECONDS - elapsed,
            }
    execute = subprocess.run if runner is None else runner
    actions = []
    try:
        for command in (
            ["systemctl", "reset-failed", *SELF_HEAL_UNITS],
            ["systemctl", "restart", *SELF_HEAL_UNITS],
        ):
            completed = execute(command, timeout=SYSTEMCTL_TIMEOUT_SECONDS, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return_code = getattr(completed, "returncode", 1)
            actions.append({"action": command[1], "returnCode": return_code if isinstance(return_code, int) else 1})
    except subprocess.TimeoutExpired:
        return {"status": "FAILED", "attemptedAtUnix": current, "errorCode": "SYSTEMCTL_TIMEOUT"}
    except OSError:
        return {"status": "FAILED", "attemptedAtUnix": current, "errorCode": "SYSTEMCTL_UNAVAILABLE"}
    succeeded = all(action["returnCode"] == 0 for action in actions)
    result = {"status": "ATTEMPTED" if succeeded else "FAILED", "attemptedAtUnix": current, "actions": actions}
    if not succeeded:
        result["errorCode"] = "SYSTEMCTL_NONZERO"
    return result


def health() -> dict:
    port = int(os.environ.get("WRP_SERVICE_PORT", "8788"))
    result: dict[str, object] = {"version": VERSION, "checkedAt": utc_now(), "database": str(database_path())}
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{port}/readyz", headers={"Accept": "application/json", "User-Agent": f"WeReadPort-Health/{VERSION}"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
            result.update({"httpStatus": response.status, "serviceReachable": True, "serviceReady": response.status == 200 and (payload.get("ready") is True or payload.get("status") == "ready")})
    except urllib.error.HTTPError as exc:
        # A readiness 503 proves the Node process is responding. Restarting it
        # cannot repair an external dependency and would add avoidable churn.
        result.update({"httpStatus": exc.code, "serviceReachable": True, "serviceReady": False, "errorCode": f"READYZ_HTTP_{exc.code}"})
    except Exception as exc:  # noqa: BLE001 - only safe code is emitted
        result.update({"serviceReady": False, "errorCode": type(exc).__name__.upper()})
    result["databaseIntegrity"] = safe_integrity(database_path())
    result["ok"] = result.get("serviceReady") is True and result["databaseIntegrity"] == "ok"
    status_path = state_root() / "platform-health.json"
    previous = read_json(status_path)
    if result["ok"]:
        result["recovery"] = {"status": "NOT_NEEDED"}
    elif result["databaseIntegrity"] != "ok":
        # Never auto-restore or start from an unverified data file.
        result["recovery"] = {"status": "SKIPPED_DATABASE_INTEGRITY", "reason": "DATABASE_INTEGRITY_NOT_OK"}
    elif result.get("serviceReachable") is True:
        result["recovery"] = {"status": "SKIPPED_DEPENDENCY_DEGRADED", "reason": "READYZ_NOT_READY"}
    else:
        result["recovery"] = self_heal(previous)
    atomic_json(status_path, result)
    if not result["ok"]:
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
    source_db = open_db(source)
    try:
        destination = open_db(temp)
        try:
            source_db.backup(destination)
        finally:
            destination.close()
    finally:
        source_db.close()
    if integrity(temp, immutable=True) != "ok":
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
    snapshot_integrity = integrity(snapshot, immutable=True)
    ok = snapshot.is_file() and snapshot_integrity == "ok" and (not manifest.get("sha256") or manifest["sha256"] == sha256(snapshot))
    return {"ok": ok, "snapshot": str(snapshot), "integrity": snapshot_integrity, "sha256": sha256(snapshot) if snapshot.is_file() else None}


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
        if integrity(temp, immutable=True) != "ok":
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
        connection = open_db(source, readonly=True)
        try:
            for table, name in (("accounts", "accounts"), ("notes", "notes"), ("provider_connections", "providerConnections"), ("import_jobs", "imports"), ("outbox", "outbox")):
                counts[name] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            connection.close()
    return {
        "schemaVersion": 1,
        "system": "weread-port",
        "version": VERSION,
        "generatedAt": utc_now(),
        "counts": counts,
        "businessLines": list(BUSINESS_LINES),
        "dataBoundary": {"containsUserContent": False, "containsCredentials": False, "objectContentAuthority": "Cloudflare R2", "structuredFactsAuthority": "Private-Database"},
    }


def clone_free_private_database() -> tuple[Path, str, str, str]:
    client_raw = os.environ.get("WRP_PRIVATE_DATABASE_CLIENT_PATH", "").strip()
    expected_sha = os.environ.get("WRP_PRIVATE_DATABASE_CLIENT_SHA256", "").strip()
    area = os.environ.get("WRP_PRIVATE_DATABASE_AREA", "").strip()
    domain = os.environ.get("WRP_PRIVATE_DATABASE_DOMAIN", "").strip()
    token = os.environ.get("WRP_PRIVATE_DATABASE_GH_TOKEN", "").strip()
    if not client_raw:
        raise RuntimeError("PRIVATE_DATABASE_CLIENT_NOT_CONFIGURED")
    client = Path(client_raw).expanduser()
    if not client.is_absolute() or not client.is_file():
        raise RuntimeError("PRIVATE_DATABASE_CLIENT_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or sha256(client) != expected_sha:
        raise RuntimeError("PRIVATE_DATABASE_CLIENT_IDENTITY_INVALID")
    if area != "Private-MetaDatabase":
        raise RuntimeError("PRIVATE_DATABASE_AREA_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{3,80}", domain):
        raise RuntimeError("PRIVATE_DATABASE_DOMAIN_INVALID")
    if len(token) < 20:
        raise RuntimeError("PRIVATE_DATABASE_TOKEN_NOT_CONFIGURED")
    return client, area, domain, token


def run_clone_free_private_database(arguments: list[str], *, timeout: int = 180) -> None:
    client, _, _, token = clone_free_private_database()
    environment = os.environ.copy()
    environment["GH_TOKEN"] = token
    completed = subprocess.run([sys.executable, str(client), *arguments], capture_output=True, text=True, timeout=timeout, env=environment)
    if completed.returncode != 0:
        raise RuntimeError("PRIVATE_DATABASE_CLIENT_FAILED")


def rclone_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in ("WRP_PRIVATE_DATABASE_GH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        environment.pop(key, None)
    return environment


def private_database_directory() -> Path:
    directory = state_root() / "private-database"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def private_database_object_path(digest: str) -> str:
    return f"objects/{digest[:2]}/{digest}_runtime-facts.json"


def read_private_database_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("PRIVATE_DATABASE_STATE_INVALID") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("PRIVATE_DATABASE_STATE_INVALID")
    return loaded


def facts_sync() -> dict:
    _, area, domain, _ = clone_free_private_database()
    payload = fact_snapshot()
    # generatedAt is intentionally excluded so unchanged facts stay content-addressed and idempotent.
    stable = {key: value for key, value in payload.items() if key != "generatedAt"}
    encoded = (json.dumps(stable, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    object_path = private_database_object_path(digest)
    directory = private_database_directory()
    snapshot = directory / "runtime-facts.json"
    state_path = directory / "facts-state.json"
    previous = read_private_database_state(state_path)
    if previous.get("sha256") == digest and previous.get("objectPath") == object_path and snapshot.is_file() and sha256(snapshot) == digest:
        return {"status": "UNCHANGED", "area": area, "objectPath": object_path, "sha256": digest}
    atomic_json(snapshot, stable)
    if sha256(snapshot) != digest:
        raise RuntimeError("PRIVATE_DATABASE_FACTS_HASH_INVALID")
    run_clone_free_private_database(["ingest", area, str(snapshot), "--domain", domain, "--batch", VERSION])
    state = {
        "schemaVersion": 1,
        "system": "weread-port",
        "area": area,
        "domain": domain,
        "objectPath": object_path,
        "sha256": digest,
        "updatedAt": utc_now(),
    }
    atomic_json(state_path, state)
    return {"status": "PUSHED", "area": area, "objectPath": object_path, "sha256": digest}


def private_database_backup() -> dict:
    target_root = os.environ.get("WRP_PRIVATE_DATABASE_R2_BACKUP_TARGET", "").strip().rstrip("/")
    if not target_root or "backups/private-database" not in target_root:
        raise RuntimeError("PRIVATE_DATABASE_BACKUP_NOT_CONFIGURED")
    synced = facts_sync()
    _, area, _, _ = clone_free_private_database()
    digest = str(synced["sha256"])
    object_path = str(synced["objectPath"])
    directory = private_database_directory()
    backup_state = directory / "backup-state.json"
    previous = read_private_database_state(backup_state)
    if previous.get("sha256") == digest and previous.get("objectPath") == object_path:
        return {**previous, "status": "UNCHANGED", "remotePrefix": "backups/private-database"}
    fd, temporary_name = tempfile.mkstemp(prefix=f"private-database-{digest[:12]}-", suffix=".json", dir=directory)
    os.close(fd)
    restored = Path(temporary_name)
    restored.unlink(missing_ok=True)
    artifact_name = f"private-database-{digest}.json"
    manifest_name = f"private-database-{digest}.manifest.json"
    manifest = directory / manifest_name
    try:
        run_clone_free_private_database(["get", area, object_path, str(restored)])
        if not restored.is_file() or sha256(restored) != digest:
            raise RuntimeError("PRIVATE_DATABASE_RESTORE_VERIFY_FAILED")
        payload = {
            "schemaVersion": 1,
            "system": "weread-port",
            "createdAt": utc_now(),
            "area": area,
            "objectPath": object_path,
            "artifact": artifact_name,
            "sha256": digest,
            "size": restored.stat().st_size,
            "containsUserContent": False,
            "authority": "Private-Database clone-free REST",
            "coldBackup": "Cloudflare R2 backups/private-database",
            "restoreVerified": True,
        }
        atomic_json(manifest, payload)
        for local, remote_name in ((restored, artifact_name), (manifest, manifest_name)):
            result = subprocess.run(["rclone", "copyto", str(local), f"{target_root}/{remote_name}", "--checksum", "--immutable", "--log-level", "NOTICE"], capture_output=True, text=True, timeout=900, env=rclone_environment())
            if result.returncode != 0:
                raise RuntimeError("PRIVATE_DATABASE_R2_COPY_FAILED")
        state = {**payload, "remotePrefix": "backups/private-database"}
        atomic_json(backup_state, state)
        return {**state, "status": "COMPLETE"}
    finally:
        restored.unlink(missing_ok=True)


def r2_to_oci() -> dict:
    source = os.environ.get("WRP_R2_RCLONE_SOURCE", "").strip()
    target = os.environ.get("WRP_OCI_RCLONE_TARGET", "").strip()
    if not source or not target:
        raise RuntimeError("R2_OR_OCI_REMOTE_NOT_CONFIGURED")
    # --fast-list 是 R2 免费额度的硬要求，不是性能调优：
    # rclone 默认按前缀逐个 ListObjects，在内容寻址树上会炸成几千次调用。
    # 2026-08-07 实测：不加时这一个每日任务打 9,300 次 ListObjects = 288,300/月
    # = R2 Class A 免费额度(100万/月)的 28.8%,是全账号最大的单一 Class A 消费者,
    # 且随对象数线性增长。加上后是一次递归列举(1000 key/页),约 14 次。
    # 它只改"怎么列",不改比对与传输语义(--checksum --immutable 照旧)。
    # 规则见 Private-Database OPS/AGENT_ONBOARDING.md §9.7。**删掉它等于把账单打开。**
    command = ["rclone", "sync", source, target, "--fast-list", "--checksum", "--immutable", "--transfers", "4", "--checkers", "8", "--log-level", "NOTICE"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600, env=rclone_environment())
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
    parser.add_argument("command", choices=("health", "backup", "restore-check", "restore", "facts-snapshot", "facts-sync", "private-database-backup", "r2-to-oci"))
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
    elif args.command == "private-database-backup": result = private_database_backup()
    else: result = r2_to_oci()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "FAILED", "errorCode": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
