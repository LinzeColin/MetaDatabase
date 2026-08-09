from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(url: str, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/readyz", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(env: dict[str, str], port: int) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_ready(f"http://127.0.0.1:{port}")
    except Exception:
        output = process.stdout.read() if process.stdout else ""
        process.terminate()
        raise RuntimeError(output)
    return process


def stop_server(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def launch_browser(playwright):
    # A dedicated Playwright browser avoids inherited enterprise policies and user profiles.
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
                "Playwright Chromium is not installed and no supported system browser was found. "
                "Run: python -m playwright install chromium"
            ) from bundled_error
        try:
            return playwright.chromium.launch(headless=True, executable_path=executable)
        except Exception as system_error:
            raise RuntimeError(
                "No usable browser is available. A system policy may block browser automation; "
                "run the acceptance flow on the target deployment host with a dedicated Playwright browser."
            ) from system_error


def sign_in(page, base_url: str) -> None:
    page.goto(base_url + "/login", wait_until="networkidle")
    page.get_by_label("登录邮箱").fill("owner@test.local")
    page.get_by_label("密码").fill("Correct-Horse-Battery-2026")
    page.get_by_role("button", name="进入工作区").click()


def run(output_dir: Path) -> dict[str, object]:
    temp_root = Path(tempfile.mkdtemp(prefix="jobhuntos-e2e-"))
    data_dir = temp_root / "data"
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "DATA_DIR": str(data_dir),
            "APP_ENV": "development",
            "BASE_URL": base_url,
            "ADMIN_EMAIL": "owner@test.local",
            "ADMIN_PASSWORD": "Correct-Horse-Battery-2026",
            "SESSION_SECRET": "e2e-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789",
            "DATA_ENCRYPTION_KEY": "v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4=",
            "MAINTENANCE_ENABLED": "false",
            "COOKIE_SECURE": "false",
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    server = start_server(env, port)
    result: dict[str, object] = {"golden_transaction": "not_run", "restart_readback": "not_run"}

    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            context = browser.new_context(viewport={"width": 1440, "height": 1050})
            page = context.new_page()
            sign_in(page, base_url)
            page.wait_for_url("**/onboarding")

            page.get_by_label("常用姓名").fill("Linze")
            page.get_by_label("申请邮箱").fill("linze@example.com")
            page.get_by_label("当前位置").fill("Sydney, NSW")
            page.get_by_label("当前状态").fill("UNSW student")
            page.get_by_label("学历摘要").fill("Master of Commerce, UNSW")
            page.get_by_label("毕业年份").fill("2027")
            page.get_by_label("可核验的全职相关经验年数").fill("1")
            page.get_by_label("你的工作权利原文").fill(
                "Australian work rights confirmed; review exact form wording before submission."
            )
            page.get_by_label("现在需要雇主 Sponsorship 吗？").select_option("no")
            page.get_by_label("未来需要雇主 Sponsorship 吗？").select_option("no")
            page.get_by_label("主要目标岗位").fill("Data Analyst, Financial Analyst")
            page.get_by_label("目标地点").fill("Sydney, Remote Australia")
            page.get_by_role("button", name="保存并继续").click()
            page.wait_for_url("**/resumes")

            page.locator('input[type="file"]').set_input_files(str(FIXTURES / "sample_resume.txt"))
            page.get_by_label("版本名称").fill("Data Analyst v1")
            page.get_by_label("适用岗位族").fill("Data Analyst")
            page.get_by_role("button", name="读取并保存简历").click()
            page.wait_for_url("**/resumes")
            page.get_by_text("Data Analyst v1", exact=True).wait_for()

            page.goto(base_url + "/jobs/new", wait_until="networkidle")
            page.get_by_label("岗位链接", exact=True).last.fill("https://careers.example.com/jobs/graduate-data-analyst")
            page.get_by_label("公司").fill("Example Co")
            page.get_by_label("职位名称").fill("Graduate Data Analyst")
            page.get_by_label("地点").fill("Sydney, NSW")
            page.get_by_label("发布日期").fill("2026-08-08")
            page.get_by_label("Job description").fill((FIXTURES / "sample_job.txt").read_text(encoding="utf-8"))
            page.get_by_role("button", name="生成判断与申请包").click()
            page.wait_for_url("**/jobs/1")
            page.get_by_text("申请准备包", exact=True).wait_for()
            page.get_by_text("Data Analyst v1", exact=True).wait_for()

            page.get_by_label("我已核对草稿中的事实").check()
            page.get_by_role("button", name="保存申请包").click()
            page.wait_for_url("**/jobs/1#application-pack")

            page.get_by_label("当前状态").select_option("Applied")
            page.get_by_label("当前阶段").fill("Application submitted")
            page.get_by_label("下一动作").fill("Wait for employer response")
            page.get_by_label("日期").fill("2026-08-16")
            page.get_by_label("提交 / 结果证据").fill("Official thank-you page displayed, reference APP-E2E-1001")
            page.get_by_label("私有备注").fill("Submitted manually on employer website.")
            page.get_by_role("button", name="保存进度").click()
            page.wait_for_url("**/jobs/1#progress")
            page.get_by_text("APP-E2E-1001", exact=False).wait_for()
            page.reload(wait_until="networkidle")
            page.get_by_text("APP-E2E-1001", exact=False).wait_for()
            page.screenshot(path=str(output_dir / "browser-desktop.png"), full_page=True)

            mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            mobile_page = mobile.new_page()
            sign_in(mobile_page, base_url)
            mobile_page.wait_for_url("**/")
            mobile_page.screenshot(path=str(output_dir / "browser-mobile.png"), full_page=True)
            mobile.close()
            context.close()
            browser.close()
            result["golden_transaction"] = "pass"
    finally:
        stop_server(server)

    server = start_server(env, port)
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            sign_in(page, base_url)
            page.wait_for_url("**/")
            page.goto(base_url + "/jobs/1", wait_until="networkidle")
            page.get_by_text("APP-E2E-1001", exact=False).wait_for()
            page.get_by_text("Applied", exact=True).first.wait_for()
            browser.close()
            result["restart_readback"] = "pass"
    finally:
        stop_server(server)

    result["database_exists"] = (data_dir / "jobhuntos.db").is_file()
    result["encrypted_upload_exists"] = bool(list((data_dir / "uploads").glob("*.bin")))
    result["evidence_dir"] = str(output_dir)
    (output_dir / "e2e-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(temp_root, ignore_errors=True)
    return result


if __name__ == "__main__":
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "evidence"
    outcome = run(destination)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    if outcome.get("golden_transaction") != "pass" or outcome.get("restart_readback") != "pass":
        raise SystemExit(1)
