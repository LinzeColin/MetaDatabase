"""SQLite Canonical Store, recovery primitives, outbox, and leases."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote

from x2n_contracts import (
    Artifact,
    CanonicalContent,
    Classification,
    DuplicateDisposition,
    ErrorCode,
    SinkReceipt,
    SourceObservation,
    TaxonomyCategory,
    UserRelation,
)

from .migrations import (
    LATEST_SCHEMA_VERSION,
    current_version,
    migrate_backward,
    migrate_forward,
    schema_snapshot,
)
from .runtime import RuntimePaths, X2NRuntimeError, _atomic_private_json


SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_MEDIA_LEASE_SECONDS = 24 * 60 * 60
HEALTHY_CHECKS: dict[str, str | int] = {
    "foreign_key_check": "ok",
    "foreign_key_violations": 0,
    "integrity_check": "ok",
    "quick_check": "ok",
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
class OutboxClaim:
    event_id: str
    lease_id: str
    sink: str
    content_key: str
    desired_projection_hash: str
    sink_schema_version: str
    attempt_count: int


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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _future(now: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(now.removesuffix("Z") + "+00:00")
    return (parsed + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_token(value: str, *, label: str) -> str:
    if SAFE_TOKEN.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    return value


def _validate_sha256(value: str, *, label: str) -> str:
    if SHA256.fullmatch(value) is None:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, f"{label} is invalid")
    return value


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
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical write violated a Store invariant") from error
            except sqlite3.Error as error:
                connection.rollback()
                raise X2NRuntimeError(ErrorCode.STORAGE_FAILED, "Canonical transaction failed atomically") from error
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
        if existing is not None and str(existing["payload_sha256"]) == payload_sha:
            return WriteDisposition.UNCHANGED
        if existing is not None and content.record_version <= int(existing["record_version"]):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Canonical content version conflicts with stored truth")
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
        existing = connection.execute(
            "SELECT payload_sha256, last_seen_at FROM user_relation WHERE relation_key = ?",
            (relation.relation_key,),
        ).fetchone()
        if existing is not None and str(existing["payload_sha256"]) == payload_sha:
            return WriteDisposition.UNCHANGED
        last_seen = relation.last_seen_at.isoformat().replace("+00:00", "Z")
        if existing is not None and last_seen < str(existing["last_seen_at"]):
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Relation observation would move backward")
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
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Observation identity conflicts with append-only history")
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
            raise X2NRuntimeError(ErrorCode.ARTIFACT_VERSION_CONFLICT, "Artifact identity conflicts with append-only history")
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

    def put_taxonomy_category(self, category: TaxonomyCategory) -> WriteDisposition:
        payload_json, payload_sha = _payload(category)
        now = _now()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_sha256, version FROM taxonomy_category WHERE category_id = ?",
                (str(category.category_id),),
            ).fetchone()
            if existing is not None and str(existing["payload_sha256"]) == payload_sha:
                return WriteDisposition.UNCHANGED
            if existing is not None and category.version <= int(existing["version"]):
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Taxonomy category version conflicts with Owner truth")
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO taxonomy_category(
                        category_id, name, slug, priority, enabled, version, level, created_by,
                        payload_json, payload_sha256, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(category.category_id), category.name, category.slug, category.priority,
                        int(category.enabled), category.version, category.level, category.created_by,
                        payload_json, payload_sha, now, now,
                    ),
                )
                return WriteDisposition.INSERTED
            connection.execute(
                """
                UPDATE taxonomy_category SET
                    name = ?, slug = ?, priority = ?, enabled = ?, version = ?, payload_json = ?,
                    payload_sha256 = ?, updated_at = ?
                WHERE category_id = ?
                """,
                (
                    category.name, category.slug, category.priority, int(category.enabled),
                    category.version, payload_json, payload_sha, now, str(category.category_id),
                ),
            )
            return WriteDisposition.UPDATED

    def append_classification(self, classification: Classification) -> WriteDisposition:
        payload_json, payload_sha = _payload(classification)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_sha256 FROM classification WHERE classification_id = ?",
                (classification.classification_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_sha256"]) == payload_sha:
                    return WriteDisposition.UNCHANGED
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Classification identity conflicts with append-only history")
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
            raise X2NRuntimeError(ErrorCode.NATIVE_DUPLICATE_REQUEST, "Request identity conflicts with the existing payload")

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
            )

    def get_skeleton_job(self, job_id: str) -> SkeletonJob:
        _validate_token(job_id, label="job_id")
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                row = connection.execute(
                    """
                    SELECT r.state
                    FROM run_record AS r
                    INNER JOIN request_ledger AS l ON l.job_id = r.run_id
                    WHERE r.run_id = ? AND r.run_kind IN ('native_capture_skeleton','native_sync_skeleton')
                    """,
                    (job_id,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Native Job does not exist")
        return SkeletonJob(
            job_id=job_id,
            state=str(row["state"]),
            disposition=DuplicateDisposition.RETURN_EXISTING_JOB,
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
                    event_id, event_key, sink, content_key, desired_projection_hash,
                    sink_schema_version, observed_at, observed_at, observed_at,
                ),
            )
            return WriteDisposition.INSERTED, event_id

    def claim_outbox(
        self,
        *,
        worker_id: str,
        now: str | None = None,
        lease_seconds: int = 60,
    ) -> OutboxClaim | None:
        _validate_token(worker_id, label="worker_id")
        if lease_seconds < 1 or lease_seconds > 3_600:
            raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Outbox lease duration is invalid")
        claimed_at = now or _now()
        expires_at = _future(claimed_at, lease_seconds)
        with self._transaction() as connection:
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

    def complete_outbox(self, claim: OutboxClaim, receipt: SinkReceipt) -> WriteDisposition:
        payload_json, payload_sha = _payload(receipt)
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT sink, content_key, desired_projection_hash, sink_schema_version, status,
                       lease_id
                FROM outbox_event WHERE event_id = ?
                """,
                (claim.event_id,),
            ).fetchone()
            if row is None or str(row["status"]) != "leased" or str(row["lease_id"]) != claim.lease_id:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Outbox lease is stale or unavailable")
            expected = (
                str(row["sink"]), str(row["content_key"]),
                str(row["desired_projection_hash"]), str(row["sink_schema_version"]),
            )
            actual = (
                receipt.sink.value, receipt.content_key,
                receipt.desired_projection_hash, receipt.sink_schema_version,
            )
            if actual != expected:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink receipt does not match the leased Outbox event")
            delivered_at = receipt.delivered_at.isoformat().replace("+00:00", "Z")
            self._ensure_run(connection, receipt.run_id, delivered_at)
            existing = connection.execute(
                "SELECT payload_sha256 FROM sink_receipt WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            if existing is not None and str(existing["payload_sha256"]) != payload_sha:
                raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Sink receipt identity conflicts with append-only history")
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
                        receipt.receipt_id, receipt.sink_key, receipt.sink.value,
                        receipt.content_key, receipt.sink_schema_version,
                        receipt.desired_projection_hash, receipt.output_hash,
                        receipt.sink_object_ref, receipt.external_ref_hash,
                        receipt.status.value, delivered_at, receipt.run_id,
                        payload_json, payload_sha,
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
        created_at = now or _now()
        lease_id = f"media_{uuid.uuid4().hex}"
        relative_path = f"{run_id}/{lease_id}.bin"
        with self._transaction() as connection:
            self._ensure_run(connection, run_id, created_at)
            connection.execute(
                """
                INSERT INTO media_lease(
                    lease_id, run_id, content_key, purpose, content_hash, mime, size_bytes,
                    duration_seconds, created_at, expires_at, status, local_relative_path,
                    cleanup_error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL)
                """,
                (
                    lease_id, run_id, content_key, purpose, content_hash, mime, size_bytes,
                    duration_seconds, created_at, _future(created_at, ttl_seconds), relative_path,
                ),
            )
        return lease_id

    def recovery_plan(self, *, now: str | None = None) -> RecoveryPlan:
        observed_at = now or _now()
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                checks = self._integrity(connection)
                values = {
                    "expired_outbox_leases": int(connection.execute(
                        "SELECT COUNT(*) FROM outbox_event WHERE status = 'leased' AND lease_expires_at <= ?",
                        (observed_at,),
                    ).fetchone()[0]),
                    "expired_media_leases": int(connection.execute(
                        "SELECT COUNT(*) FROM media_lease WHERE status IN ('active','processing','cleanup_pending') AND expires_at <= ?",
                        (observed_at,),
                    ).fetchone()[0]),
                    "running_jobs": int(connection.execute(
                        "SELECT COUNT(*) FROM run_record WHERE state IN ('running','recovery')"
                    ).fetchone()[0]),
                    "pending_outbox": int(connection.execute(
                        "SELECT COUNT(*) FROM outbox_event WHERE status IN ('pending','leased')"
                    ).fetchone()[0]),
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
                    f"recovery_{uuid.uuid4().hex}", observed_at,
                    before.expired_outbox_leases, before.expired_media_leases,
                    before.running_jobs, result_hash,
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
                column for column in columns
                if column.endswith("_sha256")
                or column.endswith("_hash")
                or column in {
                    "version", "name", "checksum", "content_key", "relation_key",
                    "artifact_id", "classification_id", "observation_id", "receipt_id",
                    "event_id", "request_id", "job_id", "lease_id", "category_id",
                    "checkpoint_id", "schema_version", "status", "state",
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

    def logical_digest(self) -> str:
        with self._file_lock(exclusive=False):
            connection = self._open(writable=False)
            try:
                return self._logical_digest(connection)
            finally:
                connection.close()

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
        if not isinstance(manifest, dict) or manifest.get("backup_id") != backup_id or manifest.get("file_name") != target.name:
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
                    raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Downgraded Store failed integrity verification")
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
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore candidate failed integrity verification")
                    if current_version(destination) != receipt.schema_version:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore candidate schema is incompatible")
                    if self._logical_digest(destination) != receipt.logical_sha256:
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restore candidate logical digest changed")
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
                        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Restored Store failed final integrity verification")
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
