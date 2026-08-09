from app.auth import safe_next_url


def test_health_endpoints(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"
    status = client.get("/api/status").json()
    assert status["product"] == "JobHuntBot Online"
    assert "long_term_sync" in status


def test_protected_page_redirects_to_login(client):
    response = client.get("/jobs", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_next_url_rejects_external_redirect():
    assert safe_next_url("https://evil.example") == "/"
    assert safe_next_url("//evil.example") == "/"
    assert safe_next_url("/jobs") == "/jobs"


def test_security_headers(client):
    response = client.get("/login")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_password_change_invalidates_other_signed_sessions(client):
    from tests.conftest import csrf_from

    # First browser signs in and keeps a valid session cookie.
    login_page = client.get("/login")
    token = csrf_from(login_page)
    assert client.post(
        "/login",
        data={
            "email": "owner@test.local",
            "password": "Correct-Horse-Battery-2026",
            "csrf_token": token,
            "next_url": "/",
        },
        follow_redirects=False,
    ).status_code == 303

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as second:
        page = second.get("/login")
        second_token = csrf_from(page)
        assert second.post(
            "/login",
            data={
                "email": "owner@test.local",
                "password": "Correct-Horse-Battery-2026",
                "csrf_token": second_token,
                "next_url": "/settings",
            },
            follow_redirects=False,
        ).status_code == 303

        settings_page = second.get("/settings")
        settings_token = csrf_from(settings_page)
        changed = second.post(
            "/settings/password",
            data={
                "csrf_token": settings_token,
                "current_password": "Correct-Horse-Battery-2026",
                "new_password": "New-Owner-Password-2026",
                "confirm_password": "New-Owner-Password-2026",
            },
            follow_redirects=False,
        )
        assert changed.status_code == 303

    stale = client.get("/jobs", follow_redirects=False)
    assert stale.status_code == 303
    assert stale.headers["location"].startswith("/login")


def test_sensitive_structured_fields_are_not_plaintext_in_sqlite(login):
    client = login
    from pathlib import Path
    import sqlite3

    from app.config import get_settings

    settings = get_settings()
    # Existing fixture completes onboarding and stores a resume/experience through the real routes.
    response = client.get("/onboarding")
    from tests.conftest import csrf_from
    token = csrf_from(response)
    client.post(
        "/profile",
        data={
            "csrf_token": token,
            "preferred_name": "DiskSecretName",
            "legal_name": "Disk Secret Legal Name",
            "email": "disk-secret@example.invalid",
            "phone": "+61 412 345 678",
            "current_location": "Private Sydney Address",
            "linkedin_url": "",
            "github_url": "",
            "portfolio_url": "",
            "current_status": "Private current status",
            "degree_summary": "Private degree summary",
            "graduation_year": "2027",
            "professional_experience_years": "1",
            "work_authorization_country": "Australia",
            "work_authorization_text": "Private work authorization statement",
            "sponsorship_now": "no",
            "sponsorship_future": "no",
            "target_roles": "Data Analyst",
            "secondary_roles": "",
            "roles_to_avoid": "",
            "industries_to_avoid": "",
            "target_locations": "Sydney",
            "work_mode": "Hybrid",
            "relocation_policy": "Private relocation policy",
            "target_level": "Graduate",
            "available_start_date": "2027-02",
            "salary_strategy": "Private salary strategy",
            "salary_range": "Private salary range",
            "self_identification_strategy": "prefer_not_to_say",
            "next_url": "/resumes",
        },
        follow_redirects=True,
    )
    resume_page = client.get("/resumes")
    resume_token = csrf_from(resume_page)
    resume_path = Path(__file__).parents[1] / "fixtures" / "sample_resume.txt"
    with resume_path.open("rb") as handle:
        uploaded = client.post(
            "/resumes/upload",
            data={
                "csrf_token": resume_token,
                "label": "Private Resume Label",
                "role_family": "Private Data Role",
                "is_default": "yes",
                "auto_import_experiences": "yes",
            },
            files={"file": ("private_resume.txt", handle, "text/plain")},
            follow_redirects=False,
        )
    assert uploaded.status_code == 303

    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "select preferred_name, legal_name, email, phone, work_authorization_text, salary_range, "
            "sponsorship_now, sponsorship_future, target_roles_json, target_locations_json "
            "from candidate_profiles limit 1"
        ).fetchone()
        resume_row = connection.execute(
            "select label, role_family, source_filename, extracted_text, skills_json from resumes limit 1"
        ).fetchone()
        experience_rows = connection.execute(
            "select title, organization, date_range, description, tags_json, source_ref from experiences"
        ).fetchall()
    finally:
        connection.close()
    assert row is not None
    assert resume_row is not None
    assert all(value in (None, "") or str(value).startswith("enc:v1:") for value in row)
    assert all(value == "" or str(value).startswith("enc:v1:") for value in resume_row)
    assert experience_rows
    assert all(
        value == "" or str(value).startswith("enc:v1:")
        for experience_row in experience_rows
        for value in experience_row
    )
    raw = database_path.read_bytes()
    for secret in (
        b"DiskSecretName",
        b"Disk Secret Legal Name",
        b"disk-secret@example.invalid",
        b"Private work authorization statement",
        b"Private salary range",
        b"Private Resume Label",
        b"Private Data Role",
        b"sample_resume.txt",
        b"UNSW",
    ):
        assert secret not in raw
