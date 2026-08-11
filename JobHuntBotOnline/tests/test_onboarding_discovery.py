from __future__ import annotations

import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.main import _confirmed_profile_fields
from app import discovery
from app.models import CandidateProfile, DiscoveryRun, Recommendation, Resume, User, utcnow
from app.resume import extract_text, parse_resume, profile_draft
from app.scoring import score_job, search_matches
from .conftest import complete_onboarding, csrf, register_verify


def test_resume_draft_preserves_unknown_high_impact_preferences():
    parsed = parse_resume("Woven amber clouds drift quietly over hills while lanterns glow beside calm rivers. " * 3)
    draft = profile_draft(parsed)

    assert parsed["role_families"] == []
    assert draft["primary_role_families"] == []
    assert draft["target_locations"] == []
    assert draft["work_mode"] == []
    assert draft["work_authorization"] == ""
    assert draft["sponsorship_now"] == ""
    assert draft["sponsorship_future"] == ""


def test_onboarding_requires_explicit_high_impact_confirmation(client):
    register_verify(client, "confirmation@example.com")
    page = client.get("/onboarding/upload")
    resume_path = Path(__file__).parent / "fixtures" / "resume.txt"
    confirmation = client.post(
        "/onboarding/upload",
        data={"csrf_token": csrf(page.text)},
        files={"resume": ("resume.txt", resume_path.read_bytes(), "text/plain")},
        follow_redirects=True,
    )
    rejected = client.post(
        "/onboarding/confirm",
        data={
            "csrf_token": csrf(confirmation.text),
            "primary_roles": "",
            "target_locations": "",
            "work_authorization": "",
            "sponsorship_now": "",
            "sponsorship_future": "",
        },
        follow_redirects=True,
    )
    assert "请明确至少一个目标岗位族" in rejected.text
    with client.app.state.session_factory() as db:
        profile = db.scalar(
            select(CandidateProfile).join(User, User.id == CandidateProfile.user_id).where(User.is_admin.is_(False))
        )
        assert profile is not None
        assert profile.onboarding_state == "needs_confirmation"
        assert profile.discovery_enabled is False
        assert db.scalar(select(DiscoveryRun)) is None


def test_server_confirmation_validation_rejects_unconfirmed_or_invalid_facts():
    base = {
        "primary_roles": "Finance",
        "target_locations": "Sydney",
        "work_authorization": "Australian full working rights",
        "sponsorship_now": "no",
        "sponsorship_future": "no",
        "work_modes": ["hybrid"],
        "relocation": "no",
        "available_start": "",
        "avoid_roles": "",
        "avoid_industries": "",
    }
    for overrides in [
        {"work_authorization": ""},
        {"sponsorship_now": "maybe"},
        {"work_modes": []},
        {"work_modes": ["hybrid", "private-network"]},
        {"relocation": "maybe"},
    ]:
        payload = {**base, **overrides}
        confirmed, error = _confirmed_profile_fields(**payload)
        assert confirmed is None
        assert error


def test_uncertain_sponsorship_remains_pending_for_no_sponsorship_job():
    score = score_job(
        {
            "target_locations": ["Sydney"],
            "work_authorization": "Australian full working rights",
            "sponsorship_now": "uncertain",
            "sponsorship_future": "uncertain",
            "work_mode": ["hybrid"],
            "skills": [],
            "keywords": [],
            "primary_role_families": [],
        },
        {
            "title": "Analyst",
            "description": "This employer offers no sponsorship.",
            "location": "Sydney",
            "city": "Sydney",
            "work_mode": "hybrid",
            "skills": [],
            "keywords": [],
        },
    )
    assert score["qualification"] == "pending"
    assert "Sponsorship 情况尚未确认" in score["reasons"]


def test_industry_list_is_normalized_for_avoidance_scoring():
    score = score_job(
        {
            "target_locations": [],
            "work_authorization": "Australian full working rights",
            "sponsorship_now": "no",
            "sponsorship_future": "no",
            "work_mode": [],
            "skills": [],
            "keywords": [],
            "primary_role_families": [],
            "avoid_industries": ["Gambling"],
        },
        {
            "title": "Compliance Analyst",
            "description": "Review controls.",
            "industry": ["Financial Services", "Gambling"],
            "location": "Sydney",
            "work_mode": "hybrid",
            "skills": [],
            "keywords": [],
        },
    )
    assert score["qualification"] == "fail"
    assert "职位属于你明确不接受的行业" in score["reasons"]


def test_legal_role_aliases_keep_engineering_out_of_high_relevance():
    profile = {
        "primary_role_families": ["法律"],
        "secondary_role_families": [],
        "target_locations": [],
        "work_mode": [],
        "skills": [],
        "keywords": [],
        "work_authorization": "Australian full working rights",
        "sponsorship_now": "no",
        "sponsorship_future": "no",
    }
    legal = score_job(profile, {
        "title": "Legal Counsel",
        "description": "Commercial contracts and legal advisory work.",
        "role_family": "Legal",
        "location": "Remote Australia",
        "work_mode": "remote",
        "skills": [],
        "keywords": [],
    })
    engineering = score_job(profile, {
        "title": "Software Engineer",
        "description": "Build distributed systems with Python.",
        "role_family": "Data",
        "location": "Remote Australia",
        "work_mode": "remote",
        "skills": ["python"],
        "keywords": [],
    })
    assert legal["relevance"] == "high"
    assert engineering["relevance"] != "high"
    assert search_matches("法律", "Senior Legal Counsel")
    assert not search_matches("法律", "Senior Software Engineer")


def test_plain_text_resume_falls_back_to_gb18030_without_garbled_output():
    text = ("法律顾问，负责合同审阅、合规与争议解决。\n" * 8).encode("gb18030")
    extracted = extract_text("resume.txt", "text/plain", text)
    assert "法律顾问" in extracted
    assert "�" not in extracted


def test_jobicy_uses_one_documented_legal_tag_and_caps_count():
    class Response:
        def json(self):
            return {"jobs": []}

    class Client:
        params = None

        def get(self, _url, params):
            self.params = params
            return Response()

    client = Client()
    assert discovery._jobicy(client, 120, {"primary_role_families": ["法律"]}) == []
    assert client.params == {"count": 100, "tag": "legal"}


def test_stale_discovery_run_is_closed_for_a_later_refresh(client):
    register_verify(client, "stale-run@example.com")
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.is_admin.is_(False)))
        assert user is not None
        db.add(DiscoveryRun(
            user_id=user.id,
            status="running",
            started_at=utcnow() - timedelta(minutes=10),
        ))
        db.commit()
        assert discovery.recover_stale_runs(db, max_age_seconds=60) == 1
        stale = db.scalar(select(DiscoveryRun).where(DiscoveryRun.status == "failed"))
        assert stale is not None and stale.completed_at is not None


def test_source_deadline_marks_a_hung_provider_failed(settings, monkeypatch):
    def slow_source(_client, _limit):
        time.sleep(2)
        return []

    monkeypatch.setattr(discovery, "_remotive", slow_source)
    guarded = replace(
        settings,
        discovery_fixture_path="",
        discovery_source_timeout_seconds=1,
        enable_remotive=True,
        enable_arbeitnow=False,
        enable_jobicy=False,
    )
    started = time.monotonic()
    rows = list(discovery.fetch_sources(guarded, {}))
    assert time.monotonic() - started < 1.8
    assert rows == [("remotive", "failed", [], "source exceeded 1s deadline")]


def test_resume_first_flow_creates_profile_and_recommendations(client):
    register_verify(client, "candidate@example.com")
    complete_onboarding(client)

    app = client.app
    with app.state.session_factory() as db:
        profile = db.scalar(select(CandidateProfile).join(User, User.id == CandidateProfile.user_id).where(User.is_admin.is_(False)))
        assert profile is not None
        assert profile.onboarding_state == "complete"
        assert profile.discovery_enabled is True
        assert profile.last_discovery_at is not None
        assert profile.next_discovery_at is not None
        delta = profile.next_discovery_at - profile.last_discovery_at
        assert delta == timedelta(hours=6)
        assert db.scalar(select(Resume)) is not None
        assert len(db.scalars(select(Recommendation)).all()) >= 5
        run = db.scalar(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()))
        assert run.status == "completed"
        assert run.jobs_seen >= 5

    feed = client.get("/recommendations")
    assert "Graduate Financial Analyst" in feed.text
    assert "Junior Data Analyst" in feed.text
    assert "每 6 小时刷新" in feed.text


def test_filters_are_composable(client):
    register_verify(client, "filters@example.com")
    complete_onboarding(client)

    default_feed = client.get("/recommendations")
    assert 'name="relevance"' in default_feed.text
    assert '<option value="high" selected>高（默认）</option>' in default_feed.text

    response = client.get("/recommendations", params={
        "city": "Sydney",
        "role": "Finance",
        "skill": "excel",
        "freshness": "7",
    })
    assert response.status_code == 200
    assert "Graduate Financial Analyst" in response.text
    assert "Junior Data Analyst" not in response.text

    response = client.get("/recommendations", params={"qualification": "fail"})
    assert response.status_code == 200


def test_manual_refresh_respects_six_hour_schedule(client):
    register_verify(client, "refresh@example.com")
    complete_onboarding(client)
    page = client.get("/recommendations")
    from .conftest import csrf
    response = client.post("/recommendations/refresh", data={"csrf_token": csrf(page.text)}, follow_redirects=True)
    assert "岗位已刷新" in response.text
    with client.app.state.session_factory() as db:
        profile = db.scalar(select(CandidateProfile).join(User, User.id == CandidateProfile.user_id).where(User.is_admin.is_(False)))
        assert profile.next_discovery_at - profile.last_discovery_at == timedelta(hours=6)
