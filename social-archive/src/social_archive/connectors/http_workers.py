from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .base import ConnectorError, ConnectorResult
from ..utils import assert_public_http_url


@dataclass(frozen=True)
class _OpenAPIWorkerRoute:
    path: str
    url_field: str
    include_download: bool


class XHSWorkerConnector:
    connector_id = "xiaohongshu"
    display_name = "小红书"

    def __init__(self, worker_url: str, timeout: float = 120.0, output_root: Path | None = None):
        self.worker_url = worker_url.rstrip("/")
        self.timeout = timeout
        self.output_root = output_root.resolve() if output_root else None
        if self.output_root:
            self.output_root.mkdir(parents=True, exist_ok=True)

    def _snapshot(self) -> set[Path]:
        if not self.output_root:
            return set()
        return {p.resolve() for p in self.output_root.rglob("*") if p.is_file() and not p.is_symlink()}

    def health(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self.worker_url}/openapi.json")
            return {"state":"healthy" if response.status_code == 200 else "degraded","status_code":response.status_code}
        except httpx.HTTPError as exc:
            return {"state":"degraded","error_code":"HEALTH_PROBE_FAILED","detail":exc.__class__.__name__}

    def capture(self, payload: dict[str, Any]) -> ConnectorResult:
        url = assert_public_http_url(str(payload["url"]))
        run_id = str(uuid.uuid4())
        body = {"url": url, "download": True, "index": payload.get("index", []), "skip": payload.get("skip", False)}
        before = self._snapshot()
        # Cookie is deliberately not accepted from payload; the isolated worker reads its own secret/config.
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.worker_url}/xhs/detail", json=body)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return ConnectorResult(self.connector_id, run_id, "degraded", scan_receipt={"completeness":"failed","item_count":0}, errors=[{"code":"XHS_WORKER_FAILED","message":str(exc),"retryable":True}])
        artifacts = [{"path":str(path),"type":"vendor_download"} for path in sorted(self._snapshot() - before)]
        return ConnectorResult(self.connector_id, run_id, "success", observations=[{"url":url,"worker_response":data}], artifacts=artifacts, scan_receipt={"completeness":"complete","item_count":1,"scope":"item"})


class OpenAPIURLWorkerConnector:
    """Probe an isolated worker OpenAPI document instead of inventing an endpoint."""

    def __init__(self, connector_id: str, display_name: str, worker_url: str, timeout: float = 120.0, output_root: Path | None = None):
        self.connector_id = connector_id
        self.display_name = display_name
        self.worker_url = worker_url.rstrip("/")
        self.timeout = timeout
        self.output_root = output_root.resolve() if output_root else None
        if self.output_root:
            self.output_root.mkdir(parents=True, exist_ok=True)

    def _snapshot(self) -> set[Path]:
        if not self.output_root:
            return set()
        return {p.resolve() for p in self.output_root.rglob("*") if p.is_file() and not p.is_symlink()}

    @staticmethod
    def _resolve_local_ref(document: dict[str, Any], value: Any) -> dict[str, Any]:
        """Resolve a local OpenAPI reference, refusing external or cyclic references."""
        seen: set[str] = set()
        while isinstance(value, dict) and isinstance(value.get("$ref"), str):
            ref = value["$ref"]
            if not ref.startswith("#/") or ref in seen:
                return {}
            seen.add(ref)
            target: Any = document
            for segment in ref[2:].split("/"):
                if not isinstance(target, dict):
                    return {}
                target = target.get(segment.replace("~1", "/").replace("~0", "~"))
            value = target
        return value if isinstance(value, dict) else {}

    @classmethod
    def _request_route(cls, document: dict[str, Any], path: str, operation: dict[str, Any]) -> _OpenAPIWorkerRoute | None:
        request_body = cls._resolve_local_ref(document, operation.get("requestBody"))
        content = request_body.get("content")
        if not isinstance(content, dict):
            return None
        json_content = content.get("application/json")
        if not isinstance(json_content, dict):
            return None
        schema = cls._resolve_local_ref(document, json_content.get("schema"))
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return None

        documented_action = " ".join(
            str(part).lower()
            for part in (path, operation.get("operationId"), operation.get("summary"), operation.get("description"))
        )
        if not any(marker in documented_action for marker in ("detail", "download", "parse", "extract")):
            return None

        url_fields = [
            field
            for field in ("url", "text")
            if isinstance(properties.get(field), dict)
            and cls._resolve_local_ref(document, properties[field]).get("type") == "string"
        ]
        if len(url_fields) != 1:
            return None

        url_field = url_fields[0]
        include_download = (
            isinstance(properties.get("download"), dict)
            and cls._resolve_local_ref(document, properties["download"]).get("type") == "boolean"
        )
        required = schema.get("required") or []
        if not isinstance(required, list):
            return None
        supplied_fields = {url_field}
        if include_download:
            supplied_fields.add("download")
        if not all(isinstance(field, str) and field in supplied_fields for field in required):
            return None
        return _OpenAPIWorkerRoute(path=path, url_field=url_field, include_download=include_download)

    def _probe_route(self) -> _OpenAPIWorkerRoute:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{self.worker_url}/openapi.json")
            response.raise_for_status()
            doc = response.json()
        if not isinstance(doc, dict):
            raise ConnectorError("OPENAPI_INVALID_DOCUMENT", f"{self.display_name} Worker 的 OpenAPI 文档不是对象；保持降级并使用当前页兜底。")
        candidates: list[_OpenAPIWorkerRoute] = []
        for path, methods in (doc.get("paths") or {}).items():
            post = methods.get("post") if isinstance(methods, dict) else None
            if not isinstance(path, str) or not isinstance(post, dict):
                continue
            if candidate := self._request_route(doc, path, post):
                candidates.append(candidate)
        if len(candidates) != 1:
            raise ConnectorError("OPENAPI_ROUTE_AMBIGUOUS", f"{self.display_name} Worker 找到 {len(candidates)} 个候选路由；保持降级并使用当前页兜底。")
        return candidates[0]

    def _resolve_route(self) -> str:
        return self._probe_route().path

    def health(self) -> dict[str, Any]:
        try:
            return {"state":"healthy","route":self._resolve_route()}
        except Exception as exc:
            return {"state":"degraded","error_code":"WORKER_PROBE_OR_CALL_FAILED","message":f"{exc.__class__.__name__}: {exc}"}

    def capture(self, payload: dict[str, Any]) -> ConnectorResult:
        run_id = str(uuid.uuid4())
        url = assert_public_http_url(str(payload["url"]))
        before = self._snapshot()
        try:
            route = self._probe_route()
            body: dict[str, Any] = {route.url_field: url}
            if route.include_download:
                body["download"] = True
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.worker_url}{route.path}", json=body)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return ConnectorResult(self.connector_id, run_id, "degraded", scan_receipt={"completeness":"failed","item_count":0}, errors=[{"code":"WORKER_PROBE_OR_CALL_FAILED","message":str(exc),"retryable":True}])
        artifacts = [{"path":str(path),"type":"vendor_download"} for path in sorted(self._snapshot() - before)]
        return ConnectorResult(self.connector_id, run_id, "success", observations=[{"url":url,"worker_response":data}], artifacts=artifacts, scan_receipt={"completeness":"complete","item_count":1,"scope":"item"})
