from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .clock import Clock, SystemClock


class RuntimeDB:
    def __init__(self, path: Path, schema: Path, clock: Clock | None = None):
        self.path = path
        self.schema = schema
        self.clock = clock or SystemClock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(schema.read_text())

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
        finally:
            conn.close()

    def now(self) -> str:
        return self.clock.now().astimezone(timezone.utc).isoformat()

    def enqueue(self, request: dict[str, Any], idempotency_key: str) -> tuple[str, bool]:
        if not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("INVALID_IDEMPOTENCY_KEY")
        now = self.now()
        job_id = str(uuid.uuid4())
        request_json = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT job_id FROM jobs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row:
                conn.execute("COMMIT")
                return row["job_id"], False
            conn.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,NULL)",
                (job_id, idempotency_key, request_json, "QUEUED", now, now),
            )
            conn.execute("COMMIT")
        return job_id, True

    @staticmethod
    def _requeue_expired(conn: sqlite3.Connection, now: str) -> int:
        rows = conn.execute(
            """
            SELECT j.job_id
            FROM jobs AS j
            JOIN leases AS l ON l.resource_id=j.job_id
            WHERE j.state='RUNNING' AND l.expires_at<=?
            """,
            (now,),
        ).fetchall()
        for row in rows:
            job_id = row["job_id"]
            conn.execute(
                """
                UPDATE attempts
                SET state='ABANDONED', ended_at=?, error_code='LEASE_EXPIRED'
                WHERE job_id=? AND state='RUNNING'
                """,
                (now, job_id),
            )
            conn.execute(
                "UPDATE jobs SET state='QUEUED',updated_at=? WHERE job_id=?",
                (now, job_id),
            )
        return len(rows)

    def claim(self, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("INVALID_WORKER_ID")
        if lease_seconds < 5 or lease_seconds > 3600:
            raise ValueError("INVALID_LEASE_SECONDS")
        now_dt = self.clock.now().astimezone(timezone.utc)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._requeue_expired(conn, now)
            row = conn.execute(
                "SELECT * FROM jobs WHERE state='QUEUED' ORDER BY created_at,job_id LIMIT 1"
            ).fetchone()
            if not row:
                conn.execute("COMMIT")
                return None
            current = conn.execute(
                "SELECT fencing_token FROM leases WHERE resource_id=?", (row["job_id"],)
            ).fetchone()
            fencing_token = int(current["fencing_token"] if current else 0) + 1
            conn.execute(
                """
                INSERT INTO leases(resource_id,owner_id,fencing_token,expires_at)
                VALUES (?,?,?,?)
                ON CONFLICT(resource_id) DO UPDATE SET
                  owner_id=excluded.owner_id,
                  fencing_token=excluded.fencing_token,
                  expires_at=excluded.expires_at
                """,
                (row["job_id"], worker_id, fencing_token, expires_at),
            )
            attempt_no = int(
                conn.execute(
                    "SELECT COALESCE(MAX(number),0)+1 AS next FROM attempts WHERE job_id=?",
                    (row["job_id"],),
                ).fetchone()["next"]
            )
            attempt_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO attempts(attempt_id,job_id,number,state,started_at) VALUES (?,?,?,?,?)",
                (attempt_id, row["job_id"], attempt_no, "RUNNING", now),
            )
            conn.execute(
                "UPDATE jobs SET state='RUNNING',updated_at=? WHERE job_id=?",
                (now, row["job_id"]),
            )
            conn.execute("COMMIT")
            return {
                "job_id": row["job_id"],
                "request": json.loads(row["request_json"]),
                "fencing_token": fencing_token,
                "attempt_id": attempt_id,
                "attempt_number": attempt_no,
                "lease_expires_at": expires_at,
            }

    def complete(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        action: dict[str, Any],
    ) -> None:
        now = self.now()
        event_id = str(uuid.uuid4())
        action_id = str(uuid.uuid4())
        payload = json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            lease = conn.execute(
                "SELECT * FROM leases WHERE resource_id=?", (job_id,)
            ).fetchone()
            job = conn.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if (
                not lease
                or not job
                or job["state"] != "RUNNING"
                or lease["owner_id"] != worker_id
                or int(lease["fencing_token"]) != int(fencing_token)
                or lease["expires_at"] <= now
            ):
                conn.execute("ROLLBACK")
                raise RuntimeError("STALE_OR_EXPIRED_FENCING_TOKEN")
            conn.execute(
                "UPDATE jobs SET state='COMPLETED',updated_at=?,result_json=? WHERE job_id=?",
                (now, payload, job_id),
            )
            conn.execute(
                "INSERT INTO actions VALUES (?,?,?,?,?,?,?)",
                (
                    action_id,
                    job_id,
                    action["symbol"],
                    action["action"],
                    action["valid_until"],
                    payload,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE attempts
                SET state='COMPLETED', ended_at=?, error_code=NULL
                WHERE attempt_id=(
                  SELECT attempt_id FROM attempts
                  WHERE job_id=? AND state='RUNNING'
                  ORDER BY number DESC LIMIT 1
                )
                """,
                (now, job_id),
            )
            conn.execute(
                "INSERT INTO runtime_journal(event_id,event_type,aggregate_id,payload_json,created_at) VALUES (?,?,?,?,?)",
                (event_id, "action.created", job_id, payload, now),
            )
            conn.execute(
                "INSERT INTO outbox VALUES (?,?,?,?,?,?,NULL)",
                (event_id, "action.created", payload, "PENDING", 0, now),
            )
            conn.execute("DELETE FROM leases WHERE resource_id=?", (job_id,))
            conn.execute("COMMIT")

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["request"] = json.loads(data.pop("request_json"))
            data["result"] = json.loads(data["result_json"]) if data["result_json"] else None
            return data

    def actions(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 200)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT packet_json FROM actions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["packet_json"]) for row in rows]

    def upsert_skill_signal(self, signal: dict[str, Any]) -> None:
        now = self.now()
        payload = json.dumps(signal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO skill_signal_inputs(skill_id,symbol,market,as_of,payload_json,source_digest,updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(skill_id,symbol,market) DO UPDATE SET
                  as_of=excluded.as_of,
                  payload_json=excluded.payload_json,
                  source_digest=excluded.source_digest,
                  updated_at=excluded.updated_at
                """,
                (
                    signal["skill_id"],
                    signal["symbol"].upper(),
                    signal["market"].upper(),
                    signal["as_of"],
                    payload,
                    signal["source_digest"],
                    now,
                ),
            )

    def upsert_market_snapshot(self, snapshot: dict[str, Any]) -> None:
        now = self.now()
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO market_snapshots(symbol,market,as_of,payload_json,source_digest,updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(symbol,market) DO UPDATE SET
                  as_of=excluded.as_of,
                  payload_json=excluded.payload_json,
                  source_digest=excluded.source_digest,
                  updated_at=excluded.updated_at
                """,
                (
                    snapshot["symbol"].upper(),
                    snapshot["market"].upper(),
                    snapshot["as_of"],
                    payload,
                    snapshot["source_digest"],
                    now,
                ),
            )

    def skill_signals(self, symbol: str | None = None, market: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        if market:
            clauses.append("market=?")
            params.append(market.upper())
        sql = "SELECT payload_json FROM skill_signal_inputs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(min(max(int(limit), 1), 1000))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def market_snapshot(self, symbol: str, market: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM market_snapshots WHERE symbol=? AND market=?",
                (symbol.upper(), market.upper()),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def skill_overview(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT skill_id, COUNT(*) AS signal_count, MAX(updated_at) AS last_updated
                FROM skill_signal_inputs GROUP BY skill_id ORDER BY skill_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def evolution_overview(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evolution_runs ORDER BY created_at DESC LIMIT ?",
                (min(max(int(limit), 1), 200),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            result.append(item)
        return result



    def upsert_skill_snapshot(self, snapshot: dict[str, Any]) -> None:
        required = {"skill_id", "source_commit", "content_sha256", "lifecycle_state", "compatibility_state", "observed_at"}
        missing = required - set(snapshot)
        if missing:
            raise ValueError("MISSING_SKILL_SNAPSHOT_FIELDS:" + ",".join(sorted(missing)))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO skill_snapshots(skill_id,source_commit,content_sha256,lifecycle_state,compatibility_state,observed_at,promoted_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(skill_id,source_commit,content_sha256) DO UPDATE SET
                  lifecycle_state=excluded.lifecycle_state,
                  compatibility_state=excluded.compatibility_state,
                  observed_at=excluded.observed_at,
                  promoted_at=COALESCE(excluded.promoted_at,skill_snapshots.promoted_at)
                """,
                (snapshot["skill_id"], snapshot["source_commit"], snapshot["content_sha256"], snapshot["lifecycle_state"], snapshot["compatibility_state"], snapshot["observed_at"], snapshot.get("promoted_at")),
            )

    def skill_source_overview(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT skill_id,source_commit,content_sha256,lifecycle_state,compatibility_state,observed_at,promoted_at
                FROM skill_snapshots ORDER BY observed_at DESC LIMIT ?
                """,
                (min(max(int(limit), 1), 1000),),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_action(self, symbol: str | None = None, market: str | None = None) -> dict[str, Any] | None:
        clauses: list[str] = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        sql = "SELECT packet_json FROM actions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        packet = json.loads(row["packet_json"])
        if market and str(packet.get("market", "")).upper() != market.upper():
            return None
        return packet

    def save_decision_snapshot(self, snapshot: dict[str, Any]) -> None:
        symbol = str(snapshot.get("symbol", "")).upper()
        market = str(snapshot.get("market", "")).upper()
        receipt = str(snapshot.get("receipt_sha256", ""))
        if not symbol or not market or len(receipt) != 64:
            raise ValueError("INVALID_DECISION_SNAPSHOT")
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO decision_snapshots(symbol,market,payload_json,receipt_sha256,created_at)
                VALUES (?,?,?,?,?)
                """,
                (symbol, market, payload, receipt, self.now()),
            )

    def decision_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM decision_snapshots ORDER BY created_at DESC LIMIT ?",
                (min(max(int(limit), 1), 200),),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def runtime_counts(self) -> dict[str, int]:
        names = (
            "jobs", "attempts", "leases", "runtime_journal", "outbox", "actions",
            "skill_snapshots", "evolution_runs", "business_line_status", "skill_signal_inputs",
            "market_snapshots", "decision_snapshots",
        )
        result: dict[str, int] = {}
        with self.connect() as conn:
            for name in names:
                result[name] = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        return result
