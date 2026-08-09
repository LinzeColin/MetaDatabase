from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db_types import ENCRYPTED_PREFIX, seal_text, unseal_text
from app.models import (
    AIApplicationEnhancement,
    ApplicationPack,
    CandidateProfile,
    Experience,
    Job,
    JobEvent,
    OutboxEvent,
    Resume,
    SystemState,
    User,
    json_dumps,
    json_loads,
    utcnow,
)


settings = get_settings()
SCHEMA_VERSION = "3"


def mark_canonical_dirty(db: Session, topic: str, payload: dict[str, Any] | None = None) -> None:
    db.add(
        OutboxEvent(
            topic=topic,
            payload_json=json_dumps(payload or {}),
        )
    )
    state = db.get(SystemState, "canonical_dirty")
    if state:
        state.value = "true"
    else:
        db.add(SystemState(key="canonical_dirty", value="true"))


def export_canonical(db: Session, output_path: Path | None = None) -> Path:
    target = output_path or settings.canonical_export_path
    target.parent.mkdir(parents=True, exist_ok=True)

    owner = db.scalar(select(User).where(User.email == settings.admin_email))
    if owner is None:
        owner = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))
    owner_id = owner.id if owner else None

    profile = (
        db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == owner_id))
        if owner_id is not None
        else None
    )
    resumes = (
        list(db.scalars(select(Resume).where(Resume.user_id == owner_id).order_by(Resume.id)))
        if owner_id is not None
        else []
    )
    experiences = (
        list(db.scalars(select(Experience).where(Experience.user_id == owner_id).order_by(Experience.id)))
        if owner_id is not None
        else []
    )
    jobs = (
        list(db.scalars(select(Job).where(Job.user_id == owner_id).order_by(Job.id)))
        if owner_id is not None
        else []
    )
    packs = (
        list(db.scalars(select(ApplicationPack).where(ApplicationPack.user_id == owner_id).order_by(ApplicationPack.id)))
        if owner_id is not None
        else []
    )
    events = (
        list(db.scalars(select(JobEvent).where(JobEvent.user_id == owner_id).order_by(JobEvent.id)))
        if owner_id is not None
        else []
    )
    ai_enhancements = (
        list(
            db.scalars(
                select(AIApplicationEnhancement)
                .where(AIApplicationEnhancement.user_id == owner_id)
                .order_by(AIApplicationEnhancement.id)
            )
        )
        if owner_id is not None
        else []
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "product": "JobHuntBot Online",
        "privacy": {
            "protected_field_format": "enc:v1",
            "description": "候选人私密字段使用部署数据密钥加密；岗位公开信息保持可审计。",
        },
        "candidate_profile": _profile_dict(profile) if profile else None,
        "resumes": [_resume_dict(item) for item in resumes],
        "experiences": [_experience_dict(item) for item in experiences],
        "jobs": [_job_dict(item) for item in jobs],
        "application_packs": [_pack_dict(item) for item in packs],
        "ai_enhancements": [_ai_enhancement_dict(item) for item in ai_enhancements],
        "job_events": [_event_dict(item) for item in events],
        "recovery_notes": {
            "encrypted_originals": "Restore encrypted upload objects from R2 or a .jhbbackup file.",
            "runtime_database": "Use a .jhbbackup file for complete authentication and runtime recovery; this JSON is a structured audit/export snapshot.",
        },
    }

    temp = target.with_name(f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    target.chmod(0o640)

    for event in db.scalars(select(OutboxEvent).where(OutboxEvent.processed_at.is_(None))):
        event.processed_at = utcnow()
        event.last_error = ""
    state = db.get(SystemState, "canonical_dirty")
    if state:
        state.value = "false"
    exported = db.get(SystemState, "canonical_last_exported_at")
    now_text = datetime.now(timezone.utc).isoformat()
    if exported:
        exported.value = now_text
    else:
        db.add(SystemState(key="canonical_last_exported_at", value=now_text))
    db.commit()
    _write_local_status("exported", "结构化事实已导出，等待或已完成 Private-Database 同步。")
    return target


def canonical_is_dirty(db: Session) -> bool:
    state = db.get(SystemState, "canonical_dirty")
    if state and state.value == "true":
        return True
    return db.scalar(select(OutboxEvent.id).where(OutboxEvent.processed_at.is_(None)).limit(1)) is not None


def ensure_canonical_export(db: Session) -> Path:
    """Return a current protected canonical file without rewriting clean data."""
    if settings.canonical_export_path.exists() and not canonical_is_dirty(db):
        return settings.canonical_export_path
    return export_canonical(db)


def owner_readable_export(db: Session) -> dict[str, Any]:
    """Build an authenticated Owner-only readable copy from the protected export."""
    path = ensure_canonical_export(db)
    payload = json.loads(path.read_text(encoding="utf-8"))

    def reveal(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: reveal(item) for key, item in value.items()}
        if isinstance(value, list):
            return [reveal(item) for item in value]
        if isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX):
            plain = unseal_text(value)
            if plain in {"true", "false", "null"} or plain.startswith("[") or plain.startswith("{"):
                try:
                    return json.loads(plain)
                except json.JSONDecodeError:
                    pass
            return plain
        return value

    readable = reveal(payload)
    readable["privacy"] = {
        "protected_field_format": "owner_readable_download",
        "description": "此副本由已登录 Owner 主动下载，包含可读私人资料；请按敏感文件保管。",
    }
    return readable


def read_sync_status() -> dict[str, Any]:
    if not settings.sync_status_path.exists():
        return {
            "state": "not_configured",
            "message": "Private-Database 同步尚未由部署环境配置；应用本身仍可使用。",
            "updated_at": "",
        }
    try:
        data = json.loads(settings.sync_status_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "state": "unknown",
        "message": "无法读取长期同步状态。",
        "updated_at": "",
    }


def _write_local_status(state: str, message: str) -> None:
    current = read_sync_status()
    channels = current.get("channels") if isinstance(current.get("channels"), dict) else {}
    channels = dict(channels)
    now = datetime.now(timezone.utc).isoformat()

    # A fresh canonical export makes the structured external copy stale until the host sync runs.
    if state == "exported":
        structured = channels.get("structured") if isinstance(channels.get("structured"), dict) else {}
        if structured:
            channels["structured"] = {
                **structured,
                "state": "pending_sync",
                "message": "结构化事实已更新，等待 Private-Database 同步",
                "updated_at": now,
            }
        state = "pending_sync"

    channel_messages = [
        item.get("message", "")
        for item in channels.values()
        if isinstance(item, dict) and item.get("message")
    ]
    payload = {
        "state": state,
        "message": "；".join(channel_messages) if channel_messages else message,
        "updated_at": now,
        "channels": channels,
    }
    settings.sync_status_path.parent.mkdir(parents=True, exist_ok=True)
    temp = settings.sync_status_path.with_name(
        f".{settings.sync_status_path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.chmod(0o660)
        os.replace(temp, settings.sync_status_path)
    finally:
        temp.unlink(missing_ok=True)
    settings.sync_status_path.chmod(0o660)


def _protected(value: Any) -> str | None:
    """Protect one private export value while preserving explicit unknowns."""
    if value is None:
        return None
    if value == "" or value == [] or value == {}:
        return ""
    if isinstance(value, str):
        plain = value
    else:
        plain = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return seal_text(plain)


def _profile_dict(profile: CandidateProfile) -> dict[str, Any]:
    return {
        "preferred_name": _protected(profile.preferred_name),
        "legal_name": _protected(profile.legal_name),
        "email": _protected(profile.email),
        "phone": _protected(profile.phone),
        "current_location": _protected(profile.current_location),
        "linkedin_url": _protected(profile.linkedin_url),
        "github_url": _protected(profile.github_url),
        "portfolio_url": _protected(profile.portfolio_url),
        "current_status": _protected(profile.current_status),
        "work_authorization_country": _protected(profile.work_authorization_country),
        "work_authorization_text": _protected(profile.work_authorization_text),
        "sponsorship_now": _protected(profile.sponsorship_now),
        "sponsorship_future": _protected(profile.sponsorship_future),
        "target_roles": _protected(profile.target_roles),
        "secondary_roles": _protected(profile.secondary_roles),
        "roles_to_avoid": _protected(profile.roles_to_avoid),
        "industries_to_avoid": _protected(profile.industries_to_avoid),
        "target_locations": _protected(profile.target_locations),
        "work_mode": _protected(profile.work_mode),
        "relocation_policy": _protected(profile.relocation_policy),
        "target_level": _protected(profile.target_level),
        "graduation_year": _protected(profile.graduation_year),
        "professional_experience_years": _protected(profile.professional_experience_years),
        "degree_summary": _protected(profile.degree_summary),
        "available_start_date": _protected(profile.available_start_date),
        "salary_strategy": _protected(profile.salary_strategy),
        "salary_range": _protected(profile.salary_range),
        "self_identification_strategy": _protected(profile.self_identification_strategy),
        "onboarding_completed": profile.onboarding_completed,
        "updated_at": profile.updated_at.isoformat(),
    }


def _resume_dict(item: Resume) -> dict[str, Any]:
    return {
        "id": item.id,
        "label": _protected(item.label),
        "role_family": _protected(item.role_family),
        "source_filename": _protected(item.source_filename),
        "file_type": item.file_type,
        "encrypted_file_object": Path(item.encrypted_file_path).name if item.encrypted_file_path else "",
        "skills": _protected(item.skills),
        "is_default": item.is_default,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _experience_dict(item: Experience) -> dict[str, Any]:
    return {
        "id": item.id,
        "resume_id": item.resume_id,
        "category": item.category,
        "title": _protected(item.title),
        "organization": _protected(item.organization),
        "date_range": _protected(item.date_range),
        "description": _protected(item.description),
        "tags": _protected(item.tags),
        "source_ref": _protected(item.source_ref),
        "updated_at": item.updated_at.isoformat(),
    }


def _job_dict(item: Job) -> dict[str, Any]:
    return {
        "id": item.id,
        "url": item.url,
        "source": item.source,
        "company": item.company,
        "title": item.title,
        "location": item.location,
        "posted_date": item.posted_date,
        "description": item.description,
        "status": item.status,
        "recommendation": item.recommendation,
        "fit_label": item.fit_label,
        "eligibility_status": item.eligibility_status,
        "freshness_status": item.freshness_status,
        "application_effort": item.application_effort,
        "reasons": _protected(item.reasons),
        "risks": _protected(item.risks),
        "unknowns": _protected(item.unknowns),
        "matched_skills": _protected(item.matched_skills),
        "missing_skills": _protected(item.missing_skills),
        "selected_resume_id": item.selected_resume_id,
        "next_action": _protected(item.next_action),
        "next_action_date": _protected(item.next_action_date),
        "current_stage": _protected(item.current_stage),
        "notes": _protected(item.notes),
        "applied_at": item.applied_at.isoformat() if item.applied_at else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _pack_dict(item: ApplicationPack) -> dict[str, Any]:
    return {
        "id": item.id,
        "job_id": item.job_id,
        "resume_id": item.resume_id,
        "experience_ids": _protected(item.experience_ids),
        "fit_summary": _protected(item.fit_summary),
        "why_role_draft": _protected(item.why_role_draft),
        "why_company_draft": _protected(item.why_company_draft),
        "work_authorization_answer": _protected(item.work_authorization_answer),
        "sponsorship_answer": _protected(item.sponsorship_answer),
        "salary_answer": _protected(item.salary_answer),
        "checklist": _protected(item.checklist),
        "user_reviewed": item.user_reviewed,
        "updated_at": item.updated_at.isoformat(),
    }


def _ai_enhancement_dict(item: AIApplicationEnhancement) -> dict[str, Any]:
    return {
        "id": item.id,
        "job_id": item.job_id,
        "provider": item.provider,
        "model": item.model,
        "mode": item.mode,
        "status": item.status,
        "prompt_version": item.prompt_version,
        "content": _protected(item.content),
        "usage": _protected(item.usage),
        "error_message": _protected(item.error_message),
        "generated_at": item.generated_at.isoformat(),
    }


def _event_dict(item: JobEvent) -> dict[str, Any]:
    return {
        "id": item.id,
        "job_id": item.job_id,
        "event_type": _protected(item.event_type),
        "note": _protected(item.note),
        "occurred_at": item.occurred_at.isoformat(),
    }
