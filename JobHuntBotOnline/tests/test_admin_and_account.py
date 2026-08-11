from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select

from app import ai
from app.models import User
from app.security import email_lookup
from .conftest import complete_onboarding, csrf, register_verify


def login(client, email: str, password: str):
    page = client.get("/login")
    return client.post("/login", data={
        "csrf_token": csrf(page.text),
        "email": email,
        "password": password,
    }, follow_redirects=True)


def logout(client):
    page = client.get("/dashboard", follow_redirects=True)
    return client.post("/logout", data={"csrf_token": csrf(page.text)}, follow_redirects=True)


def test_admin_can_change_quota_and_disable_user(client, settings):
    register_verify(client, "managed@example.com")
    complete_onboarding(client)
    logout(client)
    response = login(client, settings.admin_email, settings.admin_password)
    assert response.status_code == 200

    with client.app.state.session_factory() as db:
        target = db.scalar(select(User).where(User.email_lookup == email_lookup("managed@example.com", settings.email_lookup_secret)))
        assert target
        target_id = target.id

    page = client.get("/admin/users")
    response = client.post(f"/admin/users/{target_id}/quota", data={
        "csrf_token": csrf(page.text),
        "quota": 17,
    }, follow_redirects=True)
    assert "AI 额度已更新" in response.text

    response = client.post(f"/admin/users/{target_id}/toggle", data={
        "csrf_token": csrf(response.text),
    }, follow_redirects=True)
    assert "用户状态已更新" in response.text

    with client.app.state.session_factory() as db:
        target = db.get(User, target_id)
        assert target.daily_ai_request_limit == 17
        assert target.is_active is False

    logout(client)
    denied = login(client, "managed@example.com", "ValidPass123")
    assert "账户已停用" in denied.text


def test_user_can_delete_own_account(client, settings):
    register_verify(client, "delete@example.com")
    complete_onboarding(client)
    page = client.get("/settings/data")
    response = client.post("/settings/data/delete", data={
        "csrf_token": csrf(page.text),
        "password": "ValidPass123",
        "confirmation": "删除我的账户",
    }, follow_redirects=True)
    assert "账户和个人数据已删除" in response.text
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.email_lookup == email_lookup("delete@example.com", settings.email_lookup_secret)))
        assert user is None


def test_zero_user_ai_quota_blocks_before_provider_client_is_created(client, settings, monkeypatch):
    provider_calls: list[object] = []

    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            provider_calls.append((args, kwargs))
            raise AssertionError("zero quota must not create a provider client")

    monkeypatch.setattr(ai.httpx, "Client", ForbiddenClient)
    enabled_ai_settings = replace(settings, deepseek_api_key="test-only-deepseek-key")

    with client.app.state.session_factory() as db:
        user = User(
            email_lookup="quota-zero-user",
            email_encrypted=b"test-only-ciphertext",
            password_hash="test-only-password-hash",
            daily_ai_request_limit=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        with pytest.raises(ai.AIUnavailable, match="额度已用完"):
            ai.generate(
                db,
                enabled_ai_settings,
                user,
                system_prompt="test system prompt",
                user_prompt="test user prompt",
            )

    assert provider_calls == []


def test_platform_status_reports_configuration_without_deepseek_secret(client, settings):
    enabled_ai_settings = replace(settings, deepseek_api_key="test-only-deepseek-key")
    with client.app.state.session_factory() as db:
        status = ai.platform_status(db, enabled_ai_settings)

    assert status["configured"] is True
    assert "deepseek_api_key" not in status
    assert "test-only-deepseek-key" not in repr(status)
