from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, User, json_dumps, utcnow


settings = get_settings()
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_dummy_hash = password_hasher.hash("dummy-password-not-used")


@dataclass
class LoginRateState:
    attempts: deque[float]


_login_attempts: dict[str, LoginRateState] = defaultdict(lambda: LoginRateState(deque()))
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 10


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def seed_admin(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == settings.admin_email))
    if user:
        return user
    existing = db.scalar(select(User).order_by(User.id).limit(1))
    if existing:
        raise RuntimeError(
            "ADMIN_EMAIL does not match the existing Owner. Restore the original production configuration "
            "or perform an explicit Owner email migration."
        )
    user = User(
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        display_name="Owner",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="admin_seeded",
            object_type="user",
            object_id=str(user.id),
            details_json=json_dumps({"email": settings.admin_email}),
        )
    )
    db.commit()
    db.refresh(user)
    return user


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def login_is_rate_limited(request: Request) -> bool:
    now = time.monotonic()
    state = _login_attempts[_client_key(request)]
    while state.attempts and now - state.attempts[0] > _LOGIN_WINDOW_SECONDS:
        state.attempts.popleft()
    return len(state.attempts) >= _LOGIN_MAX_ATTEMPTS


def record_login_failure(request: Request) -> None:
    _login_attempts[_client_key(request)].attempts.append(time.monotonic())


def clear_login_failures(request: Request) -> None:
    _login_attempts.pop(_client_key(request), None)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    normalized = email.strip().lower()
    if len(normalized) > 320 or len(password) > 1024:
        try:
            password_hasher.verify(_dummy_hash, password[:1024])
        except (VerifyMismatchError, InvalidHashError):
            pass
        return None
    user = db.scalar(select(User).where(User.email == normalized))
    if not user:
        try:
            password_hasher.verify(_dummy_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            pass
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_login_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["session_version"] = user.session_version
    request.session["csrf"] = secrets.token_urlsafe(32)
    request.session["login_nonce"] = secrets.token_urlsafe(16)


def clear_login_session(request: Request) -> None:
    request.session.clear()


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return str(token)


def verify_csrf(request: Request, supplied: str | None) -> None:
    expected = str(request.session.get("csrf", ""))
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="页面已过期，请刷新后重试。")


def safe_next_url(value: str | None, fallback: str = "/") -> str:
    if not value:
        return fallback
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return fallback
    return value


def current_user_optional(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        return None
    user = db.get(User, user_id)
    session_version = request.session.get("session_version")
    if (
        not user
        or not user.is_active
        or not isinstance(session_version, int)
        or session_version != user.session_version
    ):
        request.session.clear()
        return None
    return user


def require_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = current_user_optional(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
