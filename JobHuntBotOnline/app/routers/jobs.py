from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, verify_csrf
from app.db import get_db
from app.models import (
    ApplicationPack,
    CandidateProfile,
    Experience,
    Job,
    JobEvent,
    Resume,
    json_dumps,
)
from app.services.analyzer import AnalysisResult, analyse_job
from app.services.application_pack import create_or_refresh_pack, pack_as_markdown
from app.services.ai_provider import enhance_application, get_job_enhancement, provider_view
from app.services.audit import record_audit
from app.services.canonical import mark_canonical_dirty
from app.services.job_fetcher import (
    JobDocument,
    JobFetchError,
    fetch_job_document,
    job_document_from_manual,
)
from app.web import flash, render


router = APIRouter()
ALLOWED_STATUSES = {
    "Needs review",
    "Needs user",
    "Ready",
    "Applied",
    "Interview",
    "Offer",
    "Rejected",
    "Skipped",
}


def _profile(db: Session, user_id: int) -> CandidateProfile | None:
    return db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))


def _resumes(db: Session, user_id: int) -> list[Resume]:
    return list(db.scalars(select(Resume).where(Resume.user_id == user_id).order_by(Resume.is_default.desc(), Resume.id)))


def _experiences(db: Session, user_id: int) -> list[Experience]:
    return list(db.scalars(select(Experience).where(Experience.user_id == user_id).order_by(Experience.id)))


def _job_or_none(db: Session, user_id: int, job_id: int) -> Job | None:
    return db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user_id))


def _selected_experiences_for_pack(
    db: Session, user_id: int, pack: ApplicationPack | None
) -> list[Experience]:
    if not pack or not pack.experience_ids:
        return []
    items = list(
        db.scalars(
            select(Experience).where(
                Experience.user_id == user_id,
                Experience.id.in_(pack.experience_ids),
            )
        )
    )
    order = {item_id: index for index, item_id in enumerate(pack.experience_ids)}
    items.sort(key=lambda item: order.get(item.id, 999))
    return items


def _apply_analysis(job: Job, result: AnalysisResult) -> None:
    job.recommendation = result.recommendation
    job.fit_label = result.fit_label
    job.eligibility_status = result.eligibility_status
    job.freshness_status = result.freshness_status
    job.application_effort = result.application_effort
    job.reasons_json = json_dumps(result.reasons)
    job.risks_json = json_dumps(result.risks)
    job.unknowns_json = json_dumps(result.unknowns)
    job.matched_skills_json = json_dumps(result.matched_skills)
    job.missing_skills_json = json_dumps(result.missing_skills)
    job.selected_resume_id = result.selected_resume_id
    job.next_action = result.next_action
    if job.status in {"Needs review", "Needs user", "Ready", "Skipped"}:
        job.status = {
            "Apply": "Ready",
            "Needs user": "Needs user",
            "Review": "Needs review",
            "Skip": "Skipped",
        }.get(result.recommendation, "Needs review")


@router.get("/jobs")
def job_list(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    status: str = "",
    q: str = "",
):
    statement = select(Job).where(Job.user_id == user.id)
    if status and status in ALLOWED_STATUSES:
        statement = statement.where(Job.status == status)
    if q.strip():
        needle = f"%{q.strip()}%"
        statement = statement.where(or_(Job.company.ilike(needle), Job.title.ilike(needle), Job.location.ilike(needle)))
    jobs = list(db.scalars(statement.order_by(Job.updated_at.desc())))
    return render(request, "jobs.html", user=user, jobs=jobs, selected_status=status, query=q)


@router.get("/jobs/new")
def new_job_page(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    profile = _profile(db, user.id)
    resumes = _resumes(db, user.id)
    return render(
        request,
        "job_new.html",
        user=user,
        profile=profile,
        resumes=resumes,
        preview=None,
        form_data={},
    )


@router.post("/jobs/preview")
async def preview_job_url(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    url: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    profile = _profile(db, user.id)
    resumes = _resumes(db, user.id)
    try:
        document = await fetch_job_document(url)
    except JobFetchError as exc:
        return render(
            request,
            "job_new.html",
            user=user,
            profile=profile,
            resumes=resumes,
            preview=None,
            form_data={"url": url},
            error=str(exc),
            status_code=400,
        )
    return render(
        request,
        "job_new.html",
        user=user,
        profile=profile,
        resumes=resumes,
        preview=document,
        form_data={"url": url},
        warning=document.manual_reason if not document.fetched else "",
    )


@router.post("/jobs")
async def create_job(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    company: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    posted_date: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    profile = _profile(db, user.id)
    resumes = _resumes(db, user.id)
    experiences = _experiences(db, user.id)

    if not profile or not profile.onboarding_completed:
        flash(request, "请先完成候选人资料，再分析岗位。", "warning")
        return RedirectResponse(url="/onboarding", status_code=303)
    if not resumes:
        flash(request, "请先上传至少一份简历，再分析岗位。", "warning")
        return RedirectResponse(url="/resumes", status_code=303)

    document: JobDocument
    try:
        if description.strip():
            document = job_document_from_manual(
                url=url,
                company=company,
                title=title,
                location=location,
                posted_date=posted_date,
                description=description,
            )
        elif url.strip():
            document = await fetch_job_document(url)
            if not document.fetched:
                raise JobFetchError(document.manual_reason or "请粘贴职位正文。")
        else:
            raise JobFetchError("请提供岗位链接或完整职位正文。")
    except JobFetchError as exc:
        return render(
            request,
            "job_new.html",
            user=user,
            profile=profile,
            resumes=resumes,
            preview=None,
            form_data={
                "url": url,
                "company": company,
                "title": title,
                "location": location,
                "posted_date": posted_date,
                "description": description,
            },
            error=str(exc),
            status_code=400,
        )

    if document.url:
        existing = db.scalar(select(Job).where(Job.user_id == user.id, Job.url == document.url))
        if existing:
            flash(request, "该岗位已经存在，已打开原记录。", "info")
            return RedirectResponse(url=f"/jobs/{existing.id}", status_code=303)

    job = Job(
        user_id=user.id,
        url=document.url,
        source=document.source,
        company=document.company or company.strip() or "Unknown company",
        title=document.title or title.strip() or "Unknown role",
        location=document.location or location.strip(),
        posted_date=document.posted_date or posted_date.strip(),
        description=document.description,
        snapshot_text=document.snapshot_text,
        status="Needs review",
    )
    db.add(job)
    db.flush()

    result = analyse_job(profile=profile, job=job, resumes=resumes, experiences=experiences)
    _apply_analysis(job, result)
    pack = create_or_refresh_pack(db, user_id=user.id, profile=profile, job=job, result=result)
    selected_resume = db.get(Resume, result.selected_resume_id) if result.selected_resume_id else None
    selected_experiences = _selected_experiences_for_pack(db, user.id, pack)
    ai_outcome = await enhance_application(
        db,
        user_id=user.id,
        profile=profile,
        job=job,
        rule_result=result,
        resume=selected_resume,
        experiences=selected_experiences,
        application_pack=pack,
    )
    event_note = "岗位已导入并完成透明规则分析。"
    if ai_outcome.status in {"success", "cached"}:
        event_note += " DeepSeek 已增强申请说明。"
    elif ai_outcome.status == "failed":
        event_note += " DeepSeek 未完成，已安全保留规则结果。"
    db.add(JobEvent(user_id=user.id, job_id=job.id, event_type="Imported", note=event_note))
    record_audit(
        db,
        user=user,
        action="job_imported",
        object_type="job",
        object_id=job.id,
        details={
            "source": job.source,
            "recommendation": job.recommendation,
            "status": job.status,
            "ai_status": ai_outcome.status,
        },
    )
    mark_canonical_dirty(db, "job.created", {"job_id": job.id})
    db.commit()
    if ai_outcome.status == "failed":
        flash(request, ai_outcome.user_message, "warning")
    elif ai_outcome.status in {"success", "cached"}:
        flash(request, "岗位规则分析与 DeepSeek 增强均已完成，申请包已生成。", "success")
    else:
        flash(request, "岗位已完成可解释规则分析，申请包已生成。", "success")
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)


@router.get("/jobs/{job_id}")
def job_detail(
    job_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    job = _job_or_none(db, user.id, job_id)
    if not job:
        flash(request, "没有找到该岗位。", "danger")
        return RedirectResponse(url="/jobs", status_code=303)
    pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job.id))
    resume = db.get(Resume, job.selected_resume_id) if job.selected_resume_id else None
    selected_experiences = _selected_experiences_for_pack(db, user.id, pack)
    events = list(
        db.scalars(
            select(JobEvent)
            .where(JobEvent.user_id == user.id, JobEvent.job_id == job.id)
            .order_by(JobEvent.occurred_at.desc())
        )
    )
    return render(
        request,
        "job_detail.html",
        user=user,
        job=job,
        pack=pack,
        resume=resume,
        experiences=selected_experiences,
        events=events,
        allowed_statuses=sorted(ALLOWED_STATUSES),
        ai_enhancement=get_job_enhancement(db, user.id, job.id),
        ai_provider=provider_view(db, user.id),
    )


@router.post("/jobs/{job_id}/reanalyze")
async def reanalyze_job(
    job_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    mode: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    job = _job_or_none(db, user.id, job_id)
    profile = _profile(db, user.id)
    if not job or not profile:
        flash(request, "无法重新分析该岗位。", "danger")
        return RedirectResponse(url="/jobs", status_code=303)
    resumes = _resumes(db, user.id)
    experiences = _experiences(db, user.id)
    result = analyse_job(
        profile=profile,
        job=job,
        resumes=resumes,
        experiences=experiences,
    )
    _apply_analysis(job, result)
    pack = create_or_refresh_pack(db, user_id=user.id, profile=profile, job=job, result=result)
    selected_resume = db.get(Resume, result.selected_resume_id) if result.selected_resume_id else None
    selected_experiences = _selected_experiences_for_pack(db, user.id, pack)
    ai_outcome = await enhance_application(
        db,
        user_id=user.id,
        profile=profile,
        job=job,
        rule_result=result,
        resume=selected_resume,
        experiences=selected_experiences,
        application_pack=pack,
        requested_mode=mode or None,
        force=True,
    )
    note = "根据当前资料重新运行规则分析。"
    if ai_outcome.status in {"success", "cached"}:
        note += f" DeepSeek {mode or '默认'} 模式已完成。"
    elif ai_outcome.status == "failed":
        note += " DeepSeek 失败，规则结果未受影响。"
    db.add(JobEvent(user_id=user.id, job_id=job.id, event_type="Reanalysed", note=note))
    mark_canonical_dirty(db, "job.reanalysed", {"job_id": job.id, "ai_status": ai_outcome.status})
    db.commit()
    if ai_outcome.status == "failed":
        flash(request, ai_outcome.user_message, "warning")
    elif ai_outcome.status in {"success", "cached"}:
        flash(request, "规则分析与 DeepSeek 增强已刷新。", "success")
    else:
        flash(request, "已使用当前资料重新运行规则分析并刷新申请包。", "success")
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)


@router.post("/jobs/{job_id}/status")
def update_job_status(
    job_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    status: Annotated[str, Form()],
    current_stage: Annotated[str, Form()] = "",
    next_action: Annotated[str, Form()] = "",
    next_action_date: Annotated[str, Form()] = "",
    evidence_note: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    job = _job_or_none(db, user.id, job_id)
    if not job or status not in ALLOWED_STATUSES:
        flash(request, "状态更新无效。", "danger")
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    if status == "Applied" and len(evidence_note.strip()) < 5:
        flash(request, "标记为 Applied 前，请记录官方成功页面、确认文字或申请编号。", "danger")
        return RedirectResponse(url=f"/jobs/{job_id}#progress", status_code=303)

    previous = job.status
    job.status = status
    job.current_stage = current_stage.strip()[:160]
    job.next_action = next_action.strip()[:500]
    job.next_action_date = next_action_date.strip()[:80]
    job.notes = notes.strip()[:5000]
    if status == "Applied" and not job.applied_at:
        job.applied_at = datetime.now(timezone.utc)
    event_note = evidence_note.strip() or current_stage.strip() or next_action.strip() or f"{previous} → {status}"
    db.add(JobEvent(user_id=user.id, job_id=job.id, event_type=status, note=event_note[:5000]))
    record_audit(
        db,
        user=user,
        action="job_status_updated",
        object_type="job",
        object_id=job.id,
        details={"from": previous, "to": status},
    )
    mark_canonical_dirty(db, "job.status_updated", {"job_id": job.id, "status": status})
    db.commit()
    flash(request, "岗位进度已更新并保存。", "success")
    return RedirectResponse(url=f"/jobs/{job.id}#progress", status_code=303)


@router.post("/jobs/{job_id}/pack")
def edit_application_pack(
    job_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    why_role_draft: Annotated[str, Form()] = "",
    why_company_draft: Annotated[str, Form()] = "",
    work_authorization_answer: Annotated[str, Form()] = "",
    sponsorship_answer: Annotated[str, Form()] = "",
    salary_answer: Annotated[str, Form()] = "",
    user_reviewed: Annotated[str | None, Form()] = None,
):
    verify_csrf(request, csrf_token)
    job = _job_or_none(db, user.id, job_id)
    pack = db.scalar(
        select(ApplicationPack).where(ApplicationPack.job_id == job_id, ApplicationPack.user_id == user.id)
    )
    if not job or not pack:
        flash(request, "没有找到申请包。", "danger")
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    pack.why_role_draft = why_role_draft.strip()[:5000]
    pack.why_company_draft = why_company_draft.strip()[:5000]
    pack.work_authorization_answer = work_authorization_answer.strip()[:5000]
    pack.sponsorship_answer = sponsorship_answer.strip()[:5000]
    pack.salary_answer = salary_answer.strip()[:5000]
    pack.user_reviewed = bool(user_reviewed)
    mark_canonical_dirty(db, "application_pack.updated", {"job_id": job.id})
    db.commit()
    flash(request, "申请包已保存。", "success")
    return RedirectResponse(url=f"/jobs/{job.id}#application-pack", status_code=303)


@router.get("/jobs/{job_id}/application-pack.md")
def download_application_pack(
    job_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    job = _job_or_none(db, user.id, job_id)
    pack = db.scalar(
        select(ApplicationPack).where(ApplicationPack.job_id == job_id, ApplicationPack.user_id == user.id)
    )
    if not job or not pack:
        return PlainTextResponse("Application pack not found", status_code=404)
    resume = db.get(Resume, pack.resume_id) if pack.resume_id else None
    experiences: list[Experience] = []
    if pack.experience_ids:
        experiences = list(
            db.scalars(
                select(Experience).where(
                    Experience.user_id == user.id,
                    Experience.id.in_(pack.experience_ids),
                )
            )
        )
        order = {item_id: index for index, item_id in enumerate(pack.experience_ids)}
        experiences.sort(key=lambda item: order.get(item.id, 999))
    content = pack_as_markdown(job=job, pack=pack, resume=resume, experiences=experiences)
    filename = quote(f"{job.company}_{job.title}_application_pack.md".replace("/", "-"))
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/jobs/{job_id}/delete")
def delete_job(
    job_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    job = _job_or_none(db, user.id, job_id)
    if job:
        db.delete(job)
        record_audit(db, user=user, action="job_deleted", object_type="job", object_id=job_id)
        mark_canonical_dirty(db, "job.deleted", {"job_id": job_id})
        db.commit()
        flash(request, "岗位记录已删除。", "success")
    return RedirectResponse(url="/jobs", status_code=303)
