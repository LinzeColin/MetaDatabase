"""Versioned SQLite migrations for the x2n Canonical Store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from x2n_contracts import ErrorCode

from .runtime import X2NRuntimeError


PLATFORMS_SQL = "'xiaohongshu','douyin','bilibili','kuaishou','weibo','taobao'"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: tuple[str, ...]
    down: tuple[str, ...]

    @property
    def checksum(self) -> str:
        payload = {
            "down": list(self.down),
            "name": self.name,
            "up": list(self.up),
            "version": self.version,
        }
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


CORE_UP = (
    f"""
    CREATE TABLE account_ref (
        account_ref_hash TEXT PRIMARY KEY
            CHECK(length(account_ref_hash) = 64 AND account_ref_hash NOT GLOB '*[^0-9a-f]*'),
        platform TEXT NOT NULL CHECK(platform IN ({PLATFORMS_SQL})),
        created_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE run_record (
        run_id TEXT PRIMARY KEY,
        run_kind TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending','running','succeeded','failed','cancelled','recovery')),
        input_manifest_hash TEXT
            CHECK(input_manifest_hash IS NULL OR (length(input_manifest_hash) = 64 AND input_manifest_hash NOT GLOB '*[^0-9a-f]*')),
        started_at TEXT NOT NULL,
        finished_at TEXT,
        created_at TEXT NOT NULL,
        CHECK((state IN ('pending','running','recovery') AND finished_at IS NULL) OR
              (state IN ('succeeded','failed','cancelled') AND finished_at IS NOT NULL))
    ) STRICT
    """,
    f"""
    CREATE TABLE content (
        content_key TEXT PRIMARY KEY,
        platform TEXT NOT NULL CHECK(platform IN ({PLATFORMS_SQL})),
        platform_content_id TEXT NOT NULL,
        canonical_source_url TEXT NOT NULL
            CHECK(canonical_source_url LIKE 'https://%/%' AND
                  instr(canonical_source_url, '?') = 0 AND
                  instr(canonical_source_url, '#') = 0),
        content_type TEXT NOT NULL CHECK(content_type IN ('text','image_gallery','video','mixed','unknown')),
        title TEXT,
        description TEXT,
        author_name TEXT,
        author_platform_id TEXT,
        published_at TEXT,
        content_hash TEXT NOT NULL
            CHECK(length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
        first_observed_at TEXT NOT NULL,
        last_observed_at TEXT NOT NULL,
        record_version INTEGER NOT NULL CHECK(record_version >= 1),
        status TEXT NOT NULL CHECK(status IN ('active','unavailable','unknown','deleted_by_user')),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(platform, platform_content_id),
        CHECK(content_key = platform || ':' || platform_content_id),
        CHECK(first_observed_at <= last_observed_at)
    ) STRICT
    """,
    """
    CREATE TABLE user_relation (
        relation_key TEXT PRIMARY KEY,
        account_ref_hash TEXT NOT NULL REFERENCES account_ref(account_ref_hash),
        content_key TEXT NOT NULL REFERENCES content(content_key),
        relation_type TEXT NOT NULL CHECK(relation_type IN ('liked','favorited','saved_current')),
        source_collection_id TEXT,
        source_collection_name_private TEXT,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('active','unknown','tombstone_candidate','removed')),
        confirmed_by TEXT NOT NULL CHECK(confirmed_by IN ('scan','owner')),
        scan_receipt_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(first_seen_at <= last_seen_at),
        CHECK(source_collection_name_private IS NULL OR source_collection_id IS NOT NULL)
    ) STRICT
    """,
    """
    CREATE TABLE source_observation (
        observation_id TEXT PRIMARY KEY,
        content_key TEXT NOT NULL REFERENCES content(content_key),
        adapter_name TEXT NOT NULL,
        adapter_version TEXT NOT NULL,
        source_method TEXT NOT NULL CHECK(source_method IN ('current_page','selected_collection','adapter_supplement')),
        observed_at TEXT NOT NULL,
        raw_text_hash TEXT NOT NULL
            CHECK(length(raw_text_hash) = 64 AND raw_text_hash NOT GLOB '*[^0-9a-f]*'),
        completeness REAL NOT NULL CHECK(completeness >= 0.0 AND completeness <= 1.0),
        run_id TEXT NOT NULL REFERENCES run_record(run_id),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE artifact (
        artifact_id TEXT PRIMARY KEY,
        artifact_key TEXT NOT NULL UNIQUE,
        content_key TEXT NOT NULL REFERENCES content(content_key),
        artifact_type TEXT NOT NULL CHECK(artifact_type IN ('transcript','ocr','vision','fusion_summary','search_text')),
        input_hash TEXT NOT NULL
            CHECK(length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'),
        processor TEXT NOT NULL,
        processor_version TEXT NOT NULL,
        model_provider TEXT,
        model_name TEXT,
        model_snapshot TEXT,
        prompt_version TEXT,
        language TEXT,
        private_payload_present INTEGER NOT NULL CHECK(private_payload_present IN (0,1)),
        private_payload_ref TEXT,
        private_payload_hash TEXT
            CHECK(private_payload_hash IS NULL OR (length(private_payload_hash) = 64 AND private_payload_hash NOT GLOB '*[^0-9a-f]*')),
        artifact_sequence INTEGER NOT NULL CHECK(artifact_sequence >= 1),
        created_at TEXT NOT NULL,
        supersedes_artifact_id TEXT REFERENCES artifact(artifact_id),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        UNIQUE(content_key, artifact_type, artifact_sequence),
        CHECK((private_payload_present = 1 AND private_payload_ref IS NOT NULL AND private_payload_hash IS NOT NULL) OR
              (private_payload_present = 0 AND private_payload_ref IS NULL AND private_payload_hash IS NULL)),
        CHECK(supersedes_artifact_id IS NULL OR supersedes_artifact_id <> artifact_id)
    ) STRICT
    """,
    """
    CREATE TABLE taxonomy_category (
        category_id TEXT PRIMARY KEY,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        slug TEXT NOT NULL UNIQUE,
        priority INTEGER NOT NULL,
        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
        version INTEGER NOT NULL CHECK(version >= 1),
        level INTEGER NOT NULL CHECK(level = 1),
        created_by TEXT NOT NULL CHECK(created_by = 'owner'),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE classification (
        classification_id TEXT PRIMARY KEY,
        content_key TEXT NOT NULL REFERENCES content(content_key),
        taxonomy_version INTEGER NOT NULL CHECK(taxonomy_version >= 1),
        primary_category_id TEXT NOT NULL REFERENCES taxonomy_category(category_id),
        decision_mode TEXT NOT NULL CHECK(decision_mode IN ('rule','model','hybrid','human')),
        confidence_raw REAL CHECK(confidence_raw IS NULL OR (confidence_raw >= 0.0 AND confidence_raw <= 1.0)),
        calibration_bucket TEXT,
        review_status TEXT NOT NULL CHECK(review_status IN ('auto_accepted','suggested','owner_confirmed','owner_corrected')),
        created_at TEXT NOT NULL,
        supersedes_classification_id TEXT REFERENCES classification(classification_id),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK(supersedes_classification_id IS NULL OR supersedes_classification_id <> classification_id)
    ) STRICT
    """,
    """
    CREATE TABLE classification_artifact (
        classification_id TEXT NOT NULL REFERENCES classification(classification_id),
        artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
        PRIMARY KEY(classification_id, artifact_id)
    ) WITHOUT ROWID, STRICT
    """,
    """
    CREATE TABLE checkpoint (
        checkpoint_id TEXT PRIMARY KEY,
        adapter_name TEXT NOT NULL,
        adapter_version TEXT NOT NULL,
        account_ref_hash TEXT NOT NULL REFERENCES account_ref(account_ref_hash),
        relation_type TEXT NOT NULL CHECK(relation_type IN ('liked','favorited','saved_current')),
        cursor_kind TEXT NOT NULL,
        cursor_value_private TEXT,
        last_stable_content_id TEXT,
        full_scan_id TEXT,
        observed_count INTEGER NOT NULL CHECK(observed_count >= 0),
        completion_confidence REAL NOT NULL CHECK(completion_confidence >= 0.0 AND completion_confidence <= 1.0),
        resume_compatibility_version TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('active','complete','invalidated')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE request_ledger (
        request_id TEXT PRIMARY KEY,
        payload_hash TEXT NOT NULL
            CHECK(length(payload_hash) = 64 AND payload_hash NOT GLOB '*[^0-9a-f]*'),
        job_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    ) STRICT
    """,
    "CREATE INDEX idx_relation_content ON user_relation(content_key, status)",
    "CREATE INDEX idx_observation_content ON source_observation(content_key, observed_at)",
    "CREATE INDEX idx_artifact_content ON artifact(content_key, artifact_type, artifact_sequence)",
    "CREATE INDEX idx_classification_content ON classification(content_key, created_at)",
    "CREATE INDEX idx_checkpoint_resume ON checkpoint(adapter_name, account_ref_hash, relation_type, state)",
    "CREATE TRIGGER content_no_delete BEFORE DELETE ON content BEGIN SELECT RAISE(ABORT, 'X2N_CONTENT_PHYSICAL_DELETE_BLOCKED'); END",
    "CREATE TRIGGER relation_no_delete BEFORE DELETE ON user_relation BEGIN SELECT RAISE(ABORT, 'X2N_RELATION_PHYSICAL_DELETE_BLOCKED'); END",
    "CREATE TRIGGER observation_no_update BEFORE UPDATE ON source_observation BEGIN SELECT RAISE(ABORT, 'X2N_OBSERVATION_APPEND_ONLY'); END",
    "CREATE TRIGGER observation_no_delete BEFORE DELETE ON source_observation BEGIN SELECT RAISE(ABORT, 'X2N_OBSERVATION_APPEND_ONLY'); END",
    "CREATE TRIGGER artifact_no_update BEFORE UPDATE ON artifact BEGIN SELECT RAISE(ABORT, 'X2N_ARTIFACT_APPEND_ONLY'); END",
    "CREATE TRIGGER artifact_no_delete BEFORE DELETE ON artifact BEGIN SELECT RAISE(ABORT, 'X2N_ARTIFACT_APPEND_ONLY'); END",
    "CREATE TRIGGER classification_no_update BEFORE UPDATE ON classification BEGIN SELECT RAISE(ABORT, 'X2N_CLASSIFICATION_APPEND_ONLY'); END",
    "CREATE TRIGGER classification_no_delete BEFORE DELETE ON classification BEGIN SELECT RAISE(ABORT, 'X2N_CLASSIFICATION_APPEND_ONLY'); END",
    "CREATE TRIGGER request_ledger_no_update BEFORE UPDATE ON request_ledger BEGIN SELECT RAISE(ABORT, 'X2N_REQUEST_LEDGER_APPEND_ONLY'); END",
    "CREATE TRIGGER request_ledger_no_delete BEFORE DELETE ON request_ledger BEGIN SELECT RAISE(ABORT, 'X2N_REQUEST_LEDGER_APPEND_ONLY'); END",
)

CORE_DOWN = (
    "DROP TRIGGER IF EXISTS request_ledger_no_delete",
    "DROP TRIGGER IF EXISTS request_ledger_no_update",
    "DROP TRIGGER IF EXISTS classification_no_delete",
    "DROP TRIGGER IF EXISTS classification_no_update",
    "DROP TRIGGER IF EXISTS artifact_no_delete",
    "DROP TRIGGER IF EXISTS artifact_no_update",
    "DROP TRIGGER IF EXISTS observation_no_delete",
    "DROP TRIGGER IF EXISTS observation_no_update",
    "DROP TRIGGER IF EXISTS relation_no_delete",
    "DROP TRIGGER IF EXISTS content_no_delete",
    "DROP TABLE request_ledger",
    "DROP TABLE checkpoint",
    "DROP TABLE classification_artifact",
    "DROP TABLE classification",
    "DROP TABLE taxonomy_category",
    "DROP TABLE artifact",
    "DROP TABLE source_observation",
    "DROP TABLE user_relation",
    "DROP TABLE content",
    "DROP TABLE run_record",
    "DROP TABLE account_ref",
)


RELIABILITY_UP = (
    """
    CREATE TABLE outbox_event (
        event_id TEXT PRIMARY KEY,
        event_key TEXT NOT NULL UNIQUE,
        sink TEXT NOT NULL CHECK(sink IN ('markdown','notion')),
        content_key TEXT NOT NULL REFERENCES content(content_key),
        desired_projection_hash TEXT NOT NULL
            CHECK(length(desired_projection_hash) = 64 AND desired_projection_hash NOT GLOB '*[^0-9a-f]*'),
        sink_schema_version TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','leased','delivered','dead_letter','cancelled')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
        not_before TEXT NOT NULL,
        lease_id TEXT,
        lease_owner TEXT,
        lease_expires_at TEXT,
        last_error_code TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(sink, content_key, desired_projection_hash, sink_schema_version),
        CHECK((status = 'leased' AND lease_id IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR
              (status <> 'leased' AND lease_id IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL))
    ) STRICT
    """,
    """
    CREATE TABLE sink_receipt (
        receipt_id TEXT PRIMARY KEY,
        sink_key TEXT NOT NULL,
        sink TEXT NOT NULL CHECK(sink IN ('markdown','notion')),
        content_key TEXT NOT NULL REFERENCES content(content_key),
        sink_schema_version TEXT NOT NULL,
        desired_projection_hash TEXT NOT NULL
            CHECK(length(desired_projection_hash) = 64 AND desired_projection_hash NOT GLOB '*[^0-9a-f]*'),
        output_hash TEXT NOT NULL
            CHECK(length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*'),
        sink_object_ref TEXT NOT NULL,
        external_ref_hash TEXT
            CHECK(external_ref_hash IS NULL OR (length(external_ref_hash) = 64 AND external_ref_hash NOT GLOB '*[^0-9a-f]*')),
        status TEXT NOT NULL CHECK(status IN ('delivered','verified','failed')),
        delivered_at TEXT NOT NULL,
        run_id TEXT NOT NULL REFERENCES run_record(run_id),
        payload_json TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL
            CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
        UNIQUE(sink, content_key, desired_projection_hash, sink_schema_version),
        CHECK((sink = 'notion' AND external_ref_hash IS NOT NULL) OR
              (sink = 'markdown' AND external_ref_hash IS NULL))
    ) STRICT
    """,
    """
    CREATE TABLE notion_mapping (
        content_key TEXT PRIMARY KEY REFERENCES content(content_key),
        notion_page_ref_private TEXT NOT NULL UNIQUE,
        external_ref_hash TEXT NOT NULL
            CHECK(length(external_ref_hash) = 64 AND external_ref_hash NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE media_lease (
        lease_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES run_record(run_id),
        content_key TEXT NOT NULL REFERENCES content(content_key),
        purpose TEXT NOT NULL,
        content_hash TEXT NOT NULL
            CHECK(length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
        mime TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        duration_seconds REAL CHECK(duration_seconds IS NULL OR duration_seconds >= 0.0),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('active','processing','cleanup_pending','deleted','expired','blocked_policy')),
        local_relative_path TEXT NOT NULL
            CHECK(substr(local_relative_path, 1, 1) <> '/' AND
                  instr(local_relative_path, '..') = 0 AND
                  instr(local_relative_path, '://') = 0),
        cleanup_error_code TEXT,
        CHECK(created_at <= expires_at)
    ) STRICT
    """,
    """
    CREATE TABLE recovery_event (
        event_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        quick_check TEXT NOT NULL CHECK(quick_check = 'ok'),
        integrity_check TEXT NOT NULL CHECK(integrity_check = 'ok'),
        expired_outbox_leases INTEGER NOT NULL CHECK(expired_outbox_leases >= 0),
        expired_media_leases INTEGER NOT NULL CHECK(expired_media_leases >= 0),
        running_jobs INTEGER NOT NULL CHECK(running_jobs >= 0),
        result_hash TEXT NOT NULL
            CHECK(length(result_hash) = 64 AND result_hash NOT GLOB '*[^0-9a-f]*')
    ) STRICT
    """,
    "CREATE INDEX idx_outbox_claim ON outbox_event(status, not_before, created_at)",
    "CREATE INDEX idx_outbox_lease ON outbox_event(status, lease_expires_at)",
    "CREATE INDEX idx_receipt_content ON sink_receipt(content_key, sink, delivered_at)",
    "CREATE INDEX idx_media_lease_expiry ON media_lease(status, expires_at)",
    "CREATE TRIGGER outbox_no_delete BEFORE DELETE ON outbox_event BEGIN SELECT RAISE(ABORT, 'X2N_OUTBOX_DELETE_BLOCKED'); END",
    "CREATE TRIGGER receipt_no_update BEFORE UPDATE ON sink_receipt BEGIN SELECT RAISE(ABORT, 'X2N_RECEIPT_APPEND_ONLY'); END",
    "CREATE TRIGGER receipt_no_delete BEFORE DELETE ON sink_receipt BEGIN SELECT RAISE(ABORT, 'X2N_RECEIPT_APPEND_ONLY'); END",
    "CREATE TRIGGER recovery_event_no_update BEFORE UPDATE ON recovery_event BEGIN SELECT RAISE(ABORT, 'X2N_RECOVERY_EVENT_APPEND_ONLY'); END",
    "CREATE TRIGGER recovery_event_no_delete BEFORE DELETE ON recovery_event BEGIN SELECT RAISE(ABORT, 'X2N_RECOVERY_EVENT_APPEND_ONLY'); END",
)

RELIABILITY_DOWN = (
    "DROP TRIGGER IF EXISTS recovery_event_no_delete",
    "DROP TRIGGER IF EXISTS recovery_event_no_update",
    "DROP TRIGGER IF EXISTS receipt_no_delete",
    "DROP TRIGGER IF EXISTS receipt_no_update",
    "DROP TRIGGER IF EXISTS outbox_no_delete",
    "DROP TABLE recovery_event",
    "DROP TABLE media_lease",
    "DROP TABLE notion_mapping",
    "DROP TABLE sink_receipt",
    "DROP TABLE outbox_event",
)


MIGRATIONS = (
    Migration(1, "canonical_core", CORE_UP, CORE_DOWN),
    Migration(2, "reliability_outbox_and_leases", RELIABILITY_UP, RELIABILITY_DOWN),
)
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
MIGRATION_SET_SHA256 = hashlib.sha256(
    "\n".join(item.checksum for item in MIGRATIONS).encode("ascii")
).hexdigest()


def ensure_migration_table(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migration'"
    ).fetchone()
    if existing is not None:
        return
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migration (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        ) STRICT
        """
    )


def current_version(connection: sqlite3.Connection) -> int:
    ensure_migration_table(connection)
    pragma = int(connection.execute("PRAGMA user_version").fetchone()[0])
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migration ORDER BY version"
    ).fetchall()
    expected = [(item.version, item.name, item.checksum) for item in MIGRATIONS if item.version <= pragma]
    actual = [(int(row[0]), str(row[1]), str(row[2])) for row in rows]
    if actual != expected:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Migration ledger does not match the Store schema")
    if pragma < 0 or pragma > LATEST_SCHEMA_VERSION:
        raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Store schema version is unsupported")
    return pragma


def migrate_forward(connection: sqlite3.Connection, target: int, *, applied_at: str) -> int:
    current = current_version(connection)
    if target < current or target > LATEST_SCHEMA_VERSION:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Forward migration target is invalid")
    for migration in MIGRATIONS:
        if not current < migration.version <= target:
            continue
        try:
            connection.execute("BEGIN EXCLUSIVE")
            for statement in migration.up:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migration(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum, applied_at),
            )
            connection.execute(f"PRAGMA user_version = {migration.version}")
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Forward migration failed atomically") from error
        current = migration.version
    return current_version(connection)


def migrate_backward(
    connection: sqlite3.Connection,
    target: int,
    *,
    verified_backup: bool,
) -> int:
    current = current_version(connection)
    if not verified_backup:
        raise X2NRuntimeError(ErrorCode.POLICY_BLOCKED, "Schema downgrade requires a verified backup")
    if target < 0 or target >= current:
        raise X2NRuntimeError(ErrorCode.INVALID_INPUT, "Backward migration target is invalid")
    for migration in reversed(MIGRATIONS):
        if not target < migration.version <= current:
            continue
        try:
            connection.execute("BEGIN EXCLUSIVE")
            for statement in migration.down:
                connection.execute(statement)
            connection.execute("DELETE FROM schema_migration WHERE version = ?", (migration.version,))
            connection.execute(f"PRAGMA user_version = {migration.version - 1}")
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise X2NRuntimeError(ErrorCode.DATA_INTEGRITY_FAILED, "Backward migration failed atomically") from error
        current = migration.version - 1
    return current_version(connection)


def schema_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    version = current_version(connection)
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    objects = [
        {
            "name": str(row[1]),
            "sql": " ".join(str(row[3]).split()),
            "table": str(row[2]),
            "type": str(row[0]),
        }
        for row in rows
    ]
    rendered = json.dumps(objects, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "latest_schema_version": LATEST_SCHEMA_VERSION,
        "migration_set_sha256": MIGRATION_SET_SHA256,
        "objects": objects,
        "schema_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "schema_version": version,
    }
