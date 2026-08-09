from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception as bundled_error:
        executable = (
            shutil.which("chromium")
            or shutil.which("chromium-browser")
            or shutil.which("google-chrome")
        )
        if not executable:
            raise RuntimeError(
                "Playwright Chromium is unavailable. Run: python -m playwright install chromium"
            ) from bundled_error
        try:
            return playwright.chromium.launch(headless=True, executable_path=executable)
        except Exception as system_error:
            raise RuntimeError(
                "No usable browser is available; use a dedicated Playwright browser on the deployment host."
            ) from system_error


def run(output_dir: Path) -> dict[str, object]:
    base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("LIVE_ACCEPTANCE_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "")
    if not base_url or not email or not password:
        raise RuntimeError("BASE_URL, ADMIN_EMAIL and ADMIN_PASSWORD are required in the environment.")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Live acceptance requires the real HTTPS BASE_URL.")

    output_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    result: dict[str, object] = {
        "https_entry": "not_run",
        "owner_login": "not_run",
        "protected_navigation": "not_run",
        "browser_console": "not_run",
        "first_run_state": "unknown",
    }

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))

        response = page.goto(base_url + "/login", wait_until="networkidle")
        if response is None or response.status >= 400:
            raise RuntimeError("The public HTTPS login page is not reachable.")
        if page.get_by_role("heading", name="登录你的私人工作区").count() != 1:
            raise RuntimeError("The login page did not render the expected product UI.")
        result["https_entry"] = "pass"

        page.get_by_label("登录邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="进入工作区").click()
        page.wait_for_load_state("networkidle")
        if page.url.endswith("/login") or "/login?" in page.url:
            raise RuntimeError("Owner login failed on the live deployment.")
        result["owner_login"] = "pass"

        if page.url.endswith("/onboarding"):
            page.get_by_role("heading", name="先建立你的真实求职边界").wait_for()
            result["first_run_state"] = "owner_onboarding_required"
            page.screenshot(path=str(output_dir / "live-onboarding.png"), full_page=True)
        else:
            page.goto(base_url + "/", wait_until="networkidle")
            page.get_by_role("heading", name="今天只做最值得做的申请。").wait_for()
            result["first_run_state"] = "owner_profile_present"
            page.screenshot(path=str(output_dir / "live-dashboard.png"), full_page=True)

        page.goto(base_url + "/jobs/new", wait_until="networkidle")
        page.get_by_role("heading", name="给我岗位，先回答“值不值得投”。").wait_for()
        page.goto(base_url + "/settings", wait_until="networkidle")
        page.get_by_text("不自动提交申请", exact=True).wait_for()
        page.get_by_text("DeepSeek 不是单点依赖", exact=True).wait_for()
        result["protected_navigation"] = "pass"

        filtered = [
            item for item in console_errors
            if "favicon" not in item.lower() and "failed to load resource" not in item.lower()
        ]
        result["browser_console"] = "pass" if not filtered else "fail"
        result["console_errors"] = filtered[:10]
        context.close()
        browser.close()

    (output_dir / "live-readonly-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "evidence" / "live"
    outcome = run(destination)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    required = ("https_entry", "owner_login", "protected_navigation", "browser_console")
    if any(outcome.get(key) != "pass" for key in required):
        raise SystemExit(1)
