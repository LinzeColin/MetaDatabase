"""Target-region matching between a candidate's confirmed locations and a job.

The candidate confirms free-text target locations ("Sydney", "澳大利亚", "Remote
Australia").  Job feeds describe places as "Sydney, Australia", "Sydney, NSW",
"AU - Melbourne", "APAC" or "Berlin".  A plain substring test cannot connect a
Chinese country name to an English city, so every Australian job was reported
as "地点需要确认" and 99.9% of the recommendation feed stayed pending.
"""
from __future__ import annotations

import re
from typing import Any

AU_CITIES = {
    "sydney": ("sydney", "悉尼"),
    "melbourne": ("melbourne", "墨尔本"),
    "brisbane": ("brisbane", "布里斯班"),
    "perth": ("perth", "珀斯"),
    "canberra": ("canberra", "堪培拉"),
    "adelaide": ("adelaide", "阿德莱德"),
    "hobart": ("hobart", "霍巴特"),
    "darwin": ("darwin", "达尔文"),
    "gold coast": ("gold coast", "黄金海岸"),
    "newcastle": ("newcastle nsw", "newcastle, nsw", "newcastle, new south wales"),
}
# Suburbs that appear as the only place name in some feeds.
AU_METRO = {
    "sydney": ("macquarie park", "surry hills", "north sydney", "parramatta", "chatswood", "pyrmont", "barangaroo", "ultimo", "alexandria", "redfern", "st leonards"),
    "melbourne": ("cremorne", "richmond vic", "docklands", "southbank", "south yarra", "collingwood", "altona", "footscray", "burwood"),
    "brisbane": ("fortitude valley", "south brisbane"),
}
AU_STATES = (
    "new south wales", "victoria, australia", "queensland", "western australia",
    "south australia", "tasmania", "australian capital territory",
)
AU_STATE_CODES = re.compile(r"(?<![a-z])(nsw|vic|qld|act|tas)(?![a-z])", re.I)
AU_COUNTRY_TERMS = ("australia", "澳大利亚", "澳洲", "aus", "anz", "aunz")
AU_COUNTRY_RE = re.compile(r"(?<![a-z])(australia|aunz|anz|au)(?![a-z])", re.I)
# Remote postings that explicitly allow a candidate in Australia.
REMOTE_OPEN_TERMS = ("anywhere", "worldwide", "global", "apac", "asia pacific", "asia-pacific", "oceania")
REMOTE_TOKENS = ("remote", "远程")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _city_of(text: str) -> str:
    for city, terms in AU_CITIES.items():
        if any(term in text for term in terms):
            return city
    for city, suburbs in AU_METRO.items():
        if any(suburb in text for suburb in suburbs):
            return city
    return ""


def _is_australia(text: str) -> bool:
    if AU_COUNTRY_RE.search(text) or any(term in text for term in ("澳大利亚", "澳洲")):
        return True
    if any(state in text for state in AU_STATES) or AU_STATE_CODES.search(text):
        return True
    return bool(_city_of(text))


def parse_targets(values: list[str] | str | None) -> list[dict[str, Any]]:
    """Turn confirmed free-text locations into structured targets."""
    if isinstance(values, str):
        values = re.split(r"[,，;；、\n]", values)
    targets: list[dict[str, Any]] = []
    for raw in values or []:
        text = _norm(raw)
        if not text:
            continue
        remote = any(token in text for token in REMOTE_TOKENS)
        city = _city_of(text)
        au = _is_australia(text)
        targets.append({"raw": text, "remote": remote, "au": au or bool(city), "city": city})
    return targets


def targets_include_australia(values: list[str] | str | None) -> bool:
    return any(t["au"] for t in parse_targets(values))


def location_fit(target_values: list[str] | str | None, job: dict[str, Any]) -> str:
    """Return one of: match, remote_ok, other_city, mismatch, unknown, no_target."""
    targets = parse_targets(target_values)
    if not targets:
        return "no_target"
    location = _norm(job.get("location"))
    city_field = _norm(job.get("city"))
    country_field = _norm(job.get("country"))
    text = f"{location} {city_field}".strip()
    work_mode = _norm(job.get("work_mode"))
    remote_job = work_mode == "remote" or any(token in text for token in REMOTE_TOKENS)

    job_au = country_field == "au" or _is_australia(text)
    job_city = _city_of(text)
    if not text and not country_field:
        return "unknown"

    accepts_remote = any(t["remote"] for t in targets)
    for target in targets:
        if target["au"]:
            if job_au:
                if not target["city"] or not job_city or target["city"] == job_city:
                    return "match"
        elif target["raw"] and target["raw"] in text and not target["remote"]:
            return "match"
        elif target["remote"] and not target["au"]:
            # "Remote" alone: any remote posting that is not fenced to another region.
            if remote_job and not _fenced_elsewhere(text, job_au):
                return "match"

    if remote_job and (job_au or any(term in text for term in REMOTE_OPEN_TERMS)):
        # The candidate's work-mode list decides whether remote is welcome; the
        # location list only needs to reach the job's region.
        return "remote_ok"
    if remote_job and not _fenced_elsewhere(text, job_au):
        # A bare "Remote" names no region, so it cannot be judged either way.
        return "remote_ok" if accepts_remote else "unknown"
    if any(t["au"] for t in targets) and job_au:
        return "other_city"
    return "mismatch"


def _fenced_elsewhere(text: str, job_au: bool) -> bool:
    if job_au or any(term in text for term in REMOTE_OPEN_TERMS):
        return False
    # Anything else that names a place ("USA", "Europe", "Germany") fences the role.
    return bool(re.sub(r"remote|homeoffice|home office|,|-|/|\s", "", text))
