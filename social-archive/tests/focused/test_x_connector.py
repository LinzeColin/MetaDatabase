from __future__ import annotations

import httpx

from social_archive.connectors.oauth import XConnector


def test_x_bookmark_normalizes_complete_scan(monkeypatch):
    seen: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "bookmark-1", "text": "hello"}], "meta": {}}

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
    result = XConnector("owner", lambda: "token").fetch("bookmark", 5)
    assert result.status == "success"
    assert result.scan_receipt["completeness"] == "complete"
    assert result.scan_receipt["relation_type"] == "bookmark"
    assert result.observations[0]["relation_type"] == "bookmark"
    assert seen["url"] == "https://api.x.com/2/users/owner/bookmarks"
    assert seen["params"]["max_results"] == 5
    assert seen["headers"] == {"Authorization": "Bearer token"}


def test_x_like_normalizes_partial_scan_and_next_token(monkeypatch):
    seen: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "like-1", "text": "liked"}], "meta": {"next_token": "page-2"}}

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
    result = XConnector("owner", lambda: "token").fetch("like", 101)
    assert result.status == "partial"
    assert result.scan_receipt["completeness"] == "partial"
    assert result.scan_receipt["next_token"] == "page-2"
    assert result.scan_receipt["relation_type"] == "like"
    assert result.observations[0]["relation_type"] == "like"
    assert seen["url"] == "https://api.x.com/2/users/owner/liked_tweets"
    assert seen["params"]["max_results"] == 100
