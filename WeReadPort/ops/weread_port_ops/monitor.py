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

APP_VERSION = "v0.0.0.1.7"
EXPECTED_SOURCE_SKILL_VERSION = "1.0.4"
EXPECTED_BUSINESS_GOVERNANCE_SCHEMA_VERSION = "1.0.0"
EXPECTED_BUSINESS_LINE_IDS = {
    "public-trust",
    "weread-direct-export",
    "local-import",
    "normalize-export",
    "chatgpt-handoff",
    "release-supply-chain",
    "operations-recovery",
}
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
            "schemaVersion": 2,
            "service": "weread-port",
            "checkedAt": iso(checked_at),
            "status": "unconfigured",
            "project": project_descriptor(""),
            "productPlane": {
                "configured": False,
                "livenessOk": False,
                "readinessOk": False,
                "publicStatusOk": False,
                "businessGovernanceOk": False,
                "versionOk": False,
                "healthHttpStatus": None,
                "readinessHttpStatus": None,
                "publicStatusHttpStatus": None,
                "versionHttpStatus": None,
                "latencyMs": None,
                "appVersion": None,
                "sourceSkillVersion": None,
                "runtimeMode": None,
                "errorCode": "PRODUCTION_ORIGIN_UNCONFIGURED",
            },
            "businessLines": [],
            "operationsPlane": {"status": "operational", "runtimeJournal": "ready"},
            "privacy": {"sensitiveDataRetention": "none", "userContentRetention": "none", "archiveRetention": "none"},
        }
        assert_public_safe(payload)
        return payload

    statuses: dict[str, int | None] = {"health": None, "readiness": None, "public": None, "version": None}
    latency = 0.0
    errors: list[str] = []
    app_version = source_version = runtime_mode = business_schema_version = None
    liveness_ok = readiness_ok = public_status_ok = business_governance_ok = version_ok = False
    business_lines: list[dict[str, Any]] = []

    def request_json(path: str, prefix: str) -> dict[str, Any] | None:
        nonlocal latency
        try:
            http_status, payload, observed_latency = fetcher(f"{base}{path}", settings.timeout_seconds)
            statuses[prefix] = http_status
            latency += observed_latency
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            errors.append(classify_error(exc, prefix.upper()))
            return None

    health = request_json("/healthz", "health")
    if health is not None:
        liveness_ok = statuses["health"] == 200 and health.get("ok") is True and health.get("status") == "ALIVE"
        if not liveness_ok:
            errors.append("LIVENESS_CONTRACT_FAILED")

    readiness = request_json("/readyz", "readiness")
    if readiness is not None:
        readiness_contract = readiness.get("checks", {}).get("businessGovernanceContract", {}) if isinstance(readiness.get("checks"), dict) else {}
        readiness_ok = (
            statuses["readiness"] == 200
            and readiness.get("ok") is True
            and readiness.get("status") == "READY"
            and readiness_contract.get("ready") is True
            and readiness_contract.get("schemaVersion") == EXPECTED_BUSINESS_GOVERNANCE_SCHEMA_VERSION
        )
        if not readiness_ok:
            errors.append("READINESS_CONTRACT_FAILED")

    public = request_json("/api/status", "public")
    if public is not None:
        boundary = public.get("dataBoundary") if isinstance(public.get("dataBoundary"), dict) else {}
        governance = public.get("businessGovernance") if isinstance(public.get("businessGovernance"), dict) else {}
        raw_lines = governance.get("lines") if isinstance(governance.get("lines"), list) else []
        compact_lines: list[dict[str, Any]] = []
        observed_ids: set[str] = set()
        for raw_line in raw_lines:
            if not isinstance(raw_line, dict):
                continue
            line_id = str(raw_line.get("id", ""))
            observed_ids.add(line_id)
            compact_lines.append({
                "id": line_id,
                "name": str(raw_line.get("name", "")),
                "phase": str(raw_line.get("phase", "")),
                "state": str(raw_line.get("state", "")),
                "dependsOnAll": [str(item) for item in raw_line.get("dependsOnAll", []) if isinstance(item, str)],
                "dependsOnAny": [str(item) for item in raw_line.get("dependsOnAny", []) if isinstance(item, str)],
                "reasonCode": str(raw_line.get("reasonCode", "")) or None,
            })
        business_governance_ok = (
            governance.get("schemaVersion") == EXPECTED_BUSINESS_GOVERNANCE_SCHEMA_VERSION
            and governance.get("graphStatus") == "VALID"
            and observed_ids == EXPECTED_BUSINESS_LINE_IDS
            and len(compact_lines) == len(EXPECTED_BUSINESS_LINE_IDS)
            and all(line.get("state") != "BLOCKED" for line in compact_lines)
            and boundary.get("businessGovernanceContainsUserContent") is False
        )
        if business_governance_ok:
            business_lines = compact_lines
        public_status_ok = (
            statuses["public"] == 200
            and public.get("ok") is True
            and public.get("status") == "OPERATIONAL"
            and boundary.get("serverSideUserNotePersistence") is False
            and boundary.get("serverSideUserKeyPersistence") is False
            and boundary.get("statusContainsUserContent") is False
            and business_governance_ok
        )
        runtime_mode = str(public.get("runtimeMode", "")) or None
        if not business_governance_ok:
            errors.append("BUSINESS_GOVERNANCE_CONTRACT_FAILED")
        if not public_status_ok:
            errors.append("PUBLIC_STATUS_CONTRACT_FAILED")

    version = request_json("/api/version", "version")
    if version is not None:
        app_version = str(version.get("appVersion", "")) or None
        source_version = str(version.get("sourceSkillVersion", "")) or None
        business_schema_version = str(version.get("businessGovernanceSchemaVersion", "")) or None
        version_ok = (
            statuses["version"] == 200
            and app_version == APP_VERSION
            and source_version == EXPECTED_SOURCE_SKILL_VERSION
            and business_schema_version == EXPECTED_BUSINESS_GOVERNANCE_SCHEMA_VERSION
        )
        if not version_ok:
            errors.append("VERSION_CONTRACT_FAILED")

    service_status = "operational" if all((liveness_ok, readiness_ok, public_status_ok, business_governance_ok, version_ok)) else "degraded"
    payload = {
        "schemaVersion": 2,
        "service": "weread-port",
        "checkedAt": iso(checked_at),
        "status": service_status,
        "project": project_descriptor(base),
        "productPlane": {
            "configured": True,
            "siteOrigin": base,
            "livenessOk": liveness_ok,
            "readinessOk": readiness_ok,
            "publicStatusOk": public_status_ok,
            "businessGovernanceOk": business_governance_ok,
            "versionOk": version_ok,
            "healthHttpStatus": statuses["health"],
            "readinessHttpStatus": statuses["readiness"],
            "publicStatusHttpStatus": statuses["public"],
            "versionHttpStatus": statuses["version"],
            "latencyMs": round(latency, 2),
            "appVersion": app_version,
            "sourceSkillVersion": source_version,
            "businessGovernanceSchemaVersion": business_schema_version,
            "runtimeMode": runtime_mode,
            "errorCode": errors[0] if errors else None,
        },
        "businessLines": business_lines,
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
