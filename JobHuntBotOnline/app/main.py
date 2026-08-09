from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import seed_admin
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.routers import auth, dashboard, health, jobs, profile, resumes, settings as settings_router
from app.services.backup import create_backup
from app.services.canonical import canonical_is_dirty, export_canonical
from app.services.data_migration import migrate_sensitive_storage
from app.web import render


settings = get_settings()
logger = logging.getLogger("jobhuntos")


async def _maintenance_loop(stop: asyncio.Event) -> None:
    """Keep local snapshots current without relying on an active Agent session."""
    last_backup: datetime | None = None
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                if canonical_is_dirty(db):
                    export_canonical(db)
                latest_backup = max(
                    (path.stat().st_mtime for path in (settings.data_dir / "backups").glob("*.jhbbackup")),
                    default=0,
                )
                last_backup = datetime.fromtimestamp(latest_backup, tz=timezone.utc) if latest_backup else None
                due = not last_backup or datetime.now(timezone.utc) - last_backup >= timedelta(
                    hours=max(1, settings.automatic_backup_hours)
                )
                if due:
                    create_backup(db)
        except Exception:
            logger.exception("maintenance_cycle_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=300)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        migrate_sensitive_storage(db)
        seed_admin(db)
    stop = asyncio.Event()
    task = (
        asyncio.create_task(_maintenance_loop(stop), name="jobhuntos-maintenance")
        if settings.maintenance_enabled
        else None
    )
    app.state.started_at = datetime.now(timezone.utc)
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    max_age=settings.session_max_age_seconds,
    same_site="lax",
    https_only=settings.cookie_secure,
    session_cookie="jobhuntos_session",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
    )
    if settings.cookie_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path not in {"/healthz", "/readyz", "/api/status"}:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        target = request.url.path
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(url=f"/login?next={quote(target, safe='/?:=&')}", status_code=303)
    user = None
    try:
        user_id = request.session.get("user_id")
        if user_id:
            with SessionLocal() as db:
                from app.models import User

                user = db.get(User, user_id)
    except Exception:
        user = None
    return render(
        request,
        "error.html",
        user=user,
        status_code=exc.status_code,
        error_title="操作未完成",
        error_message=str(exc.detail),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_request_error", exc_info=exc)
    return render(
        request,
        "error.html",
        user=None,
        status_code=500,
        error_title="系统暂时无法完成这个操作",
        error_message="现有数据没有被删除。请返回上一页重试；若持续发生，请运行部署诊断。",
    )


static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(settings_router.router)
app.include_router(dashboard.router)
