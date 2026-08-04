from __future__ import annotations

import httpx

from social_archive.connectors.base import ConnectorResult
from social_archive.connectors.http_workers import OpenAPIURLWorkerConnector
from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def test_ambiguous_openapi_worker_degrades_without_guessing_or_posting(monkeypatch):
    seen = {"post": 0}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "paths": {
                    "/a": {"post": {"description": "download URL"}},
                    "/b": {"post": {"description": "parse URL"}},
                }
            }

    class Client:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, *args, **kwargs):
            return Response()

        def post(self, *args, **kwargs):
            seen["post"] += 1
            raise AssertionError("ambiguous OpenAPI must never receive a guessed POST")

    monkeypatch.setattr(httpx, "Client", Client)
    connector = OpenAPIURLWorkerConnector("douyin", "抖音", "http://worker")

    health = connector.health()
    result = connector.capture({"url": "https://www.douyin.com/video/fixture"})

    assert health["state"] == "degraded"
    # **失败码要稳定，不能是 Python 类名。**
    # 这条原来断言 error_code == "ConnectorError" —— 它把反模式钉住了：
    # 类名对用户没有意义、泄漏实现，而且是无限集合，文案词典追不上，
    # 于是界面只能说「我们没能记录下原因」。生产 connector_state 里
    # 就躺着一个这么来的 CONNECTORERROR。
    # 现在码用稳定的那个，类名仍然留在 message 里给运维看——诊断信息没丢。
    assert health["error_code"] == "WORKER_PROBE_OR_CALL_FAILED"
    assert "ConnectorError" in health["message"], "类名从诊断信息里也没了，那是丢信息"
    assert result.status == "degraded"
    assert result.errors[0]["code"] == "WORKER_PROBE_OR_CALL_FAILED"
    assert seen["post"] == 0


def test_douyin_worker_failure_uses_media_fallback_and_does_not_block_current_page(settings, service):
    class FailingWorker:
        def capture(self, payload):
            return ConnectorResult(
                "douyin",
                "douk-failed",
                "degraded",
                scan_receipt={"completeness": "failed", "item_count": 0},
                errors=[{"code": "WORKER_PROBE_OR_CALL_FAILED", "message": "fixture worker unavailable", "retryable": True}],
            )

    class MediaFallback:
        def __init__(self):
            self.calls = []

        def capture_url(self, url, tool):
            self.calls.append(tool)
            if tool == "gallery-dl":
                return ConnectorResult(
                    "command-artifact",
                    "gallery-failed",
                    "degraded",
                    scan_receipt={"completeness": "failed", "item_count": 0},
                )
            return ConnectorResult(
                "command-artifact",
                "yt-success",
                "success",
                observations=[{"id": "fallback-video", "url": url, "title": "fixture fallback"}],
                scan_receipt={"completeness": "complete", "item_count": 1},
            )

    registry = ConnectorRegistry(settings)
    fallback_command = MediaFallback()
    registry._connectors["douyin"] = FailingWorker()
    registry.command = fallback_command
    url = "https://www.douyin.com/video/fixture"

    result, captures = registry.run("douyin", ConnectorRunRequest(url=url))
    current_page, current_page_captures = registry.run(
        "generic-web",
        ConnectorRunRequest(url=url, requested_levels=["L0", "L1"]),
    )

    assert fallback_command.calls == ["gallery-dl", "yt-dlp"]
    assert result.status == "success"
    assert result.connector_id == "douyin"
    assert result.scan_receipt["fallback_from_worker"] is True
    assert result.errors[0]["code"] == "WORKER_PROBE_OR_CALL_FAILED"
    assert len(captures) == 1
    assert current_page.status == "success"
    response = service.capture(current_page_captures[0])
    assert response.accepted_levels == ["L0", "L1"]
    assert response.paused_levels == []


def test_douyin_total_media_failure_still_does_not_block_current_page(settings, service):
    class FailingWorker:
        def capture(self, payload):
            return ConnectorResult(
                "douyin",
                "douk-failed",
                "degraded",
                scan_receipt={"completeness": "failed", "item_count": 0},
                errors=[{"code": "WORKER_PROBE_OR_CALL_FAILED", "message": "fixture worker unavailable", "retryable": True}],
            )

    class AllMediaFallbacksFail:
        def __init__(self):
            self.calls = []

        def capture_url(self, url, tool):
            self.calls.append(tool)
            return ConnectorResult(
                "command-artifact",
                f"{tool}-failed",
                "degraded",
                scan_receipt={"completeness": "failed", "item_count": 0},
            )

    registry = ConnectorRegistry(settings)
    fallback_command = AllMediaFallbacksFail()
    registry._connectors["douyin"] = FailingWorker()
    registry.command = fallback_command
    url = "https://www.douyin.com/video/fixture"

    failed_result, failed_captures = registry.run("douyin", ConnectorRunRequest(url=url))
    current_page, current_page_captures = registry.run(
        "generic-web",
        ConnectorRunRequest(url=url, requested_levels=["L0", "L1"]),
    )

    assert fallback_command.calls == ["gallery-dl", "yt-dlp"]
    assert failed_result.status == "degraded"
    assert failed_captures == []
    assert current_page.status == "success"
    response = service.capture(current_page_captures[0])
    assert response.accepted_levels == ["L0", "L1"]
    assert response.paused_levels == []
