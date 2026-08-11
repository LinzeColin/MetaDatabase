from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from docx import Document
from pypdf import PdfReader

SKILL_TERMS = [
    "excel", "sql", "python", "power bi", "tableau", "financial modeling",
    "valuation", "accounting", "finance", "data analysis", "business analysis",
    "risk", "operations", "project management", "stakeholder", "research",
    "statistics", "machine learning", "aws", "azure", "salesforce", "sap",
]
ROLE_RULES = {
    "Finance": ["finance", "financial", "accounting", "valuation", "investment", "banking"],
    "Data": ["data", "sql", "python", "tableau", "power bi", "statistics", "analytics"],
    "Business Analysis": ["business analysis", "business analyst", "stakeholder", "requirements"],
    "Operations": ["operations", "process", "supply chain", "project management"],
    "Risk": ["risk", "compliance", "audit", "controls"],
    "Consulting": ["consulting", "strategy", "research", "client"],
}
LOCATION_TERMS = ["Sydney", "Melbourne", "Brisbane", "Perth", "Canberra", "Adelaide", "Remote Australia"]


class ResumeError(ValueError):
    pass


def extract_text(filename: str, content_type: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif suffix == ".docx" or "wordprocessingml" in content_type:
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                text += "\n" + " | ".join(cell.text for cell in row.cells)
    elif suffix in {".txt", ".md"} or content_type.startswith("text/"):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ResumeError("支持 PDF、DOCX、TXT 和 Markdown 简历。")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    if len(text.strip()) < 80:
        raise ResumeError("没有从文件中读取到足够的简历文字，请换用可选择文字的 PDF、DOCX 或 TXT。")
    return text.strip()


def _sentences(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        line = line.strip(" \t•▪●-–—")
        if 20 <= len(line) <= 500:
            items.append(line)
    return items


def parse_resume(text: str) -> dict[str, Any]:
    lower = text.casefold()
    skills = sorted({term for term in SKILL_TERMS if term in lower})
    role_scores = {
        role: sum(lower.count(term) for term in terms)
        for role, terms in ROLE_RULES.items()
    }
    role_families = [r for r, score in sorted(role_scores.items(), key=lambda x: (-x[1], x[0])) if score > 0][:4]

    education = []
    for line in _sentences(text):
        l = line.casefold()
        if any(term in l for term in ["university", "bachelor", "master", "degree", "unsw", "college"]):
            education.append(line)
    experiences = []
    for line in _sentences(text):
        l = line.casefold()
        if any(term in l for term in ["intern", "analyst", "manager", "assistant", "project", "research"]):
            experiences.append(line)
    experiences = experiences[:10]

    locations = [loc for loc in LOCATION_TERMS if loc.casefold() in lower]
    keywords = sorted(set(skills + role_families + [w for w in re.findall(r"[A-Za-z][A-Za-z+#.\-]{2,}", text) if len(w) < 28]))[:80]
    return {
        "skills": skills,
        "role_families": role_families,
        "education": education[:6],
        "experiences": experiences,
        "locations": locations,
        "keywords": keywords,
        "summary": f"系统从简历中识别到 {len(skills)} 项技能、{len(experiences)} 段可能相关经历和 {len(role_families)} 个候选岗位族。",
    }


def profile_draft(parsed: dict[str, Any]) -> dict[str, Any]:
    locations = parsed.get("locations") or []
    return {
        "primary_role_families": parsed.get("role_families", [])[:3],
        "secondary_role_families": parsed.get("role_families", [])[3:],
        "target_locations": locations,
        "work_mode": [],
        "skills": parsed.get("skills", []),
        "keywords": parsed.get("keywords", [])[:40],
        "work_authorization": "",
        "sponsorship_now": "",
        "sponsorship_future": "",
        "relocation": "",
        "available_start": "",
        "avoid_roles": [],
        "avoid_industries": [],
    }


def experience_records(parsed: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"title": f"经历 {idx}", "detail": detail, "kind": "experience", "strength": "medium"}
        for idx, detail in enumerate(parsed.get("experiences", [])[:8], start=1)
    ]
