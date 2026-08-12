from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "BASE_URL": "http://testserver",
    "SESSION_SECRET": "test-session-secret",
    "DATA_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    "EMAIL_LOOKUP_SECRET": "test-email-secret",
    "COOKIE_SECURE": "false",
    "ADMIN_EMAIL": "owner@example.com",
    "ADMIN_PASSWORD": "AdminPass!2026",
    "ALLOW_REGISTRATION": "true",
    "OWNER_ENTRY_ENABLED": "true",
    "OWNER_ENTRY_PASSWORD": "OwnerEntryPass123",
    "DISCOVERY_REFRESH_HOURS": "6",
    "ENABLE_REMOTIVE": "false",
    "ENABLE_ARBEITNOW": "false",
    "ENABLE_JOBICY": "false",
    # Test runs must never consume the platform AI allowance or make an
    # external provider call, even when the host has a production secret.
    "DEEPSEEK_API_KEY": "",
})

from app.config import get_settings
from app.main import create_app


def csrf(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one('input[name="csrf_token"]')
    assert node and node.get("value")
    return str(node["value"])


def latest_link(client: TestClient, kind: str) -> str:
    outbox = client.get("/_test/outbox").json()
    rows = [row for row in outbox if row["kind"] == kind]
    assert rows, f"missing {kind} email"
    match = re.search(r"https?://\S+", rows[-1]["body"])
    assert match
    return match.group(0)


def confirm_verification(client: TestClient, link: str):
    parsed = urlparse(link)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    page = client.get(path)
    assert page.status_code == 200
    assert 'data-testid="verify-email-confirm"' in page.text
    token = parse_qs(parsed.query).get("token", [""])[0]
    assert token
    return client.post(
        "/verify-email",
        data={"csrf_token": csrf(page.text), "token": token},
        follow_redirects=True,
    )


def register_verify(client: TestClient, email: str, password: str = "ValidPass123") -> None:
    page = client.get("/register")
    response = client.post("/register", data={
        "csrf_token": csrf(page.text),
        "email": email,
        "display_name": "Test User",
        "password": password,
        "password_confirm": password,
    }, follow_redirects=True)
    assert response.status_code == 200
    link = latest_link(client, "verify")
    response = confirm_verification(client, link)
    assert response.status_code == 200
    assert "上传简历" in response.text


def complete_onboarding(client: TestClient) -> None:
    page = client.get("/onboarding/upload")
    resume_path = Path(__file__).parent / "fixtures" / "resume.txt"
    response = client.post(
        "/onboarding/upload",
        data={"csrf_token": csrf(page.text)},
        files={"resume": ("resume.txt", resume_path.read_bytes(), "text/plain")},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "只确认会影响推荐" in response.text
    response = client.post(
        "/onboarding/confirm",
        data={
            "csrf_token": csrf(response.text),
            "primary_roles": "Finance, Data, Business Analysis",
            "target_locations": "Sydney, Melbourne, Remote Australia",
            "work_authorization": "Australian full working rights",
            "sponsorship_now": "no",
            "sponsorship_future": "no",
            "work_modes": ["hybrid", "onsite", "remote"],
            "relocation": "no",
            "available_start": "2026-11",
            "avoid_roles": "Sales",
            "avoid_industries": "Gambling",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "岗位推荐" in response.text


@pytest.fixture
def settings(tmp_path):
    base = get_settings()
    return replace(
        base,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        base_url="http://testserver",
        upload_root=tmp_path / "uploads",
        backup_root=tmp_path / "backups",
        discovery_fixture_path=str(Path(__file__).parent / "fixtures" / "jobs.json"),
        # Unit tests exercise their own explicit delivery-limit cases.  Keep
        # ordinary lifecycle tests fast without weakening production defaults.
        email_min_interval_seconds=0,
        email_max_per_user_per_24h=100,
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
