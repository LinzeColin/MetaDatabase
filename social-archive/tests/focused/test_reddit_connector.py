from __future__ import annotations

import importlib

import httpx
import pytest

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.connectors.base import ConnectorResult
from social_archive.connectors.oauth import RedditConnector
from social_archive.models import AccountSyncRequest, CaptureRequest, ConnectorRunRequest


@pytest.fixture()
def server_owned_reddit(monkeypatch):
    """让 Reddit 这个账号**由服务端连接器驱动同步**（v0.0.0.22）。

    下面四条验的是「服务端连接器驱动一次账号同步」这台机器：翻页、断点续、
    **限流永远不许关掉一个关系**、缺授权要报 blocked_environment。
    这台机器还活着——今天 x 走的就是它。

    变的只是**谁走这条路**：v0.0.0.22 起 Reddit 的生产路线改成扩展按形状读页面
    （服务端那条 2026-08-04 打生产量出来是 REDDIT_AUTH_MISSING，一直不通），
    所以它从 SERVER_ACCOUNT_CONNECTORS 里挪走了。

    这里仍然拿 Reddit 的连接器来驱动，是因为**它是有真实翻页语义的那一个**
    （after 游标、限流、关系闭合）。换成别的连接器，这四条就退化成走过场。
    """
    from social_archive import account_sync as module
    monkeypatch.setattr(module, "SERVER_ACCOUNT_CONNECTORS",
                        set(module.SERVER_ACCOUNT_CONNECTORS) | {"reddit"})


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


def test_reddit_rate_limit_is_retryable_unknown_and_preserves_page_cursor(monkeypatch):
    request = httpx.Request("GET", "https://oauth.reddit.com/user/owner/saved")
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
    result = RedditConnector("owner", "sa-test/1", lambda: "token").fetch("saved", 5, cursor="t3_resume")

    assert result.status == "partial"
    assert result.scan_receipt == {
        "completeness": "unknown",
        "item_count": 0,
        "scope": "account_relation",
        "relation_type": "saved",
        "cursor_start": "t3_resume",
        "failure_code": "REDDIT_RATE_LIMITED",
        "retry_after_seconds": 12,
    }
    assert result.errors[0]["code"] == "REDDIT_RATE_LIMITED"
    assert result.errors[0]["retryable"] is True
    assert seen["url"] == "https://oauth.reddit.com/user/owner/saved"
    assert seen["params"] == {"limit": 5, "raw_json": 1, "after": "t3_resume"}


def test_reddit_account_sync_follows_pages_and_closes_only_after_full_relation(settings, store, service, server_owned_reddit):
    account_id = store.upsert_source_account(
        platform="reddit",
        external_account_id="owner",
        display_name="owner",
        auth_method="oauth",
        auth_handle_ref="conn_reddit_fixture",
        connection_state="connected",
    )
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(
        account_id,
        AccountSyncRequest(mode="first_full", relation_types=["saved", "upvoted"], trigger_type="first_connect"),
    )
    calls: list[tuple[str, str | None]] = []

    def item(external_id: str, relation: str) -> CaptureRequest:
        return CaptureRequest(
            platform="reddit",
            url=f"https://www.reddit.com/r/example/comments/{external_id}/item/",
            external_content_id=external_id,
            relation_type=relation,
            title=external_id,
        )

    class FixtureRegistry:
        def run(self, connector_id, request):
            assert connector_id == "reddit"
            calls.append((request.relation_type, request.cursor))
            if (request.relation_type, request.cursor) == ("saved", None):
                return (
                    ConnectorResult(
                        "reddit",
                        "saved-page-1",
                        "partial",
                        scan_receipt={
                            "completeness": "partial",
                            "item_count": 1,
                            "next_cursor": "t3_saved_page_2",
                            "scope": "account_relation",
                            "relation_type": "saved",
                        },
                    ),
                    [item("saved-1", "saved")],
                )
            if (request.relation_type, request.cursor) == ("saved", "t3_saved_page_2"):
                return (
                    ConnectorResult(
                        "reddit",
                        "saved-page-2",
                        "success",
                        scan_receipt={
                            "completeness": "complete",
                            "item_count": 1,
                            "scope": "account_relation",
                            "relation_type": "saved",
                        },
                    ),
                    [item("saved-2", "saved")],
                )
            if (request.relation_type, request.cursor) == ("upvoted", None):
                return (
                    ConnectorResult(
                        "reddit",
                        "upvoted-page-1",
                        "success",
                        scan_receipt={
                            "completeness": "complete",
                            "item_count": 1,
                            "scope": "account_relation",
                            "relation_type": "upvoted",
                        },
                    ),
                    [item("upvoted-1", "upvoted")],
                )
            raise AssertionError(f"unexpected request: {request.relation_type}, {request.cursor}")

    coordinator.registry = FixtureRegistry()
    coordinator.process_job({"sync_run_id": started["sync_run_id"], "account_id": account_id})

    assert calls == [("saved", None), ("saved", "t3_saved_page_2"), ("upvoted", None)]
    assert store.get_sync_run(started["sync_run_id"])["status"] == "completed"
    assert store.list_library_table(platform="reddit")["total"] == 3
    saved_checkpoint = store.get_sync_checkpoint(
        source_account_id=account_id,
        relation_type="saved",
        collection_key="",
    )
    assert saved_checkpoint["cursor"] == {}
    assert saved_checkpoint["last_complete_sync_run_id"] == started["sync_run_id"]


def test_reddit_account_sync_resumes_checkpoint_and_rate_limit_never_closes_relation(settings, store, service, server_owned_reddit):
    account_id = store.upsert_source_account(
        platform="reddit",
        external_account_id="owner",
        display_name="owner",
        auth_method="oauth",
        auth_handle_ref="conn_reddit_fixture",
        connection_state="connected",
    )
    existing = service.capture(
        CaptureRequest(
            platform="reddit",
            url="https://www.reddit.com/r/example/comments/existing/item/",
            external_content_id="existing",
            relation_type="saved",
            source_account_id="owner",
            title="existing",
        )
    )
    store.upsert_sync_checkpoint(
        source_account_id=account_id,
        relation_type="saved",
        collection_key="",
        cursor={"next_cursor": "t3_resume"},
        known_anchor="existing",
        last_complete_sync_run_id=None,
        complete=False,
    )
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(account_id, AccountSyncRequest(mode="incremental", relation_types=["saved"]))
    calls: list[str | None] = []

    class RateLimitedRegistry:
        def run(self, connector_id, request):
            assert connector_id == "reddit"
            calls.append(request.cursor)
            return (
                ConnectorResult(
                    "reddit",
                    "saved-rate-limited",
                    "partial",
                    scan_receipt={
                        "completeness": "unknown",
                        "item_count": 0,
                        "scope": "account_relation",
                        "relation_type": "saved",
                        "failure_code": "REDDIT_RATE_LIMITED",
                    },
                    errors=[{"code": "REDDIT_RATE_LIMITED", "message": "rate limited", "retryable": True}],
                ),
                [],
            )

    coordinator.registry = RateLimitedRegistry()
    coordinator.process_job({"sync_run_id": started["sync_run_id"], "account_id": account_id})

    assert calls == ["t3_resume"]
    assert store.get_sync_run(started["sync_run_id"])["status"] == "partial"
    assert store.get_sync_checkpoint(
        source_account_id=account_id,
        relation_type="saved",
        collection_key="",
    )["cursor"] == {"next_cursor": "t3_resume"}
    relation = store.get_content(existing.content_id)["relations"][0]
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 0


def test_reddit_checkpoint_resume_requires_fresh_scan_before_relation_closure(settings, store, service, server_owned_reddit):
    account_id = store.upsert_source_account(
        platform="reddit",
        external_account_id="owner",
        display_name="owner",
        auth_method="oauth",
        auth_handle_ref="conn_reddit_fixture",
        connection_state="connected",
    )
    existing = service.capture(
        CaptureRequest(
            platform="reddit",
            url="https://www.reddit.com/r/example/comments/earlier-page/item/",
            external_content_id="earlier-page",
            relation_type="saved",
            source_account_id="owner",
            title="earlier-page",
        )
    )
    store.upsert_sync_checkpoint(
        source_account_id=account_id,
        relation_type="saved",
        collection_key="",
        cursor={"next_cursor": "t3_resume"},
        known_anchor="earlier-page",
        last_complete_sync_run_id=None,
        complete=False,
    )
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(account_id, AccountSyncRequest(mode="incremental", relation_types=["saved"]))

    class FinalPageRegistry:
        def run(self, connector_id, request):
            assert connector_id == "reddit"
            assert request.cursor == "t3_resume"
            return (
                ConnectorResult(
                    "reddit",
                    "saved-final-page",
                    "success",
                    scan_receipt={
                        "completeness": "complete",
                        "item_count": 1,
                        "scope": "account_relation",
                        "relation_type": "saved",
                    },
                ),
                [
                    CaptureRequest(
                        platform="reddit",
                        url="https://www.reddit.com/r/example/comments/final-page/item/",
                        external_content_id="final-page",
                        relation_type="saved",
                        title="final-page",
                    )
                ],
            )

    coordinator.registry = FinalPageRegistry()
    coordinator.process_job({"sync_run_id": started["sync_run_id"], "account_id": account_id})

    run = store.get_sync_run(started["sync_run_id"])
    assert run["status"] == "partial"
    assert run["last_error_code"] == "REDDIT_FRESH_FULL_SCAN_REQUIRED"
    checkpoint = store.get_sync_checkpoint(
        source_account_id=account_id,
        relation_type="saved",
        collection_key="",
    )
    assert checkpoint["cursor"] == {}
    assert checkpoint["last_complete_sync_run_id"] is None
    relation = store.get_content(existing.content_id)["relations"][0]
    assert relation["status"] == "active"
    assert relation["missing_complete_scan_count"] == 0


def test_reddit_account_sync_reports_missing_oauth_as_blocked_environment(settings, store, service, server_owned_reddit):
    account_id = store.upsert_source_account(
        platform="reddit",
        external_account_id="owner",
        display_name="owner",
        auth_method="oauth",
        auth_handle_ref="conn_reddit_fixture",
        connection_state="connected",
    )
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(account_id, AccountSyncRequest(mode="first_full", relation_types=["saved"]))

    class MissingOAuthRegistry:
        def run(self, connector_id, request):
            assert connector_id == "reddit"
            assert request.relation_type == "saved"
            return (
                ConnectorResult(
                    "reddit",
                    "saved-auth-missing",
                    "blocked_environment",
                    scan_receipt={
                        "completeness": "unknown",
                        "item_count": 0,
                        "scope": "account_relation",
                        "relation_type": "saved",
                        "failure_code": "REDDIT_AUTH_MISSING",
                    },
                    errors=[{"code": "REDDIT_AUTH_MISSING", "message": "授权缺失", "retryable": False}],
                ),
                [],
            )

    coordinator.registry = MissingOAuthRegistry()
    coordinator.process_job({"sync_run_id": started["sync_run_id"], "account_id": account_id})

    run = store.get_sync_run(started["sync_run_id"])
    assert run["status"] == "blocked_environment"
    assert run["completeness"] == "unknown"
    assert run["last_error_code"] == "REDDIT_AUTH_MISSING"
    assert store.get_source_account(account_id)["last_sync_at"] is None


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
    with pytest.raises(api.HTTPException) as cursor_error:
        api.run_connector(
            "reddit",
            ConnectorRunRequest(relation_type="saved", source_account_id="owner", cursor="t3_client_supplied"),
        )
    assert cursor_error.value.status_code == 422
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
