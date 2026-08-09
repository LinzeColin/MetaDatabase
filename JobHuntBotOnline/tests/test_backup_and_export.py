from __future__ import annotations

import io
import json
import stat
import tarfile
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import CandidateProfile, User
from app.services.backup import create_backup, restore_backup
from app.services.security import encrypt_bytes
from app.services.canonical import ensure_canonical_export, export_canonical, owner_readable_export
from app.db_types import unseal_text


def test_canonical_export_protects_private_fields_and_omits_resume_body(ready_workspace):
    with SessionLocal() as db:
        path = export_canonical(db)
    payload = path.read_text(encoding="utf-8")
    assert "Correct-Horse-Battery-2026" not in payload
    assert '"extracted_text"' not in payload
    assert '"Linze"' not in payload
    assert "sample_resume.txt" not in payload
    parsed = json.loads(payload)
    assert parsed["schema_version"] == "3"
    assert parsed["privacy"]["protected_field_format"] == "enc:v1"
    preferred_name = parsed["candidate_profile"]["preferred_name"]
    source_filename = parsed["resumes"][0]["source_filename"]
    assert preferred_name.startswith("enc:v1:")
    assert source_filename.startswith("enc:v1:")
    assert unseal_text(preferred_name) == "Linze"
    assert unseal_text(source_filename) == "sample_resume.txt"


def test_clean_canonical_export_is_reused_without_reencrypting(ready_workspace):
    with SessionLocal() as db:
        first = ensure_canonical_export(db)
        first_bytes = first.read_bytes()
        second = ensure_canonical_export(db)
        second_bytes = second.read_bytes()
    assert first == second
    assert first_bytes == second_bytes


def test_owner_readable_export_is_clear_only_in_memory(ready_workspace):
    with SessionLocal() as db:
        payload = owner_readable_export(db)
    assert payload["privacy"]["protected_field_format"] == "owner_readable_download"
    assert payload["candidate_profile"]["preferred_name"] == "Linze"
    assert payload["candidate_profile"]["target_roles"] == ["Data Analyst", "Financial Analyst"]
    assert payload["resumes"][0]["source_filename"] == "sample_resume.txt"


def test_encrypted_backup_restores_database_and_uploads(ready_workspace, tmp_path):
    settings = get_settings()
    with SessionLocal() as db:
        backup = create_backup(db)
    raw = backup.read_bytes()
    assert b"SQLite format 3" not in raw
    assert stat.S_IMODE(backup.stat().st_mode) == 0o640
    encrypted_upload = next((get_settings().data_dir / "uploads").glob("*.bin"))
    assert stat.S_IMODE(encrypted_upload.stat().st_mode) == 0o640
    restored = tmp_path / "restored"
    restore_backup(backup, restored)
    assert (restored / "jobhuntos.db").is_file()
    assert (restored / "canonical" / "current.json").is_file()
    assert list((restored / "uploads").glob("*.bin"))


def test_restore_requires_an_empty_destination(ready_workspace, tmp_path):
    with SessionLocal() as db:
        backup = create_backup(db)
    destination = tmp_path / "nonempty"
    destination.mkdir()
    (destination / "old-wal").write_text("stale", encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="必须为空"):
        restore_backup(backup, destination)


def test_restore_rejects_path_traversal_and_unexpected_members(ready_workspace, tmp_path):
    def encrypted_archive(name: str, payload: bytes = b"bad") -> Path:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        target = tmp_path / (name.replace("/", "_").replace("..", "dot") + ".jhbbackup")
        target.write_bytes(encrypt_bytes(buffer.getvalue()))
        return target

    import pytest

    with pytest.raises(ValueError, match="不安全路径"):
        restore_backup(encrypted_archive("../outside.txt"), tmp_path / "restore-traversal")
    with pytest.raises(ValueError, match="结构化文件路径无效"):
        restore_backup(encrypted_archive("canonical/unexpected.json"), tmp_path / "restore-unknown")
    with pytest.raises(ValueError, match="上传文件路径无效"):
        restore_backup(encrypted_archive("uploads/plain-resume.pdf"), tmp_path / "restore-upload")
