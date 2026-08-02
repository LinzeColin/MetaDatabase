from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(root))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(root / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_STAGING_ROOT", str(root / "staging"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT", str(root / "private"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_WATCH_ROOT", str(root / "import"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    import social_archive.api as api

    importlib.reload(api)
    return TestClient(api.app)


def test_library_endpoint_projects_account_mirror_rows_as_table(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    captured = client.post("/v1/captures", json={
        "platform": "generic-web",
        "url": "https://www.wikipedia.org/wiki/Walking_skeleton",
        "external_content_id": "bookmark-1",
        "source_account_id": "chrome-bookmarks",
        "relation_type": "bookmark",
        "relation_observed_at": "2026-08-02T10:00:00Z",
        "title": "Walking Skeleton",
        "text": "账号镜像进入表格资料库",
        "topic": "产品验收",
        "keywords": ["账号同步", "表格"],
        "requested_levels": ["L0", "L1"],
    })
    assert captured.status_code == 202

    table = client.get(
        "/v1/library",
        params={
            "platform": "generic-web",
            "relation": "bookmark",
            "topic": "产品验收",
            "sort_by": "time",
            "sort_dir": "desc",
        },
    )
    assert table.status_code == 200
    body = table.json()
    assert body["total"] == 1
    assert {"platform", "relation_time", "topic", "keywords", "title", "canonical_url"} <= body["items"][0].keys()
    assert body["items"][0]["topic"] == "产品验收"
    assert body["items"][0]["keywords"] == ["账号同步", "表格"]
