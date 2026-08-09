from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, verify_csrf
from app.db import get_db
from app.models import CandidateProfile, json_dumps
from app.services.audit import record_audit
from app.services.canonical import mark_canonical_dirty
from app.web import flash, render


router = APIRouter()


def _list_from_text(value: str) -> list[str]:
    items = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"[,;\n]+", value or "")]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result[:50]


def _nullable_bool(value: str) -> bool | None:
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def _profile_or_new(db: Session, user_id: int, email: str) -> CandidateProfile:
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
    if not profile:
        profile = CandidateProfile(user_id=user_id, email=email)
        db.add(profile)
        db.flush()
    return profile


@router.get("/onboarding")
def onboarding(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    profile = _profile_or_new(db, user.id, user.email)
    db.commit()
    return render(request, "profile_form.html", user=user, profile=profile, onboarding=True)


@router.get("/profile")
def profile_page(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    profile = _profile_or_new(db, user.id, user.email)
    db.commit()
    return render(request, "profile_form.html", user=user, profile=profile, onboarding=False)


@router.post("/profile")
def save_profile(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    preferred_name: Annotated[str, Form()] = "",
    legal_name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    current_location: Annotated[str, Form()] = "",
    linkedin_url: Annotated[str, Form()] = "",
    github_url: Annotated[str, Form()] = "",
    portfolio_url: Annotated[str, Form()] = "",
    current_status: Annotated[str, Form()] = "",
    degree_summary: Annotated[str, Form()] = "",
    graduation_year: Annotated[str, Form()] = "",
    professional_experience_years: Annotated[str, Form()] = "",
    work_authorization_country: Annotated[str, Form()] = "Australia",
    work_authorization_text: Annotated[str, Form()] = "",
    sponsorship_now: Annotated[str, Form()] = "unknown",
    sponsorship_future: Annotated[str, Form()] = "unknown",
    target_roles: Annotated[str, Form()] = "",
    secondary_roles: Annotated[str, Form()] = "",
    roles_to_avoid: Annotated[str, Form()] = "",
    industries_to_avoid: Annotated[str, Form()] = "",
    target_locations: Annotated[str, Form()] = "",
    work_mode: Annotated[str, Form()] = "Hybrid / Onsite / Remote",
    relocation_policy: Annotated[str, Form()] = "",
    target_level: Annotated[str, Form()] = "Graduate / Entry level",
    available_start_date: Annotated[str, Form()] = "",
    salary_strategy: Annotated[str, Form()] = "Prefer not to state; use confirmed range only when required.",
    salary_range: Annotated[str, Form()] = "",
    self_identification_strategy: Annotated[str, Form()] = "prefer_not_to_say",
    next_url: Annotated[str, Form()] = "/",
):
    verify_csrf(request, csrf_token)
    profile = _profile_or_new(db, user.id, user.email)

    experience_years: int | None = None
    if professional_experience_years.strip():
        try:
            experience_years = max(0, min(60, int(professional_experience_years)))
        except ValueError:
            return render(
                request,
                "profile_form.html",
                user=user,
                profile=profile,
                onboarding=not profile.onboarding_completed,
                status_code=400,
                error="工作经验年数必须是整数。",
            )

    profile.preferred_name = preferred_name.strip()[:120]
    profile.legal_name = legal_name.strip()[:120]
    profile.email = email.strip().lower()[:320]
    profile.phone = phone.strip()[:80]
    profile.current_location = current_location.strip()[:160]
    profile.linkedin_url = linkedin_url.strip()[:500]
    profile.github_url = github_url.strip()[:500]
    profile.portfolio_url = portfolio_url.strip()[:500]
    profile.current_status = current_status.strip()[:240]
    profile.degree_summary = degree_summary.strip()[:300]
    profile.graduation_year = graduation_year.strip()[:20]
    profile.professional_experience_years = experience_years
    profile.work_authorization_country = work_authorization_country.strip()[:120]
    profile.work_authorization_text = work_authorization_text.strip()[:5000]
    profile.sponsorship_now = _nullable_bool(sponsorship_now)
    profile.sponsorship_future = _nullable_bool(sponsorship_future)
    profile.target_roles_json = json_dumps(_list_from_text(target_roles))
    profile.secondary_roles_json = json_dumps(_list_from_text(secondary_roles))
    profile.roles_to_avoid_json = json_dumps(_list_from_text(roles_to_avoid))
    profile.industries_to_avoid_json = json_dumps(_list_from_text(industries_to_avoid))
    profile.target_locations_json = json_dumps(_list_from_text(target_locations))
    profile.work_mode = work_mode.strip()[:80]
    profile.relocation_policy = relocation_policy.strip()[:240]
    profile.target_level = target_level.strip()[:80]
    profile.available_start_date = available_start_date.strip()[:80]
    profile.salary_strategy = salary_strategy.strip()[:240]
    profile.salary_range = salary_range.strip()[:120]
    profile.self_identification_strategy = self_identification_strategy.strip()[:80]

    missing: list[str] = []
    if not profile.preferred_name:
        missing.append("常用姓名")
    if not profile.email:
        missing.append("邮箱")
    if not profile.current_location:
        missing.append("当前位置")
    if not profile.work_authorization_text:
        missing.append("工作权利原文")
    if profile.sponsorship_now is None or profile.sponsorship_future is None:
        missing.append("现在及未来的 Sponsorship 状态")
    if not profile.target_roles:
        missing.append("目标岗位")
    if not profile.target_locations:
        missing.append("目标地点")

    profile.onboarding_completed = not missing
    db.add(profile)
    record_audit(
        db,
        user=user,
        action="candidate_profile_updated",
        object_type="candidate_profile",
        object_id=profile.id,
        details={"onboarding_completed": profile.onboarding_completed, "missing": missing},
    )
    mark_canonical_dirty(db, "candidate_profile.updated", {"profile_id": profile.id})
    db.commit()

    if missing:
        flash(request, "资料已保存，但还缺少：" + "、".join(missing) + "。", "warning")
        return RedirectResponse(url="/onboarding", status_code=303)
    flash(request, "候选人资料已保存。", "success")
    destination = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"
    return RedirectResponse(url=destination, status_code=303)
