from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import ai
from .config import Settings
from .discovery import NormalizedJob, _upsert_job, enqueue_discovery, enrich
from .models import (
    ApplicationEvent, ApplicationPack, AuditLog, CandidateProfile, DiscoveryRun,
    Experience, Job, Recommendation, Resume, User, utcnow,
)
from .resume import experience_records, parse_resume, profile_draft
from .scoring import score_job
from .security import CryptoBox


DEFAULT_PROFILE = {
    "primary_role_families": [],
    "secondary_role_families": [],
    "target_locations": [],
    "work_mode": [],
    "skills": [],
    "keywords": [],
    "work_authorization": "",
    "sponsorship_now": "",
    "sponsorship_future": "",
    "relocation": "",
    "available_start": "",
    "avoid_roles": [],
    "avoid_industries": [],
}


def audit(db: Session, action: str, user_id: int | None = None, detail: str | None = None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=(detail or "")[:1000] or None))
    db.commit()


def get_profile_row(db: Session, user_id: int) -> CandidateProfile | None:
    return db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))


def get_profile(db: Session, crypto: CryptoBox, user_id: int) -> dict[str, Any]:
    row = get_profile_row(db, user_id)
    if not row:
        return dict(DEFAULT_PROFILE)
    return {**DEFAULT_PROFILE, **crypto.decrypt_json(row.payload_encrypted, {})}


def save_profile(
    db: Session,
    crypto: CryptoBox,
    user_id: int,
    payload: dict[str, Any],
    *,
    onboarding_state: str | None = None,
    discovery_enabled: bool | None = None,
) -> CandidateProfile:
    row = get_profile_row(db, user_id)
    if not row:
        row = CandidateProfile(
            user_id=user_id,
            payload_encrypted=crypto.encrypt_json({**DEFAULT_PROFILE, **payload}),
            onboarding_state=onboarding_state or "needs_resume",
            discovery_enabled=bool(discovery_enabled),
        )
        db.add(row)
    else:
        row.payload_encrypted = crypto.encrypt_json({**DEFAULT_PROFILE, **payload})
        if onboarding_state is not None:
            row.onboarding_state = onboarding_state
        if discovery_enabled is not None:
            row.discovery_enabled = discovery_enabled
        row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def store_resume(
    db: Session,
    crypto: CryptoBox,
    settings: Settings,
    *,
    user_id: int,
    filename: str,
    content_type: str,
    data: bytes,
    text: str,
) -> tuple[Resume, dict]:
    parsed = parse_resume(text)
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    storage_name = secrets.token_hex(24) + Path(filename).suffix.lower()
    path = settings.upload_root / storage_name
    path.write_bytes(crypto.fernet.encrypt(data))

    for prior in db.scalars(select(Resume).where(Resume.user_id == user_id, Resume.is_primary.is_(True))).all():
        prior.is_primary = False
    resume = Resume(
        user_id=user_id,
        original_name_encrypted=crypto.encrypt_text(filename),
        storage_name=storage_name,
        text_encrypted=crypto.encrypt_text(text),
        parsed_encrypted=crypto.encrypt_json(parsed),
        content_type=content_type[:120],
        size_bytes=len(data),
        is_primary=True,
    )
    db.add(resume)
    db.flush()

    db.execute(delete(Experience).where(Experience.user_id == user_id))
    for record in experience_records(parsed):
        db.add(Experience(
            user_id=user_id,
            title_encrypted=crypto.encrypt_text(record["title"]),
            detail_encrypted=crypto.encrypt_text(record["detail"]),
            kind=record["kind"],
            strength=record["strength"],
        ))

    current = get_profile(db, crypto, user_id)
    draft = profile_draft(parsed)
    for key, value in draft.items():
        if value and not current.get(key):
            current[key] = value
    save_profile(db, crypto, user_id, current, onboarding_state="needs_confirmation", discovery_enabled=False)
    db.commit()
    db.refresh(resume)
    return resume, parsed


def list_experiences(db: Session, crypto: CryptoBox, user_id: int) -> list[dict]:
    rows = db.scalars(select(Experience).where(Experience.user_id == user_id).order_by(Experience.id)).all()
    return [{
        "id": row.id,
        "title": crypto.decrypt_text(row.title_encrypted),
        "detail": crypto.decrypt_text(row.detail_encrypted),
        "kind": row.kind,
        "strength": row.strength,
    } for row in rows]


def list_resumes(db: Session, crypto: CryptoBox, user_id: int) -> list[dict]:
    rows = db.scalars(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())).all()
    return [{
        "id": row.id,
        "name": crypto.decrypt_text(row.original_name_encrypted),
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "is_primary": row.is_primary,
        "created_at": row.created_at.isoformat(),
    } for row in rows]


def manual_job(
    db: Session,
    crypto: CryptoBox,
    user_id: int,
    *,
    url: str,
    title: str,
    company: str,
    location: str,
    description: str,
) -> Recommendation:
    profile = get_profile(db, crypto, user_id)
    item = enrich(NormalizedJob(
        source="manual",
        external_id=f"user-{user_id}-{secrets.token_hex(8)}",
        url=url,
        title=title,
        company=company,
        location=location,
        description=description,
        owner_user_id=user_id,
    ))
    job, _created = _upsert_job(db, item)
    score = score_job(profile, {
        "title": item.title,
        "description": item.description,
        "location": item.location,
        "city": item.city,
        "work_mode": item.work_mode,
        "role_family": item.role_family,
        "industry": item.industry,
        "skills": item.skills or [],
        "keywords": item.keywords or [],
        "posted_at": item.posted_at,
    })
    rec = Recommendation(
        user_id=user_id,
        job_id=job.id,
        qualification=score["qualification"],
        relevance=score["relevance"],
        opportunity=score["opportunity"],
        rank_score=score["rank_score"],
        reasons_encrypted=crypto.encrypt_json(score["reasons"]),
        user_status="new",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def recommendation_for_user(db: Session, user_id: int, rec_id: int) -> tuple[Recommendation, Job] | None:
    row = db.execute(
        select(Recommendation, Job)
        .join(Job, Job.id == Recommendation.job_id)
        .where(
            Recommendation.id == rec_id,
            Recommendation.user_id == user_id,
            or_for_owner(user_id),
        )
    ).first()
    return row if row else None


def or_for_owner(user_id: int):
    from sqlalchemy import or_
    return or_(Job.owner_user_id.is_(None), Job.owner_user_id == user_id)


def build_application_pack(
    db: Session,
    crypto: CryptoBox,
    settings: Settings,
    user: User,
    recommendation: Recommendation,
    job: Job,
) -> tuple[ApplicationPack, str | None]:
    profile = get_profile(db, crypto, user.id)
    experiences = list_experiences(db, crypto, user.id)
    primary_resume = db.scalar(
        select(Resume).where(Resume.user_id == user.id, Resume.is_primary.is_(True)).order_by(Resume.created_at.desc())
    )
    selected = experiences[:4]
    reasons = crypto.decrypt_json(recommendation.reasons_encrypted, [])
    content = {
        "company": job.company,
        "job_title": job.title,
        "job_url": job.url,
        "resume": crypto.decrypt_text(primary_resume.original_name_encrypted) if primary_resume else "未上传",
        "selected_experiences": selected,
        "qualification": recommendation.qualification,
        "relevance": recommendation.relevance,
        "opportunity": recommendation.opportunity,
        "reasons": reasons,
        "answers": {
            "why_role": f"这个岗位与我的 {', '.join(profile.get('primary_role_families', [])[:2]) or '职业方向'} 相符，我能用已有技能和经历快速贡献。",
            "why_company": f"我希望把已有能力用于 {job.company} 的实际业务问题，并在岗位要求的方向持续成长。",
            "work_authorization": profile.get("work_authorization") or "需要本人确认",
            "sponsorship_now": profile.get("sponsorship_now") or "需要本人确认",
            "sponsorship_future": profile.get("sponsorship_future") or "需要本人确认",
            "available_start": profile.get("available_start") or "需要本人确认",
        },
        "review_required": [
            "核对姓名、邮箱、电话与工作权利",
            "核对上传的简历版本",
            "核对 Sponsorship 与入职时间",
            "最终提交前由本人确认",
        ],
    }
    ai_note = None
    try:
        enhanced = ai.generate(
            db,
            settings,
            user,
            system_prompt=(
                "你是候选人求职材料编辑。只能使用输入中已有事实，不得编造经历、数字、学历、工作权利或证书。"
                "输出简洁中文，分别给出 why_role 与 why_company。"
            ),
            user_prompt=json.dumps({
                "job": {"title": job.title, "company": job.company, "description": job.description[:12000]},
                "profile": profile,
                "experiences": selected,
            }, ensure_ascii=False),
            max_tokens=900,
        )
        content["ai_enhancement"] = enhanced
    except ai.AIUnavailable as exc:
        ai_note = str(exc)
        content["ai_enhancement"] = None

    pack = ApplicationPack(
        user_id=user.id,
        job_id=job.id,
        resume_id=primary_resume.id if primary_resume else None,
        content_encrypted=crypto.encrypt_json(content),
    )
    db.add(pack)
    recommendation.user_status = "preparing"
    db.commit()
    db.refresh(pack)
    return pack, ai_note


def user_export(db: Session, crypto: CryptoBox, user: User) -> dict:
    profile = get_profile(db, crypto, user.id)
    resumes = list_resumes(db, crypto, user.id)
    experiences = list_experiences(db, crypto, user.id)
    recs = db.execute(
        select(Recommendation, Job).join(Job).where(Recommendation.user_id == user.id)
    ).all()
    packs = db.scalars(select(ApplicationPack).where(ApplicationPack.user_id == user.id)).all()
    events = db.scalars(select(ApplicationEvent).where(ApplicationEvent.user_id == user.id)).all()
    return {
        "profile": profile,
        "resumes": resumes,
        "experiences": experiences,
        "recommendations": [{
            "id": rec.id,
            "company": job.company,
            "title": job.title,
            "url": job.url,
            "qualification": rec.qualification,
            "relevance": rec.relevance,
            "opportunity": rec.opportunity,
            "status": rec.user_status,
            "reasons": crypto.decrypt_json(rec.reasons_encrypted, []),
        } for rec, job in recs],
        "application_packs": [crypto.decrypt_json(pack.content_encrypted, {}) for pack in packs],
        "application_events": [{
            "job_id": event.job_id,
            "status": event.status,
            "evidence": crypto.decrypt_text(event.evidence_encrypted, ""),
            "notes": crypto.decrypt_text(event.notes_encrypted, ""),
            "created_at": event.created_at.isoformat(),
        } for event in events],
    }


def delete_user_account(db: Session, settings: Settings, user: User) -> None:
    names = db.scalars(select(Resume.storage_name).where(Resume.user_id == user.id)).all()
    db.delete(user)
    db.commit()
    for name in names:
        path = settings.upload_root / name
        if path.exists():
            path.unlink()
