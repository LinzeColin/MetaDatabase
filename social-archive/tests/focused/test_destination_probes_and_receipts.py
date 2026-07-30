from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from social_archive.destinations import (
    PRIVATE_DATABASE_AREA,
    PRIVATE_DATABASE_REPOSITORY,
    DestinationError,
    DestinationRegistry,
    retry_after_seconds_from_error,
)
from social_archive.models import CaptureRequest
from social_archive.worker import _finish_failed_job


def _secret(path: Path, value: str) -> str:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _factory(transport: httpx.BaseTransport):
    return lambda **kwargs: httpx.Client(transport=transport, **kwargs)


def test_configured_destination_is_not_claimed_connected_before_probe(settings, store, tmp_path):
    configured = replace(
        settings,
        notion_token_file=_secret(tmp_path / "notion.token", "secret"),
        notion_data_source_id="ds_123",
    )
    notion = next(item for item in DestinationRegistry(configured, store).views() if item["destination_id"] == "notion")
    assert notion["configured"] is True
    assert notion["authorized"] is False
    assert notion["state"] == "needs_user_action"
    assert "检查连接" in notion["next_action_zh"]


def test_notion_probe_discovers_unique_data_source(settings, store, tmp_path):
    configured = replace(
        settings,
        notion_token_file=_secret(tmp_path / "notion.token", "secret"),
        notion_database_id="db_123",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Notion-Version"] == "2026-03-11"
        if request.url.path == "/v1/databases/db_123":
            return httpx.Response(200, json={"data_sources": [{"id": "ds_123"}]})
        if request.url.path == "/v1/data_sources/ds_123":
            return httpx.Response(200, json={"properties": {"Name": {"type": "title"}}})
        return httpx.Response(404, json={"message": "not found"})

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    result = registry.probe("notion")
    assert result["state"] == "connected"
    assert result["authorized"] is True
    assert result["capabilities"]["data_source_id"] == "ds_123"
    assert result["capabilities"]["api_version"] == "2026-03-11"
    assert result["last_checked_at"]


def test_notion_export_uses_data_source_and_is_idempotent(settings, store, service, tmp_path):
    configured = replace(
        settings,
        notion_token_file=_secret(tmp_path / "notion.token", "secret"),
        notion_data_source_id="ds_123",
    )
    response = service.capture(
        CaptureRequest(
            platform="generic_web",
            url="https://unit.test/article",
            title="测试内容",
            text="正文",
            requested_levels=["L0", "L1"],
            destination_ids=["social_archive"],
        )
    )
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        assert request.headers["Notion-Version"] == "2026-03-11"
        if request.method == "GET" and request.url.path == "/v1/data_sources/ds_123":
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "Name": {"type": "title"},
                        "Source": {"type": "url"},
                        "Platform": {"type": "rich_text"},
                        "Social Archive ID": {"type": "rich_text"},
                    }
                },
            )
        if request.method == "POST" and request.url.path == "/v1/pages":
            payload = __import__("json").loads(request.content)
            assert payload["parent"] == {"type": "data_source_id", "data_source_id": "ds_123"}
            return httpx.Response(200, json={"id": "page_123", "url": "https://notion.so/page_123"})
        if request.method == "PATCH" and request.url.path == "/v1/blocks/page_123/children":
            return httpx.Response(200, json={"results": [{"id": "block_123"}]})
        return httpx.Response(500, json={"message": f"unexpected {request.method} {request.url.path}"})

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    assert registry.probe("notion")["authorized"] is True
    first = registry.export("notion", response.content_id, job_id="job_1")
    request_count = len(requests)
    second = registry.export("notion", response.content_id, job_id="job_2")

    assert first["status"] == "done"
    assert first["remote_id"] == "page_123"
    assert second["status"] == "noop"
    assert len(requests) == request_count
    binding = store.get_destination_binding("notion", response.content_id)
    assert binding and binding["remote_id"] == "page_123"
    assert binding["metadata"]["notion_block_ids"] == ["block_123"]
    receipts = store.list_destination_receipts(content_id=response.content_id)
    assert [item["status"] for item in receipts] == ["noop", "done"]


def test_notion_page_checkpoint_reuses_page_and_honors_429_retry_after(settings, store, service, tmp_path, monkeypatch):
    configured = replace(
        settings,
        notion_token_file=_secret(tmp_path / "notion.token", "secret"),
        notion_data_source_id="ds_123",
    )
    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://unit.test/notion-checkpoint",
        title="Notion 恢复检查点",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive"],
    ))
    canonical_before = store.get_content(captured.content_id)
    assert canonical_before is not None
    canonical_fields = {key: canonical_before[key] for key in ("id", "canonical_url", "title", "metadata_json")}
    job_id = store.enqueue_job(
        "export_destination",
        {"content_id": captured.content_id, "destination_id": "notion"},
        connector_id="notion",
    )
    claimed = store.claim_job("notion-fixture")
    assert claimed and claimed["id"] == job_id
    phase = {"rate_limited": True}
    counts = {"requests": 0, "page_create": 0, "page_update": 0, "block_update": 0, "append": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counts["requests"] += 1
        assert request.headers["Notion-Version"] == "2026-03-11"
        if request.method == "GET" and request.url.path == "/v1/data_sources/ds_123":
            return httpx.Response(200, json={"properties": {"Name": {"type": "title"}}})
        if request.method == "POST" and request.url.path == "/v1/pages":
            counts["page_create"] += 1
            payload = json.loads(request.content)
            assert payload["parent"] == {"type": "data_source_id", "data_source_id": "ds_123"}
            return httpx.Response(200, json={"id": "page_123", "url": "https://notion.so/page_123"})
        if request.method == "PATCH" and request.url.path == "/v1/pages/page_123":
            counts["page_update"] += 1
            return httpx.Response(200, json={"id": "page_123", "url": "https://notion.so/page_123"})
        if request.method == "PATCH" and request.url.path == "/v1/blocks/page_123/children":
            counts["append"] += 1
            children = json.loads(request.content)["children"]
            if counts["append"] == 2 and phase["rate_limited"]:
                return httpx.Response(429, headers={"Retry-After": "7"}, json={"code": "rate_limited"})
            start = 0 if counts["append"] == 1 else 100
            return httpx.Response(200, json={"results": [{"id": f"block_{start + index}"} for index in range(len(children))]})
        if request.method == "PATCH" and request.url.path.startswith("/v1/blocks/block_"):
            counts["block_update"] += 1
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1]})
        return httpx.Response(500, json={"message": f"unexpected {request.method} {request.url.path}"})

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    assert registry.probe("notion")["authorized"] is True
    counts.update({key: 0 for key in counts})
    monkeypatch.setattr(registry, "_notion_chunks", lambda _: [f"chunk-{index}" for index in range(101)])

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        registry.export("notion", captured.content_id, job_id=job_id)
    assert retry_after_seconds_from_error(exc_info.value) == 7
    checkpoint = store.get_destination_binding("notion", captured.content_id)
    assert checkpoint and checkpoint["remote_id"] == "page_123"
    assert checkpoint["projection_sha256"].startswith("pending:")
    assert checkpoint["metadata"]["notion_sync_state"] == "pending"
    assert checkpoint["metadata"]["notion_block_ids"] == [f"block_{index}" for index in range(100)]
    failed_receipt = store.list_destination_receipts(content_id=captured.content_id)
    assert len(failed_receipt) == 1
    assert failed_receipt[0]["status"] == "failed"
    assert failed_receipt[0]["error_code"] == "HTTP_429"
    assert failed_receipt[0]["remote_id"] == "page_123"
    assert failed_receipt[0]["remote_path"] == "https://notion.so/page_123"
    assert failed_receipt[0]["evidence"] == {"retryable": True, "retry_after_seconds": 7}
    assert counts["page_create"] == 1

    before_finish = datetime.now(timezone.utc)
    _finish_failed_job(store, claimed, exc_info.value)
    assert store.get_job(job_id)["status"] == "retry"
    with store.connection() as con:
        row = con.execute("SELECT not_before FROM job WHERE id=?", (job_id,)).fetchone()
    due_at = datetime.fromisoformat(str(row["not_before"]).replace("Z", "+00:00"))
    assert 6 <= (due_at - before_finish).total_seconds() <= 9

    assert store.retry_job(job_id) is True
    retry_job = store.claim_job("notion-fixture-retry")
    assert retry_job and retry_job["id"] == job_id and retry_job["attempt_count"] == 1
    phase["rate_limited"] = False
    completed = registry.export("notion", captured.content_id, job_id=job_id, allow_recovery=True)
    store.finish_job(job_id, success=True)
    assert completed["status"] == "done"
    assert counts == {"requests": 107, "page_create": 1, "page_update": 1, "block_update": 100, "append": 3}
    binding = store.get_destination_binding("notion", captured.content_id)
    assert binding and not binding["projection_sha256"].startswith("pending:")
    assert binding["metadata"] == {
        "api_version": "2026-03-11",
        "data_source_id": "ds_123",
        "notion_block_ids": [f"block_{index}" for index in range(101)],
        "notion_sync_state": "complete",
    }
    assert sorted(item["status"] for item in store.list_destination_receipts(content_id=captured.content_id)) == ["done", "failed"]
    canonical_after = store.get_content(captured.content_id)
    assert canonical_after is not None
    assert {key: canonical_after[key] for key in canonical_fields} == canonical_fields

    request_count = counts["requests"]
    assert registry.export("notion", captured.content_id)["status"] == "noop"
    assert counts["requests"] == request_count


def test_notion_network_failure_is_retryable_and_leaves_canonical_store_intact(settings, store, service, tmp_path):
    configured = replace(
        settings,
        notion_token_file=_secret(tmp_path / "notion.token", "secret"),
        notion_data_source_id="ds_123",
    )
    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://unit.test/notion-network-failure",
        title="Notion 网络失败",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive"],
    ))
    canonical_before = store.get_content(captured.content_id)
    assert canonical_before is not None
    canonical_fields = {key: canonical_before[key] for key in ("id", "canonical_url", "title", "metadata_json")}
    job_id = store.enqueue_job(
        "export_destination",
        {"content_id": captured.content_id, "destination_id": "notion"},
        connector_id="notion",
    )
    claimed = store.claim_job("notion-network")
    assert claimed and claimed["id"] == job_id

    def probe_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Notion-Version"] == "2026-03-11"
        assert request.method == "GET"
        assert request.url.path == "/v1/data_sources/ds_123"
        return httpx.Response(200, json={"properties": {"Name": {"type": "title"}}})

    ready = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(probe_handler)))
    assert ready.probe("notion")["authorized"] is True

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fixture offline", request=request)

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(httpx.ConnectError) as exc_info:
        registry.export("notion", captured.content_id, job_id=job_id)
    receipt = store.list_destination_receipts(content_id=captured.content_id)
    assert len(receipt) == 1
    assert receipt[0]["status"] == "failed"
    assert receipt[0]["evidence"] == {"retryable": True}
    assert store.get_destination_binding("notion", captured.content_id) is None
    _finish_failed_job(store, claimed, exc_info.value)
    assert store.get_job(job_id)["status"] == "retry"
    canonical_after = store.get_content(captured.content_id)
    assert canonical_after is not None
    assert {key: canonical_after[key] for key in canonical_fields} == canonical_fields


def test_github_probe_rejects_public_repository_and_records_export_failure(settings, store, service, tmp_path):
    configured = replace(
        settings,
        github_repository=PRIVATE_DATABASE_REPOSITORY,
        github_token_file=_secret(tmp_path / "github.token", "secret"),
    )
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        assert request.url.path == f"/repos/{PRIVATE_DATABASE_REPOSITORY}"
        return httpx.Response(200, json={"private": False, "default_branch": "main"})

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    result = registry.probe("github")
    assert result["state"] == "blocked_policy"
    assert result["authorized"] is False
    assert "Private Repository" in result["last_message_zh"]
    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://unit.test/public-repository",
        title="公开仓库拒绝",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive"],
    ))
    with pytest.raises(DestinationError, match="主动连接检查") as exc_info:
        registry.export("github", captured.content_id, job_id="github-public")
    assert exc_info.value.code == "DESTINATION_PROBE_REQUIRED"
    assert all("/contents/" not in path for path in requested_paths)
    assert store.get_destination_binding("github", captured.content_id) is None
    receipts = store.list_destination_receipts(content_id=captured.content_id)
    assert len(receipts) == 1
    assert receipts[0]["status"] == "failed"
    assert receipts[0]["error_code"] == "DESTINATION_PROBE_REQUIRED"


def test_github_contents_export_reconciles_private_target_and_uses_sha_idempotency(settings, store, service, tmp_path):
    configured = replace(
        settings,
        github_repository=PRIVATE_DATABASE_REPOSITORY,
        github_token_file=_secret(tmp_path / "github.token", "secret"),
    )
    captured = service.capture(CaptureRequest(
        platform="generic_web",
        url="https://unit.test/github-private-database",
        title="GitHub 私有归档",
        text="只应写入 Private-Database。",
        requested_levels=["L0", "L1"],
        destination_ids=["social_archive"],
    ))
    requests: list[tuple[str, str]] = []
    put_payloads: list[dict[str, object]] = []
    remote: dict[str, str | None] = {"sha": None, "path": None}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == f"/repos/{PRIVATE_DATABASE_REPOSITORY}":
            return httpx.Response(200, json={"private": True, "default_branch": "main"})
        if request.method == "GET" and "/contents/" in request.url.path:
            assert f"/contents/{PRIVATE_DATABASE_AREA}/SocialArchive/markdown/" in request.url.path
            if remote["sha"] is None:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json={"sha": remote["sha"], "path": remote["path"]})
        if request.method == "PUT" and "/contents/" in request.url.path:
            assert f"/contents/{PRIVATE_DATABASE_AREA}/SocialArchive/markdown/" in request.url.path
            payload = json.loads(request.content)
            put_payloads.append(payload)
            markdown = base64.b64decode(str(payload["content"]))
            expected_sha = hashlib.sha1(b"blob %d\0" % len(markdown) + markdown).hexdigest()
            assert payload["branch"] == "main"
            assert b"GitHub" in markdown
            assert captured.content_id.encode("utf-8") in markdown
            if remote["sha"] is not None:
                assert payload["sha"] == remote["sha"]
            remote["sha"] = expected_sha
            remote["path"] = request.url.path.split("/contents/", 1)[1]
            return httpx.Response(
                201,
                json={
                    "content": {"sha": expected_sha, "path": remote["path"]},
                    "commit": {"sha": f"commit-{len(put_payloads)}"},
                },
            )
        return httpx.Response(500, json={"message": f"unexpected {request.method} {request.url.path}"})

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    assert registry.probe("github")["authorized"] is True
    requests.clear()
    first = registry.export("github", captured.content_id, job_id="github-first")
    first_count = len(requests)
    second = registry.export("github", captured.content_id, job_id="github-repeat")

    assert first["status"] == "done"
    assert second["status"] == "noop"
    assert [method for method, _ in requests[:3]] == ["GET", "GET", "PUT"]
    assert [method for method, _ in requests[first_count:]] == ["GET", "GET"]
    assert len(put_payloads) == 1
    binding = store.get_destination_binding("github", captured.content_id)
    assert binding and binding["remote_id"] == remote["sha"]
    assert binding["metadata"] == {
        "area": PRIVATE_DATABASE_AREA,
        "branch": "main",
        "private": True,
        "reconciled": True,
        "repository": PRIVATE_DATABASE_REPOSITORY,
    }

    # A local binding is not enough: a changed/deleted remote file is repaired
    # with the Contents API's current SHA rather than incorrectly returning noop.
    remote["sha"] = "remote-modified-sha"
    repaired = registry.export("github", captured.content_id, job_id="github-reconcile")
    assert repaired["status"] == "done"
    assert len(put_payloads) == 2
    assert put_payloads[-1]["sha"] == "remote-modified-sha"
    receipts = store.list_destination_receipts(content_id=captured.content_id)
    assert sorted(item["status"] for item in receipts) == ["done", "done", "noop"]


def test_github_rejects_noncanonical_private_database_target_without_network(settings, store, tmp_path):
    configured = replace(
        settings,
        github_repository="owner/other-private-repository",
        github_token_file=_secret(tmp_path / "github.token", "secret"),
    )

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("target identity must be checked before any network request")

    result = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler))).probe("github")
    assert result["state"] == "blocked_policy"
    assert result["authorized"] is False
    assert "Private-Database" in result["last_message_zh"]


def test_obsidian_probe_blocks_known_vulnerable_rest_version(settings, store, tmp_path):
    configured = replace(
        settings,
        obsidian_rest_url="https://127.0.0.1:27124",
        obsidian_rest_token_file=_secret(tmp_path / "obsidian.token", "secret"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, json={"versions": {"self": "4.1.2"}})
        if request.url.path == "/vault/":
            return httpx.Response(200, json={"files": []})
        return httpx.Response(404)

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    result = registry.probe("obsidian")
    assert result["state"] == "blocked_policy"
    assert "4.1.3" in result["last_message_zh"]


def test_bad_secret_permissions_are_visible_instead_of_crashing_bootstrap(settings, store, tmp_path):
    secret = tmp_path / "notion.bad-mode"
    secret.write_text("secret", encoding="utf-8")
    secret.chmod(0o644)
    configured = replace(
        settings,
        notion_token_file=str(secret),
        notion_data_source_id="ds_123",
    )
    registry = DestinationRegistry(configured, store)
    notion = next(item for item in registry.views() if item["destination_id"] == "notion")
    assert notion["configured"] is False
    assert notion["authorized"] is False
    assert notion["state"] == "needs_user_action"
    assert notion["last_message_zh"]

    probed = registry.probe("notion")
    assert probed["state"] == "needs_user_action"
    assert probed["authorized"] is False
