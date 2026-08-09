from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from app.auth import authenticate_user
from app.cli import command_create_acceptance_user, command_delete_acceptance_user, command_reset_owner_password
from app.config import get_settings
from app.db import SessionLocal
from app.models import Resume, User
from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]


def test_generated_environment_is_shell_safe_and_recoverable(tmp_path):
    env_file = tmp_path / ".env"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "deploy" / "generate_env.py"),
            "--domain",
            "jobhunt.example.invalid",
            "--admin-email",
            "owner@example.invalid",
            "--data-path",
            "/srv/jobhuntos-test-data",
            "--output",
            str(env_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                'set -a; source "$1"; '
                'printf "%s\\n%s\\n%s\\n%s\\n%s\\n%s\\n" '
                '"$APP_NAME" "$ADMIN_PASSWORD" "$HOST_DATA_GID" '
                '"$DEEPSEEK_API_KEY" "$DEEPSEEK_FAST_MODEL" "$DEEPSEEK_PRECISION_MODEL"'
            ),
            "bash",
            str(env_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    app_name, password, host_gid, deepseek_key, fast_model, precision_model = result.stdout.splitlines()
    assert app_name == "JobHuntBot Online"
    assert len(password) == 24
    assert host_gid.isdigit()
    assert "DATA_PATH=/srv/jobhuntos-test-data" in env_file.read_text(encoding="utf-8")
    assert deepseek_key == ""
    assert fast_model == "deepseek-v4-flash"
    assert precision_model == "deepseek-v4-pro"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    login_file = tmp_path / "OWNER_LOGIN.txt"
    assert stat.S_IMODE(login_file.stat().st_mode) == 0o600
    login_text = login_file.read_text(encoding="utf-8")
    assert "数据恢复密钥：" in login_text
    assert "一次性初始密码：" in login_text
    assert "DeepSeek API Key 也在该页面粘贴一次并验证" in login_text


def test_sync_status_never_calls_partial_sync_fully_synced(tmp_path):
    status_file = tmp_path / "sync_status.json"

    def update(channel: str, state: str, message: str) -> dict[str, object]:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "ops" / "update_sync_status.py"),
                "--file",
                str(status_file),
                "--channel",
                channel,
                "--state",
                state,
                "--message",
                message,
            ],
            check=True,
        )
        return json.loads(status_file.read_text(encoding="utf-8"))

    assert update("structured", "synced", "structured ok")["state"] == "synced"
    assert update("objects", "not_configured", "objects absent")["state"] == "not_configured"
    assert update("objects", "synced", "objects ok")["state"] == "synced"
    assert update("structured", "failed", "structured failed")["state"] == "failed"
    assert stat.S_IMODE(status_file.stat().st_mode) == 0o660


def test_owner_password_can_be_recovered_without_command_line_secret(client, tmp_path):
    destination = tmp_path / "reset.txt"
    try:
        assert command_reset_owner_password(str(destination)) == 0
        text = destination.read_text(encoding="utf-8")
        match = re.search(r"Temporary password: (.+)", text)
        assert match
        password = match.group(1).strip()
        with SessionLocal() as db:
            user = authenticate_user(db, "owner@test.local", password)
            stored = db.scalar(select(User).where(User.email == "owner@test.local"))
            assert stored is not None
            assert stored.session_version == 2
        assert user is not None
        assert stat.S_IMODE(destination.stat().st_mode) == 0o640
    finally:
        destination.unlink(missing_ok=True)


def test_production_dependencies_and_ingress_contract_are_frozen_to_reviewed_versions():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert requirements == [
        "fastapi==0.141.1",
        "starlette==1.3.1",
        "uvicorn[standard]==0.51.0",
        "SQLAlchemy==2.0.51",
        "Jinja2==3.1.6",
        "python-multipart==0.0.32",
        "httpx==0.28.1",
        "beautifulsoup4==4.15.0",
        "pypdf==6.14.2",
        "python-docx==1.2.0",
        "argon2-cffi==25.1.0",
        "cryptography==50.0.0",
        "itsdangerous==2.2.0",
    ]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert dockerfile.startswith("FROM python:3.13.14-slim-trixie\n")
    assert "COPY tools/verify_runtime.py ./tools/verify_runtime.py" in dockerfile
    assert "image: jobhuntos-online:0.2.0" in compose
    assert 'traefik.enable: "true"' in compose
    assert 'traefik.docker.network: "coolify"' in compose
    assert 'traefik.http.routers.jobhuntos.tls.certresolver: "letsencrypt"' in compose
    assert 'traefik.http.middlewares.jobhuntos-https.redirectscheme.scheme: "https"' in compose
    assert "caddy:" not in compose


def test_target_acceptance_requires_runtime_provider_and_dependency_consistency():
    acceptance = (ROOT / "deploy" / "acceptance.sh").read_text(encoding="utf-8")
    taskpack_validator = (ROOT / "tools" / "validate_taskpack.py").read_text(encoding="utf-8")
    assert 'tools/verify_runtime.py | tee "$evidence_dir/host-runtime-versions.json"' in acceptance
    assert 'python tools/verify_runtime.py --expected-python 3.13.14 | tee "$evidence_dir/container-runtime-versions.json"' in acceptance
    assert 'python -m pip check | tee "$evidence_dir/container-pip-check.txt"' in acceptance
    assert 'python -m pip freeze | tee "$evidence_dir/container-installed-packages.txt"' in acceptance
    assert 'TRAEFIK_PROXY_CONTAINER' in acceptance
    assert 'traefik-proxy-status.txt' in acceptance
    assert 'traefik-route-enabled.txt' in acceptance
    assert 'http-to-https.txt' in acceptance
    assert "docker compose exec -T caddy" not in acceptance
    assert 'python -m app.cli reencrypt-sensitive' in acceptance
    assert 'python -m app.cli verify-sensitive-storage' in acceptance
    assert "umask 077" in acceptance
    assert 'ai_ready = bool(deepseek.get("ready"))' in acceptance
    assert '"core_result": "PASS"' in acceptance
    assert "DeepSeek 尚未由 Owner 在网页中粘贴密钥并完成真实连通验证" in acceptance
    assert "docker compose config --quiet" in acceptance
    assert "docker compose config --services" in acceptance
    assert "docker compose config --images" in acceptance
    assert "compose-rendered.yaml" not in acceptance
    assert "create-acceptance-user" in acceptance
    assert "tests/e2e_live_golden.py" in acceptance
    assert "docker compose restart app" in acceptance
    assert "delete-acceptance-user" in acceptance
    assert 'credential_container="/data/.jobhuntos-acceptance-' in acceptance
    assert "--allow-production-runtime-secrets" in acceptance
    assert "env -i" in acceptance
    assert "jobhuntos-pytest-data" in acceptance
    assert "Unit tests must never inherit it" in acceptance
    assert "production runtime secret has unsafe location or permissions" in taskpack_validator
    live_browser = (ROOT / "tests" / "e2e_live_golden.py").read_text(encoding="utf-8")
    assert "static.cloudflareinsights.com/beacon.min.js" in live_browser
    assert "strict CSP must continue to block it" in live_browser


def test_long_term_sync_uses_clone_free_private_database_client_and_fail_closed_r2():
    private_sync = (ROOT / "ops" / "sync_private_database.sh").read_text(encoding="utf-8")
    r2_sync = (ROOT / "ops" / "sync_r2.sh").read_text(encoding="utf-8")
    r2_timer = (ROOT / "deploy" / "systemd" / "jobhuntos-r2-sync.timer").read_text(encoding="utf-8")
    assert 'python3 "$client_path" put "$area" "$target_path" "$source_file"' in private_sync
    assert "PRIVATE_DATABASE_REPO_PATH" not in private_sync
    assert 'R2_SYNC_ENABLED:-false' in r2_sync
    assert r2_sync.count("--fast-list") == 3
    assert "OnCalendar=*-*-* 05:00:00 UTC" in r2_timer
    assert "OnUnitActiveSec" not in r2_timer


def test_deploy_preserves_exact_previous_image_and_targets_current_release():
    script = (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert "docker compose images -q app" in script
    assert 'docker tag "$current_image_id" jobhuntos-online:previous' in script
    assert "docker tag jobhuntos-online:previous jobhuntos-online:0.2.0" in script
    assert script.index("docker image inspect jobhuntos-online:0.2.0") < script.index(
        "docker image inspect jobhuntos-online:0.1.0"
    )


def test_restore_uses_empty_staging_and_reverts_on_failed_readiness():
    script = (ROOT / "deploy" / "restore.sh").read_text(encoding="utf-8")
    assert "restore-staging" in script
    assert 'python -m app.cli verify-sensitive-storage' in script
    assert 'mv "$data_path" "$previous"' in script
    assert 'mv "$previous" "$data_path"' in script
    assert "reverted_to_previous_data" in script


def test_isolated_acceptance_user_lifecycle_removes_database_and_upload(client, tmp_path):
    settings = get_settings()
    credential_file = tmp_path / "probe.json"
    assert command_create_acceptance_user(str(credential_file)) == 0
    payload = json.loads(credential_file.read_text(encoding="utf-8"))
    assert payload["email"].endswith("@acceptance.invalid")
    assert len(payload["password"]) >= 20
    assert stat.S_IMODE(credential_file.stat().st_mode) == 0o600

    upload = settings.data_dir / "uploads" / "acceptance-probe.bin"
    upload.write_bytes(b"encrypted-probe")
    with SessionLocal() as db:
        db.add(
            Resume(
                user_id=int(payload["user_id"]),
                label="Acceptance Resume",
                role_family="Data Analyst",
                source_filename="probe.txt",
                file_type="txt",
                encrypted_file_path=str(upload),
                extracted_text="Acceptance-only fixture text " * 6,
                skills_json="[]",
                is_default=True,
            )
        )
        db.commit()

    assert command_delete_acceptance_user(payload["email"]) == 0
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == payload["email"])) is None
    assert not upload.exists()
    canonical = settings.canonical_export_path.read_text(encoding="utf-8")
    assert payload["email"] not in canonical


def test_production_rejects_public_development_credentials(tmp_path):
    env = dict(os.environ)
    env.update(
        {
            "DATA_DIR": str(tmp_path / "production-data"),
            "APP_ENV": "production",
            "BASE_URL": "https://jobhunt.example.invalid",
            "COOKIE_SECURE": "true",
            "ADMIN_EMAIL": "owner@example.invalid",
            "ADMIN_PASSWORD": "Correct-Horse-Battery-2026",
            "SESSION_SECRET": "test-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789",
            "DATA_ENCRYPTION_KEY": "v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4=",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "from app.config import get_settings; get_settings()"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "SESSION_SECRET" in combined
    assert "DATA_ENCRYPTION_KEY" in combined
    assert "ADMIN_PASSWORD" in combined
