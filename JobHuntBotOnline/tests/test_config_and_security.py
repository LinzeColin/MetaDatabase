from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from app.config import validate_settings
from app.security import hash_password, validate_password, verify_password


ROOT = Path(__file__).resolve().parents[1]


def test_refresh_contract_is_exactly_six_hours(settings):
    validate_settings(settings)
    with pytest.raises(RuntimeError):
        validate_settings(replace(settings, discovery_refresh_hours=5))
    with pytest.raises(RuntimeError):
        validate_settings(replace(settings, discovery_refresh_hours=12))


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


def test_production_compose_has_domain_bound_https_route_and_legacy_fallback():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    generator = (ROOT / "deploy/generate_env.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    deploy = (ROOT / "deploy/deploy.sh").read_text(encoding="utf-8")
    acceptance = (ROOT / "deploy/acceptance.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    production_e2e = (ROOT / "tools/e2e_production.py").read_text(encoding="utf-8")
    ops_probe = (ROOT / "tools/ops_probe.py").read_text(encoding="utf-8")
    backup = (ROOT / "deploy/backup.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "deploy/rollback.sh").read_text(encoding="utf-8")

    assert "DOMAIN=" in env_example
    assert "LEGACY_COMPOSE_FILE=" in env_example
    assert "@jobhuntbot-db:5432/jobhunt" in env_example
    assert "traefik.enable:" in compose
    assert "Host(`${DOMAIN}`)" in compose
    assert "aliases:" in compose
    assert "- jobhuntbot-db" in compose
    assert compose.count("disable: true") >= 2
    assert '"DOMAIN": args.domain' in generator
    assert "@jobhuntbot-db:5432/jobhunt" in generator
    assert "COPY deploy ./deploy" in dockerfile
    assert "LEGACY_COMPOSE_FILE" in deploy
    assert "LEGACY_COMPOSE_FILE" in rollback
    assert "legacy-compose:" in deploy
    assert "legacy_active=0" in deploy
    assert 'if [[ "$legacy_active" == "1" ]]; then' in deploy
    assert "python3 deploy/verify_taskpack.py" in deploy
    assert '--user "${ACCEPTANCE_UID:-$(id -u)}:${ACCEPTANCE_GID:-$(id -g)}"' in deploy
    assert "python3 deploy/verify_taskpack.py" in acceptance
    assert 'RUN_REAL_EMAIL_ACCEPTANCE:-false' in acceptance
    assert "REAL_EMAIL_ACCEPTANCE_RUN_ID" in acceptance
    assert "ACCEPTANCE_MIN_EMAIL_GAP_SECONDS" in acceptance
    assert "ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS" in acceptance
    assert 'evidence_runner_user=(--user "${ACCEPTANCE_UID:-$(id -u)}:${ACCEPTANCE_GID:-$(id -g)}")' in acceptance
    assert acceptance.count('"${evidence_runner_user[@]}"') == 4
    assert "acceptance outputs so every run creates fresh evidence" in acceptance
    assert "root result is the production-completion authority" in acceptance
    assert '"target-email.json"' in acceptance
    assert "docker compose --profile acceptance run --rm" in acceptance
    assert 'e2e_production.py:/app/tools/e2e_production.py:ro' in acceptance
    assert "run the configured acceptance harness" in acceptance
    assert 'user: "${ACCEPTANCE_UID:-1000}:${ACCEPTANCE_GID:-1000}"' in compose
    assert "./runtime-data:/app/runtime-data" in compose
    assert 'page.once("dialog"' in production_e2e
    assert "import httpx" not in ops_probe
    assert 'docker compose ps --services --filter status=running' in backup
    assert 'docker run --rm --network "$internal_network" -e DATABASE_URL' in backup


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
    for path in [output, release_dir / "OWNER_LOGIN.txt", release_dir / "secrets/postgres_password.txt"]:
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not (unrelated_cwd / "OWNER_LOGIN.txt").exists()
    assert not (unrelated_cwd / "secrets/postgres_password.txt").exists()
