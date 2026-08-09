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

import httpx
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/readyz", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("server did not become ready")


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


def csrf(response: httpx.Response) -> str:
    soup = BeautifulSoup(response.text, "html.parser")
    field = soup.select_one('input[name="csrf_token"]')
    if field is None:
        raise AssertionError("CSRF field missing")
    return str(field["value"])


def login(client: httpx.Client) -> None:
    response = client.get("/login")
    response = client.post(
        "/login",
        data={
            "email": "owner@test.local",
            "password": "Correct-Horse-Battery-2026",
            "csrf_token": csrf(response),
            "next_url": "/",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def run(output_dir: Path) -> dict[str, object]:
    temp_root = Path(tempfile.mkdtemp(prefix="jobhuntos-http-golden-"))
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
            "SESSION_SECRET": "http-golden-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789",
            "DATA_ENCRYPTION_KEY": "v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4=",
            "MAINTENANCE_ENABLED": "false",
            "COOKIE_SECURE": "false",
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "process_start": "not_run",
        "golden_transaction": "not_run",
        "restart_readback": "not_run",
        "encrypted_backup": "not_run",
    }

    server = start_server(env, port)
    result["process_start"] = "pass"
    try:
        with httpx.Client(base_url=base_url, follow_redirects=True, timeout=20) as client:
            login(client)
            response = client.get("/onboarding")
            response = client.post(
                "/profile",
                data={
                    "csrf_token": csrf(response),
                    "preferred_name": "Linze",
                    "legal_name": "",
                    "email": "linze@example.com",
                    "phone": "+61 400 000 000",
                    "current_location": "Sydney, NSW",
                    "linkedin_url": "",
                    "github_url": "",
                    "portfolio_url": "",
                    "current_status": "UNSW student",
                    "degree_summary": "Master of Commerce, UNSW",
                    "graduation_year": "2027",
                    "professional_experience_years": "1",
                    "work_authorization_country": "Australia",
                    "work_authorization_text": "Australian work rights confirmed; review exact form wording before submission.",
                    "sponsorship_now": "no",
                    "sponsorship_future": "no",
                    "target_roles": "Data Analyst, Financial Analyst",
                    "secondary_roles": "Business Analyst",
                    "roles_to_avoid": "Senior Director, pure sales",
                    "industries_to_avoid": "",
                    "target_locations": "Sydney, Remote Australia",
                    "work_mode": "Hybrid / Onsite / Remote",
                    "relocation_policy": "NSW only",
                    "target_level": "Graduate / Entry level",
                    "available_start_date": "2027-02",
                    "salary_strategy": "Prefer not to state unless required.",
                    "salary_range": "",
                    "self_identification_strategy": "prefer_not_to_say",
                    "next_url": "/resumes",
                },
            )
            assert response.url.path == "/resumes"

            token = csrf(response)
            with (FIXTURES / "sample_resume.txt").open("rb") as handle:
                response = client.post(
                    "/resumes/upload",
                    data={
                        "csrf_token": token,
                        "label": "Data Analyst v1",
                        "role_family": "Data Analyst",
                        "is_default": "yes",
                        "auto_import_experiences": "yes",
                    },
                    files={"file": ("sample_resume.txt", handle, "text/plain")},
                )
            assert "Data Analyst v1" in response.text

            response = client.get("/jobs/new")
            response = client.post(
                "/jobs",
                data={
                    "csrf_token": csrf(response),
                    "url": "https://careers.example.com/jobs/graduate-data-analyst",
                    "company": "Example Co",
                    "title": "Graduate Data Analyst",
                    "location": "Sydney, NSW",
                    "posted_date": "2026-08-08",
                    "description": (FIXTURES / "sample_job.txt").read_text(encoding="utf-8"),
                },
            )
            assert response.url.path == "/jobs/1"
            assert "申请准备包" in response.text
            assert "Data Analyst v1" in response.text

            response = client.post(
                "/jobs/1/status",
                data={
                    "csrf_token": csrf(response),
                    "status": "Applied",
                    "current_stage": "Application submitted",
                    "next_action": "Wait for employer response",
                    "next_action_date": "2026-08-16",
                    "evidence_note": "Official thank-you page displayed, reference APP-HTTP-1001",
                    "notes": "Submitted manually on employer website.",
                },
            )
            assert "APP-HTTP-1001" in response.text

            response = client.post("/settings/backup", data={"csrf_token": csrf(client.get("/settings"))})
            assert "加密备份已创建" in response.text
            result["golden_transaction"] = "pass"
    finally:
        stop_server(server)

    server = start_server(env, port)
    try:
        with httpx.Client(base_url=base_url, follow_redirects=True, timeout=20) as client:
            login(client)
            response = client.get("/jobs/1")
            assert response.status_code == 200
            assert "APP-HTTP-1001" in response.text
            assert "Applied" in response.text
            result["restart_readback"] = "pass"
    finally:
        stop_server(server)

    backups = list((data_dir / "backups").glob("*.jhbbackup"))
    result["encrypted_backup"] = "pass" if backups else "fail"
    result["database_exists"] = (data_dir / "jobhuntos.db").is_file()
    result["encrypted_upload_exists"] = bool(list((data_dir / "uploads").glob("*.bin")))
    result["canonical_export_exists"] = (data_dir / "canonical" / "current.json").is_file()
    (output_dir / "http-golden-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.rmtree(temp_root, ignore_errors=True)
    return result


if __name__ == "__main__":
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "evidence"
    outcome = run(destination)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    if any(outcome.get(key) != "pass" for key in ("process_start", "golden_transaction", "restart_readback", "encrypted_backup")):
        raise SystemExit(1)
