from __future__ import annotations

import importlib
from pathlib import Path
from fastapi.testclient import TestClient


def test_save_refresh_search_markdown_and_retry_survive_restart(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    pwa = Path(__file__).resolve().parents[2] / "apps" / "pwa"
    env = {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "runtime.sqlite3",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private-db",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_EXPORT_ROOT": root / "exports",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
        "SOCIAL_ARCHIVE_PAIRING_REQUIRED": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    client = TestClient(api.app)
    probe = client.post("/v1/destinations/markdown/probe")
    assert probe.status_code == 200
    assert probe.json()["authorized"] is True
    capture = client.post("/v1/captures", json={
        "platform": "generic-web",
        "url": "https://www.wikipedia.org/wiki/Archiving",
        "title": "值得保留的文章",
        "text": "这段正文必须可搜索并进入 Markdown。",
        "relation_type": "saved",
        "requested_levels": ["L0", "L1"],
        "destination_ids": ["social_archive", "markdown"],
    })
    assert capture.status_code == 202
    content_id = capture.json()["content_id"]
    assert client.get("/v1/library?q=正文").json()["items"][0]["id"] == content_id
    markdown = client.get(f"/v1/library/{content_id}/markdown").text
    assert "这段正文必须可搜索并进入 Markdown" in markdown
    # Recreate the application against the same SQLite path to prove persistence across process restart.
    importlib.reload(api)
    restarted = TestClient(api.app)
    assert restarted.get(f"/v1/library/{content_id}").status_code == 200
    job = next(item for item in restarted.get("/v1/jobs").json()["items"] if item["job_type"] == "export_destination")
    api.store.finish_job(job["id"], success=False, error_code="FIXTURE", error_message="可重试")
    assert restarted.post(f"/v1/jobs/{job['id']}/retry").json()["status"] == "queued"
