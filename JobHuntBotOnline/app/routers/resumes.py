from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import CurrentUser, verify_csrf
from app.config import get_settings
from app.db import get_db
from app.models import CandidateProfile, Experience, Resume, json_dumps
from app.services.audit import record_audit
from app.services.canonical import mark_canonical_dirty
from app.services.resume_parser import ResumeParseError, parse_resume
from app.services.security import decrypt_from_file, encrypt_to_file, encrypted_upload_path, sanitize_filename
from app.web import flash, render


router = APIRouter()
settings = get_settings()


@router.get("/resumes")
def resume_page(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    resumes = list(
        db.scalars(select(Resume).where(Resume.user_id == user.id).order_by(Resume.is_default.desc(), Resume.created_at.desc()))
    )
    experiences = list(
        db.scalars(select(Experience).where(Experience.user_id == user.id).order_by(Experience.category, Experience.id))
    )
    return render(request, "resumes.html", user=user, resumes=resumes, experiences=experiences)


@router.post("/resumes/upload")
async def upload_resume(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    label: Annotated[str, Form()],
    role_family: Annotated[str, Form()] = "General",
    is_default: Annotated[str | None, Form()] = None,
    auto_import_experiences: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
):
    verify_csrf(request, csrf_token)
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        flash(request, "文件超过 10 MB，未上传。", "danger")
        return RedirectResponse(url="/resumes", status_code=303)

    filename = sanitize_filename(file.filename or "resume")
    try:
        parsed = parse_resume(filename, raw)
    except ResumeParseError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(url="/resumes", status_code=303)

    if is_default:
        db.execute(update(Resume).where(Resume.user_id == user.id).values(is_default=False))
    existing_count = len(list(db.scalars(select(Resume.id).where(Resume.user_id == user.id))))
    destination = encrypted_upload_path(filename)
    if settings.original_file_retention:
        encrypt_to_file(raw, destination)
    else:
        destination = Path("")

    resume = Resume(
        user_id=user.id,
        label=label.strip()[:160] or filename,
        role_family=role_family.strip()[:160] or "General",
        source_filename=filename,
        file_type=parsed.file_type,
        encrypted_file_path=str(destination) if destination else "",
        extracted_text=parsed.text,
        skills_json=json_dumps(parsed.skills),
        is_default=bool(is_default) or existing_count == 0,
    )
    db.add(resume)
    db.flush()

    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    if profile:
        for field, value in parsed.profile_hints.items():
            if hasattr(profile, field) and not getattr(profile, field):
                setattr(profile, field, value)
        db.add(profile)

    imported = 0
    if auto_import_experiences:
        existing_titles = {
            item.lower()
            for item in db.scalars(select(Experience.title).where(Experience.user_id == user.id))
        }
        for item in parsed.experiences:
            title = str(item.get("title", "")).strip()
            if not title or title.lower() in existing_titles:
                continue
            db.add(
                Experience(
                    user_id=user.id,
                    resume_id=resume.id,
                    category=str(item.get("category", "experience"))[:40],
                    title=title[:240],
                    organization=str(item.get("organization", ""))[:240],
                    date_range=str(item.get("date_range", ""))[:120],
                    description=str(item.get("description", ""))[:5000],
                    tags_json=json_dumps(item.get("tags", [])),
                    source_ref=filename,
                )
            )
            imported += 1
            existing_titles.add(title.lower())

    record_audit(
        db,
        user=user,
        action="resume_uploaded",
        object_type="resume",
        object_id=resume.id,
        details={"filename": filename, "skills_found": len(parsed.skills), "experiences_imported": imported},
    )
    mark_canonical_dirty(db, "resume.created", {"resume_id": resume.id})
    db.commit()
    flash(request, f"简历已读取；识别到 {len(parsed.skills)} 项能力，导入 {imported} 段经历。", "success")
    return RedirectResponse(url="/resumes", status_code=303)


@router.get("/resumes/{resume_id}/download")
def download_resume(
    resume_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    if not resume or not resume.encrypted_file_path:
        flash(request, "原始文件未保留或不存在。", "warning")
        return RedirectResponse(url="/resumes", status_code=303)
    try:
        content = decrypt_from_file(Path(resume.encrypted_file_path))
    except ValueError:
        flash(request, "原始简历无法读取，请检查部署密钥或从备份恢复。", "danger")
        return RedirectResponse(url="/resumes", status_code=303)
    media_type = mimetypes.guess_type(resume.source_filename)[0] or "application/octet-stream"
    encoded = quote(resume.source_filename)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/resumes/{resume_id}/default")
def set_default_resume(
    resume_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    if not resume:
        flash(request, "没有找到该简历。", "danger")
        return RedirectResponse(url="/resumes", status_code=303)
    db.execute(update(Resume).where(Resume.user_id == user.id).values(is_default=False))
    resume.is_default = True
    mark_canonical_dirty(db, "resume.default_changed", {"resume_id": resume.id})
    db.commit()
    flash(request, "默认简历已更新。", "success")
    return RedirectResponse(url="/resumes", status_code=303)


@router.post("/resumes/{resume_id}/delete")
def delete_resume(
    resume_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    if not resume:
        flash(request, "没有找到该简历。", "danger")
        return RedirectResponse(url="/resumes", status_code=303)
    path = Path(resume.encrypted_file_path) if resume.encrypted_file_path else None
    db.delete(resume)
    record_audit(db, user=user, action="resume_deleted", object_type="resume", object_id=resume_id)
    mark_canonical_dirty(db, "resume.deleted", {"resume_id": resume_id})
    db.commit()
    if path:
        path.unlink(missing_ok=True)
    flash(request, "简历已删除。", "success")
    return RedirectResponse(url="/resumes", status_code=303)


@router.post("/experiences")
def create_experience(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    category: Annotated[str, Form()] = "experience",
    title: Annotated[str, Form()] = "",
    organization: Annotated[str, Form()] = "",
    date_range: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    if not title.strip() or not description.strip():
        flash(request, "经历名称和真实内容不能为空。", "danger")
        return RedirectResponse(url="/resumes#experience-bank", status_code=303)
    tag_list = [item.strip() for item in tags.replace("，", ",").split(",") if item.strip()]
    item = Experience(
        user_id=user.id,
        category=category[:40],
        title=title.strip()[:240],
        organization=organization.strip()[:240],
        date_range=date_range.strip()[:120],
        description=description.strip()[:5000],
        tags_json=json_dumps(tag_list[:50]),
        source_ref="user_confirmed",
    )
    db.add(item)
    db.flush()
    record_audit(db, user=user, action="experience_created", object_type="experience", object_id=item.id)
    mark_canonical_dirty(db, "experience.created", {"experience_id": item.id})
    db.commit()
    flash(request, "经历已加入事实库。", "success")
    return RedirectResponse(url="/resumes#experience-bank", status_code=303)


@router.post("/experiences/{experience_id}/edit")
def edit_experience(
    experience_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    category: Annotated[str, Form()] = "experience",
    title: Annotated[str, Form()] = "",
    organization: Annotated[str, Form()] = "",
    date_range: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    verify_csrf(request, csrf_token)
    item = db.scalar(
        select(Experience).where(Experience.id == experience_id, Experience.user_id == user.id)
    )
    if not item:
        flash(request, "没有找到该经历。", "danger")
        return RedirectResponse(url="/resumes#experience-bank", status_code=303)
    if not title.strip() or not description.strip():
        flash(request, "经历名称和真实内容不能为空。", "danger")
        return RedirectResponse(url="/resumes#experience-bank", status_code=303)
    item.category = category[:40]
    item.title = title.strip()[:240]
    item.organization = organization.strip()[:240]
    item.date_range = date_range.strip()[:120]
    item.description = description.strip()[:5000]
    item.tags_json = json_dumps([part.strip() for part in tags.replace("，", ",").split(",") if part.strip()][:50])
    item.source_ref = item.source_ref or "user_confirmed"
    mark_canonical_dirty(db, "experience.updated", {"experience_id": item.id})
    db.commit()
    flash(request, "经历已更新。", "success")
    return RedirectResponse(url="/resumes#experience-bank", status_code=303)


@router.post("/experiences/{experience_id}/delete")
def delete_experience(
    experience_id: int,
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    item = db.scalar(
        select(Experience).where(Experience.id == experience_id, Experience.user_id == user.id)
    )
    if item:
        db.delete(item)
        mark_canonical_dirty(db, "experience.deleted", {"experience_id": experience_id})
        db.commit()
        flash(request, "经历已删除。", "success")
    return RedirectResponse(url="/resumes#experience-bank", status_code=303)
