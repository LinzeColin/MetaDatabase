from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from app.models import CandidateProfile, Experience, Job, Resume
from app.services.skill_catalog import extract_skills, top_keywords


NO_SPONSORSHIP_PATTERNS = (
    r"no\s+(?:visa\s+)?sponsorship",
    r"sponsorship\s+(?:is\s+)?not\s+available",
    r"unable\s+to\s+sponsor",
    r"will\s+not\s+sponsor",
    r"not\s+provide\s+sponsorship",
)
WORK_RIGHT_RESTRICTION_PATTERNS = (
    r"unrestricted\s+(?:australian\s+)?work(?:ing)?\s+rights",
    r"must\s+have\s+(?:full|unrestricted)\s+work(?:ing)?\s+rights",
    r"australian\s+citizen(?:ship)?\s+or\s+permanent\s+resident",
    r"citizens?\s+and\s+permanent\s+residents?\s+only",
    r"permanent\s+work\s+rights",
)
SENIOR_TITLE_TERMS = {
    "senior", "lead", "principal", "director", "head", "vice president", "vp", "chief", "staff",
}
HIGH_EFFORT_SOURCES = {"Workday", "Oracle / Taleo"}
LOW_EFFORT_SOURCES = {"Greenhouse", "Lever", "Ashby"}


@dataclass
class AnalysisResult:
    recommendation: str
    fit_label: str
    eligibility_status: str
    freshness_status: str
    application_effort: str
    reasons: list[str]
    risks: list[str]
    unknowns: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    selected_resume_id: int | None
    selected_experience_ids: list[int]
    next_action: str
    internal_fit_points: int


@dataclass
class ApplicationDrafts:
    fit_summary: str
    why_role: str
    why_company: str
    work_authorization: str
    sponsorship: str
    salary: str
    checklist: list[str]


def analyse_job(
    *,
    profile: CandidateProfile,
    job: Job,
    resumes: Iterable[Resume],
    experiences: Iterable[Experience],
    today: date | None = None,
) -> AnalysisResult:
    current_date = today or datetime.now(timezone.utc).date()
    text = f"{job.title}\n{job.company}\n{job.location}\n{job.description}"
    lower = text.lower()
    title_lower = job.title.lower()

    reasons: list[str] = []
    risks: list[str] = []
    unknowns: list[str] = []
    hard_ineligible = False
    explicit_avoid = False
    fit_points = 0

    target_roles = [item.lower() for item in profile.target_roles + profile.secondary_roles if item.strip()]
    avoided_roles = [item.lower() for item in profile.roles_to_avoid if item.strip()]

    if any(_phrase_match(title_lower, role) for role in avoided_roles):
        explicit_avoid = True
        risks.append("职位名称命中了你的“必须跳过”规则。")

    role_matches = [role for role in target_roles if _role_match(title_lower, role)]
    if role_matches:
        fit_points += 4
        reasons.append(f"职位方向符合目标岗位：{', '.join(_display_role(r) for r in role_matches[:3])}。")
    elif target_roles:
        fit_points -= 1
        risks.append("职位名称没有直接命中你设置的主要或次要岗位方向。")
    else:
        unknowns.append("尚未设置目标岗位，无法判断岗位方向是否匹配。")

    if any(term in title_lower for term in SENIOR_TITLE_TERMS) and _is_early_career(profile.target_level):
        fit_points -= 4
        risks.append("职位名称显示为高级或管理层级，可能明显高于当前目标级别。")

    job_skills = extract_skills(text)
    resume_list = list(resumes)
    experience_list = list(experiences)
    selected_resume, resume_score, matched_skills = _select_resume(resume_list, job_skills, job.title)
    missing_required = _missing_required_skills(job.description, selected_resume)

    if matched_skills:
        if len(matched_skills) >= 6:
            fit_points += 4
        elif len(matched_skills) >= 3:
            fit_points += 3
        else:
            fit_points += 1
        reasons.append("简历中已找到相关能力：" + "、".join(matched_skills[:8]) + "。")
    elif job_skills:
        fit_points -= 2
        risks.append("职位列出的技能与现有简历之间没有明显交集。")
    else:
        unknowns.append("岗位正文没有提取到明确技能词，匹配判断主要依赖职位方向和资格条件。")

    if missing_required:
        fit_points -= min(4, len(missing_required))
        risks.append("职位的明确要求中未在所选简历找到：" + "、".join(missing_required[:6]) + "。")

    no_sponsorship = any(re.search(pattern, lower) for pattern in NO_SPONSORSHIP_PATTERNS)
    restricted_rights = any(re.search(pattern, lower) for pattern in WORK_RIGHT_RESTRICTION_PATTERNS)
    auth_text = profile.work_authorization_text.lower().strip()
    auth_is_unrestricted = any(
        phrase in auth_text
        for phrase in (
            "unrestricted", "permanent resident", "citizen", "full working rights", "full work rights",
            "no sponsorship required", "不限工时", "永久居民", "公民",
        )
    )

    if no_sponsorship:
        if profile.sponsorship_now is True or profile.sponsorship_future is True:
            hard_ineligible = True
            risks.append("岗位明确不提供 Sponsorship，而你的档案显示现在或未来需要 Sponsorship。")
        elif profile.sponsorship_now is None or profile.sponsorship_future is None:
            unknowns.append("岗位不提供 Sponsorship，但你的 Sponsorship 状态尚未完整确认。")
        else:
            reasons.append("岗位不提供 Sponsorship；你的档案显示现在和未来均不需要。")

    if restricted_rights:
        if auth_is_unrestricted:
            reasons.append("岗位要求完整或永久工作权利；你的档案中已有相符表述。")
        elif profile.sponsorship_now is True:
            hard_ineligible = True
            risks.append("岗位要求完整或永久工作权利，而你的档案显示当前需要 Sponsorship。")
        else:
            unknowns.append("岗位限制工作权利，需要你确认自己的身份是否完全符合原文。")

    graduation_years = sorted(set(re.findall(r"\b20(?:2[4-9]|3[0-5])\b", lower)))
    if _contains_graduate_cycle(lower) and graduation_years:
        if profile.graduation_year:
            if profile.graduation_year in graduation_years:
                reasons.append(f"岗位毕业年份范围包含你的毕业年份 {profile.graduation_year}。")
                fit_points += 1
            else:
                risks.append(
                    f"岗位提到毕业年份 {', '.join(graduation_years)}，与你填写的 {profile.graduation_year} 不一致。"
                )
                hard_ineligible = True
        else:
            unknowns.append("岗位限定毕业年份，但你的档案尚未填写毕业年份。")

    required_years = _extract_required_years(job.description)
    if required_years is not None:
        if profile.professional_experience_years is None:
            unknowns.append(f"岗位要求约 {required_years}+ 年经验，但你的档案尚未填写可核验的经验年数。")
        elif profile.professional_experience_years >= required_years:
            reasons.append(f"你的经验年数满足岗位约 {required_years}+ 年的要求。")
            fit_points += 1
        else:
            delta = required_years - profile.professional_experience_years
            if delta >= 3:
                hard_ineligible = True
            risks.append(
                f"岗位要求约 {required_years}+ 年经验，你填写的是 {profile.professional_experience_years} 年。"
            )
            fit_points -= min(4, delta)

    location_fit = _analyse_location(profile, job.location, lower)
    if location_fit == "match":
        reasons.append("岗位地点或工作模式符合你的偏好。")
        fit_points += 1
    elif location_fit == "mismatch":
        risks.append("岗位地点或现场要求与当前偏好不一致。")
        fit_points -= 2
    elif location_fit == "unknown":
        unknowns.append("岗位地点或远程政策不够明确，需要人工确认。")

    freshness = _freshness(job.posted_date, current_date)
    if freshness == "Fresh":
        reasons.append("岗位发布时间较新，适合尽快处理。")
        fit_points += 1
    elif freshness == "Old":
        risks.append("岗位发布时间较早，提交前应再次确认仍开放。")
    elif freshness == "Unknown":
        unknowns.append("无法确认发布时间，提交前应检查官方页面仍开放。")

    effort = _application_effort(job.source, job.description)
    if effort == "Low":
        reasons.append("申请路径预计较短。")
    elif effort == "High":
        risks.append("申请路径预计较长，需先判断是否值得投入。")

    selected_experiences = _select_experiences(experience_list, job_skills, top_keywords(text, 20))
    if selected_experiences:
        reasons.append(
            "建议重点使用经历：" + "、".join(item.title for item in selected_experiences[:4]) + "。"
        )
    else:
        unknowns.append("经历库为空或没有明显匹配项；生成申请包前应补充真实经历。")

    eligibility = "Eligible"
    if hard_ineligible or explicit_avoid:
        eligibility = "Ineligible"
    elif unknowns:
        eligibility = "Needs confirmation"

    fit_label = _fit_label(fit_points)
    if hard_ineligible or explicit_avoid:
        recommendation = "Skip"
        next_action = "查看阻断原因；仅在事实被更正后重新分析。"
    elif _has_high_impact_unknown(unknowns):
        recommendation = "Needs user"
        next_action = "先确认工作权利、Sponsorship、毕业年份或经验年数等高影响事实。"
    elif fit_label in {"High", "Medium"}:
        recommendation = "Apply" if effort != "High" or fit_label == "High" else "Review"
        next_action = "生成并复核申请包，然后到官方页面手动提交。"
    elif fit_label == "Stretch":
        recommendation = "Review"
        next_action = "确认缺口是否可接受，再决定是否投入定制材料。"
    else:
        recommendation = "Skip"
        next_action = "记录跳过原因，把时间投入更匹配的岗位。"

    return AnalysisResult(
        recommendation=recommendation,
        fit_label=fit_label,
        eligibility_status=eligibility,
        freshness_status=freshness,
        application_effort=effort,
        reasons=_dedupe(reasons)[:8],
        risks=_dedupe(risks)[:8],
        unknowns=_dedupe(unknowns)[:8],
        matched_skills=matched_skills[:20],
        missing_skills=missing_required[:20],
        selected_resume_id=selected_resume.id if selected_resume else None,
        selected_experience_ids=[item.id for item in selected_experiences[:4]],
        next_action=next_action,
        internal_fit_points=fit_points,
    )


def build_application_drafts(
    *,
    profile: CandidateProfile,
    job: Job,
    result: AnalysisResult,
    selected_experiences: list[Experience],
) -> ApplicationDrafts:
    experience_names = [item.title for item in selected_experiences[:3]]
    skill_names = result.matched_skills[:4]
    themes = top_keywords(job.description, 8)

    experience_phrase = _english_join(experience_names) or "my academic, project and work experience"
    skill_phrase = _english_join(skill_names) or "analysis, communication and problem solving"
    theme_phrase = _english_join(themes[:3]) or "the responsibilities described in the posting"

    why_role = (
        f"I am interested in the {job.title} role at {job.company} because it combines {theme_phrase}. "
        f"Through {experience_phrase}, I have developed practical capability in {skill_phrase}. "
        "I would welcome the opportunity to apply these strengths while continuing to learn in the role."
    )
    why_company = (
        f"Based on the published role description, I am particularly interested in {job.company}'s focus on "
        f"{theme_phrase}. The opportunity aligns with the type of work I am targeting and with the evidence "
        "in my current application materials. I would review this draft against the company's official website "
        "before submitting it."
    )

    work_authorization = profile.work_authorization_text.strip() or (
        "Not yet confirmed. Do not submit an answer until the candidate confirms the exact wording."
    )
    if profile.sponsorship_now is None or profile.sponsorship_future is None:
        sponsorship = "Not yet confirmed. Ask the candidate before answering."
    elif profile.sponsorship_now or profile.sponsorship_future:
        now = "now" if profile.sponsorship_now else "not now"
        future = "in the future" if profile.sponsorship_future else "not in the future"
        sponsorship = f"The candidate requires sponsorship {now} and {future}. Review the exact form wording."
    else:
        sponsorship = "The candidate does not require employer sponsorship now or in the future."

    salary = profile.salary_strategy.strip()
    if profile.salary_range:
        salary += f" Confirmed range: {profile.salary_range}."

    fit_summary = (
        f"Recommendation: {result.recommendation}. Fit: {result.fit_label}. "
        f"Eligibility: {result.eligibility_status}. "
        + ("Strongest evidence: " + ", ".join(skill_names) + "." if skill_names else "")
    )

    checklist = [
        "Open the employer's official application page and confirm the role is still open.",
        "Attach the exact resume version shown in this application pack.",
        "Check that every claim is supported by the candidate profile, resume or experience bank.",
        "Reconfirm work-rights, sponsorship, compensation and identity questions before answering.",
        "Do not bypass CAPTCHA, login, two-factor authentication or anti-bot controls.",
        "After submitting, return to JobHuntBot Online and record visible confirmation evidence.",
    ]
    if result.unknowns:
        checklist.insert(0, "Resolve all items under ‘Needs confirmation’ before submitting.")

    return ApplicationDrafts(
        fit_summary=fit_summary,
        why_role=why_role,
        why_company=why_company,
        work_authorization=work_authorization,
        sponsorship=sponsorship,
        salary=salary,
        checklist=checklist,
    )


def _select_resume(
    resumes: list[Resume], job_skills: list[str], job_title: str
) -> tuple[Resume | None, int, list[str]]:
    best: Resume | None = None
    best_score = -10_000
    best_matches: list[str] = []
    title_lower = job_title.lower()
    for resume in resumes:
        skills = set(resume.skills or extract_skills(resume.extracted_text))
        matches = [skill for skill in job_skills if skill in skills]
        score = len(matches) * 2
        role_family = resume.role_family.lower().strip()
        if role_family and role_family != "general" and _role_match(title_lower, role_family):
            score += 5
        if resume.is_default:
            score += 1
        if score > best_score:
            best = resume
            best_score = score
            best_matches = matches
    return best, best_score, best_matches


def _missing_required_skills(description: str, resume: Resume | None) -> list[str]:
    if not resume:
        return extract_skills(description)[:8]
    resume_skills = set(resume.skills or extract_skills(resume.extracted_text))
    required_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", description):
        lower = sentence.lower()
        if any(term in lower for term in ("required", "must have", "essential", "minimum", "you will need")):
            required_sentences.append(sentence)
    required = extract_skills("\n".join(required_sentences))
    return [skill for skill in required if skill not in resume_skills]


def _select_experiences(
    experiences: list[Experience], job_skills: list[str], keywords: list[str]
) -> list[Experience]:
    scored: list[tuple[int, int, Experience]] = []
    skill_set = {skill.lower() for skill in job_skills}
    keyword_set = {word.lower() for word in keywords}
    for item in experiences:
        text = f"{item.title} {item.organization} {item.description} {' '.join(item.tags)}".lower()
        item_skills = {skill.lower() for skill in (item.tags or extract_skills(text))}
        score = len(skill_set & item_skills) * 5
        score += sum(1 for word in keyword_set if word in text)
        if item.category == "experience":
            score += 1
        scored.append((score, -item.id, item))
    scored.sort(reverse=True, key=lambda row: (row[0], row[1]))
    positive = [item for score, _, item in scored if score > 0]
    return (positive or [item for _, _, item in scored])[:4]


def _analyse_location(profile: CandidateProfile, location: str, description_lower: str) -> str:
    targets = [item.lower() for item in profile.target_locations if item.strip()]
    loc = location.lower().strip()
    remote_allowed = "remote" in description_lower or "work from home" in description_lower
    if remote_allowed and "remote" in profile.work_mode.lower():
        return "match"
    if loc and any(target in loc or loc in target for target in targets):
        return "match"
    if not loc:
        return "unknown"
    if targets and not any(target in loc or loc in target for target in targets):
        if "onsite" in description_lower or "on-site" in description_lower or "office" in description_lower:
            return "mismatch"
        return "unknown"
    return "unknown"


def _freshness(posted_date: str, today: date) -> str:
    if not posted_date:
        return "Unknown"
    parsed: date | None = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(posted_date[:10], fmt).date()
            break
        except ValueError:
            continue
    if not parsed:
        return "Unknown"
    age = (today - parsed).days
    if age < 0:
        return "Unknown"
    if age <= 2:
        return "Fresh"
    if age <= 14:
        return "Recent"
    if age <= 30:
        return "Aging"
    return "Old"


def _application_effort(source: str, description: str) -> str:
    lower = description.lower()
    if source in HIGH_EFFORT_SOURCES:
        return "High"
    if any(term in lower for term in ("video application", "case study", "writing sample", "assessment centre")):
        return "High"
    if source in LOW_EFFORT_SOURCES:
        return "Low"
    if len(description) > 15_000:
        return "Medium"
    return "Medium"


def _fit_label(points: int) -> str:
    if points >= 7:
        return "High"
    if points >= 3:
        return "Medium"
    if points >= 0:
        return "Stretch"
    return "Low"


def _extract_required_years(text: str) -> int | None:
    patterns = (
        r"(?:minimum|min\.?|at least)\s+(\d{1,2})\+?\s+years?",
        r"(\d{1,2})\+\s+years?\s+(?:of\s+)?(?:relevant\s+)?experience",
        r"(?:requires?|seeking)\s+(\d{1,2})\+?\s+years?",
    )
    lower = text.lower()
    values: list[int] = []
    for pattern in patterns:
        values.extend(int(match) for match in re.findall(pattern, lower))
    return max(values) if values else None


def _contains_graduate_cycle(text: str) -> bool:
    return any(term in text for term in ("graduate program", "graduate programme", "campus recruitment", "graduating in"))


def _is_early_career(target_level: str) -> bool:
    lower = target_level.lower()
    return any(term in lower for term in ("graduate", "entry", "intern", "junior", "early"))


def _has_high_impact_unknown(unknowns: list[str]) -> bool:
    joined = " ".join(unknowns).lower()
    return any(
        term in joined
        for term in ("work", "sponsorship", "毕业年份", "经验年数", "工作权利", "身份")
    )


def _phrase_match(text: str, phrase: str) -> bool:
    normalized = re.sub(r"\s+", " ", phrase.strip().lower())
    return bool(normalized and normalized in text)


def _role_match(title: str, role: str) -> bool:
    role_words = [word for word in re.findall(r"[a-z0-9]+", role.lower()) if len(word) > 2]
    if not role_words:
        return False
    return all(word in title for word in role_words) or role.lower() in title


def _display_role(role: str) -> str:
    return " ".join(word.capitalize() for word in role.split())


def _english_join(values: list[str]) -> str:
    clean = [value.strip() for value in values if value.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return ", ".join(clean[:-1]) + f", and {clean[-1]}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result
