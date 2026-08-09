from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEVELOPMENT_FERNET_KEY = "v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4="
KNOWN_INSECURE_SESSION_SECRETS = {
    "development-only-session-secret-change-me",
    "local-session-secret-abcdefghijklmnopqrstuvwxyz",
    "test-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789",
    "e2e-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789",
    "http-golden-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789",
}
KNOWN_INSECURE_ADMIN_PASSWORDS = {
    "ChangeMe-Immediately-123!",
    "Local-Only-Password-2026",
    "Correct-Horse-Battery-2026",
}

def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    base_url: str
    timezone_name: str
    data_dir: Path
    database_url: str
    session_secret: str
    data_encryption_key: str
    admin_email: str
    admin_password: str
    cookie_secure: bool
    session_max_age_seconds: int
    max_upload_bytes: int
    job_fetch_timeout_seconds: float
    job_fetch_max_bytes: int
    automatic_backup_hours: int
    backup_retention_days: int
    canonical_export_path: Path
    sync_status_path: Path
    original_file_retention: bool
    maintenance_enabled: bool

    # Optional DeepSeek enhancement. The deterministic rules engine remains usable without it.
    deepseek_api_key: str
    deepseek_api_key_file: Path | None
    deepseek_base_url: str
    deepseek_fast_model: str
    deepseek_precision_model: str
    deepseek_default_mode: str
    deepseek_daily_request_limit: int
    deepseek_daily_token_limit: int
    deepseek_max_input_characters: int
    deepseek_max_output_tokens: int
    deepseek_request_timeout_seconds: int
    deepseek_circuit_breaker_failures: int
    deepseek_circuit_breaker_minutes: int

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "/data")).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    (data_dir / "backups").mkdir(exist_ok=True)
    (data_dir / "canonical").mkdir(exist_ok=True)

    db_path = data_dir / "jobhuntos.db"
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
    environment = os.getenv("APP_ENV", "development")
    key_file_raw = os.getenv("DEEPSEEK_API_KEY_FILE", "").strip()

    settings = Settings(
        app_name=os.getenv("APP_NAME", "JobHuntBot Online"),
        app_version=os.getenv("APP_VERSION", "0.2.0"),
        environment=environment,
        base_url=os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        timezone_name=os.getenv("APP_TIMEZONE", "Australia/Sydney").strip(),
        data_dir=data_dir,
        database_url=database_url,
        session_secret=os.getenv("SESSION_SECRET", "development-only-session-secret-change-me"),
        data_encryption_key=os.getenv("DATA_ENCRYPTION_KEY", ""),
        admin_email=os.getenv("ADMIN_EMAIL", "owner@example.com").strip().lower(),
        admin_password=os.getenv("ADMIN_PASSWORD", "ChangeMe-Immediately-123!"),
        cookie_secure=_as_bool(os.getenv("COOKIE_SECURE"), default=environment == "production"),
        session_max_age_seconds=int(os.getenv("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 3600))),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        job_fetch_timeout_seconds=float(os.getenv("JOB_FETCH_TIMEOUT_SECONDS", "12")),
        job_fetch_max_bytes=int(os.getenv("JOB_FETCH_MAX_BYTES", str(2 * 1024 * 1024))),
        automatic_backup_hours=int(os.getenv("AUTOMATIC_BACKUP_HOURS", "24")),
        backup_retention_days=int(os.getenv("BACKUP_RETENTION_DAYS", "14")),
        canonical_export_path=Path(
            os.getenv("CANONICAL_EXPORT_PATH", str(data_dir / "canonical" / "current.json"))
        ),
        sync_status_path=Path(
            os.getenv("SYNC_STATUS_PATH", str(data_dir / "canonical" / "sync_status.json"))
        ),
        original_file_retention=_as_bool(os.getenv("STORE_ORIGINAL_FILES"), default=True),
        maintenance_enabled=_as_bool(os.getenv("MAINTENANCE_ENABLED"), default=True),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        deepseek_api_key_file=Path(key_file_raw).expanduser().resolve() if key_file_raw else None,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_fast_model=os.getenv("DEEPSEEK_FAST_MODEL", "deepseek-v4-flash").strip(),
        deepseek_precision_model=os.getenv("DEEPSEEK_PRECISION_MODEL", "deepseek-v4-pro").strip(),
        deepseek_default_mode=os.getenv("DEEPSEEK_DEFAULT_MODE", "fast").strip().lower(),
        deepseek_daily_request_limit=int(os.getenv("DEEPSEEK_DAILY_REQUEST_LIMIT", "60")),
        deepseek_daily_token_limit=int(os.getenv("DEEPSEEK_DAILY_TOKEN_LIMIT", "600000")),
        deepseek_max_input_characters=int(os.getenv("DEEPSEEK_MAX_INPUT_CHARACTERS", "60000")),
        deepseek_max_output_tokens=int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "3000")),
        deepseek_request_timeout_seconds=int(os.getenv("DEEPSEEK_REQUEST_TIMEOUT_SECONDS", "75")),
        deepseek_circuit_breaker_failures=int(os.getenv("DEEPSEEK_CIRCUIT_BREAKER_FAILURES", "3")),
        deepseek_circuit_breaker_minutes=int(os.getenv("DEEPSEEK_CIRCUIT_BREAKER_MINUTES", "15")),
    )

    if settings.is_production:
        unsafe: list[str] = []
        if settings.session_secret in KNOWN_INSECURE_SESSION_SECRETS or len(settings.session_secret) < 32:
            unsafe.append("SESSION_SECRET")
        try:
            decoded_key = base64.urlsafe_b64decode(settings.data_encryption_key.encode("ascii"))
        except Exception:
            decoded_key = b""
        if len(decoded_key) != 32 or settings.data_encryption_key == DEVELOPMENT_FERNET_KEY:
            unsafe.append("DATA_ENCRYPTION_KEY")
        if settings.admin_password in KNOWN_INSECURE_ADMIN_PASSWORDS or len(settings.admin_password) < 12:
            unsafe.append("ADMIN_PASSWORD")
        if "@" not in settings.admin_email:
            unsafe.append("ADMIN_EMAIL")
        if not settings.base_url.startswith("https://"):
            unsafe.append("BASE_URL")
        if not settings.cookie_secure:
            unsafe.append("COOKIE_SECURE")
        if settings.deepseek_base_url != "https://api.deepseek.com":
            unsafe.append("DEEPSEEK_BASE_URL")
        allowed_models = {"deepseek-v4-flash", "deepseek-v4-pro"}
        if settings.deepseek_fast_model not in allowed_models:
            unsafe.append("DEEPSEEK_FAST_MODEL")
        if settings.deepseek_precision_model not in allowed_models:
            unsafe.append("DEEPSEEK_PRECISION_MODEL")
        if settings.deepseek_default_mode not in {"fast", "precision"}:
            unsafe.append("DEEPSEEK_DEFAULT_MODE")
        if not 1 <= settings.deepseek_daily_request_limit <= 500:
            unsafe.append("DEEPSEEK_DAILY_REQUEST_LIMIT")
        if not 10_000 <= settings.deepseek_daily_token_limit <= 10_000_000:
            unsafe.append("DEEPSEEK_DAILY_TOKEN_LIMIT")
        if not 5_000 <= settings.deepseek_max_input_characters <= 500_000:
            unsafe.append("DEEPSEEK_MAX_INPUT_CHARACTERS")
        if not 512 <= settings.deepseek_max_output_tokens <= 12_000:
            unsafe.append("DEEPSEEK_MAX_OUTPUT_TOKENS")
        if not 10 <= settings.deepseek_request_timeout_seconds <= 180:
            unsafe.append("DEEPSEEK_REQUEST_TIMEOUT_SECONDS")
        try:
            ZoneInfo(settings.timezone_name)
        except ZoneInfoNotFoundError:
            unsafe.append("APP_TIMEZONE")
        if unsafe:
            raise RuntimeError(
                "Production configuration is incomplete or unsafe: " + ", ".join(unsafe)
            )

    return settings
