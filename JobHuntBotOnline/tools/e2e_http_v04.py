#!/usr/bin/env python3
"""Run the v0.4 finance/legal golden path through a real Uvicorn process.

This is an HTTP/Cookie/form/download acceptance companion to the browser suite.
It uses only disposable test data and FastAPI's in-memory test mail outbox.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import closing
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from docx import Document

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/readyz", timeout=2)
            if response.status_code == 200 and response.json().get("refresh_hours") == 6:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("应用未在期限内就绪")


def csrf(html: str) -> str:
    node = BeautifulSoup(html, "html.parser").select_one('input[name="csrf_token"]')
    if not node or not node.get("value"):
        raise AssertionError("页面缺少防伪令牌")
    return str(node["value"])


def mail_link(base_url: str, kind: str, recipient: str) -> str:
    rows = httpx.get(f"{base_url}/_test/outbox", timeout=5).json()
    messages = [row for row in rows if row.get("kind") == kind and row.get("to") == recipient]
    if not messages:
        raise AssertionError(f"未找到 {kind} 测试邮件")
    match = re.search(r"https?://\S+", str(messages[-1].get("body", "")))
    if not match:
        raise AssertionError("测试邮件缺少链接")
    return match.group(0).rstrip(".,)")


def register_and_verify(client: httpx.Client, base_url: str, email: str) -> None:
    page = client.get("/register")
    response = client.post(
        "/register",
        data={
            "csrf_token": csrf(page.text),
            "email": email,
            "display_name": "v0.4 合成测试用户",
            "password": "ValidPass123",
            "password_confirm": "ValidPass123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200 and "验证" in response.text
    parsed = urlparse(mail_link(base_url, "verify", email))
    token = parse_qs(parsed.query).get("token", [""])[0]
    assert token
    confirmation = client.get(parsed.path + (f"?{parsed.query}" if parsed.query else ""))
    assert confirmation.status_code == 200
    response = client.post(
        "/verify-email",
        data={"csrf_token": csrf(confirmation.text), "token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200 and "上传简历" in response.text


def upload(client: httpx.Client, filename: str) -> None:
    page = client.get("/onboarding/upload")
    response = client.post(
        "/onboarding/upload",
        data={"csrf_token": csrf(page.text)},
        files={"resume": (filename, (ROOT / "tests/fixtures" / filename).read_bytes(), "text/plain")},
        follow_redirects=True,
    )
    assert response.status_code == 200 and "确认" in response.text


def confirm(
    client: httpx.Client,
    *,
    roles: str,
    years: str,
    credentials: str,
    admission: str,
    certificate: str,
) -> None:
    page = client.get("/onboarding/confirm")
    response = client.post(
        "/onboarding/confirm",
        data={
            "csrf_token": csrf(page.text),
            "primary_roles": roles,
            "target_locations": "Sydney, Melbourne, Remote Australia",
            "work_authorization": "Australian full working rights",
            "sponsorship_now": "no",
            "sponsorship_future": "no",
            "work_modes": ["remote", "hybrid", "onsite"],
            "experience_years": years,
            "professional_credentials": credentials,
            "credentials_confirmed": "true",
            "legal_admission": admission,
            "practising_certificate": certificate,
            "relocation": "no",
            "available_start": "2026-11",
            "avoid_roles": "销售",
            "avoid_industries": "博彩",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200 and "岗位推荐" in response.text


def recommendation_path(html: str, title: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select('[data-testid="job-card"]'):
        if title in card.get_text(" ", strip=True):
            link = card.select_one('[data-testid="job-detail-link"]')
            if link and link.get("href"):
                return str(link["href"])
    raise AssertionError(f"没有找到推荐岗位：{title}")


def create_pack(client: httpx.Client, detail_path: str) -> tuple[str, str]:
    detail = client.get(detail_path)
    assert detail.status_code == 200
    response = client.post(
        detail_path + "/pack",
        data={"csrf_token": csrf(detail.text)},
        follow_redirects=True,
    )
    assert response.status_code == 200 and "简历自动路由" in response.text
    return str(response.url.path), response.text


def run(args: argparse.Namespace) -> tuple[dict, int]:
    temp = Path(tempfile.mkdtemp(prefix="jobhunt-v04-http-"))
    port = args.port or free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({
        "APP_ENV": "test",
        "APP_VERSION": "0.4.0",
        "BASE_URL": base_url,
        "DATABASE_URL": f"sqlite+pysqlite:///{temp / 'journey.db'}",
        "SESSION_SECRET": "journey-session",
        "DATA_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        "EMAIL_LOOKUP_SECRET": "journey-email",
        "COOKIE_SECURE": "false",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "AdminPass!2026",
        "ALLOW_REGISTRATION": "true",
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
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
    )
    steps: list[str] = []
    result: dict = {
        "verdict": "FAIL",
        "scope": "real Uvicorn HTTP/Cookie/form/download v0.4 finance/legal golden path",
        "synthetic_data_only": True,
        "production_claimed": False,
        "email_delivery_sent": False,
    }
    try:
        wait_ready(base_url)
        with httpx.Client(base_url=base_url, follow_redirects=True, timeout=15) as finance:
            register_and_verify(finance, base_url, "finance-v04@example.com")
            upload(finance, "finance_resume.txt")
            confirm(
                finance,
                roles="金融分析、会计与审计、风险管理",
                years="3",
                credentials="CPA",
                admission="not_applicable",
                certificate="not_applicable",
            )
            feed = finance.get("/recommendations", params={"relevance": ""})
            assert "Senior Finance Director" in feed.text and "Graduate Financial Analyst" in feed.text
            director = next(card for card in BeautifulSoup(feed.text, "html.parser").select('[data-testid="job-card"]') if "Senior Finance Director" in card.get_text(" "))
            assert "不符合" in director.get_text(" ") and "15" in director.get_text(" ")
            passed_finance = finance.get("/recommendations", params={"domain": "finance", "qualification": "pass", "partial": "true"})
            assert "Graduate Financial Analyst" in passed_finance.text and "Senior Finance Director" not in passed_finance.text
            finance_detail = recommendation_path(feed.text, "Graduate Financial Analyst")
            finance_pack, finance_pack_html = create_pack(finance, finance_detail)
            assert "finance_resume.txt" in finance_pack_html
            download = finance.get(finance_pack + "/resume.docx")
            assert download.headers.get("content-type", "").startswith("application/vnd.openxmlformats")
            finance_doc = "\n".join(item.text for item in Document(BytesIO(download.content)).paragraphs)
            assert "Graduate Financial Analyst" in finance_doc and "Junior Solicitor" not in finance_doc
            upload(finance, "legal_resume.txt")
            latest_feed = finance.get("/recommendations", params={"relevance": ""})
            _, still_finance = create_pack(finance, recommendation_path(latest_feed.text, "Graduate Financial Analyst"))
            _, legal_pack_html = create_pack(finance, recommendation_path(latest_feed.text, "Commercial Solicitor"))
            assert "finance_resume.txt" in still_finance and "legal_resume.txt" in legal_pack_html
            applications = finance.get("/applications")
            job_option = BeautifulSoup(applications.text, "html.parser").select_one('[data-testid="application-job"] option')
            assert job_option and job_option.get("value")
            rejected = finance.post("/applications", data={"csrf_token": csrf(applications.text), "job_id": job_option["value"], "status": "submitted", "evidence": "", "notes": ""})
            assert "确认依据" in rejected.text
            accepted = finance.post("/applications", data={"csrf_token": csrf(rejected.text), "job_id": job_option["value"], "status": "submitted", "evidence": "申请编号 FIN-001", "notes": "合成测试"})
            assert "申请进度已保存" in accepted.text
            steps.extend(["金融注册验证", "金融硬资格拦截", "领域实时筛选服务端事务", "金融简历路由", "DOCX 下载", "默认简历不覆盖岗位路由", "申请依据校验"])

        with httpx.Client(base_url=base_url, follow_redirects=True, timeout=15) as legal:
            register_and_verify(legal, base_url, "legal-v04@example.com")
            upload(legal, "legal_resume.txt")
            confirm(
                legal,
                roles="法律、合规、合同与法务运营",
                years="4",
                credentials="JD、PLT、澳大利亚律师准入、澳大利亚执业证书",
                admission="admitted",
                certificate="current",
            )
            feed = legal.get("/recommendations", params={"relevance": ""})
            cards = {card.get_text(" ", strip=True) for card in BeautifulSoup(feed.text, "html.parser").select('[data-testid="job-card"]')}
            assert any("Commercial Solicitor" in value and "通过" in value for value in cards)
            assert any("General Counsel" in value and "不符合" in value for value in cards)
            assert legal.get(finance_pack).status_code == 404
            assert "Why this role" not in legal.get("/recommendations").text
            steps.extend(["法律注册验证", "律师准入执业证书判断", "总法律顾问年限拦截", "跨租户隔离", "全中文界面"])

        result.update({"verdict": "PASS", "steps": steps, "step_count": len(steps), "refresh_interval_hours": 6})
        return result, 0
    except Exception as exc:
        result.update({
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=4),
            "steps_completed": steps,
            "server_log_tail": "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]) if log_path.exists() else "",
        })
        return result, 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/local/e2e-http-v04.json")
    parser.add_argument("--port", type=int, default=0)
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
