from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings
from .sanitize import assert_public_safe, sanitize_public

APP_VERSION = "v0.0.0.1.3"
EXPECTED_SOURCE_SKILL_VERSION = "1.0.4"
MAX_RESPONSE_BYTES = 1024 * 1024
_VERSION_PATTERN = re.compile(r"(?m)^version:\s*([0-9]+(?:\.[0-9]+){2,})\s*$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_json(url: str, timeout: float) -> tuple[int, dict[str, Any], float]:
    started = time.monotonic()
    request = Request(url, headers={"Accept": "application/json", "User-Agent": f"WeRead-Port-Ops/{APP_VERSION}"})
    with urlopen(request, timeout=timeout) as response:
        status = int(response.status)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise ValueError("unexpected_content_type")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("response_not_object")
    return status, payload, round((time.monotonic() - started) * 1000, 2)


def fetch_text(url: str, timeout: float) -> tuple[int, str, float]:
    started = time.monotonic()
    request = Request(url, headers={"Accept": "text/plain", "User-Agent": f"WeRead-Port-Ops/{APP_VERSION}"})
    with urlopen(request, timeout=timeout) as response:
        status = int(response.status)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
    return status, raw.decode("utf-8", errors="strict"), round((time.monotonic() - started) * 1000, 2)


def project_descriptor(site_url: str) -> dict[str, Any]:
    return {
        "name": "微信读书笔记迁移",
        "url": site_url,
        "parts": ["前台", "运维"],
        "host": "ChatGPT Sites + OVH 运维面",
        "db": "OVH SQLite · 可重建运行日志",
        "store": "Private-Database 事实 + R2/OCI 冷备",
        "deploy": "Sites Version + systemd timers",
        "backup": "Private-Database + R2 + OCI",
        "agent": "无",
        "notify": "status",
    }


def check_site(
    settings: Settings,
    *,
    fetcher: Callable[[str, float], tuple[int, dict[str, Any], float]] = fetch_json,
    at: datetime | None = None,
) -> dict[str, Any]:
    checked_at = at or now_utc()
    base = settings.site_url
    if not base:
        payload = {
            "schemaVersion": 1,
            "service": "weread-port",
            "checkedAt": iso(checked_at),
            "status": "unconfigured",
            "project": project_descriptor(""),
            "productPlane": {
                "configured": False,
                "healthOk": False,
                "versionOk": False,
                "healthHttpStatus": None,
                "versionHttpStatus": None,
                "latencyMs": None,
                "appVersion": None,
                "sourceSkillVersion": None,
                "errorCode": "PRODUCTION_ORIGIN_UNCONFIGURED",
            },
            "operationsPlane": {"status": "operational", "runtimeJournal": "ready"},
            "privacy": {"sensitiveDataRetention": "none", "userContentRetention": "none", "archiveRetention": "none"},
        }
        assert_public_safe(payload)
        return payload
    health_status = version_status = None
    total_latency = 0.0
    error_code = None
    app_version = source_version = None
    health_ok = version_ok = False
    try:
        health_status, health, health_latency = fetcher(f"{base}/healthz", settings.timeout_seconds)
        total_latency += health_latency
        health_ok = health_status == 200 and health.get("ok") is True
        if not health_ok:
            error_code = "HEALTH_CONTRACT_FAILED"
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        error_code = classify_error(exc, "HEALTH")
    try:
        version_status, version, version_latency = fetcher(f"{base}/api/version", settings.timeout_seconds)
        total_latency += version_latency
        app_version = str(version.get("appVersion", "")) or None
        source_version = str(version.get("sourceSkillVersion", "")) or None
        version_ok = version_status == 200 and app_version == APP_VERSION and source_version == EXPECTED_SOURCE_SKILL_VERSION
        if not version_ok and error_code is None:
            error_code = "VERSION_CONTRACT_FAILED"
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        if error_code is None:
            error_code = classify_error(exc, "VERSION")
    service_status = "operational" if health_ok and version_ok else "degraded"
    payload = {
        "schemaVersion": 1,
        "service": "weread-port",
        "checkedAt": iso(checked_at),
        "status": service_status,
        "project": project_descriptor(base),
        "productPlane": {
            "configured": True,
            "siteOrigin": base,
            "healthOk": health_ok,
            "versionOk": version_ok,
            "healthHttpStatus": health_status,
            "versionHttpStatus": version_status,
            "latencyMs": round(total_latency, 2),
            "appVersion": app_version,
            "sourceSkillVersion": source_version,
            "errorCode": error_code,
        },
        "operationsPlane": {"status": "operational", "runtimeJournal": "ready"},
        "privacy": {"sensitiveDataRetention": "none", "userContentRetention": "none", "archiveRetention": "none"},
    }
    clean = sanitize_public(payload)
    assert_public_safe(clean)
    return clean


def check_official_source(
    settings: Settings,
    *,
    fetcher: Callable[[str, float], tuple[int, str, float]] = fetch_text,
    at: datetime | None = None,
) -> dict[str, Any]:
    checked_at = at or now_utc()
    try:
        status, text, latency = fetcher(settings.official_skill_url, settings.timeout_seconds)
        match = _VERSION_PATTERN.search(text[:64_000])
        observed = match.group(1) if match else None
        current = status == 200 and observed == EXPECTED_SOURCE_SKILL_VERSION
        return {
            "checkedAt": iso(checked_at),
            "status": "current" if current else "drift",
            "httpStatus": status,
            "expectedVersion": EXPECTED_SOURCE_SKILL_VERSION,
            "observedVersion": observed,
            "latencyMs": latency,
            "errorCode": None if current else "OFFICIAL_SKILL_VERSION_DRIFT",
        }
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError, OSError) as exc:
        return {
            "checkedAt": iso(checked_at),
            "status": "unavailable",
            "httpStatus": None,
            "expectedVersion": EXPECTED_SOURCE_SKILL_VERSION,
            "observedVersion": None,
            "latencyMs": None,
            "errorCode": classify_error(exc, "OFFICIAL_SKILL"),
        }


def combine_monitor(site: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    payload = dict(site)
    payload["officialSource"] = source
    if payload.get("status") == "operational" and source.get("status") != "current":
        payload["status"] = "degraded"
        product = dict(payload.get("productPlane") or {})
        product["errorCode"] = source.get("errorCode") or "OFFICIAL_SKILL_CHECK_FAILED"
        payload["productPlane"] = product
    clean = sanitize_public(payload)
    assert_public_safe(clean)
    return clean


def write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    clean = sanitize_public(payload)
    assert_public_safe(clean)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(clean, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def classify_error(error: Exception, prefix: str) -> str:
    if isinstance(error, HTTPError):
        return f"{prefix}_HTTP_{error.code}"
    if isinstance(error, TimeoutError):
        return f"{prefix}_TIMEOUT"
    if isinstance(error, URLError):
        return f"{prefix}_NETWORK"
    if isinstance(error, json.JSONDecodeError):
        return f"{prefix}_INVALID_JSON"
    if isinstance(error, ValueError):
        return f"{prefix}_{str(error).upper()}"
    return f"{prefix}_IO"
