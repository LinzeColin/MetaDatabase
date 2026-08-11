#!/usr/bin/env python3
"""Generate the non-interactive production configuration and one-time Owner login.

The script never asks for or writes the DeepSeek, SMTP, IMAP, GitHub, R2, or
Cloudflare credential values. NitroSend is not used or required. Delivery may
generate a deployable configuration before mail is ready; registration stays
closed until any standards-compatible SMTP relay is injected securely.
"""
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet


def q(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--smtp-host", default="")
    parser.add_argument("--smtp-from", default="JobHuntBot <no-reply@example.com>")
    parser.add_argument("--edge-network", default="coolify")
    parser.add_argument("--compose-project-name", default="jobhuntbot-online")
    parser.add_argument("--output", default=".env")
    args = parser.parse_args()

    admin_password = secrets.token_urlsafe(20) + "Aa1"
    postgres_password = secrets.token_urlsafe(32)
    database_password = quote(postgres_password, safe="")
    lines = {
        "COMPOSE_PROJECT_NAME": args.compose_project_name,
        "APP_IMAGE": "jobhuntbot-online:0.3.0",
        "ACCEPTANCE_IMAGE": "jobhuntbot-online-acceptance:0.3.0",
        "APP_ENV": "production",
        "APP_NAME": "JobHuntBot Online",
        "APP_VERSION": "0.3.0",
        "BASE_URL": f"https://{args.domain}",
        "DOMAIN": args.domain,
        "APP_TIMEZONE": "Australia/Sydney",
        "DATABASE_URL": f"postgresql+psycopg://jobhunt:{database_password}@jobhuntbot-db:5432/jobhunt",
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "DATA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "EMAIL_LOOKUP_SECRET": secrets.token_urlsafe(48),
        "COOKIE_SECURE": "true",
        "SESSION_MAX_AGE_SECONDS": "604800",
        "ADMIN_EMAIL": args.admin_email,
        "ADMIN_PASSWORD": admin_password,
        "ALLOW_REGISTRATION": "true" if args.smtp_host else "false",
        "SMTP_HOST": args.smtp_host,
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM": args.smtp_from,
        "SMTP_STARTTLS": "true",
        "EMAIL_MIN_INTERVAL_SECONDS": "1800",
        "EMAIL_MAX_PER_USER_PER_24H": "3",
        "DEEPSEEK_API_KEY": "",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_MODEL": "deepseek-chat",
        "DEEPSEEK_DAILY_PLATFORM_REQUEST_LIMIT": "1000",
        "DEEPSEEK_DAILY_PLATFORM_TOKEN_LIMIT": "5000000",
        "DEEPSEEK_DEFAULT_USER_REQUEST_LIMIT": "60",
        "DEEPSEEK_REQUEST_TIMEOUT_SECONDS": "60",
        "DEEPSEEK_CIRCUIT_BREAKER_FAILURES": "3",
        "DEEPSEEK_CIRCUIT_BREAKER_MINUTES": "15",
        "DISCOVERY_REFRESH_HOURS": "6",
        "DISCOVERY_SOURCE_TIMEOUT_SECONDS": "15",
        "DISCOVERY_MAX_JOBS_PER_SOURCE": "120",
        "DISCOVERY_FIXTURE_PATH": "",
        "ENABLE_REMOTIVE": "true",
        "ENABLE_ARBEITNOW": "true",
        "ENABLE_JOBICY": "true",
        "ADZUNA_APP_ID": "",
        "ADZUNA_APP_KEY": "",
        "GREENHOUSE_BOARDS": "",
        "LEVER_COMPANIES": "",
        "ASHBY_BOARDS": "",
        "FREEHIRE_BASE_URL": "",
        "UPLOAD_ROOT": "/data/uploads",
        "BACKUP_ROOT": "/data/backups",
        "MAX_UPLOAD_BYTES": "10485760",
        "BACKUP_ENCRYPTION_PASSPHRASE": secrets.token_urlsafe(48),
        "EDGE_NETWORK": args.edge_network,
        "V02_SQLITE_PATH": "",
        "V02_DATA_ROOT": "",
        "OLD_DATA_ENCRYPTION_KEY": "",
        "V02_PLATFORM_KEY_OUTPUT": "",
        "LEGACY_COMPOSE_FILE": "",
        "LEGACY_SERVICE": "app",
        "ACCEPTANCE_EMAIL_A": "",
        "ACCEPTANCE_EMAIL_B": "",
        "ACCEPTANCE_ACCOUNT_PASSWORD": "",
        "RUN_REAL_EMAIL_ACCEPTANCE": "false",
        "REAL_EMAIL_ACCEPTANCE_RUN_ID": "",
        "ACCEPTANCE_MIN_EMAIL_GAP_SECONDS": "1800",
        "ACCEPTANCE_EMAIL_REQUEST_SAFETY_SECONDS": "30",
        "ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS": "24",
        "ACCEPTANCE_IMAP_HOST": "",
        "ACCEPTANCE_IMAP_PORT": "993",
        "ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS": "20",
        "ACCEPTANCE_IMAP_USERNAME": "",
        "ACCEPTANCE_IMAP_PASSWORD": "",
        "ACCEPTANCE_IMAP_FOLDER": "INBOX",
        "ACCEPTANCE_IMAP_SSL": "true",
        "ACCEPTANCE_IMAP_STARTTLS": "false",
        "ACCEPTANCE_MAIL_TIMEOUT_SECONDS": "240",
        "ACCEPTANCE_DISCOVERY_TIMEOUT_SECONDS": "300",
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE": "",
        "STATUS_URL": "https://status.linzezhang.com",
        "STATUS_REGISTRATION_EVIDENCE": "",
        "PRIVATE_DATABASE_SYNC_EVIDENCE": "",
        "R2_SYNC_EVIDENCE": "",
    }
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(f"{key}={q(value)}" for key, value in lines.items()) + "\n", encoding="utf-8")
    os.chmod(out, 0o600)
    secret_dir = out.parent / "secrets"
    secret_dir.mkdir(exist_ok=True)
    postgres_file = secret_dir / "postgres_password.txt"
    postgres_file.write_text(postgres_password, encoding="utf-8")
    os.chmod(postgres_file, 0o600)
    login = out.parent / "OWNER_LOGIN.txt"
    login.write_text(
        f"URL=https://{args.domain}\nEMAIL={args.admin_email}\nPASSWORD={admin_password}\n",
        encoding="utf-8",
    )
    os.chmod(login, 0o600)
    print(f"created {out}, secrets/postgres_password.txt and OWNER_LOGIN.txt")
    if args.smtp_host:
        print("next: inject standard SMTP credentials, DeepSeek and acceptance mailbox Secrets without printing them")
    else:
        print("mail deferred: core deployment may continue with ALLOW_REGISTRATION=false; do not wait for NitroSend")
        print("before full production PASS, inject any standard SMTP relay and set ALLOW_REGISTRATION=true")


if __name__ == "__main__":
    main()
