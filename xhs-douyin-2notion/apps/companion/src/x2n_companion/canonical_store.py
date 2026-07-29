"""SQLite Canonical Store, recovery primitives, outbox, and leases."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from x2n_contracts import (
    Artifact,
    CapabilityManifest,
    CanonicalContent,
    Classification,
    DuplicateDisposition,
    ErrorCode,
    SinkReceipt,
    SourceObservation,
    TaxonomyCategory,
    UserRelation,
    build_artifact_key,
)
from x2n_contracts.models import SyncScopeId

from .adapter_dispatch import SCOPE_BINDINGS, ScopeBinding
from .migrations import (
    LATEST_SCHEMA_VERSION,
    current_version,
    migrate_backward,
    migrate_forward,
    schema_snapshot,
)
from .runtime import RuntimePaths, X2NRuntimeError, _atomic_private_json
from .taxonomy import TaxonomyRevision


SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MEDIA_LEASE_ID = re.compile(r"^media_[0-9a-f]{32}$")
MEDIA_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
MAX_MEDIA_LEASE_SECONDS = 24 * 60 * 60
PENDING_MEDIA_SHA256 = "0" * 64
PENDING_MEDIA_MIME = "application/x-x2n-pending"
HEALTHY_CHECKS: dict[str, str | int] = {
    "foreign_key_check": "ok",
    "foreign_key_violations": 0,
    "integrity_check": "ok",
    "quick_check": "ok",
}
CURRENT_PAGE_RUN_KIND = "current_page_capture_v1"
CURRENT_PAGE_CURSOR_CANONICAL = "canonical_committed"
CURRENT_PAGE_CURSOR_COMPLETE = "artifact_placeholder_committed"
CURRENT_PAGE_RESUME_VERSION = "orchestrator-1.0.0"
CURRENT_PAGE_PLACEHOLDER_PROCESSOR = "x2n-canonical-placeholder"
CURRENT_PAGE_PLACEHOLDER_VERSION = "placeholder-1.0.0"
SCOPE_SYNC_RUN_KIND = "native_scope_dispatch_v1"
LIFECYCLE_TOMBSTONE_KINDS = frozenset({"content", "relation", "sink", "runtime"})
OWNER_MVP_LIST_BASELINE_SCOPES: dict[SyncScopeId, tuple[str, str, str, str, str]] = {
    SyncScopeId.XIAOHONGSHU_FAVORITES: (
        "xiaohongshu",
        "favorited",
        "receipt_xhsfav_",
        "run_xhsfav_",
        "checkpoint_xhsfav_",
    ),
    SyncScopeId.DOUYIN_FAVORITES: ("douyin", "favorited", "receipt_dy_", "run_dy_", "checkpoint_dy_"),
    SyncScopeId.DOUYIN_LIKES: ("douyin", "liked", "receipt_dy_", "run_dy_", "checkpoint_dy_"),
}


class WriteDisposition(str, Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class BackupReceipt:
    backup_id: str
    database_sha256: str
    logical_sha256: str
    schema_version: int
    size_bytes: int
    table_counts: dict[str, int]

    def safe_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "database_sha256": self.database_sha256,
            "logical_sha256": self.logical_sha256,
            "schema_version": self.schema_version,
            "size_bytes": self.size_bytes,
            "table_counts": dict(sorted(self.table_counts.items())),
        }


@dataclass(frozen=True)
class LifecycleState:
    """Private lifecycle state whose safe form contains no target identifiers."""

    deletion_epoch: int
    durability_state: str
    latest_manifest_sha256: str | None
    updated_at: str

    def safe_dict(self) -> dict[str, Any]:
        return {
            "deletion_epoch": self.deletion_epoch,
            "durability_state": self.durability_state,
            "latest_manifest_sha256": self.latest_manifest_sha256,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class LifecycleTombstone:
    """Append-only logical delete record; private target keys never leave Runtime."""

    tombstone_id: str
    target_kind: str
    target_key_private: str = field(repr=False)
    target_key_sha256: str
    deletion_epoch: int
    created_at: str

    def safe_dict(self) -> dict[str, Any]:
        return {
            "deletion_epoch": self.deletion_epoch,
            "target_key_sha256": self.target_key_sha256,
            "target_kind": self.target_kind,
            "tombstone_id": self.tombstone_id,
        }


@dataclass(frozen=True)
class OutboxClaim:
    event_id: str
    lease_id: str
    sink: str
    content_key: str
    desired_projection_hash: str
    sink_schema_version: str
    attempt_count: int


@dataclass(frozen=True)
class OutboxState:
    """Public-safe durable delivery state without sink payloads or private refs."""

    event_id: str
    sink: str
    content_key: str
    desired_projection_hash: str
    sink_schema_version: str
    status: str
    attempt_count: int
    not_before: str
    last_error_code: str | None


@dataclass(frozen=True)
class NotionMapping:
    """Private Runtime mapping; page_ref must never enter a public receipt."""

    content_key: str
    page_ref: str = field(repr=False)
    external_ref_hash: str


@dataclass(frozen=True)
class CanonicalProjection:
    """Private Canonical snapshot consumed by deterministic derived sinks."""

    content: CanonicalContent
    relations: tuple[str, ...]
    observation: SourceObservation
    artifacts: tuple[Artifact, ...]
    classification: Classification | None
    category: TaxonomyCategory | None


@dataclass(frozen=True)
class RecoveryPlan:
    foreign_key_check: str
    foreign_key_violations: int
    integrity_check: str
    quick_check: str
    expired_outbox_leases: int
    expired_media_leases: int
    running_jobs: int
    pending_outbox: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "expired_media_leases": self.expired_media_leases,
            "expired_outbox_leases": self.expired_outbox_leases,
            "foreign_key_check": self.foreign_key_check,
            "foreign_key_violations": self.foreign_key_violations,
            "integrity_check": self.integrity_check,
            "pending_outbox": self.pending_outbox,
            "quick_check": self.quick_check,
            "running_jobs": self.running_jobs,
        }


@dataclass(frozen=True)
class SkeletonJob:
    """Public-safe Native Host job state backed only by SQLite."""

    job_id: str
    state: str
    disposition: DuplicateDisposition
    run_kind: str = "unknown"
    scope_id: str | None = None
    failure_code: ErrorCode | None = None
    fallback_eligible: bool = False


@dataclass(frozen=True)
class CurrentPageIdentity:
    """Deterministic external Job and internal opaque SQLite identities."""

    job_id: str
    run_id: str
    checkpoint_id: str
    observation_id: str
    scan_receipt_id: str


@dataclass(frozen=True)
class CurrentPageReceipt:
    """Reproducible receipt that never emits page facts or Canonical Store paths."""

    job_id: str
    state: str
    disposition: DuplicateDisposition
    checkpoint_state: str
    transition: str
    adapter_name: str
    adapter_version: str
    content_ref_sha256: str
    relation_ref_sha256: str
    observation_ref_sha256: str
    artifact_ref_sha256: str | None

    def safe_dict(self) -> dict[str, Any]:
        completed = self.state == "succeeded"
        return {
            "adapter": {"name": self.adapter_name, "version": self.adapter_version},
            "checkpoint": {"state": self.checkpoint_state, "transition": self.transition},
            "disposition": self.disposition.value,
            "downstream": {
                "classification": "DOWNSTREAM_NOT_RUN",
                "markdown": "DOWNSTREAM_NOT_RUN",
                "media_processing": "DOWNSTREAM_NOT_RUN",
                "notion": "DOWNSTREAM_NOT_RUN",
                "renderer": "DOWNSTREAM_NOT_RUN",
            },
            "entity_counts": {
                "artifact_placeholder": int(completed),
                "checkpoint": 1,
                "content": 1,
                "observation": 1,
                "relation": 1,
                "run": 1,
            },
            "job_id": self.job_id,
            "persistence": {
                "browser_state": 0,
                "credentials": 0,
                "media_cdn_urls": 0,
                "raw_media": 0,
            },
            "provenance_refs": {
                "artifact_sha256": self.artifact_ref_sha256,
                "content_sha256": self.content_ref_sha256,
                "observation_sha256": self.observation_ref_sha256,
                "relation_sha256": self.relation_ref_sha256,
            },
            "receipt_type": "canonical_current_page",
            "schema_version": "1.0",
            "state": self.state,
        }


@dataclass(frozen=True)
class MediaLeaseRecord:
    """Internal lease state; the private relative path is excluded from receipts."""

    lease_id: str
    run_id: str
    content_key: str
    purpose: str
    content_hash: str
    mime: str
    size_bytes: int
    duration_seconds: float | None
    created_at: str
    expires_at: str
    status: str
    local_relative_path: str = field(repr=False)
    cleanup_error_code: str | None = None

    def safe_dict(self) -> dict[str, Any]:
        return {
            "cleanup_error_code": self.cleanup_error_code,
            "content_hash": self.content_hash,
            "duration_seconds": self.duration_seconds,
            "expires_at": self.expires_at,
            "lease_id": self.lease_id,
            "mime": self.mime,
            "purpose": self.purpose,
            "size_bytes": self.size_bytes,
            "status": self.status,
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _future(now: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(now.removesuffix("Z") + "+00:00")
    return (parsed + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_token(value: str, *, label: str) -> str:
    if SAFE_TOKEN.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    return value


def _validate_media_timestamp(value: str, *, label: str) -> str:
    if not isinstance(value, str) or MEDIA_TIMESTAMP.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid") from None
    return value


def _validate_sha256(value: str, *, label: str) -> str:
    if SHA256.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    return value


def _validate_lifecycle_target(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value or "\n" in value:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    return value


def _uuid(value: str, *, label: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid") from None
    if str(parsed) != value.lower():
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is not canonical")
    return parsed


def current_page_identity_from_job(job_id: str) -> CurrentPageIdentity:
    parsed = _uuid(job_id, label="job_id")
    suffix = parsed.hex
    return CurrentPageIdentity(
        job_id=str(parsed),
        run_id=f"run_capture_{suffix}",
        checkpoint_id=f"checkpoint_capture_{suffix}",
        observation_id=f"obs_capture_{suffix}",
        scan_receipt_id=f"receipt_capture_{suffix}",
    )


def current_page_identity_from_request(request_id: str) -> CurrentPageIdentity:
    parsed = _uuid(request_id, label="request_id")
    job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-native-request:{parsed}"))
    return current_page_identity_from_job(job_id)


def _payload(model: Any) -> tuple[str, str]:
    value = model.model_dump(mode="json", by_alias=True)
    rendered = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return rendered, hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class CanonicalStore:
    """Single-device Store whose database always lives below RuntimePaths."""

    def __init__(self, paths: RuntimePaths, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms < 1 or busy_timeout_ms > 60_000:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "SQLite busy timeout is invalid")
        self.paths = paths
        self.busy_timeout_ms = busy_timeout_ms
        self._lock_path = paths.canonical_directory / "store.lock"

    @contextmanager
    def _file_lock(self, *, exclusive: bool) -> Iterator[None]:
        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _configure(self, connection: sqlite3.Connection, *, writable: bool) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")
        if writable:
            journal_mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]).lower()
            if journal_mode != "wal":
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "SQLite WAL mode is unavailable")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA wal_autocheckpoint = 1000")
        foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        if foreign_keys != 1:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "SQLite foreign-key enforcement is unavailable")

    def _open(self, *, writable: bool = True) -> sqlite3.Connection:
        if not self.paths.database.exists() and not writable:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Canonical Store is not initialized")
        try:
            if writable:
                connection = sqlite3.connect(
                    self.paths.database,
                    timeout=self.busy_timeout_ms / 1000,
                    isolation_level=None,
                    check_same_thread=False,
                )
            else:
                uri = f"file:{quote(str(self.paths.database))}?mode=ro"
                connection = sqlite3.connect(
                    uri,
                    uri=True,
                    timeout=self.busy_timeout_ms / 1000,
                    isolation_level=None,
                    check_same_thread=False,
                )
            self._configure(connection, writable=writable)
            return connection
        except X2NRuntimeError:
            raise
        except sqlite3.Error as error:
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Canonical Store could not be opened") from error

    def _secure_sqlite_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.paths.database) + suffix)
            if path.exists():
                try:
                    self.paths.ensure_private_file(path)
                except FileNotFoundError:
                    # SQLite may delete a transient WAL/SHM sidecar after the
                    # existence check while another connection is closing.
                    # The canonical database must never receive this waiver.
                    if suffix in {"-wal", "-shm"} and not path.exists():
                        continue
                    raise
        if self._lock_path.exists():
            self.paths.ensure_private_file(self._lock_path)

    @contextmanager
    def _transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=True)
            try:
                connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
                yield connection
                connection.commit()
            except X2NRuntimeError:
                connection.rollback()
                raise
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Canonical write violated a Store invariant"
                ) from error
            except sqlite3.Error as error:
                connection.rollback()
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Canonical transaction failed atomically") from error
            except BaseException:
                # Abrupt in-process interruption mirrors SQLite's process-exit
                # rollback and keeps kill-point tests honest.
                connection.rollback()
                raise
            finally:
                connection.close()
                self._secure_sqlite_files()

    def initialize(self) -> dict[str, Any]:
        self.paths.initialize_layout()
        existed = self.paths.database.exists()
        if existed and self.paths.database.is_symlink():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Canonical Store cannot be a symbolic link")
        try:
            with self._file_lock(exclusive=True):
                connection = self._open(writable=True)
                try:
                    version = migrate_forward(connection, LATEST_SCHEMA_VERSION, applied_at=_now())
                    checks = self._integrity(connection)
                    if checks != HEALTHY_CHECKS:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical Store integrity check failed")
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    connection.close()
                self._secure_sqlite_files()
            if self.counts().get("content", 0) == 0:
                self.paths.mark_store_initialized()
            return {
                "content_count": self.counts().get("content", 0),
                "foreign_key_check": checks["foreign_key_check"],
                "foreign_key_violations": checks["foreign_key_violations"],
                "foreign_keys": True,
                "integrity_check": "ok",
                "journal_mode": "wal",
                "quick_check": checks["quick_check"],
                "schema_version": version,
            }
        except Exception:
            if not existed:
                for suffix in ("", "-wal", "-shm"):
                    candidate = Path(str(self.paths.database) + suffix)
                    if candidate.exists():
                        candidate.unlink()
            raise

    @staticmethod
    def _integrity(connection: sqlite3.Connection) -> dict[str, str | int]:
        quick_rows = [str(row[0]) for row in connection.execute("PRAGMA quick_check").fetchall()]
        integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
        foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        return {
            "foreign_key_check": "ok" if foreign_key_violations == 0 else "failed",
            "foreign_key_violations": foreign_key_violations,
            "integrity_check": "ok" if integrity_rows == ["ok"] else "failed",
            "quick_check": "ok" if quick_rows == ["ok"] else "failed",
        }

    def health(self) -> dict[str, Any]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                checks = self._integrity(connection)
                version = current_version(connection)
                foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
            finally:
                connection.close()
        status = "healthy" if checks == HEALTHY_CHECKS and foreign_keys else "failed"
        return {**checks, "foreign_keys": foreign_keys, "schema_version": version, "status": status}

    def snapshot_schema(self) -> dict[str, Any]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                return schema_snapshot(connection)
            finally:
                connection.close()

    @staticmethod
    def _ensure_run(connection: sqlite3.Connection, run_id: str, observed_at: str) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO run_record(
                run_id, run_kind, state, input_manifest_hash, started_at, finished_at, created_at
            ) VALUES (?, 'canonical_ingest', 'running', NULL, ?, NULL, ?)
            """,
            (run_id, observed_at, observed_at),
        )

    @staticmethod
    def _upsert_content(connection: sqlite3.Connection, content: CanonicalContent, now: str) -> WriteDisposition:
        payload_json, payload_sha = _payload(content)
        existing = connection.execute(
            "SELECT payload_sha256, record_version FROM content WHERE content_key = ?",
            (content.content_key,),
        ).fetchone()
        tombstone = connection.execute(
            "SELECT 1 FROM lifecycle_tombstone WHERE target_kind = 'content' AND target_key_private = ?",
            (content.content_key,),
        ).fetchone()
        if tombstone is not None and content.status.value != "deleted_by_user":
            # Only an explicit future Owner lifecycle workflow may undo a logical
            # deletion. Ordinary Adapter observations must not resurrect content.
            return WriteDisposition.UNCHANGED
        if existing is not None and str(existing["payload_sha256"]) == payload_sha:
            return WriteDisposition.UNCHANGED
        if existing is not None and content.record_version <= int(existing["record_version"]):
            raise X2NRuntimeError(
                ErrorCode.DATA_INTEGRITY_FAILED, "Canonical content version conflicts with stored truth"
            )
        values = (
            content.content_key,
            content.platform.value,
            content.platform_content_id,
            content.canonical_source_url,
            content.content_type.value,
            content.title,
            content.description,
            content.author_name,
            content.author_platform_id,
            content.published_at.isoformat().replace("+00:00", "Z") if content.published_at else None,
            content.content_hash,
            content.first_observed_at.isoformat().replace("+00:00", "Z"),
            content.last_observed_at.isoformat().replace("+00:00", "Z"),
            content.record_version,
            content.status.value,
            payload_json,
            payload_sha,
        )
        if existing is None:
            connection.execute(
                """
                INSERT INTO content(
                    content_key, platform, platform_content_id, canonical_source_url, content_type,
                    title, description, author_name, author_platform_id, published_at, content_hash,
                    first_observed_at, last_observed_at, record_version, status, payload_json,
                    payload_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values, now, now),
            )
            return WriteDisposition.INSERTED
        connection.execute(
            """
            UPDATE content SET
                canonical_source_url = ?, content_type = ?, title = ?, description = ?,
                author_name = ?, author_platform_id = ?, published_at = ?, content_hash = ?,
                first_observed_at = ?, last_observed_at = ?, record_version = ?, status = ?,
                payload_json = ?, payload_sha256 = ?, updated_at = ?
            WHERE content_key = ?
            """,
            (
                content.canonical_source_url,
                content.content_type.value,
                content.title,
                content.description,
                content.author_name,
                content.author_platform_id,
                content.published_at.isoformat().replace("+00:00", "Z") if content.published_at else None,
                content.content_hash,
                content.first_observed_at.isoformat().replace("+00:00", "Z"),
                content.last_observed_at.isoformat().replace("+00:00", "Z"),
                content.record_version,
                content.status.value,
                payload_json,
                payload_sha,
                now,
                content.content_key,
            ),
        )
        return WriteDisposition.UPDATED

    @staticmethod
    def _upsert_relation(
        connection: sqlite3.Connection,
        relation: UserRelation,
        platform: str,
        now: str,
    ) -> WriteDisposition:
        payload_json, payload_sha = _payload(relation)
        connection.execute(
            "INSERT OR IGNORE INTO account_ref(account_ref_hash, platform, created_at) VALUES (?, ?, ?)",
            (relation.account_ref_hash, platform, now),
        )
        if relation.status.value == "removed" and relation.confirmed_by.value != "owner":
            raise X2NRuntimeError(
                ErrorCode.DATA_INTEGRITY_FAILED,
                "Removed relation requires Owner confirmation",
            )
        existing = connection.execute(
            "SELECT payload_sha256, last_seen_at, status, confirmed_by FROM user_relation WHERE relation_key = ?",
            (relation.relation_key,),
        ).fetchone()
        last_seen = relation.last_seen_at.isoformat().replace("+00:00", "Z")
        if existing is not None and last_seen < str(existing["last_seen_at"]):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Relation observation would move backward")
        if existing is not None and str(existing["status"]) == "removed":
            if str(existing["confirmed_by"]) != "owner":
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED,
                    "Stored removed relation lacks Owner confirmation",
                )
            if relation.status.value != "removed":
                # Generic adapters and reconciliation are not an Owner reactivation
                # workflow.  A later observation may update Content and evidence, but
                # it must not silently reverse an explicit Owner removal.
                return WriteDisposition.UNCHANGED
        if existing is not None and str(existing["payload_sha256"]) == payload_sha:
            return WriteDisposition.UNCHANGED
        if existing is None:
            connection.execute(
                """
                INSERT INTO user_relation(
                    relation_key, account_ref_hash, content_key, relation_type, source_collection_id,
                    source_collection_name_private, first_seen_at, last_seen_at, status, confirmed_by,
                    scan_receipt_id, payload_json, payload_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relation.relation_key,
                    relation.account_ref_hash,
                    relation.content_key,
                    relation.relation_type.value,
                    relation.source_collection_id,
                    relation.source_collection_name_private,
                    relation.first_seen_at.isoformat().replace("+00:00", "Z"),
                    last_seen,
                    relation.status.value,
                    relation.confirmed_by.value,
                    relation.scan_receipt_id,
                    payload_json,
                    payload_sha,
                    now,
                    now,
                ),
            )
            return WriteDisposition.INSERTED
        connection.execute(
            """
            UPDATE user_relation SET
                source_collection_name_private = ?, last_seen_at = ?, status = ?, confirmed_by = ?,
                scan_receipt_id = ?, payload_json = ?, payload_sha256 = ?, updated_at = ?
            WHERE relation_key = ?
            """,
            (
                relation.source_collection_name_private,
                last_seen,
                relation.status.value,
                relation.confirmed_by.value,
                relation.scan_receipt_id,
                payload_json,
                payload_sha,
                now,
                relation.relation_key,
            ),
        )
        return WriteDisposition.UPDATED

    @staticmethod
    def _append_observation(
        connection: sqlite3.Connection,
        observation: SourceObservation,
        now: str,
    ) -> WriteDisposition:
        payload_json, payload_sha = _payload(observation)
        existing = connection.execute(
            "SELECT payload_sha256 FROM source_observation WHERE observation_id = ?",
            (observation.observation_id,),
        ).fetchone()
        if existing is not None:
            if str(existing["payload_sha256"]) == payload_sha:
                return WriteDisposition.UNCHANGED
            raise X2NRuntimeError(
                ErrorCode.DATA_INTEGRITY_FAILED, "Observation identity conflicts with append-only history"
            )
        observed_at = observation.observed_at.isoformat().replace("+00:00", "Z")
        CanonicalStore._ensure_run(connection, observation.run_id, observed_at)
        connection.execute(
            """
            INSERT INTO source_observation(
                observation_id, content_key, adapter_name, adapter_version, source_method,
                observed_at, raw_text_hash, completeness, run_id, payload_json, payload_sha256,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.observation_id,
                observation.content_key,
                observation.adapter_name,
                observation.adapter_version,
                observation.source_method.value,
                observed_at,
                observation.raw_text_hash,
                observation.completeness,
                observation.run_id,
                payload_json,
                payload_sha,
                now,
            ),
        )
        return WriteDisposition.INSERTED

    @staticmethod
    def _append_artifact(connection: sqlite3.Connection, artifact: Artifact) -> WriteDisposition:
        payload_json, payload_sha = _payload(artifact)
        existing = connection.execute(
            "SELECT payload_sha256 FROM artifact WHERE artifact_id = ? OR artifact_key = ?",
            (artifact.artifact_id, artifact.artifact_key),
        ).fetchone()
        if existing is not None:
            if str(existing["payload_sha256"]) == payload_sha:
                return WriteDisposition.UNCHANGED
            raise X2NRuntimeError(
                ErrorCode.ARTIFACT_VERSION_CONFLICT, "Artifact identity conflicts with append-only history"
            )
        connection.execute(
            """
            INSERT INTO artifact(
                artifact_id, artifact_key, content_key, artifact_type, input_hash, processor,
                processor_version, model_provider, model_name, model_snapshot, prompt_version,
                language, private_payload_present, private_payload_ref, private_payload_hash,
                artifact_sequence, created_at, supersedes_artifact_id, payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.artifact_key,
                artifact.content_key,
                artifact.artifact_type.value,
                artifact.input_hash,
                artifact.processor,
                artifact.processor_version,
                artifact.model_provider,
                artifact.model_name,
                artifact.model_snapshot,
                artifact.prompt_version,
                artifact.language,
                int(artifact.private_payload_present),
                artifact.private_payload_ref,
                artifact.private_payload_hash,
                artifact.artifact_sequence,
                artifact.created_at.isoformat().replace("+00:00", "Z"),
                artifact.supersedes_artifact_id,
                payload_json,
                payload_sha,
            ),
        )
        return WriteDisposition.INSERTED

    def ingest_bundle(
        self,
        content: CanonicalContent,
        *,
        relation: UserRelation | None = None,
        observations: Sequence[SourceObservation] = (),
        artifacts: Sequence[Artifact] = (),
    ) -> dict[str, Any]:
        if relation is not None and relation.content_key != content.content_key:
            raise X2NRuntimeError(ErrorCode.RELATION_KEY_INVALID, "Relation does not belong to canonical content")
        if any(item.content_key != content.content_key for item in observations):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Observation does not belong to canonical content")
        if any(item.content_key != content.content_key for item in artifacts):
            raise X2NRuntimeError(ErrorCode.ARTIFACT_VERSION_CONFLICT, "Artifact does not belong to canonical content")
        now = _now()
        with self._transaction() as connection:
            content_result = self._upsert_content(connection, content, now)
            relation_result = (
                self._upsert_relation(connection, relation, content.platform.value, now)
                if relation is not None
                else None
            )
            observation_results = [self._append_observation(connection, item, now) for item in observations]
            artifact_results = [self._append_artifact(connection, item) for item in artifacts]
        return {
            "artifacts": [item.value for item in artifact_results],
            "content": content_result.value,
            "observations": [item.value for item in observation_results],
            "relation": relation_result.value if relation_result else None,
        }

    def ingest_contents(self, contents: Iterable[CanonicalContent]) -> dict[str, int]:
        totals = {item.value: 0 for item in WriteDisposition}
        now = _now()
        with self._transaction() as connection:
            for content in contents:
                totals[self._upsert_content(connection, content, now).value] += 1
        return totals

    @staticmethod
    def _append_taxonomy_revision(
        connection: sqlite3.Connection,
        *,
        category: TaxonomyCategory,
        operation: str,
        previous_version: int | None,
        merge_target_category_id: UUID | None,
        payload_json: str,
        payload_sha: str,
        created_at: str,
    ) -> None:
        seed = "|".join(
            (
                str(category.category_id),
                operation,
                str(category.version),
                "" if merge_target_category_id is None else str(merge_target_category_id),
                payload_sha,
            )
        )
        revision = TaxonomyRevision(
            revision_id=f"taxonomy_rev_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:32]}",
            category_id=category.category_id,
            operation=operation,  # type: ignore[arg-type]
            actor="owner",
            category_version=category.version,
            previous_version=previous_version,
            merge_target_category_id=merge_target_category_id,
            payload_sha256=payload_sha,
            created_at=created_at,
        )
        connection.execute(
            """
            INSERT INTO taxonomy_revision(
                revision_id, category_id, operation, actor, category_version, previous_version,
                merge_target_category_id, payload_json, payload_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision.revision_id,
                str(revision.category_id),
                revision.operation,
                revision.actor,
                revision.category_version,
                revision.previous_version,
                None if revision.merge_target_category_id is None else str(revision.merge_target_category_id),
                payload_json,
                revision.payload_sha256,
                revision.created_at,
            ),
        )

    def _put_taxonomy_category(
        self,
        connection: sqlite3.Connection,
        category: TaxonomyCategory,
        *,
        now: str,
        forced_operation: str | None = None,
        merge_target_category_id: UUID | None = None,
    ) -> WriteDisposition:
        payload_json, payload_sha = _payload(category)
        existing = connection.execute(
            "SELECT payload_sha256, version, enabled FROM taxonomy_category WHERE category_id = ?",
            (str(category.category_id),),
        ).fetchone()
        if existing is not None and str(existing["payload_sha256"]) == payload_sha:
            if forced_operation is not None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy merge has no source revision")
            return WriteDisposition.UNCHANGED
        if existing is not None and category.version <= int(existing["version"]):
            raise X2NRuntimeError(
                ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy category version conflicts with Owner truth"
            )
        if existing is None:
            if category.version != 1 or forced_operation not in {None, "create"}:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "New taxonomy category revision is invalid")
            connection.execute(
                """
                INSERT INTO taxonomy_category(
                    category_id, name, slug, priority, enabled, version, level, created_by,
                    payload_json, payload_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(category.category_id),
                    category.name,
                    category.slug,
                    category.priority,
                    int(category.enabled),
                    category.version,
                    category.level,
                    category.created_by,
                    payload_json,
                    payload_sha,
                    now,
                    now,
                ),
            )
            self._append_taxonomy_revision(
                connection,
                category=category,
                operation="create",
                previous_version=None,
                merge_target_category_id=None,
                payload_json=payload_json,
                payload_sha=payload_sha,
                created_at=now,
            )
            return WriteDisposition.INSERTED
        prior_version = int(existing["version"])
        operation = forced_operation or ("disable" if bool(existing["enabled"]) and not category.enabled else "update")
        if operation not in {"update", "disable", "merge"}:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy revision operation is invalid")
        if operation == "merge" and (category.enabled or merge_target_category_id is None):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy merge source is invalid")
        connection.execute(
            """
            UPDATE taxonomy_category SET
                name = ?, slug = ?, priority = ?, enabled = ?, version = ?, payload_json = ?,
                payload_sha256 = ?, updated_at = ?
            WHERE category_id = ?
            """,
            (
                category.name,
                category.slug,
                category.priority,
                int(category.enabled),
                category.version,
                payload_json,
                payload_sha,
                now,
                str(category.category_id),
            ),
        )
        self._append_taxonomy_revision(
            connection,
            category=category,
            operation=operation,
            previous_version=prior_version,
            merge_target_category_id=merge_target_category_id,
            payload_json=payload_json,
            payload_sha=payload_sha,
            created_at=now,
        )
        return WriteDisposition.UPDATED

    def put_taxonomy_category(self, category: TaxonomyCategory) -> WriteDisposition:
        if category.created_by != "owner" or category.level != 1:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Only Owner top-level taxonomy categories are permitted")
        with self._transaction() as connection:
            return self._put_taxonomy_category(connection, category, now=_now())

    def merge_taxonomy_category(
        self,
        source: TaxonomyCategory,
        target_category_id: UUID,
    ) -> WriteDisposition:
        if source.created_by != "owner" or source.level != 1 or source.enabled:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taxonomy merge requires a disabled Owner source")
        if source.category_id == target_category_id:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy merge cannot target itself")
        with self._transaction() as connection:
            target = connection.execute(
                "SELECT enabled FROM taxonomy_category WHERE category_id = ?", (str(target_category_id),)
            ).fetchone()
            if target is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy merge target is unknown")
            if not bool(target["enabled"]):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Taxonomy merge target is disabled")
            return self._put_taxonomy_category(
                connection,
                source,
                now=_now(),
                forced_operation="merge",
                merge_target_category_id=target_category_id,
            )

    def list_taxonomy_categories(self, *, include_disabled: bool = True) -> tuple[TaxonomyCategory, ...]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute(
                    "SELECT payload_json FROM taxonomy_category "
                    + ("" if include_disabled else "WHERE enabled = 1 ")
                    + "ORDER BY category_id"
                ).fetchall()
            finally:
                connection.close()
        try:
            return tuple(TaxonomyCategory.model_validate_json(str(row["payload_json"])) for row in rows)
        except Exception as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy category payload is invalid") from error

    def taxonomy_revisions(self, category_id: UUID | None = None) -> tuple[TaxonomyRevision, ...]:
        if category_id is not None and not isinstance(category_id, UUID):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Taxonomy revision category id is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute(
                    "SELECT revision_id, category_id, operation, actor, category_version, previous_version, "
                    "merge_target_category_id, payload_sha256, created_at FROM taxonomy_revision "
                    + ("WHERE category_id = ? " if category_id is not None else "")
                    + "ORDER BY category_id, category_version",
                    () if category_id is None else (str(category_id),),
                ).fetchall()
            finally:
                connection.close()
        try:
            return tuple(
                TaxonomyRevision(
                    revision_id=str(row["revision_id"]),
                    category_id=UUID(str(row["category_id"])),
                    operation=str(row["operation"]),  # type: ignore[arg-type]
                    actor=str(row["actor"]),  # type: ignore[arg-type]
                    category_version=int(row["category_version"]),
                    previous_version=None if row["previous_version"] is None else int(row["previous_version"]),
                    merge_target_category_id=(
                        None if row["merge_target_category_id"] is None else UUID(str(row["merge_target_category_id"]))
                    ),
                    payload_sha256=str(row["payload_sha256"]),
                    created_at=str(row["created_at"]),
                )
                for row in rows
            )
        except (TypeError, ValueError, X2NRuntimeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy revision payload is invalid") from error

    def append_classification(self, classification: Classification) -> WriteDisposition:
        payload_json, payload_sha = _payload(classification)
        with self._transaction() as connection:
            category = connection.execute(
                "SELECT enabled, version FROM taxonomy_category WHERE category_id = ?",
                (str(classification.primary_category_id),),
            ).fetchone()
            if category is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Classification category is unknown")
            if not bool(category["enabled"]):
                raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Classification category is disabled")
            if classification.taxonomy_version < int(category["version"]):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Classification taxonomy version is stale")
            if classification.supersedes_classification_id is not None:
                superseded = connection.execute(
                    "SELECT content_key FROM classification WHERE classification_id = ?",
                    (classification.supersedes_classification_id,),
                ).fetchone()
                if superseded is None:
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED,
                        "Classification review revision must supersede an existing classification",
                    )
                if str(superseded["content_key"]) != classification.content_key:
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED,
                        "Classification review revision cannot supersede another content item",
                    )
            existing = connection.execute(
                "SELECT payload_sha256 FROM classification WHERE classification_id = ?",
                (classification.classification_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_sha256"]) == payload_sha:
                    return WriteDisposition.UNCHANGED
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Classification identity conflicts with append-only history"
                )
            connection.execute(
                """
                INSERT INTO classification(
                    classification_id, content_key, taxonomy_version, primary_category_id,
                    decision_mode, confidence_raw, calibration_bucket, review_status, created_at,
                    supersedes_classification_id, payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    classification.classification_id,
                    classification.content_key,
                    classification.taxonomy_version,
                    str(classification.primary_category_id),
                    classification.decision_mode.value,
                    classification.confidence_raw,
                    classification.calibration_bucket,
                    classification.review_status.value,
                    classification.created_at.isoformat().replace("+00:00", "Z"),
                    classification.supersedes_classification_id,
                    payload_json,
                    payload_sha,
                ),
            )
            for artifact_id in classification.evidence_artifact_ids:
                connection.execute(
                    "INSERT INTO classification_artifact(classification_id, artifact_id) VALUES (?, ?)",
                    (classification.classification_id, artifact_id),
                )
            return WriteDisposition.INSERTED

    @staticmethod
    def _current_page_receipt(
        connection: sqlite3.Connection,
        identity: CurrentPageIdentity,
        disposition: DuplicateDisposition,
    ) -> CurrentPageReceipt:
        ledger = connection.execute(
            "SELECT payload_hash FROM request_ledger WHERE job_id = ?",
            (identity.job_id,),
        ).fetchone()
        run = connection.execute(
            "SELECT state, input_manifest_hash FROM run_record WHERE run_id = ? AND run_kind = ?",
            (identity.run_id, CURRENT_PAGE_RUN_KIND),
        ).fetchone()
        checkpoint = connection.execute(
            """
            SELECT adapter_name, adapter_version, account_ref_hash, cursor_kind, state, full_scan_id
            FROM checkpoint WHERE checkpoint_id = ?
            """,
            (identity.checkpoint_id,),
        ).fetchone()
        observation_rows = connection.execute(
            """
            SELECT observation_id, content_key, adapter_name, adapter_version, raw_text_hash
            FROM source_observation WHERE run_id = ?
            """,
            (identity.run_id,),
        ).fetchall()
        if ledger is None or run is None or checkpoint is None or len(observation_rows) != 1:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page orchestration graph is incomplete")
        observation = observation_rows[0]
        if (
            str(run["input_manifest_hash"]) != str(ledger["payload_hash"])
            or str(observation["raw_text_hash"]) != str(ledger["payload_hash"])
            or str(observation["observation_id"]) != identity.observation_id
            or str(checkpoint["full_scan_id"]) != identity.run_id
            or str(checkpoint["adapter_name"]) != str(observation["adapter_name"])
            or str(checkpoint["adapter_version"]) != str(observation["adapter_version"])
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page orchestration identity diverged")

        content_key = str(observation["content_key"])
        content = connection.execute(
            "SELECT platform, content_hash FROM content WHERE content_key = ?",
            (content_key,),
        ).fetchone()
        relations = connection.execute(
            """
            SELECT relation_key FROM user_relation
            WHERE account_ref_hash = ? AND content_key = ? AND relation_type = 'saved_current'
            """,
            (str(checkpoint["account_ref_hash"]), content_key),
        ).fetchall()
        account = connection.execute(
            "SELECT platform FROM account_ref WHERE account_ref_hash = ?",
            (str(checkpoint["account_ref_hash"]),),
        ).fetchone()
        if (
            content is None
            or account is None
            or len(relations) != 1
            or str(content["platform"]) != str(account["platform"])
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page canonical graph is incomplete")

        run_state = str(run["state"])
        checkpoint_state = str(checkpoint["state"])
        transition = str(checkpoint["cursor_kind"])
        if (run_state, checkpoint_state, transition) not in {
            ("running", "active", CURRENT_PAGE_CURSOR_CANONICAL),
            ("succeeded", "complete", CURRENT_PAGE_CURSOR_COMPLETE),
        }:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page orchestration state is invalid")

        artifact_id: str | None = None
        if run_state == "succeeded":
            artifacts = connection.execute(
                """
                SELECT artifact_id FROM artifact
                WHERE content_key = ? AND artifact_type = 'search_text' AND input_hash = ?
                  AND processor = ? AND processor_version = ?
                """,
                (
                    content_key,
                    str(content["content_hash"]),
                    CURRENT_PAGE_PLACEHOLDER_PROCESSOR,
                    CURRENT_PAGE_PLACEHOLDER_VERSION,
                ),
            ).fetchall()
            if len(artifacts) != 1:
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED,
                    "Completed current-page Run lacks one placeholder Artifact",
                )
            artifact_id = str(artifacts[0]["artifact_id"])

        relation_key = str(relations[0]["relation_key"])
        return CurrentPageReceipt(
            job_id=identity.job_id,
            state=run_state,
            disposition=disposition,
            checkpoint_state=checkpoint_state,
            transition=transition,
            adapter_name=str(observation["adapter_name"]),
            adapter_version=str(observation["adapter_version"]),
            content_ref_sha256=hashlib.sha256(content_key.encode("utf-8")).hexdigest(),
            relation_ref_sha256=hashlib.sha256(relation_key.encode("utf-8")).hexdigest(),
            observation_ref_sha256=hashlib.sha256(identity.observation_id.encode("utf-8")).hexdigest(),
            artifact_ref_sha256=(
                hashlib.sha256(artifact_id.encode("utf-8")).hexdigest() if artifact_id is not None else None
            ),
        )

    def begin_current_page_capture(
        self,
        *,
        request_id: str,
        payload_hash: str,
        content: CanonicalContent,
        relation: UserRelation,
        observation: SourceObservation,
        adapter_name: str,
        adapter_version: str,
        fallback_from_job_id: str | None = None,
    ) -> CurrentPageReceipt:
        """Commit the replayable canonical phase in one SQLite transaction."""

        identity = current_page_identity_from_request(request_id)
        _validate_sha256(payload_hash, label="payload_hash")
        _validate_token(adapter_name, label="adapter_name")
        _validate_token(adapter_version, label="adapter_version")
        fallback_job_id = (
            str(_uuid(fallback_from_job_id, label="fallback_from_job_id")) if fallback_from_job_id is not None else None
        )
        if (
            relation.content_key != content.content_key
            or observation.content_key != content.content_key
            or observation.run_id != identity.run_id
            or observation.observation_id != identity.observation_id
            or observation.raw_text_hash != payload_hash
            or relation.scan_receipt_id != identity.scan_receipt_id
            or observation.adapter_name != adapter_name
            or observation.adapter_version != adapter_version
            or relation.relation_type.value != "saved_current"
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page canonical plan is inconsistent")

        observed_at = observation.observed_at.isoformat().replace("+00:00", "Z")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash, job_id FROM request_ledger WHERE request_id = ?",
                (str(_uuid(request_id, label="request_id")),),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_hash"]) != payload_hash:
                    raise X2NRuntimeError(
                        ErrorCode.NATIVE_DUPLICATE_REQUEST,
                        "Request identity conflicts with the existing payload",
                    )
                if str(existing["job_id"]) != identity.job_id:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page Job identity diverged")
                return self._current_page_receipt(
                    connection,
                    identity,
                    DuplicateDisposition.RETURN_EXISTING_JOB,
                )

            if (
                connection.execute("SELECT 1 FROM run_record WHERE run_id = ?", (identity.run_id,)).fetchone()
                is not None
            ):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page Run exists without its request")
            connection.execute(
                """
                INSERT INTO run_record(
                    run_id, run_kind, state, input_manifest_hash, started_at, finished_at, created_at
                ) VALUES (?, ?, 'running', ?, ?, NULL, ?)
                """,
                (identity.run_id, CURRENT_PAGE_RUN_KIND, payload_hash, observed_at, observed_at),
            )
            connection.execute(
                "INSERT INTO request_ledger(request_id, payload_hash, job_id, created_at) VALUES (?, ?, ?, ?)",
                (str(_uuid(request_id, label="request_id")), payload_hash, identity.job_id, observed_at),
            )
            if fallback_job_id is not None:
                connection.execute(
                    """
                    INSERT INTO current_page_fallback(current_run_id, fallback_from_job_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (identity.run_id, fallback_job_id, observed_at),
                )

            existing_content = connection.execute(
                "SELECT first_observed_at, last_observed_at, record_version FROM content WHERE content_key = ?",
                (content.content_key,),
            ).fetchone()
            canonical = content
            if existing_content is not None:
                stored_last = datetime.fromisoformat(str(existing_content["last_observed_at"]).replace("Z", "+00:00"))
                if observation.observed_at < stored_last:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Content observation would move backward")
                canonical = content.model_copy(
                    update={
                        "first_observed_at": datetime.fromisoformat(
                            str(existing_content["first_observed_at"]).replace("Z", "+00:00")
                        ),
                        "record_version": int(existing_content["record_version"]) + 1,
                    }
                )
            self._upsert_content(connection, canonical, observed_at)

            existing_relation = connection.execute(
                "SELECT first_seen_at, last_seen_at FROM user_relation WHERE relation_key = ?",
                (relation.relation_key,),
            ).fetchone()
            canonical_relation = relation
            if existing_relation is not None:
                stored_last = datetime.fromisoformat(str(existing_relation["last_seen_at"]).replace("Z", "+00:00"))
                if relation.last_seen_at < stored_last:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Relation observation would move backward")
                canonical_relation = relation.model_copy(
                    update={
                        "first_seen_at": datetime.fromisoformat(
                            str(existing_relation["first_seen_at"]).replace("Z", "+00:00")
                        )
                    }
                )
            self._upsert_relation(connection, canonical_relation, canonical.platform.value, observed_at)
            self._append_observation(connection, observation, observed_at)
            connection.execute(
                """
                INSERT INTO checkpoint(
                    checkpoint_id, adapter_name, adapter_version, account_ref_hash, relation_type,
                    cursor_kind, cursor_value_private, last_stable_content_id, full_scan_id,
                    observed_count, completion_confidence, resume_compatibility_version, state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'saved_current', ?, NULL, ?, ?, 1, 1.0, ?, 'active', ?, ?)
                """,
                (
                    identity.checkpoint_id,
                    adapter_name,
                    adapter_version,
                    canonical_relation.account_ref_hash,
                    CURRENT_PAGE_CURSOR_CANONICAL,
                    canonical.platform_content_id,
                    identity.run_id,
                    CURRENT_PAGE_RESUME_VERSION,
                    observed_at,
                    observed_at,
                ),
            )
            return self._current_page_receipt(connection, identity, DuplicateDisposition.NEW_REQUEST)

    def finalize_current_page_capture(
        self,
        job_id: str,
        *,
        disposition: DuplicateDisposition = DuplicateDisposition.RETURN_EXISTING_JOB,
    ) -> CurrentPageReceipt:
        """Append/reuse the URL-free placeholder and atomically complete the Run."""

        identity = current_page_identity_from_job(job_id)
        with self._transaction() as connection:
            current = self._current_page_receipt(connection, identity, disposition)
            if current.state == "succeeded":
                return current
            run = connection.execute(
                "SELECT started_at FROM run_record WHERE run_id = ?",
                (identity.run_id,),
            ).fetchone()
            content = connection.execute(
                """
                SELECT c.content_key, c.content_hash
                FROM content AS c
                INNER JOIN source_observation AS o ON o.content_key = c.content_key
                WHERE o.run_id = ? AND o.observation_id = ?
                """,
                (identity.run_id, identity.observation_id),
            ).fetchone()
            if run is None or content is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page finalize input is incomplete")
            content_key = str(content["content_key"])
            input_hash = str(content["content_hash"])
            artifact_key = build_artifact_key(
                content_key,
                "search_text",
                input_hash,
                CURRENT_PAGE_PLACEHOLDER_VERSION,
            )
            artifact_id = f"art_placeholder_{hashlib.sha256(artifact_key.encode('utf-8')).hexdigest()[:32]}"
            existing_artifact = connection.execute(
                "SELECT payload_json FROM artifact WHERE artifact_key = ?",
                (artifact_key,),
            ).fetchone()
            if existing_artifact is not None:
                placeholder = Artifact.model_validate_json(str(existing_artifact["payload_json"]))
                if (
                    placeholder.artifact_id != artifact_id
                    or placeholder.processor != CURRENT_PAGE_PLACEHOLDER_PROCESSOR
                    or placeholder.private_payload_present
                    or placeholder.private_payload_ref is not None
                    or placeholder.private_payload_hash is not None
                ):
                    raise X2NRuntimeError(
                        ErrorCode.ARTIFACT_VERSION_CONFLICT,
                        "Current-page placeholder identity conflicts with append-only history",
                    )
            else:
                sequence = (
                    int(
                        connection.execute(
                            "SELECT COALESCE(MAX(artifact_sequence), 0) FROM artifact WHERE content_key = ? AND artifact_type = 'search_text'",
                            (content_key,),
                        ).fetchone()[0]
                    )
                    + 1
                )
                previous = connection.execute(
                    """
                    SELECT artifact_id FROM artifact
                    WHERE content_key = ? AND artifact_type = 'search_text' AND processor = ?
                    ORDER BY artifact_sequence DESC LIMIT 1
                    """,
                    (content_key, CURRENT_PAGE_PLACEHOLDER_PROCESSOR),
                ).fetchone()
                placeholder = Artifact.model_validate_json(
                    json.dumps(
                        {
                            "append_only": True,
                            "artifact_id": artifact_id,
                            "artifact_key": artifact_key,
                            "artifact_sequence": sequence,
                            "artifact_type": "search_text",
                            "content_key": content_key,
                            "created_at": str(run["started_at"]),
                            "input_hash": input_hash,
                            "language": None,
                            "model_name": None,
                            "model_provider": None,
                            "model_snapshot": None,
                            "private_payload_hash": None,
                            "private_payload_present": False,
                            "private_payload_ref": None,
                            "processor": CURRENT_PAGE_PLACEHOLDER_PROCESSOR,
                            "processor_version": CURRENT_PAGE_PLACEHOLDER_VERSION,
                            "prompt_version": None,
                            "quality": {"grade": "unknown", "metric_name": None, "metric_value": None},
                            "schema_version": "1.0",
                            "supersedes_artifact_id": str(previous["artifact_id"]) if previous is not None else None,
                        },
                        ensure_ascii=False,
                    )
                )
            self._append_artifact(connection, placeholder)
            checkpoint_update = connection.execute(
                """
                UPDATE checkpoint SET cursor_kind = ?, state = 'complete', updated_at = ?
                WHERE checkpoint_id = ? AND state = 'active' AND cursor_kind = ?
                """,
                (CURRENT_PAGE_CURSOR_COMPLETE, _now(), identity.checkpoint_id, CURRENT_PAGE_CURSOR_CANONICAL),
            )
            run_update = connection.execute(
                """
                UPDATE run_record SET state = 'succeeded', finished_at = ?
                WHERE run_id = ? AND state = 'running' AND run_kind = ?
                """,
                (_now(), identity.run_id, CURRENT_PAGE_RUN_KIND),
            )
            if checkpoint_update.rowcount != 1 or run_update.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page finalize transition raced")
            return self._current_page_receipt(connection, identity, disposition)

    def current_page_receipt(self, job_id: str) -> CurrentPageReceipt:
        identity = current_page_identity_from_job(job_id)
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                return self._current_page_receipt(
                    connection,
                    identity,
                    DuplicateDisposition.RETURN_EXISTING_JOB,
                )
            finally:
                connection.close()

    def resumable_current_page_jobs(self, *, limit: int = 80) -> tuple[str, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 80:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Resume batch limit is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute(
                    """
                    SELECT run_id FROM run_record
                    WHERE run_kind = ? AND state = 'running'
                    ORDER BY started_at, run_id LIMIT ?
                    """,
                    (CURRENT_PAGE_RUN_KIND, limit),
                ).fetchall()
                job_ids: list[str] = []
                for row in rows:
                    run_id = str(row["run_id"])
                    if not run_id.startswith("run_capture_"):
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Current-page Run identity is invalid")
                    job_id = str(uuid.UUID(hex=run_id.removeprefix("run_capture_")))
                    ledger = connection.execute(
                        "SELECT 1 FROM request_ledger WHERE job_id = ?",
                        (job_id,),
                    ).fetchone()
                    if ledger is None:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Resumable Run lacks its request")
                    job_ids.append(job_id)
                return tuple(job_ids)
            finally:
                connection.close()

    def record_request(self, request_id: str, payload_hash: str, job_id: str) -> tuple[DuplicateDisposition, str]:
        _validate_token(request_id, label="request_id")
        _validate_sha256(payload_hash, label="payload_hash")
        _validate_token(job_id, label="job_id")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash, job_id FROM request_ledger WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO request_ledger(request_id, payload_hash, job_id, created_at) VALUES (?, ?, ?, ?)",
                    (request_id, payload_hash, job_id, _now()),
                )
                return DuplicateDisposition.NEW_REQUEST, job_id
            if str(existing["payload_hash"]) == payload_hash:
                return DuplicateDisposition.RETURN_EXISTING_JOB, str(existing["job_id"])
            raise X2NRuntimeError(
                ErrorCode.NATIVE_DUPLICATE_REQUEST, "Request identity conflicts with the existing payload"
            )

    @staticmethod
    def _capability_manifest_from_rows(rows: Sequence[sqlite3.Row]) -> CapabilityManifest:
        if len(rows) != len(SCOPE_BINDINGS):
            raise X2NRuntimeError(
                ErrorCode.CAPABILITY_TECHNICAL_BLOCKED,
                "Capability runtime snapshot is incomplete",
            )
        by_scope = {str(row["scope_id"]): row for row in rows}
        if len(by_scope) != len(SCOPE_BINDINGS):
            raise X2NRuntimeError(
                ErrorCode.CAPABILITY_TECHNICAL_BLOCKED,
                "Capability runtime snapshot contains duplicate scopes",
            )
        outcomes: list[dict[str, Any]] = []
        try:
            for binding in SCOPE_BINDINGS:
                row = by_scope[binding.scope_id.value]
                digests = json.loads(str(row["source_registry_digests"]))
                if not isinstance(digests, dict):
                    raise ValueError("source digests must be an object")
                outcomes.append(
                    {
                        "scope_id": binding.scope_id.value,
                        "platform": binding.platform.value,
                        "relation": binding.relation.value,
                        "terminal": str(row["terminal"]),
                        "reason_code": str(row["reason_code"]),
                        "source_registry_digests": digests,
                        "feature_flag": str(row["feature_flag"]),
                        "evidence_hash": str(row["evidence_hash"]),
                        "evaluated_at": str(row["evaluated_at"]),
                    }
                )
            return CapabilityManifest.model_validate_json(
                json.dumps(
                    {"capability_contract_version": "1.0", "outcomes": outcomes},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise X2NRuntimeError(
                ErrorCode.CAPABILITY_TECHNICAL_BLOCKED,
                "Capability runtime snapshot is invalid",
            ) from error

    @staticmethod
    def _capability_rows_match_manifest(rows: Sequence[sqlite3.Row], manifest: CapabilityManifest) -> bool:
        if len(rows) != len(SCOPE_BINDINGS):
            return False
        expected = {outcome.scope_id.value: outcome.model_dump(mode="json") for outcome in manifest.outcomes}
        for row in rows:
            scope_id = str(row["scope_id"])
            outcome = expected.get(scope_id)
            if outcome is None:
                return False
            try:
                stored_digests = json.loads(str(row["source_registry_digests"]))
            except json.JSONDecodeError:
                return False
            if (
                str(row["terminal"]) != outcome["terminal"]
                or str(row["reason_code"]) != outcome["reason_code"]
                or stored_digests != outcome["source_registry_digests"]
                or str(row["feature_flag"]) != outcome["feature_flag"]
                or str(row["evidence_hash"]) != outcome["evidence_hash"]
            ):
                return False
        return True

    def persist_capability_snapshot(self, manifest: CapabilityManifest) -> CapabilityManifest:
        """Atomically persist the only runtime authority for all eight scope gates."""

        if manifest.capability_contract_version != "1.0" or len(manifest.outcomes) != len(SCOPE_BINDINGS):
            raise X2NRuntimeError(ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability manifest version is invalid")
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT scope_id, terminal, reason_code, source_registry_digests, feature_flag, evidence_hash, evaluated_at "
                "FROM capability_gate_outcome"
            ).fetchall()
            if self._capability_rows_match_manifest(rows, manifest):
                return self._capability_manifest_from_rows(rows)
            connection.execute("DELETE FROM capability_gate_outcome")
            for outcome in manifest.outcomes:
                rendered = outcome.model_dump(mode="json")
                connection.execute(
                    """
                    INSERT INTO capability_gate_outcome(
                        scope_id, terminal, reason_code, source_registry_digests, feature_flag, evidence_hash, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rendered["scope_id"],
                        rendered["terminal"],
                        rendered["reason_code"],
                        json.dumps(
                            rendered["source_registry_digests"],
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        rendered["feature_flag"],
                        rendered["evidence_hash"],
                        rendered["evaluated_at"],
                    ),
                )
            persisted = connection.execute(
                "SELECT scope_id, terminal, reason_code, source_registry_digests, feature_flag, evidence_hash, evaluated_at "
                "FROM capability_gate_outcome"
            ).fetchall()
            return self._capability_manifest_from_rows(persisted)

    def capability_snapshot(self) -> CapabilityManifest:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute(
                    "SELECT scope_id, terminal, reason_code, source_registry_digests, feature_flag, evidence_hash, evaluated_at "
                    "FROM capability_gate_outcome"
                ).fetchall()
                return self._capability_manifest_from_rows(rows)
            finally:
                connection.close()

    def invalidate_capability_scopes(self, scope_ids: Sequence[SyncScopeId]) -> int:
        """Remove stale rows for a technical veto; never serialize that veto as a terminal."""

        normalized = tuple(
            scope_id.value if isinstance(scope_id, SyncScopeId) else str(scope_id) for scope_id in scope_ids
        )
        allowed = {scope_id.value for scope_id in SyncScopeId}
        if not normalized or any(scope_id not in allowed for scope_id in normalized):
            raise X2NRuntimeError(
                ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "Capability technical invalidation is invalid"
            )
        with self._transaction() as connection:
            placeholders = ",".join("?" for _ in normalized)
            cursor = connection.execute(
                f"DELETE FROM capability_gate_outcome WHERE scope_id IN ({placeholders})",
                normalized,
            )
            return int(cursor.rowcount)

    @staticmethod
    def _binding_is_exact(binding: ScopeBinding) -> bool:
        return any(item == binding for item in SCOPE_BINDINGS)

    @staticmethod
    def _scope_job_from_row(row: sqlite3.Row, *, disposition: DuplicateDisposition) -> SkeletonJob:
        failure_code = str(row["error_code"]) if row["error_code"] is not None else None
        try:
            parsed_failure = ErrorCode(failure_code) if failure_code is not None else None
        except ValueError as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Run failure code is unknown") from error
        return SkeletonJob(
            job_id=str(row["job_id"]),
            state=str(row["state"]),
            disposition=disposition,
            run_kind=str(row["run_kind"]),
            scope_id=str(row["scope_id"]),
            failure_code=parsed_failure,
            fallback_eligible=bool(row["fallback_eligible"] or 0),
        )

    def submit_scope_dispatch_job(
        self,
        *,
        request_id: str,
        payload_hash: str,
        binding: ScopeBinding,
        dispatch_receipt_hash: str,
    ) -> SkeletonJob:
        """Create the Native job/map transaction before the synthetic adapter dispatch runs."""

        if not self._binding_is_exact(binding):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Dispatch binding is not allowlisted")
        request_id = str(_uuid(request_id, label="request_id"))
        _validate_sha256(payload_hash, label="payload_hash")
        _validate_sha256(dispatch_receipt_hash, label="dispatch_receipt_hash")
        adapter_name, adapter_version, run_kind = binding.resolve_adapter()
        job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-native-request:{request_id}"))
        observed_at = _now()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash, job_id FROM request_ledger WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_hash"]) != payload_hash:
                    raise X2NRuntimeError(
                        ErrorCode.NATIVE_DUPLICATE_REQUEST,
                        "Request identity conflicts with the existing payload",
                    )
                row = connection.execute(
                    """
                    SELECT r.run_id AS job_id, r.state, r.run_kind, d.scope_id, f.error_code, f.fallback_eligible
                    FROM run_record AS r
                    INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                    LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                    WHERE r.run_id = ?
                    """,
                    (str(existing["job_id"]),),
                ).fetchone()
                if row is None or str(row["scope_id"]) != binding.scope_id.value:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Dispatch request ledger mapping diverged")
                return self._scope_job_from_row(row, disposition=DuplicateDisposition.RETURN_EXISTING_JOB)
            connection.execute(
                """
                INSERT INTO run_record(
                    run_id, run_kind, state, input_manifest_hash, started_at, finished_at, created_at
                ) VALUES (?, ?, 'pending', ?, ?, NULL, ?)
                """,
                (job_id, SCOPE_SYNC_RUN_KIND, payload_hash, observed_at, observed_at),
            )
            connection.execute(
                """
                INSERT INTO native_dispatch_job(
                    job_id, scope_id, platform, relation, adapter_name, adapter_version, dispatch_receipt_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    binding.scope_id.value,
                    binding.platform.value,
                    binding.relation.value,
                    adapter_name,
                    adapter_version,
                    dispatch_receipt_hash,
                    observed_at,
                ),
            )
            connection.execute(
                "INSERT INTO request_ledger(request_id, payload_hash, job_id, created_at) VALUES (?, ?, ?, ?)",
                (request_id, payload_hash, job_id, observed_at),
            )
            return SkeletonJob(
                job_id=job_id,
                state="pending",
                disposition=DuplicateDisposition.NEW_REQUEST,
                run_kind=SCOPE_SYNC_RUN_KIND,
                scope_id=binding.scope_id.value,
            )

    def complete_scope_dispatch_job(self, *, job_id: str, dispatch_receipt_hash: str) -> SkeletonJob:
        _uuid(job_id, label="job_id")
        _validate_sha256(dispatch_receipt_hash, label="dispatch_receipt_hash")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT r.run_id AS job_id, r.state, r.run_kind, d.scope_id, d.dispatch_receipt_hash,
                       f.error_code, f.fallback_eligible
                FROM run_record AS r
                INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                WHERE r.run_id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None or str(row["run_kind"]) != SCOPE_SYNC_RUN_KIND:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Dispatch Job does not exist")
            if str(row["dispatch_receipt_hash"]) != dispatch_receipt_hash:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Dispatch receipt provenance diverged")
            if str(row["state"]) == "pending":
                cursor = connection.execute(
                    "UPDATE run_record SET state = 'succeeded', finished_at = ? WHERE run_id = ? AND state = 'pending'",
                    (_now(), job_id),
                )
                if cursor.rowcount != 1:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Dispatch completion transition raced")
                row = connection.execute(
                    """
                    SELECT r.run_id AS job_id, r.state, r.run_kind, d.scope_id, f.error_code, f.fallback_eligible
                    FROM run_record AS r
                    INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                    LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                    WHERE r.run_id = ?
                    """,
                    (job_id,),
                ).fetchone()
            assert row is not None
            return self._scope_job_from_row(row, disposition=DuplicateDisposition.RETURN_EXISTING_JOB)

    def fail_scope_dispatch_job(
        self,
        *,
        job_id: str,
        provenance_hash: str,
        fallback_eligible: bool,
    ) -> SkeletonJob:
        _uuid(job_id, label="job_id")
        _validate_sha256(provenance_hash, label="provenance_hash")
        if type(fallback_eligible) is not bool:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Fallback eligibility is invalid")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT r.run_id AS job_id, r.state, r.run_kind, d.scope_id, f.error_code, f.fallback_eligible
                FROM run_record AS r
                INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                WHERE r.run_id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None or str(row["run_kind"]) != SCOPE_SYNC_RUN_KIND:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Dispatch Job does not exist")
            if str(row["state"]) == "failed":
                if row["error_code"] is None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Failed dispatch lacks failure evidence")
                return self._scope_job_from_row(row, disposition=DuplicateDisposition.RETURN_EXISTING_JOB)
            if str(row["state"]) != "pending" or row["error_code"] is not None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Dispatch failure transition is invalid")
            finished_at = _now()
            cursor = connection.execute(
                "UPDATE run_record SET state = 'failed', finished_at = ? WHERE run_id = ? AND state = 'pending'",
                (finished_at, job_id),
            )
            if cursor.rowcount != 1:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Dispatch failure transition raced")
            connection.execute(
                """
                INSERT INTO run_failure(run_id, error_code, fallback_eligible, provenance_hash, created_at)
                VALUES (?, 'X2N_ADAPTER_FAILED_FALLBACK_AVAILABLE', ?, ?, ?)
                """,
                (job_id, int(fallback_eligible), provenance_hash, finished_at),
            )
            failed = connection.execute(
                """
                SELECT r.run_id AS job_id, r.state, r.run_kind, d.scope_id, f.error_code, f.fallback_eligible
                FROM run_record AS r
                INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                INNER JOIN run_failure AS f ON f.run_id = r.run_id
                WHERE r.run_id = ?
                """,
                (job_id,),
            ).fetchone()
            if failed is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Dispatch failure evidence was not persisted")
            return self._scope_job_from_row(failed, disposition=DuplicateDisposition.RETURN_EXISTING_JOB)

    def verify_current_page_fallback(self, *, fallback_from_job_id: str, current_request_id: str) -> None:
        fallback_from_job_id = str(_uuid(fallback_from_job_id, label="fallback_from_job_id"))
        current_request_id = str(_uuid(current_request_id, label="request_id"))
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    """
                    SELECT l.request_id, r.state, f.error_code, f.fallback_eligible
                    FROM request_ledger AS l
                    INNER JOIN run_record AS r ON r.run_id = l.job_id
                    INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                    INNER JOIN run_failure AS f ON f.run_id = r.run_id
                    WHERE l.job_id = ?
                    """,
                    (fallback_from_job_id,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Fallback source Job is not eligible")
        if str(row["request_id"]) == current_request_id:
            raise X2NRuntimeError(ErrorCode.NATIVE_DUPLICATE_REQUEST, "Fallback requires a new Owner request")
        if (
            str(row["state"]) != "failed"
            or str(row["error_code"]) != ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE.value
            or int(row["fallback_eligible"]) != 1
        ):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Fallback source Job is not eligible")

    def submit_skeleton_job(self, *, request_id: str, payload_hash: str, run_kind: str) -> SkeletonJob:
        """Atomically create a durable, non-executing Native request Job.

        The request ledger and run record share one transaction.  No request
        payload, page URL, account data, media reference, or credential is
        persisted by this Foundation004 skeleton.
        """

        _validate_token(request_id, label="request_id")
        _validate_sha256(payload_hash, label="payload_hash")
        if run_kind not in {"native_capture_skeleton", "native_sync_skeleton"}:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Native job kind is not enabled")
        job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-native-request:{request_id}"))
        observed_at = _now()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash, job_id FROM request_ledger WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_hash"]) != payload_hash:
                    raise X2NRuntimeError(
                        ErrorCode.NATIVE_DUPLICATE_REQUEST,
                        "Request identity conflicts with the existing payload",
                    )
                stored_job_id = str(existing["job_id"])
                job = connection.execute(
                    "SELECT state FROM run_record WHERE run_id = ?",
                    (stored_job_id,),
                ).fetchone()
                if job is None:
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED,
                        "Request ledger references a missing Job",
                    )
                return SkeletonJob(
                    job_id=stored_job_id,
                    state=str(job["state"]),
                    disposition=DuplicateDisposition.RETURN_EXISTING_JOB,
                    run_kind=run_kind,
                )
            connection.execute(
                """
                INSERT INTO run_record(
                    run_id, run_kind, state, input_manifest_hash, started_at, finished_at, created_at
                ) VALUES (?, ?, 'pending', ?, ?, NULL, ?)
                """,
                (job_id, run_kind, payload_hash, observed_at, observed_at),
            )
            connection.execute(
                "INSERT INTO request_ledger(request_id, payload_hash, job_id, created_at) VALUES (?, ?, ?, ?)",
                (request_id, payload_hash, job_id, observed_at),
            )
            return SkeletonJob(
                job_id=job_id,
                state="pending",
                disposition=DuplicateDisposition.NEW_REQUEST,
                run_kind=run_kind,
            )

    def get_skeleton_job(self, job_id: str) -> SkeletonJob:
        _validate_token(job_id, label="job_id")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                scope_row = connection.execute(
                    """
                    SELECT r.run_id AS job_id, r.state, r.run_kind, d.scope_id, f.error_code, f.fallback_eligible
                    FROM run_record AS r
                    INNER JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                    LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                    WHERE r.run_id = ? AND r.run_kind = ?
                    """,
                    (job_id, SCOPE_SYNC_RUN_KIND),
                ).fetchone()
                if scope_row is not None:
                    return self._scope_job_from_row(scope_row, disposition=DuplicateDisposition.RETURN_EXISTING_JOB)
                row = connection.execute(
                    """
                    SELECT r.state, r.run_kind
                    FROM run_record AS r
                    INNER JOIN request_ledger AS l ON l.job_id = r.run_id
                    WHERE r.run_id = ? AND r.run_kind IN ('native_capture_skeleton','native_sync_skeleton')
                    """,
                    (job_id,),
                ).fetchone()
                if row is None:
                    identity = current_page_identity_from_job(job_id)
                    row = connection.execute(
                        """
                        SELECT r.state, r.run_kind
                        FROM request_ledger AS l
                        INNER JOIN run_record AS r ON r.run_id = ?
                        WHERE l.job_id = ? AND r.run_kind = ?
                        """,
                        (identity.run_id, identity.job_id, CURRENT_PAGE_RUN_KIND),
                    ).fetchone()
            finally:
                connection.close()
        if row is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Native Job does not exist")
        return SkeletonJob(
            job_id=job_id,
            state=str(row["state"]),
            disposition=DuplicateDisposition.RETURN_EXISTING_JOB,
            run_kind=str(row["run_kind"]),
        )

    def enqueue_outbox(
        self,
        *,
        sink: str,
        content_key: str,
        desired_projection_hash: str,
        sink_schema_version: str,
        now: str | None = None,
    ) -> tuple[WriteDisposition, str]:
        if sink not in {"markdown", "notion"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Outbox sink is invalid")
        _validate_sha256(desired_projection_hash, label="desired_projection_hash")
        _validate_token(sink_schema_version, label="sink_schema_version")
        event_key = f"{sink}:{content_key}:{desired_projection_hash}:{sink_schema_version}"
        event_id = f"outbox_{hashlib.sha256(event_key.encode('utf-8')).hexdigest()[:32]}"
        observed_at = now or _now()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT event_id FROM outbox_event WHERE event_key = ?",
                (event_key,),
            ).fetchone()
            if existing is not None:
                return WriteDisposition.UNCHANGED, str(existing["event_id"])
            connection.execute(
                """
                INSERT INTO outbox_event(
                    event_id, event_key, sink, content_key, desired_projection_hash,
                    sink_schema_version, status, attempt_count, not_before, lease_id,
                    lease_owner, lease_expires_at, last_error_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (
                    event_id,
                    event_key,
                    sink,
                    content_key,
                    desired_projection_hash,
                    sink_schema_version,
                    observed_at,
                    observed_at,
                    observed_at,
                ),
            )
            return WriteDisposition.INSERTED, event_id

    def claim_outbox(
        self,
        *,
        worker_id: str,
        sink: str | None = None,
        event_id: str | None = None,
        now: str | None = None,
        lease_seconds: int = 60,
    ) -> OutboxClaim | None:
        _validate_token(worker_id, label="worker_id")
        if sink is not None and sink not in {"markdown", "notion"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Outbox sink is invalid")
        if event_id is not None:
            _validate_token(event_id, label="event_id")
        if lease_seconds < 1 or lease_seconds > 3_600:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Outbox lease duration is invalid")
        claimed_at = _validate_media_timestamp(now or _now(), label="outbox_claimed_at")
        expires_at = _future(claimed_at, lease_seconds)
        with self._transaction() as connection:
            if sink is None and event_id is None:
                row = connection.execute(
                    """
                    SELECT event_id, sink, content_key, desired_projection_hash, sink_schema_version,
                           attempt_count
                    FROM outbox_event
                    WHERE (status = 'pending' AND not_before <= ?)
                       OR (status = 'leased' AND lease_expires_at <= ?)
                    ORDER BY created_at, event_id
                    LIMIT 1
                    """,
                    (claimed_at, claimed_at),
                ).fetchone()
            elif sink is not None and event_id is None:
                row = connection.execute(
                    """
                    SELECT event_id, sink, content_key, desired_projection_hash, sink_schema_version,
                           attempt_count
                    FROM outbox_event
                    WHERE sink = ? AND (
                        (status = 'pending' AND not_before <= ?)
                        OR (status = 'leased' AND lease_expires_at <= ?)
                    )
                    ORDER BY created_at, event_id
                    LIMIT 1
                    """,
                    (sink, claimed_at, claimed_at),
                ).fetchone()
            elif sink is None:
                row = connection.execute(
                    """
                    SELECT event_id, sink, content_key, desired_projection_hash, sink_schema_version,
                           attempt_count
                    FROM outbox_event
                    WHERE event_id = ? AND (
                        (status = 'pending' AND not_before <= ?)
                        OR (status = 'leased' AND lease_expires_at <= ?)
                    )
                    """,
                    (event_id, claimed_at, claimed_at),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT event_id, sink, content_key, desired_projection_hash, sink_schema_version,
                           attempt_count
                    FROM outbox_event
                    WHERE event_id = ? AND sink = ? AND (
                        (status = 'pending' AND not_before <= ?)
                        OR (status = 'leased' AND lease_expires_at <= ?)
                    )
                    """,
                    (event_id, sink, claimed_at, claimed_at),
                ).fetchone()
            if row is None:
                return None
            lease_id = f"lease_{uuid.uuid4().hex}"
            attempt_count = int(row["attempt_count"]) + 1
            connection.execute(
                """
                UPDATE outbox_event SET
                    status = 'leased', attempt_count = ?, lease_id = ?, lease_owner = ?,
                    lease_expires_at = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (attempt_count, lease_id, worker_id, expires_at, claimed_at, row["event_id"]),
            )
            return OutboxClaim(
                event_id=str(row["event_id"]),
                lease_id=lease_id,
                sink=str(row["sink"]),
                content_key=str(row["content_key"]),
                desired_projection_hash=str(row["desired_projection_hash"]),
                sink_schema_version=str(row["sink_schema_version"]),
                attempt_count=attempt_count,
            )

    @staticmethod
    def _leased_outbox_row(connection: sqlite3.Connection, claim: OutboxClaim) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT sink, content_key, desired_projection_hash, sink_schema_version, status, lease_id
            FROM outbox_event WHERE event_id = ?
            """,
            (claim.event_id,),
        ).fetchone()
        if row is None or str(row["status"]) != "leased" or str(row["lease_id"]) != claim.lease_id:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Outbox lease is stale or unavailable")
        expected = (
            str(row["sink"]),
            str(row["content_key"]),
            str(row["desired_projection_hash"]),
            str(row["sink_schema_version"]),
        )
        actual = (claim.sink, claim.content_key, claim.desired_projection_hash, claim.sink_schema_version)
        if actual != expected:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Outbox claim identity diverged")
        return row

    def retry_outbox(
        self,
        claim: OutboxClaim,
        *,
        error_code: str,
        not_before: str,
        now: str | None = None,
    ) -> WriteDisposition:
        _validate_token(error_code, label="outbox_error_code")
        observed_at = _validate_media_timestamp(now or _now(), label="outbox_retry_at")
        scheduled_at = _validate_media_timestamp(not_before, label="outbox_not_before")
        if scheduled_at < observed_at:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Outbox retry cannot be scheduled in the past")
        with self._transaction() as connection:
            self._leased_outbox_row(connection, claim)
            connection.execute(
                """
                UPDATE outbox_event SET
                    status = 'pending', not_before = ?, lease_id = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, last_error_code = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (scheduled_at, error_code, observed_at, claim.event_id),
            )
        return WriteDisposition.UPDATED

    def dead_letter_outbox(
        self,
        claim: OutboxClaim,
        *,
        error_code: str,
        now: str | None = None,
    ) -> WriteDisposition:
        _validate_token(error_code, label="outbox_error_code")
        observed_at = _validate_media_timestamp(now or _now(), label="outbox_dead_letter_at")
        with self._transaction() as connection:
            self._leased_outbox_row(connection, claim)
            connection.execute(
                """
                UPDATE outbox_event SET
                    status = 'dead_letter', lease_id = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, last_error_code = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (error_code, observed_at, claim.event_id),
            )
        return WriteDisposition.UPDATED

    def outbox_state(self, event_id: str) -> OutboxState | None:
        _validate_token(event_id, label="event_id")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    """
                    SELECT event_id, sink, content_key, desired_projection_hash, sink_schema_version,
                           status, attempt_count, not_before, last_error_code
                    FROM outbox_event WHERE event_id = ?
                    """,
                    (event_id,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            return None
        return OutboxState(
            event_id=str(row["event_id"]),
            sink=str(row["sink"]),
            content_key=str(row["content_key"]),
            desired_projection_hash=str(row["desired_projection_hash"]),
            sink_schema_version=str(row["sink_schema_version"]),
            status=str(row["status"]),
            attempt_count=int(row["attempt_count"]),
            not_before=str(row["not_before"]),
            last_error_code=None if row["last_error_code"] is None else str(row["last_error_code"]),
        )

    def complete_outbox(self, claim: OutboxClaim, receipt: SinkReceipt) -> WriteDisposition:
        payload_json, payload_sha = _payload(receipt)
        with self._transaction() as connection:
            row = self._leased_outbox_row(connection, claim)
            expected = (
                str(row["sink"]),
                str(row["content_key"]),
                str(row["desired_projection_hash"]),
                str(row["sink_schema_version"]),
            )
            actual = (
                receipt.sink.value,
                receipt.content_key,
                receipt.desired_projection_hash,
                receipt.sink_schema_version,
            )
            if actual != expected:
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Sink receipt does not match the leased Outbox event"
                )
            delivered_at = receipt.delivered_at.isoformat().replace("+00:00", "Z")
            self._ensure_run(connection, receipt.run_id, delivered_at)
            existing = connection.execute(
                "SELECT payload_sha256 FROM sink_receipt WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            if existing is not None and str(existing["payload_sha256"]) != payload_sha:
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Sink receipt identity conflicts with append-only history"
                )
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO sink_receipt(
                        receipt_id, sink_key, sink, content_key, sink_schema_version,
                        desired_projection_hash, output_hash, sink_object_ref, external_ref_hash,
                        status, delivered_at, run_id, payload_json, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.receipt_id,
                        receipt.sink_key,
                        receipt.sink.value,
                        receipt.content_key,
                        receipt.sink_schema_version,
                        receipt.desired_projection_hash,
                        receipt.output_hash,
                        receipt.sink_object_ref,
                        receipt.external_ref_hash,
                        receipt.status.value,
                        delivered_at,
                        receipt.run_id,
                        payload_json,
                        payload_sha,
                    ),
                )
            connection.execute(
                """
                UPDATE outbox_event SET
                    status = 'delivered', lease_id = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE event_id = ?
                """,
                (delivered_at, claim.event_id),
            )
            return WriteDisposition.INSERTED if existing is None else WriteDisposition.UNCHANGED

    def notion_mapping(self, content_key: str) -> NotionMapping | None:
        if not isinstance(content_key, str) or not content_key or len(content_key) > 512:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "content_key is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    """
                    SELECT content_key, notion_page_ref_private, external_ref_hash
                    FROM notion_mapping WHERE content_key = ?
                    """,
                    (content_key,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            return None
        return NotionMapping(
            content_key=str(row["content_key"]),
            page_ref=str(row["notion_page_ref_private"]),
            external_ref_hash=str(row["external_ref_hash"]),
        )

    def record_notion_mapping(
        self,
        *,
        content_key: str,
        page_ref: str,
        now: str | None = None,
    ) -> WriteDisposition:
        page_id = str(_uuid(page_ref, label="notion_page_ref"))
        external_ref_hash = hashlib.sha256(page_id.encode("utf-8")).hexdigest()
        observed_at = _validate_media_timestamp(now or _now(), label="notion_mapping_at")
        with self._transaction() as connection:
            content = connection.execute(
                "SELECT 1 FROM content WHERE content_key = ?",
                (content_key,),
            ).fetchone()
            if content is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion mapping Content is missing")
            existing = connection.execute(
                """
                SELECT notion_page_ref_private, external_ref_hash
                FROM notion_mapping WHERE content_key = ?
                """,
                (content_key,),
            ).fetchone()
            page_owner = connection.execute(
                "SELECT content_key FROM notion_mapping WHERE notion_page_ref_private = ?",
                (page_id,),
            ).fetchone()
            if page_owner is not None and str(page_owner["content_key"]) != content_key:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion page is mapped to another Content")
            if existing is not None:
                if (
                    str(existing["notion_page_ref_private"]) != page_id
                    or str(existing["external_ref_hash"]) != external_ref_hash
                ):
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Notion mapping conflicts with stored truth")
                return WriteDisposition.UNCHANGED
            connection.execute(
                """
                INSERT INTO notion_mapping(
                    content_key, notion_page_ref_private, external_ref_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (content_key, page_id, external_ref_hash, observed_at, observed_at),
            )
        return WriteDisposition.INSERTED

    def _insert_media_lease(
        self,
        *,
        run_id: str,
        content_key: str,
        purpose: str,
        content_hash: str,
        mime: str,
        size_bytes: int,
        duration_seconds: float | None,
        ttl_seconds: int,
        now: str | None = None,
        lease_id: str | None = None,
        initial_status: str,
    ) -> str:
        _validate_token(run_id, label="run_id")
        _validate_token(purpose, label="purpose")
        _validate_sha256(content_hash, label="content_hash")
        if not mime or len(mime) > 127 or "/" not in mime:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media MIME is invalid")
        if size_bytes < 0 or duration_seconds is not None and duration_seconds < 0:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media dimensions are invalid")
        if ttl_seconds < 1 or ttl_seconds > MAX_MEDIA_LEASE_SECONDS:
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Media lease exceeds the retention policy")
        created_at = _validate_media_timestamp(now or _now(), label="media_created_at")
        lease_id_value = lease_id or f"media_{uuid.uuid4().hex}"
        if MEDIA_LEASE_ID.fullmatch(lease_id_value) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media lease identity is invalid")
        if initial_status not in {"active", "processing"}:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media lease initial status is invalid")
        relative_path = f"{run_id}/{lease_id_value}.bin"
        with self._transaction() as connection:
            self._ensure_run(connection, run_id, created_at)
            connection.execute(
                """
                INSERT INTO media_lease(
                    lease_id, run_id, content_key, purpose, content_hash, mime, size_bytes,
                    duration_seconds, created_at, expires_at, status, local_relative_path,
                    cleanup_error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    lease_id_value,
                    run_id,
                    content_key,
                    purpose,
                    content_hash,
                    mime,
                    size_bytes,
                    duration_seconds,
                    created_at,
                    _future(created_at, ttl_seconds),
                    initial_status,
                    relative_path,
                ),
            )
        return lease_id_value

    def create_media_lease(
        self,
        *,
        run_id: str,
        content_key: str,
        purpose: str,
        content_hash: str,
        mime: str,
        size_bytes: int,
        duration_seconds: float | None,
        ttl_seconds: int,
        now: str | None = None,
        lease_id: str | None = None,
    ) -> str:
        return self._insert_media_lease(
            run_id=run_id,
            content_key=content_key,
            purpose=purpose,
            content_hash=content_hash,
            mime=mime,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            ttl_seconds=ttl_seconds,
            now=now,
            lease_id=lease_id,
            initial_status="active",
        )

    def reserve_media_lease(
        self,
        *,
        run_id: str,
        content_key: str,
        purpose: str,
        ttl_seconds: int,
        now: str,
        lease_id: str,
    ) -> str:
        """Persist a URL-free cleanup identity before any media bytes are acquired."""

        return self._insert_media_lease(
            run_id=run_id,
            content_key=content_key,
            purpose=purpose,
            content_hash=PENDING_MEDIA_SHA256,
            mime=PENDING_MEDIA_MIME,
            size_bytes=0,
            duration_seconds=None,
            ttl_seconds=ttl_seconds,
            now=now,
            lease_id=lease_id,
            initial_status="processing",
        )

    def finalize_media_lease(
        self,
        lease_id: str,
        *,
        content_hash: str,
        mime: str,
        size_bytes: int,
        duration_seconds: float | None,
    ) -> WriteDisposition:
        """Replace pending metadata without ever persisting a source URL."""

        if MEDIA_LEASE_ID.fullmatch(lease_id) is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media lease identity is invalid")
        _validate_sha256(content_hash, label="content_hash")
        if not mime or len(mime) > 127 or "/" not in mime:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media MIME is invalid")
        if size_bytes < 0 or duration_seconds is not None and duration_seconds < 0:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media dimensions are invalid")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT content_hash, mime, size_bytes, duration_seconds, status
                FROM media_lease WHERE lease_id = ?
                """,
                (lease_id,),
            ).fetchone()
            if row is None or str(row["status"]) != "processing":
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Pending media lease is unavailable")
            current = (
                str(row["content_hash"]),
                str(row["mime"]),
                int(row["size_bytes"]),
                None if row["duration_seconds"] is None else float(row["duration_seconds"]),
            )
            desired = (content_hash, mime, size_bytes, duration_seconds)
            if current == desired:
                return WriteDisposition.UNCHANGED
            connection.execute(
                """
                UPDATE media_lease
                SET content_hash = ?, mime = ?, size_bytes = ?, duration_seconds = ?
                WHERE lease_id = ?
                """,
                (*desired, lease_id),
            )
        return WriteDisposition.UPDATED

    @staticmethod
    def _media_lease_record(row: sqlite3.Row) -> MediaLeaseRecord:
        return MediaLeaseRecord(
            lease_id=str(row["lease_id"]),
            run_id=str(row["run_id"]),
            content_key=str(row["content_key"]),
            purpose=str(row["purpose"]),
            content_hash=str(row["content_hash"]),
            mime=str(row["mime"]),
            size_bytes=int(row["size_bytes"]),
            duration_seconds=None if row["duration_seconds"] is None else float(row["duration_seconds"]),
            created_at=str(row["created_at"]),
            expires_at=str(row["expires_at"]),
            status=str(row["status"]),
            local_relative_path=str(row["local_relative_path"]),
            cleanup_error_code=None if row["cleanup_error_code"] is None else str(row["cleanup_error_code"]),
        )

    def get_media_lease(self, lease_id: str) -> MediaLeaseRecord | None:
        _validate_token(lease_id, label="lease_id")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    "SELECT * FROM media_lease WHERE lease_id = ?",
                    (lease_id,),
                ).fetchone()
            finally:
                connection.close()
        return None if row is None else self._media_lease_record(row)

    def list_media_leases(self) -> tuple[MediaLeaseRecord, ...]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute("SELECT * FROM media_lease ORDER BY lease_id").fetchall()
            finally:
                connection.close()
        return tuple(self._media_lease_record(row) for row in rows)

    def media_cleanup_candidates(self, *, now: str | None = None) -> tuple[MediaLeaseRecord, ...]:
        observed_at = _validate_media_timestamp(now or _now(), label="media_cleanup_at")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute(
                    """
                    SELECT * FROM media_lease
                    WHERE status IN ('cleanup_pending', 'expired')
                       OR (status IN ('active', 'processing') AND expires_at <= ?)
                    ORDER BY expires_at, lease_id
                    """,
                    (observed_at,),
                ).fetchall()
            finally:
                connection.close()
        return tuple(self._media_lease_record(row) for row in rows)

    def record_media_cleanup(
        self,
        lease_id: str,
        *,
        deleted: bool,
        error_code: str | None = None,
    ) -> WriteDisposition:
        _validate_token(lease_id, label="lease_id")
        if deleted and error_code is not None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Deleted media cannot retain a cleanup error")
        if not deleted:
            if error_code is None:
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Media cleanup failure requires a stable code")
            _validate_token(error_code, label="cleanup_error_code")
        target_status = "deleted" if deleted else "cleanup_pending"
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status, cleanup_error_code FROM media_lease WHERE lease_id = ?",
                (lease_id,),
            ).fetchone()
            if row is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Media lease is missing")
            if str(row["status"]) == "deleted" and not deleted:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Deleted media lease cannot be reopened")
            if str(row["status"]) == target_status and row["cleanup_error_code"] == error_code:
                return WriteDisposition.UNCHANGED
            connection.execute(
                "UPDATE media_lease SET status = ?, cleanup_error_code = ? WHERE lease_id = ?",
                (target_status, error_code, lease_id),
            )
        return WriteDisposition.UPDATED

    def recovery_plan(self, *, now: str | None = None) -> RecoveryPlan:
        observed_at = now or _now()
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                checks = self._integrity(connection)
                values = {
                    "expired_outbox_leases": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM outbox_event WHERE status = 'leased' AND lease_expires_at <= ?",
                            (observed_at,),
                        ).fetchone()[0]
                    ),
                    "expired_media_leases": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM media_lease WHERE status IN ('active','processing','cleanup_pending') AND expires_at <= ?",
                            (observed_at,),
                        ).fetchone()[0]
                    ),
                    "running_jobs": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM run_record WHERE state IN ('running','recovery')"
                        ).fetchone()[0]
                    ),
                    "pending_outbox": int(
                        connection.execute(
                            "SELECT COUNT(*) FROM outbox_event WHERE status IN ('pending','leased')"
                        ).fetchone()[0]
                    ),
                }
            finally:
                connection.close()
        return RecoveryPlan(**checks, **values)

    def apply_recovery(self, *, now: str | None = None) -> RecoveryPlan:
        observed_at = now or _now()
        before = self.recovery_plan(now=observed_at)
        if (
            before.integrity_check != "ok"
            or before.quick_check != "ok"
            or before.foreign_key_check != "ok"
            or before.foreign_key_violations != 0
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Recovery stopped because the Store is not healthy")
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE outbox_event SET
                    status = 'pending', lease_id = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE status = 'leased' AND lease_expires_at <= ?
                """,
                (observed_at, observed_at),
            )
            connection.execute(
                """
                UPDATE media_lease SET status = 'expired'
                WHERE status IN ('active','processing','cleanup_pending') AND expires_at <= ?
                """,
                (observed_at,),
            )
            payload = before.safe_dict()
            result_hash = hashlib.sha256(
                json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest()
            connection.execute(
                """
                INSERT INTO recovery_event(
                    event_id, created_at, quick_check, integrity_check, expired_outbox_leases,
                    expired_media_leases, running_jobs, result_hash
                ) VALUES (?, ?, 'ok', 'ok', ?, ?, ?, ?)
                """,
                (
                    f"recovery_{uuid.uuid4().hex}",
                    observed_at,
                    before.expired_outbox_leases,
                    before.expired_media_leases,
                    before.running_jobs,
                    result_hash,
                ),
            )
        return self.recovery_plan(now=observed_at)

    @staticmethod
    def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        return {table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) for table in tables}

    @staticmethod
    def _logical_digest(connection: sqlite3.Connection) -> str:
        digest = hashlib.sha256()
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]
            safe_columns = [
                column
                for column in columns
                if column.endswith("_sha256")
                or column.endswith("_hash")
                or column
                in {
                    "version",
                    "name",
                    "checksum",
                    "content_key",
                    "relation_key",
                    "artifact_id",
                    "classification_id",
                    "observation_id",
                    "receipt_id",
                    "event_id",
                    "request_id",
                    "job_id",
                    "lease_id",
                    "category_id",
                    "revision_id",
                    "taxonomy_version",
                    "operation",
                    "actor",
                    "merge_target_category_id",
                    "checkpoint_id",
                    "schema_version",
                    "status",
                    "state",
                    "deletion_epoch",
                    "durability_state",
                    "target_kind",
                    "tombstone_id",
                }
            ]
            if not safe_columns:
                safe_columns = columns[:1]
            ordering = ", ".join(f'"{column}"' for column in safe_columns)
            query = f'SELECT {ordering} FROM "{table}" ORDER BY {ordering}'
            digest.update(table.encode("utf-8") + b"\0")
            for row in connection.execute(query):
                encoded = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"), sort_keys=False)
                digest.update(encoded.encode("utf-8") + b"\n")
        return digest.hexdigest()

    def counts(self) -> dict[str, int]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                return self._table_counts(connection)
            finally:
                connection.close()

    def owner_mvp_baseline_snapshot(self, *, scope_scan_ids: dict[SyncScopeId, str]) -> dict[str, Any]:
        """Return the list-backed segment of the aggregate-only Owner MVP baseline.

        The release controller owns the private scan identifiers.  This Store
        method intentionally returns only counts and opaque hashes, so neither
        content IDs, account references, collection names nor local paths can
        become public release evidence.
        """

        if set(scope_scan_ids) != set(OWNER_MVP_LIST_BASELINE_SCOPES):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Owner MVP baseline scope set is incomplete")
        rows: dict[str, dict[str, Any]] = {}
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                for scope_id in SyncScopeId:
                    if scope_id not in OWNER_MVP_LIST_BASELINE_SCOPES:
                        continue
                    platform, relation, receipt_prefix, run_prefix, checkpoint_prefix = OWNER_MVP_LIST_BASELINE_SCOPES[
                        scope_id
                    ]
                    scan_id = str(_uuid(scope_scan_ids[scope_id], label="owner_mvp_scan_id"))
                    suffix = UUID(scan_id).hex
                    run = connection.execute(
                        "SELECT state FROM run_record WHERE run_id = ?",
                        (f"{run_prefix}{suffix}",),
                    ).fetchone()
                    checkpoint = connection.execute(
                        """
                        SELECT cursor_kind, cursor_value_private, full_scan_id, observed_count,
                               completion_confidence, state
                        FROM checkpoint WHERE checkpoint_id = ?
                        """,
                        (f"{checkpoint_prefix}{suffix}",),
                    ).fetchone()
                    checkpoint_complete = False
                    if checkpoint is not None:
                        try:
                            cursor = json.loads(str(checkpoint["cursor_value_private"]))
                        except (TypeError, json.JSONDecodeError):
                            cursor = None
                        checkpoint_complete = (
                            isinstance(cursor, dict)
                            and cursor.get("scope_mode") == "owner_mvp_20"
                            and checkpoint["state"] == "complete"
                            and checkpoint["cursor_kind"] == "bounded_scope_complete"
                            and checkpoint["full_scan_id"] is None
                            and int(checkpoint["observed_count"]) == 20
                            and float(checkpoint["completion_confidence"]) == 1.0
                        )
                    row = connection.execute(
                        """
                        SELECT
                            COUNT(DISTINCT r.relation_key) AS relation_count,
                            COUNT(DISTINCT r.content_key) AS content_count,
                            COUNT(DISTINCT o.observation_id) AS observation_count,
                            COUNT(DISTINCT CASE WHEN r.status = 'active' THEN r.relation_key END) AS active_count
                        FROM user_relation AS r
                        INNER JOIN content AS c ON c.content_key = r.content_key
                        LEFT JOIN source_observation AS o
                          ON o.run_id = ? AND o.content_key = r.content_key
                        WHERE r.scan_receipt_id = ?
                          AND c.platform = ?
                          AND r.relation_type = ?
                        """,
                        (f"{run_prefix}{suffix}", f"{receipt_prefix}{suffix}", platform, relation),
                    ).fetchone()
                    assert row is not None
                    counts = {
                        "active_count": int(row["active_count"]),
                        "content_count": int(row["content_count"]),
                        "observation_count": int(row["observation_count"]),
                        "relation_count": int(row["relation_count"]),
                        "scan_complete": run is not None and run["state"] == "succeeded" and checkpoint_complete,
                    }
                    rows[scope_id.value] = {
                        **counts,
                        "scan_ref_sha256": hashlib.sha256(scan_id.encode("ascii")).hexdigest(),
                    }
            finally:
                connection.close()
        exact = all(
            row["active_count"] == 20
            and row["content_count"] == 20
            and row["observation_count"] == 20
            and row["relation_count"] == 20
            and row["scan_complete"] is True
            for row in rows.values()
        )
        total_relations = sum(int(row["relation_count"]) for row in rows.values())
        digest_basis = {
            scope_id: {key: value for key, value in row.items() if key != "scan_ref_sha256"}
            for scope_id, row in sorted(rows.items())
        }
        return {
            "baseline_hash": hashlib.sha256(
                json.dumps(digest_basis, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "exact_list_scope_baseline": exact,
            "scopes": rows,
            "total_relations": total_relations,
        }

    def owner_mvp_current_content_snapshot(
        self,
        *,
        capture_job_ids: Mapping[str, str],
        expected_content_id_hashes: frozenset[str],
    ) -> dict[str, Any]:
        """Verify the fourth MVP scope from exactly 20 explicit current-page captures.

        The release state stores only a content-ID hash to Native Job mapping.
        This method reads the corresponding Canonical records under a shared
        lock and returns aggregates plus opaque references only; raw IDs and
        current-page URLs never leave the private data plane.
        """

        if (
            len(capture_job_ids) != 20
            or set(capture_job_ids) != set(expected_content_id_hashes)
            or len(expected_content_id_hashes) != 20
        ):
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Owner MVP current-content scope is incomplete")
        identities: dict[str, CurrentPageIdentity] = {}
        for content_id_hash, job_id in capture_job_ids.items():
            _validate_sha256(content_id_hash, label="owner_mvp_current_content_hash")
            identities[content_id_hash] = current_page_identity_from_job(job_id)

        active_count = content_count = observation_count = relation_count = 0
        scan_complete = True
        observed_content_hashes: set[str] = set()
        observed_content_keys: set[str] = set()
        observed_relation_keys: set[str] = set()
        observed_observation_ids: set[str] = set()
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                for expected_hash, identity in identities.items():
                    matched_rows = connection.execute(
                        """
                        SELECT
                            c.content_key,
                            c.platform,
                            c.platform_content_id,
                            o.observation_id,
                            r.relation_key,
                            r.relation_type,
                            r.scan_receipt_id,
                            r.status AS relation_status,
                            run.state AS run_state,
                            checkpoint.cursor_kind,
                            checkpoint.state AS checkpoint_state
                        FROM source_observation AS o
                        INNER JOIN content AS c ON c.content_key = o.content_key
                        INNER JOIN run_record AS run ON run.run_id = o.run_id
                        INNER JOIN checkpoint AS checkpoint ON checkpoint.checkpoint_id = ?
                        INNER JOIN user_relation AS r
                          ON r.content_key = c.content_key AND r.scan_receipt_id = ?
                        WHERE o.run_id = ? AND o.observation_id = ?
                        """,
                        (
                            identity.checkpoint_id,
                            identity.scan_receipt_id,
                            identity.run_id,
                            identity.observation_id,
                        ),
                    ).fetchall()
                    if len(matched_rows) != 1:
                        scan_complete = False
                        continue
                    row = matched_rows[0]
                    observed_hash = hashlib.sha256(str(row["platform_content_id"]).encode("utf-8")).hexdigest()
                    valid = (
                        observed_hash == expected_hash
                        and str(row["platform"]) == "xiaohongshu"
                        and str(row["relation_type"]) == "saved_current"
                        and str(row["relation_status"]) == "active"
                        and str(row["run_state"]) == "succeeded"
                        and str(row["checkpoint_state"]) == "complete"
                        and str(row["cursor_kind"]) == CURRENT_PAGE_CURSOR_COMPLETE
                    )
                    if not valid:
                        scan_complete = False
                        continue
                    observed_content_hashes.add(observed_hash)
                    observed_content_keys.add(str(row["content_key"]))
                    observed_relation_keys.add(str(row["relation_key"]))
                    observed_observation_ids.add(str(row["observation_id"]))
            finally:
                connection.close()
        if len(observed_content_hashes) == 20:
            content_count = 20
        if len(observed_relation_keys) == 20:
            relation_count = 20
            active_count = 20
        if len(observed_observation_ids) == 20:
            observation_count = 20
        scan_complete = (
            scan_complete
            and observed_content_hashes == set(expected_content_id_hashes)
            and len(observed_content_keys) == 20
            and relation_count == 20
            and observation_count == 20
        )
        return {
            "active_count": active_count,
            "content_count": content_count,
            "observation_count": observation_count,
            "relation_count": relation_count,
            "scan_complete": scan_complete,
            "scan_ref_sha256": hashlib.sha256(
                json.dumps(sorted(identity.job_id for identity in identities.values()), separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
        }

    @staticmethod
    def _local_ui_review_required(row: sqlite3.Row) -> bool:
        """Return whether a redacted Canonical row still needs Owner review."""

        classification_id = row["classification_id"]
        if classification_id is None:
            return True
        if str(row["review_status"]) == "suggested":
            return True
        confidence = row["confidence_raw"]
        return str(row["decision_mode"]) in {"model", "hybrid"} and confidence is not None and float(confidence) < 0.90

    @staticmethod
    def _local_ui_review_record(row: sqlite3.Row, artifact_ids: Sequence[str]) -> dict[str, Any]:
        return {
            "artifact_ids": list(artifact_ids),
            "classification_id": None if row["classification_id"] is None else str(row["classification_id"]),
            "confidence_raw": None if row["confidence_raw"] is None else float(row["confidence_raw"]),
            "content_key": str(row["content_key"]),
            "current_category_id": (None if row["primary_category_id"] is None else str(row["primary_category_id"])),
            "decision_mode": None if row["decision_mode"] is None else str(row["decision_mode"]),
            "evidence_artifact_count": len(artifact_ids),
            "platform": str(row["platform"]),
            "review_status": None if row["review_status"] is None else str(row["review_status"]),
            "taxonomy_version": None if row["taxonomy_version"] is None else int(row["taxonomy_version"]),
        }

    @staticmethod
    def _local_ui_review_rows(connection: sqlite3.Connection, *, limit: int) -> tuple[sqlite3.Row, ...]:
        return tuple(
            connection.execute(
                """
                SELECT c.content_key, c.platform, latest.classification_id, latest.primary_category_id,
                       latest.taxonomy_version, latest.decision_mode, latest.confidence_raw,
                       latest.review_status
                FROM content AS c
                LEFT JOIN classification AS latest ON latest.classification_id = (
                    SELECT candidate.classification_id
                    FROM classification AS candidate
                    WHERE candidate.content_key = c.content_key
                    ORDER BY candidate.created_at DESC, candidate.classification_id DESC
                    LIMIT 1
                )
                ORDER BY c.content_key
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )

    @staticmethod
    def _local_ui_artifact_ids(connection: sqlite3.Connection, content_key: str) -> tuple[str, ...]:
        return tuple(
            str(row["artifact_id"])
            for row in connection.execute(
                """
                SELECT artifact_id
                FROM artifact
                WHERE content_key = ?
                ORDER BY artifact_type, artifact_sequence DESC, artifact_id DESC
                """,
                (content_key,),
            ).fetchall()
        )

    def local_ui_snapshot(self, *, limit: int = 100) -> dict[str, Any]:
        """Return an allowlisted local-UI view without payload text or private paths."""

        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Local UI result limit is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                connection.execute("BEGIN")
                health = self._integrity(connection)
                health["foreign_keys"] = int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
                health["schema_version"] = current_version(connection)
                health["status"] = (
                    "healthy"
                    if all(health.get(name) == value for name, value in HEALTHY_CHECKS.items())
                    and health["foreign_keys"]
                    else "failed"
                )
                counts = self._table_counts(connection)
                job_rows = connection.execute(
                    """
                    SELECT r.run_id, r.run_kind, r.state, r.created_at, r.finished_at,
                           d.scope_id, f.error_code, f.fallback_eligible
                    FROM run_record AS r
                    LEFT JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                    LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                    ORDER BY r.created_at DESC, r.run_id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                outbox_rows = connection.execute(
                    """
                    SELECT event_id, sink, content_key, sink_schema_version, status, attempt_count,
                           last_error_code, updated_at
                    FROM outbox_event
                    ORDER BY updated_at DESC, event_id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                capability_rows = connection.execute(
                    """
                    SELECT scope_id, terminal, reason_code, feature_flag, evaluated_at
                    FROM capability_gate_outcome
                    ORDER BY scope_id
                    """
                ).fetchall()
                review_rows = self._local_ui_review_rows(connection, limit=limit)
                reviews: list[dict[str, Any]] = []
                for row in review_rows:
                    if not self._local_ui_review_required(row):
                        continue
                    artifact_ids = self._local_ui_artifact_ids(connection, str(row["content_key"]))
                    reviews.append(self._local_ui_review_record(row, artifact_ids))
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()
        return {
            "capabilities": [
                {
                    "evaluated_at": str(row["evaluated_at"]),
                    "feature_flag": str(row["feature_flag"]),
                    "reason_code": str(row["reason_code"]),
                    "scope_id": str(row["scope_id"]),
                    "terminal": str(row["terminal"]),
                }
                for row in capability_rows
            ],
            "counts": counts,
            "health": health,
            "jobs": [
                {
                    "created_at": str(row["created_at"]),
                    "error_code": None if row["error_code"] is None else str(row["error_code"]),
                    "fallback_eligible": bool(row["fallback_eligible"] or 0),
                    "finished_at": None if row["finished_at"] is None else str(row["finished_at"]),
                    "job_id": str(row["run_id"]),
                    "run_kind": str(row["run_kind"]),
                    "scope_id": None if row["scope_id"] is None else str(row["scope_id"]),
                    "state": str(row["state"]),
                }
                for row in job_rows
            ],
            "outbox": [
                {
                    "attempt_count": int(row["attempt_count"]),
                    "content_key": str(row["content_key"]),
                    "event_id": str(row["event_id"]),
                    "last_error_code": None if row["last_error_code"] is None else str(row["last_error_code"]),
                    "sink": str(row["sink"]),
                    "sink_schema_version": str(row["sink_schema_version"]),
                    "status": str(row["status"]),
                    "updated_at": str(row["updated_at"]),
                }
                for row in outbox_rows
            ],
            "review_queue": reviews,
        }

    def local_ui_review_item(self, content_key: str) -> dict[str, Any] | None:
        """Return a single reviewable item using only immutable identifiers and metadata."""

        if not isinstance(content_key, str) or not 3 <= len(content_key) <= 768 or "\x00" in content_key:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Local UI content key is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                connection.execute("BEGIN")
                row = connection.execute(
                    """
                    SELECT c.content_key, c.platform, latest.classification_id, latest.primary_category_id,
                           latest.taxonomy_version, latest.decision_mode, latest.confidence_raw,
                           latest.review_status
                    FROM content AS c
                    LEFT JOIN classification AS latest ON latest.classification_id = (
                        SELECT candidate.classification_id
                        FROM classification AS candidate
                        WHERE candidate.content_key = c.content_key
                        ORDER BY candidate.created_at DESC, candidate.classification_id DESC
                        LIMIT 1
                    )
                    WHERE c.content_key = ?
                    """,
                    (content_key,),
                ).fetchone()
                if row is None or not self._local_ui_review_required(row):
                    return None
                artifact_ids = self._local_ui_artifact_ids(connection, content_key)
                return self._local_ui_review_record(row, artifact_ids)
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def local_ui_job(self, job_id: str) -> dict[str, Any] | None:
        """Return one durable job's non-sensitive operational state."""

        _validate_token(job_id, label="job_id")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    """
                    SELECT r.run_id, r.run_kind, r.state, r.created_at, r.finished_at,
                           d.scope_id, f.error_code, f.fallback_eligible
                    FROM run_record AS r
                    LEFT JOIN native_dispatch_job AS d ON d.job_id = r.run_id
                    LEFT JOIN run_failure AS f ON f.run_id = r.run_id
                    WHERE r.run_id = ?
                    """,
                    (job_id,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            return None
        return {
            "created_at": str(row["created_at"]),
            "error_code": None if row["error_code"] is None else str(row["error_code"]),
            "fallback_eligible": bool(row["fallback_eligible"] or 0),
            "finished_at": None if row["finished_at"] is None else str(row["finished_at"]),
            "job_id": str(row["run_id"]),
            "run_kind": str(row["run_kind"]),
            "scope_id": None if row["scope_id"] is None else str(row["scope_id"]),
            "state": str(row["state"]),
        }

    def content_exists(self, content_key: str) -> bool:
        return self.content_platform(content_key) is not None

    def content_platform(self, content_key: str) -> str | None:
        if not isinstance(content_key, str) or not content_key or len(content_key) > 512:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "content_key is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    "SELECT platform FROM content WHERE content_key = ?",
                    (content_key,),
                ).fetchone()
            finally:
                connection.close()
        return None if row is None else str(row["platform"])

    @staticmethod
    def _canonical_projection_from_rows(
        *,
        content_row: sqlite3.Row | None,
        relation_rows: Sequence[sqlite3.Row],
        observation_row: sqlite3.Row | None,
        artifact_rows: Sequence[sqlite3.Row],
        classification_row: sqlite3.Row | None,
        category_row: sqlite3.Row | None,
    ) -> CanonicalProjection:
        """Validate and assemble one derived-sink projection from one read snapshot."""

        if content_row is None or observation_row is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink projection lacks Canonical provenance")
        if classification_row is not None and category_row is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink projection category is missing")
        try:
            content = CanonicalContent.model_validate_json(str(content_row["payload_json"]))
            observation = SourceObservation.model_validate_json(str(observation_row["payload_json"]))
            latest_artifacts: list[Artifact] = []
            seen_types: set[str] = set()
            for row in artifact_rows:
                artifact_type = str(row["artifact_type"])
                if artifact_type in seen_types:
                    continue
                seen_types.add(artifact_type)
                latest_artifacts.append(Artifact.model_validate_json(str(row["payload_json"])))
            classification = (
                Classification.model_validate_json(str(classification_row["payload_json"]))
                if classification_row is not None
                else None
            )
            category = (
                TaxonomyCategory.model_validate_json(str(category_row["payload_json"]))
                if category_row is not None
                else None
            )
        except (TypeError, ValueError):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink projection payload is invalid") from None
        if observation.content_key != content.content_key:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink projection provenance diverged")
        if classification is not None and (
            classification.content_key != content.content_key
            or category is None
            or str(classification.primary_category_id) != str(category.category_id)
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink projection classification diverged")
        if any(artifact.content_key != content.content_key for artifact in latest_artifacts):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink projection Artifact diverged")
        return CanonicalProjection(
            content=content,
            relations=tuple(str(row["relation_type"]) for row in relation_rows),
            observation=observation,
            artifacts=tuple(latest_artifacts),
            classification=classification,
            category=category,
        )

    def projection_snapshot(self, content_key: str) -> CanonicalProjection:
        """Read one internally consistent private snapshot for derived sinks."""

        if not isinstance(content_key, str) or not content_key or len(content_key) > 512:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "content_key is invalid")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                connection.execute("BEGIN")
                content_row = connection.execute(
                    "SELECT payload_json FROM content WHERE content_key = ? AND status <> 'deleted_by_user'",
                    (content_key,),
                ).fetchone()
                relation_rows = connection.execute(
                    """
                    SELECT relation_type FROM user_relation
                    WHERE content_key = ? AND status = 'active'
                    ORDER BY relation_type
                    """,
                    (content_key,),
                ).fetchall()
                observation_row = connection.execute(
                    """
                    SELECT payload_json FROM source_observation
                    WHERE content_key = ?
                    ORDER BY observed_at DESC, observation_id DESC LIMIT 1
                    """,
                    (content_key,),
                ).fetchone()
                artifact_rows = connection.execute(
                    """
                    SELECT artifact_type, payload_json FROM artifact
                    WHERE content_key = ?
                    ORDER BY artifact_type, artifact_sequence DESC, artifact_id DESC
                    """,
                    (content_key,),
                ).fetchall()
                classification_row = connection.execute(
                    """
                    SELECT payload_json, primary_category_id FROM classification
                    WHERE content_key = ?
                    ORDER BY created_at DESC, classification_id DESC LIMIT 1
                    """,
                    (content_key,),
                ).fetchone()
                category_row = None
                if classification_row is not None:
                    category_row = connection.execute(
                        "SELECT payload_json FROM taxonomy_category WHERE category_id = ?",
                        (str(classification_row["primary_category_id"]),),
                    ).fetchone()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()
        return self._canonical_projection_from_rows(
            content_row=content_row,
            relation_rows=relation_rows,
            observation_row=observation_row,
            artifact_rows=artifact_rows,
            classification_row=classification_row,
            category_row=category_row,
        )

    def projection_snapshots(self) -> tuple[CanonicalProjection, ...]:
        """Read the complete Canonical sink input from one SQLite read transaction.

        Rebuild callers must not stitch together independently-read Content,
        Classification, and Artifact rows.  This bounded in-memory snapshot keeps
        one deterministic source-of-truth view for a derived Markdown rebuild.
        """

        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                connection.execute("BEGIN")
                content_rows = connection.execute(
                    "SELECT content_key, payload_json FROM content WHERE status <> 'deleted_by_user' ORDER BY content_key"
                ).fetchall()
                relation_rows = connection.execute(
                    """
                    SELECT content_key, relation_type FROM user_relation
                    WHERE status = 'active'
                    ORDER BY content_key, relation_type
                    """
                ).fetchall()
                observation_rows = connection.execute(
                    """
                    SELECT content_key, payload_json FROM source_observation
                    ORDER BY content_key, observed_at DESC, observation_id DESC
                    """
                ).fetchall()
                artifact_rows = connection.execute(
                    """
                    SELECT content_key, artifact_type, payload_json FROM artifact
                    ORDER BY content_key, artifact_type, artifact_sequence DESC, artifact_id DESC
                    """
                ).fetchall()
                classification_rows = connection.execute(
                    """
                    SELECT content_key, payload_json, primary_category_id FROM classification
                    ORDER BY content_key, created_at DESC, classification_id DESC
                    """
                ).fetchall()
                category_rows = connection.execute(
                    "SELECT category_id, payload_json FROM taxonomy_category ORDER BY category_id"
                ).fetchall()
            finally:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

        relations_by_content: dict[str, list[sqlite3.Row]] = {}
        for row in relation_rows:
            relations_by_content.setdefault(str(row["content_key"]), []).append(row)

        latest_observation_by_content: dict[str, sqlite3.Row] = {}
        for row in observation_rows:
            latest_observation_by_content.setdefault(str(row["content_key"]), row)

        artifacts_by_content: dict[str, list[sqlite3.Row]] = {}
        for row in artifact_rows:
            artifacts_by_content.setdefault(str(row["content_key"]), []).append(row)

        latest_classification_by_content: dict[str, sqlite3.Row] = {}
        for row in classification_rows:
            latest_classification_by_content.setdefault(str(row["content_key"]), row)
        categories_by_id = {str(row["category_id"]): row for row in category_rows}

        snapshots: list[CanonicalProjection] = []
        for content_row in content_rows:
            content_key = str(content_row["content_key"])
            classification_row = latest_classification_by_content.get(content_key)
            category_row = (
                None
                if classification_row is None
                else categories_by_id.get(str(classification_row["primary_category_id"]))
            )
            snapshots.append(
                self._canonical_projection_from_rows(
                    content_row=content_row,
                    relation_rows=relations_by_content.get(content_key, ()),
                    observation_row=latest_observation_by_content.get(content_key),
                    artifact_rows=artifacts_by_content.get(content_key, ()),
                    classification_row=classification_row,
                    category_row=category_row,
                )
            )
        return tuple(snapshots)

    def logical_digest(self) -> str:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                return self._logical_digest(connection)
            finally:
                connection.close()

    @staticmethod
    def _lifecycle_state_from_row(row: sqlite3.Row) -> LifecycleState:
        manifest = row["latest_manifest_sha256"]
        if manifest is not None:
            _validate_sha256(str(manifest), label="latest_manifest_sha256")
        state = str(row["durability_state"])
        if state not in {"durability_pending", "durability_verified"}:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle durability state is invalid")
        epoch = int(row["deletion_epoch"])
        if epoch < 0:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle deletion epoch is invalid")
        return LifecycleState(
            deletion_epoch=epoch,
            durability_state=state,
            latest_manifest_sha256=None if manifest is None else str(manifest),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _lifecycle_tombstone_from_row(row: sqlite3.Row) -> LifecycleTombstone:
        kind = str(row["target_kind"])
        if kind not in LIFECYCLE_TOMBSTONE_KINDS:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle tombstone kind is invalid")
        target = _validate_lifecycle_target(str(row["target_key_private"]), label="lifecycle_target")
        target_hash = _validate_sha256(str(row["target_key_sha256"]), label="lifecycle_target_sha256")
        if hashlib.sha256(target.encode("utf-8")).hexdigest() != target_hash:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle tombstone target hash is invalid")
        return LifecycleTombstone(
            tombstone_id=_validate_token(str(row["tombstone_id"]), label="tombstone_id"),
            target_kind=kind,
            target_key_private=target,
            target_key_sha256=target_hash,
            deletion_epoch=int(row["deletion_epoch"]),
            created_at=str(row["created_at"]),
        )

    def lifecycle_state(self) -> LifecycleState:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    "SELECT deletion_epoch, durability_state, latest_manifest_sha256, updated_at "
                    "FROM lifecycle_state WHERE state_id = 1"
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle state is unavailable")
        return self._lifecycle_state_from_row(row)

    def lifecycle_tombstones(self) -> tuple[LifecycleTombstone, ...]:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                rows = connection.execute(
                    """
                    SELECT tombstone_id, target_kind, target_key_private, target_key_sha256, deletion_epoch, created_at
                    FROM lifecycle_tombstone ORDER BY deletion_epoch
                    """
                ).fetchall()
            finally:
                connection.close()
        return tuple(self._lifecycle_tombstone_from_row(row) for row in rows)

    def lifecycle_delete_preview(self, *, target_kind: str, target_key_private: str) -> dict[str, str | int | bool]:
        if target_kind not in LIFECYCLE_TOMBSTONE_KINDS:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle target kind is invalid")
        target = _validate_lifecycle_target(target_key_private, label="lifecycle_target")
        target_hash = hashlib.sha256(target.encode("utf-8")).hexdigest()
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                existing = connection.execute(
                    "SELECT 1 FROM lifecycle_tombstone WHERE target_kind = ? AND target_key_private = ?",
                    (target_kind, target),
                ).fetchone()
                content_rows = relation_rows = pending_outbox = 0
                if target_kind == "content":
                    content_rows = int(
                        connection.execute("SELECT COUNT(*) FROM content WHERE content_key = ?", (target,)).fetchone()[
                            0
                        ]
                    )
                    relation_rows = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM user_relation WHERE content_key = ?", (target,)
                        ).fetchone()[0]
                    )
                    pending_outbox = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM outbox_event WHERE content_key = ? AND status IN ('pending','leased')",
                            (target,),
                        ).fetchone()[0]
                    )
                elif target_kind == "relation":
                    relation_rows = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM user_relation WHERE relation_key = ?", (target,)
                        ).fetchone()[0]
                    )
                elif target_kind == "sink":
                    pending_outbox = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM outbox_event WHERE content_key = ? AND status IN ('pending','leased')",
                            (target,),
                        ).fetchone()[0]
                    )
                elif target != "active_runtime":
                    raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle runtime target is invalid")
            finally:
                connection.close()
        return {
            "already_tombstoned": existing is not None,
            "content_rows": content_rows,
            "durable_hard_erase": "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED",
            "pending_outbox": pending_outbox,
            "relation_rows": relation_rows,
            "target_key_sha256": target_hash,
            "target_kind": target_kind,
        }

    @staticmethod
    def _tombstone_content(connection: sqlite3.Connection, content_key: str, *, now: str) -> None:
        row = connection.execute(
            "SELECT payload_json, record_version, status FROM content WHERE content_key = ?", (content_key,)
        ).fetchone()
        if row is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle content target does not exist")
        if str(row["status"]) == "deleted_by_user":
            return
        try:
            current = CanonicalContent.model_validate_json(str(row["payload_json"]))
            candidate_data = current.model_dump(mode="json", by_alias=True)
            candidate_data["record_version"] = max(int(row["record_version"]), current.record_version) + 1
            candidate_data["status"] = "deleted_by_user"
            candidate = CanonicalContent.model_validate_json(
                json.dumps(candidate_data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            )
        except (TypeError, ValueError):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle content payload is invalid") from None
        payload_json, payload_sha = _payload(candidate)
        connection.execute(
            """
            UPDATE content SET record_version = ?, status = 'deleted_by_user', payload_json = ?, payload_sha256 = ?,
                updated_at = ? WHERE content_key = ?
            """,
            (candidate.record_version, payload_json, payload_sha, now, content_key),
        )

    @staticmethod
    def _tombstone_relation(connection: sqlite3.Connection, relation_key: str, *, now: str) -> None:
        row = connection.execute(
            "SELECT payload_json, status, confirmed_by FROM user_relation WHERE relation_key = ?", (relation_key,)
        ).fetchone()
        if row is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle relation target does not exist")
        if str(row["status"]) == "removed" and str(row["confirmed_by"]) == "owner":
            return
        try:
            current = UserRelation.model_validate_json(str(row["payload_json"]))
            candidate_data = current.model_dump(mode="json", by_alias=True)
            candidate_data["status"] = "removed"
            candidate_data["confirmed_by"] = "owner"
            candidate = UserRelation.model_validate_json(
                json.dumps(candidate_data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            )
        except (TypeError, ValueError):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle relation payload is invalid") from None
        payload_json, payload_sha = _payload(candidate)
        connection.execute(
            """
            UPDATE user_relation SET status = 'removed', confirmed_by = 'owner', payload_json = ?, payload_sha256 = ?,
                updated_at = ? WHERE relation_key = ?
            """,
            (payload_json, payload_sha, now, relation_key),
        )

    @staticmethod
    def _tombstone_sink(connection: sqlite3.Connection, content_key: str, *, now: str) -> None:
        existing = connection.execute("SELECT 1 FROM content WHERE content_key = ?", (content_key,)).fetchone()
        if existing is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle sink target does not exist")
        connection.execute(
            """
            UPDATE outbox_event SET status = 'cancelled', lease_id = NULL, lease_owner = NULL,
                lease_expires_at = NULL, updated_at = ?
            WHERE content_key = ? AND status IN ('pending', 'leased')
            """,
            (now, content_key),
        )

    def record_owner_tombstone(
        self, *, target_kind: str, target_key_private: str, now: str | None = None
    ) -> LifecycleTombstone:
        if target_kind not in LIFECYCLE_TOMBSTONE_KINDS:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle target kind is invalid")
        target = _validate_lifecycle_target(target_key_private, label="lifecycle_target")
        created_at = now or _now()
        target_hash = hashlib.sha256(target.encode("utf-8")).hexdigest()
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT tombstone_id, target_kind, target_key_private, target_key_sha256, deletion_epoch, created_at
                FROM lifecycle_tombstone WHERE target_kind = ? AND target_key_private = ?
                """,
                (target_kind, target),
            ).fetchone()
            if existing is not None:
                return self._lifecycle_tombstone_from_row(existing)
            state_row = connection.execute("SELECT deletion_epoch FROM lifecycle_state WHERE state_id = 1").fetchone()
            if state_row is None:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Lifecycle state is unavailable")
            next_epoch = int(state_row["deletion_epoch"]) + 1
            if target_kind == "content":
                self._tombstone_content(connection, target, now=created_at)
            elif target_kind == "relation":
                self._tombstone_relation(connection, target, now=created_at)
            elif target_kind == "sink":
                self._tombstone_sink(connection, target, now=created_at)
            elif target != "active_runtime":
                raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Lifecycle runtime target is invalid")
            payload = {
                "deletion_epoch": next_epoch,
                "schema_version": "1.0",
                "target_key_sha256": target_hash,
                "target_kind": target_kind,
            }
            rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            tombstone_id = f"tombstone_{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO lifecycle_tombstone(
                    tombstone_id, target_kind, target_key_private, target_key_sha256, deletion_epoch,
                    payload_json, payload_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tombstone_id,
                    target_kind,
                    target,
                    target_hash,
                    next_epoch,
                    rendered,
                    hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                    created_at,
                ),
            )
            connection.execute(
                """
                UPDATE lifecycle_state SET deletion_epoch = ?, durability_state = 'durability_pending',
                    latest_manifest_sha256 = NULL, updated_at = ? WHERE state_id = 1
                """,
                (next_epoch, created_at),
            )
        return LifecycleTombstone(
            tombstone_id=tombstone_id,
            target_kind=target_kind,
            target_key_private=target,
            target_key_sha256=target_hash,
            deletion_epoch=next_epoch,
            created_at=created_at,
        )

    def mark_durability_pending(self, *, now: str | None = None) -> LifecycleState:
        observed_at = now or _now()
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE lifecycle_state SET durability_state = 'durability_pending', latest_manifest_sha256 = NULL,
                    updated_at = ? WHERE state_id = 1
                """,
                (observed_at,),
            )
        return self.lifecycle_state()

    def mark_durability_verified(self, manifest_sha256: str, *, now: str | None = None) -> LifecycleState:
        verified_at = now or _now()
        _validate_sha256(manifest_sha256, label="lifecycle_manifest_sha256")
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE lifecycle_state SET durability_state = 'durability_verified', latest_manifest_sha256 = ?,
                    updated_at = ? WHERE state_id = 1
                """,
                (manifest_sha256, verified_at),
            )
        return self.lifecycle_state()

    def _backup_paths(self, backup_id: str) -> tuple[Path, Path]:
        _validate_token(backup_id, label="backup_id")
        database = self.paths.backups_directory / f"canonical-{backup_id}.sqlite"
        manifest = self.paths.backups_directory / f"canonical-{backup_id}.manifest.json"
        return database, manifest

    def backup(self, *, label: str = "recovery") -> BackupReceipt:
        _validate_token(label, label="backup_label")
        backup_id = f"backup_{label}_{uuid.uuid4().hex}"
        target, manifest_path = self._backup_paths(backup_id)
        temporary = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
        if target.exists() or manifest_path.exists():
            raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Backup identity already exists")
        try:
            with self._file_lock(exclusive=True):
                source = self._open(writable=True)
                destination = sqlite3.connect(temporary, isolation_level=None)
                try:
                    source.execute("PRAGMA wal_checkpoint(FULL)")
                    source.backup(destination)
                    destination.row_factory = sqlite3.Row
                    checks = self._integrity(destination)
                    if checks != HEALTHY_CHECKS:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backup integrity check failed")
                    version = current_version(destination)
                    counts = self._table_counts(destination)
                    logical = self._logical_digest(destination)
                finally:
                    destination.close()
                    source.close()
                temporary.chmod(0o600)
                descriptor = os.open(temporary, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(temporary, target)
                target.chmod(0o600)
                self.paths.ensure_private_file(target)
                database_sha = _file_sha256(target)
                receipt = BackupReceipt(
                    backup_id=backup_id,
                    database_sha256=database_sha,
                    logical_sha256=logical,
                    schema_version=version,
                    size_bytes=target.stat().st_size,
                    table_counts=counts,
                )
                _atomic_private_json(
                    manifest_path,
                    {
                        **receipt.safe_dict(),
                        "created_at": _now(),
                        "disaster_recovery": False,
                        "file_name": target.name,
                        "foreign_key_check": "ok",
                        "foreign_key_violations": 0,
                        "integrity_check": "ok",
                        "quick_check": "ok",
                        "scope": "local_recovery_copy_only",
                    },
                )
                self.paths.ensure_private_file(manifest_path)
            return receipt
        except Exception:
            if temporary.exists():
                temporary.unlink()
            if target.exists() and not manifest_path.exists():
                target.unlink()
            raise

    def rehearse_backup_restore(self, *, backup_id: str, expected_sha256: str) -> dict[str, Any]:
        """Restore a verified backup into a disposable private SQLite copy.

        The rehearsal proves that rollback material is readable and compatible
        without replacing the active Canonical Store or deleting Owner data.
        """

        _validate_token(backup_id, label="backup_id")
        _validate_sha256(expected_sha256, label="backup_sha256")
        backup_path, _manifest_path = self._backup_paths(backup_id)
        if not backup_path.is_file() or backup_path.is_symlink() or _file_sha256(backup_path) != expected_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Rollback backup does not match its receipt")
        rehearsal = backup_path.with_name(f".{backup_path.name}.rehearsal-{uuid.uuid4().hex}")
        completed = False
        try:
            with self._file_lock(exclusive=False):
                source: sqlite3.Connection | None = None
                restored: sqlite3.Connection | None = None
                try:
                    source = sqlite3.connect(backup_path)
                    restored = sqlite3.connect(rehearsal)
                    source.row_factory = sqlite3.Row
                    restored.row_factory = sqlite3.Row
                    restored.execute("PRAGMA foreign_keys = ON")
                    source.backup(restored)
                    source_checks = self._integrity(source)
                    restored_checks = self._integrity(restored)
                    source_version = current_version(source)
                    restored_version = current_version(restored)
                    source_counts = self._table_counts(source)
                    restored_counts = self._table_counts(restored)
                    source_digest = self._logical_digest(source)
                    restored_digest = self._logical_digest(restored)
                finally:
                    if restored is not None:
                        restored.close()
                    if source is not None:
                        source.close()
            rehearsal.chmod(0o600)
            if (
                source_checks != HEALTHY_CHECKS
                or restored_checks != HEALTHY_CHECKS
                or source_version != restored_version
                or source_counts != restored_counts
                or source_digest != restored_digest
            ):
                raise X2NRuntimeError(
                    ErrorCode.DATA_INTEGRITY_FAILED, "Rollback rehearsal did not preserve the Canonical Store"
                )
            completed = True
            return {
                "backup_sha256": expected_sha256,
                "logical_digest_match": True,
                "restored_to_disposable_private_copy": True,
                "schema_version": restored_version,
                "table_counts_match": True,
                "temporary_copy_removed": True,
            }
        finally:
            if rehearsal.exists() or rehearsal.is_symlink():
                if rehearsal.is_symlink() or not rehearsal.is_file():
                    raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Rollback rehearsal temporary target became unsafe")
                rehearsal.unlink()
            if not completed and rehearsal.exists():
                rehearsal.unlink()

    def verify_backup(self, backup_id: str, *, expected_sha256: str | None = None) -> BackupReceipt:
        target, manifest_path = self._backup_paths(backup_id)
        if not target.is_file() or target.is_symlink() or not manifest_path.is_file() or manifest_path.is_symlink():
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backup set is incomplete")
        self.paths.ensure_private_file(target)
        self.paths.ensure_private_file(manifest_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backup manifest is invalid") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("backup_id") != backup_id
            or manifest.get("file_name") != target.name
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backup manifest identity is invalid")
        actual_sha = _file_sha256(target)
        required_sha = expected_sha256 or str(manifest.get("database_sha256", ""))
        _validate_sha256(required_sha, label="backup_sha256")
        if actual_sha != required_sha or actual_sha != manifest.get("database_sha256"):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backup hash verification failed")
        uri = f"file:{quote(str(target))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            checks = self._integrity(connection)
            version = current_version(connection)
            counts = self._table_counts(connection)
            logical = self._logical_digest(connection)
        finally:
            connection.close()
        if (
            checks != HEALTHY_CHECKS
            or manifest.get("foreign_key_check") != "ok"
            or manifest.get("foreign_key_violations") != 0
            or manifest.get("integrity_check") != "ok"
            or manifest.get("quick_check") != "ok"
            or version != manifest.get("schema_version")
            or counts != manifest.get("table_counts")
            or logical != manifest.get("logical_sha256")
        ):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backup logical verification failed")
        return BackupReceipt(
            backup_id=backup_id,
            database_sha256=actual_sha,
            logical_sha256=logical,
            schema_version=version,
            size_bytes=target.stat().st_size,
            table_counts=counts,
        )

    def migrate_to_latest(self) -> int:
        with self._file_lock(exclusive=True):
            connection = self._open(writable=True)
            try:
                version = migrate_forward(connection, LATEST_SCHEMA_VERSION, applied_at=_now())
            finally:
                connection.close()
            self._secure_sqlite_files()
            return version

    def downgrade_with_backup(self, target_version: int) -> BackupReceipt:
        receipt = self.backup(label=f"before_v{target_version}")
        verified = self.verify_backup(receipt.backup_id, expected_sha256=receipt.database_sha256)
        with self._file_lock(exclusive=True):
            connection = self._open(writable=True)
            try:
                migrate_backward(connection, target_version, verified_backup=True)
                checks = self._integrity(connection)
                if checks != HEALTHY_CHECKS:
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED, "Downgraded Store failed integrity verification"
                    )
            finally:
                connection.close()
            self._secure_sqlite_files()
        return verified

    def restore(self, backup_id: str, *, expected_sha256: str) -> BackupReceipt:
        receipt = self.verify_backup(backup_id, expected_sha256=expected_sha256)
        source_path, _ = self._backup_paths(backup_id)
        temporary = self.paths.canonical_directory / f".canonical.restore-{uuid.uuid4().hex}.sqlite"
        try:
            with self._file_lock(exclusive=True):
                source_uri = f"file:{quote(str(source_path))}?mode=ro"
                source = sqlite3.connect(source_uri, uri=True, isolation_level=None)
                destination = sqlite3.connect(temporary, isolation_level=None)
                try:
                    source.backup(destination)
                    destination.row_factory = sqlite3.Row
                    if self._integrity(destination) != HEALTHY_CHECKS:
                        raise X2NRuntimeError(
                            ErrorCode.DATA_INTEGRITY_FAILED, "Restore candidate failed integrity verification"
                        )
                    if current_version(destination) != receipt.schema_version:
                        raise X2NRuntimeError(
                            ErrorCode.DATA_INTEGRITY_FAILED, "Restore candidate schema is incompatible"
                        )
                    if self._logical_digest(destination) != receipt.logical_sha256:
                        raise X2NRuntimeError(
                            ErrorCode.DATA_INTEGRITY_FAILED, "Restore candidate logical digest changed"
                        )
                finally:
                    destination.close()
                    source.close()
                temporary.chmod(0o600)
                descriptor = os.open(temporary, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                if self.paths.database.exists():
                    current = self._open(writable=True)
                    try:
                        current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    finally:
                        current.close()
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(self.paths.database) + suffix)
                    if sidecar.exists():
                        sidecar.unlink()
                os.replace(temporary, self.paths.database)
                self.paths.database.chmod(0o600)
                restored = self._open(writable=True)
                try:
                    if self._integrity(restored) != HEALTHY_CHECKS:
                        raise X2NRuntimeError(
                            ErrorCode.DATA_INTEGRITY_FAILED, "Restored Store failed final integrity verification"
                        )
                    restored.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    restored.close()
                self._secure_sqlite_files()
            if self.logical_digest() != receipt.logical_sha256:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restored Store logical digest changed")
            return receipt
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _verify_tombstone_application(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT target_kind, target_key_private FROM lifecycle_tombstone ORDER BY deletion_epoch"
        ).fetchall()
        for row in rows:
            kind = str(row["target_kind"])
            target = str(row["target_key_private"])
            if kind == "content":
                state = connection.execute("SELECT status FROM content WHERE content_key = ?", (target,)).fetchone()
                if state is None or str(state["status"]) != "deleted_by_user":
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restored content tombstone was not applied")
            elif kind == "relation":
                state = connection.execute(
                    "SELECT status, confirmed_by FROM user_relation WHERE relation_key = ?", (target,)
                ).fetchone()
                if state is None or str(state["status"]) != "removed" or str(state["confirmed_by"]) != "owner":
                    raise X2NRuntimeError(
                        ErrorCode.DATA_INTEGRITY_FAILED, "Restored relation tombstone was not applied"
                    )
            elif kind == "sink":
                pending = connection.execute(
                    "SELECT 1 FROM outbox_event WHERE content_key = ? AND status IN ('pending', 'leased')", (target,)
                ).fetchone()
                if pending is not None:
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restored sink tombstone was not applied")
            elif kind not in {"sink", "runtime"}:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restored lifecycle tombstone is invalid")

    def restore_archival_snapshot(
        self,
        snapshot_path: Path,
        *,
        expected_database_sha256: str,
        expected_logical_sha256: str,
        expected_schema_version: int,
        expected_deletion_epoch: int,
    ) -> BackupReceipt:
        """Replace the active DB only with a verified, current-epoch archive snapshot.

        The caller is responsible for making the archive path a private, temporary
        file below `X2N_DATA_ROOT`; this method refuses arbitrary external paths.
        """

        _validate_sha256(expected_database_sha256, label="archive_database_sha256")
        _validate_sha256(expected_logical_sha256, label="archive_logical_sha256")
        if not isinstance(expected_schema_version, int) or expected_schema_version < 1:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Archive schema version is invalid")
        if not isinstance(expected_deletion_epoch, int) or expected_deletion_epoch < 0:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Archive deletion epoch is invalid")
        try:
            source_path = snapshot_path.resolve(strict=True)
            source_path.relative_to(self.paths.data_root)
        except (OSError, ValueError):
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Archive snapshot is outside Private Runtime") from None
        if source_path.is_symlink() or not source_path.is_file():
            raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Archive snapshot is unsafe")
        self.paths.ensure_private_file(source_path)
        if _file_sha256(source_path) != expected_database_sha256:
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive snapshot hash is invalid")

        source_uri = f"file:{quote(str(source_path))}?mode=ro"
        source = sqlite3.connect(source_uri, uri=True, isolation_level=None)
        source.row_factory = sqlite3.Row
        try:
            self._configure(source, writable=False)
            if self._integrity(source) != HEALTHY_CHECKS:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive snapshot integrity is invalid")
            if current_version(source) != expected_schema_version:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive snapshot schema is invalid")
            if self._logical_digest(source) != expected_logical_sha256:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive snapshot logical digest is invalid")
            state_row = source.execute("SELECT deletion_epoch FROM lifecycle_state WHERE state_id = 1").fetchone()
            if state_row is None or int(state_row["deletion_epoch"]) != expected_deletion_epoch:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive deletion epoch is invalid")
            self._verify_tombstone_application(source)
            counts = self._table_counts(source)
        finally:
            source.close()

        temporary = self.paths.canonical_directory / f".canonical.archival-restore-{uuid.uuid4().hex}.sqlite"
        try:
            with self._file_lock(exclusive=True):
                if self.paths.database.exists():
                    current = self._open(writable=False)
                    try:
                        state_row = current.execute(
                            "SELECT deletion_epoch FROM lifecycle_state WHERE state_id = 1"
                        ).fetchone()
                        if state_row is None:
                            raise X2NRuntimeError(
                                ErrorCode.DATA_INTEGRITY_FAILED, "Current lifecycle state is unavailable"
                            )
                        if expected_deletion_epoch < int(state_row["deletion_epoch"]):
                            raise X2NRuntimeError(
                                ErrorCode.POLICY_BLOCKED,
                                "Archive restore would regress the deletion epoch",
                            )
                    finally:
                        current.close()
                source = sqlite3.connect(source_uri, uri=True, isolation_level=None)
                destination = sqlite3.connect(temporary, isolation_level=None)
                try:
                    source.backup(destination)
                    destination.row_factory = sqlite3.Row
                    if self._integrity(destination) != HEALTHY_CHECKS:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive restore candidate is invalid")
                    if current_version(destination) != expected_schema_version:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive restore schema changed")
                    if self._logical_digest(destination) != expected_logical_sha256:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive restore logical digest changed")
                    self._verify_tombstone_application(destination)
                finally:
                    destination.close()
                    source.close()
                temporary.chmod(0o600)
                descriptor = os.open(temporary, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                if self.paths.database.exists():
                    current = self._open(writable=True)
                    try:
                        current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    finally:
                        current.close()
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(self.paths.database) + suffix)
                    if sidecar.exists():
                        sidecar.unlink()
                os.replace(temporary, self.paths.database)
                self.paths.database.chmod(0o600)
                restored = self._open(writable=True)
                try:
                    if self._integrity(restored) != HEALTHY_CHECKS:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive restored Store is invalid")
                    if self._logical_digest(restored) != expected_logical_sha256:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Archive restored Store changed")
                    self._verify_tombstone_application(restored)
                    restored.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    restored.close()
                self._secure_sqlite_files()
            return BackupReceipt(
                backup_id=f"archive_{expected_database_sha256[:24]}",
                database_sha256=expected_database_sha256,
                logical_sha256=expected_logical_sha256,
                schema_version=expected_schema_version,
                size_bytes=source_path.stat().st_size,
                table_counts=counts,
            )
        finally:
            if temporary.exists():
                temporary.unlink()
