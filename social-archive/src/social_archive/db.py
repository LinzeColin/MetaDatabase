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
        with self.connection() as con:
            con.executescript(schema)
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
        canonical_url = canonicalize_url(str(request.url))
        content_id = stable_id("cnt", request.platform.lower(), request.external_content_id or canonical_url)
        account_id = stable_id("acct", request.platform.lower(), request.source_account_id) if request.source_account_id else None
        relation_id = stable_id("rel", account_id or "owner", content_id, request.relation_type, request.collection_key)
        payload = request.model_dump(mode="json")
        payload_bytes = json_bytes(payload)
        observation_id = stable_id("obs", request.platform.lower(), sha256_bytes(payload_bytes))
        metadata_json = json.dumps(request.raw_metadata, ensure_ascii=False, sort_keys=True)
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                """INSERT INTO content(id,platform,external_content_id,canonical_url,title,author_name,published_at,first_observed_at,last_observed_at,metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=COALESCE(excluded.title,content.title),author_name=COALESCE(excluded.author_name,content.author_name),published_at=COALESCE(excluded.published_at,content.published_at),last_observed_at=excluded.last_observed_at,metadata_json=excluded.metadata_json""",
                (content_id, request.platform.lower(), request.external_content_id, canonical_url, request.title, request.author_name, request.published_at, now, now, metadata_json),
            )
            if request.source_account_id:
                con.execute(
                    """INSERT INTO source_account(id,platform,external_account_id,created_at,updated_at)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,external_account_id=excluded.external_account_id,updated_at=excluded.updated_at""",
                    (account_id, request.platform.lower(), request.source_account_id, now, now),
                )
            con.execute(
                """INSERT INTO user_relation(id,source_account_id,content_id,relation_type,collection_key,status,first_observed_at,last_observed_at,missing_complete_scan_count)
                   VALUES(?,?,?,?,?,'active',?,?,0)
                   ON CONFLICT(id) DO UPDATE SET status='active',last_observed_at=excluded.last_observed_at,missing_complete_scan_count=0,closed_at=NULL""",
                (relation_id, account_id, content_id, request.relation_type, request.collection_key, now, now),
            )
            con.execute(
                "INSERT OR IGNORE INTO observation(id,connector_id,content_id,observed_at,payload_json,payload_sha256) VALUES(?,?,?,?,?,?)",
                (observation_id, f"capture:{request.platform.lower()}", content_id, now, payload_bytes.decode("utf-8"), sha256_bytes(payload_bytes)),
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
            fts_tags = " ".join(str(row["collection_key"]) for row in collection_rows)
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
                    AND a.status IN ('staged','ready')
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
