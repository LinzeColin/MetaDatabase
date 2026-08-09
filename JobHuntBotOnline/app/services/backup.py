from __future__ import annotations

import io
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import BackupRecord
from app.services.canonical import ensure_canonical_export
from app.services.security import decrypt_bytes, encrypt_bytes


settings = get_settings()
_MAX_RESTORE_BYTES = 200 * 1024 * 1024
_MAX_ENCRYPTED_BACKUP_BYTES = 220 * 1024 * 1024
_ALLOWED_ROOTS = {"jobhuntos.db", "canonical", "uploads"}


def create_backup(db: Session) -> Path:
    if not settings.database_url.startswith("sqlite:///"):
        raise RuntimeError("当前备份实现只支持 SQLite。")

    ensure_canonical_export(db)
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = settings.data_dir / "backups" / f"jobhuntos_{timestamp}.jhbbackup"

    with tempfile.TemporaryDirectory(prefix="jobhuntos-backup-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        db_copy = temp_dir / "jobhuntos.db"
        source = sqlite3.connect(db_path)
        destination = sqlite3.connect(db_copy)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            archive.add(db_copy, arcname="jobhuntos.db", recursive=False)
            if settings.canonical_export_path.exists():
                archive.add(settings.canonical_export_path, arcname="canonical/current.json", recursive=False)
            uploads = settings.data_dir / "uploads"
            if uploads.exists():
                for path in uploads.iterdir():
                    if path.is_file() and path.suffix == ".bin":
                        archive.add(path, arcname=f"uploads/{path.name}", recursive=False)
        backup_path.write_bytes(encrypt_bytes(buffer.getvalue()))
        backup_path.chmod(0o640)

    db.add(BackupRecord(filename=backup_path.name, status="created"))
    db.flush()
    prune_backups(db)
    db.commit()
    return backup_path


def restore_backup(backup_path: Path, destination_data_dir: Path) -> None:
    try:
        encrypted_size = backup_path.stat().st_size
    except OSError as exc:
        raise ValueError("无法读取备份文件。") from exc
    if encrypted_size > _MAX_ENCRYPTED_BACKUP_BYTES:
        raise ValueError("备份文件超过允许大小。")
    payload = decrypt_bytes(backup_path.read_bytes())
    destination_data_dir.mkdir(parents=True, exist_ok=True)
    destination_root = destination_data_dir.resolve()
    allowed_empty_dirs = {"uploads", "backups", "canonical"}
    for item in destination_root.iterdir():
        if item.is_dir() and item.name in allowed_empty_dirs and not any(item.iterdir()):
            continue
        raise ValueError("恢复目标目录必须为空，避免旧数据库日志或文件污染恢复结果。")
    total = 0

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts:
                raise ValueError("备份包含不安全路径。")
            if name.parts[0] not in _ALLOWED_ROOTS:
                raise ValueError("备份包含未知内容。")
            if name.parts[0] == "jobhuntos.db" and len(name.parts) != 1:
                raise ValueError("备份数据库路径无效。")
            if name.parts[0] == "canonical" and tuple(name.parts) != ("canonical", "current.json"):
                raise ValueError("备份结构化文件路径无效。")
            if name.parts[0] == "uploads" and (len(name.parts) != 2 or not name.name.endswith(".bin")):
                raise ValueError("备份上传文件路径无效。")
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("备份包含不允许的链接或设备文件。")
            total += max(0, member.size)
            if total > _MAX_RESTORE_BYTES:
                raise ValueError("备份展开后超过允许大小。")

        for member in members:
            name = PurePosixPath(member.name)
            target = destination_root.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("备份文件内容不完整。")
            target.write_bytes(source.read())
            target.chmod(0o640)


def prune_backups(db: Session | None = None) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.backup_retention_days)
    deleted: list[str] = []
    for path in (settings.data_dir / "backups").glob("*.jhbbackup"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            deleted.append(path.name)
            path.unlink(missing_ok=True)
    if db is not None:
        existing = {path.name for path in (settings.data_dir / "backups").glob("*.jhbbackup")}
        stale_ids = [
            record.id
            for record in db.scalars(select(BackupRecord))
            if record.filename in deleted or record.filename not in existing
        ]
        if stale_ids:
            db.execute(delete(BackupRecord).where(BackupRecord.id.in_(stale_ids)))
