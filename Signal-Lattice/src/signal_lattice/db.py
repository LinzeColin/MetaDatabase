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
            "market_snapshots", "decision_snapshots", "minute_cycles", "minute_skill_runs",
            "skill_runtime_registry", "minute_market_snapshots", "universe_members",
            "skill_reliability", "skill_outcome_queue", "source_reconcile_events",
        )
        result: dict[str, int] = {}
        with self.connect() as conn:
            for name in names:
                result[name] = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        return result

    # Minute-cycle north-star runtime -------------------------------------------------
    def runtime_skill_registry(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_runtime_registry ORDER BY skill_id"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["manifest"] = json.loads(item.pop("manifest_json"))
            item["lineage"] = json.loads(item.pop("lineage_json"))
            if item.get("lkg_manifest_json"):
                item["lkg_manifest"] = json.loads(item.pop("lkg_manifest_json"))
            else:
                item.pop("lkg_manifest_json", None)
                item["lkg_manifest"] = None
            result.append(item)
        return result

    def active_runtime_skills(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM skill_runtime_registry
                WHERE lifecycle_state='ACTIVE' AND compatibility_state IN ('BUILTIN_ADAPTER','BUNDLED_ADAPTER','BUNDLED_LAST_KNOWN_GOOD','MACHINE_CONTRACT','COMPATIBLE','LAST_KNOWN_GOOD')
                ORDER BY skill_id
                """
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["manifest"] = json.loads(item.pop("manifest_json"))
            item["lineage"] = json.loads(item.pop("lineage_json"))
            item.pop("lkg_manifest_json", None)
            result.append(item)
        return result

    def upsert_runtime_skill(self, manifest: dict[str, Any], manifest_sha256: str, now: str) -> None:
        payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        lineage = json.dumps(manifest.get("lineage", []), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT manifest_json,manifest_sha256 FROM skill_runtime_registry WHERE skill_id=?",
                (manifest["skill_id"],),
            ).fetchone()
            first_seen = now
            if existing:
                first_seen_row = conn.execute(
                    "SELECT first_seen_at FROM skill_runtime_registry WHERE skill_id=?", (manifest["skill_id"],)
                ).fetchone()
                first_seen = first_seen_row["first_seen_at"]
            conn.execute(
                """
                INSERT INTO skill_runtime_registry(
                  skill_id,display_name,skill_version,source_commit,source_path,source_sha256,
                  manifest_json,manifest_sha256,lifecycle_state,compatibility_state,runtime_profile,
                  lineage_json,first_seen_at,last_seen_at,promoted_at,lkg_manifest_json,lkg_manifest_sha256
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(skill_id) DO UPDATE SET
                  display_name=excluded.display_name,
                  skill_version=excluded.skill_version,
                  source_commit=excluded.source_commit,
                  source_path=excluded.source_path,
                  source_sha256=excluded.source_sha256,
                  lkg_manifest_json=CASE WHEN skill_runtime_registry.lifecycle_state='ACTIVE' THEN skill_runtime_registry.manifest_json ELSE skill_runtime_registry.lkg_manifest_json END,
                  lkg_manifest_sha256=CASE WHEN skill_runtime_registry.lifecycle_state='ACTIVE' THEN skill_runtime_registry.manifest_sha256 ELSE skill_runtime_registry.lkg_manifest_sha256 END,
                  manifest_json=excluded.manifest_json,
                  manifest_sha256=excluded.manifest_sha256,
                  lifecycle_state='ACTIVE',
                  compatibility_state=excluded.compatibility_state,
                  runtime_profile=excluded.runtime_profile,
                  lineage_json=excluded.lineage_json,
                  last_seen_at=excluded.last_seen_at,
                  promoted_at=excluded.promoted_at
                """,
                (
                    manifest["skill_id"], manifest["display_name"], manifest["skill_version"],
                    manifest["source_commit"], manifest["source_path"], manifest["source_sha256"],
                    payload, manifest_sha256, "ACTIVE", manifest.get("compatibility_state", "BUILTIN_ADAPTER"),
                    manifest["runtime_profile"], lineage, first_seen, now, now,
                    existing["manifest_json"] if existing else None,
                    existing["manifest_sha256"] if existing else None,
                ),
            )
            conn.execute("COMMIT")

    def retire_runtime_skill(self, skill_id: str, now: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE skill_runtime_registry SET lifecycle_state='RETIRED',last_seen_at=? WHERE skill_id=?",
                (now, skill_id),
            )

    def record_source_reconcile_event(self, event: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO source_reconcile_events(
                  event_id,source_commit,event_type,skill_id,previous_json,current_json,state,created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    event["event_id"], event["source_commit"], event["event_type"], event["skill_id"],
                    json.dumps(event.get("previous"), ensure_ascii=False, sort_keys=True, separators=(",", ":")) if event.get("previous") is not None else None,
                    json.dumps(event.get("current"), ensure_ascii=False, sort_keys=True, separators=(",", ":")) if event.get("current") is not None else None,
                    event["state"], event["created_at"],
                ),
            )

    def record_quarantined_skill(self, item: dict[str, Any], source_commit: str, now: str) -> None:
        skill_id = str(item.get("skill_id", "UNKNOWN"))
        event = {
            "event_id": str(uuid.uuid4()),
            "source_commit": source_commit,
            "event_type": "QUARANTINED",
            "skill_id": skill_id,
            "previous": None,
            "current": item,
            "state": "QUARANTINED",
            "created_at": now,
        }
        self.record_source_reconcile_event(event)

    def replace_universe(self, members: list[dict[str, Any]]) -> None:
        now = self.now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active_keys: set[tuple[str, str]] = set()
            for row in members:
                symbol = str(row["symbol"]).upper()
                market = str(row["market"]).upper()
                active_keys.add((symbol, market))
                conn.execute(
                    """
                    INSERT INTO universe_members(symbol,market,active,priority,source,metadata_json,updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(symbol,market) DO UPDATE SET
                      active=excluded.active,priority=excluded.priority,source=excluded.source,
                      metadata_json=excluded.metadata_json,updated_at=excluded.updated_at
                    """,
                    (
                        symbol, market, 1 if row.get("active", True) else 0, int(row.get("priority", 100)),
                        str(row.get("source", "CONFIG")),
                        json.dumps(row.get("metadata", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        now,
                    ),
                )
            existing = conn.execute("SELECT symbol,market FROM universe_members WHERE active=1").fetchall()
            for row in existing:
                key = (row["symbol"], row["market"])
                if key not in active_keys:
                    conn.execute(
                        "UPDATE universe_members SET active=0,updated_at=? WHERE symbol=? AND market=?",
                        (now, *key),
                    )
            conn.execute("COMMIT")

    def active_universe(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM universe_members WHERE active=1 ORDER BY priority,symbol,market"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            item["active"] = bool(item["active"])
            result.append(item)
        return result

    def begin_minute_cycle(
        self,
        cycle_id: str,
        scheduled_for: str,
        source_commit: str | None,
        universe_sha256: str | None,
        active_skill_count: int,
    ) -> bool:
        now = self.now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT cycle_id,state FROM minute_cycles WHERE scheduled_for=?", (scheduled_for,)
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return False
            running = conn.execute(
                "SELECT cycle_id FROM minute_cycles WHERE state='RUNNING' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if running:
                conn.execute(
                    """
                    INSERT INTO minute_cycles(
                      cycle_id,scheduled_for,started_at,completed_at,state,source_commit,universe_sha256,
                      active_skill_count,completed_skill_count,failed_skill_count,error_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (cycle_id, scheduled_for, now, now, "SKIPPED_OVERLAP", source_commit, universe_sha256,
                     active_skill_count, 0, 0, json.dumps({"reason": "PREVIOUS_CYCLE_RUNNING"})),
                )
                conn.execute("COMMIT")
                return False
            conn.execute(
                """
                INSERT INTO minute_cycles(
                  cycle_id,scheduled_for,started_at,state,source_commit,universe_sha256,
                  active_skill_count,completed_skill_count,failed_skill_count
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (cycle_id, scheduled_for, now, "RUNNING", source_commit, universe_sha256,
                 active_skill_count, 0, 0),
            )
            conn.execute("COMMIT")
        return True

    def save_cycle_market_snapshot(self, cycle_id: str, snapshot: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for security in snapshot.get("universe", []):
                symbol = str(security["symbol"]).upper()
                market = str(security["market"]).upper()
                payload = {
                    "schema_version": snapshot.get("schema_version", "1.0.0"),
                    "cycle_id": cycle_id,
                    "as_of": snapshot["as_of"],
                    "available_at": snapshot.get("available_at", snapshot["as_of"]),
                    "ingested_at": snapshot.get("ingested_at", snapshot["as_of"]),
                    "source": snapshot.get("source"),
                    "source_digest": snapshot["source_digest"],
                    "point_in_time_ok": snapshot.get("point_in_time_ok", False),
                    "license_ok": snapshot.get("license_ok", False),
                    "data_quality": snapshot.get("data_quality", 0.0),
                    **security,
                }
                conn.execute(
                    """
                    INSERT OR REPLACE INTO minute_market_snapshots(
                      cycle_id,symbol,market,as_of,snapshot_json,source_digest
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        cycle_id, symbol, market, snapshot["as_of"],
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        snapshot["source_digest"],
                    ),
                )
            conn.execute(
                "UPDATE minute_cycles SET market_snapshot_sha256=? WHERE cycle_id=?",
                (snapshot["source_digest"], cycle_id),
            )
            conn.execute("COMMIT")

    def start_minute_skill_run(
        self,
        cycle_id: str,
        skill: dict[str, Any],
        input_sha256: str,
        isolation_backend: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO minute_skill_runs(
                  cycle_id,skill_id,skill_version,source_commit,manifest_sha256,state,started_at,
                  input_sha256,isolation_backend
                ) VALUES (?,?,?,?,?,'RUNNING',?,?,?)
                """,
                (
                    cycle_id, skill["skill_id"], skill["skill_version"], skill["source_commit"],
                    skill["manifest_sha256"], self.now(), input_sha256, isolation_backend,
                ),
            )

    def finish_minute_skill_run(
        self,
        cycle_id: str,
        skill_id: str,
        state: str,
        duration_ms: int,
        output: dict[str, Any] | None,
        output_sha256: str | None,
        error_code: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE minute_skill_runs SET state=?,completed_at=?,duration_ms=?,output_json=?,
                  output_sha256=?,error_code=? WHERE cycle_id=? AND skill_id=?
                """,
                (
                    state, self.now(), duration_ms,
                    json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if output is not None else None,
                    output_sha256, error_code, cycle_id, skill_id,
                ),
            )

    def minute_skill_runs(self, cycle_id: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql = "SELECT * FROM minute_skill_runs"
        if cycle_id:
            sql += " WHERE cycle_id=?"
            params.append(cycle_id)
        sql += " ORDER BY started_at DESC,skill_id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["output"] = json.loads(item.pop("output_json")) if item.get("output_json") else None
            result.append(item)
        return result

    def complete_minute_cycle(
        self,
        cycle_id: str,
        state: str,
        completed_skill_count: int,
        failed_skill_count: int,
        recommendation: dict[str, Any] | None,
        receipt_sha256: str | None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        if state not in {"COMPLETED", "DEGRADED", "FAILED"}:
            raise ValueError("INVALID_CYCLE_STATE")
        payload = json.dumps(recommendation, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if recommendation else None
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE minute_cycles SET completed_at=?,state=?,completed_skill_count=?,failed_skill_count=?,
                  recommendation_json=?,receipt_sha256=?,error_json=? WHERE cycle_id=?
                """,
                (
                    self.now(), state, completed_skill_count, failed_skill_count, payload, receipt_sha256,
                    json.dumps(errors or [], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    cycle_id,
                ),
            )
            if recommendation:
                event_id = str(uuid.uuid4())
                journal_payload = json.dumps(recommendation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                conn.execute(
                    "INSERT INTO runtime_journal(event_id,event_type,aggregate_id,payload_json,created_at) VALUES (?,?,?,?,?)",
                    (event_id, "minute.recommendation.created", cycle_id, journal_payload, self.now()),
                )
                conn.execute(
                    "INSERT INTO outbox(event_id,event_type,payload_json,state,attempts,created_at,sent_at) VALUES (?,?,?,'PENDING',0,?,NULL)",
                    (event_id, "minute.recommendation.created", journal_payload, self.now()),
                )
            conn.execute("COMMIT")

    def fail_stale_cycles(self, max_age_seconds: int = 180) -> int:
        cutoff = (self.clock.now().astimezone(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE minute_cycles SET state='FAILED',completed_at=?,error_json=?
                WHERE state='RUNNING' AND started_at<?
                """,
                (self.now(), json.dumps({"reason": "STALE_CYCLE_RECOVERED"}), cutoff),
            )
            return int(cursor.rowcount)

    def latest_minute_cycle(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM minute_cycles ORDER BY scheduled_for DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["recommendation"] = json.loads(item.pop("recommendation_json")) if item.get("recommendation_json") else None
        item["errors"] = json.loads(item.pop("error_json")) if item.get("error_json") else []
        item["skill_runs"] = self.minute_skill_runs(item["cycle_id"])
        return item

    def recent_minute_cycles(self, limit: int = 60) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM minute_cycles ORDER BY scheduled_for DESC LIMIT ?",
                (min(max(int(limit), 1), 1440),),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["recommendation"] = json.loads(item.pop("recommendation_json")) if item.get("recommendation_json") else None
            item["errors"] = json.loads(item.pop("error_json")) if item.get("error_json") else []
            result.append(item)
        return result

    def latest_unique_recommendation(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT recommendation_json FROM minute_cycles
                WHERE state IN ('COMPLETED','DEGRADED') AND recommendation_json IS NOT NULL
                ORDER BY scheduled_for DESC LIMIT 1
                """
            ).fetchone()
        return json.loads(row["recommendation_json"]) if row else None

    def reliability_weights(self, market: str | None = None) -> dict[str, float]:
        params: list[Any] = []
        sql = "SELECT skill_id,weight FROM skill_reliability"
        if market:
            sql += " WHERE market=?"
            params.append(market.upper())
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {row["skill_id"]: float(row["weight"]) for row in rows}

    def upsert_reliability(
        self,
        skill_id: str,
        market: str,
        horizon_days: int,
        weight: float,
        sample_count: int,
        brier_score: float | None,
        directional_accuracy: float | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO skill_reliability(skill_id,market,horizon_days,weight,sample_count,brier_score,directional_accuracy,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(skill_id,market,horizon_days) DO UPDATE SET
                  weight=excluded.weight,sample_count=excluded.sample_count,brier_score=excluded.brier_score,
                  directional_accuracy=excluded.directional_accuracy,updated_at=excluded.updated_at
                """,
                (skill_id, market.upper(), horizon_days, weight, sample_count, brier_score, directional_accuracy, self.now()),
            )

    def queue_skill_outcome(
        self,
        cycle_id: str,
        skill_id: str,
        signal: dict[str, Any],
        reference_price: float,
    ) -> None:
        from datetime import datetime as _dt
        forecast = _dt.fromisoformat(str(signal["as_of"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        maturity = forecast + timedelta(days=max(1, min(int(signal.get("horizon_days", 20)), 365)))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO skill_outcome_queue(
                  cycle_id,skill_id,symbol,market,forecast_as_of,maturity_at,reference_price,direction,confidence,state,outcome_json
                ) VALUES (?,?,?,?,?,?,?,?,?,'PENDING',NULL)
                """,
                (
                    cycle_id, skill_id, str(signal["symbol"]).upper(), str(signal["market"]).upper(),
                    forecast.isoformat(), maturity.isoformat(), float(reference_price), int(signal["direction"]),
                    float(signal["confidence"]),
                ),
            )

    def matured_outcomes(self, now: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_outcome_queue WHERE state='PENDING' AND maturity_at<=? ORDER BY maturity_at",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def score_outcome(self, row: dict[str, Any], current_price: float, outcome: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE skill_outcome_queue SET state='SCORED',outcome_json=?
                WHERE cycle_id=? AND skill_id=? AND symbol=? AND market=?
                """,
                (
                    json.dumps(outcome, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    row["cycle_id"], row["skill_id"], row["symbol"], row["market"],
                ),
            )

    def scored_outcomes(self, skill_id: str, market: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM skill_outcome_queue
                WHERE skill_id=? AND market=? AND state='SCORED'
                ORDER BY maturity_at DESC LIMIT ?
                """,
                (skill_id, market.upper(), min(max(int(limit), 1), 5000)),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["outcome"] = json.loads(item.pop("outcome_json"))
            result.append(item)
        return result
