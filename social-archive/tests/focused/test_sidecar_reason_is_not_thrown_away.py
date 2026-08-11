"""Sidecar 已经说了原因，别把它扔掉（v0.0.0.7 / INV-NO-SILENT-ZERO 的镜像）。

实测（2026-08-04 生产）：`POST /v1/connectors/instagram/run` 返回

    {"detail":"CLI Sidecar 调用失败：HTTP 422"}

没有失败码、没有中文下一步、看不出缺的是什么。

而 sidecar 那边（sidecars/cli-tools/server.py:286）返回的是

    {"status":"failed","error":"<异常类名>","message":"<真实原因>", …}

**原因一直都在，是 raise_for_status() 之后被我们原样扔掉的。**
这和「读不懂就报没有」是同一种毛病的镜像：读到了原因，然后丢掉。
"""

import httpx
import pytest

from social_archive.connectors.command import CommandArtifactConnector
from social_archive.connectors.base import ConnectorError


def _connector(tmp_path, handler) -> CommandArtifactConnector:
    connector = CommandArtifactConnector(
        "instagram", tmp_path, worker_url="http://sidecar.invalid", worker_token_file=None
    )
    transport = httpx.MockTransport(handler)
    original = httpx.Client

    class PatchedClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.Client = PatchedClient  # type: ignore[misc]
    connector._restore_httpx = lambda: setattr(httpx, "Client", original)  # type: ignore[attr-defined]
    return connector


def test_the_sidecars_own_words_reach_the_error(tmp_path, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={
            "status": "failed", "error": "FileNotFoundError",
            "message": "Instagram Session 尚未配置", "artifacts": [], "observations": [],
        })

    connector = _connector(tmp_path, handler)
    try:
        with pytest.raises(ConnectorError) as caught:
            connector._remote("/v1/instagram/saved", {"limit": 3})
    finally:
        connector._restore_httpx()
    assert "Instagram Session 尚未配置" in str(caught.value), (
        "sidecar 说清楚了原因，我们还是只报了一个状态码"
    )
    assert "HTTP 422" not in str(caught.value), "拿状态码顶替了真实原因"


def test_a_status_code_is_the_fallback_not_the_default(tmp_path, monkeypatch) -> None:
    """响应体真的没东西时，才退回状态码。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>bad gateway</html>")

    connector = _connector(tmp_path, handler)
    try:
        with pytest.raises(ConnectorError) as caught:
            connector._remote("/v1/instagram/saved", {"limit": 3})
    finally:
        connector._restore_httpx()
    assert "HTTP 500" in str(caught.value)
