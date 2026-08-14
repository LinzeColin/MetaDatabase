from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import RateLimitBucket, User, UserSession, utcnow

PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{10,128}$")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s()\-]{7,}\d)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"https?://\S+")
PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class CryptoBox:
    def __init__(self, key: str):
        self.fernet = Fernet(key.encode())

    def encrypt_text(self, value: str) -> bytes:
        return self.fernet.encrypt(value.encode("utf-8"))

    def decrypt_text(self, value: bytes | None, default: str = "") -> str:
        if not value:
            return default
        return self.fernet.decrypt(value).decode("utf-8")

    def encrypt_json(self, value: Any) -> bytes:
        return self.encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def decrypt_json(self, value: bytes | None, default: Any = None) -> Any:
        if not value:
            return {} if default is None else default
        return json.loads(self.decrypt_text(value))


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def email_lookup(email: str, secret: str) -> str:
    return hmac.new(secret.encode(), normalize_email(email).encode(), hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    email = normalize_email(email)
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}***@{domain}"


def validate_password(password: str) -> str | None:
    if not PASSWORD_RE.match(password):
        return "密码至少 10 位，并包含大写字母、小写字母和数字。"
    return None


def hash_password(password: str) -> str:
    return PH.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PH.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def random_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, settings: Settings) -> tuple[str, UserSession]:
    raw = random_token()
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw),
        csrf_token=random_token(24),
        auth_version=user.auth_version,
        expires_at=utcnow() + timedelta(seconds=settings.session_max_age_seconds),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return raw, session


def resolve_session(db: Session, raw_token: str | None) -> tuple[User | None, UserSession | None]:
    if not raw_token:
        return None, None
    row = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash(raw_token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utcnow(),
        )
    )
    if not row:
        return None, None
    user = db.get(User, row.user_id)
    if not user or not user.is_active or row.auth_version != user.auth_version:
        return None, None
    row.last_seen_at = utcnow()
    db.commit()
    return user, row


def revoke_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw_token)))
    if row and row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()


def revoke_all_sessions(db: Session, user: User) -> None:
    managed = db.merge(user)
    managed.auth_version += 1
    db.commit()
    user.auth_version = managed.auth_version


def check_csrf(session: UserSession | None, submitted: str | None) -> bool:
    return bool(session and submitted and secrets.compare_digest(session.csrf_token, submitted))


def rate_limit(
    db: Session,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    now = utcnow()
    row = db.scalar(select(RateLimitBucket).where(RateLimitBucket.bucket_key == key))
    if not row:
        db.add(RateLimitBucket(bucket_key=key, window_started_at=now, count=1))
        db.commit()
        return True
    if row.window_started_at <= now - timedelta(seconds=window_seconds):
        row.window_started_at = now
        row.count = 1
        db.commit()
        return True
    if row.count >= limit:
        return False
    row.count += 1
    db.commit()
    return True


def redact_for_provider(value: str) -> str:
    value = EMAIL_RE.sub("[email removed]", value)
    value = PHONE_RE.sub("[phone removed]", value)
    value = URL_RE.sub("[url removed]", value)
    return value[:60000]
