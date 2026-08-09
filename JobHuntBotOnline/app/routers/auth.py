from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    clear_login_failures,
    clear_login_session,
    current_user_optional,
    get_csrf_token,
    login_is_rate_limited,
    record_login_failure,
    safe_next_url,
    set_login_session,
    verify_csrf,
)
from app.db import get_db
from app.services.audit import record_audit
from app.web import flash, render


router = APIRouter()


@router.get("/login")
def login_page(request: Request, db: Annotated[Session, Depends(get_db)], next: str = "/"):
    user = current_user_optional(request, db)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return render(request, "login.html", next_url=safe_next_url(next), user=None)


@router.post("/login")
def login_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    next_url: Annotated[str, Form()] = "/",
):
    verify_csrf(request, csrf_token)
    if login_is_rate_limited(request):
        return render(
            request,
            "login.html",
            status_code=429,
            user=None,
            next_url=safe_next_url(next_url),
            error="尝试次数过多，请稍后再试。",
        )
    user = authenticate_user(db, email, password)
    if not user:
        record_login_failure(request)
        record_audit(db, user=None, action="login_failed", details={"email": email.strip().lower()[:320]})
        db.commit()
        return render(
            request,
            "login.html",
            status_code=400,
            user=None,
            next_url=safe_next_url(next_url),
            error="邮箱或密码不正确。",
        )
    clear_login_failures(request)
    set_login_session(request, user)
    record_audit(db, user=user, action="login_success", object_type="user", object_id=user.id)
    db.commit()
    return RedirectResponse(url=safe_next_url(next_url), status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: Annotated[str, Form()]):
    verify_csrf(request, csrf_token)
    clear_login_session(request)
    response = RedirectResponse(url="/login", status_code=303)
    return response
