"""岗位质量抽检后修掉的取数与匹配问题。

每条用例对应线上抽检里实际出现过的一类错误，文本是合成的，不含任何候选人信息。
资格规则的门槛（年限、签证、学历）在这里只被「更准确地读出来」，没有被放宽。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import discovery
from app.career_intelligence import (
    detect_job_role_family,
    detect_seniority,
    extract_job_requirements,
    extract_required_years,
)
from app.discovery import NormalizedJob, content_key, drop_stale_and_duplicates, is_stale
from app.scoring import score_job
from .test_au_sources_and_regions import BODY, Internet, PROFILE, _sources


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- 年限读取

@pytest.mark.parametrize("text,expected", [
    ("Minimum 5–7 years' experience in financial accounting and month-end close", 5),
    ("CA/CPA qualified with 4–6 years’ experience in financial accounting roles", 4),
    ("Minimum 3 to 5 years underwriting / Credit analyst experience required", 3),
    ("Three or more years’ post-qualification experience in employment law", 3),
    ("At least four years’ post-admission experience in mergers and acquisitions", 4),
    ("4-7 PQE lawyer, with experience in Litigation and/or Intellectual Property", 4),
    ("Five plus years’ PQE in banking and finance transactions", 5),
    ("Three years PQE+", 3),
    ("2–6 years’ PQE", 2),
    ("1-2 years post admission experience", 1),
    ("three to five years’ post admission experience", 3),
    ("5+ years in sales enablement, sales coaching or similar", 5),
    ("Requires 15+ years of finance leadership experience", 15),
    ("Minimum 8 years of experience required.", 8),
])
def test_required_years_reads_ranges_number_words_and_pqe(text, expected):
    assert extract_required_years(text) == expected


@pytest.mark.parametrize("text", [
    "practical advice that is gained from a combined 40+ years of experience",
    "a lawyer who brings more than 20 years’ experience advising developers",
    "For more than 10 years, we've been helping small businesses succeed",
    "Quarterly refresh days and an extended break after 2 years of service",
    "",
])
def test_required_years_ignores_company_and_partner_biographies(text):
    assert extract_required_years(text) is None


def test_five_to_seven_year_role_fails_a_three_year_candidate():
    job = {
        "title": "Senior Financial Accountant", "location": "Sydney, Australia", "city": "Sydney", "country": "AU",
        "description": BODY + " Minimum 5–7 years' experience in financial accounting and consolidation.",
    }
    result = score_job(PROFILE, job)
    assert result["requirements"]["required_years"] == 5
    assert result["qualification"] == "fail"          # 3 年 < 5 年：门槛没变，只是现在读得出来


def test_pqe_requirement_fails_a_less_experienced_lawyer():
    profile = {**PROFILE, "primary_role_families": ["Legal"], "experience_years": 3}
    job = {"title": "Senior Lawyer, Banking", "location": "Perth, Australia", "city": "Perth", "country": "AU",
           "description": BODY + " Five plus years’ PQE in banking and finance transactions."}
    assert score_job(profile, job)["qualification"] == "fail"


# ---------------------------------------------------------------- 签证 / 工作权利

@pytest.mark.parametrize("text", [
    "Harvey does not currently offer visa sponsorship for this role",
    "We are unable to provide sponsorship for this position",
    "Sponsorship is not offered for this role",
    "There is no employer sponsorship available",
])
def test_sponsorship_refusals_are_recognised(text):
    assert extract_job_requirements({"title": "Analyst", "description": text})["sponsorship_unavailable"]


@pytest.mark.parametrize("text", [
    "Must have valid Australian work rights",
    "Only those with eligible right to work will be considered",
    "candidates must have full-time Australian work rights",
    "You must have the right to work in Australia",
    "Applications will only be considered from candidates who hold working rights in Australia",
])
def test_work_rights_requirements_are_recognised(text):
    assert extract_job_requirements({"title": "Analyst", "description": text})["full_work_rights_required"]


def test_ordinary_sponsor_wording_is_not_a_visa_refusal():
    text = "We advise lenders, borrowers and sponsors on complex transactions and sponsor community events."
    reqs = extract_job_requirements({"title": "Lawyer", "description": text})
    assert not reqs["sponsorship_unavailable"] and not reqs["full_work_rights_required"]


def test_sponsorship_refusal_still_blocks_a_candidate_who_needs_sponsorship():
    profile = {**PROFILE, "sponsorship_now": "yes", "sponsorship_future": "yes"}
    job = {"title": "Financial Analyst", "location": "Sydney, Australia", "city": "Sydney", "country": "AU",
           "description": BODY + " This employer does not offer visa sponsorship."}
    assert score_job(profile, job)["qualification"] == "fail"


# ---------------------------------------------------------------- 方向识别

ACCOUNTING_NOISE = (
    " We build accounting software used by accountants. Audit logs, KYC checks, compliance with AML rules and "
    "financial reporting are part of the product. " * 3
)


@pytest.mark.parametrize("title", [
    "Senior Software Engineer, Backend",
    "Engineering Manager - Data",
    "Customer Success Manager, Enterprise",
    "Business Development Manager",
    "Account Executive, Mid-Market - ANZ",
    "Senior Performance Marketer",
    "Collections Specialist",
    "Product Manager",
    "Architecture Lead",
    "Accounting Professional? Discover a new career in SaaS Sales",
    "Legal Engineer, Sydney",
])
def test_professional_role_needs_the_title_not_just_the_body(title):
    assert detect_job_role_family(title, ACCOUNTING_NOISE + " legal contracts and litigation support.") == "Other"


@pytest.mark.parametrize("title,expected", [
    ("Senior Financial Accountant", "Accounting"),
    ("Senior FP&A Analyst", "Finance"),
    ("Senior Credit Analyst", "Finance"),
    ("Tax Analyst", "Accounting"),
    ("Risk & Control Lead - 12 month FTC", "Risk"),
    ("Compliance Specialist", "Compliance"),
    ("Global Senior Payments Counsel", "Legal"),
    ("Banking & Finance Derivatives Counsel", "Legal"),
    ("Lawyer, Disputes and Investigations", "Legal"),
    ("Corporate Services & Finance Lawyer", "Legal"),
    ("Finance Business Partner", "Finance"),
])
def test_finance_and_legal_titles_are_still_recognised(title, expected):
    assert detect_job_role_family(title, "") == expected


def test_general_roles_may_still_be_inferred_from_the_body():
    assert detect_job_role_family("Specialist", "Build dashboards with SQL, Tableau and Power BI for analytics.") == "Data"


def test_unrelated_roles_are_not_a_high_relevance_match_for_finance_or_legal_candidates():
    finance = {**PROFILE, "primary_role_families": ["金融分析", "会计与审计"]}
    legal = {**PROFILE, "primary_role_families": ["法律"], "experience_years": 4}
    for title in ("Staff Software Engineer, Financial Platform", "Customer Support Specialist", "Senior Mobile Engineer"):
        job = {"title": title, "description": BODY + ACCOUNTING_NOISE, "location": "Sydney, Australia",
               "city": "Sydney", "country": "AU", "work_mode": "onsite"}
        for profile in (finance, legal):
            assert score_job(profile, job)["relevance"] == "low", title


def test_finance_business_partner_is_not_partner_level():
    assert detect_seniority("Finance Business Partner") != "partner"
    assert detect_seniority("HR Business Partner") != "partner"
    assert detect_seniority("Partner, Corporate Advisory") == "partner"
    job = {"title": "Finance Business Partner", "location": "Sydney, Australia", "city": "Sydney", "country": "AU",
           "description": BODY}
    assert score_job(PROFILE, job)["qualification"] == "pass"


# ---------------------------------------------------------------- 过期与重复

def _nj(**over) -> NormalizedJob:
    base = dict(source="s", external_id="1", url="https://x.example/1", title="Employment Lawyer", company="Acme Legal",
                location="Sydney, New South Wales, Australia", description=BODY, posted_at=_now() - timedelta(days=5),
                city="Sydney", country="AU")
    base.update(over)
    return NormalizedJob(**base)


def test_postings_older_than_a_year_are_dropped_and_undated_ones_are_kept():
    assert is_stale(_nj(posted_at=_now() - timedelta(days=discovery.MAX_POSTING_AGE_DAYS + 1)))
    assert not is_stale(_nj(posted_at=_now() - timedelta(days=200)))
    assert not is_stale(_nj(posted_at=None))
    kept = drop_stale_and_duplicates([_nj(posted_at=datetime(2020, 10, 4)), _nj(external_id="2", url="https://x.example/2")], {})
    assert [j.external_id for j in kept] == ["2"]


def test_same_opening_reposted_under_a_new_url_is_merged():
    seen: dict = {}
    first = _nj()
    repost = _nj(external_id="2", url="https://x.example/2-employment-lawyer")
    assert [j.external_id for j in drop_stale_and_duplicates([first, repost], seen)] == ["1"]
    # ... and across providers within one run
    assert drop_stale_and_duplicates([_nj(external_id="3", url="https://other.example/3", source="t")], seen) == []


def test_punctuation_and_and_plus_do_not_hide_a_duplicate():
    assert content_key(_nj(title="Lawyer, Disputes and Investigations")) == content_key(_nj(title="Lawyer, Disputes + Investigations"))
    assert content_key(_nj(company="Gilbert + Tobin")) == content_key(_nj(company="Gilbert and Tobin"))


def test_same_title_in_another_city_or_at_another_level_is_not_a_duplicate():
    seen: dict = {}
    junior = _nj(description="You are an admitted lawyer at the start of your career. " * 8)
    senior = _nj(external_id="2", url="https://x.example/2", description="Five years' PQE leading disputes matters for clients. " * 8)
    melbourne = _nj(external_id="3", url="https://x.example/3", location="Melbourne, Victoria, Australia", city="Melbourne")
    kept = drop_stale_and_duplicates([junior, senior, melbourne], seen)
    assert [j.external_id for j in kept] == ["1", "2", "3"]


class _DuplicatingInternet(Internet):
    """Greenhouse and Lever both publish the same Sydney credit-analyst opening."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.lever.co":
            return httpx.Response(200, json=[
                {"id": "l9", "text": "Credit Analyst", "hostedUrl": "https://jobs.lever.co/acme/l9",
                 "categories": {"location": "Sydney, New South Wales, Australia"}, "descriptionPlain": BODY, "createdAt": None}])
        return super().__call__(request)


def test_fetch_sources_merges_duplicates_across_providers(settings, monkeypatch):
    fake = _DuplicatingInternet()
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(fake)}))
    monkeypatch.setattr(discovery, "BOARD_REQUEST_GAP_SECONDS", 0)
    monkeypatch.setattr(discovery, "load_au_boards", lambda: {"greenhouse": ["acme"], "lever": ["acme"]})
    discovery._FEED_CACHE.clear()
    rows = _sources(settings, PROFILE)
    credit = [(name, j.url) for name, (_s, jobs, _d) in rows.items() for j in jobs if j.title == "Credit Analyst"]
    assert len(credit) == 1, credit
    assert credit[0][0] == "au-greenhouse"


# ---------------------------------------------------------------- 取数：限流/错误响应不能当成「没有岗位」

class _RateLimited(Internet):
    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host in {"api.lever.co", "remotive.com"}:
            return httpx.Response(429, text="error code: 1015")
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(404, json={"jobs": [{"id": "x", "title": "Financial Analyst"}]})
        return super().__call__(request)


def test_http_errors_are_reported_as_failures_not_as_empty_or_fake_results(settings, monkeypatch):
    fake = _RateLimited()
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(fake)}))
    monkeypatch.setattr(discovery, "BOARD_REQUEST_GAP_SECONDS", 0)
    monkeypatch.setattr(discovery, "load_au_boards", lambda: {"lever": ["acme"], "ashby": ["acme"]})
    discovery._FEED_CACHE.clear()
    cfg = replace(settings, discovery_fixture_path="", enable_remotive=True, enable_arbeitnow=False,
                  enable_jobicy=False, enable_au_boards=True)
    rows = {name: (status, jobs, detail) for name, status, jobs, detail in discovery.fetch_sources(cfg, PROFILE)}
    assert rows["remotive"][0] == "failed" and "HTTP 429" in rows["remotive"][2]
    assert rows["au-lever"][0] == "failed" and "HTTP 429" in rows["au-lever"][2]
    assert rows["au-ashby"][0] == "failed" and "HTTP 404" in rows["au-ashby"][2]   # 404 的 JSON 体不能被当成岗位
