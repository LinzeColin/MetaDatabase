from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ApplicationPack, Job, JobEvent, Resume
from tests.conftest import csrf_from


def create_job(client):
    response = client.get("/jobs/new")
    token = csrf_from(response)
    description = (Path(__file__).parents[1] / "fixtures" / "sample_job.txt").read_text(encoding="utf-8")
    response = client.post(
        "/jobs",
        data={
            "csrf_token": token,
            "url": "https://careers.example.com/jobs/graduate-data-analyst",
            "company": "Example Co",
            "title": "Graduate Data Analyst",
            "location": "Sydney, NSW",
            "posted_date": "2026-08-08",
            "description": description,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[1])


def test_login_rejects_wrong_password(client):
    response = client.get("/login")
    token = csrf_from(response)
    response = client.post(
        "/login",
        data={"email": "owner@test.local", "password": "wrong", "csrf_token": token, "next_url": "/"},
    )
    assert response.status_code == 400
    assert "邮箱或密码不正确" in response.text


def test_golden_transaction_and_persistence(ready_workspace):
    client = ready_workspace
    job_id = create_job(client)
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert "申请准备包" in response.text
    assert "Data Analyst v1" in response.text

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job_id))
        assert job is not None and job.recommendation in {"Apply", "Review"}
        assert pack is not None and pack.resume_id is not None
        assert pack.experience_ids
        assert db.scalar(select(Resume).where(Resume.id == pack.resume_id)) is not None

    token = csrf_from(response)
    response = client.post(
        f"/jobs/{job_id}/status",
        data={
            "csrf_token": token,
            "status": "Applied",
            "current_stage": "Application submitted",
            "next_action": "Wait for employer response",
            "next_action_date": "2026-08-16",
            "evidence_note": "Official thank-you page displayed, reference APP-1001",
            "notes": "Submitted manually on employer website.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = client.get(f"/jobs/{job_id}")
    assert "APP-1001" in response.text
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job is not None and job.status == "Applied"
        assert db.scalar(select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.event_type == "Applied")) is not None


def test_applied_requires_submission_evidence(ready_workspace):
    client = ready_workspace
    job_id = create_job(client)
    response = client.get(f"/jobs/{job_id}")
    token = csrf_from(response)
    response = client.post(
        f"/jobs/{job_id}/status",
        data={"csrf_token": token, "status": "Applied", "evidence_note": "", "current_stage": "", "next_action": "", "next_action_date": "", "notes": ""},
        follow_redirects=True,
    )
    assert "标记为 Applied 前" in response.text
    with SessionLocal() as db:
        assert db.get(Job, job_id).status != "Applied"


def test_duplicate_job_url_returns_existing_record(ready_workspace):
    client = ready_workspace
    first = create_job(client)
    second = create_job(client)
    assert second == first
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Job)))) == 1


def test_application_pack_download(ready_workspace):
    client = ready_workspace
    job_id = create_job(client)
    response = client.get(f"/jobs/{job_id}/application-pack.md")
    assert response.status_code == 200
    assert "Example Co — Graduate Data Analyst" in response.text
    assert "只有在官方页面看到明确成功信息" in response.text


def test_dashboard_guides_one_time_deepseek_setup(ready_workspace):
    response = ready_workspace.get("/")
    assert response.status_code == 200
    assert "DeepSeek 增强" in response.text
    assert "粘贴一次 API Key并验证" in response.text
    assert 'href="/settings#deepseek"' in response.text
