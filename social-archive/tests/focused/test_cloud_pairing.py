from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient



def test_pairing_requires_long_term_api_token_for_request_serving_core_only(tmp_path, monkeypatch):
    from social_archive.config import Settings
    data = tmp_path / "data"
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "true")
    monkeypatch.delenv("SOCIAL_ARCHIVE_API_TOKEN_FILE", raising=False)
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_CODE_FILE", str(tmp_path / "pairing-code"))
    settings = Settings.from_env()
    settings.ensure_directories()
    try:
        settings.ensure_directories(require_api_token=True)
    except RuntimeError as exc:
        assert "长期 API Token" in str(exc)
    else:
        raise AssertionError("pairing protection must require a long-term API token")


def test_generated_pairing_code_is_human_readable(tmp_path):
    import subprocess
    code_file = tmp_path / "code"
    token_file = tmp_path / "token"
    script = Path(__file__).parents[2] / "scripts/generate_pairing_code.py"
    result = subprocess.run(["python3", str(script), "--code-file", str(code_file), "--token-file", str(token_file), "--ttl-seconds", "600"], check=True, text=True, capture_output=True)
    code = result.stdout.strip()
    assert len(code) == 14 and code[4] == code[9] == "-"
    assert "0" not in code and "O" not in code and "I" not in code and "1" not in code
    payload = __import__("json").loads(code_file.read_text(encoding="utf-8"))
    assert payload["code"] == code


def test_pairing_generator_preserves_existing_secret_mode(tmp_path):
    import importlib.util

    script = Path(__file__).parents[2] / "scripts/generate_pairing_code.py"
    spec = importlib.util.spec_from_file_location("pairing_generator", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    secret = tmp_path / "pairing-code"
    secret.write_text("previous\n", encoding="utf-8")
    secret.chmod(0o640)

    module.atomic_secret(secret, "replacement")

    assert secret.read_text(encoding="utf-8") == "replacement\n"
    assert secret.stat().st_mode & 0o777 == 0o640


def test_pairing_generator_rejects_more_than_ten_minutes(tmp_path):
    import subprocess
    script = Path(__file__).parents[2] / "scripts/generate_pairing_code.py"
    result = subprocess.run(["python3", str(script), "--code-file", str(tmp_path / "code"), "--token-file", str(tmp_path / "token"), "--ttl-seconds", "601"], text=True, capture_output=True)
    assert result.returncode != 0
    assert "60–600" in (result.stdout + result.stderr)


def test_library_cloudflare_access_identity_is_host_scoped(tmp_path, monkeypatch):
    data = tmp_path / "data-access"
    pwa = tmp_path / "pwa-access"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    token = tmp_path / "token-access"
    token.write_text("device-token\n", encoding="utf-8")
    token.chmod(0o600)
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_API_TOKEN_FILE", str(token))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "https://social-archive-api.linzezhang.com")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL", "https://social-archive.linzezhang.com")
    import social_archive.api as api
    importlib.reload(api)
    client = TestClient(api.app)
    assertion = "a" * 128
    allowed = client.get("/v1/library", headers={"Host": "social-archive.linzezhang.com", "Cf-Access-Jwt-Assertion": assertion})
    assert allowed.status_code == 200
    denied = client.get("/v1/library", headers={"Host": "social-archive-api.linzezhang.com", "Cf-Access-Jwt-Assertion": assertion})
    assert denied.status_code == 401
    spoofed_forwarded_host = client.get(
        "/v1/library",
        headers={
            "Host": "social-archive-api.linzezhang.com",
            "X-Forwarded-Host": "social-archive.linzezhang.com",
            "Cf-Access-Jwt-Assertion": assertion,
        },
    )
    assert spoofed_forwarded_host.status_code == 401


