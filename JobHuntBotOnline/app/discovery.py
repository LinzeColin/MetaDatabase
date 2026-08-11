from __future__ import annotations

import hashlib
import json
import re
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import (
    CandidateProfile, DiscoveryRun, DiscoverySourceStatus, Job, Recommendation, utcnow,
)
from .scoring import role_search_tag, score_job
from .security import CryptoBox


@dataclass
class NormalizedJob:
    source: str
    external_id: str
    url: str
    title: str
    company: str
    location: str
    description: str
    posted_at: datetime | None = None
    city: str = ""
    country: str = ""
    work_mode: str = ""
    role_family: str = ""
    industry: str = ""
    skills: list[str] | None = None
    keywords: list[str] | None = None
    owner_user_id: int | None = None


def clean_html(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)


def parse_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value)
    if text.startswith("NOW-") and text.endswith("D"):
        try:
            return utcnow() - timedelta(days=int(text[4:-1]))
        except ValueError:
            return None
    for candidate in [text, text.replace("Z", "+00:00")]:
        try:
            return datetime.fromisoformat(candidate).replace(tzinfo=None)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            pass
    return None


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    except Exception:
        return url.strip()


def safe_http_url(url: str) -> str:
    """Return a normalized public http(s) URL, or an empty string when unsafe."""
    try:
        parts = urlsplit((url or "").strip())
        # Accessing .port raises ValueError for malformed ports; treat it as invalid.
        _ = parts.port
    except (TypeError, ValueError):
        return ""
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
        return ""
    host = parts.hostname.casefold().rstrip(".")
    if host in {"localhost", "0.0.0.0", "::1"} or host.startswith("127."):
        return ""
    if host.startswith("10.") or host.startswith("192.168."):
        return ""
    if host.startswith("172."):
        try:
            second = int(host.split(".", 2)[1])
            if 16 <= second <= 31:
                return ""
        except (ValueError, IndexError):
            return ""
    return urlunsplit((parts.scheme.casefold(), parts.netloc, parts.path or "/", parts.query, ""))


def canonical_key(job: NormalizedJob) -> str:
    # Public-source jobs deduplicate globally. Private manual imports include the
    # tenant identity so the same URL imported by two users never shares an
    # owner-scoped Job row.
    raw = "|".join([
        f"owner:{job.owner_user_id}" if job.owner_user_id is not None else "public",
        normalize_url(job.url),
        job.company.casefold().strip(),
        job.title.casefold().strip(),
        job.location.casefold().strip(),
    ])
    return hashlib.sha256(raw.encode()).hexdigest()


ROLE_RULES = {
    "Finance": ["finance", "financial", "accounting", "valuation", "investment", "banking"],
    "Data": ["data", "analytics", "sql", "python", "business intelligence"],
    "Business Analysis": ["business analyst", "business analysis", "requirements", "stakeholder"],
    "Operations": ["operations", "supply chain", "process", "project coordinator"],
    "Risk": ["risk", "compliance", "audit", "controls"],
    "Consulting": ["consultant", "consulting", "strategy"],
    "Legal": ["legal", "lawyer", "attorney", "counsel", "paralegal", "solicitor", "contract law"],
}
SKILLS = ["excel", "sql", "python", "power bi", "tableau", "valuation", "accounting", "risk", "salesforce", "sap"]


class SourceDeadlineExceeded(TimeoutError):
    pass


@contextmanager
def _source_deadline(seconds: int):
    """Bound one provider without letting it freeze the Worker indefinitely.

    httpx already has per-I/O timeouts, but a process-level deadline also
    covers a provider implementation that gets stuck outside an I/O phase.
    The production Worker is a Unix main thread; test and non-Unix contexts
    retain the regular httpx timeout behavior.
    """
    if (
        seconds <= 0
        or not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def _raise_timeout(_signum, _frame):
        raise SourceDeadlineExceeded(f"source exceeded {seconds}s deadline")

    old_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    old_timer = signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if old_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, old_timer[0], old_timer[1])


def enrich(job: NormalizedJob) -> NormalizedJob:
    text = f"{job.title} {job.description}".casefold()
    if not job.role_family:
        scores = {role: sum(term in text for term in terms) for role, terms in ROLE_RULES.items()}
        job.role_family = max(scores, key=scores.get) if max(scores.values(), default=0) else "Other"
    if not job.skills:
        job.skills = [s for s in SKILLS if s in text]
    if not job.keywords:
        job.keywords = sorted(set((job.skills or []) + re.findall(r"[A-Za-z][A-Za-z+#.\-]{2,}", job.title)))[:24]
    loc = job.location.casefold()
    if not job.city:
        for city in ["Sydney", "Melbourne", "Brisbane", "Perth", "Canberra", "Adelaide"]:
            if city.casefold() in loc:
                job.city = city
                break
    if not job.country and ("australia" in loc or job.city):
        job.country = "AU"
    if not job.work_mode:
        job.work_mode = "remote" if "remote" in loc or "remote" in text else ("hybrid" if "hybrid" in text else "onsite")
    return job


def _fixture(settings: Settings) -> list[NormalizedJob]:
    path = Path(settings.discovery_fixture_path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in rows:
        row = dict(row)
        row["posted_at"] = parse_date(row.get("posted_at"))
        out.append(enrich(NormalizedJob(**row)))
    return out


def _remotive(client: httpx.Client, limit: int) -> list[NormalizedJob]:
    data = client.get("https://remotive.com/api/remote-jobs", params={"limit": limit}).json()
    out = []
    for row in data.get("jobs", [])[:limit]:
        out.append(enrich(NormalizedJob(
            source="remotive",
            external_id=str(row.get("id") or row.get("url")),
            url=row.get("url") or "",
            title=row.get("title") or "",
            company=row.get("company_name") or "",
            location=row.get("candidate_required_location") or "Remote",
            description=clean_html(row.get("description") or ""),
            posted_at=parse_date(row.get("publication_date")),
            work_mode="remote",
            industry=row.get("category") or "",
            skills=list(row.get("tags") or []),
        )))
    return out


def _arbeitnow(client: httpx.Client, limit: int) -> list[NormalizedJob]:
    data = client.get("https://www.arbeitnow.com/api/job-board-api").json()
    out = []
    for row in data.get("data", [])[:limit]:
        out.append(enrich(NormalizedJob(
            source="arbeitnow",
            external_id=str(row.get("slug") or row.get("url")),
            url=row.get("url") or "",
            title=row.get("title") or "",
            company=row.get("company_name") or "",
            location=row.get("location") or ("Remote" if row.get("remote") else ""),
            description=clean_html(row.get("description") or ""),
            posted_at=parse_date(row.get("created_at")),
            work_mode="remote" if row.get("remote") else "",
            skills=list(row.get("tags") or []),
        )))
    return out


def _jobicy(client: httpx.Client, limit: int, profile: dict | None = None) -> list[NormalizedJob]:
    params: dict[str, str | int] = {"count": min(max(1, limit), 100)}
    tag = role_search_tag(profile or {})
    if tag:
        params["tag"] = tag
    data = client.get("https://jobicy.com/api/v2/remote-jobs", params=params).json()
    out = []
    for row in data.get("jobs", [])[:limit]:
        out.append(enrich(NormalizedJob(
            source="jobicy",
            external_id=str(row.get("id") or row.get("url")),
            url=row.get("url") or "",
            title=row.get("jobTitle") or "",
            company=row.get("companyName") or "",
            location=row.get("jobGeo") or "Remote",
            description=clean_html(row.get("jobDescription") or row.get("jobExcerpt") or ""),
            posted_at=parse_date(row.get("pubDate")),
            work_mode="remote",
            industry=row.get("jobIndustry") or "",
            skills=list(row.get("jobType") or []),
        )))
    return out


def _adzuna(client: httpx.Client, settings: Settings, profile: dict) -> list[NormalizedJob]:
    query = " OR ".join(profile.get("primary_role_families", [])[:2]) or "analyst"
    location = next((x for x in profile.get("target_locations", []) if "remote" not in x.casefold()), "Australia")
    data = client.get(
        "https://api.adzuna.com/v1/api/jobs/au/search/1",
        params={
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "what": query,
            "where": location,
            "results_per_page": settings.discovery_max_jobs_per_source,
            "content-type": "application/json",
        },
    ).json()
    out = []
    for row in data.get("results", []):
        out.append(enrich(NormalizedJob(
            source="adzuna",
            external_id=str(row.get("id") or row.get("redirect_url")),
            url=row.get("redirect_url") or "",
            title=row.get("title") or "",
            company=(row.get("company") or {}).get("display_name", ""),
            location=(row.get("location") or {}).get("display_name", ""),
            description=clean_html(row.get("description") or ""),
            posted_at=parse_date(row.get("created")),
        )))
    return out


def _greenhouse(client: httpx.Client, boards: list[str], limit: int) -> list[NormalizedJob]:
    out = []
    for board in boards:
        data = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"}).json()
        for row in data.get("jobs", [])[:limit]:
            out.append(enrich(NormalizedJob(
                source=f"greenhouse:{board}",
                external_id=str(row.get("id")),
                url=row.get("absolute_url") or "",
                title=row.get("title") or "",
                company=board,
                location=(row.get("location") or {}).get("name", ""),
                description=clean_html(row.get("content") or ""),
                posted_at=parse_date(row.get("updated_at")),
            )))
    return out


def _lever(client: httpx.Client, companies: list[str], limit: int) -> list[NormalizedJob]:
    out = []
    for company in companies:
        rows = client.get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"}).json()
        for row in rows[:limit]:
            cats = row.get("categories") or {}
            out.append(enrich(NormalizedJob(
                source=f"lever:{company}",
                external_id=str(row.get("id")),
                url=row.get("hostedUrl") or row.get("applyUrl") or "",
                title=row.get("text") or "",
                company=company,
                location=cats.get("location") or "",
                description=clean_html((row.get("descriptionPlain") or "") + "\n" + (row.get("additionalPlain") or "")),
                posted_at=parse_date(row.get("createdAt") / 1000 if isinstance(row.get("createdAt"), (int, float)) else None),
                work_mode=cats.get("workplaceType") or "",
            )))
    return out


def _ashby(client: httpx.Client, boards: list[str], limit: int) -> list[NormalizedJob]:
    out = []
    for board in boards:
        data = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{board}").json()
        for row in data.get("jobs", [])[:limit]:
            out.append(enrich(NormalizedJob(
                source=f"ashby:{board}",
                external_id=str(row.get("id") or row.get("jobUrl")),
                url=row.get("jobUrl") or row.get("applyUrl") or "",
                title=row.get("title") or "",
                company=board,
                location=row.get("location") or "",
                description=clean_html(row.get("descriptionHtml") or row.get("descriptionPlain") or ""),
                posted_at=parse_date(row.get("publishedAt")),
                work_mode=row.get("workplaceType") or "",
                industry=row.get("department") or "",
            )))
    return out


def _freehire(client: httpx.Client, base: str, profile: dict, limit: int) -> list[NormalizedJob]:
    query = " ".join(profile.get("primary_role_families", [])[:2])
    data = client.get(
        f"{base}/api/v1/agent/jobs/search",
        params={"q": query, "limit": limit, "description_format": "text", "sort": "posted_at", "order": "desc"},
    ).json()
    out = []
    for row in data.get("data", []):
        enrich_data = row.get("enrichment") or {}
        out.append(enrich(NormalizedJob(
            source="freehire",
            external_id=row.get("public_slug") or row.get("external_id") or row.get("url"),
            url=row.get("url") or "",
            title=row.get("title") or "",
            company=row.get("company") or "",
            location=row.get("location") or "",
            city=(row.get("cities") or [""])[0],
            country=(row.get("countries") or [""])[0],
            description=row.get("description") or "",
            posted_at=parse_date(row.get("posted_at")),
            work_mode=row.get("work_mode") or "",
            role_family=enrich_data.get("category") or "",
            industry=(enrich_data.get("domains") or [""])[0],
            skills=list(row.get("skills") or []),
        )))
    return out


def fetch_sources(settings: Settings, profile: dict) -> Iterable[tuple[str, str, list[NormalizedJob], str]]:
    if settings.discovery_fixture_path:
        try:
            yield "fixture", "ok", _fixture(settings), ""
        except Exception as exc:
            yield "fixture", "failed", [], str(exc)
        return
    with httpx.Client(timeout=settings.discovery_source_timeout_seconds, follow_redirects=True) as client:
        providers = []
        if settings.enable_remotive:
            providers.append(("remotive", lambda: _remotive(client, settings.discovery_max_jobs_per_source)))
        if settings.enable_arbeitnow:
            providers.append(("arbeitnow", lambda: _arbeitnow(client, settings.discovery_max_jobs_per_source)))
        if settings.enable_jobicy:
            providers.append(("jobicy", lambda: _jobicy(client, settings.discovery_max_jobs_per_source, profile)))
        if settings.adzuna_app_id and settings.adzuna_app_key:
            providers.append(("adzuna", lambda: _adzuna(client, settings, profile)))
        if settings.greenhouse_boards:
            providers.append(("greenhouse", lambda: _greenhouse(client, settings.greenhouse_boards, settings.discovery_max_jobs_per_source)))
        if settings.lever_companies:
            providers.append(("lever", lambda: _lever(client, settings.lever_companies, settings.discovery_max_jobs_per_source)))
        if settings.ashby_boards:
            providers.append(("ashby", lambda: _ashby(client, settings.ashby_boards, settings.discovery_max_jobs_per_source)))
        if settings.freehire_base_url:
            providers.append(("freehire", lambda: _freehire(client, settings.freehire_base_url, profile, settings.discovery_max_jobs_per_source)))
        for name, fn in providers:
            try:
                with _source_deadline(settings.discovery_source_timeout_seconds):
                    jobs = [j for j in fn() if safe_http_url(j.url) and j.title and j.company]
                for job in jobs:
                    job.url = safe_http_url(job.url)
                yield name, "ok", jobs, ""
            except Exception as exc:
                yield name, "failed", [], str(exc)[:1000]


def enqueue_discovery(db: Session, user_id: int, trigger: str = "scheduled") -> DiscoveryRun:
    existing = db.scalar(
        select(DiscoveryRun).where(
            DiscoveryRun.user_id == user_id,
            DiscoveryRun.status.in_(["queued", "running"]),
        ).order_by(DiscoveryRun.created_at.desc())
    )
    if existing:
        return existing
    run = DiscoveryRun(user_id=user_id, trigger=trigger, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def claim_run(db: Session) -> DiscoveryRun | None:
    run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.status == "queued").order_by(DiscoveryRun.created_at.asc()))
    if not run:
        return None
    run.status = "running"
    run.started_at = utcnow()
    db.commit()
    db.refresh(run)
    return run


def fail_run(db: Session, run_id: int, reason: str) -> bool:
    """Close a claimed run after an unexpected Worker exception."""
    db.rollback()
    run = db.get(DiscoveryRun, run_id)
    if not run or run.status not in {"queued", "running"}:
        return False
    run.status = "failed"
    run.completed_at = utcnow()
    run.error_summary = (reason or "worker error")[:4000]
    db.commit()
    return True


def recover_stale_runs(db: Session, max_age_seconds: int) -> int:
    """Release abandoned Worker leases so a later refresh can make progress."""
    cutoff = utcnow() - timedelta(seconds=max(1, max_age_seconds))
    rows = db.scalars(
        select(DiscoveryRun).where(
            DiscoveryRun.status == "running",
            DiscoveryRun.started_at.is_not(None),
            DiscoveryRun.started_at < cutoff,
        )
    ).all()
    for run in rows:
        run.status = "failed"
        run.completed_at = utcnow()
        suffix = "Worker lease expired before the source run completed"
        run.error_summary = f"{run.error_summary or ''}\n{suffix}".strip()[:4000]
    if rows:
        db.commit()
    return len(rows)


def _upsert_job(db: Session, item: NormalizedJob) -> tuple[Job, bool]:
    key = canonical_key(item)
    row = db.scalar(select(Job).where(Job.canonical_key == key))
    created = False
    if not row:
        row = Job(
            owner_user_id=item.owner_user_id,
            source=item.source,
            external_id=str(item.external_id),
            canonical_key=key,
            url=item.url,
            title=item.title[:255],
            company=item.company[:255],
            location=item.location[:255],
            city=item.city[:120],
            country=item.country[:8],
            work_mode=item.work_mode[:24],
            role_family=item.role_family[:80],
            industry=item.industry[:80],
            skills_text=json.dumps(item.skills or [], ensure_ascii=False),
            keywords_text=json.dumps(item.keywords or [], ensure_ascii=False),
            description=item.description,
            posted_at=item.posted_at,
        )
        db.add(row)
        db.flush()
        created = True
    else:
        row.last_seen_at = utcnow()
        row.closed_at = None
        row.description = item.description or row.description
        row.posted_at = item.posted_at or row.posted_at
    return row, created


def _stored_job_payload(job: Job) -> dict:
    return {
        "title": job.title,
        "description": job.description,
        "location": job.location,
        "city": job.city,
        "work_mode": job.work_mode,
        "role_family": job.role_family,
        "industry": job.industry,
        "skills": json.loads(job.skills_text or "[]"),
        "keywords": json.loads(job.keywords_text or "[]"),
        "posted_at": job.posted_at,
    }


def rescore_existing_recommendations(
    db: Session,
    user_id: int,
    profile: dict,
    crypto: CryptoBox,
) -> int:
    """Refresh existing tenant recommendations after a confirmed preference change.

    This deliberately does not create a recommendation for every global job;
    it only updates records the candidate has already received. New targeted
    source rows remain the mechanism that adds new opportunities.
    """
    rows = db.execute(
        select(Recommendation, Job)
        .join(Job, Job.id == Recommendation.job_id)
        .where(
            Recommendation.user_id == user_id,
            Job.closed_at.is_(None),
            or_(Job.owner_user_id.is_(None), Job.owner_user_id == user_id),
        )
    ).all()
    for rec, job in rows:
        score = score_job(profile, _stored_job_payload(job))
        rec.qualification = score["qualification"]
        rec.relevance = score["relevance"]
        rec.opportunity = score["opportunity"]
        rec.rank_score = score["rank_score"]
        rec.reasons_encrypted = crypto.encrypt_json(score["reasons"])
        rec.last_scored_at = utcnow()
    if rows:
        db.commit()
    return len(rows)


def process_run(db: Session, run: DiscoveryRun, settings: Settings, crypto: CryptoBox) -> DiscoveryRun:
    profile_row = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == run.user_id))
    if not profile_row:
        run.status = "failed"
        run.error_summary = "候选人资料不存在"
        run.completed_at = utcnow()
        db.commit()
        return run
    profile = crypto.decrypt_json(profile_row.payload_encrypted, {})
    rescore_existing_recommendations(db, run.user_id, profile, crypto)
    total_seen = total_new = total_rec = sources = 0
    failures = []
    for source, status, jobs, detail in fetch_sources(settings, profile):
        sources += 1
        source_row = DiscoverySourceStatus(
            run_id=run.id, source=source, status=status, jobs_seen=len(jobs), detail=detail or None
        )
        db.add(source_row)
        if status != "ok":
            failures.append(f"{source}: {detail}")
            continue
        for item in jobs:
            total_seen += 1
            job, created = _upsert_job(db, item)
            total_new += int(created)
            if item.owner_user_id is not None and item.owner_user_id != run.user_id:
                continue
            score = score_job(profile, {
                **asdict(item),
                "skills": item.skills or [],
                "keywords": item.keywords or [],
            })
            rec = db.scalar(
                select(Recommendation).where(
                    Recommendation.user_id == run.user_id,
                    Recommendation.job_id == job.id,
                )
            )
            if not rec:
                rec = Recommendation(user_id=run.user_id, job_id=job.id, reasons_encrypted=b"")
                db.add(rec)
            rec.qualification = score["qualification"]
            rec.relevance = score["relevance"]
            rec.opportunity = score["opportunity"]
            rec.rank_score = score["rank_score"]
            rec.reasons_encrypted = crypto.encrypt_json(score["reasons"])
            rec.last_scored_at = utcnow()
            total_rec += 1
        db.commit()

    completed = utcnow()
    run.source_count = sources
    run.jobs_seen = total_seen
    run.jobs_new = total_new
    run.recommendations_updated = total_rec
    run.completed_at = completed
    run.status = "completed" if total_rec or not failures else "failed"
    run.error_summary = "\n".join(failures)[:4000] if failures else None
    profile_row.last_discovery_at = completed
    # 冻结业务合同：下一轮刷新严格安排在六小时后。
    profile_row.next_discovery_at = completed + timedelta(hours=6)
    db.commit()
    return run


def enqueue_due_profiles(db: Session) -> int:
    now = utcnow()
    profiles = db.scalars(
        select(CandidateProfile).where(
            CandidateProfile.discovery_enabled.is_(True),
            or_(CandidateProfile.next_discovery_at.is_(None), CandidateProfile.next_discovery_at <= now),
        )
    ).all()
    count = 0
    for profile in profiles:
        before = db.scalar(
            select(DiscoveryRun).where(
                DiscoveryRun.user_id == profile.user_id,
                DiscoveryRun.status.in_(["queued", "running"]),
            )
        )
        if not before:
            enqueue_discovery(db, profile.user_id, "scheduled")
            count += 1
    return count
