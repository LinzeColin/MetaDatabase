"""Deterministic, credential-safe canonical facts for the Private-Database API.

This module deliberately builds facts from the RuntimeStore's completed state;
it never reads or writes a local Private-Database checkout.  The API transport
and the encrypted cold-backup script reuse the exact same serialization so a
backup can only cover facts that were already acknowledged as delivered.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Iterator

from .db import CompletedScanProgress, RuntimeStore
from .utils import json_bytes, redact, sha256_bytes


PRIVATE_DATABASE_EVENT = "private_database_fact"
PRIVATE_DATABASE_FACT_SCHEMA = "1.0"
_SENSITIVE_KEY = re.compile(
    r"(?:token|secret|password|cookie|authorization|credential|api[_-]?key|session|identity|private[_-]?key)",
    re.IGNORECASE,
)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not _SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value))


def _safe_url(value: Any) -> str | None:
    if value is None:
        return None
    raw = redact(str(value))
    try:
        parsed = urllib.parse.urlsplit(raw)
        query = [
            (key, item)
            for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if not _SENSITIVE_KEY.search(key)
        ]
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query, doseq=True), ""))
    except ValueError:
        return raw


def _metadata(raw: Any) -> dict[str, Any]:
    try:
        decoded = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"status": "invalid_json_omitted"}
    sanitized = _safe_value(decoded)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


def completed_content_fact(bundle: dict[str, Any]) -> dict[str, Any]:
    """Serialize a fully replicated content bundle without local paths or secrets."""
    content = {
        "id": str(bundle["id"]),
        "platform": _safe_value(bundle.get("platform")),
        "external_content_id": _safe_value(bundle.get("external_content_id")),
        "canonical_url": _safe_url(bundle.get("canonical_url")),
        "content_type": _safe_value(bundle.get("content_type")),
        "title": _safe_value(bundle.get("title")),
        "author_name": _safe_value(bundle.get("author_name")),
        "published_at": _safe_value(bundle.get("published_at")),
        "first_observed_at": _safe_value(bundle.get("first_observed_at")),
        "last_observed_at": _safe_value(bundle.get("last_observed_at")),
        "availability": _safe_value(bundle.get("availability")),
        "metadata": _metadata(bundle.get("metadata_json")),
    }
    relations = [
        {
            key: _safe_value(row.get(key))
            for key in (
                "id", "source_account_id", "content_id", "relation_type", "collection_key", "status",
                "first_observed_at", "last_observed_at", "missing_complete_scan_count", "closed_at",
            )
        }
        for row in bundle.get("relations", [])
    ]
    artifacts = [
        {
            key: _safe_value(row.get(key))
            for key in (
                "id", "content_id", "archive_level", "artifact_type", "sha256", "byte_size",
                "media_type", "created_at", "status",
            )
        }
        for row in bundle.get("artifacts", [])
    ]
    replicas = [
        {
            key: _safe_value(row.get(key))
            for key in (
                "id", "artifact_id", "store_id", "object_key", "status", "etag", "verified_sha256",
                "original_sha256", "encryption", "updated_at", "last_error_code",
            )
        }
        for row in bundle.get("object_replicas", [])
    ]
    return {
        "schema_version": PRIVATE_DATABASE_FACT_SCHEMA,
        "kind": "social_archive.completed_content",
        "content": content,
        "body": _safe_value(bundle.get("body") or ""),
        "relations": sorted(relations, key=lambda item: str(item["id"])),
        "artifacts": sorted(artifacts, key=lambda item: str(item["id"])),
        "object_replicas": sorted(replicas, key=lambda item: (str(item["artifact_id"]), str(item["store_id"]))),
    }


COMPLETED_SCAN_MAX = 20000
COMPLETED_SCAN_BATCH = 200


def completed_content_facts(store: RuntimeStore, *, limit: int = 100) -> list[dict[str, Any]]:
    """One bounded page of the OLDEST completed facts.  Not a full view.

    Anything that must cover every completed content (sync, backup) uses
    :func:`iter_completed_content_facts`.
    """
    return [completed_content_fact(bundle) for bundle in store.list_completed_content_bundles(limit=limit)]


def iter_completed_content_facts(
    store: RuntimeStore,
    *,
    batch_size: int = COMPLETED_SCAN_BATCH,
    max_scan: int = COMPLETED_SCAN_MAX,
    progress: CompletedScanProgress | None = None,
) -> Iterator[dict[str, Any]]:
    """Every completed content as a fact, oldest first, keyset-paged, bounded by ``max_scan``."""
    for bundle in store.iter_completed_content_bundles(
        batch_size=batch_size, max_scan=max_scan, progress=progress
    ):
        yield completed_content_fact(bundle)


def fact_bytes(fact: dict[str, Any]) -> bytes:
    return json_bytes(fact)


def fact_sha256(fact: dict[str, Any]) -> str:
    return sha256_bytes(fact_bytes(fact))


def delivered_completed_content_facts(
    store: RuntimeStore,
    *,
    limit: int | None = None,
    max_scan: int = COMPLETED_SCAN_MAX,
    progress: CompletedScanProgress | None = None,
) -> list[dict[str, Any]]:
    """Every completed content's current version whose matching outbox ACK exists.

    Walks ALL completed content (keyset-paged); ``limit`` is an optional hard
    cap on the returned facts, not on what is examined.
    """
    delivered: list[dict[str, Any]] = []
    for fact in iter_completed_content_facts(store, max_scan=max_scan, progress=progress):
        content_id = str(fact["content"]["id"])
        event = store.get_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT,
            aggregate_id=content_id,
            payload_sha256=fact_sha256(fact),
        )
        if event and event.get("status") == "delivered":
            delivered.append(fact)
            if limit is not None and len(delivered) >= limit:
                break
    return delivered


@dataclass
class SyncPlan:
    """What one sync pass should deliver, found without holding every fact."""

    completed_total: int = 0
    scanned: int = 0
    scan_truncated_count: int = 0
    already_delivered: int = 0
    never_delivered: int = 0
    changed_since_delivery: int = 0
    selected: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pending_total(self) -> int:
        return self.never_delivered + self.changed_since_delivery


def plan_sync(store: RuntimeStore, *, limit: int, max_scan: int = COMPLETED_SCAN_MAX) -> SyncPlan:
    """Scan every completed content once and pick up to ``limit`` facts to deliver.

    Priority: never delivered first, then delivered-but-changed; inside each
    group oldest ``last_observed_at`` first (the scan order).  Only the facts
    that can be selected are kept -- at most ``2 * limit`` at any moment.
    """
    progress = CompletedScanProgress()
    delivered_ids = store.delivered_outbox_aggregate_ids(event_type=PRIVATE_DATABASE_EVENT)
    plan = SyncPlan()
    never: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for fact in iter_completed_content_facts(store, max_scan=max_scan, progress=progress):
        content_id = str(fact["content"]["id"])
        event = store.get_outbox_event(
            event_type=PRIVATE_DATABASE_EVENT,
            aggregate_id=content_id,
            payload_sha256=fact_sha256(fact),
        )
        if event and event.get("status") == "delivered":
            plan.already_delivered += 1
        elif content_id in delivered_ids:
            plan.changed_since_delivery += 1
            if len(changed) < limit:
                changed.append(fact)
        else:
            plan.never_delivered += 1
            if len(never) < limit:
                never.append(fact)
    plan.completed_total = progress.completed_total
    plan.scanned = progress.scanned
    plan.scan_truncated_count = progress.truncated_count if progress.truncated else 0
    plan.selected = (never + changed)[:limit]
    return plan
