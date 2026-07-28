"""Deterministic Canonical Markdown projection and owner-private atomic sink."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x2n_contracts import ErrorCode, SinkReceipt, build_sink_key

from .canonical_store import CanonicalProjection, CanonicalStore, WriteDisposition
from .runtime import X2NRuntimeError
from .sink_projection import (
    PROJECTION_SCHEMA_VERSION,
    SinkProjection,
    UNCLASSIFIED_NAME,
    UNCLASSIFIED_SLUG,
    validate_persistable_text,
)


MARKDOWN_SINK_SCHEMA_VERSION = "1.1.0"
MARKDOWN_RENDERER_VERSION = "1.1.0"
TRANSITION_BEFORE_ATOMIC_REPLACE = "before_markdown_atomic_replace"
TRANSITION_AFTER_ATOMIC_REPLACE = "after_markdown_atomic_replace"
_FRONTMATTER_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CATEGORY_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_CONTENT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_INDEX_LINK = re.compile(
    r"^- \[(?:\\.|[^\]])*\]\((\.\./\.\./content/[a-z0-9_-]+/[A-Za-z0-9._-]+\.md)\)$"
)
_SUPPORTED_PLATFORM_DIRECTORIES = frozenset(
    {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"}
)


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


@dataclass(frozen=True)
class MarkdownLibraryManifest:
    """A compact, content-free digest of one generated Markdown library."""

    renderer_version: str
    content_count: int
    category_index_count: int
    content_sha256: str
    category_index_sha256: str
    library_sha256: str

    def safe_dict(self) -> dict[str, str | int]:
        return {
            "category_index_count": self.category_index_count,
            "category_index_sha256": self.category_index_sha256,
            "content_count": self.content_count,
            "content_sha256": self.content_sha256,
            "library_sha256": self.library_sha256,
            "renderer_version": self.renderer_version,
        }


@dataclass(frozen=True)
class MarkdownRebuild:
    """Result of a derived-library rebuild; no Canonical payload is exposed."""

    manifest: MarkdownLibraryManifest
    checked_links: int
    content_writes: int
    category_index_writes: int
    removed_content_files: int
    removed_category_indexes: int

    def safe_dict(self) -> dict[str, str | int]:
        return {
            **self.manifest.safe_dict(),
            "category_index_writes": self.category_index_writes,
            "checked_links": self.checked_links,
            "content_writes": self.content_writes,
            "removed_category_indexes": self.removed_category_indexes,
            "removed_content_files": self.removed_content_files,
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


def _payload_digest(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative_path, payload in sorted(entries.items()):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).hexdigest().encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _library_manifest(
    content_entries: dict[str, bytes],
    category_entries: dict[str, bytes],
) -> MarkdownLibraryManifest:
    content_sha256 = _payload_digest(content_entries)
    category_index_sha256 = _payload_digest(category_entries)
    rendered = json.dumps(
        {
            "category_index_count": len(category_entries),
            "category_index_sha256": category_index_sha256,
            "content_count": len(content_entries),
            "content_sha256": content_sha256,
            "renderer_version": MARKDOWN_RENDERER_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return MarkdownLibraryManifest(
        renderer_version=MARKDOWN_RENDERER_VERSION,
        content_count=len(content_entries),
        category_index_count=len(category_entries),
        content_sha256=content_sha256,
        category_index_sha256=category_index_sha256,
        library_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    )


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
        "renderer_version": MARKDOWN_RENDERER_VERSION,
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
        if path != self._library:
            self._ensure_directory(path.parent)
        try:
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown directory could not be created") from None

    def content_path(self, projection: SinkProjection) -> Path:
        target = self._library / self._content_relative_path(projection)
        self._ensure_directory(target.parent)
        return target

    def _atomic_write(
        self,
        target: Path,
        payload: bytes,
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> None:
        try:
            target.relative_to(self._library)
        except ValueError:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown target escaped the library") from None
        self._ensure_directory(target.parent)
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

    def _write_if_changed(
        self,
        target: Path,
        payload: bytes,
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> bool:
        """Atomically write only a changed generated file, preserving no-op rebuilds."""

        if target.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown target is unsafe")
        if target.exists():
            if not target.is_file():
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown target is unsafe")
            try:
                unchanged = target.read_bytes() == payload and stat.S_IMODE(target.stat().st_mode) == 0o600
            except OSError:
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown target could not be read") from None
            if unchanged:
                return False
        self._atomic_write(target, payload, transition_hook=transition_hook)
        return True

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

    @staticmethod
    def _escape_index_label(title: str) -> str:
        return " ".join(title.splitlines()).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")

    @staticmethod
    def _content_relative_path(projection: SinkProjection) -> str:
        content = projection.canonical.content
        platform = content.platform.value
        content_id = content.platform_content_id
        if platform not in _SUPPORTED_PLATFORM_DIRECTORIES or _CONTENT_IDENTIFIER.fullmatch(content_id) is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical Markdown path is invalid")
        return f"content/{platform}/{content_id}.md"

    @staticmethod
    def _category_relative_path(category_slug: str) -> str:
        if _CATEGORY_SLUG.fullmatch(category_slug) is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index path is invalid")
        return f"categories/{category_slug}/INDEX.md"

    def _normalized_projections(
        self,
        projections: Iterable[SinkProjection],
    ) -> tuple[tuple[SinkProjection, str, bytes], ...]:
        """Deduplicate exact projections and reject competing Canonical renderings."""

        by_content_key: dict[str, tuple[SinkProjection, str, bytes]] = {}
        for projection in projections:
            if not isinstance(projection, SinkProjection):
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Markdown rebuild projection is invalid")
            content_key = projection.canonical.content.content_key
            relative_path = self._content_relative_path(projection)
            payload = render_markdown(projection).encode("utf-8")
            current = by_content_key.get(content_key)
            if current is not None:
                if current[1] != relative_path or current[2] != payload:
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED,
                        "Markdown rebuild received competing Canonical projections",
                    )
                continue
            by_content_key[content_key] = (projection, relative_path, payload)
        return tuple(by_content_key[key] for key in sorted(by_content_key))

    def _render_category_index(
        self,
        *,
        category_id: str | None,
        category_slug: str,
        category_name: str,
        entries: Sequence[tuple[SinkProjection, str]],
    ) -> bytes:
        values = {
            "category_id": category_id,
            "category_slug": category_slug,
            "entry_count": len(entries),
            "generated": True,
            "renderer_version": MARKDOWN_RENDERER_VERSION,
            "schema_version": PROJECTION_SCHEMA_VERSION,
        }
        lines = [_frontmatter(values), "", f"# {category_name}", ""]
        for projection, content_relative_path in entries:
            label = self._escape_index_label(projection.title)
            lines.append(f"- [{label}](../../{content_relative_path})")
        if not entries:
            lines.append(f"_No {category_slug} content._")
        payload = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
        try:
            validate_persistable_text(payload.decode("utf-8"))
        except UnicodeDecodeError:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index is not UTF-8") from None
        return payload

    def _expected_library(
        self,
        projections: Iterable[SinkProjection],
    ) -> tuple[dict[str, bytes], dict[str, bytes]]:
        normalized = self._normalized_projections(projections)
        content_entries = {relative_path: payload for _, relative_path, payload in normalized}
        groups: dict[str, tuple[str | None, str, list[tuple[SinkProjection, str]]]] = {
            UNCLASSIFIED_SLUG: (None, UNCLASSIFIED_NAME, [])
        }
        for projection, content_relative_path, _ in normalized:
            category_id = projection.category_id
            category_slug = projection.category_slug
            category_name = projection.category_name
            if category_id is not None and category_slug == UNCLASSIFIED_SLUG:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Owner taxonomy collides with Unclassified")
            current = groups.get(category_slug)
            if current is None:
                groups[category_slug] = (category_id, category_name, [(projection, content_relative_path)])
                continue
            expected_id, expected_name, entries = current
            if expected_id != category_id or expected_name != category_name:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index identity diverged")
            entries.append((projection, content_relative_path))

        category_entries: dict[str, bytes] = {}
        for category_slug, (category_id, category_name, entries) in sorted(groups.items()):
            ordered_entries = sorted(entries, key=lambda item: item[0].canonical.content.content_key)
            relative_path = self._category_relative_path(category_slug)
            category_entries[relative_path] = self._render_category_index(
                category_id=category_id,
                category_slug=category_slug,
                category_name=category_name,
                entries=ordered_entries,
            )
        return content_entries, category_entries

    @staticmethod
    def _safe_directory(path: Path) -> None:
        if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown generated directory is unsafe")

    def _read_generated_entries(self, root: Path, *, category_indexes: bool) -> dict[str, bytes]:
        if not root.exists():
            return {}
        self._safe_directory(root)
        entries: dict[str, bytes] = {}
        for directory in sorted(root.iterdir(), key=lambda item: item.name):
            self._safe_directory(directory)
            if category_indexes:
                if _CATEGORY_SLUG.fullmatch(directory.name) is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index directory is invalid")
                children = tuple(directory.iterdir())
                if len(children) != 1 or children[0].name != "INDEX.md":
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index layout is invalid")
                candidates = children
            else:
                if directory.name not in _SUPPORTED_PLATFORM_DIRECTORIES:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical content directory is invalid")
                candidates = tuple(directory.iterdir())
            for candidate in candidates:
                if candidate.is_symlink() or not candidate.is_file() or stat.S_IMODE(candidate.stat().st_mode) != 0o600:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown generated file is unsafe")
                if not category_indexes and (
                    candidate.suffix != ".md" or _CONTENT_IDENTIFIER.fullmatch(candidate.stem) is None
                ):
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical content filename is invalid")
                relative_path = candidate.relative_to(self._library).as_posix()
                try:
                    payload = candidate.read_bytes()
                    validate_persistable_text(payload.decode("utf-8"))
                except UnicodeDecodeError:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown generated file is not UTF-8") from None
                except OSError:
                    raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown generated file could not be read") from None
                entries[relative_path] = payload
        return entries

    def _remove_generated_file(self, target: Path) -> None:
        try:
            target.relative_to(self._library)
        except ValueError:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown deletion escaped the library") from None
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target.parent, flags)
            status = os.stat(target.name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(status.st_mode):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Markdown generated file is unsafe")
            os.unlink(target.name, dir_fd=descriptor)
            os.fsync(descriptor)
        except X2NRuntimeError:
            raise
        except OSError:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown generated file could not be removed") from None
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown directory close failed") from None

    def _prune_generated_entries(
        self,
        root: Path,
        expected_entries: dict[str, bytes],
        *,
        category_indexes: bool,
    ) -> int:
        existing_entries = self._read_generated_entries(root, category_indexes=category_indexes)
        removed = 0
        for relative_path in sorted(set(existing_entries).difference(expected_entries)):
            self._remove_generated_file(self._library / relative_path)
            removed += 1
        if root.exists():
            self._safe_directory(root)
            for directory in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
                self._safe_directory(directory)
                if any(directory.iterdir()):
                    continue
                try:
                    directory.rmdir()
                except OSError:
                    raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Markdown generated directory could not be removed") from None
        return removed

    def library_manifest(self) -> MarkdownLibraryManifest:
        """Return a deterministic digest of the generated library without contents."""

        return _library_manifest(
            self._read_generated_entries(self._content_root, category_indexes=False),
            self._read_generated_entries(self._category_root, category_indexes=True),
        )

    def _validate_category_links(self, *, only_slug: str | None = None) -> int:
        category_entries = self._read_generated_entries(self._category_root, category_indexes=True)
        checked = 0
        seen_targets: set[str] = set()
        for relative_path, payload in sorted(category_entries.items()):
            index = self._library / relative_path
            category_slug = index.parent.name
            if only_slug is not None and category_slug != only_slug:
                continue
            try:
                frontmatter, body = parse_frontmatter(payload.decode("utf-8"))
            except UnicodeDecodeError:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index is not UTF-8") from None
            if (
                frontmatter.get("generated") is not True
                or frontmatter.get("category_slug") != category_slug
                or frontmatter.get("renderer_version") != MARKDOWN_RENDERER_VERSION
                or frontmatter.get("schema_version") != PROJECTION_SCHEMA_VERSION
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index frontmatter diverged")
            index_links = 0
            for line in body.splitlines():
                match = _INDEX_LINK.fullmatch(line)
                if match is None:
                    if line.startswith("- [") or "](" in line:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index link is invalid")
                    continue
                target_parts = Path(match.group(1)).parts
                if target_parts[:3] != ("..", "..", "content") or len(target_parts) != 5:
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Category index link escaped the library")
                platform, filename = target_parts[3:]
                if platform not in _SUPPORTED_PLATFORM_DIRECTORIES:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index platform is invalid")
                target = self._content_root / platform / filename
                self._safe_directory(self._content_root)
                self._safe_directory(target.parent)
                if target.is_symlink() or not target.is_file() or stat.S_IMODE(target.stat().st_mode) != 0o600:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index contains a dead link")
                target_relative = target.relative_to(self._library).as_posix()
                if target_relative in seen_targets:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category indexes duplicate Canonical content")
                try:
                    content_frontmatter, _ = parse_frontmatter(target.read_text(encoding="utf-8"))
                except OSError:
                    raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Category link target could not be read") from None
                if (
                    content_frontmatter.get("renderer_version") != MARKDOWN_RENDERER_VERSION
                    or content_frontmatter.get("platform") != platform
                    or content_frontmatter.get("platform_content_id") != Path(filename).stem
                    or content_frontmatter.get("content_key") != f"{platform}:{Path(filename).stem}"
                ):
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category link target renderer diverged")
                seen_targets.add(target_relative)
                index_links += 1
                checked += 1
            if frontmatter.get("entry_count") != index_links:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Category index entry count diverged")
        return checked

    def validate_category_links(self) -> int:
        """Verify every generated category link is unique, local, and live."""

        return self._validate_category_links()

    def validate_unclassified_links(self) -> int:
        index = self._category_root / UNCLASSIFIED_SLUG / "INDEX.md"
        if not index.is_file() or index.is_symlink():
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Unclassified index is unavailable")
        return self._validate_category_links(only_slug=UNCLASSIFIED_SLUG)

    def seed_unclassified_index(
        self,
        projections: Iterable[SinkProjection],
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> str:
        """Preserve the Stage 2 seed API while emitting the current renderer format."""

        entries = [
            (projection, relative_path)
            for projection, relative_path, _ in self._normalized_projections(projections)
            if projection.category_slug == UNCLASSIFIED_SLUG
        ]
        payload = self._render_category_index(
            category_id=None,
            category_slug=UNCLASSIFIED_SLUG,
            category_name=UNCLASSIFIED_NAME,
            entries=entries,
        )
        target = self._library / self._category_relative_path(UNCLASSIFIED_SLUG)
        self._write_if_changed(target, payload, transition_hook=transition_hook)
        return hashlib.sha256(payload).hexdigest()

    def rebuild(
        self,
        projections: Iterable[SinkProjection],
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> MarkdownRebuild:
        """Rebuild the complete derived library without changing Canonical or Outbox state."""

        content_entries, category_entries = self._expected_library(projections)
        content_writes = 0
        for relative_path, payload in sorted(content_entries.items()):
            if self._write_if_changed(self._library / relative_path, payload, transition_hook=transition_hook):
                content_writes += 1
        category_index_writes = 0
        for relative_path, payload in sorted(category_entries.items()):
            if self._write_if_changed(self._library / relative_path, payload, transition_hook=transition_hook):
                category_index_writes += 1
        removed_content_files = self._prune_generated_entries(
            self._content_root,
            content_entries,
            category_indexes=False,
        )
        removed_category_indexes = self._prune_generated_entries(
            self._category_root,
            category_entries,
            category_indexes=True,
        )
        manifest = self.library_manifest()
        expected_manifest = _library_manifest(content_entries, category_entries)
        if manifest != expected_manifest:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown rebuild manifest diverged")
        checked_links = self.validate_category_links()
        if checked_links != manifest.content_count:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown rebuild link count diverged")
        return MarkdownRebuild(
            manifest=manifest,
            checked_links=checked_links,
            content_writes=content_writes,
            category_index_writes=category_index_writes,
            removed_content_files=removed_content_files,
            removed_category_indexes=removed_category_indexes,
        )

    def rebuild_from_canonical(
        self,
        projection_builder: Callable[[CanonicalProjection], SinkProjection],
        *,
        transition_hook: Callable[[str], None] | None = None,
    ) -> MarkdownRebuild:
        """Build from one SQLite snapshot while keeping private text selection explicit."""

        if not callable(projection_builder):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Markdown projection builder is invalid")
        projections: list[SinkProjection] = []
        for canonical in self.store.projection_snapshots():
            projection = projection_builder(canonical)
            if not isinstance(projection, SinkProjection) or projection.canonical != canonical:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Markdown projection builder diverged")
            projections.append(projection)
        return self.rebuild(projections, transition_hook=transition_hook)
