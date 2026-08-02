from __future__ import annotations

import httpx

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.connectors.base import ConnectorResult
from social_archive.connectors.oauth import XConnector
from social_archive.models import AccountSyncRequest, CaptureRequest


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
    result = XConnector("owner", lambda: "token").fetch("like", 101, cursor="page-1")
    assert result.status == "partial"
    assert result.scan_receipt["completeness"] == "partial"
    assert result.scan_receipt["next_token"] == "page-2"
    assert result.scan_receipt["cursor_start"] == "page-1"
    assert result.scan_receipt["relation_type"] == "like"
    assert result.observations[0]["relation_type"] == "like"
    assert seen["url"] == "https://api.x.com/2/users/owner/liked_tweets"
    assert seen["params"]["max_results"] == 100
    assert seen["params"]["pagination_token"] == "page-1"


def test_x_rate_limit_is_retryable_unknown_and_preserves_page_token(monkeypatch):
    request = httpx.Request("GET", "https://api.x.com/2/users/owner/bookmarks")
    response = httpx.Response(429, headers={"Retry-After": "12"}, request=request)
    seen: dict[str, object] = {}

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
            return response

    monkeypatch.setattr("social_archive.connectors.oauth.httpx.Client", Client)
    result = XConnector("owner", lambda: "token").fetch("bookmark", 5, cursor="page-2")

    assert result.status == "partial"
    assert result.scan_receipt == {
        "completeness": "unknown",
        "item_count": 0,
        "scope": "account_relation",
        "relation_type": "bookmark",
        "cursor_start": "page-2",
        "failure_code": "X_RATE_LIMITED",
        "retry_after_seconds": 12,
    }
    assert result.errors[0]["code"] == "X_RATE_LIMITED"
    assert result.errors[0]["retryable"] is True
    assert seen["url"] == "https://api.x.com/2/users/owner/bookmarks"
    assert seen["params"]["pagination_token"] == "page-2"


def test_x_account_sync_follows_next_token_for_bookmarks_and_likes(settings, store, service):
    account_id = store.upsert_source_account(
        platform="x",
        external_account_id="owner",
        display_name="owner",
        auth_method="oauth",
        auth_handle_ref="conn_x_fixture",
        connection_state="connected",
    )
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(
        account_id,
        AccountSyncRequest(mode="first_full", relation_types=["bookmark", "like"], trigger_type="first_connect"),
    )
    calls: list[tuple[str, str | None]] = []

    def item(external_id: str, relation: str) -> CaptureRequest:
        return CaptureRequest(
            platform="x",
            url=f"https://x.com/i/web/status/{external_id}",
            external_content_id=external_id,
            relation_type=relation,
            title=external_id,
        )

    class FixtureRegistry:
        def run(self, connector_id, request):
            assert connector_id == "x"
            calls.append((request.relation_type, request.cursor))
            if (request.relation_type, request.cursor) == ("bookmark", None):
                return (
                    ConnectorResult(
                        "x",
                        "bookmark-page-1",
                        "partial",
                        scan_receipt={
                            "completeness": "partial",
                            "item_count": 1,
                            "next_token": "bookmark-page-2",
                            "scope": "account_relation",
                            "relation_type": "bookmark",
                        },
                    ),
                    [item("bookmark-1", "bookmark")],
                )
            if (request.relation_type, request.cursor) == ("bookmark", "bookmark-page-2"):
                return (
                    ConnectorResult(
                        "x",
                        "bookmark-page-2",
                        "success",
                        scan_receipt={
                            "completeness": "complete",
                            "item_count": 1,
                            "scope": "account_relation",
                            "relation_type": "bookmark",
                        },
                    ),
                    [item("bookmark-2", "bookmark")],
                )
            if (request.relation_type, request.cursor) == ("like", None):
                return (
                    ConnectorResult(
                        "x",
                        "like-page-1",
                        "success",
                        scan_receipt={
                            "completeness": "complete",
                            "item_count": 1,
                            "scope": "account_relation",
                            "relation_type": "like",
                        },
                    ),
                    [item("like-1", "like")],
                )
            raise AssertionError(f"unexpected request: {request.relation_type}, {request.cursor}")

    coordinator.registry = FixtureRegistry()
    coordinator.process_job({"sync_run_id": started["sync_run_id"], "account_id": account_id})

    assert calls == [("bookmark", None), ("bookmark", "bookmark-page-2"), ("like", None)]
    assert store.get_sync_run(started["sync_run_id"])["status"] == "completed"
    assert store.list_library_table(platform="x")["total"] == 3
    bookmark_checkpoint = store.get_sync_checkpoint(
        source_account_id=account_id,
        relation_type="bookmark",
        collection_key="",
    )
    assert bookmark_checkpoint["cursor"] == {}


def test_x_checkpoint_resume_requires_fresh_full_before_relation_closure(settings, store, service):
    account_id = store.upsert_source_account(
        platform="x",
        external_account_id="owner",
        display_name="owner",
        auth_method="oauth",
        auth_handle_ref="conn_x_fixture",
        connection_state="connected",
    )
    existing = service.capture(
        CaptureRequest(
            platform="x",
            url="https://x.com/i/web/status/earlier-page",
            external_content_id="earlier-page",
            relation_type="bookmark",
            source_account_id="owner",
            title="earlier-page",
        )
    )
    store.upsert_sync_checkpoint(
        source_account_id=account_id,
        relation_type="bookmark",
        collection_key="",
        cursor={"next_token": "resume-page"},
        known_anchor="earlier-page",
        last_complete_sync_run_id=None,
        complete=False,
    )
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(account_id, AccountSyncRequest(mode="incremental", relation_types=["bookmark"]))

    class FinalPageRegistry:
        def run(self, connector_id, request):
            assert connector_id == "x"
            assert request.relation_type == "bookmark"
            assert request.cursor == "resume-page"
            return (
                ConnectorResult(
                    "x",
                    "bookmark-final-page",
                    "success",
                    scan_receipt={
                        "completeness": "complete",
                        "item_count": 1,
                        "scope": "account_relation",
                        "relation_type": "bookmark",
                    },
                ),
                [
                    CaptureRequest(
                        platform="x",
                        url="https://x.com/i/web/status/final-page",
                        external_content_id="final-page",
                        relation_type="bookmark",
                        title="final-page",
                    )
                ],
            )

    coordinator.registry = FinalPageRegistry()
    coordinator.process_job({"sync_run_id": started["sync_run_id"], "account_id": account_id})

    run = store.get_sync_run(started["sync_run_id"])
    assert run["status"] == "partial"
    assert run["last_error_code"] == "X_FRESH_FULL_SCAN_REQUIRED"
    checkpoint = store.get_sync_checkpoint(
        source_account_id=account_id,
        relation_type="bookmark",
        collection_key="",
    )
    assert checkpoint["cursor"] == {}
    relation = store.get_content(existing.content_id)["relations"][0]
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 0
