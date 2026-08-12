from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from sqlalchemy import select

from app.models import ApplicationPack, Job, Recommendation, Resume
from app.scoring import score_job
from app.services import decode_score_evidence
from .conftest import csrf, register_verify


FIXTURES = Path(__file__).parent / "fixtures"


def _upload(client, filename: str):
    page = client.get("/onboarding/upload")
    return client.post(
        "/onboarding/upload",
        data={"csrf_token": csrf(page.text)},
        files={"resume": (filename, (FIXTURES / filename).read_bytes(), "text/plain")},
        follow_redirects=True,
    )


def _confirm(client, *, roles: str, years: str, credentials: str, admission: str = "not_applicable", certificate: str = "not_applicable"):
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
            "work_modes": ["hybrid", "onsite", "remote"],
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
    assert response.status_code == 200
    assert "岗位推荐" in response.text


def _recommendations(client):
    with client.app.state.session_factory() as db:
        return {job.title: (rec, job) for rec, job in db.execute(select(Recommendation, Job).join(Job)).all()}


def _create_pack(client, rec_id: int):
    detail = client.get(f"/recommendations/{rec_id}")
    response = client.post(
        f"/recommendations/{rec_id}/pack",
        data={"csrf_token": csrf(detail.text)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "简历自动路由" in response.text
    return response


def test_finance_and_legal_hard_requirements_are_explainable(client):
    register_verify(client, "finance-hard@example.com")
    assert _upload(client, "finance_resume.txt").status_code == 200
    _confirm(client, roles="金融分析、会计与审计", years="3", credentials="CPA")
    rows = _recommendations(client)
    assert rows["Senior Finance Director"][0].qualification == "fail"
    assert rows["Financial Accountant"][0].qualification == "pass"
    evidence = decode_score_evidence(client.app.state.crypto, rows["Senior Finance Director"][0].reasons_encrypted)
    assert any(item["status"] == "fail" and "15" in item["label"] for item in evidence["requirement_checks"])

    score = score_job(
        {
            "primary_role_families": ["法律"],
            "target_locations": ["Melbourne"],
            "work_mode": ["hybrid"],
            "work_authorization": "Australian full working rights",
            "sponsorship_now": "no",
            "sponsorship_future": "no",
            "experience_years": 4,
            "professional_credentials": ["JD", "PLT"],
            "credentials_confirmed": True,
            "legal_admission": "not_admitted",
            "practising_certificate": "not_current",
        },
        {
            "title": "Commercial Solicitor",
            "description": "Requires admission to legal practice in Australia and a current practising certificate with 2 years experience.",
            "location": "Melbourne, Australia",
            "city": "Melbourne",
            "work_mode": "hybrid",
            "role_family": "Legal",
            "skills": ["contract drafting"],
            "keywords": ["solicitor"],
        },
    )
    assert score["qualification"] == "fail"


def test_job_specific_resume_routing_and_docx_are_fact_bounded(client):
    register_verify(client, "routing-v04@example.com")
    _upload(client, "finance_resume.txt")
    _confirm(
        client,
        roles="金融分析、法律",
        years="4",
        credentials="CPA、JD、PLT、澳大利亚律师准入、澳大利亚执业证书",
        admission="admitted",
        certificate="current",
    )
    _upload(client, "legal_resume.txt")  # Latest/default must not override the job-specific route.
    rows = _recommendations(client)

    finance_page = _create_pack(client, rows["Graduate Financial Analyst"][0].id)
    assert "finance_resume.txt" in finance_page.text
    legal_page = _create_pack(client, rows["Commercial Solicitor"][0].id)
    assert "legal_resume.txt" in legal_page.text

    with client.app.state.session_factory() as db:
        pack = db.scalar(select(ApplicationPack).order_by(ApplicationPack.id.desc()))
        assert pack is not None
        resume = db.get(Resume, pack.resume_id)
        assert resume is not None
        assert client.app.state.crypto.decrypt_text(resume.original_name_encrypted) == "legal_resume.txt"
        pack_id = pack.id

    download = client.get(f"/application-packs/{pack_id}/resume.docx")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/vnd.openxmlformats")
    document = Document(BytesIO(download.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "岗位适配摘要" in text
    assert "Financial Analyst（2023" not in text
    assert "提交前待确认" in text


def test_major_candidate_surfaces_are_chinese(client):
    register_verify(client, "chinese-v04@example.com")
    _upload(client, "finance_resume.txt")
    _confirm(client, roles="金融分析", years="3", credentials="CPA")
    for path in ["/dashboard", "/recommendations", "/onboarding/upload", "/settings/profile", "/applications"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "Why this role" not in response.text
        assert "Application status" not in response.text
        assert "Job family" not in response.text
