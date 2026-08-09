from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.db import get_db
from app.models import CandidateProfile, Experience, Job, Resume
from app.services.ai_provider import provider_view
from app.services.canonical import read_sync_status
from app.web import render


router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    if not profile or not profile.onboarding_completed:
        return RedirectResponse(url="/onboarding", status_code=303)

    counts = {
        row[0]: row[1]
        for row in db.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.user_id == user.id)
            .group_by(Job.status)
        ).all()
    }
    recent_jobs = list(
        db.scalars(
            select(Job)
            .where(Job.user_id == user.id)
            .order_by(Job.updated_at.desc())
            .limit(8)
        )
    )
    resume_count = db.scalar(select(func.count(Resume.id)).where(Resume.user_id == user.id)) or 0
    experience_count = db.scalar(select(func.count(Experience.id)).where(Experience.user_id == user.id)) or 0
    action_jobs = list(
        db.scalars(
            select(Job)
            .where(
                Job.user_id == user.id,
                Job.status.in_(["Needs review", "Needs user", "Ready", "Interview"]),
            )
            .order_by(Job.updated_at.desc())
            .limit(6)
        )
    )
    return render(
        request,
        "dashboard.html",
        user=user,
        profile=profile,
        counts=counts,
        recent_jobs=recent_jobs,
        action_jobs=action_jobs,
        resume_count=resume_count,
        experience_count=experience_count,
        ai_provider=provider_view(db, user.id),
        sync_status=read_sync_status(),
    )
