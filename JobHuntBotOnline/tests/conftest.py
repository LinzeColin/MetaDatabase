from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="jobhuntos-tests-"))
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("ADMIN_EMAIL", "owner@test.local")
os.environ.setdefault("ADMIN_PASSWORD", "Correct-Horse-Battery-2026")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4=")
os.environ.setdefault("MAINTENANCE_ENABLED", "false")

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    data_dir = Path(os.environ["DATA_DIR"])
    for folder in (data_dir / "uploads", data_dir / "backups", data_dir / "canonical"):
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.iterdir():
            if path.is_file():
                path.unlink()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def csrf_from(response) -> str:
    soup = BeautifulSoup(response.text, "html.parser")
    field = soup.select_one('input[name="csrf_token"]')
    assert field is not None
    return str(field["value"])


@pytest.fixture
def login(client):
    response = client.get("/login")
    token = csrf_from(response)
    response = client.post(
        "/login",
        data={
            "email": "owner@test.local",
            "password": "Correct-Horse-Battery-2026",
            "csrf_token": token,
            "next_url": "/",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


@pytest.fixture
def completed_profile(login):
    client = login
    response = client.get("/onboarding")
    token = csrf_from(response)
    response = client.post(
        "/profile",
        data={
            "csrf_token": token,
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
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/resumes"
    return client


@pytest.fixture
def ready_workspace(completed_profile):
    client = completed_profile
    response = client.get("/resumes")
    token = csrf_from(response)
    resume_path = Path(__file__).parents[1] / "fixtures" / "sample_resume.txt"
    with resume_path.open("rb") as handle:
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
            follow_redirects=False,
        )
    assert response.status_code == 303
    return client
