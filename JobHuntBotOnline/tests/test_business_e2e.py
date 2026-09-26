"""业务主链路端到端：注册 → 上传两份简历 → 真实来源适配器聚合 → 硬资格过滤 →
按岗位选简历 → DeepSeek 复核 → 导出 DOCX → 六小时后调度器再聚合出新岗位。

外部网络全部由 httpx.MockTransport 应答（Greenhouse / Lever 录制格式、DeepSeek
chat/completions 格式），因此走的是生产同一套适配器解析、打分、路由与导出代码。
第二轮聚合走生产 Scheduler/Worker 调用的同一组函数（enqueue_due_profiles →
claim_run → process_run），不是测试专用入口。
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.discovery import claim_run, enqueue_due_profiles, fail_run, process_run
from app.main import create_app
from app.models import ApplicationPack, CandidateProfile, DiscoveryRun, Job, Recommendation, Resume, utcnow
from .conftest import csrf, register_verify

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")

# Greenhouse board API (`/v1/boards/{board}/jobs?content=true`) 录制格式。
GREENHOUSE_ROUND_1 = {"jobs": [
    {
        "id": 4001, "title": "Graduate Financial Analyst", "updated_at": TODAY,
        "absolute_url": "https://boards.greenhouse.io/harbourfinance/jobs/4001",
        "location": {"name": "Sydney, Australia"},
        "content": "&lt;p&gt;Graduate analyst role using Excel, valuation and financial modelling. "
                   "Full Australian working rights required.&lt;/p&gt;",
    },
    {
        "id": 4002, "title": "Senior Finance Director", "updated_at": TODAY,
        "absolute_url": "https://boards.greenhouse.io/harbourfinance/jobs/4002",
        "location": {"name": "Sydney, Australia"},
        "content": "<p>Director role requiring 15+ years of finance leadership experience and CFA charter.</p>",
    },
]}
GREENHOUSE_ROUND_2_EXTRA = {
    "id": 4003, "title": "Risk Analyst", "updated_at": TODAY,
    "absolute_url": "https://boards.greenhouse.io/harbourfinance/jobs/4003",
    "location": {"name": "Melbourne, Australia"},
    "content": "<p>Risk analyst using Excel and financial reporting. Australian working rights required.</p>",
}
# Lever postings API (`/v0/postings/{company}?mode=json`) 录制格式。
LEVER = [
    {
        "id": "lv-1", "text": "Commercial Solicitor", "createdAt": 1_790_000_000_000,
        "hostedUrl": "https://jobs.lever.co/southernlaw/lv-1",
        "categories": {"location": "Melbourne, Australia", "workplaceType": "hybrid"},
        "descriptionPlain": "Commercial solicitor drafting and reviewing contracts. Requires admission to legal "
                            "practice in Australia and a current practising certificate with 2 years experience.",
        "additionalPlain": "Legal research and due diligence.",
    },
    {
        "id": "lv-2", "text": "General Counsel", "createdAt": 1_790_000_000_000,
        "hostedUrl": "https://jobs.lever.co/southernlaw/lv-2",
        "categories": {"location": "Melbourne, Australia", "workplaceType": "onsite"},
        "descriptionPlain": "General Counsel leading the legal function. Requires 12+ years post-admission "
                            "experience, admission as an Australian lawyer and a current practising certificate.",
        "additionalPlain": "",
    },
]
AI_REVIEW = "AI 复核：最强证据是合同起草与审核经历；待确认：执业证书有效期。"


class FakeInternet:
    """Routes every outbound request the product makes to recorded responses."""

    def __init__(self) -> None:
        self.round = 1
        self.deepseek_requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "boards-api.greenhouse.io" and url.path == "/v1/boards/harbourfinance/jobs":
            payload = json.loads(json.dumps(GREENHOUSE_ROUND_1))
            if self.round >= 2:
                payload["jobs"].append(GREENHOUSE_ROUND_2_EXTRA)
            return httpx.Response(200, json=payload)
        if url.host == "api.lever.co" and url.path == "/v0/postings/southernlaw":
            return httpx.Response(200, json=LEVER)
        if url.host == "api.deepseek.com" and url.path == "/chat/completions":
            assert request.headers["Authorization"] == "Bearer test-deepseek-key"
            self.deepseek_requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                "choices": [{"message": {"content": AI_REVIEW}}],
                "usage": {"total_tokens": 321},
            })
        raise AssertionError(f"unexpected outbound request: {request.method} {url}")


@pytest.fixture
def internet(monkeypatch):
    fake = FakeInternet()
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(fake)
        return real_client(*args, **kwargs)

    # TestClient subclasses the original httpx.Client, so only product code is rerouted.
    monkeypatch.setattr(httpx, "Client", client_factory)
    return fake


@pytest.fixture
def live_sources_client(settings, internet):
    app = create_app(replace(
        settings,
        discovery_fixture_path="",
        greenhouse_boards=["harbourfinance"],
        lever_companies=["southernlaw"],
        deepseek_api_key="test-deepseek-key",
    ))
    with TestClient(app) as client:
        yield client


def _upload(client: TestClient, filename: str) -> None:
    page = client.get("/onboarding/upload")
    response = client.post(
        "/onboarding/upload",
        data={"csrf_token": csrf(page.text)},
        files={"resume": (filename, (FIXTURES / filename).read_bytes(), "text/plain")},
        follow_redirects=True,
    )
    assert response.status_code == 200


def _confirm(client: TestClient) -> None:
    page = client.get("/onboarding/confirm")
    response = client.post("/onboarding/confirm", data={
        "csrf_token": csrf(page.text),
        "primary_roles": "金融分析、法律",
        "target_locations": "Sydney, Melbourne",
        "work_authorization": "Australian full working rights",
        "sponsorship_now": "no",
        "sponsorship_future": "no",
        "work_modes": ["hybrid", "onsite", "remote"],
        "experience_years": "4",
        "professional_credentials": "CPA、JD、PLT、澳大利亚律师准入、澳大利亚执业证书",
        "credentials_confirmed": "true",
        "legal_admission": "admitted",
        "practising_certificate": "current",
        "relocation": "no",
        "available_start": "2026-11",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "岗位推荐" in response.text


def _recommendations(client: TestClient) -> dict[str, Recommendation]:
    with client.app.state.session_factory() as db:
        return {job.title: rec for rec, job in db.execute(select(Recommendation, Job).join(Job)).all()}


def test_candidate_gets_eligible_jobs_tailored_docx_and_six_hour_refresh(live_sources_client, internet):
    client = live_sources_client
    register_verify(client, "candidate-e2e@example.com")
    _upload(client, "finance_resume.txt")
    _confirm(client)  # 触发首轮聚合（测试环境内联执行同一个 process_run）
    _upload(client, "legal_resume.txt")

    # 1) 聚合：两个真实来源适配器都成功，四个岗位入库。
    with client.app.state.session_factory() as db:
        first_run = db.scalar(select(DiscoveryRun).order_by(DiscoveryRun.id))
        assert first_run.status == "completed", first_run.error_summary
        assert first_run.jobs_seen == 4
        user_id = first_run.user_id
    recs = _recommendations(client)
    assert set(recs) == {"Graduate Financial Analyst", "Senior Finance Director", "Commercial Solicitor", "General Counsel"}

    # 2) 硬资格过滤：年限/资质不够的岗位被判不合格，合格岗位通过。
    assert recs["Senior Finance Director"].qualification == "fail"
    assert recs["General Counsel"].qualification == "fail"
    assert recs["Graduate Financial Analyst"].qualification != "fail"
    assert recs["Commercial Solicitor"].qualification != "fail"
    page = client.get("/recommendations")
    assert "Commercial Solicitor" in page.text and "Graduate Financial Analyst" in page.text

    # 3) 按岗位选简历 + DeepSeek 复核（mock）。
    rec_id = recs["Commercial Solicitor"].id
    detail = client.get(f"/recommendations/{rec_id}")
    pack_page = client.post(f"/recommendations/{rec_id}/pack", data={"csrf_token": csrf(detail.text)}, follow_redirects=True)
    assert pack_page.status_code == 200
    assert "legal_resume.txt" in pack_page.text
    assert len(internet.deepseek_requests) == 1
    assert "candidate-e2e@example.com" not in json.dumps(internet.deepseek_requests[0], ensure_ascii=False)
    with client.app.state.session_factory() as db:
        pack = db.scalar(select(ApplicationPack).order_by(ApplicationPack.id.desc()))
        resume = db.get(Resume, pack.resume_id)
        assert client.app.state.crypto.decrypt_text(resume.original_name_encrypted) == "legal_resume.txt"
        assert client.app.state.crypto.decrypt_json(pack.content_encrypted, {})["ai_enhancement"] == AI_REVIEW
        pack_id = pack.id

    # 4) 导出 DOCX：只含所选法律简历的事实，不串入金融简历。
    download = client.get(f"/application-packs/{pack_id}/resume.docx")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/vnd.openxmlformats")
    text = "\n".join(p.text for p in Document(BytesIO(download.content)).paragraphs)
    assert text.splitlines()[0] == "李安然"
    assert "目标岗位：Commercial Solicitor｜southernlaw" in text
    assert "岗位适配摘要" in text and "相关经历" in text
    assert "Junior Solicitor" in text
    assert "陈晓明" not in text and "CPA Australia" not in text

    # 5) 六小时刷新：未到期不排队；到期后 Scheduler 排队、Worker 处理，新岗位进入推荐。
    with client.app.state.session_factory() as db:
        profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
        assert profile.next_discovery_at - profile.last_discovery_at == timedelta(hours=6)
        assert enqueue_due_profiles(db) == 0
        profile.next_discovery_at = utcnow() - timedelta(minutes=1)  # 时间快进六小时
        db.commit()
        internet.round = 2
        assert enqueue_due_profiles(db) == 1
        run = claim_run(db)
        assert run is not None and run.trigger == "scheduled"
        process_run(db, run, client.app.state.settings, client.app.state.crypto)
        assert run.status == "completed", run.error_summary
    recs = _recommendations(client)
    assert "Risk Analyst" in recs
    assert recs["Risk Analyst"].qualification != "fail"


def test_unexpected_worker_failure_waits_for_the_next_six_hour_slot(live_sources_client):
    client = live_sources_client
    register_verify(client, "failure-e2e@example.com")
    _upload(client, "finance_resume.txt")
    _confirm(client)
    with client.app.state.session_factory() as db:
        user_id = db.scalar(select(DiscoveryRun.user_id))
        profile = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
        profile.next_discovery_at = utcnow() - timedelta(minutes=1)
        db.commit()
        assert enqueue_due_profiles(db) == 1
        run = claim_run(db)
        assert fail_run(db, run.id, "RuntimeError: scoring crashed")
        db.refresh(profile)
        # 否则每分钟一次的 Scheduler 会立刻把同一个失败用户再次排队，持续打外部来源。
        assert profile.next_discovery_at > utcnow() + timedelta(hours=5, minutes=59)
        assert enqueue_due_profiles(db) == 0
