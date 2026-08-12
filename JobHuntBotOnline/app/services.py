from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import ai
from .career_intelligence import (
    domain_for_role,
    domain_label,
    extract_job_requirements,
    normalize_role,
    normalize_roles,
    role_label,
)
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
    "experience_years": None,
    "professional_credentials": [],
    "credentials_confirmed": False,
    "education_levels": [],
    "legal_admission": "uncertain",
    "practising_certificate": "uncertain",
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


def score_evidence(score: dict[str, Any]) -> dict[str, Any]:
    """Keep score explanations structured while accepting existing records."""
    return {
        "reasons": list(score.get("reasons") or []),
        "requirement_checks": list(score.get("requirement_checks") or []),
        "requirements": dict(score.get("requirements") or {}),
        "domain": str(score.get("domain") or "general"),
        "role_family": str(score.get("role_family") or ""),
    }


def decode_score_evidence(crypto: CryptoBox, encrypted: bytes | None) -> dict[str, Any]:
    raw = crypto.decrypt_json(encrypted, {})
    if isinstance(raw, list):
        return {
            "reasons": [str(item) for item in raw],
            "requirement_checks": [],
            "requirements": {},
            "domain": "general",
            "role_family": "",
        }
    if not isinstance(raw, dict):
        raw = {}
    return {
        "reasons": [str(item) for item in raw.get("reasons", []) if str(item)],
        "requirement_checks": [
            item for item in raw.get("requirement_checks", []) if isinstance(item, dict)
        ],
        "requirements": raw.get("requirements", {}) if isinstance(raw.get("requirements"), dict) else {},
        "domain": str(raw.get("domain") or "general"),
        "role_family": str(raw.get("role_family") or ""),
    }


def _job_payload(job: Job) -> dict[str, Any]:
    return {
        "title": job.title,
        "description": job.description,
        "location": job.location,
        "city": job.city,
        "work_mode": job.work_mode,
        "role_family": job.role_family,
        "industry": job.industry,
        "skills": _json_strings(job.skills_text),
        "keywords": _json_strings(job.keywords_text),
        "posted_at": job.posted_at,
    }


def _terms(value: Any) -> set[str]:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    text = str(value or "")
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}|[\u4e00-\u9fff]{2,8}", text)
    }


def route_resume_for_job(
    db: Session,
    crypto: CryptoBox,
    user_id: int,
    job: Job,
) -> tuple[Resume | None, dict[str, Any], dict[str, Any]]:
    """Select the most evidenced resume for this job, not merely the latest one."""
    rows = db.scalars(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())
    ).all()
    if not rows:
        return None, {}, {"score": 0, "reasons": ["尚未上传简历"], "alternatives": []}

    job_info = _job_payload(job)
    requirements = extract_job_requirements(job_info)
    job_role = normalize_role(job.role_family or str(requirements.get("role_family") or ""))
    job_domain = domain_for_role(job_role, f"{job.title} {job.description}")
    job_terms = (
        _terms(job_info["skills"])
        | _terms(job_info["keywords"])
        | _terms(job.title)
        | _terms(job_role)
    )
    required_credentials = set(requirements.get("required_credentials") or [])
    ranked: list[tuple[int, Resume, dict[str, Any], list[str]]] = []

    for row in rows:
        text = crypto.decrypt_text(row.text_encrypted, "")
        parsed = parse_resume(text) if text else crypto.decrypt_json(row.parsed_encrypted, {})
        roles = normalize_roles(parsed.get("role_families", []))
        domains = {domain_for_role(role) for role in roles}
        resume_terms = _terms(parsed.get("skills", [])) | _terms(parsed.get("keywords", []))
        credentials = set(parsed.get("professional_credentials", []))
        overlap = resume_terms & job_terms
        route_score = len(overlap) * 7
        reasons: list[str] = []
        if job_role and job_role in roles:
            route_score += 60
            reasons.append(f"简历方向与“{role_label(job_role)}”直接一致")
        elif job_domain in domains:
            route_score += 34
            reasons.append(f"简历属于同一{domain_label(job_domain)}领域")
        if overlap:
            route_score += min(35, len(overlap) * 3)
            reasons.append("覆盖岗位关键词：" + "、".join(sorted(overlap, key=str.casefold)[:6]))
        covered_credentials = credentials & required_credentials
        if covered_credentials:
            route_score += 22 * len(covered_credentials)
            reasons.append("覆盖岗位资质：" + "、".join(sorted(covered_credentials)))
        if required_credentials - credentials:
            route_score -= 8 * len(required_credentials - credentials)
        ranked.append((
            route_score,
            row,
            parsed,
            reasons or ["这份简历与岗位的直接证据较少，建议本人核对。"],
        ))

    # The primary/default flag is deliberately a tie-breaker only.  It must
    # never compensate for weaker job evidence from another resume.
    ranked.sort(
        key=lambda item: (item[0], int(item[1].is_primary), item[1].created_at),
        reverse=True,
    )
    best_score, best, parsed, reasons = ranked[0]
    alternatives = [
        {
            "resume_id": row.id,
            "name": crypto.decrypt_text(row.original_name_encrypted),
            "score": score,
        }
        for score, row, _parsed, _reasons in ranked[1:4]
    ]
    return best, parsed, {
        "score": best_score,
        "reasons": reasons,
        "alternatives": alternatives,
        "job_role": job_role,
        "job_domain": job_domain,
    }


def _selected_resume_experiences(parsed: dict[str, Any], job: Job) -> list[dict[str, str]]:
    terms = _terms(_json_strings(job.skills_text)) | _terms(_json_strings(job.keywords_text)) | _terms(job.title)
    rows: list[dict[str, Any]] = []
    for index, detail in enumerate(parsed.get("experiences", []), start=1):
        detail_text = str(detail).strip()
        if not detail_text:
            continue
        overlap = len(_terms(detail_text) & terms)
        rows.append({
            "title": f"经历 {index}",
            "detail": detail_text,
            "kind": "experience",
            "strength": "high" if overlap >= 2 else "medium",
            "overlap": overlap,
        })
    rows.sort(key=lambda row: (row["overlap"], row["strength"] == "high"), reverse=True)
    return [{key: value for key, value in row.items() if key != "overlap"} for row in rows[:4]]


def _routed_requirement_evidence(
    requirement: str,
    parsed: dict[str, Any],
    selected: list[dict[str, str]],
) -> dict[str, str]:
    needle = requirement.casefold()
    credentials = {str(item).casefold() for item in parsed.get("professional_credentials", [])}
    skills = {str(item).casefold() for item in parsed.get("skills", [])}
    if needle in credentials:
        return {
            "requirement": requirement,
            "state": "confirmed",
            "evidence": f"所选简历中识别到专业资质：{requirement}",
        }
    for skill in skills:
        if needle == skill or (len(needle) > 2 and (needle in skill or skill in needle)):
            return {
                "requirement": requirement,
                "state": "confirmed",
                "evidence": f"所选简历中识别到技能：{skill}",
            }
    for item in selected:
        if needle and needle in f"{item['title']} {item['detail']}".casefold():
            return {"requirement": requirement, "state": "confirmed", "evidence": item["detail"]}
    return {
        "requirement": requirement,
        "state": "needs_confirmation",
        "evidence": "所选简历没有直接证据，请勿写成已具备。",
    }


def build_routed_application_materials(
    profile: dict[str, Any],
    parsed: dict[str, Any],
    selected: list[dict[str, str]],
    job: Job,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    requirements = list(dict.fromkeys([
        role_label(job.role_family),
        *_json_strings(job.skills_text),
        *(str(item.get("label") or "") for item in evidence.get("requirement_checks", [])),
    ]))[:10]
    requirement_evidence = [
        _routed_requirement_evidence(item, parsed, selected) for item in requirements if item
    ]
    confirmed = [item for item in requirement_evidence if item["state"] == "confirmed"]
    gaps = [item["requirement"] for item in requirement_evidence if item["state"] != "confirmed"]
    fact_lines = [item["detail"] for item in selected if item.get("detail")][:4]
    role_names = "、".join(
        role_label(role) for role in profile.get("primary_role_families", [])[:3]
    ) or "待确认的职业方向"
    return {
        "why_me": {
            "summary": (
                f"本申请材料只引用所选简历中的已确认内容。你的目标方向为 {role_names}；"
                f"系统优先选择了 {len(fact_lines)} 段与岗位更相关的经历。未被证据覆盖的要求会保留为待确认。"
            ),
            "evidence": requirement_evidence,
        },
        "tailored_cv": {
            "candidate_name": str(parsed.get("candidate_name") or "").strip(),
            "headline": f"面向 {job.title} 的岗位定制简历",
            "summary": f"目标岗位：{job.title}｜{job.company}。以下内容来自所选原始简历，不新增未经确认的事实。",
            "skills": [str(item) for item in parsed.get("skills", []) if str(item).strip()],
            "bullets": fact_lines,
            "education": [str(item) for item in parsed.get("education", []) if str(item).strip()],
            "credentials": [str(item) for item in parsed.get("professional_credentials", []) if str(item).strip()],
            "matched_terms": [item["requirement"] for item in confirmed],
            "gaps": gaps,
        },
        "interview_answers": [
            {
                "key": "why_role",
                "title": "为什么申请这个岗位？",
                "answer": f"这个岗位与我确认的 {role_names} 方向相关。我会重点说明所选简历中可核对的经历，而不会把待确认条件写成已有能力。",
            },
            {
                "key": "why_me",
                "title": "为什么选择我？",
                "answer": "我能提供的是可回到原始简历核对的事实：" + (
                    "；".join(fact_lines[:2]) if fact_lines else "目前需要先补充一段直接相关的真实经历。"
                ),
            },
            {
                "key": "role_example",
                "title": "请举例说明最相关的一段经历",
                "answer": fact_lines[0] if fact_lines else "所选简历尚无可直接复述的相关经历，请先补充真实例子。",
            },
        ],
    }


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
        reasons_encrypted=crypto.encrypt_json(score_evidence(score)),
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
                f"这份岗位适配说明只使用已确认资料：你的目标方向为 {roles}；"
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
                "title": "为什么申请这个岗位？",
                "answer": (
                    f"我申请 {job.title}，因为它与我已确认的目标方向 {roles} 有关。"
                    f"我会重点呈现可核对的经历与技能：{known_evidence}。"
                    "岗位其余要求会在投递前逐项确认，而不会写成未经证实的能力。"
                ),
            },
            {
                "key": "why_me",
                "title": "我为什么适合这个岗位？",
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
    selected_resume, parsed, routing = route_resume_for_job(db, crypto, user.id, job)
    selected_experiences = _selected_resume_experiences(parsed, job) if selected_resume else []
    evidence = decode_score_evidence(crypto, recommendation.reasons_encrypted)
    materials = build_routed_application_materials(
        profile, parsed, selected_experiences, job, evidence
    )
    answers_by_key = {
        item["key"]: item["answer"]
        for item in materials["interview_answers"]
    }
    resume_name = (
        crypto.decrypt_text(selected_resume.original_name_encrypted)
        if selected_resume else "未上传"
    )
    content = {
        "company": job.company,
        "job_title": job.title,
        "job_url": job.url,
        "resume": resume_name,
        "resume_id": selected_resume.id if selected_resume else None,
        "resume_routing": routing,
        "selected_experiences": selected_experiences,
        "qualification": recommendation.qualification,
        "relevance": recommendation.relevance,
        "opportunity": recommendation.opportunity,
        "reasons": evidence["reasons"],
        "requirement_checks": evidence["requirement_checks"],
        "requirements": evidence["requirements"],
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
            "核对姓名、联系方式与工作权利",
            "核对系统自动选择的简历版本及路由理由",
            "核对所有待确认资质、经验和雇主担保条件",
            "下载岗位定制 DOCX 后逐页检查，再由本人上传和提交",
        ],
    }
    ai_note = None
    try:
        enhanced = ai.generate(
            db,
            settings,
            user,
            system_prompt=(
                "你是候选人求职材料复核员。只能使用输入中已有事实，不得编造经历、数字、学历、"
                "执业资格、工作权利或证书。输出中文；先指出最强证据，再列待确认项。"
            ),
            user_prompt=json.dumps({
                "job": {"title": job.title, "company": job.company, "description": clean_html(job.description)[:12000]},
                "profile": profile,
                "selected_resume": {"name": resume_name, "parsed": parsed},
                "routing": routing,
                "requirement_checks": evidence["requirement_checks"],
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
        resume_id=selected_resume.id if selected_resume else None,
        content_encrypted=crypto.encrypt_json(content),
    )
    db.add(pack)
    recommendation.user_status = "preparing"
    db.commit()
    db.refresh(pack)
    return pack, ai_note


def application_pack_for_user(
    db: Session,
    crypto: CryptoBox,
    user_id: int,
    pack_id: int,
) -> tuple[ApplicationPack, Job, Resume | None, dict[str, Any], dict[str, Any]] | None:
    pack = db.scalar(
        select(ApplicationPack).where(
            ApplicationPack.id == pack_id, ApplicationPack.user_id == user_id
        )
    )
    if not pack:
        return None
    job = db.get(Job, pack.job_id)
    if not job or (job.owner_user_id is not None and job.owner_user_id != user_id):
        return None
    resume = db.get(Resume, pack.resume_id) if pack.resume_id else None
    if resume and resume.user_id != user_id:
        return None
    text = crypto.decrypt_text(resume.text_encrypted, "") if resume else ""
    parsed = parse_resume(text) if text else {}
    content = crypto.decrypt_json(pack.content_encrypted, {})
    return pack, job, resume, parsed, content


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
            "reasons": decode_score_evidence(crypto, rec.reasons_encrypted)["reasons"],
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
