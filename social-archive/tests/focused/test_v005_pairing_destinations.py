from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch, *, pairing: bool = False) -> tuple[TestClient, object]:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    env = {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_EXPORT_ROOT": root / "exports",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
        "SOCIAL_ARCHIVE_PAIRING_REQUIRED": "true" if pairing else "false",
    }
    if pairing:
        token = root / "token"
        code = root / "code"
        root.mkdir(parents=True, exist_ok=True)
        token.write_text("secret-token", encoding="utf-8")
        code.write_text(json.dumps({
            "code": "ABCD-EFGH-JKLM",
            "expires_at_epoch": time.time() + 600,
            "attempts_remaining": 5,
        }), encoding="utf-8")
        token.chmod(0o600)
        code.chmod(0o600)
        env["SOCIAL_ARCHIVE_API_TOKEN_FILE"] = token
        env["SOCIAL_ARCHIVE_PAIRING_CODE_FILE"] = code
        env["SOCIAL_ARCHIVE_PUBLIC_BASE_URL"] = "https://social-archive-api.linzezhang.com"
        env["SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL"] = "https://social-archive.linzezhang.com"
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app), api


def test_pairing_status_and_exchange_match_extension_contract(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch, pairing=True)
    api_headers = {"Host": "social-archive-api.linzezhang.com"}
    status = client.get("/v1/pairing/status", headers=api_headers)
    assert status.status_code == 200
    assert status.json()["pairing_required"] is True
    assert status.json()["service_ready"] is True
    bad = client.post(
        "/v1/pairing/exchange",
        json={"code": "0000-0000-0000", "device_name": "Chrome"},
        headers=api_headers,
    )
    assert bad.status_code == 401
    good = client.post(
        "/v1/pairing/exchange",
        json={"code": "ABCD-EFGH-JKLM", "device_name": "Chrome"},
        headers=api_headers,
    )
    assert good.status_code == 200
    assert good.json()["token"] == "secret-token"
    bootstrap = client.get(
        "/v1/extension/bootstrap",
        headers={**api_headers, "Authorization": "Bearer secret-token"},
    )
    assert bootstrap.status_code == 200


def test_markdown_probe_and_destination_receipt_api(tmp_path, monkeypatch):
    client, api_module = _client(tmp_path, monkeypatch)
    probe = client.post("/v1/destinations/markdown/probe")
    assert probe.status_code == 200
    assert probe.json()["state"] == "connected"
    capture = client.post("/v1/captures", json={
        "platform": "generic-web",
        "url": "https://example.com/receipt-fixture",
        "title": "回执夹具",
        "requested_levels": ["L0", "L1"],
        "destination_ids": ["social_archive"],
    })
    assert capture.status_code == 202
    api_module.store.record_destination_receipt(
        destination_id="markdown",
        status="done",
        content_id=capture.json()["content_id"],
        projection_sha256="0" * 64,
        attempted_at="2026-08-02T00:00:00Z",
        message_zh="导出完成",
    )
    receipts = client.get("/v1/destinations/receipts")
    assert receipts.status_code == 200
    assert receipts.json()["items"][0]["destination_id"] == "markdown"
