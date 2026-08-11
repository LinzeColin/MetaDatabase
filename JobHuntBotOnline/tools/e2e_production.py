#!/usr/bin/env python3
"""Execute the critical JobHuntBot SaaS transaction on the real HTTPS deployment.

This script uses two synthetic acceptance accounts, the real SMTP/IMAP path, the
real background Worker, and a real Chromium browser. It deletes the synthetic
accounts at the end. It never prints mailbox passwords, application passwords,
DeepSeek credentials, cookies, verification tokens, or resume contents. When
the email lifecycle prerequisites are deliberately unavailable, it reports
EMAIL_ONLY_BLOCKED before creating an account or sending email.
"""
from __future__ import annotations

import argparse
import email
import email.utils
import fcntl
import imaplib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MIN_ACCEPTANCE_EMAIL_GAP_SECONDS = 1800
MIN_REAL_EMAIL_COOLDOWN_HOURS = 24
MAX_REAL_EMAIL_MESSAGES = 3
DEFAULT_IMAP_CONNECT_TIMEOUT_SECONDS = 20
MAX_IMAP_CONNECT_TIMEOUT_SECONDS = 60
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,79}$")


def env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def acceptance_minimum_email_gap_seconds() -> int:
    raw = os.getenv("ACCEPTANCE_MIN_EMAIL_GAP_SECONDS", str(MIN_ACCEPTANCE_EMAIL_GAP_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("ACCEPTANCE_MIN_EMAIL_GAP_SECONDS must be an integer") from exc
    if value < MIN_ACCEPTANCE_EMAIL_GAP_SECONDS:
        raise RuntimeError(
            f"ACCEPTANCE_MIN_EMAIL_GAP_SECONDS must be at least {MIN_ACCEPTANCE_EMAIL_GAP_SECONDS}"
        )
    return value


def acceptance_real_email_cooldown_hours() -> int:
    raw = os.getenv("ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS", str(MIN_REAL_EMAIL_COOLDOWN_HOURS)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS must be an integer") from exc
    if value < MIN_REAL_EMAIL_COOLDOWN_HOURS:
        raise RuntimeError(
            f"ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS must be at least {MIN_REAL_EMAIL_COOLDOWN_HOURS}"
        )
    return value


def imap_connect_timeout_seconds() -> int:
    raw = os.getenv("ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS", str(DEFAULT_IMAP_CONNECT_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS must be an integer") from exc
    if not 1 <= value <= MAX_IMAP_CONNECT_TIMEOUT_SECONDS:
        raise RuntimeError(
            f"ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS must be between 1 and {MAX_IMAP_CONNECT_TIMEOUT_SECONDS}"
        )
    return value


def has_distinct_acceptance_recipients() -> bool:
    first = os.getenv("ACCEPTANCE_EMAIL_A", "").strip()
    second = os.getenv("ACCEPTANCE_EMAIL_B", "").strip()
    return bool(first and second and first.casefold() != second.casefold())


def acceptance_run_id() -> str:
    value = os.getenv("REAL_EMAIL_ACCEPTANCE_RUN_ID", "").strip()
    if not RUN_ID_RE.fullmatch(value):
        raise RuntimeError("REAL_EMAIL_ACCEPTANCE_RUN_ID is missing or invalid")
    return value


def real_email_guard_path() -> Path:
    return ROOT / "runtime-data" / "real-email-acceptance-guard.json"


def reserve_real_email_acceptance(
    *,
    state_path: Path,
    run_id: str,
    cooldown_hours: int,
    minimum_gap_seconds: int,
) -> None:
    """Persist a one-shot reservation before any browser action can send mail.

    The state has no recipient, credential, or candidate information.  It is
    placed under runtime-data so deployment-runtime verification treats it as
    operational state rather than distributable taskpack source.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_name(state_path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            now = datetime.now(timezone.utc)
            if state_path.exists():
                try:
                    previous = json.loads(state_path.read_text(encoding="utf-8"))
                    if not isinstance(previous, dict) or previous.get("version") != 1:
                        raise ValueError("unexpected state shape")
                    previous_run_id = previous.get("run_id")
                    cooldown_until = datetime.fromisoformat(str(previous["cooldown_until"]).replace("Z", "+00:00"))
                    if cooldown_until.tzinfo is None or not isinstance(previous_run_id, str):
                        raise ValueError("invalid state values")
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise RuntimeError("real email acceptance guard state is invalid; refusing to send") from exc
                if previous_run_id == run_id:
                    raise RuntimeError("real email acceptance run id has already been consumed")
                if cooldown_until > now:
                    raise RuntimeError("real email acceptance is within its cooldown; refusing to send")

            cooldown_until = now + timedelta(hours=cooldown_hours)
            payload = {
                "version": 1,
                "run_id": run_id,
                "reserved_at": now.isoformat().replace("+00:00", "Z"),
                "cooldown_until": cooldown_until.isoformat().replace("+00:00", "Z"),
                "minimum_email_gap_seconds": minimum_gap_seconds,
                "maximum_real_messages": MAX_REAL_EMAIL_MESSAGES,
            }
            temporary = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, state_path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class EmailPacer:
    def __init__(self, minimum_gap_seconds: int):
        self.minimum_gap_seconds = minimum_gap_seconds
        self._last_request_at: float | None = None

    def wait_before_request(self) -> None:
        if self._last_request_at is not None:
            remaining = self.minimum_gap_seconds - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()


def email_lifecycle_preflight() -> dict[str, object] | None:
    """Return a truthful email-only block before the browser transaction starts."""
    registration_enabled = bool_env("ALLOW_REGISTRATION", False)
    standard_smtp_configured = bool(os.getenv("SMTP_HOST", "").strip())
    acceptance_recipient_configured = has_distinct_acceptance_recipients()
    acceptance_imap_configured = all(
        os.getenv(name, "").strip()
        for name in ("ACCEPTANCE_IMAP_HOST", "ACCEPTANCE_IMAP_USERNAME", "ACCEPTANCE_IMAP_PASSWORD")
    )
    real_email_opt_in = bool_env("RUN_REAL_EMAIL_ACCEPTANCE", False)
    real_email_run_id_configured = bool(RUN_ID_RE.fullmatch(os.getenv("REAL_EMAIL_ACCEPTANCE_RUN_ID", "").strip()))
    pacing_configured = True
    imap_timeout_configured = True
    try:
        acceptance_minimum_email_gap_seconds()
        acceptance_real_email_cooldown_hours()
    except RuntimeError:
        pacing_configured = False
    try:
        imap_connect_timeout_seconds()
    except RuntimeError:
        imap_timeout_configured = False
    missing: list[str] = []
    if not registration_enabled:
        missing.append("ALLOW_REGISTRATION=true")
    if not standard_smtp_configured:
        missing.append("standard SMTP_HOST")
    if not acceptance_recipient_configured:
        missing.append("two distinct dedicated acceptance recipients")
    if not acceptance_imap_configured:
        missing.append("acceptance IMAP mailbox")
    if not real_email_opt_in:
        missing.append("RUN_REAL_EMAIL_ACCEPTANCE=true")
    if not real_email_run_id_configured:
        missing.append("valid REAL_EMAIL_ACCEPTANCE_RUN_ID")
    if not pacing_configured:
        missing.append("email pacing safety configuration")
    if not imap_timeout_configured:
        missing.append("IMAP connection timeout safety configuration")
    if not missing:
        return None
    return {
        "verdict": "BLOCKED",
        "blocker": "EMAIL_ONLY_BLOCKED",
        "scope": "real HTTPS email lifecycle preflight",
        "reason": "email lifecycle prerequisites are not configured",
        "missing_prerequisites": missing,
        "registration_enabled": registration_enabled,
        "standard_smtp_configured": standard_smtp_configured,
        "acceptance_recipient_configured": acceptance_recipient_configured,
        "acceptance_imap_configured": acceptance_imap_configured,
        "real_email_opt_in": real_email_opt_in,
        "real_email_run_id_configured": real_email_run_id_configured,
        "pacing_configured": pacing_configured,
        "imap_timeout_configured": imap_timeout_configured,
        "smtp_contract": "standards-compatible SMTP",
        "nitrosend_dependency": False,
        "email_delivery_sent": False,
        "synthetic_accounts_created": False,
        "full_production_pass_still_requires_real_email_lifecycle": True,
        "production_claimed": False,
        "secret_values_exposed": False,
    }


def derived_emails() -> tuple[str, str]:
    explicit_a = os.getenv("ACCEPTANCE_EMAIL_A", "").strip()
    explicit_b = os.getenv("ACCEPTANCE_EMAIL_B", "").strip()
    if explicit_a and explicit_b and explicit_a.casefold() != explicit_b.casefold():
        return explicit_a, explicit_b
    raise RuntimeError("set two distinct dedicated ACCEPTANCE_EMAIL_A and ACCEPTANCE_EMAIL_B values")


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
    connect_timeout = imap_connect_timeout_seconds()
    use_ssl = bool_env("ACCEPTANCE_IMAP_SSL", True)
    if use_ssl:
        client = imaplib.IMAP4_SSL(host, port, timeout=connect_timeout)
    else:
        client = imaplib.IMAP4(host, port, timeout=connect_timeout)
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
        client = None
        try:
            client = imap_connection()
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
        except (OSError, imaplib.IMAP4.error):
            # A bounded socket timeout or transient IMAP failure must consume
            # only this polling attempt.  It never triggers a second SMTP
            # request; the browser keeps waiting until the overall deadline.
            last_seen = "IMAP connection or request unavailable"
        finally:
            if client is not None:
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


def register_verify(
    page: Page,
    base_url: str,
    address: str,
    password: str,
    steps: list[str],
    pacer: EmailPacer,
) -> None:
    start = time.time()
    page.goto(f"{base_url}/register", wait_until="domcontentloaded")
    page.get_by_test_id("register-name").fill("Production Acceptance Candidate")
    page.get_by_test_id("register-email").fill(address)
    page.get_by_test_id("register-password").fill(password)
    page.get_by_test_id("register-password-confirm").fill(password)
    pacer.wait_before_request()
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


def reset_password(
    page: Page,
    base_url: str,
    address: str,
    old_password: str,
    steps: list[str],
    pacer: EmailPacer,
) -> str:
    page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
    click_wait(page, '[data-testid="logout-button"]')
    start = time.time()
    page.goto(f"{base_url}/forgot-password", wait_until="domcontentloaded")
    page.get_by_test_id("forgot-email").fill(address)
    pacer.wait_before_request()
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
    # This helper is used twice in one browser context. Registering a persistent
    # listener would make the second confirmation attempt accept the same dialog
    # twice and leak a harness error into otherwise clean production evidence.
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_test_id("delete-password").fill(password)
    page.get_by_test_id("delete-confirmation").fill("删除我的账户")
    click_wait(page, '[data-testid="delete-account-submit"]')
    expect_path(page, "/")


def run(args: argparse.Namespace) -> tuple[dict, int]:
    base_url = env_required("BASE_URL").rstrip("/")
    if not base_url.startswith("https://"):
        return {"verdict": "BLOCKED", "reason": "BASE_URL is not HTTPS", "production_claimed": False}, 2
    preflight = email_lifecycle_preflight()
    if preflight:
        return preflight, 2
    try:
        email_a, email_b = derived_emails()
        minimum_email_gap_seconds = acceptance_minimum_email_gap_seconds()
        cooldown_hours = acceptance_real_email_cooldown_hours()
        imap_connect_timeout = imap_connect_timeout_seconds()
        reserve_real_email_acceptance(
            state_path=real_email_guard_path(),
            run_id=acceptance_run_id(),
            cooldown_hours=cooldown_hours,
            minimum_gap_seconds=minimum_email_gap_seconds,
        )
    except RuntimeError as exc:
        return {
            "verdict": "BLOCKED",
            "blocker": "EMAIL_ONLY_BLOCKED",
            "scope": "real HTTPS email lifecycle anti-burst guard",
            "reason": str(exc),
            "email_delivery_sent": False,
            "synthetic_accounts_created": False,
            "full_production_pass_still_requires_real_email_lifecycle": True,
            "production_claimed": False,
            "secret_values_exposed": False,
        }, 2
    pacer = EmailPacer(minimum_email_gap_seconds)
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
            register_verify(page, base_url, email_a, password, steps, pacer)
            onboard_and_wait(page, base_url, steps)
            detail_url, pack_url = candidate_actions(page, steps)
            password_a = reset_password(page, base_url, email_a, password, steps, pacer)
            cleanup[email_a] = password_a

            logout(page, base_url)
            register_verify(page, base_url, email_b, password, steps, pacer)
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
            "email_safety": {
                "minimum_gap_seconds": minimum_email_gap_seconds,
                "cooldown_hours": cooldown_hours,
                "imap_connect_timeout_seconds": imap_connect_timeout,
                "maximum_real_messages": MAX_REAL_EMAIL_MESSAGES,
            },
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
