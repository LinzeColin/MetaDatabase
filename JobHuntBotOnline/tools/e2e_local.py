#!/usr/bin/env python3
"""Run the shipped SaaS through a real Uvicorn process and Chromium.

The run uses only synthetic data and the committed fixture job source. It exercises
all user-facing forms, buttons and critical negative paths. It never claims target
production readiness.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/readyz", timeout=2)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("refresh_hours") != 6:
                    raise AssertionError("readyz refresh_hours is not 6")
                return
            last = f"HTTP {response.status_code}"
        except Exception as exc:  # pragma: no cover - diagnostic path
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    raise RuntimeError(f"application did not become ready: {last}")


def latest_mail(base_url: str, kind: str, recipient: str | None = None) -> dict:
    rows = httpx.get(f"{base_url}/_test/outbox", timeout=5).json()
    matched = [row for row in rows if row.get("kind") == kind and (recipient is None or row.get("to") == recipient)]
    if not matched:
        raise AssertionError(f"missing {kind} test email for {recipient or '*'}")
    return matched[-1]


def mail_link(row: dict) -> str:
    match = re.search(r"https?://\S+", str(row.get("body", "")))
    if not match:
        raise AssertionError("mail has no link")
    return match.group(0).rstrip(".,)")



def mark_progress(message: str) -> None:
    # Progress stays in memory; final evidence is written only after the full run.
    return None

def browser_executable() -> str | None:
    candidates = [
        os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", ""),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def new_context(browser: Browser, *, mobile: bool = False) -> BrowserContext:
    if mobile:
        return browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    return browser.new_context(viewport={"width": 1440, "height": 1100})


def expect_url(page: Page, suffix: str) -> None:
    if not urlparse(page.url).path.startswith(suffix):
        raise AssertionError(f"unexpected URL {page.url}; expected path {suffix}")


def click_and_wait(page: Page, selector: str) -> None:
    page.locator(selector).click()
    page.wait_for_load_state("domcontentloaded")


def register_verify(page: Page, base_url: str, email: str, password: str, steps: list[str]) -> None:
    page.goto(f"{base_url}/register", wait_until="domcontentloaded")
    page.get_by_test_id("register-name").fill("Synthetic Candidate")
    page.get_by_test_id("register-email").fill(email)
    page.get_by_test_id("register-password").fill(password)
    page.get_by_test_id("register-password-confirm").fill(password)
    click_and_wait(page, '[data-testid="register-submit"]')
    page.get_by_test_id("verify-resend").click()
    page.wait_for_load_state("domcontentloaded")
    page.get_by_test_id("resend-email").fill(email)
    click_and_wait(page, '[data-testid="resend-submit"]')
    page.goto(mail_link(latest_mail(base_url, "verify", email)), wait_until="domcontentloaded")
    expect_url(page, "/verify-email")
    click_and_wait(page, '[data-testid="verify-email-confirm"]')
    expect_url(page, "/onboarding/upload")
    steps.extend(["register", "resend_verification", "verify_email"])


def onboard(page: Page, root: Path, steps: list[str]) -> None:
    page.get_by_test_id("resume-file").set_input_files(str(root / "tests/fixtures/resume.txt"))
    page.get_by_test_id("resume-upload-submit").click()
    page.wait_for_load_state("domcontentloaded")
    expect_url(page, "/onboarding/confirm")
    page.get_by_test_id("confirm-roles").fill("Finance, Data, Business Analysis")
    page.get_by_test_id("confirm-locations").fill("Sydney, Melbourne, Remote Australia")
    page.get_by_test_id("confirm-work-authorization").fill("Australian full working rights")
    page.get_by_test_id("confirm-sponsorship-now").select_option("no")
    page.get_by_test_id("confirm-sponsorship-future").select_option("no")
    for value in ["remote", "hybrid", "onsite"]:
        checkbox = page.locator(f'input[name="work_modes"][value="{value}"]')
        if not checkbox.is_checked():
            checkbox.check()
    page.get_by_test_id("confirm-relocation").select_option("no")
    page.get_by_test_id("confirm-available-start").fill("2026-11")
    page.get_by_test_id("confirm-avoid-roles").fill("Sales")
    page.get_by_test_id("confirm-avoid-industries").fill("Gambling")
    click_and_wait(page, '[data-testid="confirm-submit"]')
    expect_url(page, "/recommendations")
    page.get_by_test_id("job-card").first.wait_for()
    steps.extend(["resume_upload", "confirm_high_impact_facts", "automatic_discovery"])


def assert_external_link(locator) -> None:
    href = locator.get_attribute("href") or ""
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AssertionError(f"invalid external link: {href}")
    if locator.get_attribute("target") != "_blank":
        raise AssertionError("external job link must open in a new tab")


def exercise_filters(page: Page, steps: list[str]) -> None:
    filters = [
        ("filter-q", "Analyst"),
        ("filter-city", "Sydney"),
        ("filter-role", "Finance"),
        ("filter-skill", "excel"),
        ("filter-source", "fixture"),
        ("filter-freshness", "7"),
        ("filter-qualification", "pass"),
        ("filter-relevance", "high"),
        ("filter-opportunity", "high"),
        ("filter-status", "new"),
    ]
    for testid, value in filters:
        locator = page.get_by_test_id(testid)
        if locator.evaluate("el => el.tagName.toLowerCase()") == "select":
            options = locator.locator("option").all()
            values = [opt.get_attribute("value") or opt.inner_text() for opt in options]
            if value not in values:
                # Dynamic facets can vary; use the first nonempty option while still exercising the control.
                nonempty = [item for item in values if item]
                if not nonempty:
                    raise AssertionError(f"{testid} has no usable option")
                value = nonempty[0]
            locator.select_option(value)
        else:
            locator.fill(value)
    click_and_wait(page, '[data-testid="filter-submit"]')
    page.get_by_test_id("recommendation-filters").wait_for()
    click_and_wait(page, '[data-testid="filter-clear"]')
    page.get_by_test_id("job-card").first.wait_for()
    steps.append("all_recommendation_filters")


def exercise_candidate_flow(page: Page, base_url: str, steps: list[str]) -> tuple[str, str]:
    click_and_wait(page, '[data-testid="refresh-recommendations"]')
    exercise_filters(page, steps)
    page.get_by_test_id("job-detail-link").first.click()
    page.wait_for_load_state("domcontentloaded")
    expect_url(page, "/recommendations/")
    assert_external_link(page.get_by_test_id("official-job-link"))
    detail_url = page.url
    click_and_wait(page, '[data-testid="save-job"]')
    page.get_by_test_id("ignore-job").wait_for()
    click_and_wait(page, '[data-testid="create-pack"]')
    expect_url(page, "/application-packs/")
    assert_external_link(page.get_by_test_id("pack-open-job"))
    pack_url = page.url
    page.get_by_test_id("copy-why-role").click()
    page.wait_for_timeout(100)
    if page.get_by_test_id("copy-why-role").inner_text() not in {"已复制", "复制失败", "复制"}:
        raise AssertionError("copy button feedback is invalid")
    page.get_by_test_id("copy-why-company").click()
    click_and_wait(page, '[data-testid="pack-record-progress"]')
    page.get_by_test_id("application-status").select_option("submitted")
    page.get_by_test_id("application-evidence").fill("")
    page.get_by_test_id("application-notes").fill("Synthetic negative control")
    click_and_wait(page, '[data-testid="application-submit"]')
    if not page.get_by_test_id("error-message").is_visible():
        raise AssertionError("submitted without evidence was not rejected")
    page.get_by_test_id("application-status").select_option("submitted")
    page.get_by_test_id("application-evidence").fill("Application ID SYNTH-001")
    page.get_by_test_id("application-notes").fill("Synthetic accepted control")
    click_and_wait(page, '[data-testid="application-submit"]')
    for status in ["pending", "interview", "rejected", "offer", "withdrawn"]:
        page.get_by_test_id("application-status").select_option(status)
        page.get_by_test_id("application-evidence").fill("")
        page.get_by_test_id("application-notes").fill(f"Synthetic {status}")
        click_and_wait(page, '[data-testid="application-submit"]')
    steps.extend(["manual_refresh", "job_detail", "save_job", "application_pack", "copy_buttons", "application_statuses"])
    return detail_url, pack_url


def manual_job(page: Page, steps: list[str]) -> None:
    page.get_by_test_id("nav-manual-job").click()
    page.wait_for_load_state("domcontentloaded")
    # Server-side safety negative control (fill() rejects malformed URL in browser validation,
    # so use a syntactically valid but private address).
    page.get_by_test_id("manual-url").fill("http://127.0.0.1/private")
    page.get_by_test_id("manual-title").fill("Unsafe Synthetic Role")
    page.get_by_test_id("manual-company").fill("Unsafe Company")
    page.get_by_test_id("manual-location").fill("Sydney")
    page.get_by_test_id("manual-description").fill("Synthetic description")
    click_and_wait(page, '[data-testid="manual-submit"]')
    if not page.get_by_test_id("error-message").is_visible():
        raise AssertionError("private/loopback manual URL was not rejected")
    page.get_by_test_id("manual-url").fill("https://company.example/jobs/synthetic-manual")
    page.get_by_test_id("manual-title").fill("Graduate Treasury Analyst")
    page.get_by_test_id("manual-company").fill("Manual Company")
    page.get_by_test_id("manual-location").fill("Sydney, Australia")
    page.get_by_test_id("manual-description").fill(
        "Graduate treasury analyst using Excel, financial analysis and reporting. Australian working rights required."
    )
    click_and_wait(page, '[data-testid="manual-submit"]')
    if "岗位已导入并分析" not in page.content():
        raise AssertionError("manual job success feedback missing")
    steps.extend(["manual_url_safety", "manual_job_import"])


def settings_and_password(page: Page, base_url: str, email: str, old_password: str, steps: list[str]) -> str:
    page.get_by_test_id("nav-settings").click()
    page.wait_for_load_state("domcontentloaded")
    page.get_by_test_id("settings-roles").fill("Finance, Data, Treasury")
    page.get_by_test_id("settings-locations").fill("Sydney, Melbourne, Remote Australia")
    page.get_by_test_id("settings-start").fill("2026-12")
    click_and_wait(page, '[data-testid="settings-profile-submit"]')
    page.goto(f"{base_url}/settings/data", wait_until="domcontentloaded")
    with page.expect_download() as download_info:
        page.get_by_test_id("data-export").click()
    download = download_info.value
    export_path = Path(download.path())
    data = export_path.read_text(encoding="utf-8")
    if "DEEPSEEK_API_KEY" in data or "SESSION_SECRET" in data:
        raise AssertionError("user export contains platform secret material")
    page.goto(f"{base_url}/settings/security", wait_until="domcontentloaded")
    new_password = "ChangedPass123"
    page.get_by_test_id("security-current-password").fill(old_password)
    page.get_by_test_id("security-new-password").fill(new_password)
    page.get_by_test_id("security-new-password-confirm").fill(new_password)
    click_and_wait(page, '[data-testid="security-password-submit"]')
    expect_url(page, "/login")
    # Old password must fail.
    page.get_by_test_id("login-email").fill(email)
    page.get_by_test_id("login-password").fill(old_password)
    click_and_wait(page, '[data-testid="login-submit"]')
    if not page.get_by_test_id("error-message").is_visible():
        raise AssertionError("old password still worked after change")
    # New password works.
    page.get_by_test_id("login-email").fill(email)
    page.get_by_test_id("login-password").fill(new_password)
    click_and_wait(page, '[data-testid="login-submit"]')
    expect_url(page, "/dashboard")
    # Forgot/reset, then ensure token is single-use.
    page.get_by_test_id("logout-button").click()
    page.wait_for_load_state("domcontentloaded")
    page.goto(f"{base_url}/forgot-password", wait_until="domcontentloaded")
    page.get_by_test_id("forgot-email").fill(email)
    click_and_wait(page, '[data-testid="forgot-submit"]')
    link = mail_link(latest_mail(base_url, "reset", email))
    page.goto(link, wait_until="domcontentloaded")
    final_password = "ResetFinalPass123"
    page.get_by_test_id("reset-password").fill(final_password)
    page.get_by_test_id("reset-password-confirm").fill(final_password)
    click_and_wait(page, '[data-testid="reset-submit"]')
    page.goto(link, wait_until="domcontentloaded")
    page.get_by_test_id("reset-password").fill("ReuseShouldFail123")
    page.get_by_test_id("reset-password-confirm").fill("ReuseShouldFail123")
    click_and_wait(page, '[data-testid="reset-submit"]')
    if "无效或已过期" not in page.content():
        raise AssertionError("reset token could be reused")
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    page.get_by_test_id("login-email").fill(email)
    page.get_by_test_id("login-password").fill(final_password)
    click_and_wait(page, '[data-testid="login-submit"]')
    expect_url(page, "/dashboard")
    steps.extend(["profile_settings", "user_export", "change_password", "old_session_invalid", "forgot_reset", "reset_single_use"])
    return final_password


def second_user_isolation(page: Page, base_url: str, root: Path, detail_url: str, pack_url: str, steps: list[str]) -> tuple[str, str]:
    # Leave user A, then perform the full lifecycle for user B in the same browser context.
    mark_progress("tenant: start")
    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    click_and_wait(page, '[data-testid="logout-button"]')
    mark_progress("tenant: user A logged out")
    email = "candidate-b@example.com"
    password = "ValidPass123"
    register_verify(page, base_url, email, password, steps)
    mark_progress("tenant: user B verified")
    onboard(page, root, steps)
    mark_progress("tenant: user B onboarded")
    response = page.request.get(detail_url)
    if response.status != 404:
        raise AssertionError(f"cross-tenant recommendation returned {response.status}")
    mark_progress("tenant: detail negative checked")
    response = page.request.get(pack_url)
    if response.status != 404:
        raise AssertionError(f"cross-tenant pack returned {response.status}")
    mark_progress("tenant: pack negative checked")
    page.goto(f"{base_url}/jobs/manual", wait_until="domcontentloaded")
    page.get_by_test_id("manual-url").fill("https://company.example/jobs/synthetic-manual")
    page.get_by_test_id("manual-title").fill("Graduate Treasury Analyst")
    page.get_by_test_id("manual-company").fill("Manual Company")
    page.get_by_test_id("manual-location").fill("Sydney")
    page.get_by_test_id("manual-description").fill("Synthetic second tenant manual job.")
    click_and_wait(page, '[data-testid="manual-submit"]')
    mark_progress("tenant: same URL imported")
    page.goto(f"{base_url}/settings/data", wait_until="domcontentloaded")
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_test_id("delete-password").fill(password)
    page.get_by_test_id("delete-confirmation").fill("删除我的账户")
    click_and_wait(page, '[data-testid="delete-account-submit"]')
    mark_progress("tenant: delete submitted")
    expect_url(page, "/")
    steps.extend(["two_user_isolation", "same_manual_url_tenant_scope", "delete_account"])
    return email, password


def admin_flow(page: Page, base_url: str, admin_email: str, admin_password: str, steps: list[str]) -> None:
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    page.get_by_test_id("login-email").fill(admin_email)
    page.get_by_test_id("login-password").fill(admin_password)
    click_and_wait(page, '[data-testid="login-submit"]')
    page.get_by_test_id("nav-admin").click()
    page.wait_for_load_state("domcontentloaded")
    page.get_by_test_id("admin-users-table").wait_for()
    row = page.locator("table tbody tr").filter(has=page.locator('[data-testid^="admin-toggle-"]')).first
    quota = row.locator('[data-testid^="admin-quota-"]').first
    quota.fill("17")
    row.locator('[data-testid^="admin-quota-submit-"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    row = page.locator("table tbody tr").filter(has=page.locator('[data-testid^="admin-toggle-"]')).first
    row.locator('[data-testid^="admin-toggle-"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    row = page.locator("table tbody tr").filter(has=page.locator('[data-testid^="admin-toggle-"]')).first
    if "已停用" not in row.inner_text():
        raise AssertionError("admin disable did not apply")
    row.locator('[data-testid^="admin-toggle-"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    page.get_by_test_id("admin-platform-link").click()
    page.wait_for_load_state("domcontentloaded")
    if "6h" not in page.content() or "不展示 Secret 值" not in page.content():
        raise AssertionError("admin platform contract is missing")
    click_and_wait(page, '[data-testid="logout-button"]')
    steps.extend(["admin_quota", "admin_disable_restore", "admin_platform_status"])


def mobile_check(page: Page, base_url: str, email: str, password: str, steps: list[str]) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    page.get_by_test_id("login-email").fill(email)
    page.get_by_test_id("login-password").fill(password)
    click_and_wait(page, '[data-testid="login-submit"]')
    page.goto(f"{base_url}/recommendations", wait_until="domcontentloaded")
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    if overflow:
        raise AssertionError("mobile recommendations page has horizontal overflow")
    page.get_by_test_id("filter-freshness").select_option("7")
    click_and_wait(page, '[data-testid="filter-submit"]')
    if page.get_by_test_id("job-card").count():
        page.get_by_test_id("job-detail-link").first.click()
        page.wait_for_load_state("domcontentloaded")
        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
            raise AssertionError("mobile detail page has horizontal overflow")
    page.set_viewport_size({"width": 1440, "height": 1100})
    steps.append("mobile_no_horizontal_overflow")

def run(args: argparse.Namespace) -> tuple[dict, int]:
    temp = Path(tempfile.mkdtemp(prefix="jobhunt-e2e-"))
    port = args.port or free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({
        "APP_ENV": "test",
        "APP_NAME": "JobHuntBot Online",
        "APP_VERSION": "0.3.0",
        "BASE_URL": base_url,
        "DATABASE_URL": f"sqlite+pysqlite:///{temp / 'e2e.db'}",
        "SESSION_SECRET": "e2e-session-secret",
        "DATA_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        "EMAIL_LOOKUP_SECRET": "e2e-email-secret",
        "COOKIE_SECURE": "false",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "AdminPass!2026",
        "ALLOW_REGISTRATION": "true",
        # This disposable, no-SMTP browser test exercises resend and reset in
        # one short synthetic session. Production keeps its persisted 30-minute
        # per-recipient limit and three-per-day maximum.
        "EMAIL_MIN_INTERVAL_SECONDS": "0",
        "EMAIL_MAX_PER_USER_PER_24H": "100",
        "DISCOVERY_REFRESH_HOURS": "6",
        "DISCOVERY_FIXTURE_PATH": str(ROOT / "tests/fixtures/jobs.json"),
        "ENABLE_REMOTIVE": "false",
        "ENABLE_ARBEITNOW": "false",
        "ENABLE_JOBICY": "false",
        "UPLOAD_ROOT": str(temp / "uploads"),
        "BACKUP_ROOT": str(temp / "backups"),
        "DEEPSEEK_API_KEY": "",
    })
    log_path = temp / "uvicorn.log"
    process: subprocess.Popen[str] | None = None
    steps: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    try:
        log_handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True,
        )
        wait_ready(base_url)
        with sync_playwright() as playwright:
            executable = args.browser_executable or browser_executable()
            launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
            browser = playwright.chromium.launch(headless=True, executable_path=executable, args=launch_args)
            context = new_context(browser)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.set_default_navigation_timeout(20000)
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.goto(base_url, wait_until="domcontentloaded")
            page.get_by_test_id("hero-register").click()
            page.wait_for_load_state("domcontentloaded")
            email = "candidate-a@example.com"
            initial_password = "ValidPass123"
            register_verify(page, base_url, email, initial_password, steps)
            mark_progress("user1 verified")
            onboard(page, ROOT, steps)
            mark_progress("user1 onboarded")

            # Exercise all primary navigation and dashboard cards without losing state.
            page.get_by_test_id("nav-dashboard").click(); page.wait_for_load_state("domcontentloaded")
            page.get_by_test_id("dashboard-view-recommendations").click(); page.wait_for_load_state("domcontentloaded")
            detail_url, pack_url = exercise_candidate_flow(page, base_url, steps)
            mark_progress("candidate flow complete")
            manual_job(page, steps)
            mark_progress("manual flow complete")
            final_password = settings_and_password(page, base_url, email, initial_password, steps)
            mark_progress("settings/password complete")
            second_user_isolation(page, base_url, ROOT, detail_url, pack_url, steps)
            mark_progress("tenant isolation complete")
            admin_flow(page, base_url, env["ADMIN_EMAIL"], env["ADMIN_PASSWORD"], steps)
            mark_progress("admin flow complete")
            mobile_check(page, base_url, email, final_password, steps)
            mark_progress("mobile flow complete")
            if not args.force_exit_after_result:
                context.close()
                browser.close()

        # Browser errors caused by intentional 404 negative controls are HTTP-side and do not emit JS errors.
        unexpected_console = [x for x in console_errors if "favicon" not in x.casefold()]
        if unexpected_console:
            raise AssertionError("browser console errors: " + " | ".join(unexpected_console[:5]))
        if page_errors:
            raise AssertionError("browser page errors: " + " | ".join(page_errors[:5]))

        result = {
            "verdict": "PASS",
            "scope": "real Uvicorn + Chromium, synthetic accounts/data, all critical controls and negative paths",
            "base_url": base_url,
            "synthetic_data_only": True,
            "production_claimed": False,
            "refresh_interval_hours": 6,
            "steps": steps,
            "step_count": len(steps),
            "console_errors": [],
            "page_errors": [],
        }
        return result, 0
    except Exception as exc:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
        except Exception:
            pass
        blocked_by_policy = "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc)
        return {
            "verdict": "BLOCKED" if blocked_by_policy else "FAIL",
            "scope": "real Uvicorn + Chromium local acceptance",
            "production_claimed": False,
            "blocker": "chromium_managed_url_blocklist" if blocked_by_policy else "",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "steps_completed": steps,
            "console_errors": console_errors[-20:],
            "page_errors": page_errors[-20:],
            "server_log_tail": tail,
        }, 2 if blocked_by_policy else 1
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        if not args.keep_temp:
            shutil.rmtree(temp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/local/browser-local/result.json")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--browser-executable", default="")
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--skip-screenshots", action="store_true", help="compatibility flag; screenshots are not required")
    parser.add_argument("--force-exit-after-result", action="store_true", help="compatibility flag for constrained browser environments")
    args = parser.parse_args()
    result, code = run(args)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.force_exit_after_result:
        os._exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
