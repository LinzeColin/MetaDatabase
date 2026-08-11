from __future__ import annotations

import json
from urllib.parse import urlparse

from sqlalchemy import select

from app.models import ApplicationEvent, ApplicationPack, ApplicationProgress, Job, Recommendation, Resume, User
from app.security import email_lookup
from .conftest import complete_onboarding, csrf, register_verify


def first_recommendation_id(client) -> int:
    with client.app.state.session_factory() as db:
        row = db.scalar(select(Recommendation).order_by(Recommendation.rank_score.desc()))
        assert row
        return row.id


def test_recommendation_detail_sanitizes_existing_escaped_provider_markup(client):
    register_verify(client, "escaped-description@example.com")
    complete_onboarding(client)
    rec_id = first_recommendation_id(client)
    with client.app.state.session_factory() as db:
        rec = db.get(Recommendation, rec_id)
        assert rec is not None
        job = db.get(Job, rec.job_id)
        assert job is not None
        job.description = (
            "&lt;div class=&quot;content-intro&quot;&gt;&lt;p&gt;Readable job description&lt;/p&gt;"
            "&lt;span data-ccp-props=&quot;{}&quot;&gt;extra detail&lt;/span&gt;"
            "&lt;script&gt;should-not-render()&lt;/script&gt;&lt;/div&gt;"
        )
        db.commit()

    response = client.get(f"/recommendations/{rec_id}")
    assert response.status_code == 200
    assert 'data-testid="job-description"' in response.text
    assert "Readable job description" in response.text
    assert "extra detail" in response.text
    assert "data-ccp-props" not in response.text
    assert "should-not-render" not in response.text
    assert "&lt;div" not in response.text


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
        content = client.app.state.crypto.decrypt_json(pack.content_encrypted, {})
        assert content["materials"]["why_me"]["evidence"]
        assert len(content["materials"]["interview_answers"]) == 3

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
        progress = db.scalar(select(ApplicationProgress))
        event = db.scalar(select(ApplicationEvent))
        assert progress and progress.status == "submitted" and progress.version == 1
        assert event and event.status == "submitted" and event.action == "created" and event.revision == 1
        progress_id = progress.id

    edit_page = client.get(f"/applications/{progress_id}/edit")
    assert edit_page.status_code == 200
    edited = client.post(f"/applications/{progress_id}/edit", data={
        "csrf_token": csrf(edit_page.text),
        "status": "interview",
        "evidence": "",
        "notes": "Phone screen booked through the official recruiter.",
    }, follow_redirects=True)
    assert "申请进度已更新，并保留了修订记录" in edited.text
    with client.app.state.session_factory() as db:
        progress = db.get(ApplicationProgress, progress_id)
        events = db.scalars(select(ApplicationEvent).order_by(ApplicationEvent.id)).all()
        rec = db.get(Recommendation, rec_id)
        assert progress and progress.status == "interview" and progress.version == 2
        assert [(event.action, event.revision, event.status) for event in events] == [
            ("created", 1, "submitted"), ("edited", 2, "interview"),
        ]
        assert rec and rec.user_status == "preparing"


def test_editable_application_materials_do_not_overwrite_original_resume(client):
    register_verify(client, "materials@example.com")
    complete_onboarding(client)
    rec_id = first_recommendation_id(client)
    with client.app.state.session_factory() as db:
        resume = db.scalar(select(Resume).where(Resume.is_primary.is_(True)))
        assert resume is not None
        original_resume_text = client.app.state.crypto.decrypt_text(resume.text_encrypted)

    detail = client.get(f"/recommendations/{rec_id}")
    created = client.post(
        f"/recommendations/{rec_id}/pack",
        data={"csrf_token": csrf(detail.text)},
        follow_redirects=True,
    )
    assert "我为什么适合" in created.text
    assert "三道常见问题" in created.text
    assert 'data-testid="pack-ask-ai"' in created.text

    with client.app.state.session_factory() as db:
        pack = db.scalar(select(ApplicationPack))
        assert pack is not None
        pack_id = pack.id
        content = client.app.state.crypto.decrypt_json(pack.content_encrypted, {})
        answers = {item["key"]: item["answer"] for item in content["materials"]["interview_answers"]}

    edit_page = client.get(f"/application-packs/{pack_id}/edit")
    assert edit_page.status_code == 200
    edited = client.post(f"/application-packs/{pack_id}/edit", data={
        "csrf_token": csrf(edit_page.text),
        "why_me_summary": "我会只用已确认的商业分析经历说明适配性。",
        "cv_headline": "面向目标岗位的真实经历 CV",
        "cv_summary": "原始简历保持不变；此处仅调整投递时的事实顺序。",
        "cv_bullets": "真实项目经历\n真实数据分析技能",
        "answer_why_role": answers["why_role"],
        "answer_why_me": answers["why_me"],
        "answer_role_example": answers["role_example"],
    }, follow_redirects=True)
    assert "原始简历未被修改" in edited.text

    with client.app.state.session_factory() as db:
        pack = db.get(ApplicationPack, pack_id)
        resume = db.scalar(select(Resume).where(Resume.is_primary.is_(True)))
        assert pack is not None and pack.version == 2
        assert resume is not None
        assert client.app.state.crypto.decrypt_text(resume.text_encrypted) == original_resume_text
        content = client.app.state.crypto.decrypt_json(pack.content_encrypted, {})
        assert content["materials"]["why_me"]["summary"] == "我会只用已确认的商业分析经历说明适配性。"
        assert content["materials"]["tailored_cv"]["bullets"] == ["真实项目经历", "真实数据分析技能"]

    consultation = client.get(f"/application-packs/{pack_id}/ai")
    assert consultation.status_code == 200
    assert 'data-testid="ai-consult-form"' in consultation.text
    fallback = client.post(f"/application-packs/{pack_id}/ai", data={
        "csrf_token": csrf(consultation.text),
        "question": "我最应该突出哪一段已确认经历？",
    })
    assert fallback.status_code == 200
    assert "平台 AI 当前不可用" in fallback.text


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
    manual = client.get("/jobs/manual")
    detail = client.post("/jobs/manual", data={
        "csrf_token": csrf(manual.text),
        "url": "https://company.example/jobs/tenant-a-only",
        "title": "Tenant A Private Role",
        "company": "Tenant A Company",
        "location": "Sydney, Australia",
        "description": "Private tenant test role using Excel and financial analysis.",
    }, follow_redirects=True)
    with client.app.state.session_factory() as db:
        rec_a = db.scalar(
            select(Recommendation).join(User, User.id == Recommendation.user_id).where(
                User.email_lookup == email_lookup("tenant-a@example.com", client.app.state.settings.email_lookup_secret)
            ).order_by(Recommendation.id.desc())
        )
        assert rec_a is not None
        job_id_a = rec_a.job_id
    client.post(f"/recommendations/{rec_a.id}/pack", data={"csrf_token": csrf(detail.text)}, follow_redirects=True)
    with client.app.state.session_factory() as db:
        pack_a = db.scalar(select(ApplicationPack).where(ApplicationPack.user_id == rec_a.user_id))
        assert pack_a
    applications = client.get("/applications")
    recorded = client.post("/applications", data={
        "csrf_token": csrf(applications.text),
        "job_id": job_id_a,
        "status": "submitted",
        "evidence": "Tenant A confirmation evidence",
        "notes": "Tenant A private note",
    }, follow_redirects=True)
    assert "申请进度已保存" in recorded.text
    with client.app.state.session_factory() as db:
        progress_a = db.scalar(select(ApplicationProgress).where(ApplicationProgress.user_id == rec_a.user_id))
        assert progress_a is not None

    page = client.get("/recommendations")
    client.post("/logout", data={"csrf_token": csrf(page.text)}, follow_redirects=True)
    register_verify(client, "tenant-b@example.com")
    complete_onboarding(client)

    response = client.get(f"/recommendations/{rec_a.id}", follow_redirects=False)
    assert response.status_code == 404
    response = client.get(f"/application-packs/{pack_a.id}", follow_redirects=False)
    assert response.status_code == 404
    assert client.get(f"/recommendations/{rec_a.id}/ai", follow_redirects=False).status_code == 404
    assert client.get(f"/application-packs/{pack_a.id}/edit", follow_redirects=False).status_code == 404
    assert client.get(f"/application-packs/{pack_a.id}/ai", follow_redirects=False).status_code == 404
    assert client.get(f"/applications/{progress_a.id}/edit", follow_redirects=False).status_code == 404
    applications_b = client.get("/applications")
    assert "Tenant A Private Role" not in applications_b.text
    assert "Tenant A confirmation evidence" not in applications_b.text
    forbidden_event = client.post("/applications", data={
        "csrf_token": csrf(applications_b.text),
        "job_id": job_id_a,
        "status": "pending",
        "evidence": "",
        "notes": "",
    }, follow_redirects=False)
    assert forbidden_event.status_code == 404
    exported = client.get("/settings/data/export")
    assert exported.status_code == 200
    assert "Tenant A Private Role" not in json.dumps(exported.json())
    assert "Tenant A private note" not in json.dumps(exported.json())


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
