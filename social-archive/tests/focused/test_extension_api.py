from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    (pwa / "extension-install.html").write_text("六步安装 Social Archive", encoding="utf-8")
    extension_package = tmp_path / "social-archive-extension.zip"
    extension_package.write_bytes(b"PK\x03\x04fixture-extension")
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(root / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(root / "staging"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(root / "private"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_WATCH_ROOT", str(root / "import"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    monkeypatch.setenv("SOCIAL_ARCHIVE_EXTENSION_PACKAGE", str(extension_package))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app)


def test_extension_install_guide_and_package_are_real_downloads(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    guide = client.get("/extension-install")
    assert guide.status_code == 200
    assert "六步安装 Social Archive" in guide.text

    package = client.get("/downloads/social-archive-extension.zip")
    assert package.status_code == 200
    assert package.content == b"PK\x03\x04fixture-extension"
    assert package.headers["content-type"] == "application/zip"
    assert "social-archive-extension-v0.0.0.6.zip" in package.headers["content-disposition"]
    assert len(package.headers["x-social-archive-sha256"]) == 64


def test_extension_bootstrap_is_single_render_payload(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/v1/extension/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "Social Archive"
    assert body["version"] == "0.0.0.6"
    assert body["archive_defaults"] == ["L0", "L1", "L3"]
    # 这条断言原先逐字钉着 {"cookie_custody": False, "password_custody": False,
    # "user_triggered_capture_only": True}。**其中第一条从 T05/T06 起就是假的**
    # ——产品确实在托管西方三源的登录状态（加密后落库）。
    # 也就是说：一句错的事实，由一盏绿灯守着。
    #
    # 现在这三项全部由 store.privacy_facts() 与托管清单算出来，判据也跟着
    # 改成断言"算出来的东西对不对"，而不是"字面量有没有被改动"。
    privacy = body["privacy"]
    assert privacy["cookie_custody"] is True, "产品在托管西方三源的登录状态，不能对外说没有"
    assert set(privacy["cookie_custody_platforms"]) == {"x", "instagram", "youtube"}
    assert set(privacy["cookie_never_leaves_browser_platforms"]) == {
        "xiaohongshu", "douyin", "bilibili", "kuaishou"
    }
    assert privacy["password_custody"] is False
    assert privacy["password_shaped_columns"] == [], (
        "库里出现了 password 形状的列——这不是文案问题，是 L0 边界被越过了"
    )
    assert privacy["auto_sync_accounts"] == 0, "全新库里不该有开着定时同步的账号"
    assert {"connectors", "destinations", "jobs", "storage", "summary"} <= body.keys()
    assert all({"last_checked_at", "latency_ms", "last_message_zh"} <= item.keys() for item in body["connectors"])
    assert all({"last_checked_at", "latency_ms", "last_message_zh"} <= item.keys() for item in body["destinations"])


def test_batch_capture_and_retry_flow(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    probe = client.post("/v1/destinations/markdown/probe")
    assert probe.status_code == 200
    assert probe.json()["authorized"] is True
    payload = {
        "items": [
            {
                "platform": "generic_web",
                "url": "https://www.wikipedia.org/wiki/Archive",
                "title": "归档",
                "requested_levels": ["L0", "L1"],
                "destination_ids": ["social_archive", "markdown"],
            },
            {
                "platform": "generic_web",
                "url": "https://www.wikipedia.org/wiki/Bookmark",
                "title": "书签",
                "requested_levels": ["L0", "L1"],
            },
        ]
    }
    response = client.post("/v1/captures/batch", json=payload)
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] == 2 and body["failed"] == 0
    jobs = client.get("/v1/jobs").json()["items"]
    export_job = next(job for job in jobs if job["job_type"] == "export_destination")
    # A queued job cannot be retried; force a failed export with its receipt to exercise the user action.
    import social_archive.api as api
    api.store.finish_job(export_job["id"], success=False, error_code="TEST", error_message="fixture")
    receipt_id = api.store.record_destination_receipt(
        destination_id="markdown",
        content_id=body["items"][0]["content_id"],
        status="failed",
        projection_sha256="0" * 64,
        attempted_at="2026-07-31T00:00:00Z",
        message_zh="fixture destination failure",
        job_id=export_job["id"],
        error_code="TEST",
    )
    bootstrap = client.get("/v1/extension/bootstrap").json()
    assert bootstrap["summary"]["failed_exports"] == 1
    assert [item["id"] for item in bootstrap["destination_receipts"]] == [receipt_id]
    receipt_retry = client.post(f"/v1/destinations/receipts/{receipt_id}/retry")
    assert receipt_retry.status_code == 202
    assert receipt_retry.json()["job_id"] == export_job["id"]
    assert receipt_retry.json()["status"] == "queued"
    retry = client.post(f"/v1/jobs/{export_job['id']}/retry")
    assert retry.status_code == 409


def test_manual_export_waits_for_active_destination_probe(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    captured = client.post("/v1/captures", json={
        "platform": "generic_web",
        "url": "https://www.wikipedia.org/wiki/Manual_export",
        "title": "手动导出阶段门",
        "requested_levels": ["L0", "L1"],
    })
    assert captured.status_code == 202
    content_id = captured.json()["content_id"]

    blocked = client.post(f"/v1/library/{content_id}/export", json={"destination_ids": ["markdown"]})
    assert blocked.status_code == 202
    assert blocked.json()["destination_ids"] == []
    assert blocked.json()["skipped_destination_ids"] == ["markdown"]
    assert blocked.json()["job_ids"] == []

    assert client.post("/v1/destinations/markdown/probe").json()["authorized"] is True
    queued = client.post(f"/v1/library/{content_id}/export", json={"destination_ids": ["markdown"]})
    assert queued.status_code == 202
    assert queued.json()["destination_ids"] == ["markdown"]
    assert queued.json()["skipped_destination_ids"] == []
    assert len(queued.json()["job_ids"]) == 1


def test_local_obsidian_bridge_receipts_are_safe_and_separate_from_server_obsidian(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    captured = client.post("/v1/captures", json={
        "platform": "generic_web",
        "url": "https://www.wikipedia.org/wiki/Obsidian_bridge",
        "title": "本机 Obsidian 回执",
        "text": "桥接正文",
        "requested_levels": ["L0", "L1"],
    })
    assert captured.status_code == 202
    content_id = captured.json()["content_id"]

    done = client.post("/v1/destinations/obsidian-local/receipts", json={
        "content_id": content_id,
        "status": "done",
        "remote_path": "Social Archive/generic_web/本机-bridge.md",
    })
    assert done.status_code == 202
    assert done.json()["destination_id"] == "obsidian_local"

    import social_archive.api as api
    detail = api.store.get_content(content_id)
    assert detail is not None
    binding = next(item for item in detail["destination_bindings"] if item["destination_id"] == "obsidian_local")
    assert binding["remote_path"] == "Social Archive/generic_web/本机-bridge.md"
    assert binding["metadata"] == {"attested": True, "mode": "chrome_loopback"}

    failed = client.post("/v1/destinations/obsidian-local/receipts", json={
        "content_id": content_id,
        "status": "failed",
        "remote_path": "Social Archive/generic_web/本机-bridge.md",
    })
    assert failed.status_code == 202
    receipt = api.store.get_destination_receipt(failed.json()["receipt_id"])
    assert receipt and receipt["status"] == "failed"
    assert receipt["evidence"] == {"attested": True, "bridge": "chrome_loopback", "retryable": True}
    assert receipt["error_code"] == "OBSIDIAN_LOCAL_BRIDGE_FAILED"

    rejected = client.post("/v1/destinations/obsidian-local/receipts", json={
        "content_id": content_id,
        "status": "done",
        "remote_path": "../../outside.md",
    })
    assert rejected.status_code == 422
    after = api.store.get_content(content_id)
    assert after is not None
    assert {key: after[key] for key in ("id", "canonical_url", "title", "metadata_json")} == {
        key: detail[key] for key in ("id", "canonical_url", "title", "metadata_json")
    }
