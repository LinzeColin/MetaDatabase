
from __future__ import annotations

import json
import ipaddress
import os
import secrets
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlparse

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, auth
from .account_sync import AccountSyncCoordinator, PLATFORM_RELATIONS
from .config import Settings
from .db import RuntimeStore
from .destinations import DestinationRegistry, _markdown
from .models import (
    AccountConnectCompleteRequest,
    AccountConnectRequest,
    AccountSyncRequest,
    CaptureBatchRequest,
    CaptureRequest,
    CaptureResponse,
    ConnectorRunRequest,
    JobView,
    MarkdownImportRequest,
    SyncBatchRequest,
    SyncControlRequest,
)
from .registry import ConnectorRegistry
from .service import ArchiveService
from .utils import atomic_write, json_bytes, read_secret, sha256_bytes, utcnow

settings = Settings.from_env()
settings.ensure_directories(require_api_token=True)
store = RuntimeStore(settings.runtime_db)
store.initialize()
service = ArchiveService(settings, store)
registry = ConnectorRegistry(settings)
destinations = DestinationRegistry(settings, store)
account_sync = AccountSyncCoordinator(settings, store, service, registry)
app = FastAPI(title="Social Archive", version=__version__, docs_url="/api/docs", redoc_url=None)
# 登录路由（v0.0.0.7 / T02）。挂在这里而不是散进本文件：auth 有自己的
# Cookie 语义与失败文案，混进 pairing/token 那套只会互相污染。
app.include_router(auth.build_router(settings, store))


class ExportRequest(BaseModel):
    destination_ids: list[str] = Field(default_factory=list, max_length=8)


class LocalObsidianReceiptRequest(BaseModel):
    """An attested receipt from the paired extension's fixed loopback bridge."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    content_id: str = Field(min_length=1, max_length=200)
    status: Literal["done", "noop", "failed"]
    remote_path: str | None = Field(default=None, max_length=2048)


def _observed_bound(value: str | None, *, end_of_day: bool) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        if len(candidate) == 10:
            day = date.fromisoformat(candidate)
            return f"{day.isoformat()}T{'23:59:59.999999Z' if end_of_day else '00:00:00Z'}"
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="时间筛选仅支持 ISO 8601 日期或日期时间") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_local_obsidian_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) < 3
        or path.parts[0] != "Social Archive"
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() != ".md"
    ):
        raise HTTPException(status_code=422, detail="Obsidian 本机回执路径必须位于 Social Archive/ 且为 Markdown 文件")
    return str(path)


def _expected_token() -> str | None:
    return read_secret(settings.api_token_file)


def _request_hostname(request: Request) -> str:
    raw = request.headers.get("host", "").strip().lower()
    if not raw or "," in raw:
        return ""
    return (urlparse(f"//{raw}").hostname or "").lower().rstrip(".")


def _public_hostname(value: str) -> str:
    return (urlparse(value).hostname or "").lower().rstrip(".")


def _trusted_library_access(request: Request) -> bool:
    """Trust Cloudflare Access only on the dedicated library hostname.

    The origin is loopback-only behind Cloudflare Tunnel. Cloudflare Access injects
    the assertion after authentication; the API hostname is deliberately excluded.
    """
    expected_host = _public_hostname(settings.public_library_url)
    actual_host = _request_hostname(request)
    assertion = request.headers.get("cf-access-jwt-assertion", "").strip()
    return bool(expected_host and actual_host == expected_host and len(assertion) >= 80)


def require_api_hostname(request: Request) -> None:
    """Keep unauthenticated pairing endpoints off the private-library hostname."""
    expected_host = _public_hostname(settings.public_base_url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if settings.pairing_required and expected_host and expected_host not in local_hosts:
        if _request_hostname(request) != expected_host:
            raise HTTPException(404, "该入口只在扩展 API 域名提供")


def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    if not settings.pairing_required:
        return
    if _trusted_library_access(request):
        return
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    # v0.0.0.7 / T03：先认扩展令牌（长期、可撤销、绑 user_id）。
    # 配对码那条路暂时保留，等它整条链路删干净再摘——先加后删，
    # 否则会出现一个扩展既不能用旧机制也还没接上新机制的空窗期。
    if supplied and store.resolve_extension_token(supplied):
        return
    expected = _expected_token()
    if not expected:
        raise HTTPException(503, "服务端配对尚未完成")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "扩展尚未授权或令牌已失效")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "project": "Social Archive",
        "version": __version__,
        "time": utcnow(),
        "paid_api_allowed": settings.paid_api_allowed,
        "archive_defaults": {"L0": True, "L1": True, "L2": settings.l2_enabled, "L3": settings.l3_enabled},
    }


@app.get("/v1/status", dependencies=[Depends(require_token)])
def status() -> dict[str, Any]:
    return {
        "project": "Social Archive",
        "version": __version__,
        "endpoint": settings.public_base_url,
        "library_url": settings.public_library_url,
        "archive_defaults": ["L0", "L1", "L3"],
        "l2_enabled": settings.l2_enabled,
        "connectors": registry.health_views(store.connector_states()),
        "destinations": destinations.views(),
        "queue": {"items": store.list_jobs(limit=20)},
        "storage": {"items": store.quota_states(), "replicas": store.replica_summary(), "completion": store.replication_completion()},
    }


def _safe_account_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Reject credential-shaped metadata before it reaches the runtime journal."""
    forbidden = ("cookie", "token", "authorization", "password", "secret", "auth_header")
    bad: list[str] = []

    def inspect(value: Any, path: str = "metadata") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key)
                key_path = f"{path}.{key_text}"
                if any(marker in key_text.lower() for marker in forbidden):
                    bad.append(key_path)
                inspect(nested, key_path)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                inspect(nested, f"{path}[{index}]")

    inspect(metadata)
    if bad:
        raise HTTPException(status_code=422, detail="账号连接元数据不得包含 Cookie、令牌、密码或认证头")
    return dict(metadata)


@app.get("/v1/accounts", dependencies=[Depends(require_token)])
def accounts() -> dict[str, Any]:
    return {
        "items": store.list_source_accounts(),
        "supported_platforms": [
            {"platform": platform, "relations": relations}
            for platform, relations in PLATFORM_RELATIONS.items()
        ],
    }


@app.post("/v1/accounts/connect/start", status_code=202, dependencies=[Depends(require_token)])
def account_connect_start(request: AccountConnectRequest) -> dict[str, Any]:
    try:
        result = account_sync.connect_start(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "connection_ref": result.connection_ref,
        "platform": result.platform,
        "auth_method": result.auth_method,
        "state": result.state,
        "next_action_zh": result.next_action_zh,
        "supported_relations": result.supported_relations,
    }


@app.post("/v1/accounts/connect/{platform}/complete", status_code=201, dependencies=[Depends(require_token)])
def account_connect_complete(platform: str, request: AccountConnectCompleteRequest) -> dict[str, Any]:
    metadata = _safe_account_metadata(request.metadata)
    auth_method = str(metadata.get("auth_method") or "browser_session")
    allowed_methods = {"oauth", "qr", "browser_session", "official_export", "local_import", "chrome_bookmarks"}
    if auth_method not in allowed_methods:
        raise HTTPException(status_code=422, detail="账号连接方式无效")
    try:
        account_id = account_sync.complete_connection(
            platform=platform.strip().lower(),
            auth_method=auth_method,
            connection_ref=request.connection_ref,
            external_account_id=request.external_account_id,
            display_name=request.display_name,
            auto_sync_enabled=bool(metadata.get("auto_sync_enabled", True)),
            sync_interval_minutes=int(metadata.get("sync_interval_minutes", settings.account_sync_default_interval_minutes)),
            metadata=metadata,
            verified=request.verified,
        )
        first = account_sync.start_sync(account_id, AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "account_id": account_id,
        "state": "connected",
        "first_sync": first,
        "next_action_zh": "账号已连接，首次全量同步已经开始。",
    }


@app.post("/v1/accounts/{account_id}/sync", status_code=202, dependencies=[Depends(require_token)])
def start_account_sync(account_id: str, request: AccountSyncRequest) -> dict[str, Any]:
    try:
        return account_sync.start_sync(account_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/accounts/{account_id}/sync-runs", dependencies=[Depends(require_token)])
def account_sync_runs(account_id: str, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    if not store.get_source_account(account_id):
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"items": store.list_sync_runs(source_account_id=account_id, limit=limit)}


@app.get("/v1/sync-runs", dependencies=[Depends(require_token)])
def sync_runs(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"items": store.list_sync_runs(limit=limit)}


@app.get("/v1/sync-runs/{sync_run_id}", dependencies=[Depends(require_token)])
def sync_run_detail(sync_run_id: str) -> dict[str, Any]:
    row = store.get_sync_run(sync_run_id)
    if not row:
        raise HTTPException(status_code=404, detail="同步运行不存在")
    return row


@app.post("/v1/sync-runs/{sync_run_id}/control", dependencies=[Depends(require_token)])
def control_sync_run(sync_run_id: str, request: SyncControlRequest) -> dict[str, Any]:
    if not store.control_sync_run(sync_run_id, request.action):
        raise HTTPException(status_code=409, detail="当前状态不能执行该操作")
    row = store.get_sync_run(sync_run_id)
    return {"sync_run_id": sync_run_id, "action": request.action, "status": row["status"] if row else "unknown"}


@app.post("/v1/sync-runs/{sync_run_id}/batches", status_code=202, dependencies=[Depends(require_token)])
def ingest_sync_batch(sync_run_id: str, request: SyncBatchRequest) -> dict[str, Any]:
    try:
        return account_sync.ingest_batch(sync_run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/connectors", dependencies=[Depends(require_token)])
def connectors() -> dict[str, Any]:
    return {"items": registry.health_views(store.connector_states())}


@app.get("/v1/extension/bootstrap", dependencies=[Depends(require_token)])
def extension_bootstrap() -> dict[str, Any]:
    """Single low-latency payload for popup/options/side-panel rendering."""
    connector_items = registry.health_views(store.connector_states())
    destination_items = destinations.views()
    jobs = store.list_jobs(limit=100)
    storage_items = store.quota_states()
    replicas = store.replica_summary()
    destination_receipts = store.list_destination_receipts(limit=30)
    connected_sources = sum(1 for item in connector_items if item["state"] == "healthy")
    connected_destinations = sum(1 for item in destination_items if item["state"] == "connected")
    return {
        "project": "Social Archive",
        "version": __version__,
        "endpoint": settings.public_base_url,
        "library_url": settings.public_library_url,
        "archive_defaults": ["L0", "L1", "L3"],
        "l2_enabled": settings.l2_enabled,
        "connectors": connector_items,
        "destinations": destination_items,
        "jobs": jobs,
        "destination_receipts": destination_receipts,
        "storage": {"items": storage_items, "replicas": replicas, "completion": store.replication_completion()},
        "summary": {
            "connected_sources": connected_sources,
            "connected_destinations": connected_destinations,
            "failed_exports": sum(1 for item in destination_receipts if item["status"] == "failed"),
            "needs_user_action": (
                sum(1 for job in jobs if job["status"] in {"retry", "failed"})
                + sum(1 for item in destination_items if item["state"] in {"needs_user_action", "degraded", "expired", "blocked_policy"})
            ),
        },
        "pairing": {
            "required": settings.pairing_required,
            "paired": bool(_expected_token()) if settings.pairing_required else True,
            "mode": "cloud_first" if settings.public_base_url.startswith("https://") else "local_development",
        },
        "privacy": {
            "cookie_custody": False,
            "password_custody": False,
            "user_triggered_capture_only": True,
        },
    }


def _artifact_mapping(captures: list[CaptureRequest], artifacts: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    mapping: dict[int, list[dict[str, Any]]] = {}
    if not artifacts or not captures:
        return mapping
    if len(captures) == 1:
        mapping[0] = artifacts
        return mapping
    for index, capture in enumerate(captures):
        key = capture.external_content_id
        if not key:
            continue
        matched = [item for item in artifacts if key in Path(str(item.get("path") or "")).name]
        if matched:
            mapping[index] = matched
    return mapping


@app.post("/v1/connectors/{connector_id}/run", status_code=202, dependencies=[Depends(require_token)])
def run_connector(connector_id: str, request: ConnectorRunRequest) -> dict[str, Any]:
    if request.cursor:
        raise HTTPException(status_code=422, detail="分页检查点仅由账号同步任务内部管理，不能从请求提交")
    started = time.perf_counter()
    try:
        result, captures = registry.run(connector_id, request)
        mapping = _artifact_mapping(captures, result.artifacts)
        responses: list[CaptureResponse] = []
        adopted_artifact_ids: list[str] = []
        for index, item in enumerate(captures):
            mapped = mapping.get(index, [])
            effective = item
            if mapped and "L3" in item.requested_levels:
                effective = item.model_copy(update={"requested_levels": [level for level in item.requested_levels if level != "L3"]})
            response = service.capture(effective)
            responses.append(response)
            if mapped and "L3" in item.requested_levels:
                adopted_artifact_ids.extend(service.attach_local_artifacts(response.content_id, mapped))

        receipt = dict(result.scan_receipt)
        relation_type = str(receipt.get("relation_type") or request.relation_type or "saved")
        collection_key = str(receipt.get("collection_key") or request.collection_key or "")
        source_account_id = str(receipt.get("source_account_id") or request.source_account_id or "") or None
        receipt_id = store.record_scan_receipt(connector_id, result.run_id, receipt, source_account_id=source_account_id, relation_type=relation_type)
        advanced_missing = 0
        if receipt.get("completeness") == "complete" and receipt.get("scope") == "account_relation":
            advanced_missing = store.apply_complete_scan(
                connector_id,
                {response.relation_id for response in responses},
                relation_type=relation_type,
                collection_key=collection_key,
                source_account_id=source_account_id,
            )
        state = "healthy" if result.status in {"success", "partial"} else ("blocked_environment" if result.status == "blocked_environment" else "degraded")
        store.upsert_connector_state(
            connector_id,
            state=state,
            policy_gate="pass",
            auth_gate="pass" if state == "healthy" else "unknown",
            technical_gate="pass" if state == "healthy" else "unknown",
            error_code=(result.errors[0].get("code") if result.errors else None),
            last_checked_at=utcnow(),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            message_zh="最近一次读取完成。" if state == "healthy" else "最近一次读取未完成；请按下一步处理或使用保存当前页面。",
        )
        return {
            "connector_id": connector_id,
            "run_id": result.run_id,
            "status": result.status,
            "scan_receipt": receipt,
            "scan_receipt_id": receipt_id,
            "imported": len(responses),
            "adopted_artifact_count": len(adopted_artifact_ids),
            "advanced_missing_relation_count": advanced_missing,
            "content_ids": [response.content_id for response in responses],
            "errors": result.errors,
            "next_action_zh": "已进入资料库。" if responses else (result.errors[0].get("message") if result.errors else "没有读取到可导入内容；仍可使用浏览器扩展保存当前页面。"),
        }
    except (ValueError, OSError, PermissionError, RuntimeError) as exc:
        store.upsert_connector_state(
            connector_id,
            state="degraded",
            policy_gate="pass",
            auth_gate="unknown",
            technical_gate="unknown",
            error_code=exc.__class__.__name__.upper(),
            last_checked_at=utcnow(),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            message_zh="本次读取失败；请检查配置或使用保存当前页面。",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/captures", response_model=CaptureResponse, status_code=202, dependencies=[Depends(require_token)])
def capture(request: CaptureRequest) -> CaptureResponse:
    try:
        return service.capture(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/captures/batch", status_code=202, dependencies=[Depends(require_token)])
def capture_batch(request: CaptureBatchRequest) -> dict[str, Any]:
    responses: list[CaptureResponse] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(request.items):
        try:
            responses.append(service.capture(item))
        except ValueError as exc:
            errors.append({"index": index, "detail": str(exc)})
    return {
        "accepted": len(responses),
        "failed": len(errors),
        "items": [item.model_dump(mode="json") for item in responses],
        "errors": errors,
    }


@app.post("/v1/import/markdown", dependencies=[Depends(require_token)])
def import_markdown(request: MarkdownImportRequest) -> dict[str, Any]:
    try:
        return service.import_markdown(request)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/import/social-archiver", dependencies=[Depends(require_token)])
async def import_social_archiver(
    request: Request,
    x_archive_filename: str = Header(default="social-archiver-export.zip"),
    platform_hint: str = Query(default="import", min_length=1, max_length=64),
    relation_type: str = Query(default="saved"),
    limit: int = Query(default=1000, ge=1, le=10000),
) -> dict[str, Any]:
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="导入包超过 200 MiB")
    payload = await request.body()
    try:
        return service.import_social_archiver_bundle(
            payload,
            filename=Path(x_archive_filename).name,
            platform_hint=platform_hint,
            relation_type=relation_type,
            limit=limit,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/jobs", dependencies=[Depends(require_token)])
def jobs(limit: int = Query(100, ge=1, le=500), status_filter: str | None = Query(default=None, alias="status")) -> dict[str, Any]:
    return {"items": store.list_jobs(limit=limit, status=status_filter)}


@app.get("/v1/jobs/{job_id}", response_model=JobView, dependencies=[Depends(require_token)])
def get_job(job_id: str) -> dict[str, Any]:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return row


@app.post("/v1/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
def retry_job(job_id: str) -> dict[str, Any]:
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row["status"] in {"queued", "running", "done"}:
        raise HTTPException(status_code=409, detail="当前任务已在队列中、正在处理或已经完成，不能重试")
    if not store.retry_job(job_id):
        raise HTTPException(status_code=409, detail="任务状态已变化，请刷新后重试")
    return {"job_id": job_id, "status": "queued", "message_zh": "已重新加入队列"}


@app.get("/v1/destinations", dependencies=[Depends(require_token)])
def destination_status() -> dict[str, Any]:
    return {"items": destinations.views()}


@app.post("/v1/destinations/{destination_id}/probe", dependencies=[Depends(require_token)])
def probe_destination(destination_id: str) -> dict[str, Any]:
    try:
        return destinations.probe(destination_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/destinations/receipts", dependencies=[Depends(require_token)])
def destination_receipts(
    limit: int = Query(default=100, ge=1, le=500),
    destination_id: str | None = Query(default=None),
    content_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    return {
        "items": store.list_destination_receipts(
            limit=limit,
            destination_id=destination_id,
            content_id=content_id,
            status=status_filter,
        )
    }


@app.post("/v1/destinations/receipts/{receipt_id}/retry", status_code=202, dependencies=[Depends(require_token)])
def retry_destination_receipt(receipt_id: str) -> dict[str, Any]:
    receipt = store.get_destination_receipt(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="目的地回执不存在")
    if receipt["status"] != "failed":
        raise HTTPException(status_code=409, detail="该回执不处于失败状态，无需重试")
    if receipt["destination_id"] != "social_archive" and not destinations.is_export_authorized(receipt["destination_id"], allow_recovery=True):
        raise HTTPException(status_code=409, detail="目的地尚未完成主动连接检查或授权已失效；请先检查连接后再重试")
    job_id = str(receipt.get("job_id") or "")
    if job_id:
        job = store.get_job(job_id)
        if job:
            if job["status"] in {"queued", "running"}:
                return {"job_id": job_id, "status": job["status"], "message_zh": "该目的地任务已在处理中。"}
            if job["status"] == "done":
                raise HTTPException(status_code=409, detail="该目的地任务已经完成，请刷新回执")
            if store.retry_job(job_id):
                return {"job_id": job_id, "status": "queued", "message_zh": "已重新加入目的地导出队列"}
    replacement_id = store.enqueue_job(
        "export_destination",
        {"content_id": receipt["content_id"], "destination_id": receipt["destination_id"]},
        connector_id=receipt["destination_id"],
    )
    replacement = store.get_job(replacement_id)
    if not replacement:
        raise HTTPException(status_code=409, detail="无法创建目的地重试任务，请刷新后重试")
    if replacement["status"] in {"queued", "running"}:
        return {"job_id": replacement_id, "status": replacement["status"], "message_zh": "该目的地任务已在处理中。"}
    if replacement["status"] == "done":
        raise HTTPException(status_code=409, detail="该目的地任务已经完成，请刷新回执")
    if not store.retry_job(replacement_id):
        raise HTTPException(status_code=409, detail="任务状态已变化，请刷新后重试")
    return {"job_id": replacement_id, "status": "queued", "message_zh": "已重新加入目的地导出队列"}


@app.post("/v1/destinations/obsidian-local/receipts", status_code=202, dependencies=[Depends(require_token)])
def record_local_obsidian_receipt(request: LocalObsidianReceiptRequest) -> dict[str, Any]:
    """Persist a paired Chrome-to-loopback Obsidian projection receipt.

    The API cannot itself inspect a user's local Vault.  It records a bounded,
    paired-client attestation without mixing this target with server-side Obsidian
    Vault/REST bindings, which may refer to a different Vault entirely.
    """
    content = store.get_content(request.content_id)
    if not content:
        raise HTTPException(status_code=404, detail="内容不存在")
    remote_path = _safe_local_obsidian_path(request.remote_path)
    if request.status in {"done", "noop"} and not remote_path:
        raise HTTPException(status_code=422, detail="成功的 Obsidian 本机回执必须包含目标路径")
    projection_sha256 = sha256_bytes(_markdown(content).encode("utf-8"))
    destination_id = "obsidian_local"
    attempted_at = utcnow()
    remote_id = request.content_id if remote_path else None
    if request.status in {"done", "noop"}:
        store.upsert_destination_binding(
            destination_id=destination_id,
            content_id=request.content_id,
            projection_sha256=projection_sha256,
            remote_id=remote_id,
            remote_path=remote_path,
            metadata={"mode": "chrome_loopback", "attested": True},
        )
    message_zh = {
        "done": "Obsidian 本机桥接已写入并回传回执。",
        "noop": "Obsidian 本机桥接内容未变化，未重复写入。",
        "failed": "Obsidian 本机桥接失败；请打开 Obsidian 后在扩展任务中心重试。",
    }[request.status]
    receipt_id = store.record_destination_receipt(
        destination_id=destination_id,
        content_id=request.content_id,
        status=request.status,
        projection_sha256=projection_sha256,
        attempted_at=attempted_at,
        message_zh=message_zh,
        remote_id=remote_id,
        remote_path=remote_path,
        error_code="OBSIDIAN_LOCAL_BRIDGE_FAILED" if request.status == "failed" else None,
        evidence={
            "attested": True,
            "bridge": "chrome_loopback",
            "retryable": request.status == "failed",
        },
    )
    return {
        "receipt_id": receipt_id,
        "content_id": request.content_id,
        "destination_id": destination_id,
        "status": request.status,
        "retryable": request.status == "failed",
    }


@app.post("/v1/library/{content_id}/export", status_code=202, dependencies=[Depends(require_token)])
def export_content(content_id: str, request: ExportRequest) -> dict[str, Any]:
    if not store.get_content(content_id):
        raise HTTPException(404, "内容不存在")
    allowed = set(destinations.known_destination_ids())
    requested_ids = list(dict.fromkeys(item.lower() for item in request.destination_ids if item.lower() in allowed and item.lower() != "social_archive"))
    ids = [destination_id for destination_id in requested_ids if destinations.is_export_authorized(destination_id)]
    skipped_destination_ids = [destination_id for destination_id in requested_ids if destination_id not in ids]
    job_ids = [store.enqueue_job("export_destination", {"content_id": content_id, "destination_id": destination_id}, connector_id=destination_id) for destination_id in ids]
    return {
        "content_id": content_id,
        "destination_ids": ids,
        "skipped_destination_ids": skipped_destination_ids,
        "job_ids": job_ids,
    }


@app.get("/v1/library/{content_id}/markdown", dependencies=[Depends(require_token)])
def export_markdown(content_id: str) -> PlainTextResponse:
    content = store.get_content(content_id)
    if not content:
        raise HTTPException(404, "内容不存在")
    return PlainTextResponse(_markdown(content), media_type="text/markdown; charset=utf-8")


@app.get("/v1/library", dependencies=[Depends(require_token)])
def library(
    q: str | None = None,
    platform: str | None = None,
    relation: str | None = None,
    topic: str | None = None,
    collection: str | None = None,
    archive_status: str | None = Query(default=None, alias="archive"),
    after: str | None = Query(default=None),
    observed_from: str | None = None,
    observed_to: str | None = None,
    sort_by: str = Query(default="time"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    start = _observed_bound(observed_from, end_of_day=False)
    end = _observed_bound(observed_to, end_of_day=True)
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="开始时间不得晚于结束时间")
    return store.list_library_table(
        q=q,
        platform=platform,
        relation=relation,
        topic=topic,
        collection=collection,
        archive_status=archive_status,
        after=after,
        observed_from=start,
        observed_to=end,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/search", dependencies=[Depends(require_token)])
def search(q: str = Query(min_length=1), limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"items": store.list_library(q=q, limit=limit)}


@app.get("/v1/library/{content_id}", dependencies=[Depends(require_token)])
def detail(content_id: str) -> dict[str, Any]:
    row = store.get_content(content_id)
    if not row:
        raise HTTPException(status_code=404, detail="内容不存在")
    return row


@app.get("/v1/storage/status", dependencies=[Depends(require_token)])
def storage_status() -> dict[str, Any]:
    decision = service.quota.evaluate_local_staging()
    return {"items": store.quota_states(), "replicas": store.replica_summary(), "completion": store.replication_completion(), "l3_allowed": decision.allow_l3, "message_zh": decision.message_zh}


@app.get("/v1/status-projection", dependencies=[Depends(require_token)])
def status_projection() -> dict[str, Any]:
    connector_items = registry.health_views(store.connector_states())
    overall = "healthy" if all(item["state"] == "healthy" for item in connector_items) else "degraded"
    return {
        "project": "Social Archive",
        "version": __version__,
        "generated_at": utcnow(),
        "overall": overall,
        "connectors": connector_items,
        "destinations": destinations.views(),
        "storage": store.quota_states(),
        "replicas": store.replica_summary(),
        "recovery": {"last_backup": "unknown", "last_restore_drill": "unknown"},
    }


pwa_root = settings.pwa_root
extension_package = Path(
    os.getenv(
        "SOCIAL_ARCHIVE_EXTENSION_PACKAGE",
        str(Path(__file__).resolve().parents[2] / "dist" / "social-archive-extension.zip"),
    )
).resolve()


@app.get("/downloads/social-archive-extension.zip")
def download_browser_extension() -> FileResponse:
    if not extension_package.is_file():
        raise HTTPException(status_code=503, detail="浏览器插件安装包尚未生成，请稍后重试")
    payload = extension_package.read_bytes()
    return FileResponse(
        extension_package,
        media_type="application/zip",
        filename=f"social-archive-extension-v{__version__}.zip",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Social-Archive-SHA256": sha256_bytes(payload),
        },
    )


if pwa_root.exists():
    app.mount("/assets", StaticFiles(directory=pwa_root), name="assets")

    @app.get("/")
    def pwa_index() -> FileResponse:
        return FileResponse(pwa_root / "index.html")

    @app.get("/extension-install")
    def extension_install_guide() -> FileResponse:
        return FileResponse(pwa_root / "extension-install.html")

    @app.get("/item/{content_id}")
    def pwa_item(content_id: str) -> FileResponse:
        return FileResponse(pwa_root / "index.html")


def run() -> None:
    uvicorn.run("social_archive.api:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower(), proxy_headers=True)


if __name__ == "__main__":
    run()
