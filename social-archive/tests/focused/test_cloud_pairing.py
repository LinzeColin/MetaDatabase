from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_one_time_pairing_code_is_consumed(tmp_path, monkeypatch):
    data = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    token = tmp_path / "api-token"
    code = tmp_path / "pairing-code"
    token.write_text("device-token\n", encoding="utf-8")
    code.write_text(json.dumps({"code": "ABCD-EFGH-JKLM", "expires_at_epoch": int(time.time()) + 600, "attempts_remaining": 5}) + "\n", encoding="utf-8")
    token.chmod(0o600)
    code.chmod(0o600)
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_API_TOKEN_FILE", str(token))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_CODE_FILE", str(code))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "https://social-archive-api.linzezhang.com")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL", "https://social-archive.linzezhang.com")
    import social_archive.api as api
    importlib.reload(api)
    client = TestClient(api.app)
    api_headers = {"Host": "social-archive-api.linzezhang.com"}

    status = client.get("/v1/pairing/status", headers=api_headers).json()
    assert status["service_ready"] is True and status["one_time_code_available"] is True
    paired = client.post("/v1/pairing/exchange", headers=api_headers, json={"code": "abcd efgh jklm", "device_name": "Chrome"})
    assert paired.status_code == 200
    assert paired.json()["token"] == "device-token"
    assert paired.json()["endpoint"] == "https://social-archive-api.linzezhang.com"
    assert paired.json()["library_url"] == "https://social-archive.linzezhang.com"
    assert code.exists(), "the source pairing Secret is read-only to Core"
    assert client.get("/v1/pairing/status", headers=api_headers).json()["one_time_code_available"] is False
    assert client.post("/v1/pairing/exchange", headers=api_headers, json={"code": "ABCD-EFGH-JKLM"}).status_code == 409
    bootstrap = client.get("/v1/extension/bootstrap", headers={"Authorization": "Bearer device-token"})
    assert bootstrap.status_code == 200
    assert bootstrap.json()["pairing"]["mode"] == "cloud_first"


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


def test_pairing_rotation_keeps_the_inode_a_bind_mount_follows(tmp_path):
    # Compose publishes every secret as an individual file bind mount, so the
    # running Core follows the inode.  Rotating by rename left production
    # serving the pre-rotation record forever, which presented as a refreshed
    # code that never became available.
    import importlib.util

    script = Path(__file__).parents[2] / "scripts/generate_pairing_code.py"
    spec = importlib.util.spec_from_file_location("pairing_generator_inode", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    secret = tmp_path / "pairing-code"
    secret.write_text("previous-and-much-longer-than-the-replacement\n", encoding="utf-8")
    secret.chmod(0o640)
    before = secret.stat().st_ino

    module.atomic_secret(secret, "replacement")

    assert secret.stat().st_ino == before, "rotation must not swap the inode a bind mount follows"
    assert secret.read_text(encoding="utf-8") == "replacement\n", "stale bytes must be truncated"
    assert secret.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".*tmp")), "in-place rotation must not leave a temporary secret behind"


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


def test_pairing_edge_is_api_host_only_size_bounded_and_rate_limited(tmp_path, monkeypatch):
    data = tmp_path / "data-edge"
    pwa = tmp_path / "pwa-edge"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    token = tmp_path / "token-edge"
    code = tmp_path / "code-edge"
    token.write_text("device-token\n", encoding="utf-8")
    code.write_text(json.dumps({"code": "ABCD-EFGH-JKLM", "expires_at_epoch": int(time.time()) + 600, "attempts_remaining": 5}) + "\n", encoding="utf-8")
    token.chmod(0o600)
    code.chmod(0o600)
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": data,
        "SOCIAL_ARCHIVE_RUNTIME_DB": data / "db.sqlite",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
        "SOCIAL_ARCHIVE_PAIRING_REQUIRED": "true",
        "SOCIAL_ARCHIVE_API_TOKEN_FILE": token,
        "SOCIAL_ARCHIVE_PAIRING_CODE_FILE": code,
        "SOCIAL_ARCHIVE_PUBLIC_BASE_URL": "https://social-archive-api.linzezhang.com",
        "SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL": "https://social-archive.linzezhang.com",
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    api = importlib.reload(api)
    client = TestClient(api.app)
    api_headers = {"Host": "social-archive-api.linzezhang.com", "Cf-Connecting-Ip": "192.0.2.50"}
    library_headers = {"Host": "social-archive.linzezhang.com"}

    assert client.get("/v1/pairing/status", headers=api_headers).status_code == 200
    assert client.get("/v1/pairing/status", headers=library_headers).status_code == 404
    assert client.get("/v1/extension/bootstrap", headers=api_headers).status_code == 401
    assert client.get(
        "/v1/extension/bootstrap",
        headers={**api_headers, "Cf-Access-Jwt-Assertion": "x" * 128},
    ).status_code == 401

    oversized = client.post(
        "/v1/pairing/exchange",
        headers={**api_headers, "Content-Type": "application/json"},
        content=b"x" * (16 * 1024 + 1),
    )
    assert oversized.status_code == 413

    api.pairing_rate_limiter = api.PairingRateLimiter(max_requests=2)
    assert client.post("/v1/pairing/exchange", headers=api_headers, json={"code": "WRONGX"}).status_code == 401
    assert client.post("/v1/pairing/exchange", headers=api_headers, json={"code": "WRONGX"}).status_code == 401
    assert client.post("/v1/pairing/exchange", headers=api_headers, json={"code": "WRONGX"}).status_code == 429


def _issue_client(tmp_path, monkeypatch, *, token="device-token"):
    data = tmp_path / "issue-data"
    pwa = tmp_path / "issue-pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    token_file = tmp_path / "issue-token"
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_API_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("SOCIAL_ARCHIVE_TRUST_CLOUDFLARE_ACCESS", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "https://social-archive-api.linzezhang.com")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL", "https://social-archive.linzezhang.com")
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app)


def test_library_page_can_issue_device_config_without_a_one_time_code(tmp_path, monkeypatch):
    # Typing a one-time code was the zero-barrier failure: it lives ten minutes,
    # so the Owner raced a clock to copy a string by hand.
    client = _issue_client(tmp_path, monkeypatch)
    response = client.post(
        "/v1/pairing/issue",
        headers={"host": "social-archive.linzezhang.com", "cf-access-jwt-assertion": "a" * 80},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token"] == "device-token"
    assert payload["endpoint"] == "https://social-archive-api.linzezhang.com"


def test_issue_refuses_a_bearer_token_and_the_api_hostname(tmp_path, monkeypatch):
    # The route must be reachable only from the Access-authenticated library
    # page, never by anything holding just a Bearer token.
    client = _issue_client(tmp_path, monkeypatch)
    assert client.post("/v1/pairing/issue").status_code == 403
    assert client.post(
        "/v1/pairing/issue", headers={"Authorization": "Bearer device-token"}
    ).status_code == 403
    assert client.post(
        "/v1/pairing/issue",
        headers={"host": "social-archive-api.linzezhang.com", "cf-access-jwt-assertion": "a" * 80},
    ).status_code == 403
    assert client.post(
        "/v1/pairing/issue",
        headers={"host": "social-archive.linzezhang.com", "cf-access-jwt-assertion": "short"},
    ).status_code == 403
