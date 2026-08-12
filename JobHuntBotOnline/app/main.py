from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai
from .config import Settings, get_settings
from .db import Base, make_engine, make_session_factory, session_dependency
from .discovery import clean_html, claim_run, enqueue_discovery, process_run, rescore_existing_recommendations, safe_http_url
from .email_service import MailRateLimited, Mailer
from .models import (
    ApplicationEvent, ApplicationPack, CandidateProfile, DiscoveryRun, DiscoverySourceStatus,
    Job, Recommendation, Resume, User, utcnow,
)
from .resume import ResumeError, extract_text
from .scoring import search_matches
from .security import (
    CryptoBox, check_csrf, create_session, email_lookup, hash_password, mask_email,
    normalize_email, rate_limit, resolve_session, revoke_all_sessions, revoke_session,
    validate_password, verify_password,
)
from .services import (
    application_progress_error, application_progress_for_user, audit, build_application_materials,
    build_application_pack, consult_application_materials, create_application_progress,
    delete_user_account, ensure_application_materials, get_profile, get_profile_row,
    list_application_progresses, list_experiences, list_resumes, manual_job,
    recommendation_for_user, save_profile, store_resume, update_application_materials,
    update_application_progress, user_export,
)

SESSION_COOKIE = "jobhunt_session"
CSRF_COOKIE = "jobhunt_csrf"
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
STATIC_ROOT = Path(__file__).parent / "static"


def _static_asset_revision() -> str:
    digest = hashlib.sha256()
    for asset in ("app.css", "app.js"):
        digest.update((STATIC_ROOT / asset).read_bytes())
    return digest.hexdigest()[:12]


STATIC_ASSET_REVISION = _static_asset_revision()


def _csv_list(value: str) -> list[str]:
    return [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]


SPONSORSHIP_VALUES = {"yes", "no", "uncertain"}
WORK_MODE_VALUES = {"remote", "hybrid", "onsite"}
APPLICATION_STATUS_LABELS = {
    "pending": "待处理",
    "submitted": "已提交",
    "interview": "面试／笔试",
    "rejected": "已拒绝",
    "offer": "Offer",
    "withdrawn": "已撤回",
}


def _confirmed_profile_fields(
    *,
    primary_roles: str,
    target_locations: str,
    work_authorization: str,
    sponsorship_now: str,
    sponsorship_future: str,
    work_modes: list[str],
    relocation: str,
    available_start: str,
    avoid_roles: str,
    avoid_industries: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Accept only facts that the user has explicitly confirmed in this form."""
    roles = _csv_list(primary_roles)
    locations = _csv_list(target_locations)
    authorization = work_authorization.strip()
    now = sponsorship_now.strip().casefold()
    future = sponsorship_future.strip().casefold()
    modes = list(dict.fromkeys(value.strip().casefold() for value in work_modes if value.strip()))
    relocation_value = relocation.strip().casefold()
    if not roles:
        return None, "请明确至少一个目标岗位族。"
    if not locations:
        return None, "请明确至少一个目标城市或地区。"
    if not authorization:
        return None, "请填写当前工作权利；如不确定请明确填写“不确定”。"
    if now not in SPONSORSHIP_VALUES or future not in SPONSORSHIP_VALUES:
        return None, "请明确现在和未来是否需要 Sponsorship。"
    if not modes:
        return None, "请至少选择一种可接受的工作模式。"
    if any(value not in WORK_MODE_VALUES for value in modes):
        return None, "工作模式包含无效值。"
    if relocation_value not in {"", "yes", "no"}:
        return None, "搬迁偏好无效。"
    return {
        "primary_role_families": roles,
        "target_locations": locations,
        "work_authorization": authorization,
        "sponsorship_now": now,
        "sponsorship_future": future,
        "work_mode": modes,
        "relocation": relocation_value,
        "available_start": available_start.strip(),
        "avoid_roles": _csv_list(avoid_roles),
        "avoid_industries": _csv_list(avoid_industries),
    }, None


def _query_url(path: str, **params: str) -> str:
    filtered = {k: v for k, v in params.items() if v}
    if not filtered:
        return path
    return f"{path}{'&' if '?' in path else '?'}{urlencode(filtered)}"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    get_db = session_dependency(factory)
    crypto = CryptoBox(settings.data_encryption_key)
    mailer = Mailer(settings, crypto)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        settings.upload_root.mkdir(parents=True, exist_ok=True)
        settings.backup_root.mkdir(parents=True, exist_ok=True)
        if settings.app_env != "production":
            Base.metadata.create_all(engine)
        with factory() as db:
            _bootstrap_admin(db, settings, crypto)
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.crypto = crypto
    app.state.mailer = mailer
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.middleware("http")
    async def auth_and_security(request: Request, call_next):
        request.state.user = None
        request.state.user_session = None
        raw = request.cookies.get(SESSION_COOKIE)
        if raw:
            with factory() as db:
                user, user_session = resolve_session(db, raw)
                request.state.user = user
                request.state.user_session = user_session
        request.state.anon_csrf = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(24)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self' https://static.cloudflareinsights.com; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE,
                request.state.anon_csrf,
                httponly=False,
                secure=settings.cookie_secure,
                samesite="strict",
                max_age=settings.session_max_age_seconds,
            )
        return response

    def _csrf(request: Request) -> str:
        if request.state.user_session:
            return request.state.user_session.csrf_token
        return request.state.anon_csrf

    def _require_csrf(request: Request, submitted: str) -> None:
        expected = _csrf(request)
        if not submitted or not secrets.compare_digest(expected, submitted):
            raise HTTPException(403, "页面已过期，请刷新后重试。")

    def _require_user(request: Request) -> User:
        user = request.state.user
        if not user:
            raise HTTPException(401, "请先登录。")
        if not user.is_verified:
            raise HTTPException(403, "请先验证邮箱。")
        return user

    def _require_admin(request: Request) -> User:
        user = _require_user(request)
        if not user.is_admin:
            raise HTTPException(403, "只有平台管理员可以访问。")
        return user

    def _render(request: Request, name: str, context: dict[str, Any] | None = None, status_code: int = 200):
        context = context or {}
        context.update({
            "request": request,
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "static_revision": STATIC_ASSET_REVISION,
            "user": request.state.user,
            "csrf_token": _csrf(request),
            "registration_open": settings.allow_registration,
            "email_delivery_ready": settings.testing or settings.app_env != "production" or bool(settings.smtp_host),
            "message": request.query_params.get("message", ""),
            "error": request.query_params.get("error", ""),
        })
        return TEMPLATES.TemplateResponse(request=request, name=name, context=context, status_code=status_code)

    def _redirect(path: str, *, message: str = "", error: str = "", status_code: int = 303):
        return RedirectResponse(_query_url(path, message=message, error=error), status_code=status_code)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            return _redirect("/login", error=str(exc.detail), status_code=303)
        return _render(request, "error.html", {"status": exc.status_code, "detail": str(exc.detail)}, exc.status_code)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "version": settings.app_version}

    @app.get("/readyz")
    def readyz(db: Session = Depends(get_db)):
        db.scalar(select(func.count(User.id)))
        return {"status": "ready", "refresh_hours": settings.discovery_refresh_hours}

    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request):
        if request.state.user and request.state.user.is_verified:
            return _redirect("/dashboard")
        return _render(request, "landing.html", {"registration_open": settings.allow_registration})

    @app.get("/owner-entry", response_class=HTMLResponse, include_in_schema=False)
    def owner_entry_page(request: Request):
        if not settings.owner_entry_enabled:
            raise HTTPException(404, "资源不存在。")
        if request.state.user and request.state.user.is_admin and request.state.user.is_verified:
            return _redirect("/dashboard")
        return _render(request, "owner_entry.html")

    @app.post("/owner-entry", include_in_schema=False)
    def owner_entry(
        request: Request,
        password: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        if not settings.owner_entry_enabled:
            raise HTTPException(404, "资源不存在。")
        _require_csrf(request, csrf_token)
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(db, key=f"owner-entry:{ip}", limit=5, window_seconds=900):
            return _redirect("/owner-entry", error="尝试次数过多，请 15 分钟后再试。")
        owner = db.scalar(select(User).where(
            User.email_lookup == email_lookup(settings.admin_email, settings.email_lookup_secret),
        ))
        if (
            not owner
            or not owner.is_active
            or not owner.is_admin
            or not settings.owner_entry_password
            or not secrets.compare_digest(settings.owner_entry_password, password)
        ):
            return _redirect("/owner-entry", error="Owner 入口密码不正确或当前不可用。")
        # This is deliberately limited to the pre-provisioned platform Owner.
        # It creates an ordinary authenticated session but never registers a
        # user, changes verification state, or invokes SMTP.
        raw, _session = create_session(db, owner, settings)
        owner.last_login_at = utcnow()
        db.commit()
        audit(db, "owner_entry_login", owner.id)
        profile = get_profile_row(db, owner.id)
        target = "/dashboard" if profile and profile.onboarding_state == "complete" else "/onboarding/upload"
        response = _redirect(target, message="Owner 入口已打开；无需邮箱验证。")
        response.set_cookie(
            SESSION_COOKIE, raw, httponly=True, secure=settings.cookie_secure,
            samesite="lax", max_age=settings.session_max_age_seconds,
        )
        return response

    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request):
        if not settings.allow_registration:
            raise HTTPException(403, "当前未开放注册。")
        return _render(request, "register.html")

    @app.post("/register")
    def register(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        password_confirm: str = Form(...),
        display_name: str = Form(""),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        if not settings.allow_registration:
            raise HTTPException(403, "当前未开放注册。")
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(db, key=f"register:{ip}", limit=8, window_seconds=3600):
            return _redirect("/register", error="尝试次数过多，请稍后再试。")
        normalized = normalize_email(email)
        if "@" not in normalized or len(normalized) > 254:
            return _redirect("/register", error="请输入有效邮箱。")
        password_error = validate_password(password)
        if password_error:
            return _redirect("/register", error=password_error)
        if password != password_confirm:
            return _redirect("/register", error="两次输入的密码不一致。")
        lookup = email_lookup(normalized, settings.email_lookup_secret)
        if db.scalar(select(User).where(User.email_lookup == lookup)):
            return _redirect("/login", message="该邮箱已注册，请直接登录或找回密码。")
        user = User(
            email_lookup=lookup,
            email_encrypted=crypto.encrypt_text(normalized),
            display_name_encrypted=crypto.encrypt_text(display_name.strip()) if display_name.strip() else None,
            password_hash=hash_password(password),
            is_verified=False,
            daily_ai_request_limit=settings.deepseek_default_user_request_limit,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        save_profile(db, crypto, user.id, {}, onboarding_state="needs_resume", discovery_enabled=False)
        try:
            mailer.send_verification(db, user)
        except MailRateLimited:
            audit(db, "user_registered_email_deferred", user.id)
            return _redirect("/verify-required", message="账户已创建；验证邮件受发送保护，暂未发出，请稍后重试。")
        audit(db, "user_registered", user.id)
        return _redirect("/verify-required", message="验证邮件已发送，请打开邮箱完成验证。")

    @app.get("/verify-required", response_class=HTMLResponse)
    def verify_required(request: Request):
        return _render(request, "verify_required.html")

    @app.get("/verify-email", response_class=HTMLResponse)
    def verify_email_page(request: Request, token: str, db: Session = Depends(get_db)):
        # Opening an email link is deliberately non-mutating. Mail gateway
        # scanners fetch links before the recipient does, so consuming the
        # token on GET would make a real recipient see an unusable link.
        if not mailer.token_is_active(db, token, "verify"):
            return _redirect(
                "/resend-verification",
                error="验证链接无效、已过期或已被使用。若你刚刚完成验证，请直接登录；否则请在限速结束后手动申请新链接。",
            )
        response = _render(request, "verify_email.html", {"token": token})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/verify-email")
    def verify_email(
        request: Request,
        token: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = mailer.consume_token(db, token, "verify")
        if not user:
            return _redirect(
                "/resend-verification",
                error="验证链接无效、已过期或已被使用。若你刚刚完成验证，请直接登录；否则请在限速结束后手动申请新链接。",
            )
        user.is_verified = True
        user.verified_at = utcnow()
        db.commit()
        raw, session = create_session(db, user, settings)
        audit(db, "email_verified", user.id)
        response = _redirect("/onboarding/upload", message="邮箱验证成功。现在只需上传简历。")
        response.set_cookie(
            SESSION_COOKIE, raw, httponly=True, secure=settings.cookie_secure,
            samesite="lax", max_age=settings.session_max_age_seconds,
        )
        return response

    @app.get("/resend-verification", response_class=HTMLResponse)
    def resend_page(request: Request):
        if settings.app_env == "production" and not settings.smtp_host:
            raise HTTPException(503, "邮件服务正在配置中，请稍后再试。")
        return _render(request, "resend_verification.html")

    @app.post("/resend-verification")
    def resend_verification(
        request: Request,
        email: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        if settings.app_env == "production" and not settings.smtp_host:
            raise HTTPException(503, "邮件服务正在配置中，请稍后再试。")
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(db, key=f"resend:{ip}", limit=5, window_seconds=3600):
            return _redirect("/resend-verification", error="请求过于频繁，请稍后再试。")
        lookup = email_lookup(email, settings.email_lookup_secret)
        user = db.scalar(select(User).where(User.email_lookup == lookup))
        if user and user.is_active and not user.is_verified:
            try:
                mailer.send_verification(db, user)
            except MailRateLimited:
                pass
        return _redirect("/verify-required", message="如该邮箱需要验证，系统会在允许发送时处理请求。")

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return _render(request, "login.html")

    @app.post("/login")
    def login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        ip = request.client.host if request.client else "unknown"
        lookup = email_lookup(email, settings.email_lookup_secret)
        if not rate_limit(db, key=f"login:{ip}:{lookup[:12]}", limit=10, window_seconds=900):
            return _redirect("/login", error="登录尝试过多，请 15 分钟后再试。")
        user = db.scalar(select(User).where(User.email_lookup == lookup))
        if not user or not verify_password(user.password_hash, password):
            return _redirect("/login", error="邮箱或密码不正确。")
        if not user.is_active:
            return _redirect("/login", error="账户已停用，请联系管理员。")
        if not user.is_verified:
            return _redirect("/verify-required", error="请先验证邮箱。")
        raw, _session = create_session(db, user, settings)
        user.last_login_at = utcnow()
        db.commit()
        audit(db, "login", user.id)
        profile = get_profile_row(db, user.id)
        target = "/dashboard" if profile and profile.onboarding_state == "complete" else "/onboarding/upload"
        response = _redirect(target, message="登录成功。")
        response.set_cookie(
            SESSION_COOKIE, raw, httponly=True, secure=settings.cookie_secure,
            samesite="lax", max_age=settings.session_max_age_seconds,
        )
        return response

    @app.post("/logout")
    def logout(request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
        _require_csrf(request, csrf_token)
        user = request.state.user
        revoke_session(db, request.cookies.get(SESSION_COOKIE))
        if user:
            audit(db, "logout", user.id)
        response = _redirect("/", message="你已安全退出。")
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/forgot-password", response_class=HTMLResponse)
    def forgot_page(request: Request):
        if settings.app_env == "production" and not settings.smtp_host:
            raise HTTPException(503, "邮件找回正在配置中，请稍后再试。")
        return _render(request, "forgot_password.html")

    @app.post("/forgot-password")
    def forgot(
        request: Request,
        email: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        if settings.app_env == "production" and not settings.smtp_host:
            raise HTTPException(503, "邮件找回正在配置中，请稍后再试。")
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(db, key=f"forgot:{ip}", limit=6, window_seconds=3600):
            return _redirect("/forgot-password", error="请求过于频繁，请稍后再试。")
        user = db.scalar(select(User).where(User.email_lookup == email_lookup(email, settings.email_lookup_secret)))
        if user and user.is_active and user.is_verified:
            try:
                mailer.send_reset(db, user)
            except MailRateLimited:
                pass
            else:
                audit(db, "password_reset_requested", user.id)
        return _redirect("/login", message="如果邮箱已注册，系统会在允许发送时处理请求。")

    @app.get("/reset-password", response_class=HTMLResponse)
    def reset_page(request: Request, token: str):
        return _render(request, "reset_password.html", {"token": token})

    @app.post("/reset-password")
    def reset_password(
        request: Request,
        token: str = Form(...),
        password: str = Form(...),
        password_confirm: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        password_error = validate_password(password)
        if password_error:
            return _redirect(f"/reset-password?token={token}", error=password_error)
        if password != password_confirm:
            return _redirect(f"/reset-password?token={token}", error="两次密码不一致。")
        user = mailer.consume_token(db, token, "reset")
        if not user:
            return _redirect("/forgot-password", error="重置链接无效或已过期。")
        user.password_hash = hash_password(password)
        revoke_all_sessions(db, user)
        audit(db, "password_reset", user.id)
        return _redirect("/login", message="密码已重置，请使用新密码登录。")

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, db: Session = Depends(get_db)):
        user = _require_user(request)
        profile_row = get_profile_row(db, user.id)
        if not profile_row or profile_row.onboarding_state != "complete":
            return _redirect("/onboarding/upload")
        counts = {
            "recommendations": db.scalar(select(func.count(Recommendation.id)).where(Recommendation.user_id == user.id)) or 0,
            "saved": db.scalar(select(func.count(Recommendation.id)).where(Recommendation.user_id == user.id, Recommendation.user_status == "saved")) or 0,
            "applied": db.scalar(select(func.count(ApplicationEvent.id)).where(ApplicationEvent.user_id == user.id, ApplicationEvent.status == "submitted")) or 0,
        }
        latest_run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id).order_by(DiscoveryRun.created_at.desc()))
        return _render(request, "dashboard.html", {
            "counts": counts,
            "profile_row": profile_row,
            "latest_run": latest_run,
            "refresh_hours": settings.discovery_refresh_hours,
        })

    @app.get("/onboarding/upload", response_class=HTMLResponse)
    def onboarding_upload(request: Request, db: Session = Depends(get_db)):
        user = _require_user(request)
        return _render(request, "onboarding_upload.html", {"resumes": list_resumes(db, crypto, user.id)})

    @app.post("/onboarding/upload")
    async def onboarding_upload_post(
        request: Request,
        resume: UploadFile,
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        data = await resume.read()
        if len(data) > settings.max_upload_bytes:
            return _redirect("/onboarding/upload", error="文件超过 10MB，请压缩后重试。")
        try:
            text = extract_text(resume.filename or "resume", resume.content_type or "", data)
            _row, parsed = store_resume(
                db, crypto, settings, user_id=user.id, filename=resume.filename or "resume",
                content_type=resume.content_type or "application/octet-stream", data=data, text=text,
            )
        except ResumeError as exc:
            return _redirect("/onboarding/upload", error=str(exc))
        audit(db, "resume_uploaded", user.id, f"skills={len(parsed.get('skills', []))}")
        return _redirect("/onboarding/confirm", message="简历已整理。只需确认几项会影响推荐结果的信息。")

    @app.get("/onboarding/confirm", response_class=HTMLResponse)
    def onboarding_confirm(request: Request, db: Session = Depends(get_db)):
        user = _require_user(request)
        if not db.scalar(select(Resume).where(Resume.user_id == user.id)):
            return _redirect("/onboarding/upload", error="请先上传简历。")
        return _render(request, "onboarding_confirm.html", {"profile": get_profile(db, crypto, user.id)})

    @app.post("/onboarding/confirm")
    def onboarding_confirm_post(
        request: Request,
        primary_roles: str = Form(...),
        target_locations: str = Form(...),
        work_authorization: str = Form(...),
        sponsorship_now: str = Form(...),
        sponsorship_future: str = Form(...),
        work_modes: list[str] = Form([]),
        relocation: str = Form(""),
        available_start: str = Form(""),
        avoid_roles: str = Form(""),
        avoid_industries: str = Form(""),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        confirmed, error = _confirmed_profile_fields(
            primary_roles=primary_roles,
            target_locations=target_locations,
            work_authorization=work_authorization,
            sponsorship_now=sponsorship_now,
            sponsorship_future=sponsorship_future,
            work_modes=work_modes,
            relocation=relocation,
            available_start=available_start,
            avoid_roles=avoid_roles,
            avoid_industries=avoid_industries,
        )
        if error or confirmed is None:
            return _redirect("/onboarding/confirm", error=error or "关键事实尚未确认。")
        profile = get_profile(db, crypto, user.id)
        profile.update(confirmed)
        row = save_profile(db, crypto, user.id, profile, onboarding_state="complete", discovery_enabled=True)
        rescore_existing_recommendations(db, user.id, profile, crypto)
        row.next_discovery_at = utcnow()
        db.commit()
        run = enqueue_discovery(db, user.id, "onboarding")
        if settings.testing:
            process_run(db, run, settings, crypto)
        audit(db, "onboarding_completed", user.id)
        return _redirect("/recommendations", message="资料已保存，岗位发现已启动。系统每 6 小时自动刷新。")

    @app.post("/recommendations/refresh")
    def refresh_recommendations(
        request: Request,
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        if not rate_limit(db, key=f"manual-refresh:{user.id}", limit=4, window_seconds=3600):
            return _redirect("/recommendations", error="手动刷新过于频繁。系统每 6 小时会自动刷新。")
        run = enqueue_discovery(db, user.id, "manual")
        if settings.testing:
            process_run(db, run, settings, crypto)
            return _redirect("/recommendations", message="岗位已刷新。")
        return _redirect("/recommendations", message="刷新任务已进入队列，稍后自动更新。")

    def _recommendation_context(
        request: Request,
        db: Session,
        user: User,
        *,
        q: str,
        city: str,
        role: str,
        skill: str,
        source: str,
        freshness: str,
        qualification: str,
        relevance: str,
        opportunity: str,
        status: str,
    ) -> dict[str, Any]:
        active_filters = {key: value for key, value in request.query_params.items() if key != "partial"}
        # The default feed is deliberately high relevance only. An explicit
        # `relevance=` from the "全部" option remains available for users who
        # want to inspect the broader queue.
        if "relevance" not in active_filters:
            relevance = "high"
            active_filters["relevance"] = relevance
        rows = db.execute(
            select(Recommendation, Job)
            .join(Job, Job.id == Recommendation.job_id)
            .where(
                Recommendation.user_id == user.id,
                ((Job.owner_user_id.is_(None)) | (Job.owner_user_id == user.id)),
            )
            .order_by(Recommendation.rank_score.desc(), Job.posted_at.desc())
        ).all()
        try:
            freshness_days = int(freshness) if freshness else None
        except ValueError:
            freshness_days = None
        now = utcnow()
        filtered = []
        for rec, job in rows:
            skills = json.loads(job.skills_text or "[]")
            keywords = json.loads(job.keywords_text or "[]")
            hay = " ".join([
                job.title, job.company, job.location, job.role_family,
                " ".join(skills), " ".join(keywords), job.description,
            ])
            age = (now - (job.posted_at or job.discovered_at)).days
            if q and not search_matches(q, hay):
                continue
            if city and city != job.city:
                continue
            if role and role != job.role_family:
                continue
            if skill and skill.casefold() not in {x.casefold() for x in skills}:
                continue
            if source and source != job.source:
                continue
            if freshness_days is not None and age > freshness_days:
                continue
            if qualification and qualification != rec.qualification:
                continue
            if relevance and relevance != rec.relevance:
                continue
            if opportunity and opportunity != rec.opportunity:
                continue
            if status and status != rec.user_status:
                continue
            filtered.append({
                "rec": rec,
                "job": job,
                "skills": skills,
                "age_days": age,
                "reasons": crypto.decrypt_json(rec.reasons_encrypted, []),
            })
        facets = {
            "cities": sorted({job.city for _rec, job in rows if job.city}),
            "roles": sorted({job.role_family for _rec, job in rows if job.role_family}),
            "skills": sorted({s for _rec, job in rows for s in json.loads(job.skills_text or "[]")})[:80],
            "sources": sorted({job.source for _rec, job in rows}),
        }
        latest_run = db.scalar(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id).order_by(DiscoveryRun.created_at.desc()))
        source_rows = []
        if latest_run:
            source_rows = db.scalars(select(DiscoverySourceStatus).where(DiscoverySourceStatus.run_id == latest_run.id)).all()
        return {
            "items": filtered, "facets": facets, "filters": active_filters,
            "latest_run": latest_run, "source_rows": source_rows,
            "refresh_hours": settings.discovery_refresh_hours,
        }

    @app.get("/recommendations", response_class=HTMLResponse)
    def recommendations(
        request: Request,
        q: str = "",
        city: str = "",
        role: str = "",
        skill: str = "",
        source: str = "",
        freshness: str = "",
        qualification: str = "",
        relevance: str = "",
        opportunity: str = "",
        status: str = "",
        partial: bool = False,
        db: Session = Depends(get_db),
    ):
        user = _require_user(request)
        context = _recommendation_context(
            request, db, user,
            q=q, city=city, role=role, skill=skill, source=source,
            freshness=freshness, qualification=qualification, relevance=relevance,
            opportunity=opportunity, status=status,
        )
        if partial:
            return _render(request, "recommendation_results.html", context)
        return _render(request, "recommendations.html", context)

    @app.get("/recommendations/{rec_id}", response_class=HTMLResponse)
    def recommendation_detail(request: Request, rec_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        result = recommendation_for_user(db, user.id, rec_id)
        if not result:
            raise HTTPException(404, "岗位不存在。")
        rec, job = result
        return _render(request, "recommendation_detail.html", {
            "rec": rec, "job": job,
            "job_description": clean_html(job.description),
            "skills": json.loads(job.skills_text or "[]"),
            "keywords": json.loads(job.keywords_text or "[]"),
            "reasons": crypto.decrypt_json(rec.reasons_encrypted, []),
        })

    @app.post("/recommendations/{rec_id}/status")
    def recommendation_status(
        request: Request,
        rec_id: int,
        status: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        result = recommendation_for_user(db, user.id, rec_id)
        if not result:
            raise HTTPException(404, "岗位不存在。")
        if status not in {"new", "saved", "ignored", "preparing", "applied"}:
            raise HTTPException(400, "无效状态。")
        rec, _job = result
        rec.user_status = status
        db.commit()
        return _redirect(f"/recommendations/{rec_id}", message="状态已更新。")

    @app.post("/recommendations/{rec_id}/pack")
    def create_pack(
        request: Request,
        rec_id: int,
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        result = recommendation_for_user(db, user.id, rec_id)
        if not result:
            raise HTTPException(404, "岗位不存在。")
        rec, job = result
        pack, note = build_application_pack(db, crypto, settings, user, rec, job)
        return _redirect(f"/application-packs/{pack.id}", message=note or "申请包已生成。")

    def _owned_pack_context(db: Session, user: User, pack_id: int) -> tuple[ApplicationPack, Job, dict[str, Any]]:
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == pack_id, ApplicationPack.user_id == user.id))
        if not pack:
            raise HTTPException(404, "申请包不存在。")
        job = db.get(Job, pack.job_id)
        if not job:
            raise HTTPException(404, "岗位不存在。")
        content = ensure_application_materials(
            crypto.decrypt_json(pack.content_encrypted, {}),
            profile=get_profile(db, crypto, user.id),
            experiences=list_experiences(db, crypto, user.id),
            job=job,
        )
        return pack, job, content

    def _render_ai_consultation(
        request: Request,
        *,
        job: Job,
        materials: dict[str, Any],
        form_action: str,
        back_url: str,
        question: str = "",
        answer: str | None = None,
        note: str | None = None,
        error: str | None = None,
    ):
        return _render(request, "ai_consult.html", {
            "job": job,
            "materials": materials,
            "form_action": form_action,
            "back_url": back_url,
            "question": question,
            "answer": answer,
            "ai_note": note,
            "error": error or "",
        })

    @app.get("/recommendations/{rec_id}/ai", response_class=HTMLResponse)
    def recommendation_ai_page(request: Request, rec_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        result = recommendation_for_user(db, user.id, rec_id)
        if not result:
            raise HTTPException(404, "岗位不存在。")
        _rec, job = result
        materials = build_application_materials(
            get_profile(db, crypto, user.id),
            list_experiences(db, crypto, user.id),
            job,
        )
        return _render_ai_consultation(
            request,
            job=job,
            materials=materials,
            form_action=f"/recommendations/{rec_id}/ai",
            back_url=f"/recommendations/{rec_id}",
        )

    @app.post("/recommendations/{rec_id}/ai", response_class=HTMLResponse)
    def recommendation_ai_post(
        request: Request,
        rec_id: int,
        question: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        result = recommendation_for_user(db, user.id, rec_id)
        if not result:
            raise HTTPException(404, "岗位不存在。")
        _rec, job = result
        materials = build_application_materials(
            get_profile(db, crypto, user.id),
            list_experiences(db, crypto, user.id),
            job,
        )
        if not question.strip():
            return _render_ai_consultation(
                request, job=job, materials=materials,
                form_action=f"/recommendations/{rec_id}/ai", back_url=f"/recommendations/{rec_id}",
                error="请输入希望咨询的问题。",
            )
        answer, note = consult_application_materials(
            db, settings, user, job=job, materials=materials, question=question,
        )
        audit(db, "recommendation_ai_consulted", user.id, f"rec={rec_id}")
        return _render_ai_consultation(
            request, job=job, materials=materials,
            form_action=f"/recommendations/{rec_id}/ai", back_url=f"/recommendations/{rec_id}",
            question=question, answer=answer, note=note,
        )

    @app.get("/application-packs/{pack_id}", response_class=HTMLResponse)
    def pack_detail(request: Request, pack_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        pack, job, content = _owned_pack_context(db, user, pack_id)
        return _render(request, "application_pack.html", {
            "pack": pack, "job": job, "content": content,
        })

    @app.get("/application-packs/{pack_id}/edit", response_class=HTMLResponse)
    def pack_edit_page(request: Request, pack_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        pack, job, content = _owned_pack_context(db, user, pack_id)
        return _render(request, "application_pack_edit.html", {
            "pack": pack, "job": job, "content": content,
        })

    @app.post("/application-packs/{pack_id}/edit")
    def pack_edit_post(
        request: Request,
        pack_id: int,
        why_me_summary: str = Form(...),
        cv_headline: str = Form(...),
        cv_summary: str = Form(...),
        cv_bullets: str = Form(""),
        answer_why_role: str = Form(...),
        answer_why_me: str = Form(...),
        answer_role_example: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        pack, _job, content = _owned_pack_context(db, user, pack_id)
        required = [why_me_summary, cv_headline, cv_summary, answer_why_role, answer_why_me, answer_role_example]
        if any(not value.strip() for value in required):
            return _redirect(f"/application-packs/{pack_id}/edit", error="请保留 Why me、简历概要与三道回答；它们都可以如实改写。")
        update_application_materials(
            db,
            crypto,
            pack,
            content=content,
            why_me_summary=why_me_summary,
            cv_headline=cv_headline,
            cv_summary=cv_summary,
            cv_bullets=cv_bullets,
            interview_answers={
                "why_role": answer_why_role,
                "why_me": answer_why_me,
                "role_example": answer_role_example,
            },
        )
        audit(db, "application_pack_edited", user.id, f"pack={pack_id};version={pack.version}")
        return _redirect(f"/application-packs/{pack_id}", message="岗位适配 CV 与回答已更新；原始简历未被修改。")

    @app.get("/application-packs/{pack_id}/ai", response_class=HTMLResponse)
    def pack_ai_page(request: Request, pack_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        _pack, job, content = _owned_pack_context(db, user, pack_id)
        return _render_ai_consultation(
            request,
            job=job,
            materials=content["materials"],
            form_action=f"/application-packs/{pack_id}/ai",
            back_url=f"/application-packs/{pack_id}",
        )

    @app.post("/application-packs/{pack_id}/ai", response_class=HTMLResponse)
    def pack_ai_post(
        request: Request,
        pack_id: int,
        question: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        _pack, job, content = _owned_pack_context(db, user, pack_id)
        if not question.strip():
            return _render_ai_consultation(
                request, job=job, materials=content["materials"],
                form_action=f"/application-packs/{pack_id}/ai", back_url=f"/application-packs/{pack_id}",
                error="请输入希望咨询的问题。",
            )
        answer, note = consult_application_materials(
            db, settings, user, job=job, materials=content["materials"], question=question,
        )
        audit(db, "application_pack_ai_consulted", user.id, f"pack={pack_id}")
        return _render_ai_consultation(
            request, job=job, materials=content["materials"],
            form_action=f"/application-packs/{pack_id}/ai", back_url=f"/application-packs/{pack_id}",
            question=question, answer=answer, note=note,
        )

    @app.get("/jobs/manual", response_class=HTMLResponse)
    def manual_page(request: Request):
        _require_user(request)
        return _render(request, "manual_job.html")

    @app.post("/jobs/manual")
    def manual_post(
        request: Request,
        url: str = Form(...),
        title: str = Form(...),
        company: str = Form(...),
        location: str = Form(""),
        description: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        safe_url = safe_http_url(url)
        if not safe_url:
            return _redirect("/jobs/manual", error="请输入有效的 http 或 https 官方岗位链接。")
        rec = manual_job(
            db, crypto, user.id, url=safe_url, title=title.strip(), company=company.strip(),
            location=location.strip(), description=description.strip(),
        )
        audit(db, "manual_job_imported", user.id)
        return _redirect(f"/recommendations/{rec.id}", message="岗位已导入并分析。")

    @app.get("/applications", response_class=HTMLResponse)
    def applications_page(request: Request, job_id: int | None = None, db: Session = Depends(get_db)):
        user = _require_user(request)
        events = db.execute(
            select(ApplicationEvent, Job)
            .join(Job, Job.id == ApplicationEvent.job_id)
            .where(ApplicationEvent.user_id == user.id, (Job.owner_user_id.is_(None)) | (Job.owner_user_id == user.id))
            .order_by(ApplicationEvent.created_at.desc())
        ).all()
        recommendations = db.execute(
            select(Recommendation, Job)
            .join(Job, Job.id == Recommendation.job_id)
            .where(Recommendation.user_id == user.id, (Job.owner_user_id.is_(None)) | (Job.owner_user_id == user.id))
            .order_by(Job.company, Job.title)
        ).all()
        history = [{
            "event": event,
            "job": job,
            "evidence": crypto.decrypt_text(event.evidence_encrypted, ""),
            "notes": crypto.decrypt_text(event.notes_encrypted, ""),
        } for event, job in events]
        return _render(request, "applications.html", {
            "events": history,
            "progresses": list_application_progresses(db, crypto, user.id),
            "recommendations": recommendations,
            "selected_job_id": job_id,
            "status_labels": APPLICATION_STATUS_LABELS,
        })

    @app.post("/applications")
    def applications_post(
        request: Request,
        job_id: int = Form(...),
        status: str = Form(...),
        evidence: str = Form(""),
        notes: str = Form(""),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        rec = db.scalar(
            select(Recommendation)
            .join(Job, Job.id == Recommendation.job_id)
            .where(Recommendation.user_id == user.id, Recommendation.job_id == job_id, (Job.owner_user_id.is_(None)) | (Job.owner_user_id == user.id))
        )
        if not rec:
            raise HTTPException(404, "岗位不存在。")
        error = application_progress_error(status, evidence)
        if error:
            return _redirect("/applications", error=error)
        progress, created = create_application_progress(
            db, crypto, user_id=user.id, job_id=job_id, status=status, evidence=evidence, notes=notes,
        )
        if not created:
            return _redirect(f"/applications/{progress.id}/edit", message="这个岗位已有申请进度，请编辑当前记录。")
        if status == "submitted":
            rec.user_status = "applied"
        db.commit()
        audit(db, "application_progress_created", user.id, status)
        return _redirect("/applications", message="申请进度已保存。")

    @app.get("/applications/{progress_id}/edit", response_class=HTMLResponse)
    def application_edit_page(request: Request, progress_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        progress = application_progress_for_user(db, user.id, progress_id)
        if not progress:
            raise HTTPException(404, "申请进度不存在。")
        job = db.get(Job, progress.job_id)
        if not job or (job.owner_user_id is not None and job.owner_user_id != user.id):
            raise HTTPException(404, "申请进度不存在。")
        return _render(request, "application_edit.html", {
            "progress": progress,
            "job": job,
            "evidence": crypto.decrypt_text(progress.evidence_encrypted, ""),
            "notes": crypto.decrypt_text(progress.notes_encrypted, ""),
            "status_labels": APPLICATION_STATUS_LABELS,
        })

    @app.post("/applications/{progress_id}/edit")
    def application_edit_post(
        request: Request,
        progress_id: int,
        status: str = Form(...),
        evidence: str = Form(""),
        notes: str = Form(""),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        progress = application_progress_for_user(db, user.id, progress_id)
        if not progress:
            raise HTTPException(404, "申请进度不存在。")
        error = application_progress_error(status, evidence)
        if error:
            return _redirect(f"/applications/{progress_id}/edit", error=error)
        rec = db.scalar(
            select(Recommendation).where(Recommendation.user_id == user.id, Recommendation.job_id == progress.job_id)
        )
        if not rec:
            raise HTTPException(404, "岗位不存在。")
        update_application_progress(db, crypto, progress, status=status, evidence=evidence, notes=notes)
        if status == "submitted":
            rec.user_status = "applied"
        elif rec.user_status == "applied":
            rec.user_status = "preparing"
        db.commit()
        audit(db, "application_progress_edited", user.id, f"status={status};version={progress.version}")
        return _redirect("/applications", message="申请进度已更新，并保留了修订记录。")

    @app.get("/settings/profile", response_class=HTMLResponse)
    def settings_profile(request: Request, db: Session = Depends(get_db)):
        user = _require_user(request)
        return _render(request, "settings_profile.html", {"profile": get_profile(db, crypto, user.id)})

    @app.post("/settings/profile")
    def settings_profile_post(
        request: Request,
        primary_roles: str = Form(...),
        target_locations: str = Form(...),
        work_authorization: str = Form(...),
        sponsorship_now: str = Form(...),
        sponsorship_future: str = Form(...),
        work_modes: list[str] = Form([]),
        relocation: str = Form(""),
        available_start: str = Form(""),
        avoid_roles: str = Form(""),
        avoid_industries: str = Form(""),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        confirmed, error = _confirmed_profile_fields(
            primary_roles=primary_roles,
            target_locations=target_locations,
            work_authorization=work_authorization,
            sponsorship_now=sponsorship_now,
            sponsorship_future=sponsorship_future,
            work_modes=work_modes,
            relocation=relocation,
            available_start=available_start,
            avoid_roles=avoid_roles,
            avoid_industries=avoid_industries,
        )
        if error or confirmed is None:
            return _redirect("/settings/profile", error=error or "关键事实尚未确认。")
        profile = get_profile(db, crypto, user.id)
        profile.update(confirmed)
        row = save_profile(db, crypto, user.id, profile, onboarding_state="complete", discovery_enabled=True)
        row.next_discovery_at = utcnow()
        db.commit()
        enqueue_discovery(db, user.id, "profile_changed")
        return _redirect("/settings/profile", message="偏好已保存，新的推荐将在下一次刷新中生效。")

    @app.get("/settings/security", response_class=HTMLResponse)
    def security_page(request: Request):
        user = _require_user(request)
        return _render(request, "settings_security.html", {
            "masked_email": mask_email(crypto.decrypt_text(user.email_encrypted)),
        })

    @app.post("/settings/security")
    def security_post(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        new_password_confirm: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        if not verify_password(user.password_hash, current_password):
            return _redirect("/settings/security", error="当前密码不正确。")
        error = validate_password(new_password)
        if error:
            return _redirect("/settings/security", error=error)
        if new_password != new_password_confirm:
            return _redirect("/settings/security", error="两次新密码不一致。")
        user.password_hash = hash_password(new_password)
        revoke_all_sessions(db, user)
        audit(db, "password_changed", user.id)
        response = _redirect("/login", message="密码已修改，请重新登录。")
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/settings/data", response_class=HTMLResponse)
    def settings_data(request: Request):
        _require_user(request)
        return _render(request, "settings_data.html")

    @app.get("/settings/data/export")
    def export_data(request: Request, db: Session = Depends(get_db)):
        user = _require_user(request)
        payload = user_export(db, crypto, user)
        audit(db, "data_exported", user.id)
        return JSONResponse(
            payload,
            headers={"Content-Disposition": 'attachment; filename="jobhunt-data-export.json"'},
        )

    @app.post("/settings/data/delete")
    def delete_data(
        request: Request,
        password: str = Form(...),
        confirmation: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        user = _require_user(request)
        if confirmation != "删除我的账户":
            return _redirect("/settings/data", error="请输入“删除我的账户”确认。")
        if not verify_password(user.password_hash, password):
            return _redirect("/settings/data", error="密码不正确。")
        user_id = user.id
        delete_user_account(db, settings, user)
        audit(db, "account_deleted", None, f"user_id={user_id}")
        response = _redirect("/", message="账户和个人数据已删除。")
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/admin/users", response_class=HTMLResponse)
    def admin_users(request: Request, db: Session = Depends(get_db)):
        _require_admin(request)
        users = db.scalars(select(User).order_by(User.created_at.desc())).all()
        view = [{
            "id": u.id,
            "email": mask_email(crypto.decrypt_text(u.email_encrypted)),
            "verified": u.is_verified,
            "active": u.is_active,
            "admin": u.is_admin,
            "quota": u.daily_ai_request_limit,
            "created_at": u.created_at,
        } for u in users]
        return _render(request, "admin_users.html", {"users": view})

    @app.post("/admin/users/{user_id}/toggle")
    def admin_toggle(
        request: Request,
        user_id: int,
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        admin = _require_admin(request)
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "用户不存在。")
        if target.id == admin.id:
            return _redirect("/admin/users", error="不能停用当前管理员自己。")
        target.is_active = not target.is_active
        if not target.is_active:
            revoke_all_sessions(db, target)
        db.commit()
        audit(db, "admin_user_toggled", admin.id, f"target={user_id};active={target.is_active}")
        return _redirect("/admin/users", message="用户状态已更新。")

    @app.post("/admin/users/{user_id}/quota")
    def admin_quota(
        request: Request,
        user_id: int,
        quota: int = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        admin = _require_admin(request)
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "用户不存在。")
        target.daily_ai_request_limit = max(0, min(quota, 1000))
        db.commit()
        audit(db, "admin_quota_changed", admin.id, f"target={user_id};quota={target.daily_ai_request_limit}")
        return _redirect("/admin/users", message="AI 额度已更新。")

    @app.get("/admin/platform", response_class=HTMLResponse)
    def admin_platform(request: Request, db: Session = Depends(get_db)):
        _require_admin(request)
        queued = db.scalar(select(func.count(DiscoveryRun.id)).where(DiscoveryRun.status == "queued")) or 0
        running = db.scalar(select(func.count(DiscoveryRun.id)).where(DiscoveryRun.status == "running")) or 0
        return _render(request, "admin_platform.html", {
            "ai_status": ai.platform_status(db, settings),
            "queued": queued, "running": running,
            "refresh_hours": settings.discovery_refresh_hours,
        })

    if settings.testing:
        @app.get("/_test/outbox")
        def test_outbox():
            if not mailer.outbox_path.exists():
                return []
            return json.loads(mailer.outbox_path.read_text(encoding="utf-8"))

        @app.post("/_test/run-discovery")
        def test_discovery():
            with factory() as db:
                run = claim_run(db)
                if not run:
                    return {"status": "empty"}
                process_run(db, run, settings, crypto)
                return {"status": run.status, "id": run.id}

    return app


def _bootstrap_admin(db: Session, settings: Settings, crypto: CryptoBox) -> None:
    lookup = email_lookup(settings.admin_email, settings.email_lookup_secret)
    admin = db.scalar(select(User).where(User.email_lookup == lookup))
    if not admin:
        admin = User(
            email_lookup=lookup,
            email_encrypted=crypto.encrypt_text(normalize_email(settings.admin_email)),
            display_name_encrypted=crypto.encrypt_text("平台管理员"),
            password_hash=hash_password(settings.admin_password),
            is_verified=True,
            is_active=True,
            is_admin=True,
            verified_at=utcnow(),
            daily_ai_request_limit=1000,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        save_profile(db, crypto, admin.id, {}, onboarding_state="needs_resume", discovery_enabled=False)
    else:
        admin.is_admin = True
        admin.is_verified = True
        admin.is_active = True
        db.commit()


app = create_app()
