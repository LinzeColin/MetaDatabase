"""公开数据面的 FastAPI 应用工厂。"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import DatabaseUnavailable, PublicDatabase
from .events import BadFilter
from .routes import PublicContext, health_router, router
from .settings import PublicSettings, get_public_settings
from .stats import SurfaceStatsService

log = logging.getLogger("eei.public")


def create_public_app(settings: PublicSettings | None = None, *, warm_up: bool = True) -> FastAPI:
    settings = settings or get_public_settings()
    app = FastAPI(
        title="EEI public publication surface",
        version=settings.build_sha,
        # 公开面不挂自动文档：路由表以 worker.mjs 为契约，不另开一份对外说明。
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    db = PublicDatabase(settings)
    stats = SurfaceStatsService(
        db,
        surface_ttl=settings.surface_stats_ttl_seconds,
        light_ttl=settings.pulse_ttl_seconds,
    )
    app.state.public = PublicContext(settings=settings, db=db, stats=stats)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_allow_origin],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type"],
    )

    @app.middleware("http")
    async def edge_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        # 数据接口一律不缓存：前置 nginx 自己决定缓存多久，这里不让浏览器替它缓存 404。
        response.headers.setdefault("cache-control", "no-store")
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        response.headers["x-eei-build"] = settings.build_sha
        return response

    @app.exception_handler(DatabaseUnavailable)
    async def database_unavailable(_request: Request, exc: DatabaseUnavailable) -> JSONResponse:
        log.warning("database unavailable: %s", exc)
        return JSONResponse({"detail": "database unavailable"}, status_code=503)

    @app.exception_handler(BadFilter)
    async def bad_filter(_request: Request, exc: BadFilter) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())
        log.exception("unhandled error request_id=%s", request_id, exc_info=exc)
        # 不把内部错误原文带给调用方（与 Worker 的失败闭合边界一致）。
        return JSONResponse({"detail": "internal error", "request_id": request_id}, status_code=500)

    app.include_router(health_router)
    app.include_router(router)

    if warm_up and settings.database_url:
        stats.warm_up()
    return app
