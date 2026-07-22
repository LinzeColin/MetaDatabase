"""Deterministic private projection shared by Markdown and Notion sinks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from x2n_contracts import ErrorCode, canonical_json_sha256

from .canonical_store import CanonicalProjection
from .media_safety import _SCAN_PATTERNS
from .runtime import X2NRuntimeError


PROJECTION_SCHEMA_VERSION = "1.0.0"
UNCLASSIFIED_NAME = "Unclassified"
UNCLASSIFIED_SLUG = "unclassified"
MAX_PROJECTION_TEXT_CHARACTERS = 2_000_000
_LOCAL_PATH_OR_SECRET = re.compile(
    r"(?i)(?:file://|(?:^|[\s'\"])/(?:Users|home|var/folders)/|[A-Z]:\\|(?:authorization|cookie|set-cookie)\s*:)",
)
_CREDENTIAL_MARKERS = ("github" + "_" + "pat" + "_", "gh" + "p" + "_", "secret" + "_")
_CREDENTIAL_VALUE = re.compile(
    r"(?i)(?:" + "|".join(re.escape(marker) for marker in _CREDENTIAL_MARKERS) + r")[A-Za-z0-9_]{16,}"
)


@dataclass(frozen=True)
class ProjectionText:
    """Caller-supplied private Artifact payloads; values never enter public evidence."""

    original_text: str = field(default="", repr=False)
    summary: str = field(default="", repr=False)
    transcript: str = field(default="", repr=False)
    ocr: str = field(default="", repr=False)
    vision: str = field(default="", repr=False)
    classification_reason: str = field(default="", repr=False)

    def values(self) -> tuple[str, ...]:
        return (
            self.original_text,
            self.summary,
            self.transcript,
            self.ocr,
            self.vision,
            self.classification_reason,
        )


@dataclass(frozen=True)
class SinkProjection:
    """Normalized sink input whose hash is independent from file or page identity."""

    canonical: CanonicalProjection
    text: ProjectionText
    desired_projection_hash: str

    @property
    def category_id(self) -> str | None:
        return None if self.canonical.category is None else str(self.canonical.category.category_id)

    @property
    def category_name(self) -> str:
        return UNCLASSIFIED_NAME if self.canonical.category is None else self.canonical.category.name

    @property
    def category_slug(self) -> str:
        return UNCLASSIFIED_SLUG if self.canonical.category is None else self.canonical.category.slug

    @property
    def tags(self) -> tuple[str, ...]:
        return () if self.canonical.classification is None else self.canonical.classification.tags

    @property
    def review_status(self) -> str:
        return (
            "unclassified"
            if self.canonical.classification is None
            else self.canonical.classification.review_status.value
        )

    @property
    def title(self) -> str:
        content = self.canonical.content
        return content.title or f"{content.platform.value} {content.platform_content_id}"

    def hash_payload(self) -> dict[str, Any]:
        content = self.canonical.content
        observation = self.canonical.observation
        classification = self.canonical.classification
        return {
            "artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "artifact_type": item.artifact_type.value,
                    "input_hash": item.input_hash,
                    "processor": item.processor,
                    "processor_version": item.processor_version,
                }
                for item in self.canonical.artifacts
            ],
            "category_id": self.category_id,
            "category_name": self.category_name,
            "category_slug": self.category_slug,
            "classification_id": None if classification is None else classification.classification_id,
            "content": {
                "author_name": content.author_name,
                "canonical_source_url": content.canonical_source_url,
                "content_hash": content.content_hash,
                "content_key": content.content_key,
                "content_type": content.content_type.value,
                "platform": content.platform.value,
                "platform_content_id": content.platform_content_id,
                "published_at": None if content.published_at is None else content.published_at.isoformat(),
                "record_version": content.record_version,
                "title": content.title,
            },
            "observation": {
                "adapter_name": observation.adapter_name,
                "adapter_version": observation.adapter_version,
                "observation_id": observation.observation_id,
                "observed_at": observation.observed_at.isoformat(),
                "raw_text_hash": observation.raw_text_hash,
                "run_id": observation.run_id,
            },
            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
            "relations": list(self.canonical.relations),
            "review_status": self.review_status,
            "tags": list(self.tags),
            "text": {
                "classification_reason": self.text.classification_reason,
                "ocr": self.text.ocr,
                "original_text": self.text.original_text,
                "summary": self.text.summary,
                "transcript": self.text.transcript,
                "vision": self.text.vision,
            },
        }


def validate_persistable_text(value: str) -> None:
    """Reject prohibited media URLs and private references before any sink write."""

    if not isinstance(value, str):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Sink projection text is invalid")
    encoded = value.encode("utf-8")
    if any(pattern.search(encoded) is not None for pattern in _SCAN_PATTERNS.values()):
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Sink projection contains a prohibited URL")
    if _LOCAL_PATH_OR_SECRET.search(value) is not None or _CREDENTIAL_VALUE.search(value) is not None:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Sink projection contains a prohibited private reference")


def _validate_projection_text(text: ProjectionText) -> None:
    values = text.values()
    if any(not isinstance(value, str) for value in values):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Sink projection text is invalid")
    if sum(len(value) for value in values) > MAX_PROJECTION_TEXT_CHARACTERS:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Sink projection text exceeds the local policy")
    validate_persistable_text("\n".join(values))


def build_sink_projection(canonical: CanonicalProjection, text: ProjectionText | None = None) -> SinkProjection:
    value = text or ProjectionText()
    _validate_projection_text(value)
    provisional = SinkProjection(canonical=canonical, text=value, desired_projection_hash="0" * 64)
    validate_persistable_text(
        json.dumps(provisional.hash_payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    return SinkProjection(
        canonical=canonical,
        text=value,
        desired_projection_hash=canonical_json_sha256(provisional.hash_payload()),
    )
