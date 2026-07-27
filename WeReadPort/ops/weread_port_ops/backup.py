from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .db import RuntimeDB, iso
from .sanitize import sanitize_public

Runner = Callable[..., subprocess.CompletedProcess[str]]
ArchiveFetcher = Callable[[str, Path], subprocess.CompletedProcess[str]]
ToolLookup = Callable[[str], str | None]

PRIVATE_DATABASE_REPOSITORY = "LinzeColin/Private-Database"


def _default_archive_fetcher(commit: str, output: Path) -> subprocess.CompletedProcess[str]:
    command = ["gh", "api", f"repos/{PRIVATE_DATABASE_REPOSITORY}/tarball/{commit}"]
    with output.open("wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, timeout=1800)
    return subprocess.CompletedProcess(command, result.returncode, "", result.stderr.decode("utf-8", "replace"))


def _private_db_commit(runner: Runner) -> tuple[str | None, str | None]:
    command = ["gh", "api", f"repos/{PRIVATE_DATABASE_REPOSITORY}/commits/main", "--jq", ".sha"]
    result = runner(command, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        return None, f"GITHUB_COMMIT_EXIT_{result.returncode}"
    commit = (result.stdout or "").strip()
    if len(commit) != 40 or any(char not in "0123456789abcdefABCDEF" for char in commit):
        return None, "GITHUB_COMMIT_INVALID"
    return commit.lower(), None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_archive(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("Private-Database archive is empty")
    member_count = 0
    with tarfile.open(path, mode="r:gz") as archive:
        # Verification only. Iterate instead of materializing the full member list so a
        # large authoritative repository cannot exhaust the backup process memory.
        for member in archive:
            member_count += 1
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RuntimeError("Private-Database archive contains an unsafe member path")
    if member_count == 0:
        raise RuntimeError("Private-Database archive has no members")
    return {
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "members": member_count,
    }


def _backup_private_database(
    settings: Settings,
    db: RuntimeDB,
    *,
    moment: datetime,
    runner: Runner,
    archive_fetcher: ArchiveFetcher,
    tool_lookup: ToolLookup,
) -> tuple[str, str, dict[str, Any]]:
    """Back up the canonical GitHub repository to encrypted R2, then mirror R2 to OCI.

    The rebuildable SQLite journal is deliberately not uploaded as the canonical
    backup object. A successful routine backup also does not enqueue a new
    Private-Database fact, preventing a self-triggering commit/backup loop.
    """
    details: dict[str, Any] = {"repository": PRIVATE_DATABASE_REPOSITORY}
    if not settings.restic_repository:
        return "not_configured", "not_configured", details
    if not tool_lookup("gh"):
        return "gh_missing", "not_attempted", details
    if not tool_lookup("restic"):
        return "restic_missing", "not_attempted", details

    commit, error = _private_db_commit(runner)
    if error or not commit:
        return error or "github_commit_unavailable", "not_attempted", details
    details["commit"] = commit
    previous = db.get_cursor("private_db_r2_commit")
    if previous == commit:
        return "unchanged", "unchanged", details

    with tempfile.TemporaryDirectory(prefix="weread-private-db-backup-", dir=settings.state_dir) as folder:
        temp = Path(folder)
        archive_path = temp / f"Private-Database-{commit}.tar.gz"
        archive_result = archive_fetcher(commit, archive_path)
        if archive_result.returncode != 0:
            details["archiveError"] = sanitize_public((archive_result.stderr or "")[-1200:])
            return f"archive_failed_exit_{archive_result.returncode}", "not_attempted", details
        archive_info = _verify_archive(archive_path)
        metadata = {
            "schemaVersion": 1,
            "repository": PRIVATE_DATABASE_REPOSITORY,
            "branch": "main",
            "commit": commit,
            "capturedAt": iso(moment),
            "archiveSha256": archive_info["sha256"],
            "archiveBytes": archive_info["bytes"],
            "archiveMembers": archive_info["members"],
        }
        metadata_path = temp / "backup-metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        restic = runner(
            [
                "restic",
                "backup",
                str(archive_path),
                str(metadata_path),
                "--tag",
                "private-database",
                "--tag",
                f"commit-{commit}",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        details["archive"] = archive_info
        details["resticResult"] = sanitize_public((restic.stdout or restic.stderr or "")[-1500:])
        if restic.returncode != 0:
            return f"restic_failed_exit_{restic.returncode}", "not_attempted", details
        db.set_cursor("private_db_r2_commit", commit, at=moment)

    oci_status = "not_configured"
    if settings.r2_remote and settings.oci_remote:
        if not tool_lookup("rclone"):
            oci_status = "rclone_missing"
        else:
            replica = runner(
                [
                    "rclone",
                    "sync",
                    settings.r2_remote,
                    settings.oci_remote,
                    "--checksum",
                    "--fast-list",
                    "--transfers",
                    "4",
                    "--checkers",
                    "8",
                ],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            oci_status = "replicated" if replica.returncode == 0 else f"failed_exit_{replica.returncode}"
            details["replicationResult"] = sanitize_public((replica.stdout or replica.stderr or "")[-1500:])
    return "stored", oci_status, details


def run_backup(
    settings: Settings,
    db: RuntimeDB,
    *,
    at: datetime | None = None,
    runner: Runner = subprocess.run,
    archive_fetcher: ArchiveFetcher = _default_archive_fetcher,
    tool_lookup: ToolLookup = shutil.which,
) -> dict[str, Any]:
    moment = at or datetime.now(timezone.utc)
    snapshot_dir = settings.state_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    snapshot = snapshot_dir / f"runtime-{stamp}.sqlite3"
    digest = db.consistent_backup(snapshot)

    r2_status, oci_status, details = _backup_private_database(
        settings,
        db,
        moment=moment,
        runner=runner,
        archive_fetcher=archive_fetcher,
        tool_lookup=tool_lookup,
    )
    details.update({"localRuntimeSnapshot": str(snapshot), "localRuntimeSha256": digest})
    backup_id = hashlib.sha256(f"{iso(moment)}\0{digest}\0{details.get('commit', '')}".encode()).hexdigest()
    with db.connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO backup_state(backup_id,created_at,snapshot_path,snapshot_sha256,sqlite_integrity,r2_status,oci_status,details_json) VALUES(?,?,?,?,?,?,?,?)",
            (
                backup_id,
                iso(moment),
                str(snapshot),
                digest,
                "ok",
                r2_status,
                oci_status,
                json.dumps(sanitize_public(details), ensure_ascii=False, sort_keys=True),
            ),
        )
    r2_ok = r2_status in {"not_configured", "unchanged", "stored"}
    oci_ok = oci_status in {"not_configured", "unchanged", "replicated"}
    overall = "complete" if r2_ok and oci_ok else "degraded"
    return {
        "status": overall,
        "backupId": backup_id,
        "localRuntimeSnapshot": str(snapshot),
        "localRuntimeSha256": digest,
        "r2Status": r2_status,
        "ociStatus": oci_status,
        "privateDatabaseCommit": details.get("commit"),
    }


def purge_local_snapshots(settings: Settings, cutoff: datetime) -> int:
    snapshot_dir = settings.state_dir / "snapshots"
    if not snapshot_dir.is_dir():
        return 0
    deleted = 0
    threshold = cutoff.timestamp()
    for path in snapshot_dir.glob("runtime-*.sqlite3"):
        try:
            if path.is_file() and path.stat().st_mtime < threshold:
                path.unlink()
                deleted += 1
        except OSError:
            continue
    return deleted


def check_snapshot(snapshot: Path) -> dict[str, Any]:
    snapshot = Path(snapshot).expanduser().resolve()
    if not snapshot.is_file():
        raise FileNotFoundError(snapshot)
    source = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    try:
        integrity = str(source.execute("PRAGMA integrity_check").fetchone()[0])
        tables = {str(row[0]) for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {
            "runtimeEvents": source.execute("SELECT count(*) FROM runtime_events").fetchone()[0] if "runtime_events" in tables else 0,
            "healthSamples": source.execute("SELECT count(*) FROM health_samples").fetchone()[0] if "health_samples" in tables else 0,
            "pendingOutbox": source.execute("SELECT count(*) FROM outbox WHERE delivered_at IS NULL").fetchone()[0] if "outbox" in tables else 0,
        }
    finally:
        source.close()
    if integrity != "ok":
        raise RuntimeError(f"Snapshot integrity failed: {integrity}")
    return {"status": "verified", "snapshot": str(snapshot), "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(), "sqliteIntegrity": integrity, "counts": counts}


def restore_local_snapshot(settings: Settings, db: RuntimeDB, snapshot: Path, *, apply: bool = False) -> dict[str, Any]:
    verified = check_snapshot(snapshot)
    if not apply:
        return {**verified, "status": "verified_not_applied"}
    source = Path(snapshot).expanduser().resolve()
    safety = settings.state_dir / "restore-safety"
    safety.mkdir(parents=True, exist_ok=True, mode=0o700)
    pre_restore = safety / "pre-restore.sqlite3"
    if db.path.exists():
        db.consistent_backup(pre_restore)
    temporary = db.path.with_suffix(".restore.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(db.path)
    if db.integrity_check() != "ok":
        raise RuntimeError("Restored database failed integrity check")
    return {**verified, "status": "restored", "preRestoreBackup": str(pre_restore)}
