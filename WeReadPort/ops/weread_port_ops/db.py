from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .sanitize import assert_public_safe, sanitize_public


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RuntimeDB:
    def __init__(self, path: Path, schema_path: Path | None = None):
        self.path = Path(path)
        self.schema_path = schema_path or Path(__file__).resolve().parent.parent / "schema.sql"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        script = self.schema_path.read_text(encoding="utf-8")
        with self.connect() as connection:
            self._prepare_legacy_tables(connection)
            connection.executescript(script)
            self._import_legacy_rows(connection)

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}

    def _prepare_legacy_tables(self, connection: sqlite3.Connection) -> None:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # v0.0.0.5 used a different outbox shape. Preserve and translate it instead
        # of silently deleting short-lived operational state.
        if "outbox" in tables and "topic" not in self._table_columns(connection, "outbox"):
            connection.execute("ALTER TABLE outbox RENAME TO outbox_v5_legacy")

    def _import_legacy_rows(self, connection: sqlite3.Connection) -> None:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "outbox_v5_legacy" in tables:
            connection.execute(
                """INSERT OR IGNORE INTO outbox(
                    outbox_id,topic,payload_json,created_at,delivered_at,attempt_count,last_error
                )
                SELECT outbox_id,COALESCE(NULLIF(aggregate_type,''),'legacy'),payload_json,created_at,delivered_at,
                       MIN(COALESCE(attempts,0),32),NULLIF(last_error_code,'')
                FROM outbox_v5_legacy"""
            )
            connection.execute("DROP TABLE outbox_v5_legacy")
        if "runtime_event" in tables:
            connection.execute(
                """INSERT OR IGNORE INTO runtime_events(
                    event_id,event_type,event_status,occurred_at,payload_json,created_at
                )
                SELECT event_id,kind,status,occurred_at,details_json,occurred_at FROM runtime_event"""
            )
            connection.execute("DROP TABLE runtime_event")
        if "release_record" in tables:
            rows = connection.execute(
                "SELECT * FROM release_record ORDER BY deployed_at DESC LIMIT 2"
            ).fetchall()
            if rows:
                current = rows[0]
                previous = rows[1] if len(rows) > 1 else None
                connection.execute(
                    """INSERT OR REPLACE INTO release_state(
                        singleton,current_commit,current_saved_version,current_production_version,production_origin,
                        previous_commit,previous_saved_version,previous_production_version,updated_at
                    ) VALUES(1,?,?,?,?,?,?,?,?)""",
                    (
                        current["git_commit"], current["saved_version"], current["production_version"],
                        current["production_url"],
                        previous["git_commit"] if previous else None,
                        previous["saved_version"] if previous else None,
                        previous["production_version"] if previous else None,
                        current["deployed_at"],
                    ),
                )
            connection.execute("DROP TABLE release_record")
        if "backup_record" in tables:
            connection.execute(
                """INSERT OR IGNORE INTO backup_state(
                    backup_id,created_at,snapshot_path,snapshot_sha256,sqlite_integrity,r2_status,oci_status,details_json
                )
                SELECT backup_id,created_at,location,sha256,'legacy-unverified',status,'legacy-unverified',
                       json_object('legacyBackupKind',backup_kind,'sizeBytes',size_bytes)
                FROM backup_record"""
            )
            connection.execute("DROP TABLE backup_record")

    def integrity_check(self) -> str:
        with self.connect() as connection:
            value = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return str(value)

    def record_event(
        self,
        event_type: str,
        event_status: str,
        payload: dict[str, Any],
        *,
        occurred_at: datetime | None = None,
        event_id: str | None = None,
    ) -> str:
        clean = sanitize_public(payload)
        assert_public_safe(clean)
        timestamp = iso(occurred_at or utc_now())
        encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        identifier = event_id or hashlib.sha256(f"{event_type}\0{timestamp}\0{encoded}".encode()).hexdigest()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO runtime_events(event_id,event_type,event_status,occurred_at,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                (identifier, event_type, event_status, timestamp, encoded, iso(utc_now())),
            )
        return identifier

    def record_health(self, payload: dict[str, Any]) -> None:
        clean = sanitize_public(payload)
        assert_public_safe(clean)
        product = clean.get("productPlane", {}) if isinstance(clean, dict) else {}
        encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO health_samples(
                    checked_at,service_status,health_http_status,version_http_status,latency_ms,
                    app_version,source_skill_version,error_code,payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    str(clean.get("checkedAt", "")),
                    str(clean.get("status", "unknown")),
                    product.get("healthHttpStatus"),
                    product.get("versionHttpStatus"),
                    product.get("latencyMs"),
                    product.get("appVersion"),
                    product.get("sourceSkillVersion"),
                    product.get("errorCode"),
                    encoded,
                ),
            )

    def enqueue(self, topic: str, payload: dict[str, Any], *, outbox_id: str, at: datetime | None = None) -> bool:
        clean = sanitize_public(payload)
        assert_public_safe(clean)
        encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO outbox(outbox_id,topic,payload_json,created_at) VALUES(?,?,?,?)",
                (outbox_id, topic, encoded, iso(at or utc_now())),
            )
        return cursor.rowcount == 1

    def pending(self, limit: int = 500) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM outbox WHERE delivered_at IS NULL ORDER BY created_at,outbox_id LIMIT ?",
                    (max(1, min(limit, 5000)),),
                ).fetchall()
            )

    def mark_delivered(self, identifiers: list[str], *, delivered_at: datetime | None = None) -> None:
        if not identifiers:
            return
        timestamp = iso(delivered_at or utc_now())
        with self.connect() as connection:
            connection.executemany(
                "UPDATE outbox SET delivered_at=?, attempt_count=MIN(attempt_count+1,32), last_error=NULL WHERE outbox_id=?",
                [(timestamp, item) for item in identifiers],
            )

    def mark_failed(self, identifiers: list[str], error_code: str) -> None:
        if not identifiers:
            return
        safe = sanitize_public(error_code)
        with self.connect() as connection:
            connection.executemany(
                "UPDATE outbox SET attempt_count=MIN(attempt_count+1,32),last_error=? WHERE outbox_id=?",
                [(safe, item) for item in identifiers],
            )

    def get_cursor(self, name: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute("SELECT cursor_value FROM cursors WHERE cursor_name=?", (name,)).fetchone()
        return None if row is None else str(row[0])

    def set_cursor(self, name: str, value: str, *, at: datetime | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO cursors(cursor_name,cursor_value,updated_at) VALUES(?,?,?)
                ON CONFLICT(cursor_name) DO UPDATE SET cursor_value=excluded.cursor_value,updated_at=excluded.updated_at""",
                (name, value, iso(at or utc_now())),
            )

    def purge_before(self, cutoff: datetime) -> dict[str, int]:
        threshold = iso(cutoff)
        with self.connect() as connection:
            health = connection.execute("DELETE FROM health_samples WHERE checked_at < ?", (threshold,)).rowcount
            events = connection.execute("DELETE FROM runtime_events WHERE occurred_at < ?", (threshold,)).rowcount
            outbox = connection.execute("DELETE FROM outbox WHERE delivered_at IS NOT NULL AND delivered_at < ?", (threshold,)).rowcount
        return {"healthSamples": health, "runtimeEvents": events, "deliveredOutbox": outbox}

    def summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            counts = {
                "healthSamples": connection.execute("SELECT COUNT(*) FROM health_samples").fetchone()[0],
                "runtimeEvents": connection.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0],
                "pendingOutbox": connection.execute("SELECT COUNT(*) FROM outbox WHERE delivered_at IS NULL").fetchone()[0],
            }
            latest = connection.execute(
                "SELECT checked_at,service_status,error_code,latency_ms,app_version,source_skill_version FROM health_samples ORDER BY sample_id DESC LIMIT 1"
            ).fetchone()
        return {
            **counts,
            "latestHealth": dict(latest) if latest is not None else None,
            "integrity": self.integrity_check(),
        }

    def set_release(
        self,
        *,
        commit: str,
        saved_version: str,
        production_version: str,
        production_origin: str,
        at: datetime | None = None,
    ) -> None:
        with self.connect() as connection:
            current = connection.execute("SELECT * FROM release_state WHERE singleton=1").fetchone()
            previous_commit = current["current_commit"] if current else None
            previous_saved = current["current_saved_version"] if current else None
            previous_production = current["current_production_version"] if current else None
            connection.execute(
                """INSERT INTO release_state(
                  singleton,current_commit,current_saved_version,current_production_version,production_origin,
                  previous_commit,previous_saved_version,previous_production_version,updated_at
                ) VALUES(1,?,?,?,?,?,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                  previous_commit=release_state.current_commit,
                  previous_saved_version=release_state.current_saved_version,
                  previous_production_version=release_state.current_production_version,
                  current_commit=excluded.current_commit,
                  current_saved_version=excluded.current_saved_version,
                  current_production_version=excluded.current_production_version,
                  production_origin=excluded.production_origin,
                  updated_at=excluded.updated_at""",
                (
                    commit,
                    saved_version,
                    production_version,
                    production_origin,
                    previous_commit,
                    previous_saved,
                    previous_production,
                    iso(at or utc_now()),
                ),
            )

    def release(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM release_state WHERE singleton=1").fetchone()
        return dict(row) if row is not None else None

    def consistent_backup(self, destination: Path) -> str:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        source = sqlite3.connect(self.path, timeout=5.0)
        target = sqlite3.connect(destination)
        try:
            source.execute("PRAGMA wal_checkpoint(PASSIVE)")
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"Snapshot integrity failed: {result}")
        finally:
            target.close()
            source.close()
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return digest
