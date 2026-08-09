from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db_types import ENCRYPTED_PREFIX, seal_text
from app.models import (
    AIApplicationEnhancement,
    AIProviderConfig,
    ApplicationPack,
    AuditLog,
    BackupRecord,
    CandidateProfile,
    Experience,
    Job,
    JobEvent,
    OutboxEvent,
    Resume,
)


settings = get_settings()
_OPAQUE_UPLOAD_RE = re.compile(r"^[0-9a-f]{40}\.bin$")

# Hard-coded identifiers are part of the application schema, never user input.
_SENSITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "candidate_profiles": {
        "preferred_name": "text",
        "legal_name": "text",
        "email": "text",
        "phone": "text",
        "current_location": "text",
        "linkedin_url": "text",
        "github_url": "text",
        "portfolio_url": "text",
        "current_status": "text",
        "work_authorization_country": "text",
        "work_authorization_text": "text",
        "sponsorship_now": "bool",
        "sponsorship_future": "bool",
        "target_roles_json": "text",
        "secondary_roles_json": "text",
        "roles_to_avoid_json": "text",
        "industries_to_avoid_json": "text",
        "target_locations_json": "text",
        "work_mode": "text",
        "relocation_policy": "text",
        "target_level": "text",
        "graduation_year": "text",
        "professional_experience_years": "int",
        "degree_summary": "text",
        "available_start_date": "text",
        "salary_strategy": "text",
        "salary_range": "text",
        "self_identification_strategy": "text",
    },
    "resumes": {
        "label": "text",
        "role_family": "text",
        "source_filename": "text",
        "extracted_text": "text",
        "skills_json": "text",
    },
    "experiences": {
        "title": "text",
        "organization": "text",
        "date_range": "text",
        "description": "text",
        "tags_json": "text",
        "source_ref": "text",
    },
    "jobs": {
        "reasons_json": "text",
        "risks_json": "text",
        "unknowns_json": "text",
        "matched_skills_json": "text",
        "missing_skills_json": "text",
        "next_action": "text",
        "next_action_date": "text",
        "current_stage": "text",
        "notes": "text",
    },
    "ai_provider_configs": {
        "api_key": "text",
        "last_error": "text",
    },
    "ai_application_enhancements": {
        "content_json": "text",
        "usage_json": "text",
        "error_message": "text",
    },
    "application_packs": {
        "fit_summary": "text",
        "why_role_draft": "text",
        "why_company_draft": "text",
        "work_authorization_answer": "text",
        "sponsorship_answer": "text",
        "salary_answer": "text",
    },
    "job_events": {"note": "text"},
    "audit_logs": {"details_json": "text"},
    "outbox_events": {"payload_json": "text"},
    "backup_records": {"note": "text"},
}

_MODELS_WITH_PROTECTED_FIELDS = (
    CandidateProfile,
    AIProviderConfig,
    AIApplicationEnhancement,
    Resume,
    Experience,
    Job,
    ApplicationPack,
    JobEvent,
    AuditLog,
    OutboxEvent,
    BackupRecord,
)


def _legacy_plaintext(raw: Any, kind: str) -> str:
    if kind == "bool":
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return "true"
            if normalized in {"false", "0", "no", "off"}:
                return "false"
        return "true" if bool(raw) else "false"
    if kind == "int":
        return str(int(raw))
    return str(raw)


def _verify_readable(db: Session) -> None:
    # Loading each mapped row forces every encrypted field through the current key.
    for model in _MODELS_WITH_PROTECTED_FIELDS:
        list(db.scalars(select(model)).all())


def migrate_sensitive_storage(db: Session) -> dict[str, int]:
    """Encrypt legacy plaintext fields and remove filenames from upload object paths.

    The operation is idempotent. Existing encrypted rows are verified with the
    configured key before any filesystem rename occurs.
    """

    _verify_readable(db)
    encrypted_fields = 0
    renamed_uploads = 0
    renames: list[tuple[Path, Path]] = []

    try:
        for table, columns in _SENSITIVE_COLUMNS.items():
            select_columns = ", ".join(["id", *[f'"{column}"' for column in columns]])
            rows = db.execute(text(f'SELECT {select_columns} FROM "{table}"')).mappings().all()
            for row in rows:
                updates: dict[str, str] = {}
                for column, kind in columns.items():
                    raw = row[column]
                    if raw is None or raw == "":
                        continue
                    raw_text = str(raw)
                    if raw_text.startswith(ENCRYPTED_PREFIX):
                        continue
                    updates[column] = seal_text(_legacy_plaintext(raw, kind))
                if not updates:
                    continue
                assignments = ", ".join(f'"{column}" = :{column}' for column in updates)
                db.execute(
                    text(f'UPDATE "{table}" SET {assignments} WHERE id = :row_id'),
                    {**updates, "row_id": row["id"]},
                )
                encrypted_fields += len(updates)

        uploads_root = (settings.data_dir / "uploads").resolve()
        rows = db.execute(text("SELECT id, encrypted_file_path FROM resumes")).mappings().all()
        for row in rows:
            raw_path = str(row["encrypted_file_path"] or "").strip()
            if not raw_path:
                continue
            source = Path(raw_path).expanduser().resolve()
            try:
                source.relative_to(uploads_root)
            except ValueError as exc:
                raise ValueError("简历加密对象路径不在受控上传目录内。") from exc
            if _OPAQUE_UPLOAD_RE.fullmatch(source.name):
                continue
            if not source.is_file():
                raise ValueError("需要迁移的简历加密对象不存在。")
            while True:
                target = uploads_root / f"{secrets.token_hex(20)}.bin"
                if not target.exists():
                    break
            source.rename(target)
            renames.append((source, target))
            db.execute(
                text("UPDATE resumes SET encrypted_file_path = :path WHERE id = :row_id"),
                {"path": str(target), "row_id": row["id"]},
            )
            renamed_uploads += 1

        # Verify the new representations before the database transaction is committed.
        db.flush()
        db.expire_all()
        _verify_readable(db)
        db.commit()
    except Exception:
        db.rollback()
        for source, target in reversed(renames):
            if target.exists() and not source.exists():
                target.rename(source)
        raise

    return {
        "encrypted_fields": encrypted_fields,
        "renamed_uploads": renamed_uploads,
    }


def verify_sensitive_storage(db: Session) -> dict[str, int]:
    """Confirm that every governed sensitive value and upload object is protected."""

    _verify_readable(db)
    checked_fields = 0
    protected_fields = 0
    violations: list[str] = []

    for table, columns in _SENSITIVE_COLUMNS.items():
        select_columns = ", ".join(["id", *[f'"{column}"' for column in columns]])
        rows = db.execute(text(f'SELECT {select_columns} FROM "{table}"')).mappings().all()
        for row in rows:
            for column in columns:
                raw = row[column]
                if raw is None or raw == "":
                    continue
                checked_fields += 1
                if str(raw).startswith(ENCRYPTED_PREFIX):
                    protected_fields += 1
                else:
                    violations.append(f"{table}.{column}#{row['id']}")

    uploads_root = (settings.data_dir / "uploads").resolve()
    upload_objects = 0
    if uploads_root.exists():
        for path in uploads_root.iterdir():
            if not path.is_file():
                continue
            upload_objects += 1
            if not _OPAQUE_UPLOAD_RE.fullmatch(path.name):
                violations.append(f"uploads/{path.name}")

    resume_rows = db.execute(text("SELECT id, encrypted_file_path FROM resumes")).mappings().all()
    for row in resume_rows:
        raw_path = str(row["encrypted_file_path"] or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        try:
            path.relative_to(uploads_root)
        except ValueError:
            violations.append(f"resumes.encrypted_file_path#{row['id']}")
            continue
        if not _OPAQUE_UPLOAD_RE.fullmatch(path.name) or not path.is_file():
            violations.append(f"resumes.encrypted_file_path#{row['id']}")

    if violations:
        preview = ", ".join(violations[:10])
        raise ValueError(f"敏感存储验证失败：{preview}")

    return {
        "checked_fields": checked_fields,
        "protected_fields": protected_fields,
        "upload_objects": upload_objects,
    }
