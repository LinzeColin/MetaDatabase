"""Deterministic Canonical Markdown projection and owner-private atomic sink."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode, SinkReceipt, build_sink_key

from .canonical_store import CanonicalStore, WriteDisposition
from .runtime import X2NRuntimeError
from .sink_projection import (
    PROJECTION_SCHEMA_VERSION,
    SinkProjection,
    UNCLASSIFIED_NAME,
    UNCLASSIFIED_SLUG,
    validate_persistable_text,
)


MARKDOWN_SINK_SCHEMA_VERSION = "1.0.0"
TRANSITION_BEFORE_ATOMIC_REPLACE = "before_markdown_atomic_replace"
TRANSITION_AFTER_ATOMIC_REPLACE = "after_markdown_atomic_replace"
_FRONTMATTER_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_INDEX_LINK = re.compile(r"^- \[.*\]\((\.\./\.\./content/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.md)\)$")


@dataclass(frozen=True)
class MarkdownDelivery:
    event_id: str
    state: str
    disposition: WriteDisposition
    output_hash: str
    object_ref: str

    def safe_dict(self) -> dict[str, str]:
        return {
            "disposition": self.disposition.value,
            "event_id": self.event_id,
            "object_ref": self.object_ref,
            "output_hash": self.output_hash,
            "state": self.state,
        }


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _frontmatter(values: dict[str, Any]) -> str:
    if any(_FRONTMATTER_KEY.fullmatch(key) is None for key in values):
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown frontmatter key is invalid")
    lines = ["---"]
    lines.extend(f"{key}: {_json_value(values[key])}" for key in sorted(values))
    lines.append("---")
    return "\n".join(lines)


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Parse the renderer's deterministic JSON-compatible YAML subset."""

    if not markdown.startswith("---\n") or "\n---\n" not in markdown[4:]:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown frontmatter is unavailable")
    header, body = markdown[4:].split("\n---\n", 1)
    parsed: dict[str, Any] = {}
    for line in header.splitlines():
        key, separator, raw = line.partition(": ")
        if not separator or _FRONTMATTER_KEY.fullmatch(key) is None or key in parsed:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown frontmatter is invalid")
        try:
            parsed[key] = json.loads(raw)
        except json.JSONDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown frontmatter is invalid") from None
    return parsed, body


def render_markdown(projection: SinkProjection) -> str:
    content = projection.canonical.content
    observation = projection.canonical.observation
    classification = projection.canonical.classification
    artifacts = {
        item.artifact_type.value: {
            "artifact_id": item.artifact_id,
            "input_hash": item.input_hash,
            "processor": item.processor,
            "processor_version": item.processor_version,
        }
        for item in projection.canonical.artifacts
    }
    values: dict[str, Any] = {
        "artifact_versions": artifacts,
        "author": content.author_name,
        "canonical_source_url": content.canonical_source_url,
        "captured_at": observation.observed_at.isoformat().replace("+00:00", "Z"),
        "category_slug": projection.category_slug,
        "content_key": content.content_key,
        "content_type": content.content_type.value,
        "platform": content.platform.value,
        "platform_content_id": content.platform_content_id,
        "primary_category": projection.category_name,
        "primary_category_id": projection.category_id,
        "projection_hash": projection.desired_projection_hash,
        "published_at": (
            None if content.published_at is None else content.published_at.isoformat().replace("+00:00", "Z")
        ),
        "record_version": content.record_version,
        "relations": list(projection.canonical.relations),
        "review_status": projection.review_status,
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "tags": list(projection.tags),
    }
    sections = (
        ("Original text", projection.text.original_text),
        ("Summary", projection.text.summary),
        ("Transcript", projection.text.transcript),
        ("OCR", projection.text.ocr),
        ("Vision", projection.text.vision),
        ("Classification rationale", projection.text.classification_reason),
    )
    title = " ".join(projection.title.splitlines()).strip()
    body: list[str] = [f"# {title}"]
    for heading, text in sections:
        body.extend(("", f"## {heading}", "", text if text else "_Not available in this projection._"))
    provenance = {
        "adapter_name": observation.adapter_name,
        "adapter_version": observation.adapter_version,
        "artifact_ids": [item.artifact_id for item in projection.canonical.artifacts],
        "classification_id": None if classification is None else classification.classification_id,
        "observation_id": observation.observation_id,
        "raw_text_hash": observation.raw_text_hash,
        "run_id": observation.run_id,
    }
    body.extend(
        (
            "",
            "## Provenance",
            "",
            "```json",
            json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
        )
    )
    rendered = _frontmatter(values) + "\n\n" + "\n".join(body).rstrip() + "\n"
    validate_persistable_text(rendered)
    parsed, _ = parse_frontmatter(rendered)
    if parsed.get("projection_hash") != projection.desired_projection_hash:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown projection hash diverged")
    return rendered


class MarkdownSink:
    """Outbox-backed Markdown sink with deterministic, recoverable writes."""

    def __init__(self, store: CanonicalStore) -> None:
        self.store = store
        self.paths = store.paths
        self._library = self.paths.data_root / "runtime/library"
        self._content_root = self._library / "content"
        self._category_root = self._library / "categories"

    def _ensure_directory(self, path: Path) -> None:
        try:
            path.relative_to(self._library)
        except ValueError:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown directory escaped the library") from None
        if path.exists():
            if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown directory is unsafe")
            return
        try:
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown directory could not be created") from None

    def content_path(self, projection: SinkProjection) -> Path:
        content = projection.canonical.content
        platform_directory = self._content_root / content.platform.value
        self._ensure_directory(platform_directory)
        target = platform_directory / f"{content.platform_content_id}.md"
        if target.parent != platform_directory:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown path is unsafe")
        return target

    def _atomic_write(
        self,
        target: Path,
        payload: bytes,
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> None:
        temporary_name = f".{target.name}.tmp-{uuid.uuid4().hex}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        directory_descriptor: int | None = None
        try:
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                directory_flags |= os.O_NOFOLLOW
            directory_descriptor = os.open(target.parent, directory_flags)
            try:
                target_status = os.stat(target.name, dir_fd=directory_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                target_status = None
            if target_status is not None and not stat.S_ISREG(target_status.st_mode):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown target is unsafe")
            descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_descriptor)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fchmod(handle.fileno(), 0o600)
                os.fsync(handle.fileno())
            if transition_hook is not None:
                transition_hook(TRANSITION_BEFORE_ATOMIC_REPLACE)
            os.replace(
                temporary_name,
                target.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
            if transition_hook is not None:
                transition_hook(TRANSITION_AFTER_ATOMIC_REPLACE)
        except X2NRuntimeError:
            raise
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown atomic write failed") from None
        except BaseException:
            raise
        finally:
            if directory_descriptor is not None:
                cleanup_failed = False
                try:
                    os.unlink(temporary_name, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    pass
                except OSError:
                    cleanup_failed = True
                try:
                    os.close(directory_descriptor)
                except OSError:
                    cleanup_failed = True
                if cleanup_failed:
                    raise X2NRuntimeError(
                        ErrorCode.STORAGE_FAILED,
                        "Markdown temporary file cleanup failed",
                    ) from None

    @staticmethod
    def _receipt(projection: SinkProjection, output_hash: str, delivered_at: str) -> SinkReceipt:
        content_key = projection.canonical.content.content_key
        identity = hashlib.sha256(
            f"markdown:{content_key}:{projection.desired_projection_hash}:{MARKDOWN_SINK_SCHEMA_VERSION}".encode(
                "utf-8"
            )
        ).hexdigest()
        return SinkReceipt.model_validate_json(
            json.dumps(
                {
                    "content_key": content_key,
                    "delivered_at": delivered_at,
                    "desired_projection_hash": projection.desired_projection_hash,
                    "external_ref_hash": None,
                    "output_hash": output_hash,
                    "receipt_id": f"receipt_markdown_{identity[:32]}",
                    "run_id": projection.canonical.observation.run_id,
                    "schema_version": "1.0",
                    "sink": "markdown",
                    "sink_key": build_sink_key("markdown", content_key, MARKDOWN_SINK_SCHEMA_VERSION),
                    "sink_object_ref": f"sinkref_markdown_{identity[:32]}",
                    "sink_schema_version": MARKDOWN_SINK_SCHEMA_VERSION,
                    "status": "verified",
                },
                ensure_ascii=False,
            )
        )

    def deliver(
        self,
        projection: SinkProjection,
        *,
        now: str,
        transition_hook: Callable[[str], None] | None = None,
    ) -> MarkdownDelivery:
        rendered = render_markdown(projection).encode("utf-8")
        output_hash = hashlib.sha256(rendered).hexdigest()
        disposition, event_id = self.store.enqueue_outbox(
            sink="markdown",
            content_key=projection.canonical.content.content_key,
            desired_projection_hash=projection.desired_projection_hash,
            sink_schema_version=MARKDOWN_SINK_SCHEMA_VERSION,
            now=now,
        )
        state = self.store.outbox_state(event_id)
        if state is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown Outbox event is unavailable")
        target = self.content_path(projection)
        object_ref = self._receipt(projection, output_hash, now).sink_object_ref
        if state.status == "delivered":
            if not target.is_file() or target.is_symlink():
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Delivered Markdown projection is missing")
            try:
                observed_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            except OSError:
                raise X2NRuntimeError(
                    ErrorCode.STORAGE_FAILED,
                    "Delivered Markdown projection could not be read",
                ) from None
            if observed_hash != output_hash:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Delivered Markdown projection drifted")
            return MarkdownDelivery(event_id, "delivered", WriteDisposition.UNCHANGED, output_hash, object_ref)
        claim = self.store.claim_outbox(
            worker_id="markdown-worker-v1",
            sink="markdown",
            event_id=event_id,
            now=now,
        )
        if claim is None:
            return MarkdownDelivery(event_id, state.status, disposition, output_hash, object_ref)
        if claim.event_id != event_id:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown worker claimed an unexpected event")
        self._atomic_write(target, rendered, transition_hook=transition_hook)
        receipt = self._receipt(projection, output_hash, now)
        self.store.complete_outbox(claim, receipt)
        return MarkdownDelivery(event_id, "delivered", disposition, output_hash, receipt.sink_object_ref)

    def seed_unclassified_index(
        self,
        projections: Iterable[SinkProjection],
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> str:
        entries: list[tuple[str, str, str, str]] = []
        for projection in projections:
            if projection.category_slug != UNCLASSIFIED_SLUG:
                continue
            content = projection.canonical.content
            entries.append((content.content_key, content.platform.value, content.platform_content_id, projection.title))
        entries.sort(key=lambda item: item[0])
        self._ensure_directory(self._category_root / UNCLASSIFIED_SLUG)
        target = self._category_root / UNCLASSIFIED_SLUG / "INDEX.md"
        values = {
            "category_id": None,
            "category_slug": UNCLASSIFIED_SLUG,
            "entry_count": len(entries),
            "generated": True,
            "schema_version": PROJECTION_SCHEMA_VERSION,
        }
        lines = [_frontmatter(values), "", f"# {UNCLASSIFIED_NAME}", ""]
        for _, platform, content_id, title in entries:
            label = " ".join(title.splitlines()).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
            lines.append(f"- [{label}](../../content/{platform}/{content_id}.md)")
        if not entries:
            lines.append("_No unclassified content._")
        payload = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
        validate_persistable_text(payload.decode("utf-8"))
        self._atomic_write(target, payload, transition_hook=transition_hook)
        return hashlib.sha256(payload).hexdigest()

    def validate_unclassified_links(self) -> int:
        index = self._category_root / UNCLASSIFIED_SLUG / "INDEX.md"
        if not index.is_file() or index.is_symlink():
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Unclassified index is unavailable")
        checked = 0
        for line in index.read_text(encoding="utf-8").splitlines():
            match = _INDEX_LINK.fullmatch(line)
            if match is None:
                continue
            target = (index.parent / match.group(1)).resolve(strict=False)
            try:
                target.relative_to(self._library)
            except ValueError:
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Category index link escaped the library") from None
            if not target.is_file() or target.is_symlink():
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index contains a dead link")
            checked += 1
        return checked
