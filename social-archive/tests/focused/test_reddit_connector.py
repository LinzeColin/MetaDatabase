from __future__ import annotations

import importlib

import httpx

from social_archive.connectors.base import ConnectorResult
from social_archive.connectors.oauth import RedditConnector
from social_archive.models import CaptureRequest, ConnectorRunRequest


def test_reddit_saved_normalizes_complete_scan(monkeypatch):
    seen: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"children": [{"kind": "t3", "data": {"id": "r1", "permalink": "/r/a/r1", "title": "A"}}], "after": None}}

    class Client:
        def __init__(self, *args, **kwargs):
            seen["headers"] = kwargs["headers"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            seen["url"] = url
            seen["params"] = kwargs["params"]
            return Response()

    monkeypatch.setattr("social_archive.connectors.oauth.httpx.Client", Client)
    result = RedditConnector("owner", "sa-test/1", lambda: "token").fetch("saved", 5)
    assert result.status == "success"
    assert result.scan_receipt["completeness"] == "complete"
    assert result.scan_receipt["relation_type"] == "saved"
    assert result.observations[0]["relation_type"] == "saved"
    assert seen["url"] == "https://oauth.reddit.com/user/owner/saved"
    assert seen["params"] == {"limit": 5, "raw_json": 1}
    assert seen["headers"] == {"Authorization": "Bearer token", "User-Agent": "sa-test/1"}


def test_reddit_upvoted_partial_scan_preserves_cursor_and_relation(monkeypatch):
    seen: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"children": [{"kind": "t3", "data": {"id": "u1", "permalink": "/r/a/u1", "title": "U"}}], "after": "t3_next"}}

    class Client:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            seen["url"] = url
            seen["params"] = kwargs["params"]
            return Response()

    monkeypatch.setattr("social_archive.connectors.oauth.httpx.Client", Client)
    result = RedditConnector("owner", "sa-test/1", lambda: "token").fetch("upvoted", 3)
    assert result.status == "partial"
    assert result.scan_receipt["completeness"] == "partial"
    assert result.scan_receipt["next_cursor"] == "t3_next"
    assert result.scan_receipt["relation_type"] == "upvoted"
    assert result.observations[0]["relation_type"] == "upvoted"
    assert seen["url"] == "https://oauth.reddit.com/user/owner/upvoted"
    assert seen["params"] == {"limit": 3, "raw_json": 1}


def test_partial_reddit_api_run_does_not_close_existing_relation(monkeypatch, tmp_path):
    root = tmp_path / "data"
    pwa_root = tmp_path / "pwa"
    pwa_root.mkdir()
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite3",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private-database",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa_root,
    }.items():
        monkeypatch.setenv(key, str(value))

    import social_archive.api as api

    api = importlib.reload(api)
    captured = api.service.capture(
        CaptureRequest(
            platform="reddit",
            url="https://www.reddit.com/r/example/comments/1/item/",
            relation_type="saved",
            source_account_id="owner",
            requested_levels=["L0", "L1"],
        )
    )

    class PartialRegistry:
        def run(self, connector_id, request):
            assert connector_id == "reddit"
            assert request.relation_type == "saved"
            return (
                ConnectorResult(
                    "reddit",
                    "partial-run",
                    "partial",
                    scan_receipt={
                        "completeness": "partial",
                        "item_count": 0,
                        "next_cursor": "t3_next",
                        "scope": "account_relation",
                        "relation_type": "saved",
                        "source_account_id": "owner",
                    },
                ),
                [],
            )

    monkeypatch.setattr(api, "registry", PartialRegistry())
    result = api.run_connector("reddit", ConnectorRunRequest(relation_type="saved", source_account_id="owner"))
    relation = api.store.get_content(captured.content_id)["relations"][0]
    assert result["status"] == "partial"
    assert result["scan_receipt"]["next_cursor"] == "t3_next"
    assert result["advanced_missing_relation_count"] == 0
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 0
