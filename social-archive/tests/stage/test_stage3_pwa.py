from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
PWA_ROOT = ROOT / "apps" / "pwa"
LIBRARY_HOST = "social-archive.linzezhang.com"
API_HOST = "social-archive-api.linzezhang.com"
LIBRARY_HEADERS = {
    "host": LIBRARY_HOST,
    "cf-access-jwt-assertion": "stage3-fixture-" + "x" * 96,
}


def _stage3_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, str]:
    data_root = tmp_path / "data"
    token_file = tmp_path / "api-token"
    pairing_file = tmp_path / "pairing.json"
    token = "stage3-fixture-device-token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    pairing_file.write_text(
        json.dumps(
            {
                "code": "ABCD-EFGH-JKLM",
                "expires_at_epoch": time.time() + 300,
                "attempts_remaining": 5,
            }
        ),
        encoding="utf-8",
    )
    pairing_file.chmod(0o600)
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": data_root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": data_root / "runtime.sqlite3",
        "SOCIAL_ARCHIVE_STAGING_ROOT": data_root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": data_root / "private-database",
        "SOCIAL_ARCHIVE_WATCH_ROOT": data_root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": PWA_ROOT,
        "SOCIAL_ARCHIVE_API_TOKEN_FILE": token_file,
        "SOCIAL_ARCHIVE_PAIRING_CODE_FILE": pairing_file,
        "SOCIAL_ARCHIVE_PAIRING_REQUIRED": "true",
        "SOCIAL_ARCHIVE_PUBLIC_BASE_URL": f"https://{API_HOST}",
        "SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL": f"https://{LIBRARY_HOST}",
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api

    api = importlib.reload(api)
    return TestClient(api.app), api, token


def test_pwa_shell_is_self_contained_and_mobile_ready():
    assert all((PWA_ROOT / name).exists() for name in ("index.html", "styles.css", "app.js", "sw.js", "manifest.webmanifest"))
    html = (PWA_ROOT / "index.html").read_text(encoding="utf-8")
    app = (PWA_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (PWA_ROOT / "styles.css").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    # The Owner-approved table shell replaced the v0.0.0.5 three-step onboarding
    # copy and its modal detail dialog with a persistent detail drawer, and it
    # dropped the .library.feed/.library.grid views at the 900/600px
    # breakpoints.  Bind what the current shell actually ships.
    assert 'id="detailDrawer"' in html
    assert all(token in app for token in ("/v1/library?", "openDetail", "next_action_zh"))
    assert all(token in styles for token in ("@media (max-width: 1180px)", "@media (max-width: 760px)"))


def test_cloudflare_access_allows_library_not_independent_extension_api(tmp_path, monkeypatch):
    client, _, token = _stage3_client(tmp_path, monkeypatch)

    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200
    assert client.get("/v1/library").status_code == 401
    assert client.get("/v1/library", headers=LIBRARY_HEADERS).status_code == 200

    api_domain_headers = {**LIBRARY_HEADERS, "host": API_HOST}
    assert client.get("/v1/library", headers=api_domain_headers).status_code == 401
    assert client.get("/v1/extension/bootstrap", headers=api_domain_headers).status_code == 401
    assert client.get("/v1/extension/bootstrap", headers={"authorization": f"Bearer {token}"}).status_code == 200


def test_stage3_first_setup_save_find_failure_and_retry(tmp_path, monkeypatch):
    client, api, _ = _stage3_client(tmp_path, monkeypatch)

    api_headers = {"host": API_HOST}
    status = client.get("/v1/pairing/status", headers=api_headers)
    assert status.status_code == 200
    assert status.json()["one_time_code_available"] is True
    paired = client.post("/v1/pairing/exchange", headers=api_headers, json={"code": "ABCD-EFGH-JKLM", "device_name": "Stage 3 fixture"})
    assert paired.status_code == 200
    assert paired.json()["library_url"] == f"https://{LIBRARY_HOST}"
    assert paired.json()["endpoint"] == f"https://{API_HOST}"
    assert client.get("/v1/pairing/status", headers=api_headers).json()["one_time_code_available"] is False

    markdown_probe = client.post("/v1/destinations/markdown/probe", headers=LIBRARY_HEADERS)
    assert markdown_probe.status_code == 200
    assert markdown_probe.json()["authorized"] is True

    saved = client.post(
        "/v1/captures",
        headers=LIBRARY_HEADERS,
        json={
            "platform": "generic-web",
            "url": "https://example.test/stage3-acceptance",
            "title": "Stage 3 可检索内容",
            "text": "首次配置后的一次保存和查找夹具",
            "requested_levels": ["L0", "L1"],
            "destination_ids": ["social_archive", "markdown"],
        },
    )
    assert saved.status_code == 202
    content_id = saved.json()["content_id"]
    found = client.get("/v1/library?q=可检索", headers=LIBRARY_HEADERS)
    assert found.status_code == 200
    assert [item["id"] for item in found.json()["items"]] == [content_id]
    assert client.get(f"/v1/library/{content_id}", headers=LIBRARY_HEADERS).status_code == 200

    jobs = client.get("/v1/jobs", headers=LIBRARY_HEADERS).json()["items"]
    export_job = next(job for job in jobs if job["job_type"] == "export_destination" and job["connector_id"] == "markdown")
    api.store.finish_job(export_job["id"], success=False, error_code="STAGE3_FIXTURE", error_message="fixture")
    receipt_id = api.store.record_destination_receipt(
        destination_id="markdown",
        content_id=content_id,
        status="failed",
        projection_sha256="0" * 64,
        attempted_at="2026-07-30T00:00:00Z",
        message_zh="本地 Markdown 投影失败，请检查配置后重试。",
        job_id=export_job["id"],
        error_code="STAGE3_FIXTURE",
    )
    failed = client.get("/v1/destinations/receipts", headers=LIBRARY_HEADERS).json()["items"]
    assert [(item["id"], item["status"], item["message_zh"]) for item in failed] == [
        (receipt_id, "failed", "本地 Markdown 投影失败，请检查配置后重试。")
    ]
    retried = client.post(f"/v1/destinations/receipts/{receipt_id}/retry", headers=LIBRARY_HEADERS)
    assert retried.status_code == 202
    assert retried.json()["job_id"] == export_job["id"]
    assert retried.json()["status"] == "queued"
    assert "重新加入目的地导出队列" in retried.json()["message_zh"]

    connector_actions = client.get("/v1/connectors", headers=LIBRARY_HEADERS).json()["items"]
    assert connector_actions
    assert all(item["next_action_zh"].strip() and "\n" not in item["next_action_zh"] for item in connector_actions)
