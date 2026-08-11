#!/usr/bin/env python3
"""Prove persistence and exact six-hour scheduling across an application restart."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update({
    "APP_ENV": "test", "BASE_URL": "http://testserver", "SESSION_SECRET": "restart-session",
    "DATA_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    "EMAIL_LOOKUP_SECRET": "restart-email", "COOKIE_SECURE": "false",
    "ADMIN_EMAIL": "owner@example.com", "ADMIN_PASSWORD": "AdminPass!2026",
    "DISCOVERY_REFRESH_HOURS": "6", "ENABLE_REMOTIVE": "false",
    "ENABLE_ARBEITNOW": "false", "ENABLE_JOBICY": "false",
})

from app.config import get_settings
from app.main import create_app
from app.models import CandidateProfile, Recommendation, User


def csrf(html: str) -> str:
    node = BeautifulSoup(html, "html.parser").select_one('input[name="csrf_token"]')
    if not node or not node.get("value"):
        raise AssertionError("csrf token missing")
    return str(node["value"])


def latest_link(client: TestClient, kind: str) -> str:
    rows = [x for x in client.get("/_test/outbox").json() if x["kind"] == kind]
    if not rows:
        raise AssertionError(f"missing {kind} mail")
    match = re.search(r"https?://\S+", rows[-1]["body"])
    if not match:
        raise AssertionError(f"missing link in {kind} mail")
    parsed = urlparse(match.group(0))
    return parsed.path + ("?" + parsed.query if parsed.query else "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/local/restart_readback.json")
    args = parser.parse_args()
    temp = Path(tempfile.mkdtemp(prefix="jobhunt-restart-"))
    try:
        base = get_settings()
        settings = replace(
            base,
            database_url=f"sqlite+pysqlite:///{temp / 'persistent.db'}",
            upload_root=temp / "uploads",
            backup_root=temp / "backups",
            discovery_fixture_path=str(ROOT / "tests/fixtures/jobs.json"),
        )
        email = "restart@example.com"
        password = "ValidPass123"

        app1 = create_app(settings)
        with TestClient(app1) as client:
            page = client.get("/register")
            response = client.post("/register", data={
                "csrf_token": csrf(page.text), "email": email, "display_name": "Restart Test",
                "password": password, "password_confirm": password,
            }, follow_redirects=True)
            assert response.status_code == 200
            verify_link = latest_link(client, "verify")
            verify_page = client.get(verify_link)
            token = parse_qs(urlparse(verify_link).query).get("token", [""])[0]
            assert token
            response = client.post(
                "/verify-email",
                data={"csrf_token": csrf(verify_page.text), "token": token},
                follow_redirects=True,
            )
            assert "邮箱验证成功" in response.text
            page = client.get("/onboarding/upload")
            response = client.post(
                "/onboarding/upload", data={"csrf_token": csrf(page.text)},
                files={"resume": ("resume.txt", (ROOT / "tests/fixtures/resume.txt").read_bytes(), "text/plain")},
                follow_redirects=True,
            )
            response = client.post("/onboarding/confirm", data={
                "csrf_token": csrf(response.text), "primary_roles": "Finance, Data",
                "target_locations": "Sydney, Remote Australia",
                "work_authorization": "Australian full working rights",
                "sponsorship_now": "no", "sponsorship_future": "no",
                "work_modes": ["hybrid", "remote"], "relocation": "no",
                "available_start": "2026-11", "avoid_roles": "Sales", "avoid_industries": "Gambling",
            }, follow_redirects=True)
            assert "岗位推荐" in response.text
            with app1.state.session_factory() as db:
                user = db.scalar(select(User).where(User.is_admin.is_(False)))
                assert user
                profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
                assert profile and profile.last_discovery_at and profile.next_discovery_at
                assert profile.next_discovery_at - profile.last_discovery_at == timedelta(hours=6)
                count_before = len(db.scalars(select(Recommendation).where(Recommendation.user_id == user.id)).all())
                assert count_before > 0

        # New application object and engine against the same disk state.
        app2 = create_app(settings)
        with TestClient(app2) as client:
            page = client.get("/login")
            response = client.post("/login", data={
                "csrf_token": csrf(page.text), "email": email, "password": password,
            }, follow_redirects=True)
            assert response.status_code == 200 and "求职控制台" in response.text
            feed = client.get("/recommendations")
            assert feed.status_code == 200 and "Graduate Financial Analyst" in feed.text
            with app2.state.session_factory() as db:
                user = db.scalar(select(User).where(User.is_admin.is_(False)))
                profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
                count_after = len(db.scalars(select(Recommendation).where(Recommendation.user_id == user.id)).all())
                assert count_after == count_before
                assert profile.next_discovery_at - profile.last_discovery_at == timedelta(hours=6)

        result = {
            "verdict": "PASS", "synthetic_data_only": True,
            "application_instances": 2, "recommendations_before": count_before,
            "recommendations_after": count_after, "refresh_interval_hours": 6,
            "production_claimed": False,
        }
        code = 0
    except Exception as exc:
        result = {"verdict": "FAIL", "error_type": type(exc).__name__, "error": str(exc), "production_claimed": False}
        code = 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
