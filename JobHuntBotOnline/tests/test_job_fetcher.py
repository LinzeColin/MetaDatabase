from __future__ import annotations

import asyncio
import socket

import pytest

from app.services.job_fetcher import (
    JobFetchError,
    _assert_public_host,
    domain_is_fetch_allowed,
    domain_requires_manual_paste,
    fetch_job_document,
    parse_job_html,
    validate_fetch_target,
    _validate_url,
)


def test_parses_jobposting_jsonld():
    html = """
    <html><head><script type="application/ld+json">{
      "@context":"https://schema.org", "@type":"JobPosting",
      "title":"Graduate Data Analyst",
      "hiringOrganization":{"@type":"Organization","name":"Example Co"},
      "datePosted":"2026-08-08",
      "jobLocation":{"address":{"addressLocality":"Sydney","addressRegion":"NSW","addressCountry":"AU"}},
      "description":"<p>Analyse datasets using Python, SQL and Excel.</p><p>Build Power BI dashboards and communicate findings to stakeholders. This role provides meaningful graduate development and cross-functional work.</p>"
    }</script></head><body><h1>Fallback</h1></body></html>
    """
    document = parse_job_html("https://careers.example.com/jobs/1", html)
    assert document.company == "Example Co"
    assert document.title == "Graduate Data Analyst"
    assert document.location == "Sydney, NSW, AU"
    assert document.posted_date == "2026-08-08"
    assert "Python" in document.description


def test_only_reviewed_ats_domains_are_fetched_server_side():
    assert domain_requires_manual_paste("https://www.seek.com.au/job/123")
    assert domain_requires_manual_paste("https://jobs.linkedin.com/view/123")
    assert domain_requires_manual_paste("https://careers.example.com/jobs/1")
    assert domain_is_fetch_allowed("https://boards.greenhouse.io/example/jobs/1")
    assert domain_is_fetch_allowed("https://jobs.lever.co/example/1")
    assert not domain_requires_manual_paste("https://boards.greenhouse.io/example/jobs/1")


def test_unreviewed_domain_returns_manual_path_without_network(monkeypatch):
    def forbidden_getaddrinfo(*args, **kwargs):
        raise AssertionError("DNS must not be called for an unreviewed domain")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden_getaddrinfo)
    document = asyncio.run(fetch_job_document("https://careers.example.com/jobs/1"))
    assert document.fetched is False
    assert "复制职位正文" in document.manual_reason


def test_private_network_url_is_rejected(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(JobFetchError, match="非公开网络地址"):
        asyncio.run(_assert_public_host("https://internal.example/path"))


def test_job_links_require_https():
    with pytest.raises(JobFetchError, match="https"):
        _validate_url("http://boards.greenhouse.io/example/jobs/1")


def test_fetch_redirect_target_must_remain_on_reviewed_ats_domain():
    assert validate_fetch_target("https://boards.greenhouse.io/example/jobs/1")
    with pytest.raises(JobFetchError, match="未授权域名"):
        validate_fetch_target("https://careers.example.com/jobs/1")
