from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import (
    AIApplicationEnhancement,
    AIProviderConfig,
    AIUsageRecord,
    ApplicationPack,
    CandidateProfile,
    Experience,
    Job,
    Resume,
)
from app.services.ai_provider import (
    AIProviderError,
    enhance_application,
    provider_view,
    save_provider_config,
    verify_connection,
)
from app.services.analyzer import analyse_job
from tests.conftest import csrf_from
from tests.test_routes import create_job


FAKE_KEY = "sk-test-deepseek-secret-1234567890"


def _success_body(*, suggested_action: str = "Skip") -> dict[str, object]:
    content = {
        "summary_zh": "该岗位与数据分析方向一致，但所有硬性资格仍应以规则核验为准。",
        "reasons_zh": ["现有 Python、SQL 与 Power BI 经历能够支持申请。"],
        "risks_zh": ["需要人工确认岗位是否仍开放。"],
        "questions_for_user_zh": ["是否愿意投入时间定制这一岗位？"],
        "matched_skills": ["Python", "SQL", "Power BI"],
        "missing_skills": ["Tableau"],
        "why_role_en": "I am interested in this role because it aligns with my verified analytics experience.",
        "why_company_en": "The responsibilities in this posting align with my evidence-backed experience.",
        "confidence": "medium",
        "suggested_action": suggested_action,
    }
    return {
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 180, "total_tokens": 1080},
    }


def test_web_saved_key_is_encrypted_and_never_echoed(ready_workspace):
    client = ready_workspace
    response = client.get("/settings")
    assert response.status_code == 200
    token = csrf_from(response)
    response = client.post(
        "/settings/deepseek",
        data={
            "csrf_token": token,
            "api_key": FAKE_KEY,
            "default_mode": "fast",
            "daily_request_limit": "25",
            "daily_token_limit": "250000",
            "consent": "yes",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert FAKE_KEY not in response.text
    assert FAKE_KEY[-4:] in response.text
    assert "当前保持停用" in response.text

    with SessionLocal() as db:
        raw = db.execute(text("SELECT api_key FROM ai_provider_configs LIMIT 1")).scalar_one()
        config = db.scalar(select(AIProviderConfig))
        assert FAKE_KEY not in str(raw)
        assert str(raw).startswith("enc:v1:")
        assert config is not None and config.api_key == FAKE_KEY
        assert config.enabled is False


def test_connection_verification_uses_official_models_and_json_mode(ready_workspace):
    create_job(ready_workspace)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"status":"ok"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
            },
        )

    with SessionLocal() as db:
        owner_id = db.scalar(select(CandidateProfile.id))
        profile = db.scalar(select(CandidateProfile))
        assert profile is not None and owner_id is not None
        config = save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        view = asyncio.run(
            verify_connection(
                db,
                user_id=profile.user_id,
                transport=httpx.MockTransport(handler),
            )
        )
        db.commit()
        assert view.ready is True
        assert config.last_success_at is not None

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == f"Bearer {FAKE_KEY}"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}


def test_ai_enhancement_redacts_direct_identifiers_and_cannot_override_rules(ready_workspace):
    job_id = create_job(ready_workspace)
    captured_body = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = request.content.decode("utf-8")
        return httpx.Response(200, json=_success_body(suggested_action="Skip"))

    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        job = db.get(Job, job_id)
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job_id))
        resumes = list(db.scalars(select(Resume).where(Resume.user_id == profile.user_id)))
        experiences = list(db.scalars(select(Experience).where(Experience.user_id == profile.user_id)))
        assert profile and job and pack and resumes
        profile.linkedin_url = "https://linkedin.example/in/linze"
        profile.portfolio_url = "https://private-portfolio.example/linze"
        profile.work_authorization_text = (
            "Australian work rights confirmed. Contact linze@example.com or +61 400 000 000; "
            "private evidence: https://private-portfolio.example/linze"
        )
        db.add(profile)
        rule_result = analyse_job(profile=profile, job=job, resumes=resumes, experiences=experiences)
        selected_resume = db.get(Resume, pack.resume_id)
        selected = [item for item in experiences if item.id in set(pack.experience_ids)]
        original_recommendation = job.recommendation
        original_eligibility = job.eligibility_status

        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        outcome = asyncio.run(
            enhance_application(
                db,
                user_id=profile.user_id,
                profile=profile,
                job=job,
                rule_result=rule_result,
                resume=selected_resume,
                experiences=selected,
                application_pack=pack,
                force=True,
                transport=httpx.MockTransport(handler),
            )
        )
        db.commit()
        db.refresh(job)
        db.refresh(pack)
        assert outcome.status == "success"
        assert job.recommendation == original_recommendation
        assert job.eligibility_status == original_eligibility
        assert "DeepSeek 语义说明" in pack.fit_summary
        assert "verified analytics experience" in pack.why_role_draft
        enhancement = db.scalar(select(AIApplicationEnhancement).where(AIApplicationEnhancement.job_id == job_id))
        assert enhancement is not None and enhancement.content["suggested_action"] == "Skip"

    assert "Linze Zhang" not in captured_body
    assert "linze@example.com" not in captured_body
    assert "+61 400 000 000" not in captured_body
    assert "https://private-portfolio.example/linze" not in captured_body
    assert "https://linkedin.example/in/linze" not in captured_body
    assert FAKE_KEY not in captured_body
    assert "Data Analyst Intern" in captured_body


def test_provider_failure_preserves_deterministic_pack_and_records_failure(ready_workspace):
    job_id = create_job(ready_workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        job = db.get(Job, job_id)
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job_id))
        resumes = list(db.scalars(select(Resume).where(Resume.user_id == profile.user_id)))
        experiences = list(db.scalars(select(Experience).where(Experience.user_id == profile.user_id)))
        assert profile and job and pack and resumes
        rule_result = analyse_job(profile=profile, job=job, resumes=resumes, experiences=experiences)
        original_draft = pack.why_role_draft
        original_recommendation = job.recommendation
        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="precision",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        outcome = asyncio.run(
            enhance_application(
                db,
                user_id=profile.user_id,
                profile=profile,
                job=job,
                rule_result=rule_result,
                resume=db.get(Resume, pack.resume_id),
                experiences=[item for item in experiences if item.id in set(pack.experience_ids)],
                application_pack=pack,
                requested_mode="precision",
                force=True,
                transport=httpx.MockTransport(handler),
            )
        )
        db.commit()
        assert outcome.status == "failed"
        assert job.recommendation == original_recommendation
        assert pack.why_role_draft == original_draft
        usage = db.scalar(select(AIUsageRecord).where(AIUsageRecord.job_id == job_id))
        enhancement = db.scalar(select(AIApplicationEnhancement).where(AIApplicationEnhancement.job_id == job_id))
        assert usage is not None and usage.status == "failed" and usage.error_code == "provider_unavailable"
        assert enhancement is not None and enhancement.status == "failed"
        view = provider_view(db, profile.user_id)
        assert view.configured is True


def test_invalid_key_is_mapped_without_exposing_provider_body(ready_workspace):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "provider secret detail"}})

    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        assert profile is not None
        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        try:
            asyncio.run(
                verify_connection(
                    db,
                    user_id=profile.user_id,
                    transport=httpx.MockTransport(handler),
                )
            )
        except AIProviderError as exc:
            assert exc.code == "invalid_key"
            assert "provider secret detail" not in exc.user_message
        else:
            raise AssertionError("Expected invalid key failure")
        config = db.scalar(select(AIProviderConfig))
        assert config is not None and config.circuit_open_until is not None


def test_settings_enable_flow_and_job_route_use_deepseek_without_real_network(ready_workspace, monkeypatch):
    async def fake_request_json(**kwargs):
        if kwargs.get("max_tokens") == 64:
            return {
                "choices": [{"message": {"content": '{"status":"ok"}'}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
            }, 25
        return _success_body(suggested_action="Apply"), 80

    import app.services.ai_provider as provider_module

    monkeypatch.setattr(provider_module, "_request_json", fake_request_json)
    client = ready_workspace
    response = client.get("/settings")
    token = csrf_from(response)
    response = client.post(
        "/settings/deepseek",
        data={
            "csrf_token": token,
            "api_key": FAKE_KEY,
            "default_mode": "fast",
            "daily_request_limit": "30",
            "daily_token_limit": "300000",
            "consent": "yes",
            "enabled": "yes",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "DeepSeek 已保存、验证并启用" in response.text
    assert FAKE_KEY not in response.text

    job_id = create_job(client)
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert "AI 语义增强" in response.text
    assert "该岗位与数据分析方向一致" in response.text

    with SessionLocal() as db:
        config = db.scalar(select(AIProviderConfig))
        enhancement = db.scalar(select(AIApplicationEnhancement).where(AIApplicationEnhancement.job_id == job_id))
        assert config is not None and config.enabled is True and config.last_success_at is not None
        assert enhancement is not None and enhancement.status == "success"


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (402, "insufficient_balance"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
    ],
)
def test_official_provider_errors_are_mapped_and_do_not_expose_response(
    ready_workspace, status_code, expected_code
):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"error": {"message": "private provider detail"}})

    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        assert profile is not None
        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        with pytest.raises(AIProviderError) as captured:
            asyncio.run(
                verify_connection(
                    db,
                    user_id=profile.user_id,
                    transport=httpx.MockTransport(handler),
                )
            )
        assert captured.value.code == expected_code
        assert "private provider detail" not in captured.value.user_message
        # 429/500 are retried once; a balance failure is not.
        assert calls == (2 if status_code in {429, 500} else 1)


def test_precision_mode_uses_v4_pro_thinking_and_high_effort(ready_workspace):
    job_id = create_job(ready_workspace)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=_success_body(suggested_action="Review"))

    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        job = db.get(Job, job_id)
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job_id))
        resumes = list(db.scalars(select(Resume).where(Resume.user_id == profile.user_id)))
        experiences = list(db.scalars(select(Experience).where(Experience.user_id == profile.user_id)))
        assert profile and job and pack and resumes
        result = analyse_job(profile=profile, job=job, resumes=resumes, experiences=experiences)
        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="precision",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        outcome = asyncio.run(
            enhance_application(
                db,
                user_id=profile.user_id,
                profile=profile,
                job=job,
                rule_result=result,
                resume=db.get(Resume, pack.resume_id),
                experiences=[item for item in experiences if item.id in set(pack.experience_ids)],
                application_pack=pack,
                requested_mode="precision",
                force=True,
                transport=httpx.MockTransport(handler),
            )
        )
        assert outcome.status == "success"

    assert captured["model"] == "deepseek-v4-pro"
    assert captured["thinking"] == {"type": "enabled"}
    assert captured["reasoning_effort"] == "high"
    assert captured["response_format"] == {"type": "json_object"}
    assert "temperature" not in captured
    assert "top_p" not in captured


def test_daily_request_budget_stops_network_but_preserves_rules(ready_workspace):
    job_id = create_job(ready_workspace)
    network_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal network_called
        network_called = True
        return httpx.Response(200, json=_success_body())

    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        job = db.get(Job, job_id)
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.job_id == job_id))
        resumes = list(db.scalars(select(Resume).where(Resume.user_id == profile.user_id)))
        experiences = list(db.scalars(select(Experience).where(Experience.user_id == profile.user_id)))
        assert profile and job and pack and resumes
        result = analyse_job(profile=profile, job=job, resumes=resumes, experiences=experiences)
        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=1,
            daily_token_limit=200000,
        )
        db.add(
            AIUsageRecord(
                user_id=profile.user_id,
                job_id=None,
                operation="existing_usage",
                provider="deepseek",
                model="deepseek-v4-flash",
                mode="fast",
                status="success",
                total_tokens=100,
            )
        )
        db.flush()
        original = pack.why_role_draft
        outcome = asyncio.run(
            enhance_application(
                db,
                user_id=profile.user_id,
                profile=profile,
                job=job,
                rule_result=result,
                resume=db.get(Resume, pack.resume_id),
                experiences=[item for item in experiences if item.id in set(pack.experience_ids)],
                application_pack=pack,
                force=True,
                transport=httpx.MockTransport(handler),
            )
        )
        assert outcome.status == "failed"
        assert "调用次数" in outcome.user_message
        assert pack.why_role_draft == original

    assert network_called is False


def test_replacing_api_key_requires_a_fresh_connection_verification(ready_workspace):
    with SessionLocal() as db:
        profile = db.scalar(select(CandidateProfile))
        assert profile is not None
        config = save_provider_config(
            db,
            user_id=profile.user_id,
            api_key=FAKE_KEY,
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        from datetime import datetime, timezone

        config.last_success_at = datetime.now(timezone.utc)
        config.last_error = ""
        db.flush()
        assert provider_view(db, profile.user_id).ready is True

        save_provider_config(
            db,
            user_id=profile.user_id,
            api_key="sk-test-deepseek-replacement-0987654321",
            enabled=True,
            consent=True,
            default_mode="fast",
            daily_request_limit=20,
            daily_token_limit=200000,
        )
        view = provider_view(db, profile.user_id)
        assert view.configured is True
        assert view.ready is False
        assert view.last_success_at is None
