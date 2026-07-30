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
