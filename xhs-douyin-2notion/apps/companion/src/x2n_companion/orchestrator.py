"""Durable current-page walking path for Skeleton004.

This module accepts only the already-sanitized Native Contract. It performs no
browser, network, media, model, Markdown, Notion, shell, or arbitrary-path work.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from x2n_contracts import (
    CanonicalContent,
    ErrorCode,
    SourceObservation,
    UserRelation,
    build_content_key,
    build_relation_key,
    canonical_json_sha256,
)
from x2n_contracts.models import CaptureCurrentPayload

from .canonical_store import (
    CurrentPageReceipt,
    CanonicalStore,
    current_page_identity_from_request,
)
from .runtime import X2NRuntimeError


ADAPTER_VERSION = "1.0.0"
ADAPTER_NAMES = {
    "bilibili": "x2n-bilibili-current-page",
    "douyin": "x2n-douyin-current-page",
    "kuaishou": "x2n-kuaishou-current-page",
    "taobao": "x2n-taobao-current-page",
    "weibo": "x2n-weibo-current-page",
    "xiaohongshu": "x2n-xiaohongshu-current-page",
}
TRANSITION_BEFORE_CANONICAL = "before_canonical_transaction"
TRANSITION_AFTER_CANONICAL = "after_canonical_commit"
TRANSITION_BEFORE_FINALIZE = "before_artifact_finalize"
TRANSITION_AFTER_COMPLETE = "after_completion_commit"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contract(model: Any, payload: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def _page_identity_matches(payload: CaptureCurrentPayload) -> bool:
    parsed = urlsplit(payload.page_url)
    content_id = payload.page_context.content_id
    platform = payload.platform.value
    expected_paths = {
        "bilibili": {f"/video/{content_id}", f"/read/{content_id}"},
        "douyin": {f"/video/{content_id}", f"/note/{content_id}"},
        "kuaishou": {f"/short-video/{content_id}"},
        "taobao": {"/item.htm"},
        "weibo": {f"/detail/{content_id}"},
        "xiaohongshu": {f"/explore/{content_id}"},
    }
    return parsed.path in expected_paths[platform]


def _plan(
    payload: CaptureCurrentPayload,
    *,
    request_id: str,
    payload_hash: str,
    observed_at: str,
) -> tuple[CanonicalContent, UserRelation, SourceObservation, str, str]:
    if payload.category_id is not None:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Category assignment belongs to a downstream Owner-gated Task")
    if not _page_identity_matches(payload):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical page identity does not match page context")
    normalized_payload = payload.model_dump(mode="json", by_alias=True)
    if canonical_json_sha256(normalized_payload) != payload_hash:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Capture payload hash diverged after validation")

    platform = payload.platform.value
    adapter_name = ADAPTER_NAMES[platform]
    identity = current_page_identity_from_request(request_id)
    content_key = build_content_key(platform, payload.page_context.content_id)
    semantic_content = {
        "canonical_source_url": payload.page_url,
        "content_type": payload.page_context.content_type.value,
        "platform": platform,
        "platform_content_id": payload.page_context.content_id,
        "title": payload.page_context.title,
    }
    content_hash = canonical_json_sha256(semantic_content)
    content = _contract(
        CanonicalContent,
        {
            "author_name": None,
            "author_platform_id": None,
            "canonical_source_url": payload.page_url,
            "content_hash": content_hash,
            "content_key": content_key,
            "content_type": payload.page_context.content_type.value,
            "description": None,
            "first_observed_at": observed_at,
            "last_observed_at": observed_at,
            "platform": platform,
            "platform_content_id": payload.page_context.content_id,
            "published_at": None,
            "record_version": 1,
            "schema_version": "1.0",
            "status": "active",
            "title": payload.page_context.title,
        },
    )

    account_ref_hash = hashlib.sha256(f"x2n-local-owner-library-v1:{platform}".encode("utf-8")).hexdigest()
    relation_key = build_relation_key(account_ref_hash, content_key, "saved_current")
    relation = _contract(
        UserRelation,
        {
            "account_ref_hash": account_ref_hash,
            "confirmed_by": "owner",
            "content_key": content_key,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "relation_key": relation_key,
            "relation_type": "saved_current",
            "scan_receipt_id": identity.scan_receipt_id,
            "schema_version": "1.0",
            "source_collection_id": None,
            "source_collection_name_private": None,
            "status": "active",
        },
    )

    title_present = payload.page_context.title is not None
    observation = _contract(
        SourceObservation,
        {
            "adapter_name": adapter_name,
            "adapter_version": ADAPTER_VERSION,
            "completeness": 1.0 if title_present else 0.75,
            "content_key": content_key,
            "ephemeral_media_ref_ids": [],
            "field_provenance": [
                {"confidence": 1.0, "field": "platform_content_id", "source": "dom", "status": "present"},
                {"confidence": 1.0, "field": "canonical_source_url", "source": "derived", "status": "present"},
                {"confidence": 1.0, "field": "content_type", "source": "dom", "status": "present"},
                {
                    "confidence": 1.0 if title_present else None,
                    "field": "title",
                    "source": "dom",
                    "status": "present" if title_present else "unavailable",
                },
            ],
            "normalized_fields": ["platform_content_id", "canonical_source_url", "content_type", "title"],
            "observation_id": identity.observation_id,
            "observed_at": observed_at,
            "raw_text_hash": payload_hash,
            "run_id": identity.run_id,
            "schema_version": "1.0",
            "source_method": "current_page",
            "warning_codes": [],
        },
    )
    return content, relation, observation, adapter_name, ADAPTER_VERSION


class CurrentPageOrchestrator:
    """Two-transaction, replay-safe Canonical Store state machine."""

    def __init__(self, store: CanonicalStore, *, clock: Callable[[], str] = _now) -> None:
        self.store = store
        self.clock = clock

    @staticmethod
    def _notify(hook: Callable[[str], None] | None, transition: str) -> None:
        if hook is not None:
            hook(transition)

    def execute(
        self,
        payload: CaptureCurrentPayload,
        *,
        request_id: str,
        payload_hash: str,
        transition_hook: Callable[[str], None] | None = None,
    ) -> CurrentPageReceipt:
        observed_at = self.clock()
        content, relation, observation, adapter_name, adapter_version = _plan(
            payload,
            request_id=request_id,
            payload_hash=payload_hash,
            observed_at=observed_at,
        )
        self._notify(transition_hook, TRANSITION_BEFORE_CANONICAL)
        receipt = self.store.begin_current_page_capture(
            request_id=request_id,
            payload_hash=payload_hash,
            content=content,
            relation=relation,
            observation=observation,
            adapter_name=adapter_name,
            adapter_version=adapter_version,
        )
        self._notify(transition_hook, TRANSITION_AFTER_CANONICAL)
        if receipt.state == "running":
            self._notify(transition_hook, TRANSITION_BEFORE_FINALIZE)
            receipt = self.store.finalize_current_page_capture(
                receipt.job_id,
                disposition=receipt.disposition,
            )
        self._notify(transition_hook, TRANSITION_AFTER_COMPLETE)
        return receipt

    def resume(self, job_id: str) -> CurrentPageReceipt:
        return self.store.finalize_current_page_capture(job_id)

    def resume_pending(self, *, limit: int = 80) -> tuple[CurrentPageReceipt, ...]:
        return tuple(self.resume(job_id) for job_id in self.store.resumable_current_page_jobs(limit=limit))
