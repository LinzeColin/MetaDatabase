from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


LEVEL_POINTS = {"high": 3, "medium": 2, "low": 1}
QUAL_POINTS = {"pass": 3, "pending": 2, "fail": 0}


def _tokens(value: str | list[str]) -> set[str]:
    if isinstance(value, list):
        value = " ".join(value)
    return {x.casefold() for x in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}", value or "")}


def score_job(profile: dict[str, Any], job: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    reasons: list[str] = []
    hard_fail: list[str] = []
    pending: list[str] = []

    description = (job.get("title", "") + " " + job.get("description", "")).casefold()
    location = (job.get("location", "") + " " + job.get("city", "")).casefold()
    avoid_roles = [x.casefold() for x in profile.get("avoid_roles", [])]
    avoid_industries = [x.casefold() for x in profile.get("avoid_industries", [])]
    if any(x and x in description for x in avoid_roles):
        hard_fail.append("职位属于你明确不接受的岗位")
    if any(x and x in (job.get("industry", "") or "").casefold() for x in avoid_industries):
        hard_fail.append("职位属于你明确不接受的行业")

    target_locations = [x.casefold() for x in profile.get("target_locations", [])]
    work_mode = (job.get("work_mode") or "").casefold()
    if target_locations and not any(x in location for x in target_locations):
        if work_mode == "remote" and any("remote" in x for x in target_locations):
            reasons.append("远程模式符合地点偏好")
        else:
            pending.append("地点是否可接受需要确认")

    sponsorship_now = str(profile.get("sponsorship_now", "")).casefold()
    sponsorship_future = str(profile.get("sponsorship_future", "")).casefold()
    if "no sponsorship" in description or "not sponsor" in description:
        if sponsorship_now in {"yes", "true", "需要", "是"} or sponsorship_future in {"yes", "true", "需要", "是"}:
            hard_fail.append("岗位明确不提供 Sponsorship")
        elif not sponsorship_now or not sponsorship_future:
            pending.append("Sponsorship 情况尚未确认")
    if not profile.get("work_authorization"):
        pending.append("工作权利尚未确认")

    qualification = "fail" if hard_fail else ("pending" if pending else "pass")

    candidate_tokens = _tokens(profile.get("skills", [])) | _tokens(profile.get("keywords", []))
    role_tokens = _tokens(profile.get("primary_role_families", [])) | _tokens(profile.get("secondary_role_families", []))
    job_tokens = _tokens(job.get("skills", [])) | _tokens(job.get("keywords", [])) | _tokens(job.get("title", ""))
    overlap = candidate_tokens & job_tokens
    role_match = role_tokens & _tokens(job.get("role_family", "") + " " + job.get("title", ""))
    rel_score = min(100, len(overlap) * 12 + len(role_match) * 24)
    if role_match:
        reasons.append("岗位族与目标方向一致")
    if overlap:
        reasons.append("匹配技能：" + "、".join(sorted(overlap)[:6]))
    relevance = "high" if rel_score >= 55 else ("medium" if rel_score >= 25 else "low")

    posted_at = job.get("posted_at")
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            posted_at = None
    age_days = max(0, (now - posted_at).days) if posted_at else 30
    opportunity_score = 70
    if age_days <= 1:
        opportunity_score += 15
        reasons.append("岗位在 24 小时内发布")
    elif age_days <= 7:
        opportunity_score += 8
        reasons.append("岗位在最近 7 天发布")
    elif age_days > 30:
        opportunity_score -= 25
    if qualification == "fail":
        opportunity_score = 0
    elif qualification == "pending":
        opportunity_score -= 10
    if relevance == "high":
        opportunity_score += 10
    elif relevance == "low":
        opportunity_score -= 20
    opportunity = "high" if opportunity_score >= 75 else ("medium" if opportunity_score >= 45 else "low")

    rank = QUAL_POINTS[qualification] * 100 + LEVEL_POINTS[relevance] * 30 + LEVEL_POINTS[opportunity] * 20 - min(age_days, 60)
    reasons.extend(hard_fail or pending)
    return {
        "qualification": qualification,
        "relevance": relevance,
        "opportunity": opportunity,
        "rank_score": rank,
        "reasons": reasons[:10] or ["岗位信息不足，建议打开详情核对"],
    }
