#!/usr/bin/env python3
"""Execute the critical JobHuntBot SaaS transaction on the real HTTPS deployment.

This script uses two synthetic acceptance accounts, the real SMTP/IMAP path, the
real background Worker, and a real Chromium browser. It deletes the synthetic
accounts at the end. It never prints mailbox passwords, application passwords,
DeepSeek credentials, cookies, verification tokens, or resume contents.
"""
from __future__ import annotations

import argparse
import email
import email.utils
import imaplib
import json
import os
import re
import time
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def derived_emails() -> tuple[str, str]:
    explicit_a = os.getenv("ACCEPTANCE_EMAIL_A", "").strip()
    explicit_b = os.getenv("ACCEPTANCE_EMAIL_B", "").strip()
    if explicit_a and explicit_b:
        return explicit_a, explicit_b
    base = env_required("ACCEPTANCE_EMAIL")
    if not bool_env("ACCEPTANCE_EMAIL_PLUS_ALIAS", True):
        raise RuntimeError("set ACCEPTANCE_EMAIL_A and ACCEPTANCE_EMAIL_B when plus aliases are disabled")
    local, sep, domain = base.partition("@")
    if not sep:
        raise RuntimeError("ACCEPTANCE_EMAIL is invalid")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{local}+jobhunt-a-{run_id}@{domain}", f"{local}+jobhunt-b-{run_id}@{domain}"


def message_text(msg: Message) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            parts.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(parts)


def imap_connection():
    host = env_required("ACCEPTANCE_IMAP_HOST")
    port = int(os.getenv("ACCEPTANCE_IMAP_PORT", "993"))
    use_ssl = bool_env("ACCEPTANCE_IMAP_SSL", True)
    if use_ssl:
        client = imaplib.IMAP4_SSL(host, port)
    else:
        client = imaplib.IMAP4(host, port)
        if bool_env("ACCEPTANCE_IMAP_STARTTLS", True):
            client.starttls()
    client.login(env_required("ACCEPTANCE_IMAP_USERNAME"), env_required("ACCEPTANCE_IMAP_PASSWORD"))
    return client


def wait_mail_link(recipient: str, kind: str, base_url: str, not_before: float) -> str:
    timeout = int(os.getenv("ACCEPTANCE_MAIL_TIMEOUT_SECONDS", "240"))
    folder = os.getenv("ACCEPTANCE_IMAP_FOLDER", "INBOX")
    required_path = "/verify-email" if kind == "verify" else "/reset-password"
    deadline = time.time() + timeout
    last_seen = ""
    while time.time() < deadline:
        client = imap_connection()
        try:
            status, _ = client.select(folder, readonly=True)
            if status != "OK":
                raise RuntimeError(f"cannot select IMAP folder {folder}")
            status, data = client.search(None, "ALL")
            if status != "OK":
                raise RuntimeError("IMAP search failed")
            ids = (data[0] or b"").split()[-120:]
            for message_id in reversed(ids):
                status, payload = client.fetch(message_id, "(RFC822)")
                if status != "OK" or not payload or not isinstance(payload[0], tuple):
                    continue
                msg = email.message_from_bytes(payload[0][1])
                date_value = msg.get("Date")
                if date_value:
                    try:
                        received = email.utils.parsedate_to_datetime(date_value)
                        if received.tzinfo is None:
                            received = received.replace(tzinfo=timezone.utc)
                        if received.timestamp() < not_before - 300:
                            continue
                    except Exception:
                        pass
                headers = " ".join(str(msg.get(name, "")) for name in ["To", "Delivered-To", "X-Original-To"])
                body = message_text(msg)
                hay = (headers + "\n" + body).casefold()
                if recipient.casefold() not in hay:
                    continue
                urls = re.findall(r"https?://[^\s<>\"]+", body)
                for candidate in urls:
                    candidate = candidate.rstrip(".,);]")
                    parsed = urlparse(candidate)
                    if candidate.startswith(base_url) and parsed.path == required_path:
                        return candidate
                last_seen = f"matching recipient found but no {kind} link"
        finally:
            try:
                client.logout()
            except Exception:
                pass
        time.sleep(4)
    raise RuntimeError(f"timed out waiting for {kind} email ({last_seen or 'no matching mail'})")


def expect_path(page: Page, prefix: str) -> None:
    if not urlparse(page.url).path.startswith(prefix):
        raise AssertionError(f"unexpected path {urlparse(page.url).path}; expected {prefix}")


def click_wait(page: Page, selector: str) -> None:
    page.locator(selector).click()
    page.wait_for_load_state("domcontentloaded")


def register_verify(page: Page, base_url: str, address: str, password: str, steps: list[str]) -> None:
    start = time.time()
    page.goto(f"{base_url}/register", wait_until="domcontentloaded")
    page.get_by_test_id("register-name").fill("Production Acceptance Candidate")
    page.get_by_test_id("register-email").fill(address)
    page.get_by_test_id("register-password").fill(password)
    page.get_by_test_id("register-password-confirm").fill(password)
    click_wait(page, '[data-testid="register-submit"]')
    expect_path(page, "/verify-required")
    link = wait_mail_link(address, "verify", base_url, start)
    page.goto(link, wait_until="domcontentloaded")
    expect_path(page, "/onboarding/upload")
    steps.extend(["register", "real_email_verification"])


def onboard_and_wait(page: Page, base_url: str, steps: list[str]) -> None:
    page.get_by_test_id("resume-file").set_input_files(str(ROOT / "tests/fixtures/resume.txt"))
    click_wait(page, '[data-testid="resume-upload-submit"]')
    expect_path(page, "/onboarding/confirm")
    page.get_by_test_id("confirm-roles").fill("Finance, Data, Business Analysis")
    page.get_by_test_id("confirm-locations").fill("Sydney, Melbourne, Remote Australia")
    page.get_by_test_id("confirm-work-authorization").fill("Australian full working rights")
    page.get_by_test_id("confirm-sponsorship-now").select_option("no")
    page.get_by_test_id("confirm-sponsorship-future").select_option("no")
    for value in ["remote", "hybrid", "onsite"]:
        box = page.locator(f'input[name="work_modes"][value="{value}"]')
        if not box.is_checked():
            box.check()
    page.get_by_test_id("confirm-relocation").select_option("no")
    page.get_by_test_id("confirm-available-start").fill("2026-11")
    page.get_by_test_id("confirm-avoid-roles").fill("Sales")
    page.get_by_test_id("confirm-avoid-industries").fill("Gambling")
    click_wait(page, '[data-testid="confirm-submit"]')
    expect_path(page, "/recommendations")
    deadline = time.time() + int(os.getenv("ACCEPTANCE_DISCOVERY_TIMEOUT_SECONDS", "300"))
    while time.time() < deadline:
        if page.get_by_test_id("job-card").count() > 0:
            steps.extend(["resume_upload", "confirm_high_impact_facts", "background_worker_discovery"])
            return
        page.wait_for_timeout(4000)
        page.reload(wait_until="domcontentloaded")
    raise RuntimeError("no automatic recommendation appeared before the discovery timeout")


def exercise_filters(page: Page, steps: list[str]) -> None:
    ids = [
        "filter-q", "filter-city", "filter-role", "filter-skill", "filter-source",
        "filter-freshness", "filter-qualification", "filter-relevance",
        "filter-opportunity", "filter-status",
    ]
    for testid in ids:
        node = page.get_by_test_id(testid)
        tag = node.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            values = [x.get_attribute("value") or "" for x in node.locator("option").all()]
            usable = [x for x in values if x]
            if usable:
                node.select_option(usable[0])
        else:
            node.fill("Analyst")
    click_wait(page, '[data-testid="filter-submit"]')
    page.get_by_test_id("recommendation-filters").wait_for()
    click_wait(page, '[data-testid="filter-clear"]')
    page.get_by_test_id("job-card").first.wait_for()
    steps.append("all_feed_filters")


def candidate_actions(page: Page, steps: list[str]) -> tuple[str, str]:
    exercise_filters(page, steps)
    page.get_by_test_id("job-detail-link").first.click()
    page.wait_for_load_state("domcontentloaded")
    detail_url = page.url
    official = page.get_by_test_id("official-job-link")
    parsed = urlparse(official.get_attribute("href") or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AssertionError("official job link is invalid")
    click_wait(page, '[data-testid="save-job"]')
    click_wait(page, '[data-testid="create-pack"]')
    pack_url = page.url
    page.get_by_test_id("pack-open-job").wait_for()
    click_wait(page, '[data-testid="pack-record-progress"]')
    page.get_by_test_id("application-status").select_option("submitted")
    page.get_by_test_id("application-evidence").fill("")
    click_wait(page, '[data-testid="application-submit"]')
    if not page.get_by_test_id("error-message").is_visible():
        raise AssertionError("submitted without evidence was accepted")
    page.get_by_test_id("application-status").select_option("submitted")
    page.get_by_test_id("application-evidence").fill("Acceptance ID PROD-SYNTHETIC")
    click_wait(page, '[data-testid="application-submit"]')
    steps.extend(["job_detail", "save_job", "application_pack", "submission_evidence_gate"])
    return detail_url, pack_url


def reset_password(page: Page, base_url: str, address: str, old_password: str, steps: list[str]) -> str:
    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    click_wait(page, '[data-testid="logout-button"]')
    start = time.time()
    page.goto(f"{base_url}/forgot-password", wait_until="domcontentloaded")
    page.get_by_test_id("forgot-email").fill(address)
    click_wait(page, '[data-testid="forgot-submit"]')
    link = wait_mail_link(address, "reset", base_url, start)
    page.goto(link, wait_until="domcontentloaded")
    new_password = "ProdResetPass123"
    page.get_by_test_id("reset-password").fill(new_password)
    page.get_by_test_id("reset-password-confirm").fill(new_password)
    click_wait(page, '[data-testid="reset-submit"]')
    page.goto(link, wait_until="domcontentloaded")
    page.get_by_test_id("reset-password").fill("TokenReuseShouldFail123")
    page.get_by_test_id("reset-password-confirm").fill("TokenReuseShouldFail123")
    click_wait(page, '[data-testid="reset-submit"]')
    if "无效或已过期" not in page.content():
        raise AssertionError("password reset token was reusable")
    page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    page.get_by_test_id("login-email").fill(address)
    page.get_by_test_id("login-password").fill(new_password)
    click_wait(page, '[data-testid="login-submit"]')
    expect_path(page, "/dashboard")
    steps.extend(["real_email_password_reset", "reset_token_single_use"])
    return new_password


def logout(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    click_wait(page, '[data-testid="logout-button"]')


def delete_account(page: Page, base_url: str, password: str) -> None:
    page.goto(f"{base_url}/settings/data", wait_until="domcontentloaded")
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_test_id("delete-password").fill(password)
    page.get_by_test_id("delete-confirmation").fill("删除我的账户")
    click_wait(page, '[data-testid="delete-account-submit"]')
    expect_path(page, "/")


def run(args: argparse.Namespace) -> tuple[dict, int]:
    base_url = env_required("BASE_URL").rstrip("/")
    if not base_url.startswith("https://"):
        return {"verdict": "BLOCKED", "reason": "BASE_URL is not HTTPS", "production_claimed": False}, 2
    email_a, email_b = derived_emails()
    password = os.getenv("ACCEPTANCE_ACCOUNT_PASSWORD", "ProdAcceptPass123").strip()
    steps: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    cleanup: dict[str, str] = {}
    try:
        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(
                headless=True,
                executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, ignore_https_errors=False)
            page = context.new_page()
            page.set_default_timeout(20000)
            page.set_default_navigation_timeout(30000)
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            page.goto(base_url, wait_until="domcontentloaded")
            if urlparse(page.url).scheme != "https":
                raise AssertionError("browser did not remain on HTTPS")
            register_verify(page, base_url, email_a, password, steps)
            onboard_and_wait(page, base_url, steps)
            detail_url, pack_url = candidate_actions(page, steps)
            password_a = reset_password(page, base_url, email_a, password, steps)
            cleanup[email_a] = password_a

            logout(page, base_url)
            register_verify(page, base_url, email_b, password, steps)
            onboard_and_wait(page, base_url, steps)
            cleanup[email_b] = password
            for target in [detail_url, pack_url]:
                response = page.request.get(target)
                if response.status != 404:
                    raise AssertionError(f"cross-tenant resource returned {response.status}")
            steps.append("two_user_tenant_isolation")
            delete_account(page, base_url, password)
            cleanup.pop(email_b, None)

            page.goto(f"{base_url}/login", wait_until="domcontentloaded")
            page.get_by_test_id("login-email").fill(email_a)
            page.get_by_test_id("login-password").fill(password_a)
            click_wait(page, '[data-testid="login-submit"]')
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"{base_url}/recommendations", wait_until="domcontentloaded")
            if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                raise AssertionError("mobile feed has horizontal overflow")
            steps.append("mobile_feed")
            page.set_viewport_size({"width": 1440, "height": 1100})
            delete_account(page, base_url, password_a)
            cleanup.pop(email_a, None)

            context.close()
            browser.close()

        unexpected_console = [item for item in console_errors if "favicon" not in item.casefold()]
        if unexpected_console:
            raise AssertionError("browser console errors: " + " | ".join(unexpected_console[:5]))
        if page_errors:
            raise AssertionError("browser page errors: " + " | ".join(page_errors[:5]))
        return {
            "verdict": "PASS",
            "scope": "real HTTPS, real SMTP/IMAP, real background discovery, two synthetic tenants and Chromium",
            "production_claimed": True,
            "base_url": base_url,
            "refresh_interval_hours": 6,
            "steps": steps,
            "step_count": len(steps),
            "synthetic_accounts_deleted": True,
            "console_errors": [],
            "page_errors": [],
            "secret_values_exposed": False,
        }, 0
    except Exception as exc:
        return {
            "verdict": "FAIL",
            "scope": "real production browser acceptance",
            "production_claimed": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "steps_completed": steps,
            "synthetic_accounts_requiring_cleanup": len(cleanup),
            "console_errors": console_errors[-20:],
            "page_errors": page_errors[-20:],
            "secret_values_exposed": False,
        }, 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/target-browser.json")
    args = parser.parse_args()
    result, code = run(args)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
