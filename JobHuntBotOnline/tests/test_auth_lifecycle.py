from __future__ import annotations

from urllib.parse import urlparse

from .conftest import csrf, latest_link, register_verify


def test_registration_verification_login_logout(client):
    register_verify(client, "new@example.com")
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 303 or "上传简历" in dashboard.text

    page = client.get("/onboarding/upload")
    token = csrf(page.text)
    response = client.post("/logout", data={"csrf_token": token}, follow_redirects=True)
    assert "上传简历" not in response.text or "开始使用" in response.text

    login = client.get("/login")
    response = client.post("/login", data={
        "csrf_token": csrf(login.text),
        "email": "new@example.com",
        "password": "ValidPass123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "上传简历" in response.text


def test_password_reset_token_is_single_use_and_old_session_invalid(client):
    register_verify(client, "reset@example.com")
    forgot = client.get("/forgot-password")
    client.post("/forgot-password", data={
        "csrf_token": csrf(forgot.text),
        "email": "reset@example.com",
    }, follow_redirects=True)
    link = latest_link(client, "reset")
    parsed = urlparse(link)
    reset_page = client.get(parsed.path + "?" + parsed.query)
    response = client.post("/reset-password", data={
        "csrf_token": csrf(reset_page.text),
        "token": parsed.query.split("token=", 1)[1],
        "password": "NewValidPass123",
        "password_confirm": "NewValidPass123",
    }, follow_redirects=True)
    assert "密码已重置" in response.text

    second = client.post("/reset-password", data={
        "csrf_token": csrf(client.get(parsed.path + "?" + parsed.query).text),
        "token": parsed.query.split("token=", 1)[1],
        "password": "AnotherPass123",
        "password_confirm": "AnotherPass123",
    }, follow_redirects=True)
    assert "无效或已过期" in second.text

    login = client.get("/login")
    old = client.post("/login", data={
        "csrf_token": csrf(login.text),
        "email": "reset@example.com",
        "password": "ValidPass123",
    }, follow_redirects=True)
    assert "不正确" in old.text
    login2 = client.get("/login")
    new = client.post("/login", data={
        "csrf_token": csrf(login2.text),
        "email": "reset@example.com",
        "password": "NewValidPass123",
    }, follow_redirects=True)
    assert "上传简历" in new.text


def test_duplicate_registration_does_not_create_second_account(client):
    register_verify(client, "dup@example.com")
    logout = client.get("/onboarding/upload")
    client.post("/logout", data={"csrf_token": csrf(logout.text)})
    page = client.get("/register")
    response = client.post("/register", data={
        "csrf_token": csrf(page.text),
        "email": "DUP@example.com",
        "display_name": "",
        "password": "ValidPass123",
        "password_confirm": "ValidPass123",
    }, follow_redirects=True)
    assert "已注册" in response.text


def test_registration_links_are_hidden_when_mail_is_deferred(settings):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.main import create_app

    deferred = replace(settings, app_env="production", cookie_secure=True, allow_registration=False, smtp_host="")
    app = create_app(deferred)
    from app.db import Base
    Base.metadata.create_all(app.state.engine)
    with TestClient(app, base_url="https://testserver") as deferred_client:
        landing = deferred_client.get("/")
        assert 'data-testid="hero-register"' not in landing.text
        login = deferred_client.get("/login")
        assert 'data-testid="login-register-link"' not in login.text
        assert 'data-testid="forgot-password-link"' not in login.text
        assert deferred_client.get("/register").status_code == 403
        assert deferred_client.get("/forgot-password").status_code == 503
