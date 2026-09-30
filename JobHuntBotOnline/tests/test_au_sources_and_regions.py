"""Region-aware sourcing: Australian public boards, location matching, feed politeness."""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app import discovery
from app.regions import location_fit
from app.scoring import score_job

PROFILE = {
    "primary_role_families": ["Finance"],
    "secondary_role_families": [],
    "target_locations": ["Sydney"],
    "work_mode": ["hybrid", "onsite", "remote"],
    "skills": [],
    "keywords": [],
    "experience_years": 3,
    "work_authorization": "Australian full working rights",
    "sponsorship_now": "no",
    "sponsorship_future": "no",
}
BODY = "You will prepare monthly management accounts, forecasts and variance analysis for the business. " * 2


def _job(**over):
    base = {"title": "Financial Analyst", "description": BODY, "location": "Sydney, Australia",
            "city": "Sydney", "country": "AU", "work_mode": "onsite", "role_family": "Finance",
            "skills": [], "keywords": []}
    base.update(over)
    return base


@pytest.mark.parametrize("targets,job,expected", [
    (["Sydney"], {"location": "Sydney, NSW"}, "match"),
    (["Sydney"], {"location": "AU - Sydney"}, "match"),
    (["澳大利亚"], {"location": "Melbourne, Australia"}, "match"),
    (["悉尼"], {"location": "Macquarie Park, Australia"}, "match"),
    (["Sydney"], {"location": "Melbourne, Australia"}, "other_city"),
    (["Sydney"], {"location": "Berlin"}, "mismatch"),
    (["Sydney"], {"location": "Remote, USA", "work_mode": "remote"}, "mismatch"),
    (["Sydney"], {"location": "APAC", "work_mode": "remote"}, "remote_ok"),
    (["Sydney"], {"location": "Anywhere", "work_mode": "remote"}, "remote_ok"),
    (["Sydney"], {"location": "Remote, Australia", "work_mode": "remote"}, "match"),
    (["Sydney"], {"location": "Remote, Australia", "work_mode": "remote", "city": "Melbourne"}, "remote_ok"),
    (["Sydney"], {"location": "", "country": ""}, "unknown"),
    (["Remote"], {"location": "Remote", "work_mode": "remote"}, "match"),
    (["London"], {"location": "London, UK"}, "match"),
    ([], {"location": "Berlin"}, "no_target"),
])
def test_location_fit_connects_chinese_and_english_place_names(targets, job, expected):
    job = {"city": "", "country": "", "work_mode": "", **job}
    assert location_fit(targets, job) == expected


def test_job_outside_target_region_is_out_of_scope_not_a_qualified_match():
    berlin = score_job(PROFILE, _job(location="Berlin, Germany", city="", country="", work_mode="onsite"))
    assert berlin["location_fit"] == "mismatch"
    assert berlin["qualification"] == "pending"      # never promoted to pass by location
    assert berlin["relevance"] == "low"
    sydney = score_job(PROFILE, _job())
    assert sydney["location_fit"] == "match"
    assert sydney["qualification"] == "pass"
    assert sydney["relevance"] == "high"


def test_chinese_country_target_reaches_australian_job():
    profile = {**PROFILE, "target_locations": ["澳大利亚"]}
    assert score_job(profile, _job(location="Sydney, NSW", city="Sydney"))["qualification"] == "pass"


def test_hard_requirements_still_decide_qualification_in_region():
    senior = score_job(PROFILE, _job(description=BODY + " Minimum 8 years of experience required."))
    assert senior["location_fit"] == "match"
    assert senior["qualification"] == "fail"


def test_posting_without_body_cannot_pass_hard_requirements():
    result = score_job(PROFILE, _job(description=""))
    assert result["qualification"] == "pending"
    assert any("正文" in reason for reason in result["reasons"])


def test_taxonomy_role_word_in_description_does_not_make_engineering_high_relevance():
    engineer = score_job(PROFILE, _job(
        title="Senior Software Engineer",
        description="Build distributed systems. You will partner with the Finance team on tooling. " * 3,
        role_family="",
    ))
    assert engineer["relevance"] != "high"


# ---------- adapters ----------
class Internet:
    def __init__(self):
        self.hits: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.hits.append(str(url))
        assert "JobHuntBot" in request.headers["user-agent"]
        if url.host == "api.smartrecruiters.com" and url.path.endswith("/postings"):
            return httpx.Response(200, json={"content": [
                {"id": "111", "name": "Senior Financial Accountant", "location": {"city": "Melbourne", "country": "au"},
                 "department": {"label": "Finance"}, "releasedDate": "2026-09-28T00:00:00Z"},
                {"id": "222", "name": "Barista", "location": {"city": "Sydney", "country": "au"}},
            ]})
        if url.host == "api.smartrecruiters.com":
            return httpx.Response(200, json={
                "postingUrl": "https://jobs.smartrecruiters.com/acme/111",
                "jobAd": {"sections": {"jobDescription": {"text": "<p>" + BODY + "</p>"}}},
            })
        if url.host == "apply.workable.com":
            return httpx.Response(200, json={"name": "Acme Legal", "jobs": [
                {"shortcode": "AB1", "title": "Commercial Lawyer", "url": "https://apply.workable.com/acme/j/AB1/",
                 "city": "Sydney", "state": "NSW", "country": "Australia", "description": "<p>" + BODY + "</p>",
                 "published_on": "2026-09-27"},
                {"shortcode": "AB2", "title": "Lawyer", "url": "https://apply.workable.com/acme/j/AB2/",
                 "city": "London", "country": "United Kingdom", "description": BODY},
            ]})
        if url.host == "api.lever.co":
            return httpx.Response(200, json=[
                {"id": "l1", "text": "FP&A Analyst", "hostedUrl": "https://jobs.lever.co/acme/l1",
                 "categories": {"location": "Sydney"}, "descriptionPlain": BODY, "createdAt": None},
                {"id": "l2", "text": "FP&A Analyst", "hostedUrl": "https://jobs.lever.co/acme/l2",
                 "categories": {"location": "Austin, TX"}, "descriptionPlain": BODY, "createdAt": 1790000000000},
            ])
        if url.host == "boards-api.greenhouse.io" and "broken" in url.path:
            return httpx.Response(500, text="oops")
        if url.host == "boards-api.greenhouse.io":
            return httpx.Response(200, json={"jobs": [
                {"id": 1, "title": "Credit Analyst", "absolute_url": "https://boards.greenhouse.io/x/jobs/1",
                 "location": {"name": "Sydney, New South Wales, Australia"}, "content": BODY, "updated_at": "2026-09-20T00:00:00Z"},
                {"id": 2, "title": "Credit Analyst", "absolute_url": "https://boards.greenhouse.io/x/jobs/2",
                 "location": {"name": "New York"}, "content": BODY},
            ]})
        if url.host == "api.ashbyhq.com":
            return httpx.Response(200, json={"jobs": []})
        if url.host == "jobicy.com":
            if "geo" not in url.params:
                return httpx.Response(200, json={"jobs": []})
            assert url.params["geo"] == "australia"
            return httpx.Response(200, json={"jobs": [
                {"id": 9, "url": "https://jobicy.com/jobs/9", "jobTitle": "Remote Tax Analyst", "companyName": "Acme",
                 "jobGeo": "Australia", "jobDescription": BODY, "pubDate": "2026-09-29 10:00:00"}]})
        raise AssertionError(f"unexpected request {request.method} {url}")


@pytest.fixture
def internet(monkeypatch):
    fake = Internet()
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(fake)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    monkeypatch.setattr(discovery, "BOARD_REQUEST_GAP_SECONDS", 0)
    monkeypatch.setattr(discovery, "load_au_boards", lambda: {
        "greenhouse": ["acme", "broken"], "lever": ["acme"], "ashby": ["acme"],
        "smartrecruiters": ["acme"], "workable": ["acme"],
    })
    discovery._FEED_CACHE.clear()
    return fake


def _sources(settings, profile, **over):
    cfg = replace(settings, discovery_fixture_path="", enable_remotive=False, enable_arbeitnow=False,
                  enable_jobicy=True, enable_au_boards=True, **over)
    return {name: (status, jobs, detail) for name, status, jobs, detail in discovery.fetch_sources(cfg, profile)}


def test_australian_boards_return_only_australian_postings_with_bodies(settings, internet):
    rows = _sources(settings, PROFILE)
    titles = {j.title for _s, jobs, _d in rows.values() for j in jobs}
    assert titles == {"Senior Financial Accountant", "Commercial Lawyer", "FP&A Analyst", "Credit Analyst", "Remote Tax Analyst"}
    assert all(j.country == "AU" for name, (_s, jobs, _d) in rows.items() if name.startswith("au-") for j in jobs)
    sr = rows["au-smartrecruiters"][1][0]
    assert sr.description.startswith("You will prepare") and sr.url.endswith("/acme/111")
    assert not any("/222" in hit for hit in internet.hits), "non finance/legal roles must not trigger a detail request"
    assert rows["au-lever"][0] == "ok"
    # one failing employer board is reported but does not hide the others
    status, jobs, detail = rows["au-greenhouse"]
    assert status == "ok" and len(jobs) == 1 and "broken" in detail


def test_australian_sources_are_skipped_for_candidates_elsewhere(settings, internet):
    rows = _sources(settings, {**PROFILE, "target_locations": ["London"]})
    assert not [name for name in rows if name.startswith("au-") or name == "jobicy-au"]


def test_public_feed_is_fetched_once_per_cycle_for_all_candidates(settings, internet):
    _sources(settings, PROFILE, feed_cache_seconds=3600)
    _sources(settings, PROFILE, feed_cache_seconds=3600)
    from collections import Counter
    repeated = {u: n for u, n in Counter(internet.hits).items() if n > 1 and "broken" not in u}
    assert not repeated, repeated
    discovery._FEED_CACHE.clear()


def test_run_does_not_recommend_jobs_outside_the_confirmed_region(client):
    from sqlalchemy import select
    from app.models import DiscoveryRun, Job, Recommendation, CandidateProfile
    from app.security import CryptoBox
    from .conftest import register_verify, complete_onboarding

    register_verify(client, "region@example.com")
    complete_onboarding(client)
    state = client.app.state
    with state.session_factory() as db:
        rows = db.execute(select(Recommendation, Job).join(Job)).all()
        assert rows, "fixture aggregation should recommend the in-region jobs"
        profile = CryptoBox(state.settings.data_encryption_key).decrypt_json(
            db.scalar(select(CandidateProfile.payload_encrypted)), {})
        for _rec, job in rows:
            assert location_fit(profile["target_locations"], {
                "location": job.location, "city": job.city, "country": job.country, "work_mode": job.work_mode,
            }) != "mismatch"
