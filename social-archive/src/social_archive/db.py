from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

from .models import CaptureRequest
from .utils import canonicalize_url, json_bytes, sha256_bytes, stable_id, utcnow


_CJK_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CJK_HAN_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _literal_fts_query(value: str) -> str | None:
    """Turn non-CJK user text into literal FTS terms instead of accepting operators."""
    tokens = re.findall(r"\w+", _CJK_HAN_RUN_RE.sub(" ", value), flags=re.UNICODE)
    if not tokens:
        return None
    return " AND ".join(f'"{token}"' for token in tokens)


def _cjk_substrings(value: str) -> list[str]:
    """Return literal Han runs for a substring fallback.

    SQLite's unicode61 tokenizer indexes a contiguous Han phrase as one token.
    A person searching a prefix inside that phrase must still be able to find it.
    """
    return list(dict.fromkeys(_CJK_HAN_RUN_RE.findall(value)))


def _like_pattern(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class RuntimeStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            yield con
        finally:
            con.close()

    def initialize(self) -> None:
        schema = files("social_archive").joinpath("sql/runtime_schema.sql").read_text(encoding="utf-8")
        account_additions = {
            "connection_state": "TEXT NOT NULL DEFAULT 'disconnected'",
            "auth_method": "TEXT",
            "auth_handle_ref": "TEXT",
            "auto_sync_enabled": "INTEGER NOT NULL DEFAULT 1",
            "sync_interval_minutes": "INTEGER NOT NULL DEFAULT 360",
            "last_verified_at": "TEXT",
            "last_sync_at": "TEXT",
            "last_error_code": "TEXT",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        content_additions = {
            "summary": "TEXT",
            "language": "TEXT",
            "media_count": "INTEGER NOT NULL DEFAULT 0",
            "last_synced_at": "TEXT",
        }
        relation_additions = {
            "relation_observed_at": "TEXT",
            "external_relation_id": "TEXT",
            "source_order": "INTEGER",
            "last_sync_run_id": "TEXT",
        }
        with self.connection() as con:
            # The schema adds an index over connection_state.  Upgrade an
            # existing pre-v0.0.0.6 source_account before executescript reaches
            # that index; a fresh database has no table yet and is created with
            # the full definition below.
            account_columns = {row[1] for row in con.execute("PRAGMA table_info(source_account)").fetchall()}
            for name, declaration in account_additions.items():
                if account_columns and name not in account_columns:
                    con.execute(f"ALTER TABLE source_account ADD COLUMN {name} {declaration}")
            # These columns are indexed by the current schema, so legacy rows
            # must gain them before executescript creates the indexes.
            content_columns = {row[1] for row in con.execute("PRAGMA table_info(content)").fetchall()}
            for name, declaration in content_additions.items():
                if content_columns and name not in content_columns:
                    con.execute(f"ALTER TABLE content ADD COLUMN {name} {declaration}")
            relation_columns = {row[1] for row in con.execute("PRAGMA table_info(user_relation)").fetchall()}
            for name, declaration in relation_additions.items():
                if relation_columns and name not in relation_columns:
                    con.execute(f"ALTER TABLE user_relation ADD COLUMN {name} {declaration}")
            con.executescript(schema)
            con.execute(
                "UPDATE user_relation SET relation_observed_at=COALESCE(relation_observed_at,first_observed_at)"
            )
            # Additive migration for pre-v0.0.0.4 runtime databases. SQLite remains
            # rebuildable, but preserving an existing queue avoids unnecessary loss.
            columns = {row[1] for row in con.execute("PRAGMA table_info(object_replica)").fetchall()}
            if "original_sha256" not in columns:
                con.execute("ALTER TABLE object_replica ADD COLUMN original_sha256 TEXT")
            if "encryption" not in columns:
                con.execute("ALTER TABLE object_replica ADD COLUMN encryption TEXT")
            destination_columns = {row[1] for row in con.execute("PRAGMA table_info(destination_state)").fetchall()}
            destination_additions = {
                "last_checked_at": "TEXT",
                "latency_ms": "INTEGER",
                "capabilities_json": "TEXT NOT NULL DEFAULT '{}'",
                "last_message_zh": "TEXT",
            }
            for name, declaration in destination_additions.items():
                if name not in destination_columns:
                    con.execute(f"ALTER TABLE destination_state ADD COLUMN {name} {declaration}")
            connector_columns = {row[1] for row in con.execute("PRAGMA table_info(connector_state)").fetchall()}
            connector_additions = {
                "last_checked_at": "TEXT",
                "latency_ms": "INTEGER",
                "last_message_zh": "TEXT",
            }
            for name, declaration in connector_additions.items():
                if name not in connector_columns:
                    con.execute(f"ALTER TABLE connector_state ADD COLUMN {name} {declaration}")

    def capture(self, request: CaptureRequest) -> tuple[str, str, str]:
        now = utcnow()
        relation_time = request.relation_observed_at or now
        canonical_url = canonicalize_url(str(request.url))
        platform = request.platform.lower()
        content_id = stable_id("cnt", platform, request.external_content_id or canonical_url)
        account_id = stable_id("acct", platform, request.source_account_id) if request.source_account_id else None
        relation_id = stable_id("rel", account_id or "owner", content_id, request.relation_type, request.collection_key)
        payload = request.model_dump(mode="json")
        payload_bytes = json_bytes(payload)
        observation_id = stable_id("obs", platform, sha256_bytes(payload_bytes))
        metadata_json = json.dumps(request.raw_metadata, ensure_ascii=False, sort_keys=True)
        summary = (request.text or "").strip()[:1000] or None
        keywords = list(dict.fromkeys(item.strip() for item in request.keywords if item and item.strip()))[:32]
        topic = (request.topic or "未分类").strip()[:256] or "未分类"
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                """INSERT INTO content(id,platform,external_content_id,canonical_url,title,author_name,published_at,first_observed_at,last_observed_at,metadata_json,summary,language,media_count,last_synced_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=COALESCE(excluded.title,content.title),
                     author_name=COALESCE(excluded.author_name,content.author_name),
                     published_at=COALESCE(excluded.published_at,content.published_at),
                     last_observed_at=excluded.last_observed_at,
                     metadata_json=excluded.metadata_json,
                     summary=COALESCE(excluded.summary,content.summary),
                     language=COALESCE(excluded.language,content.language),
                     media_count=MAX(content.media_count,excluded.media_count),
                     last_synced_at=excluded.last_synced_at""",
                (content_id, platform, request.external_content_id, canonical_url, request.title, request.author_name, request.published_at, now, now, metadata_json, summary, request.language, len(request.media_urls), now),
            )
            if request.source_account_id:
                con.execute(
                    """INSERT INTO source_account(id,platform,external_account_id,created_at,updated_at)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,external_account_id=excluded.external_account_id,updated_at=excluded.updated_at""",
                    (account_id, platform, request.source_account_id, now, now),
                )
            con.execute(
                """INSERT INTO user_relation(id,source_account_id,content_id,relation_type,collection_key,status,first_observed_at,last_observed_at,relation_observed_at,missing_complete_scan_count,last_sync_run_id)
                   VALUES(?,?,?,?,?,'active',?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status='active',
                     last_observed_at=excluded.last_observed_at,
                     relation_observed_at=COALESCE(excluded.relation_observed_at,user_relation.relation_observed_at),
                     missing_complete_scan_count=0,
                     last_sync_run_id=COALESCE(excluded.last_sync_run_id,user_relation.last_sync_run_id),
                     closed_at=NULL""",
                (relation_id, account_id, content_id, request.relation_type, request.collection_key, now, now, relation_time, 0, str(request.raw_metadata.get("sync_run_id") or "") or None),
            )
            con.execute(
                "INSERT OR IGNORE INTO observation(id,connector_id,content_id,observed_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?)",
                (observation_id, f"capture:{platform}", content_id, now, payload_bytes.decode("utf-8"), sha256_bytes(payload_bytes)),
            )
            con.execute(
                """INSERT INTO content_classification(content_id,topic,keywords_json,confidence,source,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(content_id) DO UPDATE SET
                     topic=CASE WHEN excluded.topic!='未分类' THEN excluded.topic ELSE content_classification.topic END,
                     keywords_json=CASE WHEN excluded.keywords_json!='[]' THEN excluded.keywords_json ELSE content_classification.keywords_json END,
                     confidence=MAX(content_classification.confidence,excluded.confidence),
                     source=CASE WHEN excluded.topic!='未分类' OR excluded.keywords_json!='[]' THEN excluded.source ELSE content_classification.source END,
                     updated_at=excluded.updated_at""",
                (content_id, topic, json.dumps(keywords, ensure_ascii=False), 1.0 if request.topic or keywords else 0.0, str(request.raw_metadata.get("classification_source") or "connector"), now),
            )
            stored_content = con.execute(
                "SELECT title,author_name FROM content WHERE id=?",
                (content_id,),
            ).fetchone()
            previous_fts = con.execute(
                "SELECT body FROM content_fts WHERE content_id=?",
                (content_id,),
            ).fetchone()
            body = request.text if request.text is not None else (str(previous_fts["body"]) if previous_fts else "")
            collection_rows = con.execute(
                """SELECT DISTINCT collection_key FROM user_relation
                   WHERE content_id=? AND collection_key<>'' ORDER BY collection_key""",
                (content_id,),
            ).fetchall()
            fts_tags = " ".join([*(str(row["collection_key"]) for row in collection_rows), topic, *keywords])
            con.execute("DELETE FROM content_fts WHERE content_id=?", (content_id,))
            con.execute(
                "INSERT INTO content_fts(content_id,title,author_name,body,tags) VALUES(?,?,?,?,?)",
                (content_id, str(stored_content["title"] or ""), str(stored_content["author_name"] or ""), body, fts_tags),
            )
            con.execute("COMMIT")
        return content_id, relation_id, observation_id

    def add_artifact(self, *, content_id: str, archive_level: str, artifact_type: str, sha256: str, byte_size: int, media_type: str | None, local_path: str | None, status: str = "staged") -> str:
        artifact_id = stable_id("art", content_id, artifact_type, sha256)
        with self.connection() as con:
            con.execute(
                """INSERT INTO artifact(id,content_id,archive_level,artifact_type,sha256,byte_size,media_type,local_path,created_at,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,local_path=COALESCE(excluded.local_path,artifact.local_path)""",
                (artifact_id, content_id, archive_level, artifact_type, sha256, byte_size, media_type, local_path, utcnow(), status),
            )
        return artifact_id

    def enqueue_job(self, job_type: str, payload: dict[str, Any], connector_id: str | None = None) -> str:
        payload_raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        job_id = stable_id("job", job_type, connector_id, sha256_bytes(payload_raw.encode("utf-8")))
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT OR IGNORE INTO job(id,job_type,connector_id,payload_json,status,attempt_count,not_before,created_at,updated_at)
                   VALUES(?,?,?,?,'queued',0,?,?,?)""",
                (job_id, job_type, connector_id, payload_raw, now, now, now),
            )
        return job_id

    def claim_job(self, owner: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """SELECT * FROM job WHERE status IN ('queued','retry') AND not_before <= strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   AND (lease_expires_at IS NULL OR lease_expires_at < strftime('%Y-%m-%dT%H:%M:%fZ','now')) ORDER BY created_at LIMIT 1"""
            ).fetchone()
            if row is None:
                con.execute("COMMIT")
                return None
            con.execute(
                """UPDATE job SET status='running',lease_owner=?,lease_expires_at=strftime('%Y-%m-%dT%H:%M:%fZ','now',?),attempt_count=attempt_count+1,updated_at=? WHERE id=?""",
                (owner, f"+{lease_seconds} seconds", utcnow(), row["id"]),
            )
            con.execute("COMMIT")
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result

    def finish_job(
        self,
        job_id: str,
        *,
        success: bool,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        status = "done" if success else ("retry" if retryable else "failed")
        requested_delay = 60 if retry_after_seconds is None else retry_after_seconds
        delay_seconds = min(max(int(requested_delay), 1), 3600)
        with self.connection() as con:
            con.execute(
                """UPDATE job SET status=?,updated_at=?,lease_owner=NULL,lease_expires_at=NULL,last_error_code=?,last_error_message=?,
                   not_before=CASE WHEN ?='retry' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now',?) ELSE not_before END WHERE id=?""",
                (status, utcnow(), error_code, error_message, status, f"+{delay_seconds} seconds", job_id),
            )

    def retry_job(self, job_id: str) -> bool:
        """Move a terminal/retryable job back to the queue without changing its identity."""
        with self.connection() as con:
            row = con.execute("SELECT status FROM job WHERE id=?", (job_id,)).fetchone()
            if row is None or row["status"] in {"running", "done"}:
                return False
            con.execute(
                """UPDATE job SET status='queued',not_before=?,lease_owner=NULL,lease_expires_at=NULL,
                   last_error_code=NULL,last_error_message=NULL,updated_at=? WHERE id=?""",
                (utcnow(), utcnow(), job_id),
            )
            return True

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT id,job_type,connector_id,status,attempt_count,created_at,updated_at,last_error_code,last_error_message FROM job WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        args: list[Any] = []
        if status:
            clauses.append("status=?")
            args.append(status)
        args.append(min(max(limit, 1), 500))
        with self.connection() as con:
            rows = con.execute(
                f"""SELECT id,job_type,connector_id,status,attempt_count,created_at,updated_at,last_error_code,last_error_message
                    FROM job WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?""",
                args,
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_destination_state(
        self,
        destination_id: str,
        *,
        state: str,
        enabled: bool,
        error_code: str | None = None,
        last_checked_at: str | None = None,
        latency_ms: int | None = None,
        capabilities: dict[str, Any] | None = None,
        message_zh: str | None = None,
    ) -> None:
        now = utcnow()
        success_at = now if state == "connected" else None
        failure_at = now if state in {"degraded", "expired", "blocked_policy"} else None
        capabilities_json = json.dumps(capabilities or {}, ensure_ascii=False, sort_keys=True)
        with self.connection() as con:
            con.execute(
                """INSERT INTO destination_state(
                     destination_id,state,enabled,last_success_at,last_failure_at,last_error_code,
                     last_checked_at,latency_ms,capabilities_json,last_message_zh,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(destination_id) DO UPDATE SET
                     state=excluded.state,enabled=excluded.enabled,
                     last_success_at=COALESCE(excluded.last_success_at,destination_state.last_success_at),
                     last_failure_at=COALESCE(excluded.last_failure_at,destination_state.last_failure_at),
                     last_error_code=excluded.last_error_code,
                     last_checked_at=COALESCE(excluded.last_checked_at,destination_state.last_checked_at),
                     latency_ms=COALESCE(excluded.latency_ms,destination_state.latency_ms),
                     capabilities_json=COALESCE(excluded.capabilities_json,destination_state.capabilities_json),
                     last_message_zh=COALESCE(excluded.last_message_zh,destination_state.last_message_zh),
                     updated_at=excluded.updated_at""",
                (
                    destination_id,
                    state,
                    1 if enabled else 0,
                    success_at,
                    failure_at,
                    error_code,
                    last_checked_at,
                    latency_ms,
                    capabilities_json,
                    message_zh,
                    now,
                ),
            )

    def destination_states(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = [dict(row) for row in con.execute("SELECT * FROM destination_state ORDER BY destination_id").fetchall()]
        for row in rows:
            raw = row.pop("capabilities_json", "{}") or "{}"
            try:
                row["capabilities"] = json.loads(raw)
            except (TypeError, ValueError):
                row["capabilities"] = {}
        return rows

    def get_destination_binding(self, destination_id: str, content_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute(
                "SELECT * FROM destination_binding WHERE destination_id=? AND content_id=?",
                (destination_id, content_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        except (TypeError, ValueError):
            result["metadata"] = {}
        return result

    def upsert_destination_binding(
        self,
        *,
        destination_id: str,
        content_id: str,
        projection_sha256: str,
        remote_id: str | None = None,
        remote_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        binding_id = stable_id("dstbind", destination_id, content_id)
        with self.connection() as con:
            con.execute(
                """INSERT INTO destination_binding(
                     id,destination_id,content_id,remote_id,remote_path,projection_sha256,last_export_at,metadata_json
                   ) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(destination_id,content_id) DO UPDATE SET
                     remote_id=COALESCE(excluded.remote_id,destination_binding.remote_id),
                     remote_path=COALESCE(excluded.remote_path,destination_binding.remote_path),
                     projection_sha256=excluded.projection_sha256,last_export_at=excluded.last_export_at,
                     metadata_json=excluded.metadata_json""",
                (
                    binding_id,
                    destination_id,
                    content_id,
                    remote_id,
                    remote_path,
                    projection_sha256,
                    utcnow(),
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return binding_id

    def record_destination_receipt(
        self,
        *,
        destination_id: str,
        content_id: str,
        status: str,
        projection_sha256: str,
        attempted_at: str,
        message_zh: str,
        job_id: str | None = None,
        remote_id: str | None = None,
        remote_path: str | None = None,
        error_code: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        finished_at = utcnow()
        receipt_id = stable_id(
            "dstreceipt", destination_id, content_id, job_id or attempted_at, status, projection_sha256
        )
        with self.connection() as con:
            con.execute(
                """INSERT INTO destination_receipt(
                     id,job_id,destination_id,content_id,status,projection_sha256,remote_id,remote_path,
                     attempted_at,finished_at,error_code,message_zh,evidence_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     status=excluded.status,remote_id=excluded.remote_id,remote_path=excluded.remote_path,
                     finished_at=excluded.finished_at,error_code=excluded.error_code,
                     message_zh=excluded.message_zh,evidence_json=excluded.evidence_json""",
                (
                    receipt_id,
                    job_id,
                    destination_id,
                    content_id,
                    status,
                    projection_sha256,
                    remote_id,
                    remote_path,
                    attempted_at,
                    finished_at,
                    error_code,
                    message_zh,
                    json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return receipt_id

    def list_destination_receipts(
        self,
        *,
        limit: int = 100,
        destination_id: str | None = None,
        content_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        args: list[Any] = []
        if destination_id:
            clauses.append("destination_id=?")
            args.append(destination_id)
        if content_id:
            clauses.append("content_id=?")
            args.append(content_id)
        if status:
            clauses.append("status=?")
            args.append(status)
        args.append(min(max(limit, 1), 500))
        with self.connection() as con:
            rows = [dict(row) for row in con.execute(
                f"SELECT * FROM destination_receipt WHERE {' AND '.join(clauses)} ORDER BY finished_at DESC LIMIT ?",
                args,
            ).fetchall()]
        for row in rows:
            try:
                row["evidence"] = json.loads(row.pop("evidence_json") or "{}")
            except (TypeError, ValueError):
                row["evidence"] = {}
        return rows

    def get_destination_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM destination_receipt WHERE id=?", (receipt_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["evidence"] = json.loads(result.pop("evidence_json") or "{}")
        except (TypeError, ValueError):
            result["evidence"] = {}
        return result

    def list_library(
        self,
        *,
        q: str | None = None,
        platform: str | None = None,
        relation: str | None = None,
        collection: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        where_args: list[Any] = []
        if platform:
            clauses.append("c.platform=?")
            where_args.append(platform.lower())
        if q:
            literal_query = _literal_fts_query(q)
            cjk_terms = _cjk_substrings(q)
            if literal_query:
                clauses.append("c.id IN (SELECT content_id FROM content_fts WHERE content_fts MATCH ?)")
                where_args.append(literal_query)
            for term in cjk_terms:
                pattern = _like_pattern(term)
                clauses.append(
                    """c.id IN (SELECT content_id FROM content_fts
                       WHERE title LIKE ? ESCAPE '\\' OR author_name LIKE ? ESCAPE '\\'
                          OR body LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"""
                )
                where_args.extend([pattern, pattern, pattern, pattern])
            if not literal_query and not cjk_terms:
                clauses.append("0=1")
        relation_clauses: list[str] = []
        relation_args: list[Any] = []
        if relation:
            relation_clauses.append("r2.relation_type=?")
            relation_args.append(relation)
        if collection:
            relation_clauses.append("r2.collection_key=?")
            relation_args.append(collection)
        if observed_from:
            relation_clauses.append("r2.last_observed_at>=?")
            relation_args.append(observed_from)
        if observed_to:
            relation_clauses.append("r2.last_observed_at<=?")
            relation_args.append(observed_to)
        relation_clause = "".join(f" AND {clause}" for clause in relation_clauses)
        args = relation_args + where_args + [min(max(limit, 1), 500), max(offset, 0)]
        sql = f"""SELECT c.*,r.relation_type,r.collection_key,r.status AS relation_status,
                 (SELECT COUNT(*) FROM artifact a WHERE a.content_id=c.id) artifact_count,
                 (SELECT COUNT(*) FROM object_replica o JOIN artifact a2 ON a2.id=o.artifact_id WHERE a2.content_id=c.id AND o.status='verified') verified_replica_count
                 FROM content c JOIN user_relation r ON r.id=(
                   SELECT r2.id FROM user_relation r2
                   WHERE r2.content_id=c.id{relation_clause}
                   ORDER BY CASE WHEN r2.status='active' THEN 0 ELSE 1 END, r2.last_observed_at DESC, r2.id ASC
                   LIMIT 1
                 )
                 WHERE {' AND '.join(clauses)} ORDER BY c.last_observed_at DESC LIMIT ? OFFSET ?"""
        with self.connection() as con:
            return [dict(row) for row in con.execute(sql, args).fetchall()]

    _TABLE_SORT_COLUMNS = {
        "time": "relation_time",
        "platform": "platform",
        "topic": "topic",
        "keywords": "keywords_json",
        "content": "title",
        "link": "canonical_url",
        "relation": "primary_relation",
        "author": "author_name",
        "collection": "primary_collection",
        "media": "media_count",
        "archive": "archive_status",
        "published": "published_at",
        "account": "account_name",
        "synced": "last_synced_at",
    }

    def list_library_table(
        self,
        *,
        q: str | None = None,
        platform: str | None = None,
        relation: str | None = None,
        topic: str | None = None,
        collection: str | None = None,
        archive_status: str | None = None,
        after: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        sort_by: str = "time",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses = ["r.status='active'"]
        args: list[Any] = []
        if platform:
            clauses.append("c.platform=?")
            args.append(platform.lower())
        if relation:
            clauses.append("r.relation_type=?")
            args.append(relation)
        if topic:
            clauses.append("COALESCE(cc.topic,'未分类')=?")
            args.append(topic)
        if collection:
            clauses.append("r.collection_key=?")
            args.append(collection)
        for boundary in (after, observed_from):
            if boundary:
                clauses.append("COALESCE(r.relation_observed_at,r.first_observed_at)>=?")
                args.append(boundary)
        if observed_to:
            clauses.append("COALESCE(r.relation_observed_at,r.first_observed_at)<=?")
            args.append(observed_to)
        if q:
            literal_query = _literal_fts_query(q)
            cjk_terms = _cjk_substrings(q)
            if literal_query:
                clauses.append("c.id IN (SELECT content_id FROM content_fts WHERE content_fts MATCH ?)")
                args.append(literal_query)
            for term in cjk_terms:
                pattern = _like_pattern(term)
                clauses.append(
                    """c.id IN (SELECT content_id FROM content_fts
                       WHERE title LIKE ? ESCAPE '\\' OR author_name LIKE ? ESCAPE '\\'
                          OR body LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"""
                )
                args.extend([pattern, pattern, pattern, pattern])
            if not literal_query and not cjk_terms:
                clauses.append("0=1")
        where = " AND ".join(clauses)
        direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
        order_column = self._TABLE_SORT_COLUMNS.get(sort_by, "relation_time")
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)
        base = f"""WITH relation_rows AS (
            SELECT c.id,c.platform,c.external_content_id,c.canonical_url,c.title,c.author_name,c.published_at,
                   c.summary,c.language,c.media_count,c.last_synced_at,c.last_observed_at,
                   r.id AS relation_id,r.relation_type AS primary_relation,r.collection_key AS primary_collection,
                   COALESCE(r.relation_observed_at,r.first_observed_at) AS relation_time,
                   COALESCE(sa.display_name,sa.external_account_id,'') AS account_name,
                   COALESCE(cc.topic,'未分类') AS topic,COALESCE(cc.keywords_json,'[]') AS keywords_json,
                   COALESCE(cc.confidence,0) AS classification_confidence,COALESCE(cc.source,'local_rules') AS classification_source,
                   (SELECT COUNT(*) FROM artifact a WHERE a.content_id=c.id) AS artifact_count,
                   CASE
                     WHEN EXISTS(SELECT 1 FROM artifact a WHERE a.content_id=c.id AND a.status='complete') THEN '完整'
                     WHEN EXISTS(SELECT 1 FROM artifact a WHERE a.content_id=c.id AND a.status IN ('staged','ready')) THEN '处理中'
                     ELSE '仅元数据'
                   END AS archive_status,
                   (SELECT COUNT(*) FROM destination_receipt dr WHERE dr.content_id=c.id AND dr.status='done') AS export_done_count,
                   (SELECT GROUP_CONCAT(dr.destination_id) FROM destination_receipt dr WHERE dr.content_id=c.id AND dr.status='done') AS export_destination_ids,
                   ROW_NUMBER() OVER (PARTITION BY c.id ORDER BY COALESCE(r.relation_observed_at,r.first_observed_at) DESC,r.id) AS row_rank,
                   GROUP_CONCAT(r.relation_type) OVER (PARTITION BY c.id) AS relation_types,
                   GROUP_CONCAT(NULLIF(r.collection_key,'')) OVER (PARTITION BY c.id) AS collection_names
            FROM content c
            JOIN user_relation r ON r.content_id=c.id
            LEFT JOIN source_account sa ON sa.id=r.source_account_id
            LEFT JOIN content_classification cc ON cc.content_id=c.id
            WHERE {where}
        )
        SELECT * FROM relation_rows WHERE row_rank=1"""
        archive_clause = ""
        query_args = list(args)
        if archive_status:
            archive_clause = " AND archive_status=?"
            query_args.append(archive_status)
        count_sql = f"SELECT COUNT(*) AS total FROM ({base}) WHERE 1=1{archive_clause}"
        query_sql = f"SELECT * FROM ({base}) WHERE 1=1{archive_clause} ORDER BY {order_column} {direction}, id ASC LIMIT ? OFFSET ?"
        with self.connection() as con:
            total = int(con.execute(count_sql, query_args).fetchone()["total"])
            rows = [dict(row) for row in con.execute(query_sql, [*query_args, safe_limit, safe_offset]).fetchall()]
            platform_rows = con.execute(
                f"""SELECT c.platform,COUNT(DISTINCT c.id) AS count
                    FROM content c JOIN user_relation r ON r.content_id=c.id
                    LEFT JOIN content_classification cc ON cc.content_id=c.id
                    WHERE {where} GROUP BY c.platform ORDER BY count DESC""",
                args,
            ).fetchall()
            topic_rows = con.execute(
                f"""SELECT COALESCE(cc.topic,'未分类') AS topic,COUNT(DISTINCT c.id) AS count
                    FROM content c JOIN user_relation r ON r.content_id=c.id
                    LEFT JOIN content_classification cc ON cc.content_id=c.id
                    WHERE {where} GROUP BY COALESCE(cc.topic,'未分类') ORDER BY count DESC LIMIT 100""",
                args,
            ).fetchall()
        for row in rows:
            try:
                row["keywords"] = json.loads(row.pop("keywords_json") or "[]")
            except (TypeError, ValueError):
                row["keywords"] = []
            row["relations"] = list(dict.fromkeys(item for item in (row.pop("relation_types") or "").split(",") if item))
            row["collections"] = list(dict.fromkeys(item for item in (row.pop("collection_names") or "").split(",") if item))
            row["export_destinations"] = list(dict.fromkeys(item for item in (row.pop("export_destination_ids") or "").split(",") if item))
        return {
            "items": rows,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "sort_by": sort_by if sort_by in self._TABLE_SORT_COLUMNS else "time",
            "sort_dir": direction.lower(),
            "facets": {
                "platforms": [dict(row) for row in platform_rows],
                "topics": [dict(row) for row in topic_rows],
            },
        }

    def content_bodies(self, content_ids: list[str]) -> dict[str, str]:
        """Read export text from FTS without widening the library API payload."""
        identifiers = list(dict.fromkeys(str(content_id) for content_id in content_ids if content_id))
        result: dict[str, str] = {}
        with self.connection() as con:
            for start in range(0, len(identifiers), 500):
                batch = identifiers[start : start + 500]
                if not batch:
                    continue
                placeholders = ",".join("?" for _ in batch)
                rows = con.execute(
                    f"SELECT content_id,body FROM content_fts WHERE content_id IN ({placeholders})",
                    batch,
                ).fetchall()
                result.update({str(row["content_id"]): str(row["body"] or "") for row in rows})
        return result

    def get_content(self, content_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            content = con.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone()
            if not content:
                return None
            result = dict(content)
            body = con.execute(
                "SELECT body FROM content_fts WHERE content_id=?",
                (content_id,),
            ).fetchone()
            result["body"] = str(body["body"] or "") if body else ""
            result["relations"] = [dict(r) for r in con.execute(
                """SELECT * FROM user_relation WHERE content_id=?
                   ORDER BY last_observed_at DESC, first_observed_at DESC, id ASC""",
                (content_id,),
            ).fetchall()]
            result["artifacts"] = [dict(a) for a in con.execute("SELECT * FROM artifact WHERE content_id=?", (content_id,)).fetchall()]
            bindings = [dict(row) for row in con.execute(
                "SELECT * FROM destination_binding WHERE content_id=? ORDER BY destination_id", (content_id,)
            ).fetchall()]
            for binding in bindings:
                try:
                    binding["metadata"] = json.loads(binding.pop("metadata_json") or "{}")
                except (TypeError, ValueError):
                    binding["metadata"] = {}
            receipts = [dict(row) for row in con.execute(
                "SELECT * FROM destination_receipt WHERE content_id=? ORDER BY finished_at DESC LIMIT 100", (content_id,)
            ).fetchall()]
            for receipt in receipts:
                try:
                    receipt["evidence"] = json.loads(receipt.pop("evidence_json") or "{}")
                except (TypeError, ValueError):
                    receipt["evidence"] = {}
            result["destination_bindings"] = bindings
            result["export_receipts"] = receipts
            result["object_replicas"] = [dict(row) for row in con.execute(
                """SELECT r.* FROM object_replica r
                   JOIN artifact a ON a.id=r.artifact_id
                   WHERE a.content_id=?
                   ORDER BY a.created_at ASC,a.id ASC,r.store_id ASC""",
                (content_id,),
            ).fetchall()]
            return result

    def list_completed_content_bundles(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return only content whose every archived artifact has all three receipts.

        ``artifact.status='complete'`` is set exclusively by the shared replica
        completion gate, so this method cannot elevate a partially replicated
        capture into a durable business fact.
        """
        with self.connection() as con:
            rows = con.execute(
                """SELECT c.id
                   FROM content c
                   JOIN artifact a ON a.content_id=c.id
                   GROUP BY c.id
                   HAVING COUNT(a.id)>0
                      AND SUM(CASE WHEN a.status='complete' THEN 0 ELSE 1 END)=0
                   ORDER BY MAX(c.last_observed_at) ASC,c.id ASC
                   LIMIT ?""",
                (min(max(limit, 1), 1000),),
            ).fetchall()
        return [bundle for row in rows if (bundle := self.get_content(str(row["id"]))) is not None]

    def get_outbox_event(
        self,
        *,
        event_type: str,
        aggregate_id: str,
        payload_sha256: str,
    ) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute(
                """SELECT * FROM outbox
                   WHERE event_type=? AND aggregate_id=? AND payload_sha256=?""",
                (event_type, aggregate_id, payload_sha256),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(str(result.pop("payload_json")))
        return result

    def ensure_outbox_event(self, *, event_type: str, aggregate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one content-addressed durable-delivery event without replacing history."""
        payload_raw = json_bytes(payload).decode("utf-8")
        payload_sha256 = sha256_bytes(payload_raw.encode("utf-8"))
        event_id = stable_id("outbox", event_type, aggregate_id, payload_sha256)
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT OR IGNORE INTO outbox(
                     id,event_type,aggregate_id,payload_json,payload_sha256,status,attempt_count,not_before,created_at
                   ) VALUES(?,?,?,?,?,'pending',0,?,?)""",
                (event_id, event_type, aggregate_id, payload_raw, payload_sha256, now, now),
            )
        event = self.get_outbox_event(
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload_sha256=payload_sha256,
        )
        if event is None:  # pragma: no cover - SQLite insert/read failure boundary
            raise RuntimeError("Outbox 事件写入后不可读取")
        return event

    def mark_outbox_delivered(self, event_id: str) -> None:
        with self.connection() as con:
            con.execute(
                """UPDATE outbox
                   SET status='delivered',attempt_count=attempt_count+1,delivered_at=?,last_error_code=NULL
                   WHERE id=?""",
                (utcnow(), event_id),
            )

    def mark_outbox_failed(self, event_id: str, error_code: str) -> None:
        with self.connection() as con:
            con.execute(
                """UPDATE outbox
                   SET status='pending',attempt_count=attempt_count+1,last_error_code=?
                   WHERE id=?""",
                (error_code[:160], event_id),
            )

    def upsert_connector_state(
        self,
        connector_id: str,
        *,
        state: str,
        policy_gate: str,
        auth_gate: str,
        technical_gate: str,
        error_code: str | None = None,
        last_checked_at: str | None = None,
        latency_ms: int | None = None,
        message_zh: str | None = None,
    ) -> None:
        now = utcnow()
        success_at = now if state == "healthy" else None
        failure_at = now if state in {"degraded", "blocked_environment", "paused", "disabled"} else None
        with self.connection() as con:
            con.execute(
                """INSERT INTO connector_state(
                     connector_id,state,policy_gate,auth_gate,technical_gate,last_success_at,last_failure_at,
                     last_error_code,last_checked_at,latency_ms,last_message_zh,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(connector_id) DO UPDATE SET
                     state=excluded.state,policy_gate=excluded.policy_gate,auth_gate=excluded.auth_gate,
                     technical_gate=excluded.technical_gate,
                     last_success_at=COALESCE(excluded.last_success_at,connector_state.last_success_at),
                     last_failure_at=COALESCE(excluded.last_failure_at,connector_state.last_failure_at),
                     last_error_code=excluded.last_error_code,last_checked_at=excluded.last_checked_at,
                     latency_ms=excluded.latency_ms,last_message_zh=excluded.last_message_zh,updated_at=excluded.updated_at""",
                (
                    connector_id,
                    state,
                    policy_gate,
                    auth_gate,
                    technical_gate,
                    success_at,
                    failure_at,
                    error_code,
                    last_checked_at or now,
                    latency_ms,
                    message_zh,
                    now,
                ),
            )

    def connector_states(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM connector_state ORDER BY connector_id").fetchall()]

    def quota_states(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM quota_state ORDER BY store_id").fetchall()]

    def set_quota_state(self, store_id: str, measured: int, soft: int, hard: int, action: str) -> None:
        with self.connection() as con:
            con.execute(
                """INSERT INTO quota_state(store_id,measured_bytes,soft_limit_bytes,hard_limit_bytes,action,measured_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(store_id) DO UPDATE SET measured_bytes=excluded.measured_bytes,soft_limit_bytes=excluded.soft_limit_bytes,hard_limit_bytes=excluded.hard_limit_bytes,action=excluded.action,measured_at=excluded.measured_at""",
                (store_id, measured, soft, hard, action, utcnow()),
            )


    def record_scan_receipt(
        self,
        connector_id: str,
        run_id: str,
        receipt: dict[str, Any],
        *,
        source_account_id: str | None,
        relation_type: str,
    ) -> str:
        """Persist every scan attempt, including partial, failed and blocked runs."""
        now = utcnow()
        account_id = stable_id("acct", connector_id.strip().lower(), source_account_id) if source_account_id else None
        raw = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        receipt_id = stable_id("scan", connector_id, run_id)
        completeness = str(receipt.get("completeness") or "unknown")
        if completeness not in {"complete", "partial", "failed", "unknown"}:
            completeness = "unknown"
        item_count = max(0, int(receipt.get("item_count") or 0))
        cursor_start = receipt.get("cursor_start")
        cursor_end = receipt.get("cursor_end") or receipt.get("next_token") or receipt.get("next_cursor")
        failure_code = receipt.get("failure_code")
        with self.connection() as con:
            if source_account_id:
                con.execute(
                    """INSERT INTO source_account(id,platform,external_account_id,created_at,updated_at)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,external_account_id=excluded.external_account_id,updated_at=excluded.updated_at""",
                    (account_id, connector_id.strip().lower(), source_account_id, now, now),
                )
            con.execute(
                """INSERT INTO scan_receipt(id,connector_id,source_account_id,relation_type,started_at,completed_at,completeness,item_count,cursor_start,cursor_end,failure_code,evidence_sha256)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET completed_at=excluded.completed_at,completeness=excluded.completeness,item_count=excluded.item_count,cursor_end=excluded.cursor_end,failure_code=excluded.failure_code,evidence_sha256=excluded.evidence_sha256""",
                (
                    receipt_id,
                    connector_id,
                    account_id,
                    relation_type,
                    str(receipt.get("started_at") or now),
                    now,
                    completeness,
                    item_count,
                    str(cursor_start) if cursor_start is not None else None,
                    str(cursor_end) if cursor_end is not None else None,
                    str(failure_code) if failure_code else None,
                    sha256_bytes(raw.encode("utf-8")),
                ),
            )
        return receipt_id

    def apply_complete_scan(
        self,
        connector_id: str,
        observed_relation_ids: set[str],
        *,
        relation_type: str,
        collection_key: str = "",
        source_account_id: str | None = None,
    ) -> int:
        """Close only the exact scanned relation scope after two complete absences."""
        changed = 0
        platform = connector_id.strip().lower()
        account_scope = stable_id("acct", platform, source_account_id) if source_account_id else ""
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            rows = con.execute(
                """SELECT r.id,r.missing_complete_scan_count
                   FROM user_relation r
                   JOIN content c ON c.id=r.content_id
                   WHERE r.status='active'
                     AND c.platform=?
                     AND r.relation_type=?
                     AND r.collection_key=?
                     AND COALESCE(r.source_account_id,'')=?""",
                (platform, relation_type, collection_key, account_scope),
            ).fetchall()
            now = utcnow()
            for row in rows:
                if row["id"] in observed_relation_ids:
                    con.execute(
                        "UPDATE user_relation SET missing_complete_scan_count=0,last_observed_at=? WHERE id=?",
                        (now, row["id"]),
                    )
                    continue
                count = int(row["missing_complete_scan_count"]) + 1
                if count >= 2:
                    con.execute(
                        "UPDATE user_relation SET missing_complete_scan_count=?,status='closed',closed_at=? WHERE id=?",
                        (count, now, row["id"]),
                    )
                else:
                    con.execute(
                        "UPDATE user_relation SET missing_complete_scan_count=? WHERE id=?",
                        (count, row["id"]),
                    )
                changed += 1
            con.execute("COMMIT")
        return changed

    # Account-mirror state belongs to the rebuildable runtime journal.  The
    # methods below intentionally expose opaque handle references only to the
    # coordinator, never to public account-list responses.
    def upsert_source_account(
        self,
        *,
        platform: str,
        external_account_id: str,
        display_name: str | None,
        auth_method: str,
        auth_handle_ref: str | None,
        connection_state: str,
        auto_sync_enabled: bool = True,
        sync_interval_minutes: int = 360,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        now = utcnow()
        normalized_platform = platform.strip().lower()
        account_id = stable_id("acct", normalized_platform, external_account_id)
        with self.connection() as con:
            con.execute(
                """INSERT INTO source_account(
                       id,platform,external_account_id,display_name,auth_ref,
                       connection_state,auth_method,auth_handle_ref,auto_sync_enabled,
                       sync_interval_minutes,last_verified_at,metadata_json,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     platform=excluded.platform,
                     external_account_id=excluded.external_account_id,
                     display_name=COALESCE(excluded.display_name,source_account.display_name),
                     auth_method=excluded.auth_method,
                     auth_handle_ref=COALESCE(excluded.auth_handle_ref,source_account.auth_handle_ref),
                     connection_state=excluded.connection_state,
                     auto_sync_enabled=excluded.auto_sync_enabled,
                     sync_interval_minutes=excluded.sync_interval_minutes,
                     last_verified_at=CASE WHEN excluded.connection_state='connected' THEN excluded.last_verified_at ELSE source_account.last_verified_at END,
                     metadata_json=excluded.metadata_json,
                     updated_at=excluded.updated_at""",
                (
                    account_id,
                    normalized_platform,
                    external_account_id,
                    display_name,
                    None,
                    connection_state,
                    auth_method,
                    auth_handle_ref,
                    1 if auto_sync_enabled else 0,
                    sync_interval_minutes,
                    now if connection_state == "connected" else None,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return account_id

    @staticmethod
    def _decode_json_field(row: dict[str, Any], field: str, fallback: Any) -> None:
        try:
            row[field.removesuffix("_json")] = json.loads(row.pop(field) or fallback)
        except (TypeError, ValueError):
            row[field.removesuffix("_json")] = json.loads(fallback)

    def list_source_accounts(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT sa.*,
                          (SELECT COUNT(DISTINCT r.content_id)
                           FROM user_relation r
                           WHERE r.source_account_id=sa.id AND r.status='active') AS content_count,
                          (SELECT COUNT(*) FROM platform_collection pc
                           WHERE pc.source_account_id=sa.id AND pc.status='active') AS collection_count,
                          (SELECT id FROM sync_run sr WHERE sr.source_account_id=sa.id
                           ORDER BY sr.updated_at DESC LIMIT 1) AS latest_sync_run_id,
                          (SELECT status FROM sync_run sr WHERE sr.source_account_id=sa.id
                           ORDER BY sr.updated_at DESC LIMIT 1) AS latest_sync_status
                   FROM source_account sa
                   ORDER BY sa.platform,COALESCE(sa.display_name,sa.external_account_id),sa.id"""
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            self._decode_json_field(item, "metadata_json", "{}")
            item["auto_sync_enabled"] = bool(item.get("auto_sync_enabled"))
            item.pop("auth_ref", None)
            item.pop("auth_handle_ref", None)
            result.append(item)
        return result

    def get_source_account(self, account_id: str, *, include_handle: bool = False) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM source_account WHERE id=?", (account_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        self._decode_json_field(item, "metadata_json", "{}")
        item["auto_sync_enabled"] = bool(item.get("auto_sync_enabled"))
        if not include_handle:
            item.pop("auth_ref", None)
            item.pop("auth_handle_ref", None)
        return item

    def set_source_account_state(
        self,
        account_id: str,
        state: str,
        *,
        error_code: str | None = None,
        verified: bool = False,
    ) -> bool:
        now = utcnow()
        with self.connection() as con:
            cur = con.execute(
                """UPDATE source_account
                   SET connection_state=?,last_error_code=?,updated_at=?,
                       last_verified_at=CASE WHEN ? THEN ? ELSE last_verified_at END
                   WHERE id=?""",
                (state, error_code, now, 1 if verified else 0, now, account_id),
            )
        return cur.rowcount == 1

    def upsert_platform_collection(
        self,
        *,
        source_account_id: str,
        relation_type: str,
        name: str,
        external_collection_id: str | None = None,
        item_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        now = utcnow()
        external = external_collection_id or name
        collection_id = stable_id("col", source_account_id, relation_type, external)
        with self.connection() as con:
            con.execute(
                """INSERT INTO platform_collection(
                       id,source_account_id,external_collection_id,relation_type,name,item_count,
                       status,first_observed_at,last_observed_at,metadata_json
                   ) VALUES(?,?,?,?,?,?,'active',?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     item_count=COALESCE(excluded.item_count,platform_collection.item_count),
                     status='active',last_observed_at=excluded.last_observed_at,
                     metadata_json=excluded.metadata_json""",
                (
                    collection_id,
                    source_account_id,
                    external_collection_id,
                    relation_type,
                    name,
                    item_count,
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return collection_id

    def create_sync_run(
        self,
        *,
        source_account_id: str,
        platform: str,
        mode: str,
        relation_types: list[str],
        trigger_type: str,
    ) -> str:
        now = utcnow()
        run_id = stable_id("sync", source_account_id, mode, trigger_type, now)
        normalized_relations = list(dict.fromkeys(relation_types))
        with self.connection() as con:
            con.execute(
                """INSERT INTO sync_run(
                       id,source_account_id,platform,mode,trigger_type,status,relation_scope_json,updated_at
                   ) VALUES(?,?,?,?,?,'queued',?,?)""",
                (
                    run_id,
                    source_account_id,
                    platform.strip().lower(),
                    mode,
                    trigger_type,
                    json.dumps(normalized_relations, ensure_ascii=False),
                    now,
                ),
            )
            for relation_type in normalized_relations:
                con.execute(
                    """INSERT OR IGNORE INTO sync_run_scope(
                           sync_run_id,relation_type,collection_key,status,completeness,updated_at
                       ) VALUES(?,?,?,'pending','unknown',?)""",
                    (run_id, relation_type, "__relation__", now),
                )
        self.append_sync_event(run_id, "queued", {"mode": mode, "relations": normalized_relations})
        return run_id

    def append_sync_event(self, sync_run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> str:
        with self.connection() as con:
            row = con.execute(
                "SELECT COALESCE(MAX(sequence_no),0)+1 AS next_no FROM sync_run_event WHERE sync_run_id=?",
                (sync_run_id,),
            ).fetchone()
            sequence_no = int(row["next_no"])
            event_id = stable_id("sync_event", sync_run_id, sequence_no, event_type)
            con.execute(
                """INSERT INTO sync_run_event(id,sync_run_id,event_type,sequence_no,payload_json,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (event_id, sync_run_id, event_type, sequence_no, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True), utcnow()),
            )
        return event_id

    def update_sync_run(
        self,
        sync_run_id: str,
        *,
        status: str | None = None,
        completeness: str | None = None,
        discovered_delta: int = 0,
        imported_delta: int = 0,
        duplicate_delta: int = 0,
        failed_delta: int = 0,
        unavailable_delta: int = 0,
        cursor: dict[str, Any] | None = None,
        resume_token: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> bool:
        now = utcnow()
        completed = status in {"completed", "partial", "cancelled", "failed", "blocked_environment"}
        with self.connection() as con:
            cur = con.execute(
                """UPDATE sync_run SET
                     status=COALESCE(?,status),
                     completeness=COALESCE(?,completeness),
                     discovered_count=discovered_count+?,
                     imported_count=imported_count+?,
                     duplicate_count=duplicate_count+?,
                     failed_count=failed_count+?,
                     unavailable_count=unavailable_count+?,
                     cursor_json=CASE WHEN ? IS NULL THEN cursor_json ELSE ? END,
                     resume_token=COALESCE(?,resume_token),
                     last_error_code=?,last_error_message=?,
                     evidence_json=CASE WHEN ? IS NULL THEN evidence_json ELSE ? END,
                     started_at=CASE WHEN started_at IS NULL AND COALESCE(?,status) NOT IN ('queued','paused') THEN ? ELSE started_at END,
                     completed_at=CASE WHEN ? THEN ? ELSE completed_at END,
                     updated_at=?
                   WHERE id=?""",
                (
                    status,
                    completeness,
                    discovered_delta,
                    imported_delta,
                    duplicate_delta,
                    failed_delta,
                    unavailable_delta,
                    None if cursor is None else 1,
                    json.dumps(cursor or {}, ensure_ascii=False, sort_keys=True),
                    resume_token,
                    error_code,
                    error_message,
                    None if evidence is None else 1,
                    json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
                    status,
                    now,
                    1 if completed else 0,
                    now,
                    now,
                    sync_run_id,
                ),
            )
        if cur.rowcount and status:
            self.append_sync_event(sync_run_id, status, {"error_code": error_code, "message": error_message})
        return cur.rowcount == 1

    def _decode_sync_run(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        self._decode_json_field(item, "relation_scope_json", "[]")
        self._decode_json_field(item, "cursor_json", "{}")
        self._decode_json_field(item, "evidence_json", "{}")
        return item

    def get_sync_run(self, sync_run_id: str) -> dict[str, Any] | None:
        with self.connection() as con:
            row = con.execute("SELECT * FROM sync_run WHERE id=?", (sync_run_id,)).fetchone()
            events = con.execute(
                "SELECT * FROM sync_run_event WHERE sync_run_id=? ORDER BY sequence_no",
                (sync_run_id,),
            ).fetchall() if row else []
        if not row:
            return None
        result = self._decode_sync_run(row)
        result["events"] = []
        for event in events:
            item = dict(event)
            self._decode_json_field(item, "payload_json", "{}")
            result["events"].append(item)
        return result

    def list_sync_runs(self, *, source_account_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sync_run"
        args: list[Any] = []
        if source_account_id:
            sql += " WHERE source_account_id=?"
            args.append(source_account_id)
        sql += " ORDER BY updated_at DESC,id DESC LIMIT ?"
        args.append(min(max(limit, 1), 500))
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        return [self._decode_sync_run(row) for row in rows]

    def control_sync_run(self, sync_run_id: str, action: str) -> bool:
        run = self.get_sync_run(sync_run_id)
        if not run:
            return False
        transitions = {
            "pause": ({"queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting"}, "paused"),
            "resume": ({"paused", "partial", "failed", "blocked_environment"}, "queued"),
            "cancel": ({"queued", "authorizing", "discovering", "scanning", "normalizing", "artifacting", "exporting", "paused"}, "cancelled"),
            "retry": ({"partial", "failed", "blocked_environment"}, "queued"),
        }
        allowed, target = transitions.get(action, (set(), ""))
        if run["status"] not in allowed:
            return False
        return self.update_sync_run(sync_run_id, status=target, error_code=None, error_message=None)

    def record_sync_seen_relations(
        self,
        *,
        sync_run_id: str,
        relation_type: str,
        relation_ids_by_collection: dict[str, set[str]],
    ) -> int:
        now = utcnow()
        inserted = 0
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            for collection_key, relation_ids in relation_ids_by_collection.items():
                for relation_id in relation_ids:
                    cur = con.execute(
                        """INSERT OR IGNORE INTO sync_seen_relation(
                               sync_run_id,relation_type,collection_key,relation_id,observed_at
                           ) VALUES(?,?,?,?,?)""",
                        (sync_run_id, relation_type, collection_key or "", relation_id, now),
                    )
                    inserted += max(cur.rowcount, 0)
            con.execute("COMMIT")
        return inserted

    def list_sync_seen_relation_ids(
        self,
        *,
        sync_run_id: str,
        relation_type: str,
        collection_key: str | None = None,
    ) -> set[str]:
        sql = "SELECT relation_id FROM sync_seen_relation WHERE sync_run_id=? AND relation_type=?"
        args: list[Any] = [sync_run_id, relation_type]
        if collection_key is not None:
            sql += " AND collection_key=?"
            args.append(collection_key)
        with self.connection() as con:
            return {str(row["relation_id"]) for row in con.execute(sql, args).fetchall()}

    def list_sync_seen_collections(self, *, sync_run_id: str, relation_type: str) -> set[str]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT DISTINCT collection_key FROM sync_seen_relation
                   WHERE sync_run_id=? AND relation_type=?""",
                (sync_run_id, relation_type),
            ).fetchall()
        return {str(row["collection_key"] or "") for row in rows}

    def list_existing_relation_collections(
        self,
        *,
        platform: str,
        external_account_id: str,
        relation_type: str,
    ) -> set[str]:
        account_id = stable_id("acct", platform.strip().lower(), external_account_id)
        with self.connection() as con:
            rows = con.execute(
                """SELECT DISTINCT r.collection_key FROM user_relation r
                   JOIN content c ON c.id=r.content_id
                   WHERE c.platform=? AND r.source_account_id=? AND r.relation_type=?""",
                (platform.strip().lower(), account_id, relation_type),
            ).fetchall()
        return {str(row["collection_key"] or "") for row in rows}

    def upsert_sync_run_scope(
        self,
        *,
        sync_run_id: str,
        relation_type: str,
        collection_key: str,
        status: str,
        completeness: str,
        discovered_delta: int = 0,
        imported_delta: int = 0,
        failed_delta: int = 0,
    ) -> None:
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT INTO sync_run_scope(
                       sync_run_id,relation_type,collection_key,status,completeness,
                       discovered_count,imported_count,failed_count,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(sync_run_id,relation_type,collection_key) DO UPDATE SET
                     status=excluded.status,
                     completeness=excluded.completeness,
                     discovered_count=sync_run_scope.discovered_count+excluded.discovered_count,
                     imported_count=sync_run_scope.imported_count+excluded.imported_count,
                     failed_count=sync_run_scope.failed_count+excluded.failed_count,
                     updated_at=excluded.updated_at""",
                (
                    sync_run_id,
                    relation_type,
                    collection_key,
                    status,
                    completeness,
                    discovered_delta,
                    imported_delta,
                    failed_delta,
                    now,
                ),
            )

    def list_sync_run_scopes(self, sync_run_id: str) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT * FROM sync_run_scope WHERE sync_run_id=?
                   ORDER BY relation_type,collection_key""",
                (sync_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_sync_checkpoint(
        self,
        *,
        source_account_id: str,
        relation_type: str,
        collection_key: str,
        cursor: dict[str, Any],
        known_anchor: str | None,
        last_complete_sync_run_id: str | None,
        complete: bool,
    ) -> str:
        checkpoint_id = stable_id("checkpoint", source_account_id, relation_type, collection_key)
        now = utcnow()
        with self.connection() as con:
            con.execute(
                """INSERT INTO sync_checkpoint(
                       id,source_account_id,relation_type,collection_key,cursor_json,known_anchor,
                       last_complete_sync_run_id,last_success_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     cursor_json=excluded.cursor_json,
                     known_anchor=COALESCE(excluded.known_anchor,sync_checkpoint.known_anchor),
                     last_complete_sync_run_id=CASE WHEN ? THEN excluded.last_complete_sync_run_id ELSE sync_checkpoint.last_complete_sync_run_id END,
                     last_success_at=CASE WHEN ? THEN excluded.last_success_at ELSE sync_checkpoint.last_success_at END,
                     updated_at=excluded.updated_at""",
                (
                    checkpoint_id,
                    source_account_id,
                    relation_type,
                    collection_key,
                    json.dumps(cursor, ensure_ascii=False, sort_keys=True),
                    known_anchor,
                    last_complete_sync_run_id,
                    now,
                    now,
                    1 if complete else 0,
                    1 if complete else 0,
                ),
            )
        return checkpoint_id

    def artifact_unique_bytes(self) -> int:
        with self.connection() as con:
            row = con.execute("SELECT COALESCE(SUM(byte_size),0) AS total FROM (SELECT sha256,MAX(byte_size) AS byte_size FROM artifact GROUP BY sha256)").fetchone()
            return int(row["total"] if row else 0)

    def list_artifacts_for_replication(
        self,
        store_id: str,
        *,
        limit: int = 100,
        requires_verified_store: str | None = None,
    ) -> list[dict[str, Any]]:
        args: list[Any] = [store_id]
        prerequisite = ""
        if requires_verified_store:
            prerequisite = """AND EXISTS (
                SELECT 1 FROM object_replica required
                WHERE required.artifact_id=a.id AND required.store_id=? AND required.status='verified'
            )"""
            args.append(requires_verified_store)
        args.append(min(max(limit, 1), 1000))
        sql = f"""SELECT a.*
                  FROM artifact a
                  LEFT JOIN object_replica current
                    ON current.artifact_id=a.id AND current.store_id=?
                  WHERE a.local_path IS NOT NULL
                    AND a.status IN ('staged','ready','complete')
                    AND (current.status IS NULL OR current.status!='verified')
                    {prerequisite}
                  ORDER BY a.created_at ASC
                  LIMIT ?"""
        with self.connection() as con:
            return [dict(row) for row in con.execute(sql, args).fetchall()]

    def get_object_replica(self, artifact_id: str, store_id: str) -> dict[str, Any] | None:
        """Return one replica receipt without granting it completion authority."""
        with self.connection() as con:
            row = con.execute(
                """SELECT id,artifact_id,store_id,object_key,status,etag,verified_sha256,
                          original_sha256,encryption,updated_at,last_error_code
                   FROM object_replica WHERE artifact_id=? AND store_id=?""",
                (artifact_id, store_id),
            ).fetchone()
        return dict(row) if row else None

    def upsert_object_replica(
        self,
        *,
        artifact_id: str,
        store_id: str,
        object_key: str,
        status: str,
        etag: str | None = None,
        verified_sha256: str | None = None,
        original_sha256: str | None = None,
        encryption: str | None = None,
        last_error_code: str | None = None,
    ) -> str:
        replica_id = stable_id("replica", artifact_id, store_id)
        with self.connection() as con:
            con.execute(
                """INSERT INTO object_replica(id,artifact_id,store_id,object_key,status,etag,verified_sha256,original_sha256,encryption,updated_at,last_error_code)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(artifact_id,store_id) DO UPDATE SET
                     object_key=excluded.object_key,status=excluded.status,etag=excluded.etag,
                     verified_sha256=excluded.verified_sha256,original_sha256=excluded.original_sha256,
                     encryption=excluded.encryption,updated_at=excluded.updated_at,last_error_code=excluded.last_error_code""",
                (replica_id, artifact_id, store_id, object_key, status, etag, verified_sha256, original_sha256, encryption, utcnow(), last_error_code),
            )
            if status == "verified":
                rows = con.execute(
                    "SELECT store_id,verified_sha256,original_sha256,encryption FROM object_replica WHERE artifact_id=? AND status='verified'",
                    (artifact_id,),
                ).fetchall()
                by_store = {row["store_id"]: row for row in rows}
                required = {"r2", "oci", "github"}
                if required.issubset(by_store):
                    cipher_hashes = {str(by_store[item]["verified_sha256"] or "") for item in required}
                    original_hashes = {str(by_store[item]["original_sha256"] or "") for item in required}
                    algorithms = {str(by_store[item]["encryption"] or "") for item in required}
                    if len(cipher_hashes) == 1 and "" not in cipher_hashes and len(original_hashes) == 1 and len(algorithms) == 1:
                        con.execute("UPDATE artifact SET status='complete' WHERE id=?", (artifact_id,))
        return replica_id

    def replica_summary(self) -> list[dict[str, Any]]:
        with self.connection() as con:
            rows = con.execute(
                """SELECT r.store_id,r.status,COUNT(*) AS object_count,COALESCE(SUM(a.byte_size),0) AS byte_count
                   FROM object_replica r JOIN artifact a ON a.id=r.artifact_id
                   GROUP BY r.store_id,r.status ORDER BY r.store_id,r.status"""
            ).fetchall()
            return [dict(row) for row in rows]

    def replication_completion(self) -> dict[str, int]:
        with self.connection() as con:
            total = int(con.execute("SELECT COUNT(*) FROM artifact").fetchone()[0])
            complete = int(con.execute("SELECT COUNT(*) FROM artifact WHERE status='complete'").fetchone()[0])
            pending = max(0, total - complete)
            return {"required_replicas": 3, "total_artifacts": total, "all_three_verified": complete, "pending": pending}
