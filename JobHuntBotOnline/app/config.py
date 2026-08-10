from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是整数") from exc


def _test_fernet_key() -> str:
    return "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_name: str
    app_version: str
    base_url: str
    database_url: str
    session_secret: str
    data_encryption_key: str
    email_lookup_secret: str
    cookie_secure: bool
    session_max_age_seconds: int
    admin_email: str
    admin_password: str
    allow_registration: bool

    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool

    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    deepseek_daily_platform_request_limit: int
    deepseek_daily_platform_token_limit: int
    deepseek_default_user_request_limit: int
    deepseek_request_timeout_seconds: int
    deepseek_circuit_breaker_failures: int
    deepseek_circuit_breaker_minutes: int

    discovery_refresh_hours: int
    discovery_source_timeout_seconds: int
    discovery_max_jobs_per_source: int
    discovery_fixture_path: str
    enable_remotive: bool
    enable_arbeitnow: bool
    enable_jobicy: bool
    adzuna_app_id: str
    adzuna_app_key: str
    greenhouse_boards: list[str]
    lever_companies: list[str]
    ashby_boards: list[str]
    freehire_base_url: str

    upload_root: Path
    backup_root: Path
    max_upload_bytes: int

    @property
    def testing(self) -> bool:
        return self.app_env == "test"


def get_settings() -> Settings:
    env = os.getenv("APP_ENV", "development").strip().lower()
    testing = env == "test"
    local = env != "production"
    settings = Settings(
        app_env=env,
        app_name=os.getenv("APP_NAME", "JobHuntBot Online"),
        app_version=os.getenv("APP_VERSION", "0.3.0"),
        base_url=os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        database_url=os.getenv(
            "DATABASE_URL",
            "sqlite+pysqlite:///./runtime-data/jobhunt.db",
        ),
        session_secret=os.getenv("SESSION_SECRET", "local-session-secret" if local else ""),
        data_encryption_key=os.getenv("DATA_ENCRYPTION_KEY", _test_fernet_key() if local else ""),
        email_lookup_secret=os.getenv("EMAIL_LOOKUP_SECRET", "local-email-secret" if local else ""),
        cookie_secure=_bool("COOKIE_SECURE", not testing),
        session_max_age_seconds=_int("SESSION_MAX_AGE_SECONDS", 7 * 24 * 3600),
        admin_email=os.getenv("ADMIN_EMAIL", "owner@example.com"),
        admin_password=os.getenv("ADMIN_PASSWORD", "AdminPass!2026" if local else ""),
        allow_registration=_bool("ALLOW_REGISTRATION", True),

        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", "JobHuntBot <no-reply@example.com>"),
        smtp_starttls=_bool("SMTP_STARTTLS", True),

        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        deepseek_daily_platform_request_limit=_int("DEEPSEEK_DAILY_PLATFORM_REQUEST_LIMIT", 1000),
        deepseek_daily_platform_token_limit=_int("DEEPSEEK_DAILY_PLATFORM_TOKEN_LIMIT", 5_000_000),
        deepseek_default_user_request_limit=_int("DEEPSEEK_DEFAULT_USER_REQUEST_LIMIT", 60),
        deepseek_request_timeout_seconds=_int("DEEPSEEK_REQUEST_TIMEOUT_SECONDS", 60),
        deepseek_circuit_breaker_failures=_int("DEEPSEEK_CIRCUIT_BREAKER_FAILURES", 3),
        deepseek_circuit_breaker_minutes=_int("DEEPSEEK_CIRCUIT_BREAKER_MINUTES", 15),

        discovery_refresh_hours=_int("DISCOVERY_REFRESH_HOURS", 6),
        discovery_source_timeout_seconds=_int("DISCOVERY_SOURCE_TIMEOUT_SECONDS", 15),
        discovery_max_jobs_per_source=_int("DISCOVERY_MAX_JOBS_PER_SOURCE", 120),
        discovery_fixture_path=os.getenv("DISCOVERY_FIXTURE_PATH", ""),
        enable_remotive=_bool("ENABLE_REMOTIVE", True),
        enable_arbeitnow=_bool("ENABLE_ARBEITNOW", True),
        enable_jobicy=_bool("ENABLE_JOBICY", True),
        adzuna_app_id=os.getenv("ADZUNA_APP_ID", ""),
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY", ""),
        greenhouse_boards=[x.strip() for x in os.getenv("GREENHOUSE_BOARDS", "").split(",") if x.strip()],
        lever_companies=[x.strip() for x in os.getenv("LEVER_COMPANIES", "").split(",") if x.strip()],
        ashby_boards=[x.strip() for x in os.getenv("ASHBY_BOARDS", "").split(",") if x.strip()],
        freehire_base_url=os.getenv("FREEHIRE_BASE_URL", "").rstrip("/"),

        upload_root=Path(os.getenv("UPLOAD_ROOT", "./runtime-data/uploads")),
        backup_root=Path(os.getenv("BACKUP_ROOT", "./runtime-data/backups")),
        max_upload_bytes=_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
    )
    validate_settings(settings)
    return settings


def validate_settings(s: Settings) -> None:
    # 产品合同：所有候选人的默认岗位新鲜度每六小时刷新一次。
    if s.discovery_refresh_hours != 6:
        raise RuntimeError("DISCOVERY_REFRESH_HOURS 必须固定为 6")
    if s.session_max_age_seconds < 900:
        raise RuntimeError("SESSION_MAX_AGE_SECONDS 过短")
    if s.max_upload_bytes < 1024:
        raise RuntimeError("MAX_UPLOAD_BYTES 无效")
    try:
        Fernet(s.data_encryption_key.encode())
    except Exception as exc:
        raise RuntimeError("DATA_ENCRYPTION_KEY 必须是有效 Fernet Key") from exc
    if s.app_env == "production":
        missing = [
            name for name, value in {
                "SESSION_SECRET": s.session_secret,
                "DATA_ENCRYPTION_KEY": s.data_encryption_key,
                "EMAIL_LOOKUP_SECRET": s.email_lookup_secret,
                "ADMIN_EMAIL": s.admin_email,
                "ADMIN_PASSWORD": s.admin_password,
            }.items() if not value
        ]
        if missing:
            raise RuntimeError("生产配置缺失：" + ", ".join(missing))
        if not s.cookie_secure:
            raise RuntimeError("生产环境 COOKIE_SECURE 必须为 true")
        if not s.smtp_host:
            raise RuntimeError("公开注册 SaaS 必须配置 SMTP_HOST")
