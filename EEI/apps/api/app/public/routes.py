"""公开数据面路由：路径、方法、请求体、响应字段与 worker.mjs 一致。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from scripts.publish_to_cloud_channel import active_analysis_context_payload

from ..domain_repository import CatalogRepository, NotFoundError, RepositoryError
from . import events as events_mod
from . import modules
from .db import PublicDatabase
from .gate import parse_uuid
from .graph import GRAPH_HARD_LIMITS, explore_graph, normalize_budget, normalize_direction
from .settings import PublicSettings
from .stats import (
    GRAPH_QUERY_VERSION,
    SurfaceStatsService,
    build_pulse,
    production_context,
    publication_meta,
    sources_freshness,
)

log = logging.getLogger("eei.public")

router = APIRouter(prefix="/v1")

# 个人状态、本地流水线与任何写入：公开部署一律不提供（读也不行——saved_views 等表里是个人数据）。
DENIED_PREFIXES = (
    "saved-views",
    "watchlists",
    "exploration-log",
    "cloud",
    "calibrations",
    "internal",
    "audit-logs",
    "data",
    "export",
)
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class PublicContext:
    settings: PublicSettings
    db: PublicDatabase
    stats: SurfaceStatsService


def _ctx(request: Request) -> PublicContext:
    return request.app.state.public


def _stats(request: Request, *, block: bool):
    ctx = _ctx(request)
    return ctx.stats.light.get(block=block), ctx.stats.surface.get(block=block)


def _explore_context(request: Request, as_of: Any) -> dict[str, Any]:
    light, surface = _stats(request, block=False)
    return production_context(light, surface, as_of)


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


# -- 健康与元信息 ---------------------------------------------------------------


def build_info(settings: PublicSettings) -> dict[str, Any]:
    return {
        "repo": "LinzeColin/MetaDatabase",
        "commit": settings.build_sha,
        "built_at": settings.build_time,
        "deploy_id": settings.deploy_id,
    }


health_router = APIRouter()


@health_router.get("/health")
def health(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    database = ctx.db.health()
    light = ctx.stats.light.peek()
    body = {
        "status": "ok" if database["ok"] else "degraded",
        "surface": "selfhost_publication",
        "snapshot_key": light.snapshot["snapshot_key"] if light and light.snapshot else None,
        "graph_query_version": GRAPH_QUERY_VERSION,
        "build": build_info(ctx.settings),
        "database": database,
    }
    return JSONResponse(body, status_code=200 if database["ok"] else 503)


@router.get("/publication/meta")
def get_publication_meta(request: Request) -> dict[str, Any]:
    light, surface = _stats(request, block=True)
    return {
        "publication_meta": publication_meta(light, surface),
        "snapshot": light.snapshot,
        "published_relationship_count": surface.published_relationship_count,
    }


@router.get("/meta/build")
def get_meta_build(request: Request) -> dict[str, Any]:
    ctx = _ctx(request)
    surface = ctx.stats.surface.peek()
    return {
        **build_info(ctx.settings),
        "publisher_version": "eei-selfhost-api-v1",
        "published_at": surface.computed_at if surface else None,
    }


@router.get("/meta/pulse")
def get_pulse(request: Request) -> dict[str, Any]:
    try:
        days = int(request.query_params.get("days", "60"))
    except ValueError:
        days = 60
    light, surface = _stats(request, block=True)
    return build_pulse(light, surface, days=days)


@router.get("/sources/freshness")
def get_sources_freshness(request: Request) -> dict[str, Any]:
    light, _ = _stats(request, block=True)
    return sources_freshness(light)


@router.get("/scoring/active-context")
def get_active_context(
    request: Request, client_refresh_token: Annotated[str | None, Query()] = None
) -> dict[str, Any]:
    with _ctx(request).db.connection() as conn:
        context = active_analysis_context_payload(conn)
    if context is None:
        raise _not_found("no active analysis context is available")
    state = (
        "stale"
        if client_refresh_token is not None and client_refresh_token != context["refresh_token"]
        else "current"
    )
    return {
        **context,
        "client_state": state,
        "stale_client_semantics": (
            "Clients with a different refresh_token must discard cached graph, score, model and"
            " module state and refetch the active context."
        ),
    }


@router.get("/scoring/profiles")
def get_scoring_profiles(request: Request) -> list[dict[str, Any]]:
    with _ctx(request).db.connection() as conn:
        return modules.scoring_profiles(conn)


@router.get("/catalogs")
def get_catalogs() -> dict[str, Any]:
    return CatalogRepository().list_catalogs()


@router.get("/catalogs/{catalog_key}", response_model=None)
def get_catalog(
    catalog_key: str, format: Annotated[Literal["json", "csv"], Query()] = "json"
) -> dict[str, Any] | FileResponse:
    repository = CatalogRepository()
    try:
        if format == "csv":
            path = repository.csv_path_for_key(catalog_key)
            return FileResponse(path, media_type="text/csv", filename=path.name)
        return repository.get_catalog(catalog_key)
    except NotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# -- 实体 -----------------------------------------------------------------------


@router.get("/entities")
def get_entities(request: Request) -> dict[str, Any]:
    q = request.query_params.get("q", "")
    if not q.strip():
        raise HTTPException(status_code=400, detail="q query parameter is required")
    limit = events_mod.clamp_limit(request.query_params.get("limit"), default=20, ceiling=50)
    with _ctx(request).db.connection() as conn:
        return modules.search_entities(conn, q, limit)


@router.get("/entities/{entity_id}/empire")
def get_empire(request: Request, entity_id: str) -> dict[str, Any]:
    parsed = parse_uuid(entity_id)
    light, _ = _stats(request, block=False)
    with _ctx(request).db.connection() as conn:
        body = modules.entity_empire(conn, parsed, light) if parsed else None
    if body is None:
        raise _not_found(f"Entity not found: {entity_id}")
    return body


# -- 图谱探索 -------------------------------------------------------------------


def _run_explore(request: Request, focus_id: Any, **kwargs: Any) -> dict[str, Any]:
    parsed = parse_uuid(focus_id)
    body = None
    if parsed is not None:
        with _ctx(request).db.connection() as conn:
            body = explore_graph(
                conn,
                focus_entity_id=parsed,
                context=_explore_context(request, kwargs.get("as_of")),
                **kwargs,
            )
    if body is None:
        raise _not_found(f"Entity not found: {focus_id}")
    return body


def _common(body: dict[str, Any]) -> dict[str, Any]:
    layers = body.get("active_layers")
    return {
        "active_layers": layers if isinstance(layers, list) else [],
        "filters": body.get("filters") or {},
        "as_of": body.get("as_of"),
    }


@router.post("/explore")
async def post_explore(request: Request) -> dict[str, Any]:
    body = await _json_body(request)
    focus = body.get("focus") if isinstance(body.get("focus"), dict) else {}
    focus_id = focus.get("object_id")
    if not focus_id:
        raise HTTPException(status_code=400, detail="focus.object_id is required")
    return await run_in_threadpool(
        _run_explore,
        request,
        focus_id,
        session_id=body.get("session_id"),
        direction=normalize_direction(body.get("direction")),
        hops=body.get("hops"),
        budget=normalize_budget(body.get("budget")),
        **_common(body),
    )


@router.post("/explore/reroot")
async def post_reroot(request: Request) -> dict[str, Any]:
    body = await _json_body(request)
    new_focus = body.get("new_focus_entity_id")
    if not new_focus:
        raise HTTPException(status_code=400, detail="new_focus_entity_id is required")
    return await run_in_threadpool(
        _run_explore,
        request,
        new_focus,
        session_id=body.get("session_id") or str(uuid.uuid4()),
        direction=normalize_direction(body.get("direction", "both")),
        hops=body.get("hops", 1),
        budget=normalize_budget(body.get("budget")),
        **_common(body),
    )


@router.post("/explore/expand")
async def post_expand(request: Request) -> dict[str, Any]:
    body = await _json_body(request)
    anchor = body.get("anchor_entity_id")
    if not anchor:
        raise HTTPException(status_code=400, detail="anchor_entity_id is required")
    budget = normalize_budget(body.get("budget"))
    budget["max_nodes"] = min(budget["expand_nodes"], GRAPH_HARD_LIMITS["max_nodes"])
    return await run_in_threadpool(
        _run_explore,
        request,
        anchor,
        session_id=body.get("session_id") or str(uuid.uuid4()),
        direction=normalize_direction(body.get("direction", "both")),
        hops=1,
        budget=budget,
        **_common(body),
    )


# -- 证据与评分解释 -------------------------------------------------------------


@router.get("/evidence/relationship/{relationship_id}")
def get_relationship_evidence(request: Request, relationship_id: str) -> dict[str, Any]:
    parsed = parse_uuid(relationship_id)
    with _ctx(request).db.connection() as conn:
        body = modules.relationship_evidence(conn, parsed) if parsed else None
    if body is None:
        raise _not_found(f"Relationship not found: {relationship_id}")
    return body


@router.get("/evidence/event/{event_id}")
def get_event_evidence(
    request: Request, event_id: str, limit: Annotated[str | None, Query()] = None
) -> dict[str, Any]:
    parsed = parse_uuid(event_id)
    with _ctx(request).db.connection() as conn:
        body = events_mod.event_evidence(conn, parsed, limit) if parsed else None
    if body is None:
        raise _not_found(f"Event not found: {event_id}")
    return body


@router.get("/scoring/relationship/{relationship_id}/explanation")
def get_relationship_explanation(request: Request, relationship_id: str) -> dict[str, Any]:
    parsed = parse_uuid(relationship_id)
    light, surface = _stats(request, block=False)
    with _ctx(request).db.connection() as conn:
        body = modules.score_explanation(conn, parsed, light, surface) if parsed else None
    if body is None:
        raise _not_found(f"Relationship not found: {relationship_id}")
    return body


# -- 资本河事件 -----------------------------------------------------------------

_EVENT_FILTERS = ("entity", "theme", "from", "to", "event_type", "currency", "amount_kind")


def _event_params(request: Request) -> tuple[dict[str, str | None], int]:
    q = request.query_params
    params = {name: q.get(name) for name in _EVENT_FILTERS}
    return params, events_mod.clamp_limit(q.get("limit"))


@router.get("/events")
def get_events(request: Request) -> list[dict[str, Any]]:
    params, limit = _event_params(request)
    with _ctx(request).db.connection() as conn:
        return events_mod.list_events(conn, params, limit)


@router.get("/events/amount-summary")
def get_event_amount_summary(request: Request) -> dict[str, Any]:
    params, limit = _event_params(request)
    with _ctx(request).db.connection() as conn:
        return events_mod.amount_summary(conn, params, limit)


# -- 模块概览与变更流 -----------------------------------------------------------


@router.get("/control/overview")
def get_control_overview(request: Request) -> dict[str, Any]:
    with _ctx(request).db.connection() as conn:
        return modules.control_overview(conn)


@router.get("/ma/overview")
def get_ma_overview(request: Request) -> dict[str, Any]:
    with _ctx(request).db.connection() as conn:
        return modules.ma_overview(conn)


@router.get("/signals/overview")
def get_signals_overview(request: Request) -> dict[str, Any]:
    with _ctx(request).db.connection() as conn:
        return modules.signals_overview(conn)


@router.get("/policy/overview")
def get_policy_overview(request: Request) -> dict[str, Any]:
    light, _ = _stats(request, block=True)
    with _ctx(request).db.connection() as conn:
        return modules.policy_overview(conn, light)


@router.get("/supply-chain/overview")
def get_supply_chain_overview(request: Request) -> dict[str, Any]:
    light, _ = _stats(request, block=True)
    with _ctx(request).db.connection() as conn:
        return modules.supply_chain_overview(conn, light)


@router.get("/changes")
def get_changes(
    request: Request, since: Annotated[str | None, Query()] = None
) -> list[dict[str, Any]]:
    try:
        parsed = modules.parse_since(since)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="since must be an ISO-8601 timestamp") from exc
    with _ctx(request).db.connection() as conn:
        return modules.list_changes(conn, parsed)


# -- 兜底：写入 / 个人状态 / 不存在的路由 ---------------------------------------


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    include_in_schema=False,
)
def fallback(request: Request, path: str) -> JSONResponse:
    settings = _ctx(request).settings
    first = path.split("/", 1)[0]
    if request.method not in READ_METHODS or first in DENIED_PREFIXES or path.startswith(
        "scoring/profiles/"
    ):
        if settings.write_route_mode == "hidden":
            return JSONResponse(
                {"detail": f"No public route for {request.method} /v1/{path}"}, status_code=404
            )
        return JSONResponse(
            {
                "detail": (
                    "This route is disabled on the public deployment (read-only publication"
                    " surface)."
                )
            },
            status_code=403,
        )
    return JSONResponse(
        {"detail": f"No public route for {request.method} /v1/{path}"}, status_code=404
    )
