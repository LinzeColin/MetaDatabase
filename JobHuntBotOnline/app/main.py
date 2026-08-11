from __future__ import annotations

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
from .discovery import claim_run, enqueue_discovery, process_run, safe_http_url
from .email_service import Mailer
from .models import (
    ApplicationEvent, ApplicationPack, CandidateProfile, DiscoveryRun, DiscoverySourceStatus,
    Job, Recommendation, Resume, User, utcnow,
)
from .resume import ResumeError, extract_text
from .security import (
    CryptoBox, check_csrf, create_session, email_lookup, hash_password, mask_email,
    normalize_email, rate_limit, resolve_session, revoke_all_sessions, revoke_session,
    validate_password, verify_password,
)
from .services import (
    audit, build_application_pack, delete_user_account, get_profile, get_profile_row,
    list_experiences, list_resumes, manual_job, recommendation_for_user, save_profile,
    store_resume, user_export,
)

SESSION_COOKIE = "jobhunt_session"
CSRF_COOKIE = "jobhunt_csrf"
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _csv_list(value: str) -> list[str]:
    return [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]


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
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
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
            "user": request.state.user,
            "csrf_token": _csrf(request),
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
        mailer.send_verification(db, user)
        audit(db, "user_registered", user.id)
        return _redirect("/verify-required", message="验证邮件已发送，请打开邮箱完成验证。")

    @app.get("/verify-required", response_class=HTMLResponse)
    def verify_required(request: Request):
        return _render(request, "verify_required.html")

    @app.get("/verify-email")
    def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
        user = mailer.consume_token(db, token, "verify")
        if not user:
            return _redirect("/resend-verification", error="验证链接无效或已过期。")
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
        return _render(request, "resend_verification.html")

    @app.post("/resend-verification")
    def resend_verification(
        request: Request,
        email: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(db, key=f"resend:{ip}", limit=5, window_seconds=3600):
            return _redirect("/resend-verification", error="请求过于频繁，请稍后再试。")
        lookup = email_lookup(email, settings.email_lookup_secret)
        user = db.scalar(select(User).where(User.email_lookup == lookup))
        if user and user.is_active and not user.is_verified:
            mailer.send_verification(db, user)
        return _redirect("/verify-required", message="如果该邮箱需要验证，新的邮件已经发送。")

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
        return _render(request, "forgot_password.html")

    @app.post("/forgot-password")
    def forgot(
        request: Request,
        email: str = Form(...),
        csrf_token: str = Form(...),
        db: Session = Depends(get_db),
    ):
        _require_csrf(request, csrf_token)
        ip = request.client.host if request.client else "unknown"
        if not rate_limit(db, key=f"forgot:{ip}", limit=6, window_seconds=3600):
            return _redirect("/forgot-password", error="请求过于频繁，请稍后再试。")
        user = db.scalar(select(User).where(User.email_lookup == email_lookup(email, settings.email_lookup_secret)))
        if user and user.is_active and user.is_verified:
            mailer.send_reset(db, user)
            audit(db, "password_reset_requested", user.id)
        return _redirect("/login", message="如果邮箱已注册，重置邮件已经发送。")

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
        profile = get_profile(db, crypto, user.id)
        profile.update({
            "primary_role_families": _csv_list(primary_roles),
            "target_locations": _csv_list(target_locations),
            "work_authorization": work_authorization.strip(),
            "sponsorship_now": sponsorship_now,
            "sponsorship_future": sponsorship_future,
            "work_mode": work_modes or ["hybrid", "onsite", "remote"],
            "relocation": relocation,
            "available_start": available_start.strip(),
            "avoid_roles": _csv_list(avoid_roles),
            "avoid_industries": _csv_list(avoid_industries),
        })
        row = save_profile(db, crypto, user.id, profile, onboarding_state="complete", discovery_enabled=True)
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
        db: Session = Depends(get_db),
    ):
        user = _require_user(request)
        rows = db.execute(
            select(Recommendation, Job)
            .join(Job, Job.id == Recommendation.job_id)
            .where(
                Recommendation.user_id == user.id,
                ((Job.owner_user_id.is_(None)) | (Job.owner_user_id == user.id)),
            )
            .order_by(Recommendation.rank_score.desc(), Job.posted_at.desc())
        ).all()
        now = utcnow()
        filtered = []
        for rec, job in rows:
            skills = json.loads(job.skills_text or "[]")
            keywords = json.loads(job.keywords_text or "[]")
            hay = " ".join([job.title, job.company, job.location, job.role_family, " ".join(skills), " ".join(keywords)]).casefold()
            age = (now - (job.posted_at or job.discovered_at)).days
            if q and q.casefold() not in hay:
                continue
            if city and city != job.city:
                continue
            if role and role != job.role_family:
                continue
            if skill and skill.casefold() not in {x.casefold() for x in skills}:
                continue
            if source and source != job.source:
                continue
            if freshness and age > int(freshness):
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
        return _render(request, "recommendations.html", {
            "items": filtered, "facets": facets, "filters": dict(request.query_params),
            "latest_run": latest_run, "source_rows": source_rows,
            "refresh_hours": settings.discovery_refresh_hours,
        })

    @app.get("/recommendations/{rec_id}", response_class=HTMLResponse)
    def recommendation_detail(request: Request, rec_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        result = recommendation_for_user(db, user.id, rec_id)
        if not result:
            raise HTTPException(404, "岗位不存在。")
        rec, job = result
        return _render(request, "recommendation_detail.html", {
            "rec": rec, "job": job,
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

    @app.get("/application-packs/{pack_id}", response_class=HTMLResponse)
    def pack_detail(request: Request, pack_id: int, db: Session = Depends(get_db)):
        user = _require_user(request)
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == pack_id, ApplicationPack.user_id == user.id))
        if not pack:
            raise HTTPException(404, "申请包不存在。")
        job = db.get(Job, pack.job_id)
        return _render(request, "application_pack.html", {
            "pack": pack, "job": job, "content": crypto.decrypt_json(pack.content_encrypted, {}),
        })

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
    def applications_page(request: Request, db: Session = Depends(get_db)):
        user = _require_user(request)
        events = db.execute(
            select(ApplicationEvent, Job)
            .join(Job, Job.id == ApplicationEvent.job_id)
            .where(ApplicationEvent.user_id == user.id)
            .order_by(ApplicationEvent.created_at.desc())
        ).all()
        recommendations = db.execute(
            select(Recommendation, Job)
            .join(Job, Job.id == Recommendation.job_id)
            .where(Recommendation.user_id == user.id)
            .order_by(Job.company, Job.title)
        ).all()
        return _render(request, "applications.html", {"events": events, "recommendations": recommendations})

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
        rec = db.scalar(select(Recommendation).where(Recommendation.user_id == user.id, Recommendation.job_id == job_id))
        if not rec:
            raise HTTPException(404, "岗位不存在。")
        allowed = {"pending", "submitted", "interview", "rejected", "offer", "withdrawn"}
        if status not in allowed:
            raise HTTPException(400, "无效申请状态。")
        if status == "submitted" and len(evidence.strip()) < 5:
            return _redirect("/applications", error="只有看到确认页面、确认文字或申请编号后，才能记录为已提交。")
        event = ApplicationEvent(
            user_id=user.id,
            job_id=job_id,
            status=status,
            evidence_encrypted=crypto.encrypt_text(evidence.strip()) if evidence.strip() else None,
            notes_encrypted=crypto.encrypt_text(notes.strip()) if notes.strip() else None,
        )
        db.add(event)
        if status == "submitted":
            rec.user_status = "applied"
        db.commit()
        audit(db, "application_event_recorded", user.id, status)
        return _redirect("/applications", message="申请进度已保存。")

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
        profile = get_profile(db, crypto, user.id)
        profile.update({
            "primary_role_families": _csv_list(primary_roles),
            "target_locations": _csv_list(target_locations),
            "work_authorization": work_authorization.strip(),
            "sponsorship_now": sponsorship_now,
            "sponsorship_future": sponsorship_future,
            "work_mode": work_modes,
            "relocation": relocation,
            "available_start": available_start.strip(),
            "avoid_roles": _csv_list(avoid_roles),
            "avoid_industries": _csv_list(avoid_industries),
        })
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
