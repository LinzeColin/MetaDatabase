from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


LEVEL_POINTS = {"high": 3, "medium": 2, "low": 1}
QUAL_POINTS = {"pass": 3, "pending": 2, "fail": 0}
NO_SPONSORSHIP_NEEDED = {"no", "false", "不需要", "否"}
SPONSORSHIP_NEEDED = {"yes", "true", "需要", "是"}
UNCONFIRMED_FACT_VALUES = {"uncertain", "unknown", "unsure", "not sure", "不确定", "待确认"}

# A small deterministic role vocabulary is deliberately shared by scoring,
# search and source targeting. It is not an AI classification and does not
# invent a candidate's preference: it only makes a confirmed Chinese or
# English role label comparable with the public job vocabulary.
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "Finance": ("finance", "financial", "accounting", "valuation", "investment", "banking", "财务", "金融", "会计", "投资", "估值"),
    "Data": ("data", "analytics", "sql", "python", "business intelligence", "数据", "数据分析", "商业智能"),
    "Business Analysis": ("business analyst", "business analysis", "requirements", "stakeholder", "业务分析", "需求分析"),
    "Operations": ("operations", "supply chain", "process", "project coordinator", "运营", "供应链", "流程"),
    "Risk": ("risk", "audit", "controls", "风险", "审计", "内控"),
    "Consulting": ("consultant", "consulting", "strategy", "咨询", "战略"),
    "Legal": ("legal", "law", "lawyer", "attorney", "counsel", "paralegal", "solicitor", "contract law", "法律", "法务", "律师", "法律顾问", "合同法"),
}

# Jobicy documents this public keyword parameter. One targeted query replaces
# its generic query for a profile, so it does not multiply the 6-hour source
# cadence or its provider-operation budget.
ROLE_SEARCH_TAGS = {
    "Finance": "finance",
    "Data": "data",
    "Business Analysis": "business analyst",
    "Operations": "operations",
    "Risk": "risk",
    "Consulting": "consulting",
    "Legal": "legal",
}


def _tokens(value: str | list[str]) -> set[str]:
    if isinstance(value, list):
        value = " ".join(value)
    return {
        x.casefold()
        for x in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}|[\u4e00-\u9fff]+", value or "")
    }


def _text(value: str | list[str]) -> str:
    return " ".join(value) if isinstance(value, list) else str(value or "")


def _has_alias(text: str, alias: str) -> bool:
    if any("\u4e00" <= char <= "\u9fff" for char in alias):
        return alias in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text))


def role_categories(value: str | list[str]) -> set[str]:
    """Return known role categories explicitly evidenced by the text."""
    text = _text(value).casefold()
    return {
        category
        for category, aliases in ROLE_ALIASES.items()
        if any(_has_alias(text, alias) for alias in aliases)
    }


def role_search_tag(profile: dict[str, Any]) -> str:
    """Choose one documented provider search tag from confirmed role intent."""
    primary = profile.get("primary_role_families", [])
    for category in ROLE_ALIASES:
        if category in role_categories(primary):
            return ROLE_SEARCH_TAGS[category]
    return ""


def search_matches(query: str, haystack: str) -> bool:
    """Match literal text first, then role aliases such as 法律 <-> legal."""
    needle = query.casefold().strip()
    text = haystack.casefold()
    if not needle:
        return True
    if needle in text:
        return True
    for category in role_categories(needle):
        if any(_has_alias(text, alias) for alias in ROLE_ALIASES[category]):
            return True
    return False


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

    sponsorship_now = str(profile.get("sponsorship_now", "")).strip().casefold()
    sponsorship_future = str(profile.get("sponsorship_future", "")).strip().casefold()
    if "no sponsorship" in description or "not sponsor" in description:
        if sponsorship_now in SPONSORSHIP_NEEDED or sponsorship_future in SPONSORSHIP_NEEDED:
            hard_fail.append("岗位明确不提供 Sponsorship")
        elif sponsorship_now not in NO_SPONSORSHIP_NEEDED or sponsorship_future not in NO_SPONSORSHIP_NEEDED:
            pending.append("Sponsorship 情况尚未确认")
    authorization = str(profile.get("work_authorization", "")).strip().casefold()
    if not authorization or authorization in UNCONFIRMED_FACT_VALUES:
        pending.append("工作权利尚未确认")

    accepted_modes = {str(mode).strip().casefold() for mode in profile.get("work_mode", []) if str(mode).strip()}
    job_mode = str(job.get("work_mode", "")).strip().casefold()
    if accepted_modes and job_mode and job_mode not in accepted_modes:
        pending.append("工作模式不符合已确认偏好")

    qualification = "fail" if hard_fail else ("pending" if pending else "pass")

    candidate_tokens = _tokens(profile.get("skills", [])) | _tokens(profile.get("keywords", []))
    profile_role_categories = role_categories(profile.get("primary_role_families", [])) | role_categories(profile.get("secondary_role_families", []))
    job_role_categories = role_categories(
        f"{job.get('role_family', '')} {job.get('title', '')} {job.get('description', '')}"
    )
    job_tokens = _tokens(job.get("skills", [])) | _tokens(job.get("keywords", [])) | _tokens(job.get("title", ""))
    overlap = candidate_tokens & job_tokens
    role_match = profile_role_categories & job_role_categories
    rel_score = min(100, len(overlap) * 12 + (60 if role_match else 0))
    if role_match:
        reasons.append("岗位族与目标方向一致：" + "、".join(sorted(role_match)))
    if overlap:
        reasons.append("匹配技能：" + "、".join(sorted(overlap)[:6]))
    # When a candidate has confirmed a known role direction, high relevance is
    # reserved for that direction. Generic transferable skills alone must not
    # make an engineering role a high-priority legal recommendation.
    if profile_role_categories:
        relevance = "high" if role_match else ("medium" if rel_score >= 25 else "low")
    else:
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
