from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import ai
from .config import Settings
from .discovery import NormalizedJob, _upsert_job, clean_html, enqueue_discovery, enrich
from .models import (
    ApplicationEvent, ApplicationPack, ApplicationProgress, AuditLog, CandidateProfile, DiscoveryRun,
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

APPLICATION_STATUSES = {"pending", "submitted", "interview", "rejected", "offer", "withdrawn"}


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


def _json_strings(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _requirement_evidence(
    requirement: str,
    *,
    role_family: str,
    profile: dict[str, Any],
    experiences: list[dict],
) -> dict[str, str]:
    needle = requirement.casefold()
    primary_roles = [str(role).strip() for role in profile.get("primary_role_families", []) if str(role).strip()]
    profile_skills = [str(skill).strip() for skill in profile.get("skills", []) if str(skill).strip()]
    if role_family and needle == role_family.casefold() and any(role.casefold() == needle for role in primary_roles):
        return {
            "requirement": requirement,
            "state": "confirmed_direction",
            "evidence": f"已确认的目标岗位方向：{requirement}",
        }
    for skill in profile_skills:
        normalized = skill.casefold()
        if needle == normalized or (len(needle) > 2 and (needle in normalized or normalized in needle)):
            return {
                "requirement": requirement,
                "state": "confirmed",
                "evidence": f"简历中已识别的技能：{skill}",
            }
    for experience in experiences:
        detail = str(experience.get("detail") or "").strip()
        title = str(experience.get("title") or "").strip()
        if needle and needle in f"{title} {detail}".casefold():
            return {
                "requirement": requirement,
                "state": "confirmed",
                "evidence": detail or title,
            }
    return {
        "requirement": requirement,
        "state": "needs_confirmation",
        "evidence": "当前已确认资料未找到直接依据，请在投递前自行补充或核对。",
    }


def build_application_materials(
    profile: dict[str, Any],
    experiences: list[dict],
    job: Job,
) -> dict[str, Any]:
    """Create an editable, fact-grounded application draft without touching a Resume."""
    requirements = _unique_strings([
        job.role_family,
        *_json_strings(job.skills_text),
        *_json_strings(job.keywords_text),
    ])[:7]
    evidence = [
        _requirement_evidence(
            requirement,
            role_family=job.role_family,
            profile=profile,
            experiences=experiences,
        )
        for requirement in requirements
    ]
    confirmed = [item for item in evidence if item["state"] != "needs_confirmation"]
    selected_experiences = [
        item for item in experiences
        if any(
            requirement.casefold() in f"{item.get('title', '')} {item.get('detail', '')}".casefold()
            for requirement in requirements
            if requirement
        )
    ]
    selected_experiences.extend(item for item in experiences if item not in selected_experiences)
    selected_experiences = selected_experiences[:4]
    fact_lines = [item["evidence"] for item in confirmed if item["state"] == "confirmed"]
    if not fact_lines:
        fact_lines = [str(item.get("detail") or item.get("title") or "").strip() for item in selected_experiences]
    fact_lines = [line for line in fact_lines if line][:3]
    known_evidence = "；".join(fact_lines) if fact_lines else "当前资料中尚无可直接复述的相关经历"
    roles = "、".join(str(role) for role in profile.get("primary_role_families", []) if str(role).strip()) or "待本人确认的职业方向"
    lead_requirement = requirements[0] if requirements else (job.role_family or job.title)
    gaps = [item["requirement"] for item in evidence if item["state"] == "needs_confirmation"]
    return {
        "why_me": {
            "summary": (
                f"这份 Why me 只使用已确认资料：你的目标方向为 {roles}；"
                f"可直接核对的相关内容包括：{known_evidence}。"
                "未被证据覆盖的要求会明确列为待确认，不应写成既有经历。"
            ),
            "evidence": evidence,
        },
        "tailored_cv": {
            "headline": f"面向 {job.title} 的岗位适配简历草稿",
            "summary": "这是派生申请材料，不会修改或覆盖原始简历；仅优先呈现已确认的技能和经历。",
            "bullets": [str(item.get("detail") or item.get("title") or "").strip() for item in selected_experiences if str(item.get("detail") or item.get("title") or "").strip()],
            "matched_terms": [item["requirement"] for item in confirmed],
            "gaps": gaps,
        },
        "interview_answers": [
            {
                "key": "why_role",
                "title": "Why this role?",
                "answer": (
                    f"我申请 {job.title}，因为它与我已确认的目标方向 {roles} 有关。"
                    f"我会重点呈现可核对的经历与技能：{known_evidence}。"
                    "岗位其余要求会在投递前逐项确认，而不会写成未经证实的能力。"
                ),
            },
            {
                "key": "why_me",
                "title": "Why should we hire you?",
                "answer": (
                    f"我能提供的是可回到简历核对的事实，而不是泛化承诺：{known_evidence}。"
                    f"这些材料可用于说明我如何接近岗位所需的 {lead_requirement}；"
                    "任何未覆盖的要求我会如实说明并补充证据。"
                ),
            },
            {
                "key": "role_example",
                "title": f"请举例说明你与 {lead_requirement} 相关的经历",
                "answer": (
                    f"我会从简历中这段真实经历开始说明：{fact_lines[0] if fact_lines else '目前没有可直接复述的经历，请先补充真实例子。'}"
                    "我会按情境、本人行动和可核对结果组织回答，不补造数字或职责。"
                ),
            },
        ],
    }


def ensure_application_materials(
    content: dict[str, Any],
    *,
    profile: dict[str, Any],
    experiences: list[dict],
    job: Job,
) -> dict[str, Any]:
    if not isinstance(content, dict):
        content = {}
    generated = build_application_materials(profile, experiences, job)
    materials = content.get("materials")
    if not isinstance(materials, dict):
        content["materials"] = generated
        return content

    # Old packs may predate the editable workspace.  Fill only missing fields
    # so an applicant's deliberate edits always remain the source of truth.
    for section in ("why_me", "tailored_cv"):
        existing = materials.get(section)
        if not isinstance(existing, dict):
            existing = {}
            materials[section] = existing
        for key, value in generated[section].items():
            existing.setdefault(key, value)

    existing_answers = {
        str(item.get("key")): item
        for item in materials.get("interview_answers", [])
        if isinstance(item, dict) and item.get("key")
    }
    materials["interview_answers"] = [
        {**answer, **existing_answers.get(answer["key"], {})}
        for answer in generated["interview_answers"]
    ]
    return content


def update_application_materials(
    db: Session,
    crypto: CryptoBox,
    pack: ApplicationPack,
    *,
    content: dict[str, Any] | None = None,
    why_me_summary: str,
    cv_headline: str,
    cv_summary: str,
    cv_bullets: str,
    interview_answers: dict[str, str],
) -> dict[str, Any]:
    content = content if content is not None else crypto.decrypt_json(pack.content_encrypted, {})
    materials = content.setdefault("materials", {})
    why_me = materials.setdefault("why_me", {})
    tailored_cv = materials.setdefault("tailored_cv", {})
    questions = materials.setdefault("interview_answers", [])
    why_me["summary"] = why_me_summary.strip()[:3000]
    tailored_cv["headline"] = cv_headline.strip()[:240]
    tailored_cv["summary"] = cv_summary.strip()[:3000]
    tailored_cv["bullets"] = [line.strip()[:1000] for line in cv_bullets.splitlines() if line.strip()][:12]
    for question in questions:
        key = str(question.get("key") or "")
        if key in interview_answers:
            question["answer"] = interview_answers[key].strip()[:4000]
    pack.content_encrypted = crypto.encrypt_json(content)
    pack.updated_at = utcnow()
    pack.version += 1
    db.commit()
    db.refresh(pack)
    return content


def consult_application_materials(
    db: Session,
    settings: Settings,
    user: User,
    *,
    job: Job,
    materials: dict[str, Any],
    question: str,
) -> tuple[str, str | None]:
    safe_question = question.strip()[:2000]
    source_context = {
        "job": {
            "title": job.title,
            "company": job.company,
            "description": clean_html(job.description)[:6000],
            "requirements": _unique_strings([job.role_family, *_json_strings(job.skills_text), *_json_strings(job.keywords_text)])[:8],
        },
        "materials": materials,
        "candidate_question": safe_question,
    }
    try:
        answer = ai.generate(
            db,
            settings,
            user,
            system_prompt=(
                "你是站内求职材料顾问。只能依据输入的岗位和候选人材料回答；"
                "不得编造经历、数字、学历、证书、工作权利或公司事实。"
                "缺少证据时明确写‘资料不足，需本人确认’。"
                "给出简洁、可编辑的建议，并区分已确认事实与待确认项。"
            ),
            user_prompt=json.dumps(source_context, ensure_ascii=False),
            max_tokens=900,
        )
        return answer, None
    except ai.AIUnavailable as exc:
        evidence = materials.get("why_me", {}).get("evidence", []) if isinstance(materials, dict) else []
        confirmed = [str(item.get("evidence") or "") for item in evidence if item.get("state") != "needs_confirmation"]
        fallback = (
            "平台 AI 当前不可用，不能替你生成未经核对的回答。"
            "请先围绕这些已确认材料准备："
            + ("；".join(confirmed[:3]) if confirmed else "资料不足，需本人确认并补充真实经历。")
        )
        return fallback, str(exc)


def application_progress_error(status: str, evidence: str) -> str | None:
    if status not in APPLICATION_STATUSES:
        return "无效申请状态。"
    if status == "submitted" and len(evidence.strip()) < 5:
        return "只有看到确认页面、确认文字或申请编号后，才能记录为已提交。"
    return None


def list_application_progresses(db: Session, crypto: CryptoBox, user_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ApplicationProgress, Job)
        .join(Job, Job.id == ApplicationProgress.job_id)
        .where(ApplicationProgress.user_id == user_id, or_for_owner(user_id))
        .order_by(ApplicationProgress.updated_at.desc(), ApplicationProgress.id.desc())
    ).all()
    return [{
        "progress": progress,
        "job": job,
        "evidence": crypto.decrypt_text(progress.evidence_encrypted, ""),
        "notes": crypto.decrypt_text(progress.notes_encrypted, ""),
    } for progress, job in rows]


def application_progress_for_user(db: Session, user_id: int, progress_id: int) -> ApplicationProgress | None:
    return db.scalar(
        select(ApplicationProgress).where(
            ApplicationProgress.id == progress_id,
            ApplicationProgress.user_id == user_id,
        )
    )


def create_application_progress(
    db: Session,
    crypto: CryptoBox,
    *,
    user_id: int,
    job_id: int,
    status: str,
    evidence: str,
    notes: str,
) -> tuple[ApplicationProgress, bool]:
    existing = db.scalar(
        select(ApplicationProgress).where(ApplicationProgress.user_id == user_id, ApplicationProgress.job_id == job_id)
    )
    if existing:
        return existing, False
    progress = ApplicationProgress(
        user_id=user_id,
        job_id=job_id,
        status=status,
        evidence_encrypted=crypto.encrypt_text(evidence.strip()) if evidence.strip() else None,
        notes_encrypted=crypto.encrypt_text(notes.strip()) if notes.strip() else None,
        version=1,
    )
    db.add(progress)
    db.flush()
    db.add(ApplicationEvent(
        user_id=user_id,
        job_id=job_id,
        status=status,
        evidence_encrypted=progress.evidence_encrypted,
        notes_encrypted=progress.notes_encrypted,
        action="created",
        revision=progress.version,
    ))
    db.commit()
    db.refresh(progress)
    return progress, True


def update_application_progress(
    db: Session,
    crypto: CryptoBox,
    progress: ApplicationProgress,
    *,
    status: str,
    evidence: str,
    notes: str,
) -> ApplicationProgress:
    progress.status = status
    progress.evidence_encrypted = crypto.encrypt_text(evidence.strip()) if evidence.strip() else None
    progress.notes_encrypted = crypto.encrypt_text(notes.strip()) if notes.strip() else None
    progress.updated_at = utcnow()
    progress.version += 1
    db.add(ApplicationEvent(
        user_id=progress.user_id,
        job_id=progress.job_id,
        status=status,
        evidence_encrypted=progress.evidence_encrypted,
        notes_encrypted=progress.notes_encrypted,
        action="edited",
        revision=progress.version,
    ))
    db.commit()
    db.refresh(progress)
    return progress


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
    reasons = crypto.decrypt_json(recommendation.reasons_encrypted, [])
    materials = build_application_materials(profile, experiences, job)
    answers_by_key = {
        item["key"]: item["answer"]
        for item in materials["interview_answers"]
    }
    content = {
        "company": job.company,
        "job_title": job.title,
        "job_url": job.url,
        "resume": crypto.decrypt_text(primary_resume.original_name_encrypted) if primary_resume else "未上传",
        "selected_experiences": experiences[:4],
        "qualification": recommendation.qualification,
        "relevance": recommendation.relevance,
        "opportunity": recommendation.opportunity,
        "reasons": reasons,
        "materials": materials,
        "answers": {
            # Keep the established keys for data exports and older pack links.
            "why_role": answers_by_key["why_role"],
            "why_company": answers_by_key["why_me"],
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
                "你是候选人求职材料复核助手。只能使用输入中已有事实，不得编造经历、数字、学历、工作权利或证书。"
                "只指出可改进的表达、待确认要求和可核对的证据，不要把未知信息补成事实。"
            ),
            user_prompt=json.dumps({
                "job": {"title": job.title, "company": job.company, "description": clean_html(job.description)[:12000]},
                "materials": materials,
            }, ensure_ascii=False),
            max_tokens=700,
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
    progresses = db.scalars(select(ApplicationProgress).where(ApplicationProgress.user_id == user.id)).all()
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
        "application_progresses": [{
            "job_id": progress.job_id,
            "status": progress.status,
            "evidence": crypto.decrypt_text(progress.evidence_encrypted, ""),
            "notes": crypto.decrypt_text(progress.notes_encrypted, ""),
            "version": progress.version,
            "created_at": progress.created_at.isoformat(),
            "updated_at": progress.updated_at.isoformat(),
        } for progress in progresses],
        "application_events": [{
            "job_id": event.job_id,
            "status": event.status,
            "evidence": crypto.decrypt_text(event.evidence_encrypted, ""),
            "notes": crypto.decrypt_text(event.notes_encrypted, ""),
            "action": event.action,
            "revision": event.revision,
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
