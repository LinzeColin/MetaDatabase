from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from social_archive.destinations import DestinationRegistry
from social_archive.models import CaptureRequest
from social_archive.service import ArchiveService


def _secret(path: Path, value: str) -> str:
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _factory(transport: httpx.BaseTransport):
    return lambda **kwargs: httpx.Client(transport=transport, **kwargs)


def _capture(service) -> str:
    return service.capture(
        CaptureRequest(
            platform="generic_web",
            url="https://example.test/article",
            title="可重建阅读投影",
            text="正文",
            requested_levels=["L0", "L1"],
            destination_ids=["social_archive"],
        )
    ).content_id


def _canonical_facts(store, content_id: str) -> dict[str, object]:
    content = store.get_content(content_id)
    assert content is not None
    return {
        key: content[key]
        for key in ("id", "platform", "canonical_url", "title", "author_name", "published_at", "metadata_json")
    }


def test_karakeep_probe_and_projection_are_idempotent(settings, store, service, tmp_path):
    configured = replace(
        settings,
        karakeep_url="http://karakeep:3000",
        karakeep_token_file=_secret(tmp_path / "karakeep.token", "reader-secret"),
    )
    requests: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer reader-secret"
        body = __import__("json").loads(request.content) if request.content else {}
        requests.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/api/v1/bookmarks":
            return httpx.Response(200, json={"bookmarks": []})
        if request.method == "POST" and request.url.path == "/api/v1/bookmarks":
            assert body == {"type": "link", "url": "https://example.test/article"}
            return httpx.Response(201, json={"id": "karakeep-1"})
        return httpx.Response(404)

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    assert registry.probe("karakeep")["state"] == "connected"
    content_id = _capture(service)
    canonical_before = _canonical_facts(store, content_id)
    first = registry.export("karakeep", content_id)
    count = len(requests)
    second = registry.export("karakeep", content_id)
    assert first["remote_id"] == "karakeep-1"
    assert second["status"] == "noop"
    assert len(requests) == count
    assert _canonical_facts(store, content_id) == canonical_before

    # A reader binding is a disposable projection. Removing only its binding
    # must allow a new projection without changing canonical content.
    with store.connection() as con:
        con.execute("DELETE FROM destination_binding WHERE destination_id=? AND content_id=?", ("karakeep", content_id))
    rebuilt = registry.export("karakeep", content_id)
    assert rebuilt["remote_id"] == "karakeep-1"
    assert len(requests) == count + 1
    assert _canonical_facts(store, content_id) == canonical_before


def test_unavailable_karakeep_does_not_block_canonical_generic_capture(settings, store, service, tmp_path):
    configured = replace(
        settings,
        karakeep_url="http://karakeep:3000",
        karakeep_token_file=_secret(tmp_path / "karakeep.token", "reader-secret"),
    )

    def ready_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer reader-secret"
        assert request.method == "GET"
        return httpx.Response(200, json={"bookmarks": []})

    ready = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(ready_handler)))
    assert ready.probe("karakeep")["authorized"] is True

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer reader-secret"
        return httpx.Response(503, json={"message": "temporarily unavailable"})

    response = ArchiveService(configured, store).capture(
        CaptureRequest(
            platform="generic_web",
            url="https://example.test/reader-degraded",
            title="主档案不受阅读器故障阻断",
            text="正文",
            requested_levels=["L0", "L1"],
            destination_ids=["social_archive", "karakeep"],
        )
    )
    canonical_before = _canonical_facts(store, response.content_id)
    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError):
        registry.export("karakeep", response.content_id, job_id=response.job_ids[0])

    assert _canonical_facts(store, response.content_id) == canonical_before
    assert store.get_job(response.job_ids[0])["status"] == "queued"
    assert registry.probe("karakeep")["state"] == "degraded"
    content = store.get_content(response.content_id)
    assert content is not None
    assert not content["destination_bindings"]
    assert content["export_receipts"][0]["status"] == "failed"
    assert content["export_receipts"][0]["error_code"] == "HTTP_503"


def test_linkwarden_probe_and_projection(settings, store, service, tmp_path):
    configured = replace(
        settings,
        linkwarden_url="http://linkwarden:3000",
        linkwarden_token_file=_secret(tmp_path / "linkwarden.token", "reader-secret"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer reader-secret"
        if request.method == "GET" and request.url.path == "/api/v1/links":
            return httpx.Response(200, json={"response": []})
        if request.method == "POST" and request.url.path == "/api/v1/links":
            body = __import__("json").loads(request.content)
            assert body == {"url": "https://example.test/article"}
            return httpx.Response(200, json={"response": {"id": 42}})
        return httpx.Response(404)

    registry = DestinationRegistry(configured, store, client_factory=_factory(httpx.MockTransport(handler)))
    assert registry.probe("linkwarden")["state"] == "connected"
    result = registry.export("linkwarden", _capture(service))
    assert result["remote_id"] == "42"


def test_archivebox_queue_is_local_rebuildable_projection(settings, store, service):
    registry = DestinationRegistry(settings, store)
    view = registry.probe("archivebox")
    assert view["state"] == "connected"
    content_id = _capture(service)
    first = registry.export("archivebox", content_id)
    second = registry.export("archivebox", content_id)
    queue = Path(first["path"])
    assert queue.read_text(encoding="utf-8").splitlines() == ["https://example.test/article"]
    assert second["status"] == "noop"
