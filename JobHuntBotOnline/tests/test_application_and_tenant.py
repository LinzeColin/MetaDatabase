from __future__ import annotations

import json
from urllib.parse import urlparse

from sqlalchemy import select

from app.models import ApplicationEvent, ApplicationPack, Recommendation, User
from app.security import email_lookup
from .conftest import complete_onboarding, csrf, register_verify


def first_recommendation_id(client) -> int:
    with client.app.state.session_factory() as db:
        row = db.scalar(select(Recommendation).order_by(Recommendation.rank_score.desc()))
        assert row
        return row.id


def test_recommendation_actions_application_pack_and_progress(client):
    register_verify(client, "apply@example.com")
    complete_onboarding(client)
    rec_id = first_recommendation_id(client)

    detail = client.get(f"/recommendations/{rec_id}")
    assert detail.status_code == 200
    saved = client.post(f"/recommendations/{rec_id}/status", data={
        "csrf_token": csrf(detail.text), "status": "saved"
    }, follow_redirects=True)
    assert "状态已更新" in saved.text

    pack_response = client.post(f"/recommendations/{rec_id}/pack", data={
        "csrf_token": csrf(saved.text)
    }, follow_redirects=True)
    assert "申请准备" in pack_response.text
    assert "Why this role" in pack_response.text

    with client.app.state.session_factory() as db:
        pack = db.scalar(select(ApplicationPack))
        rec = db.get(Recommendation, rec_id)
        assert pack is not None
        assert rec.user_status == "preparing"

    applications = client.get("/applications")
    with client.app.state.session_factory() as db:
        rec = db.get(Recommendation, rec_id)
        job_id = rec.job_id

    rejected = client.post("/applications", data={
        "csrf_token": csrf(applications.text),
        "job_id": job_id,
        "status": "submitted",
        "evidence": "",
        "notes": "",
    }, follow_redirects=True)
    assert "确认依据" in rejected.text

    accepted = client.post("/applications", data={
        "csrf_token": csrf(rejected.text),
        "job_id": job_id,
        "status": "submitted",
        "evidence": "Application ID AU-2026-001",
        "notes": "Submitted on official site",
    }, follow_redirects=True)
    assert "申请进度已保存" in accepted.text
    with client.app.state.session_factory() as db:
        event = db.scalar(select(ApplicationEvent))
        assert event and event.status == "submitted"


def test_manual_job_import_remains_available(client):
    register_verify(client, "manual@example.com")
    complete_onboarding(client)
    page = client.get("/jobs/manual")
    response = client.post("/jobs/manual", data={
        "csrf_token": csrf(page.text),
        "url": "https://company.example/jobs/manual-one",
        "title": "Graduate Treasury Analyst",
        "company": "Manual Company",
        "location": "Sydney, Australia",
        "description": "Graduate treasury role using Excel and financial analysis. Australian working rights required.",
    }, follow_redirects=True)
    assert "Graduate Treasury Analyst" in response.text
    assert "岗位已导入并分析" in response.text


def test_tenant_isolation_blocks_cross_user_recommendation_and_pack(client):
    register_verify(client, "tenant-a@example.com")
    complete_onboarding(client)
    rec_a = first_recommendation_id(client)
    detail = client.get(f"/recommendations/{rec_a}")
    client.post(f"/recommendations/{rec_a}/pack", data={"csrf_token": csrf(detail.text)}, follow_redirects=True)
    with client.app.state.session_factory() as db:
        pack_a = db.scalar(select(ApplicationPack))
        assert pack_a

    page = client.get("/recommendations")
    client.post("/logout", data={"csrf_token": csrf(page.text)}, follow_redirects=True)
    register_verify(client, "tenant-b@example.com")
    complete_onboarding(client)

    response = client.get(f"/recommendations/{rec_a}", follow_redirects=False)
    assert response.status_code == 404
    response = client.get(f"/application-packs/{pack_a.id}", follow_redirects=False)
    assert response.status_code == 404


def test_export_contains_user_data_but_not_platform_key(client):
    register_verify(client, "export@example.com")
    complete_onboarding(client)
    response = client.get("/settings/data/export")
    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["work_authorization"] == "Australian full working rights"
    encoded = json.dumps(data)
    assert "DEEPSEEK_API_KEY" not in encoded
    assert "test-session-secret" not in encoded
