from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models import CandidateProfile, DiscoveryRun, Recommendation, Resume, User, utcnow
from .conftest import complete_onboarding, register_verify


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
