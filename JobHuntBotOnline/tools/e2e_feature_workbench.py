#!/usr/bin/env python3
"""Read-only browser verification for the JobHuntBot application workspace.

This deliberately does not run the email lifecycle and must never be used to
claim complete production acceptance.  It creates one short-lived session for
an existing verified account, performs only GET/browser-filter operations, and
revokes that session before writing its small, non-sensitive receipt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from sqlalchemy import func, or_, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import Job, Recommendation, User
from app.security import create_session, revoke_session


def _write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("base URL must be an https URL")
    return value.rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    parser.add_argument("--output", default="evidence/target-feature-workbench.json")
    args = parser.parse_args()
    output = Path(args.output)
    settings = get_settings()
    result = {
        "verdict": "FAIL",
        "scope": "real HTTPS read-only workspace browser verification",
        "email_delivery_sent": False,
        "provider_ai_called": False,
        "production_claimed": False,
        "full_production_pass_still_requires_real_email_lifecycle": True,
    }
    raw_session: str | None = None
    factory = make_session_factory(make_engine(settings.database_url))
    try:
        base_url = _base_url(args.base_url or settings.base_url)
        with factory() as db:
            row = db.execute(
                select(User, Recommendation, Job)
                .join(Recommendation, Recommendation.user_id == User.id)
                .join(Job, Job.id == Recommendation.job_id)
                .where(
                    User.is_active.is_(True),
                    User.is_verified.is_(True),
                    Job.role_family != "",
                    or_(Job.owner_user_id.is_(None), Job.owner_user_id == User.id),
                )
                .order_by(Recommendation.rank_score.desc(), Recommendation.id.desc())
            ).first()
            if not row:
                raise RuntimeError("no verified account with an accessible recommendation is available")
            user, recommendation, job = row
            role = job.role_family
            expected_all = db.scalar(
                select(func.count(Recommendation.id))
                .join(Job, Job.id == Recommendation.job_id)
                .where(
                    Recommendation.user_id == user.id,
                    or_(Job.owner_user_id.is_(None), Job.owner_user_id == user.id),
                )
            ) or 0
            expected_role = db.scalar(
                select(func.count(Recommendation.id))
                .join(Job, Job.id == Recommendation.job_id)
                .where(
                    Recommendation.user_id == user.id,
                    Job.role_family == role,
                    or_(Job.owner_user_id.is_(None), Job.owner_user_id == user.id),
                )
            ) or 0
            raw_session, _session = create_session(db, user, settings)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            context.add_cookies([{
                "name": "jobhunt_session",
                "value": raw_session,
                "url": base_url,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }])
            page = context.new_page()
            page.goto(f"{base_url}/recommendations", wait_until="networkidle")
            page.wait_for_load_state("networkidle")
            if page.locator("[data-testid='recommendation-results']").count() != 1:
                raise RuntimeError("recommendation result region is unavailable")
            with page.expect_response(lambda response: "/recommendations" in response.url and "partial=true" in response.url):
                page.locator("[data-testid='filter-relevance']").select_option(value="")
            page.wait_for_load_state("networkidle")
            all_count = page.locator("[data-testid='job-card']").count()
            with page.expect_response(lambda response: "/recommendations" in response.url and "partial=true" in response.url):
                page.locator("[data-testid='filter-role']").select_option(label=role)
            page.wait_for_load_state("networkidle")
            role_count = page.locator("[data-testid='job-card']").count()
            if all_count != expected_all or role_count != expected_role:
                raise RuntimeError("live filter result count differs from the server-side record count")
            if "partial=true" in page.url or "role=" not in page.url:
                raise RuntimeError("live filter did not keep a clean, selected URL state")

            page.goto(f"{base_url}/recommendations/{recommendation.id}/ai", wait_until="networkidle")
            page.wait_for_load_state("networkidle")
            if page.locator("[data-testid='ai-consult-form']").count() != 1:
                raise RuntimeError("AI consultation entry is unavailable")
            page.goto(f"{base_url}/applications", wait_until="networkidle")
            page.wait_for_load_state("networkidle")
            if page.locator("[data-testid='application-event-form']").count() != 1:
                raise RuntimeError("application progress workspace is unavailable")
            context.close()
            browser.close()

        result.update({
            "verdict": "PASS",
            "live_filter_server_count": expected_all,
            "live_filter_role_count": expected_role,
            "ai_consultation_entry": True,
            "application_progress_workspace": True,
        })
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    finally:
        if raw_session:
            with factory() as db:
                revoke_session(db, raw_session)
        _write_result(output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
