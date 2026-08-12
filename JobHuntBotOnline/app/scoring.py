from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .career_intelligence import (
    DOMAIN_ROLES,
    domain_for_role,
    extract_job_requirements,
    normalize_role,
    normalize_roles,
    qualification_checks,
    role_label,
)

LEVEL_POINTS = {"high": 3, "medium": 2, "low": 1}
QUAL_POINTS = {"pass": 4, "pending": 1, "fail": -20}


# Search is intentionally narrower than scoring.  It preserves the existing
# source-query behavior while allowing Chinese finance/legal terms to reach
# the corresponding public job vocabulary.
SEARCH_ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "Finance": ("finance", "financial", "财务", "金融", "金融分析"),
    "Accounting": ("accounting", "accountant", "audit", "会计", "审计"),
    "Investment": ("investment", "banking", "投资", "投行", "证券"),
    "Risk": ("risk", "风险", "风险管理"),
    "Legal": ("legal", "law", "lawyer", "solicitor", "counsel", "法务", "法律", "律师"),
    "Compliance": ("compliance", "aml", "kyc", "合规", "反洗钱"),
    "Contracts": ("contract", "contracts", "合同", "合同管理"),
    "Data": ("data", "analytics", "sql", "python", "数据", "数据分析"),
    "Business Analysis": ("business analyst", "business analysis", "requirements", "业务分析", "需求分析"),
    "Operations": ("operations", "supply chain", "process", "运营", "供应链", "流程"),
    "Consulting": ("consultant", "consulting", "strategy", "咨询", "战略"),
}
ROLE_SEARCH_TAGS = {
    "Finance": "finance",
    "Accounting": "accounting",
    "Investment": "investment",
    "Risk": "risk",
    "Legal": "legal",
    "Compliance": "compliance",
    "Contracts": "contract",
    "Data": "data",
    "Business Analysis": "business analyst",
    "Operations": "operations",
    "Consulting": "consulting",
}


def _role_values(value: str | list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [re.sub(r"\s+", " ", str(item)).strip() for item in values if str(item).strip()]


def _has_alias(text: str, alias: str) -> bool:
    if any("\u4e00" <= char <= "\u9fff" for char in alias):
        return alias in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text))


def role_categories(value: str | list[str]) -> set[str]:
    text = " ".join(_role_values(value)).casefold()
    return {
        category
        for category, aliases in SEARCH_ROLE_ALIASES.items()
        if any(_has_alias(text, alias) for alias in aliases)
    }


def role_search_tag(profile: dict[str, Any]) -> str:
    primary = _role_values(profile.get("primary_role_families", []))
    for category in ROLE_SEARCH_TAGS:
        if category in role_categories(primary):
            return ROLE_SEARCH_TAGS[category]
    return primary[0][:80] if primary else ""


def search_matches(query: str, haystack: str) -> bool:
    needle = query.casefold().strip()
    text = haystack.casefold()
    if not needle:
        return True
    if needle in text:
        return True
    for category in role_categories(needle):
        if any(_has_alias(text, alias) for alias in SEARCH_ROLE_ALIASES[category]):
            return True
    return False

def _tokens(value: str | list[str]) -> set[str]:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    text = value or ""
    latin = {x.casefold() for x in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}", text)}
    chinese = {x for x in re.findall(r"[\u4e00-\u9fff]{2,8}", text)}
    return latin | chinese


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _same_or_adjacent_domain(candidate_roles: list[str], job_role: str) -> tuple[bool, bool]:
    candidate = set(normalize_roles(candidate_roles))
    job_role = normalize_role(job_role)
    exact = job_role in candidate
    if exact:
        return True, True
    job_domain = domain_for_role(job_role)
    adjacent = bool(candidate & DOMAIN_ROLES.get(job_domain, set()))
    return False, adjacent


def _qualification_from_checks(checks: list[dict[str, str]], extra_hard: list[str], extra_pending: list[str]) -> str:
    statuses = [item["status"] for item in checks]
    if extra_hard or "fail" in statuses:
        return "fail"
    if extra_pending or "pending" in statuses:
        return "pending"
    return "pass"


def score_job(profile: dict[str, Any], job: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    reasons: list[str] = []
    hard_fail: list[str] = []
    pending: list[str] = []

    title = str(job.get("title") or "")
    description = str(job.get("description") or "")
    text = f"{title} {description}".casefold()
    location = f"{job.get('location', '')} {job.get('city', '')}".casefold()

    avoid_roles = [x.casefold() for x in _as_list(profile.get("avoid_roles"))]
    avoid_industries = [x.casefold() for x in _as_list(profile.get("avoid_industries"))]
    if any(x and x in text for x in avoid_roles):
        hard_fail.append("职位属于你明确不接受的岗位")
    industry = str(job.get("industry") or "").casefold()
    if any(x and x in industry for x in avoid_industries):
        hard_fail.append("职位属于你明确不接受的行业")

    target_locations = [x.casefold() for x in _as_list(profile.get("target_locations"))]
    work_mode = str(job.get("work_mode") or "").casefold()
    accepted_modes = {str(value).casefold() for value in _as_list(profile.get("work_mode"))}
    if accepted_modes and work_mode and work_mode not in accepted_modes:
        pending.append("工作模式不在你的已确认偏好内")
    if target_locations and not any(x in location for x in target_locations):
        if work_mode == "remote" and any("remote" in x or "远程" in x for x in target_locations):
            reasons.append("远程模式符合地点偏好")
        else:
            pending.append("地点是否可接受需要确认")

    raw_checks, requirements = qualification_checks(profile, job)
    checks = [item.to_dict() for item in raw_checks]
    qualification = _qualification_from_checks(checks, hard_fail, pending)

    candidate_roles = normalize_roles(
        _as_list(profile.get("primary_role_families")) + _as_list(profile.get("secondary_role_families"))
    )
    job_role = normalize_role(str(job.get("role_family") or requirements.get("role_family") or "Other"))
    exact_role, adjacent_domain = _same_or_adjacent_domain(candidate_roles, job_role)
    # Preserve a confirmed narrow role outside the compact finance/legal taxonomy.
    # It is an exact literal signal only; transferable skills cannot promote an
    # unrelated role (for example, engineering) to high relevance.
    job_role_text = f"{title} {description}"
    confirmed_custom_role = any(
        normalize_role(role) == role
        and role != "Other"
        and _has_alias(job_role_text.casefold(), role.casefold())
        for role in _as_list(profile.get("primary_role_families"))
    )
    if confirmed_custom_role:
        exact_role = True

    candidate_tokens = _tokens(_as_list(profile.get("skills"))) | _tokens(_as_list(profile.get("keywords")))
    job_tokens = (
        _tokens(_as_list(job.get("skills")))
        | _tokens(_as_list(job.get("keywords")))
        | _tokens(title)
        | _tokens(job_role)
    )
    overlap = candidate_tokens & job_tokens
    rel_score = min(100, len(overlap) * 10)
    if exact_role:
        rel_score += 50
        if confirmed_custom_role:
            reasons.append("岗位标题与你确认的目标方向一致")
        else:
            reasons.append(f"岗位方向与你确认的“{role_label(job_role)}”一致")
    elif adjacent_domain:
        rel_score += 28
        reasons.append("岗位属于你的相邻专业领域")
    elif job_role and job_role != "Other":
        rel_score -= 10
    if overlap:
        reasons.append("匹配技能／关键词：" + "、".join(sorted(overlap, key=str.casefold)[:7]))
    if requirements["domain"] in {"finance", "legal"} and domain_for_role(job_role) == requirements["domain"]:
        rel_score += 5
    rel_score = max(0, min(100, rel_score))
    relevance = "high" if rel_score >= 55 else ("medium" if rel_score >= 25 else "low")

    posted_at = job.get("posted_at")
    if isinstance(posted_at, str):
        try:
            posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            posted_at = None
    age_days = max(0, (now - posted_at).days) if isinstance(posted_at, datetime) else 30

    opportunity_score = 58
    if age_days <= 1:
        opportunity_score += 20
        reasons.append("岗位在 24 小时内发布")
    elif age_days <= 7:
        opportunity_score += 10
        reasons.append("岗位在最近 7 天发布")
    elif age_days <= 14:
        opportunity_score += 3
    elif age_days > 30:
        opportunity_score -= 25

    if qualification == "fail":
        opportunity_score = 0
    elif qualification == "pending":
        opportunity_score -= 18
    if relevance == "high":
        opportunity_score += 16
    elif relevance == "medium":
        opportunity_score += 2
    else:
        opportunity_score -= 22
    seniority = requirements.get("seniority")
    if seniority in {"director", "executive", "partner"} and qualification != "pass":
        opportunity_score = min(opportunity_score, 15)
    opportunity_score = max(0, min(100, opportunity_score))
    opportunity = "high" if opportunity_score >= 75 else ("medium" if opportunity_score >= 45 else "low")

    for item in checks:
        if item["status"] in {"fail", "pending"}:
            reasons.append(f"{item['label']}：{item['evidence']}")
    reasons.extend(hard_fail)
    reasons.extend(pending)

    # Fail items must never rank above a viable role, regardless of freshness.
    rank = (
        QUAL_POINTS[qualification] * 1000
        + LEVEL_POINTS[relevance] * 100
        + LEVEL_POINTS[opportunity] * 50
        + rel_score
        + opportunity_score
        - min(age_days, 90)
    )
    if qualification == "fail":
        rank -= 10000

    return {
        "qualification": qualification,
        "relevance": relevance,
        "opportunity": opportunity,
        "rank_score": int(rank),
        "reasons": reasons[:12] or ["岗位信息不足，建议打开详情核对"],
        "requirement_checks": checks,
        "requirements": requirements,
        "relevance_score": rel_score,
        "opportunity_score": opportunity_score,
        "domain": requirements.get("domain", "general"),
        "role_family": job_role,
        "age_days": age_days,
    }
