from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Iterable


ROLE_LABELS: dict[str, str] = {
    "Finance": "金融分析",
    "Accounting": "会计与审计",
    "Investment": "投资与银行",
    "Risk": "风险管理",
    "Legal": "法律",
    "Compliance": "合规",
    "Contracts": "合同与法务运营",
    "Data": "数据分析",
    "Business Analysis": "业务分析",
    "Operations": "运营与项目",
    "Consulting": "咨询",
    "Other": "其他",
}

ROLE_ALIASES: dict[str, str] = {
    "finance": "Finance",
    "financial": "Finance",
    "金融": "Finance",
    "金融分析": "Finance",
    "财务": "Finance",
    "accounting": "Accounting",
    "accountant": "Accounting",
    "会计": "Accounting",
    "会计与审计": "Accounting",
    "audit": "Accounting",
    "审计": "Accounting",
    "investment": "Investment",
    "banking": "Investment",
    "投资": "Investment",
    "投资与银行": "Investment",
    "risk": "Risk",
    "风险": "Risk",
    "风险管理": "Risk",
    "legal": "Legal",
    "law": "Legal",
    "lawyer": "Legal",
    "法律": "Legal",
    "法务": "Legal",
    "compliance": "Compliance",
    "合规": "Compliance",
    "contracts": "Contracts",
    "contract": "Contracts",
    "合同": "Contracts",
    "合同与法务运营": "Contracts",
    "data": "Data",
    "analytics": "Data",
    "数据": "Data",
    "数据分析": "Data",
    "business analysis": "Business Analysis",
    "业务分析": "Business Analysis",
    "operations": "Operations",
    "project": "Operations",
    "运营": "Operations",
    "运营与项目": "Operations",
    "consulting": "Consulting",
    "咨询": "Consulting",
    "other": "Other",
    "其他": "Other",
}

ROLE_RULES: dict[str, tuple[str, ...]] = {
    "Finance": (
        "financial analyst", "finance analyst", "fp&a", "commercial analyst", "treasury analyst",
        "finance business partner", "financial planning", "financial modelling", "financial modeling",
        "corporate finance", "credit analyst", "finance graduate", "财务", "金融分析",
    ),
    "Accounting": (
        "accountant", "accounting", "management accounting", "financial accounting", "audit",
        "tax analyst", "bookkeeper", "month end", "会计", "审计", "税务",
    ),
    "Investment": (
        "investment analyst", "equity research", "investment banking", "asset management",
        "portfolio analyst", "wealth management", "fund analyst", "投资", "投行", "证券",
    ),
    "Legal": (
        "lawyer", "solicitor", "legal counsel", "legal assistant", "paralegal", "law clerk",
        "graduate lawyer", "litigation", "legal research", "律师", "法律", "法务",
    ),
    "Compliance": (
        "compliance analyst", "regulatory compliance", "aml", "kyc", "financial crime",
        "risk and compliance", "合规", "反洗钱",
    ),
    "Contracts": (
        "contract administrator", "contracts manager", "contract specialist", "commercial contracts",
        "contract review", "contract drafting", "合同管理", "合同审核",
    ),
    "Risk": (
        "risk analyst", "operational risk", "credit risk", "market risk", "internal controls",
        "governance risk", "风险", "内控",
    ),
    "Data": (
        "data analyst", "analytics", "business intelligence", "sql", "python", "power bi",
        "tableau", "数据分析",
    ),
    "Business Analysis": (
        "business analyst", "business analysis", "requirements gathering", "process analyst",
        "业务分析",
    ),
    "Operations": (
        "operations", "project coordinator", "project officer", "supply chain", "process improvement",
        "运营", "项目协调",
    ),
    "Consulting": (
        "consultant", "consulting", "strategy analyst", "advisory", "咨询",
    ),
}

DOMAIN_ROLES: dict[str, set[str]] = {
    "finance": {"Finance", "Accounting", "Investment", "Risk"},
    "legal": {"Legal", "Compliance", "Contracts"},
    "general": {"Data", "Business Analysis", "Operations", "Consulting", "Other"},
}

DOMAIN_LABELS = {"finance": "金融", "legal": "法律", "general": "其他"}

SKILL_TERMS: tuple[str, ...] = (
    # 金融
    "excel", "financial modelling", "financial modeling", "valuation", "fp&a", "forecasting",
    "budgeting", "management accounting", "financial reporting", "ifrs", "month end", "treasury",
    "credit analysis", "audit", "tax", "accounting", "power bi", "sap", "xero", "myob",
    # 法律
    "legal research", "contract drafting", "contract review", "due diligence", "litigation",
    "case management", "legal writing", "westlaw", "lexisnexis", "corporate law", "commercial law",
    "employment law", "privacy law", "regulatory", "aml", "kyc", "legal operations",
    # 通用
    "sql", "python", "tableau", "data analysis", "business analysis", "project management",
    "stakeholder management", "research", "statistics", "salesforce", "communication",
)

CREDENTIAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "CPA": (r"\bCPA\b", r"certified public accountant"),
    "CA": (r"\bCA\s*ANZ\b", r"\bchartered accountant\b", r"\bCA\b"),
    "CFA": (r"\bCFA\b", r"chartered financial analyst"),
    "ACCA": (r"\bACCA\b",),
    "CIMA": (r"\bCIMA\b",),
    "RG146": (r"\bRG\s*146\b",),
    "LLB": (r"\bLL\.?B\.?\b", r"bachelor of laws?"),
    "JD": (r"\bJ\.?D\.?\b", r"juris doctor"),
    "PLT": (r"\bPLT\b", r"practical legal training", r"graduate diploma of legal practice", r"\bGDLP\b"),
    "澳大利亚律师准入": (
        r"admitted to (?:legal )?practice", r"admitted (?:as|in) (?:an? )?(?:australian )?(?:lawyer|solicitor)",
        r"australian legal practitioner", r"admitted lawyer", r"admission to practice",
    ),
    "澳大利亚执业证书": (
        r"practising certificate", r"practicing certificate", r"current australian practising certificate",
    ),
}

MANDATORY_WORDS = (
    "required", "essential", "mandatory", "must have", "must hold", "you will have",
    "you must", "minimum qualification", "qualified", "current", "admitted",
)

SENIORITY_LEVELS = {
    "intern": 0,
    "graduate": 1,
    "junior": 2,
    "associate": 3,
    "mid": 4,
    "senior": 5,
    "manager": 6,
    "director": 7,
    "executive": 8,
    "partner": 9,
}

SENIORITY_LABELS = {
    "intern": "实习",
    "graduate": "毕业生",
    "junior": "初级",
    "associate": "助理／中初级",
    "mid": "中级",
    "senior": "高级",
    "manager": "经理",
    "director": "总监",
    "executive": "高管",
    "partner": "合伙人",
    "unknown": "未说明",
}


@dataclass(frozen=True)
class RequirementCheck:
    key: str
    label: str
    status: str
    evidence: str
    source: str = "岗位正文"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_role(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if not cleaned:
        return ""
    return ROLE_ALIASES.get(cleaned.casefold(), cleaned if cleaned in ROLE_LABELS else cleaned)


def normalize_roles(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_role(str(value))
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def role_label(value: str) -> str:
    normalized = normalize_role(value)
    return ROLE_LABELS.get(normalized, value or ROLE_LABELS["Other"])


def domain_for_role(role: str, text: str = "") -> str:
    normalized = normalize_role(role)
    for domain, roles in DOMAIN_ROLES.items():
        if normalized in roles:
            return domain
    detected = detect_role_family(text)
    for domain, roles in DOMAIN_ROLES.items():
        if detected in roles:
            return domain
    return "general"


def domain_label(value: str) -> str:
    return DOMAIN_LABELS.get(value, "其他")


def detect_role_family(text: str) -> str:
    hay = (text or "").casefold()
    scores: dict[str, int] = {}
    for role, terms in ROLE_RULES.items():
        score = 0
        for term in terms:
            count = hay.count(term.casefold())
            if count:
                score += 3 if term.casefold() in hay[:300] else 1
                score += min(count, 3)
        scores[role] = score
    if not scores or max(scores.values(), default=0) <= 0:
        return "Other"
    return max(scores, key=lambda key: (scores[key], key))


def detect_skills(text: str) -> list[str]:
    hay = (text or "").casefold()
    return [term for term in SKILL_TERMS if term.casefold() in hay]


def detect_credentials(text: str) -> list[str]:
    found: list[str] = []
    for credential, patterns in CREDENTIAL_PATTERNS.items():
        if any(re.search(pattern, text or "", flags=re.I) for pattern in patterns):
            found.append(credential)
    return found


def estimate_experience_years(text: str) -> float | None:
    explicit: list[float] = []
    patterns = (
        r"(?:over|more than|at least|minimum of|min\.?\s*)?\s*(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+)?experience",
        r"(?:experience|experienced)\s+(?:of\s+)?(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)",
        r"(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)\s+in\s+(?:finance|accounting|law|legal|compliance|contracts|data|operations)",
    )
    for pattern in patterns:
        explicit.extend(float(value) for value in re.findall(pattern, text or "", flags=re.I))
    if explicit:
        return min(max(explicit), 50.0)

    # Conservative date-range inference. It is only used as a draft and is shown
    # to the user for confirmation before it can drive a hard decision.
    durations: list[int] = []
    current_year = 2026
    for start, end in re.findall(r"\b(20\d{2})\s*[-–—]\s*(20\d{2}|present|current|now)\b", text or "", flags=re.I):
        start_year = int(start)
        end_year = current_year if end.casefold() in {"present", "current", "now"} else int(end)
        if 0 <= end_year - start_year <= 30:
            durations.append(end_year - start_year)
    return float(max(durations)) if durations else None


def infer_professional_facts(text: str) -> dict[str, Any]:
    credentials = detect_credentials(text)
    lower = (text or "").casefold()
    admission = "admitted" if "澳大利亚律师准入" in credentials else "uncertain"
    certificate = "current" if "澳大利亚执业证书" in credentials and "current" in lower else (
        "held" if "澳大利亚执业证书" in credentials else "uncertain"
    )
    education_levels: list[str] = []
    if re.search(r"\b(?:bachelor|b\.?(?:com|bus|econ|laws?|sc)|ll\.?b)\b", lower):
        education_levels.append("本科")
    if re.search(r"\b(?:master|m\.?(?:com|fin|law|ba)|juris doctor|j\.?d)\b", lower):
        education_levels.append("硕士／JD")
    if re.search(r"\b(?:phd|doctor of philosophy)\b", lower):
        education_levels.append("博士")
    return {
        "experience_years": estimate_experience_years(text),
        "professional_credentials": credentials,
        "legal_admission": admission,
        "practising_certificate": certificate,
        "education_levels": education_levels,
    }


def detect_seniority(title: str, description: str = "") -> str:
    text = f"{title} {description[:1200]}".casefold()
    title_lower = (title or "").casefold()
    ordered = (
        ("partner", ("partner",)),
        ("executive", ("chief ", "general counsel", "vice president", " vp ", "cfo", "coo")),
        ("director", ("director", "head of")),
        ("manager", ("manager", "managing counsel")),
        ("senior", ("senior", "sr.", "sr ")),
        ("graduate", ("graduate", "new grad", "trainee solicitor")),
        ("intern", ("intern", "internship", "clerkship")),
        ("junior", ("junior", "entry level", "assistant", "paralegal")),
        ("associate", ("associate",)),
    )
    for level, terms in ordered:
        if any(term in title_lower for term in terms):
            return level
    if re.search(r"\b[3-5]\+?\s*years?\b", text):
        return "mid"
    return "unknown"


def extract_required_years(text: str) -> int | None:
    candidates: list[int] = []
    patterns = (
        r"(?:minimum(?: of)?|at least|no less than|more than|over|requires?|required)?\s*(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|post[- ]qualification\s+|professional\s+)?(?:[a-z-]+\s+){0,3}?experience",
        r"(?:experience|experienced)\s+(?:of\s+)?(?:at least\s+)?(\d{1,2})\+?\s*(?:years?|yrs?)",
        r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
    )
    for match in re.finditer(patterns[0], text or "", flags=re.I):
        candidates.append(int(match.group(1)))
    for match in re.finditer(patterns[1], text or "", flags=re.I):
        candidates.append(int(match.group(1)))
    for match in re.finditer(patterns[2], text or "", flags=re.I):
        candidates.append(int(match.group(1)))
    return max(candidates) if candidates else None


def _credential_is_mandatory(text: str, credential: str) -> bool:
    patterns = CREDENTIAL_PATTERNS[credential]
    lower = (text or "").casefold()
    for pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            start = max(0, match.start() - 90)
            end = min(len(text), match.end() + 90)
            window = text[start:end].casefold()
            if any(word in window for word in MANDATORY_WORDS):
                return True
    if credential in {"澳大利亚律师准入", "澳大利亚执业证书"}:
        return any(re.search(pattern, text or "", flags=re.I) for pattern in patterns)
    return False


def extract_job_requirements(job: dict[str, Any]) -> dict[str, Any]:
    title = str(job.get("title") or "")
    description = str(job.get("description") or "")
    text = f"{title}\n{description}"
    role = normalize_role(str(job.get("role_family") or "")) or detect_role_family(text)
    domain = domain_for_role(role, text)
    required_credentials = [
        credential for credential in CREDENTIAL_PATTERNS
        if _credential_is_mandatory(text, credential)
    ]
    lower = text.casefold()
    degree_required = bool(re.search(
        r"(?:bachelor(?:'s)?|degree|ll\.?b|juris doctor|j\.?d).{0,55}(?:required|essential|mandatory|must)|"
        r"(?:required|essential|mandatory|must).{0,55}(?:bachelor(?:'s)?|degree|ll\.?b|juris doctor|j\.?d)",
        lower,
    ))
    sponsorship_unavailable = any(phrase in lower for phrase in (
        "no sponsorship", "will not sponsor", "not able to sponsor", "unable to sponsor",
        "sponsorship is not available", "must have unrestricted work rights",
    ))
    full_work_rights_required = any(phrase in lower for phrase in (
        "full working rights", "unrestricted work rights", "citizen or permanent resident",
        "australian citizenship", "permanent residency required",
    ))
    credential_any_groups: list[list[str]] = []
    if re.search(r"\bCPA\b\s*(?:or|/)\s*\bCA(?:\s*ANZ)?\b|\bCA(?:\s*ANZ)?\b\s*(?:or|/)\s*\bCPA\b", text, flags=re.I):
        credential_any_groups.append(["CPA", "CA"])
    if re.search(r"\bLL\.?B\.?\b\s*(?:or|/)\s*(?:J\.?D\.?|Juris Doctor)|(?:J\.?D\.?|Juris Doctor)\s*(?:or|/)\s*\bLL\.?B\.?\b", text, flags=re.I):
        credential_any_groups.append(["LLB", "JD"])
    return {
        "role_family": role,
        "domain": domain,
        "seniority": detect_seniority(title, description),
        "required_years": extract_required_years(text),
        "required_credentials": required_credentials,
        "credential_any_groups": credential_any_groups,
        "degree_required": degree_required,
        "admission_required": "澳大利亚律师准入" in required_credentials,
        "practising_certificate_required": "澳大利亚执业证书" in required_credentials,
        "sponsorship_unavailable": sponsorship_unavailable,
        "full_work_rights_required": full_work_rights_required,
    }


def _profile_float(profile: dict[str, Any], key: str) -> float | None:
    raw = profile.get(key)
    if raw in (None, "", "unknown", "uncertain"):
        return None
    try:
        return max(0.0, min(float(raw), 60.0))
    except (TypeError, ValueError):
        return None


def _normalised_credentials(profile: dict[str, Any]) -> set[str]:
    values = profile.get("professional_credentials") or []
    if isinstance(values, str):
        values = re.split(r"[,，;；\n]", values)
    result: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        canonical = next((key for key, patterns in CREDENTIAL_PATTERNS.items() if any(re.search(p, text, re.I) for p in patterns)), text.upper())
        result.add(canonical)
    return result


def qualification_checks(profile: dict[str, Any], job: dict[str, Any]) -> tuple[list[RequirementCheck], dict[str, Any]]:
    req = extract_job_requirements(job)
    checks: list[RequirementCheck] = []
    candidate_years = _profile_float(profile, "experience_years")
    credentials = _normalised_credentials(profile)
    credentials_confirmed = bool(profile.get("credentials_confirmed"))

    required_years = req["required_years"]
    if required_years is not None:
        if candidate_years is None:
            checks.append(RequirementCheck(
                "experience_years", f"至少 {required_years} 年相关经验", "pending",
                "你的相关工作年限尚未确认。",
            ))
        elif candidate_years + 0.01 < required_years:
            checks.append(RequirementCheck(
                "experience_years", f"至少 {required_years} 年相关经验", "fail",
                f"已确认相关经验约 {candidate_years:g} 年，低于岗位明确要求。",
            ))
        else:
            checks.append(RequirementCheck(
                "experience_years", f"至少 {required_years} 年相关经验", "pass",
                f"已确认相关经验约 {candidate_years:g} 年。",
            ))
    elif req["seniority"] in {"director", "executive", "partner"}:
        floor = {"director": 8, "executive": 10, "partner": 8}[req["seniority"]]
        if candidate_years is None:
            checks.append(RequirementCheck(
                "seniority", f"{SENIORITY_LABELS[req['seniority']]}级岗位", "pending",
                "岗位级别较高，但你的相关经验年限尚未确认。",
            ))
        elif candidate_years < floor:
            checks.append(RequirementCheck(
                "seniority", f"{SENIORITY_LABELS[req['seniority']]}级岗位", "fail",
                f"已确认相关经验约 {candidate_years:g} 年，明显低于该级别通常要求；请以岗位正文为准。",
            ))

    if req["admission_required"]:
        status = str(profile.get("legal_admission") or "uncertain")
        if status == "admitted":
            checks.append(RequirementCheck("legal_admission", "澳大利亚律师准入", "pass", "你已确认具备律师准入资格。"))
        elif status == "not_admitted":
            checks.append(RequirementCheck("legal_admission", "澳大利亚律师准入", "fail", "你已确认目前尚未取得该准入资格。"))
        else:
            checks.append(RequirementCheck("legal_admission", "澳大利亚律师准入", "pending", "该资格尚未确认。"))

    if req["practising_certificate_required"]:
        status = str(profile.get("practising_certificate") or "uncertain")
        if status in {"current", "held"}:
            checks.append(RequirementCheck("practising_certificate", "当前有效的澳大利亚执业证书", "pass", "你已确认持有该证书。"))
        elif status == "not_current":
            checks.append(RequirementCheck("practising_certificate", "当前有效的澳大利亚执业证书", "fail", "你已确认目前没有有效证书。"))
        else:
            checks.append(RequirementCheck("practising_certificate", "当前有效的澳大利亚执业证书", "pending", "证书状态尚未确认。"))

    grouped_credentials = {credential for group in req.get("credential_any_groups", []) for credential in group}
    for group in req.get("credential_any_groups", []):
        label = " 或 ".join(group)
        covered = sorted(credentials & set(group))
        if covered:
            checks.append(RequirementCheck(f"credential_any:{label}", f"专业资质：{label}（满足其一）", "pass", "你的已确认资质中包含：" + "、".join(covered)))
        elif credentials_confirmed:
            checks.append(RequirementCheck(f"credential_any:{label}", f"专业资质：{label}（满足其一）", "fail", "你已核对专业资质，但未包含岗位要求的任一项。"))
        else:
            checks.append(RequirementCheck(f"credential_any:{label}", f"专业资质：{label}（满足其一）", "pending", "简历中未确认找到这些资质，请投递前核对。"))
    for credential in req["required_credentials"]:
        if credential in {"澳大利亚律师准入", "澳大利亚执业证书"} or credential in grouped_credentials:
            continue
        if credential in credentials:
            checks.append(RequirementCheck(f"credential:{credential}", f"专业资质：{credential}", "pass", "你的已确认资质中包含该项。"))
        elif credentials_confirmed:
            checks.append(RequirementCheck(f"credential:{credential}", f"专业资质：{credential}", "fail", "你已核对专业资质，但未包含岗位明确要求的这一项。"))
        else:
            checks.append(RequirementCheck(f"credential:{credential}", f"专业资质：{credential}", "pending", "简历中未确认找到该资质，请投递前核对。"))

    if req["degree_required"]:
        education = profile.get("education_levels") or []
        if isinstance(education, str):
            education = [education]
        if education:
            checks.append(RequirementCheck("degree", "岗位明确要求的学历", "pass", "简历中识别到学历信息；仍需核对专业和具体要求。"))
        else:
            checks.append(RequirementCheck("degree", "岗位明确要求的学历", "pending", "尚未确认学历是否满足岗位具体要求。"))

    sponsorship_now = str(profile.get("sponsorship_now") or "").casefold()
    sponsorship_future = str(profile.get("sponsorship_future") or "").casefold()
    if req["sponsorship_unavailable"]:
        if sponsorship_now in {"yes", "true", "需要", "是"} or sponsorship_future in {"yes", "true", "需要", "是"}:
            checks.append(RequirementCheck("sponsorship", "岗位不提供雇主担保", "fail", "你已确认现在或未来需要雇主担保。"))
        elif sponsorship_now in {"no", "false", "不需要", "否"} and sponsorship_future in {"no", "false", "不需要", "否"}:
            checks.append(RequirementCheck("sponsorship", "岗位不提供雇主担保", "pass", "你已确认现在和未来均不需要雇主担保。"))
        else:
            checks.append(RequirementCheck("sponsorship", "岗位不提供雇主担保", "pending", "你的雇主担保情况尚未完全确认。"))

    work_authorization = str(profile.get("work_authorization") or "").strip()
    if req["full_work_rights_required"]:
        if not work_authorization:
            checks.append(RequirementCheck("work_authorization", "完整／不受限工作权利", "pending", "工作权利尚未确认。"))
        elif any(term in work_authorization.casefold() for term in ("full", "unrestricted", "citizen", "permanent", "完整", "不受限")):
            checks.append(RequirementCheck("work_authorization", "完整／不受限工作权利", "pass", f"你已填写：{work_authorization}"))
        else:
            checks.append(RequirementCheck("work_authorization", "完整／不受限工作权利", "pending", f"你已填写：{work_authorization}；请核对是否满足岗位原文。"))
    elif not work_authorization:
        checks.append(RequirementCheck("work_authorization", "工作权利", "pending", "工作权利尚未确认。"))

    return checks, req


def career_specialism_summary(role_families: Iterable[str]) -> str:
    domains = {domain_for_role(role) for role in role_families if role}
    labels = [DOMAIN_LABELS[d] for d in ("finance", "legal", "general") if d in domains]
    return "、".join(labels) if labels else "综合"
