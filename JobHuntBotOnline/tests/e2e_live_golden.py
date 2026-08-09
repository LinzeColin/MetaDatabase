from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


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
                "Playwright Chromium is unavailable. Install the dedicated Chromium browser on the deployment host."
            ) from bundled_error
        try:
            return playwright.chromium.launch(headless=True, executable_path=executable)
        except Exception as system_error:
            raise RuntimeError("No usable dedicated browser is available on the deployment host.") from system_error


def required_environment() -> tuple[str, str, str, str]:
    base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
    email = os.environ.get("LIVE_ACCEPTANCE_EMAIL", "").strip().lower()
    password = os.environ.get("LIVE_ACCEPTANCE_PASSWORD", "")
    marker = os.environ.get("LIVE_ACCEPTANCE_MARKER", "").strip()
    if not all((base_url, email, password, marker)):
        raise RuntimeError(
            "BASE_URL, LIVE_ACCEPTANCE_EMAIL, LIVE_ACCEPTANCE_PASSWORD and LIVE_ACCEPTANCE_MARKER are required."
        )
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("Live acceptance requires the real HTTPS BASE_URL.")
    if not email.endswith("@acceptance.invalid"):
        raise RuntimeError("Live acceptance requires an isolated acceptance identity.")
    if len(marker) < 12:
        raise RuntimeError("Live acceptance marker is invalid.")
    return base_url, email, password, marker


def sign_in(page: Page, base_url: str, email: str, password: str) -> None:
    response = page.goto(base_url + "/login", wait_until="networkidle")
    if response is None or response.status >= 400:
        raise RuntimeError("The public HTTPS login page is not reachable.")
    page.get_by_role("heading", name="登录你的私人工作区").wait_for()
    page.get_by_label("登录邮箱").fill(email)
    page.get_by_label("密码").fill(password)
    page.get_by_role("button", name="进入工作区").click()
    page.wait_for_load_state("networkidle")
    if page.url.endswith("/login") or "/login?" in page.url:
        raise RuntimeError("The isolated acceptance login failed.")


def filtered_console_errors(messages: list[str]) -> list[str]:
    def is_proxy_injected_beacon_csp_notice(item: str) -> bool:
        normalized = item.lower()
        return (
            "static.cloudflareinsights.com/beacon.min.js" in normalized
            and "content security policy" in normalized
        )

    return [
        item
        for item in messages
        if "favicon" not in item.lower() and "failed to load resource" not in item.lower()
        # The target Cloudflare proxy injects this optional analytics beacon.
        # The application's strict CSP must continue to block it; this notice
        # is infrastructure noise rather than an application browser failure.
        and not is_proxy_injected_beacon_csp_notice(item)
    ][:10]


def run_transaction(output_dir: Path, state_file: Path) -> dict[str, object]:
    base_url, email, password, marker = required_environment()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    result: dict[str, object] = {
        "https_entry": "not_run",
        "isolated_login": "not_run",
        "onboarding": "not_run",
        "resume_upload": "not_run",
        "job_analysis": "not_run",
        "application_pack": "not_run",
        "progress_write": "not_run",
        "refresh_readback": "not_run",
        "safe_settings": "not_run",
        "browser_console": "not_run",
    }

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))

        sign_in(page, base_url, email, password)
        result["https_entry"] = "pass"
        result["isolated_login"] = "pass"
        if not page.url.endswith("/onboarding"):
            raise RuntimeError("The isolated acceptance identity did not start from a clean onboarding state.")

        page.get_by_label("常用姓名").fill("Acceptance Probe")
        page.get_by_label("申请邮箱").fill("candidate@example.invalid")
        page.get_by_label("当前位置").fill("Sydney, NSW")
        page.get_by_label("当前状态").fill("Acceptance-only candidate")
        page.get_by_label("学历摘要").fill("Acceptance fixture degree")
        page.get_by_label("毕业年份").fill("2027")
        page.get_by_label("可核验的全职相关经验年数").fill("1")
        page.get_by_label("你的工作权利原文").fill(
            "Acceptance fixture: Australian work rights confirmed for this isolated test identity."
        )
        page.get_by_label("现在需要雇主 Sponsorship 吗？").select_option("no")
        page.get_by_label("未来需要雇主 Sponsorship 吗？").select_option("no")
        page.get_by_label("主要目标岗位").fill("Data Analyst, Financial Analyst")
        page.get_by_label("目标地点").fill("Sydney, Remote Australia")
        page.get_by_role("button", name="保存并继续").click()
        page.wait_for_url("**/resumes")
        result["onboarding"] = "pass"

        page.locator('input[type="file"]').set_input_files(str(FIXTURES / "sample_resume.txt"))
        page.get_by_label("版本名称").fill("Acceptance Resume")
        page.get_by_label("适用岗位族").fill("Data Analyst")
        page.get_by_role("button", name="读取并保存简历").click()
        page.wait_for_url("**/resumes")
        page.get_by_text("Acceptance Resume", exact=True).wait_for()
        result["resume_upload"] = "pass"

        page.goto(base_url + "/jobs/new", wait_until="networkidle")
        page.get_by_label("岗位链接", exact=True).last.fill(
            "https://careers.example.invalid/jobs/acceptance-data-analyst"
        )
        page.get_by_label("公司").fill("Acceptance Example Co")
        page.get_by_label("职位名称").fill("Graduate Data Analyst")
        page.get_by_label("地点").fill("Sydney, NSW")
        page.get_by_label("发布日期").fill("2026-08-09")
        page.get_by_label("Job description").fill((FIXTURES / "sample_job.txt").read_text(encoding="utf-8"))
        page.get_by_role("button", name="生成判断与申请包").click()
        page.wait_for_load_state("networkidle")
        match = re.search(r"/jobs/(\d+)", page.url)
        if not match:
            raise RuntimeError("The live transaction did not create a traceable job record.")
        job_id = int(match.group(1))
        page.get_by_text("申请准备包", exact=True).wait_for()
        page.get_by_text("Acceptance Resume", exact=True).wait_for()
        result["job_analysis"] = "pass"

        page.get_by_label("我已核对草稿中的事实").check()
        page.get_by_role("button", name="保存申请包").click()
        page.wait_for_url(f"**/jobs/{job_id}#application-pack")
        result["application_pack"] = "pass"

        page.get_by_label("当前状态").select_option("Applied")
        page.get_by_label("当前阶段").fill("Application submitted")
        page.get_by_label("下一动作").fill("Wait for employer response")
        page.get_by_label("日期").fill("2026-08-16")
        page.get_by_label("提交 / 结果证据").fill(f"Official acceptance evidence {marker}")
        page.get_by_label("私有备注").fill("Isolated production acceptance transaction; automatically removed.")
        page.get_by_role("button", name="保存进度").click()
        page.wait_for_url(f"**/jobs/{job_id}#progress")
        page.get_by_text(marker, exact=False).wait_for()
        result["progress_write"] = "pass"

        page.reload(wait_until="networkidle")
        page.get_by_text(marker, exact=False).wait_for()
        page.get_by_text("Applied", exact=True).first.wait_for()
        result["refresh_readback"] = "pass"

        page.goto(base_url + "/settings", wait_until="networkidle")
        page.get_by_text("不自动提交申请", exact=True).wait_for()
        page.get_by_text("DeepSeek 不是单点依赖", exact=True).wait_for()
        result["safe_settings"] = "pass"

        errors = filtered_console_errors(console_errors)
        result["browser_console"] = "pass" if not errors else "fail"
        result["console_errors"] = errors
        page.screenshot(path=str(output_dir / "live-transaction.png"), full_page=True)
        context.close()
        browser.close()

    state_file.write_text(json.dumps({"job_id": job_id, "marker": marker}), encoding="utf-8")
    state_file.chmod(0o600)
    (output_dir / "live-transaction-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def run_readback(output_dir: Path, state_file: Path) -> dict[str, object]:
    base_url, email, password, marker = required_environment()
    if not state_file.is_file():
        raise RuntimeError("The live transaction state file is missing.")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    job_id = int(state["job_id"])
    if state.get("marker") != marker:
        raise RuntimeError("The live transaction marker changed before readback.")

    output_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    result: dict[str, object] = {
        "https_entry_after_restart": "not_run",
        "isolated_login_after_restart": "not_run",
        "persisted_job_readback": "not_run",
        "persisted_evidence_readback": "not_run",
        "browser_console": "not_run",
    }

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        sign_in(page, base_url, email, password)
        result["https_entry_after_restart"] = "pass"
        result["isolated_login_after_restart"] = "pass"
        page.goto(f"{base_url}/jobs/{job_id}", wait_until="networkidle")
        page.get_by_text("Graduate Data Analyst", exact=True).wait_for()
        page.get_by_text("Applied", exact=True).first.wait_for()
        result["persisted_job_readback"] = "pass"
        page.get_by_text(marker, exact=False).wait_for()
        result["persisted_evidence_readback"] = "pass"
        errors = filtered_console_errors(console_errors)
        result["browser_console"] = "pass" if not errors else "fail"
        result["console_errors"] = errors
        page.screenshot(path=str(output_dir / "live-readback-after-restart.png"), full_page=True)
        context.close()
        browser.close()

    (output_dir / "live-readback-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--mode", choices=("transaction", "readback"), required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "transaction":
        outcome = run_transaction(args.output_dir.resolve(), args.state.resolve())
    else:
        outcome = run_readback(args.output_dir.resolve(), args.state.resolve())
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if all(value == "pass" for key, value in outcome.items() if key != "console_errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
