from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from app.config import get_settings, validate_settings
from app.security import hash_password, validate_password, verify_password


ROOT = Path(__file__).resolve().parents[1]


def test_refresh_contract_is_exactly_six_hours(settings):
    validate_settings(settings)
    with pytest.raises(RuntimeError):
        validate_settings(replace(settings, discovery_refresh_hours=5))
    with pytest.raises(RuntimeError):
        validate_settings(replace(settings, discovery_refresh_hours=12))


def test_registration_is_closed_when_the_deployment_variable_is_missing(monkeypatch):
    monkeypatch.delenv("ALLOW_REGISTRATION", raising=False)
    assert get_settings().allow_registration is False


def test_enabled_owner_entry_requires_a_dedicated_secret(settings):
    with pytest.raises(RuntimeError, match="OWNER_ENTRY_PASSWORD"):
        validate_settings(replace(settings, owner_entry_enabled=True, owner_entry_password=""))


def test_password_contract():
    assert validate_password("short") is not None
    assert validate_password("alllowercase123") is not None
    assert validate_password("NoNumberPassword") is not None
    assert validate_password("ValidPass123") is None
    hashed = hash_password("ValidPass123")
    assert verify_password(hashed, "ValidPass123")
    assert not verify_password(hashed, "WrongPass123")


def test_production_can_deploy_with_registration_closed_while_mail_is_deferred(settings):
    deferred = replace(
        settings,
        app_env="production",
        cookie_secure=True,
        allow_registration=False,
        smtp_host="",
        session_secret="production-session-secret",
        email_lookup_secret="production-email-secret",
        admin_email="owner@example.com",
        admin_password="ValidAdminPass123",
        email_min_interval_seconds=1800,
        email_max_per_user_per_24h=3,
    )
    validate_settings(deferred)


def test_public_registration_requires_standard_smtp_but_not_a_named_vendor(settings):
    base = replace(
        settings,
        app_env="production",
        cookie_secure=True,
        allow_registration=True,
        smtp_host="",
        session_secret="production-session-secret",
        email_lookup_secret="production-email-secret",
        admin_email="owner@example.com",
        admin_password="ValidAdminPass123",
        email_min_interval_seconds=1800,
        email_max_per_user_per_24h=3,
    )
    with pytest.raises(RuntimeError, match="标准 SMTP_HOST"):
        validate_settings(base)
    validate_settings(replace(base, smtp_host="smtp.example.test"))


def test_production_email_cadence_cannot_be_relaxed(settings):
    base = replace(
        settings,
        app_env="production",
        cookie_secure=True,
        allow_registration=True,
        smtp_host="smtp.example.test",
        session_secret="production-session-secret",
        email_lookup_secret="production-email-secret",
        admin_email="owner@example.com",
        admin_password="ValidAdminPass123",
        email_min_interval_seconds=1800,
        email_max_per_user_per_24h=3,
    )
    validate_settings(base)
    with pytest.raises(RuntimeError, match="EMAIL_MIN_INTERVAL_SECONDS"):
        validate_settings(replace(base, email_min_interval_seconds=1799))
    with pytest.raises(RuntimeError, match="EMAIL_MAX_PER_USER_PER_24H"):
        validate_settings(replace(base, email_max_per_user_per_24h=4))


def test_security_header_allows_only_cloudflare_automatic_analytics_script():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "script-src 'self' https://static.cloudflareinsights.com" in main
    assert "connect-src 'self'" in main
    assert "script-src *" not in main


def test_env_generator_keeps_runtime_secrets_beside_requested_output(tmp_path):
    release_dir = tmp_path / "release"
    output = release_dir / ".env"
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "deploy/generate_env.py"),
            "--domain", "jobhunt.example.test",
            "--admin-email", "owner@example.test",
            "--output", str(output),
        ],
        cwd=unrelated_cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = output.read_text(encoding="utf-8")
    assert "DOMAIN='jobhunt.example.test'" in rendered
    assert "ALLOW_REGISTRATION='false'" in rendered
    assert "OWNER_ENTRY_PASSWORD='" in rendered
    for path in [output, release_dir / "OWNER_LOGIN.txt", release_dir / "secrets/postgres_password.txt"]:
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not (unrelated_cwd / "OWNER_LOGIN.txt").exists()
    assert not (unrelated_cwd / "secrets/postgres_password.txt").exists()
    login = (release_dir / "OWNER_LOGIN.txt").read_text(encoding="utf-8")
    assert "OWNER_ENTRY_PASSWORD=" in login
