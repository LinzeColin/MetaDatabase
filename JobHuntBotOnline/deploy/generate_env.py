from __future__ import annotations

import argparse
import base64
import os
import secrets
import shlex
from pathlib import Path



def password() -> str:
    groups = [
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "abcdefghijkmnopqrstuvwxyz",
        "23456789",
        "_-.@",
    ]
    chars = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    chars.extend(secrets.choice(alphabet) for _ in range(20))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate JobHuntBot Online production environment")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--data-path", default="./runtime-data")
    parser.add_argument("--output", default=".env")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output).resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing {output}. Use --force only for a deliberate credential rotation.")
    domain = args.domain.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not domain or "/" in domain or " " in domain:
        raise SystemExit("Invalid domain")
    admin_email = args.admin_email.strip().lower()
    if "@" not in admin_email:
        raise SystemExit("Invalid admin email")
    data_path = args.data_path.strip()
    if not data_path:
        raise SystemExit("Invalid data path")

    admin_password = password()
    data_recovery_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    values = {
        "APP_ENV": "production",
        "APP_NAME": "JobHuntBot Online",
        "APP_VERSION": "0.2.0",
        "APP_TIMEZONE": "Australia/Sydney",
        "DOMAIN": domain,
        "BASE_URL": f"https://{domain}",
        "ADMIN_EMAIL": admin_email,
        "ADMIN_PASSWORD": admin_password,
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "DATA_ENCRYPTION_KEY": data_recovery_key,
        "COOKIE_SECURE": "true",
        "SESSION_MAX_AGE_SECONDS": "604800",
        "MAX_UPLOAD_BYTES": "10485760",
        "JOB_FETCH_TIMEOUT_SECONDS": "12",
        "JOB_FETCH_MAX_BYTES": "2097152",
        "AUTOMATIC_BACKUP_HOURS": "24",
        "BACKUP_RETENTION_DAYS": "14",
        "STORE_ORIGINAL_FILES": "true",
        "MAINTENANCE_ENABLED": "true",
        "DATA_PATH": data_path,
        "HOST_DATA_GID": str(os.getgid()),
        "TRAEFIK_PROXY_CONTAINER": "coolify-proxy",
        "DEEPSEEK_API_KEY": "",
        "DEEPSEEK_API_KEY_FILE": "",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_FAST_MODEL": "deepseek-v4-flash",
        "DEEPSEEK_PRECISION_MODEL": "deepseek-v4-pro",
        "DEEPSEEK_DEFAULT_MODE": "fast",
        "DEEPSEEK_DAILY_REQUEST_LIMIT": "60",
        "DEEPSEEK_DAILY_TOKEN_LIMIT": "600000",
        "DEEPSEEK_MAX_INPUT_CHARACTERS": "60000",
        "DEEPSEEK_MAX_OUTPUT_TOKENS": "3000",
        "DEEPSEEK_REQUEST_TIMEOUT_SECONDS": "75",
        "DEEPSEEK_CIRCUIT_BREAKER_FAILURES": "3",
        "DEEPSEEK_CIRCUIT_BREAKER_MINUTES": "15",
        "PRIVATE_DATABASE_CLIENT_PATH": "tools/private_db_client.py",
        "PRIVATE_DATABASE_AREA": "Private-MetaDatabase",
        "PRIVATE_DATABASE_TARGET_PATH": "products/jobhuntos-online/current.json",
        "R2_SYNC_ENABLED": "false",
        "RCLONE_R2_REMOTE": "",
    }
    output.write_text(
        "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    output.chmod(0o600)

    login_file = output.parent / "OWNER_LOGIN.txt"
    login_file.write_text(
        f"JobHuntBot Online\n网址：https://{domain}\n登录邮箱：{admin_email}\n"
        f"一次性初始密码：{admin_password}\n数据恢复密钥：{data_recovery_key}\n\n"
        "首次登录后，请在“数据、AI 与安全”中修改初始密码；DeepSeek API Key 也在该页面粘贴一次并验证。请把数据恢复密钥保存到私人密码管理器；"
        "服务器完全丢失后，解密简历和恢复包必须使用该密钥。Owner 安全保存上述信息后，"
        "请从服务器删除本文件。不得提交到 Git、Issue 或聊天。\n",
        encoding="utf-8",
    )
    login_file.chmod(0o600)
    print(f"created: {output}")
    print(f"owner_login: {login_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
