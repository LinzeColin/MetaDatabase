from __future__ import annotations

from typing import Any

from social_archive.utils import redact, utcnow


MAX_STATUS_MESSAGE_CHARS = 512


def _safe_text(value: object, *, limit: int = MAX_STATUS_MESSAGE_CHARS) -> str | None:
    if value is None:
        return None
    text = redact(str(value)).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit] if text else None


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _safe_bool(value: object) -> bool:
    return value is True


def _safe_rows(value: object, fields: tuple[str, ...]) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        row: dict[str, object] = {}
        for field in fields:
            raw = item.get(field)
            if field in {"latency_ms", "measured_bytes", "soft_limit_bytes", "hard_limit_bytes", "object_count", "byte_count"}:
                safe = _safe_int(raw)
            elif field in {"enabled", "configured", "authorized", "automatic"}:
                safe = _safe_bool(raw)
            else:
                safe = _safe_text(raw)
            if safe is not None:
                row[field] = safe
        if row:
            result.append(row)
    return result


def sanitize_status_document(document: object) -> dict[str, object]:
    """Publish an allowlisted health summary, never a Runtime or provider payload."""
    raw = document if isinstance(document, dict) else {}
    overall = str(raw.get("overall") or "degraded")
    if overall not in {"healthy", "degraded", "down"}:
        overall = "degraded"
    version = _safe_text(raw.get("version"), limit=64) or "unknown"
    generated_at = _safe_text(raw.get("generated_at"), limit=64) or utcnow()
    return {
        "project": "Social Archive",
        "version": version,
        "generated_at": generated_at,
        "overall": overall,
        # 被声明为「本版本还不能自动读取」的连接器条数。
        # overall 不把它们算作故障，**但也不许把它们藏起来**——
        # 「全绿」盖住「大部分还没做」，是另一种形式的谎。
        "not_yet_supported": max(0, int(raw.get("not_yet_supported") or 0)),
        "connectors": _safe_rows(
            raw.get("connectors"),
            ("connector_id", "display_name", "state", "last_checked_at", "latency_ms", "last_error_code", "last_message_zh", "next_action_zh"),
        ),
        "destinations": _safe_rows(
            raw.get("destinations"),
            ("destination_id", "display_name", "state", "enabled", "configured", "authorized", "automatic", "last_checked_at", "latency_ms", "last_message_zh", "next_action_zh"),
        ),
        "storage": _safe_rows(
            raw.get("storage"),
            ("store_id", "measured_bytes", "soft_limit_bytes", "hard_limit_bytes", "action", "measured_at"),
        ),
        "replicas": _safe_rows(
            raw.get("replicas"),
            ("store_id", "status", "object_count", "byte_count"),
        ),
        # The status host is a non-authoritative projection. Do not copy error
        # details, paths, manifests, or recovery metadata into its public file.
        "recovery": {"last_backup": "unknown", "last_restore_drill": "unknown"},
    }
