from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import unicodedata
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_PATTERN = re.compile(r"(?i)(token|secret|password|cookie|authorization|session)[=: ]+[^\s,;]+")
SHARED_HOST_SECRET_ROOT = Path("/opt/social-archive/runtime/secrets")
CORE_SECRET_UID_GID = 10001


def utcnow() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:32]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonicalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅允许有效的 http/https URL")
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    query = [(k, v) for k, v in query if k.lower() not in tracking]
    clean = urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", urllib.parse.urlencode(query, doseq=True), ""))
    return clean


def assert_public_http_url(value: str, resolve_dns: bool = False) -> str:
    clean = canonicalize_url(value)
    host = urllib.parse.urlsplit(clean).hostname or ""
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("拒绝本机或内网地址")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("拒绝本机或内网地址")
    except ValueError as exc:
        if "拒绝" in str(exc):
            raise
        if resolve_dns:
            for info in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(info[4][0])
                if not ip.is_global:
                    raise ValueError("DNS 解析到了本机或内网地址")
    return clean


def safe_slug(value: str, fallback: str = "item") -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-._")
    return (value[:120] or fallback).lower()


def atomic_write(path: Path, data: bytes, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def redact(value: str) -> str:
    return SECRET_PATTERN.sub(lambda m: f"{m.group(1)}=<已隐藏>", value)


def approved_shared_host_secret(path: Path, *, mode: int, uid: int, gid: int) -> bool:
    """Allow only the documented non-root Docker/systemd Secret bridge.

    Docker Compose file-backed secrets preserve host ownership. Production uses
    uid/gid 10001 for the non-root Core and one dedicated host service group;
    this exception must never make arbitrary 0640 files acceptable.
    """
    try:
        under_runtime_secret_root = path.resolve().is_relative_to(SHARED_HOST_SECRET_ROOT)
    except OSError:
        return False
    return (
        under_runtime_secret_root
        and mode == 0o640
        and uid == CORE_SECRET_UID_GID
        and gid == CORE_SECRET_UID_GID
    )


def read_secret(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    metadata = path.stat()
    mode = metadata.st_mode & 0o777
    runtime_secret = str(path.resolve()).startswith("/run/secrets/")
    shared_host_secret = approved_shared_host_secret(
        path,
        mode=mode,
        uid=metadata.st_uid,
        gid=metadata.st_gid,
    )
    if mode & 0o022 or (not runtime_secret and mode & 0o077 and not shared_host_secret):
        raise PermissionError(
            f"宿主机秘密文件必须为 0600，或为已批准的 10001:10001 0640 运行时 Secret；"
            f"Docker secret 不得可被组/其他用户写入：{path}"
        )
    return path.read_text(encoding="utf-8").strip()
