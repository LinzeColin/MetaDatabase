#!/usr/bin/env python3
"""阅迁 v0.0.0.1.9 部署前确定性检查；绝不输出 Secret 值。"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

VERSION = "v0.0.0.1.9"
EXPECTED_ORIGIN = "https://weread.linzezhang.com"
EXPECTED_ADMIN_ORIGIN = "https://admin.weread.linzezhang.com"
REQUIRED = (
    "NODE_ENV", "WRP_PUBLIC_BASE_URL", "WRP_ADMIN_BASE_URL", "WRP_ADMIN_ACCOUNT_IDS", "WRP_SERVICE_HOST", "WRP_SERVICE_PORT", "WRP_EDGE_BRIDGE_HOST", "WRP_EDGE_BRIDGE_PORT",
    "WRP_DATABASE_PATH", "WRP_OBJECT_STORE_MODE", "WRP_SESSION_PEPPER",
    "WRP_CREDENTIAL_PEPPER", "WRP_KEYRING_JSON", "WRP_ACTIVE_KEY_ID",
    "WRP_INTERNAL_PROXY_SECRET", "WRP_R2_ENDPOINT", "WRP_R2_BUCKET",
    "WRP_R2_ACCESS_KEY_ID", "WRP_R2_SECRET_ACCESS_KEY", "WRP_GOOGLE_CLIENT_ID",
    "WRP_GOOGLE_CLIENT_SECRET", "WRP_GITHUB_CLIENT_ID", "WRP_GITHUB_CLIENT_SECRET",
    "WRP_NOTION_CLIENT_ID", "WRP_NOTION_CLIENT_SECRET", "WRP_PRIVATE_DATABASE_CLIENT_PATH",
    "WRP_PRIVATE_DATABASE_CLIENT_SHA256", "WRP_PRIVATE_DATABASE_AREA", "WRP_PRIVATE_DATABASE_DOMAIN",
    "WRP_PRIVATE_DATABASE_GH_TOKEN",
    "WRP_TASKPACK_VERSION", "WRP_RELEASE_COMMIT", "WRP_OVH_RELEASE_ID", "WRP_SITES_PROJECT_ID",
    "WRP_PRIMARY_OBJECT_PREFIX", "WRP_PRIVATE_DATABASE_BACKUP_PREFIX",
    "WRP_PRIVATE_DATABASE_R2_BACKUP_TARGET", "WRP_R2_RCLONE_SOURCE", "WRP_OCI_RCLONE_TARGET",
)
PLACEHOLDER = re.compile(r"(?:example\.invalid|replace|changeme|your[-_ ]|account_id|^secret$|base64-32|same-as)", re.I)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_environment(values: dict[str, str], *, env_file: Path | None = None, require_paths: bool = False) -> dict:
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def block(code: str, field: str, message: str) -> None:
        blockers.append({"code": code, "field": field, "message": message})

    def warn(code: str, field: str, message: str) -> None:
        warnings.append({"code": code, "field": field, "message": message})

    for key in REQUIRED:
        if not values.get(key, "").strip():
            block("MISSING", key, "必填部署输入缺失。")
        elif PLACEHOLDER.search(values[key].strip()):
            block("PLACEHOLDER", key, "仍是示例或占位值。")

    if values.get("NODE_ENV") != "production":
        block("NODE_ENV", "NODE_ENV", "生产部署必须为 production。")
    origin = values.get("WRP_PUBLIC_BASE_URL", "")
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        block("PUBLIC_URL", "WRP_PUBLIC_BASE_URL", "必须是无路径、无查询参数的 HTTPS origin。")
    elif origin.rstrip("/") != EXPECTED_ORIGIN:
        block("TARGET_DOMAIN", "WRP_PUBLIC_BASE_URL", f"当前版本冻结域名必须为 {EXPECTED_ORIGIN}。")
    admin_origin = values.get("WRP_ADMIN_BASE_URL", "")
    admin_parsed = urlparse(admin_origin)
    if admin_parsed.scheme != "https" or not admin_parsed.netloc or admin_parsed.path not in ("", "/") or admin_parsed.query or admin_parsed.fragment:
        block("ADMIN_URL", "WRP_ADMIN_BASE_URL", "必须是无路径、无查询参数的 HTTPS origin。")
    elif admin_origin.rstrip("/") != EXPECTED_ADMIN_ORIGIN:
        block("ADMIN_DOMAIN", "WRP_ADMIN_BASE_URL", f"当前版本管理域必须为 {EXPECTED_ADMIN_ORIGIN}。")
    admin_ids = [item.strip() for item in values.get("WRP_ADMIN_ACCOUNT_IDS", "").split(",") if item.strip()]
    if not admin_ids or any(not re.fullmatch(r"acct_[A-Za-z0-9_-]{8,200}", item) for item in admin_ids):
        block("ADMIN_ACCOUNTS", "WRP_ADMIN_ACCOUNT_IDS", "必须配置至少一个有效的不可变管理员账户 ID。")
    if values.get("WRP_SERVICE_HOST") not in {"127.0.0.1", "::1"}:
        block("BIND_ADDRESS", "WRP_SERVICE_HOST", "账户服务必须只监听回环地址。")
    try:
        port = int(values.get("WRP_SERVICE_PORT", ""))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        block("PORT", "WRP_SERVICE_PORT", "必须是 1–65535 的整数。")
    edge_host = values.get("WRP_EDGE_BRIDGE_HOST", "")
    try:
        edge_address = ipaddress.ip_address(edge_host)
        edge_octets = str(edge_address).split(".")
        rfc1918 = edge_address.version == 4 and (
            edge_octets[0] == "10"
            or (edge_octets[0] == "172" and 16 <= int(edge_octets[1]) <= 31)
            or (edge_octets[0] == "192" and edge_octets[1] == "168")
        )
        if not rfc1918:
            raise ValueError
    except ValueError:
        block("EDGE_BRIDGE_ADDRESS", "WRP_EDGE_BRIDGE_HOST", "必须是非回环 RFC1918 Docker 私网 IPv4 地址。")
    if edge_host != "10.0.1.1":
        block("EDGE_BRIDGE_TARGET", "WRP_EDGE_BRIDGE_HOST", "当前 socket 桥接固定监听 Coolify 网桥网关 10.0.1.1。")
    try:
        edge_port = int(values.get("WRP_EDGE_BRIDGE_PORT", ""))
        if not 1 <= edge_port <= 65535:
            raise ValueError
    except ValueError:
        block("EDGE_BRIDGE_PORT", "WRP_EDGE_BRIDGE_PORT", "必须是 1–65535 的整数。")
    else:
        if edge_port != 8789:
            block("EDGE_BRIDGE_TARGET", "WRP_EDGE_BRIDGE_PORT", "当前 socket 桥接固定监听 8789 端口。")
    db_path = Path(values.get("WRP_DATABASE_PATH", "") or ".")
    if not db_path.is_absolute():
        block("DATABASE_PATH", "WRP_DATABASE_PATH", "SQLite 路径必须是绝对路径。")
    if values.get("WRP_OBJECT_STORE_MODE") != "r2":
        block("OBJECT_MODE", "WRP_OBJECT_STORE_MODE", "生产用户正文必须使用 R2 加密对象平面。")
    if values.get("WRP_TASKPACK_VERSION") != VERSION:
        block("TASKPACK_VERSION", "WRP_TASKPACK_VERSION", f"必须精确等于 {VERSION}。")
    if not re.fullmatch(r"[0-9a-f]{40}", values.get("WRP_RELEASE_COMMIT", "")):
        block("RELEASE_COMMIT", "WRP_RELEASE_COMMIT", "必须是 40 位小写 Git SHA。")
    for field in ("WRP_OVH_RELEASE_ID", "WRP_SITES_PROJECT_ID"):
        if not re.fullmatch(r"[A-Za-z0-9._:-]{3,160}", values.get(field, "")):
            block("RELEASE_ID", field, "部署身份格式无效。")
    if values.get("WRP_PRIMARY_OBJECT_PREFIX") != "primary-objects":
        block("R2_PRIMARY_NAMESPACE", "WRP_PRIMARY_OBJECT_PREFIX", "权威隐私对象必须写入 primary-objects。")
    if values.get("WRP_PRIVATE_DATABASE_BACKUP_PREFIX") != "backups/private-database":
        block("R2_BACKUP_NAMESPACE", "WRP_PRIVATE_DATABASE_BACKUP_PREFIX", "Private-Database 冷备必须写入 backups/private-database。")
    backup_target = values.get("WRP_PRIVATE_DATABASE_R2_BACKUP_TARGET", "")
    if "backups/private-database" not in backup_target or not re.fullmatch(r"[^\s:]+:.+", backup_target):
        block("PRIVATE_DATABASE_R2_TARGET", "WRP_PRIVATE_DATABASE_R2_BACKUP_TARGET", "必须是指向 backups/private-database 的 rclone 远端路径。")
    if not values.get("WRP_R2_RCLONE_SOURCE") or not values.get("WRP_OCI_RCLONE_TARGET"):
        block("OCI_BACKUP", "WRP_R2_RCLONE_SOURCE/WRP_OCI_RCLONE_TARGET", "R2 到 OCI 异地冷备必须配置。")
    _check_b64(values.get("WRP_SESSION_PEPPER", ""), "WRP_SESSION_PEPPER", block)
    _check_b64(values.get("WRP_CREDENTIAL_PEPPER", ""), "WRP_CREDENTIAL_PEPPER", block)
    try:
        keyring = json.loads(values.get("WRP_KEYRING_JSON", "{}"))
        if not isinstance(keyring, dict) or not keyring:
            raise ValueError
        for key_id, material in keyring.items():
            if not isinstance(key_id, str) or not key_id or len(base64.b64decode(str(material), validate=True)) < 32:
                raise ValueError
        if values.get("WRP_ACTIVE_KEY_ID") not in keyring:
            block("ACTIVE_KEY", "WRP_ACTIVE_KEY_ID", "活动密钥 ID 不在 WRP_KEYRING_JSON。")
    except (ValueError, TypeError, json.JSONDecodeError):
        block("KEYRING", "WRP_KEYRING_JSON", "必须是至少含一个 32 字节 Base64 密钥的 JSON 对象。")
    if len(values.get("WRP_INTERNAL_PROXY_SECRET", "")) < 32:
        block("INTERNAL_SECRET", "WRP_INTERNAL_PROXY_SECRET", "内部代理共享 Secret 至少 32 个字符。")
    r2 = urlparse(values.get("WRP_R2_ENDPOINT", ""))
    if r2.scheme != "https" or not r2.netloc or r2.query or r2.fragment:
        block("R2_ENDPOINT", "WRP_R2_ENDPOINT", "R2 endpoint 必须是 HTTPS URL。")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", values.get("WRP_R2_BUCKET", "")):
        block("R2_BUCKET", "WRP_R2_BUCKET", "R2 bucket 名称格式无效。")
    for name in ("WRP_UPSTREAM_TIMEOUT_MS", "WRP_UPSTREAM_RETRY_ATTEMPTS", "WRP_AUTH_FAILURE_LIMIT", "WRP_AUTH_LOCK_SECONDS", "WRP_IMPORT_LEASE_SECONDS", "WRP_WORKER_STALE_SECONDS"):
        if name in values and values[name]:
            try:
                if int(values[name]) <= 0:
                    raise ValueError
            except ValueError:
                block("INTEGER", name, "必须是正整数。")
    area = values.get("WRP_PRIVATE_DATABASE_AREA", "")
    if area != "Private-MetaDatabase":
        block("PRIVATE_DATABASE_AREA", "WRP_PRIVATE_DATABASE_AREA", "阅迁结构化事实必须写入 Private-MetaDatabase。")
    domain = values.get("WRP_PRIVATE_DATABASE_DOMAIN", "")
    if domain and not re.fullmatch(r"[A-Za-z0-9._:-]{3,80}", domain):
        block("PRIVATE_DATABASE_DOMAIN", "WRP_PRIVATE_DATABASE_DOMAIN", "Private-Database domain 标识格式无效。")
    token = values.get("WRP_PRIVATE_DATABASE_GH_TOKEN", "")
    if token and len(token) < 20:
        block("PRIVATE_DATABASE_TOKEN", "WRP_PRIVATE_DATABASE_GH_TOKEN", "clone-free 客户端令牌格式无效。")
    client_raw = values.get("WRP_PRIVATE_DATABASE_CLIENT_PATH", "")
    expected_client_sha = values.get("WRP_PRIVATE_DATABASE_CLIENT_SHA256", "")
    if client_raw:
        client = Path(client_raw).expanduser()
        if not client.is_absolute():
            block("PRIVATE_DATABASE_CLIENT", "WRP_PRIVATE_DATABASE_CLIENT_PATH", "clone-free 客户端路径必须是绝对路径。")
        elif require_paths:
            if not client.is_file():
                block("PRIVATE_DATABASE_CLIENT", "WRP_PRIVATE_DATABASE_CLIENT_PATH", "目标机上未找到 canonical clone-free Private-Database 客户端。")
            elif re.fullmatch(r"[0-9a-f]{64}", expected_client_sha) and _sha256(client) != expected_client_sha:
                block("PRIVATE_DATABASE_CLIENT_HASH", "WRP_PRIVATE_DATABASE_CLIENT_SHA256", "客户端 SHA-256 与冻结 canonical 身份不一致。")
    if expected_client_sha and not re.fullmatch(r"[0-9a-f]{64}", expected_client_sha):
        block("PRIVATE_DATABASE_CLIENT_HASH", "WRP_PRIVATE_DATABASE_CLIENT_SHA256", "客户端 SHA-256 必须是 64 位小写十六进制。")
    if env_file and env_file.exists():
        mode = stat.S_IMODE(env_file.stat().st_mode)
        if mode & 0o077:
            block("ENV_PERMISSIONS", str(env_file), "环境文件权限必须不高于 0600。")
    callback_urls = {
        provider: f"{origin.rstrip('/')}/api/platform/v1/oauth/{provider}/callback"
        for provider in ("google", "github", "notion") if origin
    }
    return {
        "status": "PASS" if not blockers else "BLOCKED",
        "version": VERSION,
        "blockers": sorted(blockers, key=lambda item: (item["field"], item["code"])),
        "warnings": sorted(warnings, key=lambda item: (item["field"], item["code"])),
        "oauthCallbackUrls": callback_urls,
        "secretValuesPrinted": False,
        "next": "可执行安装与部署" if not blockers else "只补齐 blockers 中列出的 Owner 输入；不得修改产品代码或版本号",
    }


def _check_b64(raw: str, field: str, block) -> None:
    try:
        if len(base64.b64decode(raw, validate=True)) < 32:
            raise ValueError
    except (ValueError, TypeError):
        block("BASE64_SECRET", field, "必须是至少 32 字节的 Base64 随机值。")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--require-paths", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if not args.env_file.is_file():
        payload = {"status": "BLOCKED", "version": VERSION, "blockers": [{"code": "ENV_FILE", "field": str(args.env_file), "message": "环境文件不存在。"}], "warnings": [], "secretValuesPrinted": False}
    else:
        payload = check_environment(read_env(args.env_file), env_file=args.env_file, require_paths=args.require_paths)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" or not args.strict else 3


if __name__ == "__main__":
    raise SystemExit(main())
