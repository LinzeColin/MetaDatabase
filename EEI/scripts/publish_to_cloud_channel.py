#!/usr/bin/env python3
"""S7PDT04: one-way local -> Cloudflare cloud publication channel.

Exports the PUBLICATION SURFACE ONLY from the local production database -
owner-signed published relationships plus provenance-bound authoritative
first-hand facts (SEC/GLEIF), their endpoint entities, the evidence index
(locator + excerpt + official URL), first-hand events and active snapshot
metadata - pushes it to the remote D1 database, and verifies remote row
counts against the export.

Memory contract (shared-box hard cap): the exporter is STREAMING end to end.
Every large table is read through a server-side cursor and rendered into
bounded multi-row INSERT statements; the full surface is never materialised
in memory, so publish RSS stays flat at any coverage scale.

Transports:
- worker-api (containers / OVH box): POST chunked statement batches to the
  public worker's authenticated internal channel (/v1/internal/publish/exec).
  The box holds only a narrow publish token - never an account-level
  Cloudflare credential - and ships no Node/wrangler at all.
- wrangler (local manual runs): render one SQL file and apply it via
  `npx wrangler d1 execute` from apps/cloudflare-public (OAuth session).
Default --transport auto: worker-api when EEI_PUBLISH_URL and
EEI_PUBLISH_TOKEN are set, wrangler otherwise.

Boundary (ROOT_LOCK HR1 / S7PDT04 contract):
- One-way: nothing is ever read back from the cloud into the local DB.
- The publication layer carries published facts, score context and evidence
  index only; candidates, review queues, raw texts and scoring internals
  never leave the machine.
- Raw official-source archives belong in R2; the wrangler transport records
  R2 status honestly, the worker-api transport skips that wrangler-only probe.

Free-tier quota accounting is emitted with every run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402

SCHEMA_VERSION = "eei-cloud-publication-channel-v3-streaming"
TASK_ID = "S7PDT04"
ACCEPTANCE_IDS = ["ACC-S7PDT04"]
D1_DATABASE = "eei-publication"
SCHEMA_FILE = ROOT / "infra" / "cloudflare" / "d1_publication_schema.sql"
PUBLISHED_RULE = "reviewed_relationship_fact_publication"
# Automated, provenance-bound first-hand facts (SEC/GLEIF) publish alongside
# the owner-signed golden vertical. Both carry full evidence rows.
AUTHORITATIVE_RULE = "authoritative_first_hand_ingestion"
PUBLISHED_RULES = (PUBLISHED_RULE, AUTHORITATIVE_RULE)

PUBLISH_URL_ENV = "EEI_PUBLISH_URL"
PUBLISH_TOKEN_ENV = "EEI_PUBLISH_TOKEN"

# EEI-F05: the public surface never carries contact identifiers or internal
# review/signature internals. Qualifiers are reduced to this allowlist at
# export time; owner_actor is replaced by the opaque owner_role that already
# rides in the same payload. Everything else stays local.
PUBLIC_QUALIFIER_ALLOWLIST = (
    "path_role",
    "owner_role",
    "record_mode",
    "reviewed_at",
    "direction_note",
    "decision_set_key",
    "parser_version",
    "structured_fact",
    "source_threshold_policy",
)

D1_FREE_TIER = {
    "storage_gb": 5,
    "rows_read_per_day": 5_000_000,
    "rows_written_per_day": 100_000,
}

# DELETE order: children before parents. INSERT order below is the reverse
# dependency direction (entities/events first). Matches the pre-streaming
# publisher exactly.
DELETE_ORDER = (
    "event_evidence",
    "event_participants",
    "events",
    "relationship_evidence",
    "relationships",
    "entities",
    "snapshot_meta",
    "filing_year_counts",
    "supply_chain_stages",
    "pulse_daily",
    "pulse_composition",
)
COUNT_TABLES = (
    "entities",
    "relationships",
    "relationship_evidence",
    "events",
    "event_participants",
    "event_evidence",
    "snapshot_meta",
    "filing_year_counts",
    "supply_chain_stages",
    "pulse_daily",
    "pulse_composition",
)


def sanitize_public_qualifiers(qualifiers: dict[str, Any] | None) -> dict[str, Any] | None:
    if not qualifiers:
        return None
    public = {k: qualifiers[k] for k in PUBLIC_QUALIFIER_ALLOWLIST if k in qualifiers}
    return public or None


def qualifiers_json(qualifiers: dict[str, Any] | None) -> str | None:
    sanitized = sanitize_public_qualifiers(qualifiers)
    return json.dumps(sanitized, ensure_ascii=False) if sanitized else None


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def insert_statement(
    table: str, columns: tuple[str, ...], rows: list[dict[str, Any]], *, verb: str = "INSERT"
) -> str:
    """One bounded multi-row INSERT (a few hundred rows max, never the table).

    verb='INSERT OR REPLACE' gives an idempotent upsert used by the incremental
    real-time path (every D1 table has a PK, so REPLACE never duplicates).
    """
    col_list = ", ".join(columns)
    values = ",\n".join(
        "(" + ", ".join(sql_quote(row[c]) for c in columns) + ")" for row in rows
    )
    return f"{verb} INTO {table}({col_list}) VALUES\n{values};"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Streaming export: server-side cursors -> bounded INSERT statements.
# ---------------------------------------------------------------------------

ENTITIES_SQL = """
    SELECT id, canonical_name, entity_type, status FROM entities
    WHERE status = 'research_target'
       OR id IN (
            SELECT subject_entity_id FROM relationships WHERE derivation_rule = ANY(%s)
            UNION
            SELECT object_entity_id FROM relationships WHERE derivation_rule = ANY(%s)
       )
"""

RELATIONSHIPS_SQL = """
    SELECT r.id, r.subject_entity_id, r.object_entity_id,
           r.relationship_type, r.relationship_family, r.status,
           r.confidence, r.observed_at, r.created_at, r.qualifiers
    FROM relationships r
    WHERE r.derivation_rule = ANY(%s)
"""

RELATIONSHIP_EVIDENCE_SQL = """
    SELECT re.relationship_id, re.source_document_id, re.role::text,
           re.locator, re.support_excerpt, sd.url, sd.title,
           sd.publisher, sd.document_date
    FROM relationship_evidence re
    JOIN relationships r ON r.id = re.relationship_id
     AND r.derivation_rule = ANY(%s)
    JOIN source_documents sd ON sd.id = re.source_document_id
"""

EVENTS_SQL = """
    SELECT ev.id, ev.event_type, ev.title, ev.status::text,
           ev.announced_at, ev.effective_at, ev.period_start,
           ev.period_end, ev.observed_at, ev.amount, ev.currency,
           ev.amount_kind, ev.description, ev.qualifiers
    FROM events ev
    WHERE ev.derivation_rule = ANY(%s)
      AND ev.status NOT IN ('superseded', 'revoked')
"""

EVENT_PARTICIPANTS_SQL = """
    SELECT ep.event_id, ep.entity_id, e.canonical_name, ep.role, ep.direction
    FROM event_participants ep
    JOIN events ev ON ev.id = ep.event_id
     AND ev.derivation_rule = ANY(%s)
     AND ev.status NOT IN ('superseded', 'revoked')
    JOIN entities e ON e.id = ep.entity_id
"""

EVENT_EVIDENCE_SQL = """
    SELECT ee.event_id, ee.source_document_id, ee.role::text,
           ee.locator, ee.support_excerpt, sd.url, sd.title,
           sd.publisher, sd.document_date
    FROM event_evidence ee
    JOIN events ev ON ev.id = ee.event_id
     AND ev.derivation_rule = ANY(%s)
     AND ev.status NOT IN ('superseded', 'revoked')
    JOIN source_documents sd ON sd.id = ee.source_document_id
"""


def map_entity(r: tuple) -> dict[str, Any]:
    return {
        "id": str(r[0]),
        "canonical_name": r[1],
        "entity_type": r[2],
        "status": r[3],
    }


def map_relationship(r: tuple) -> dict[str, Any]:
    return {
        "id": str(r[0]),
        "subject_entity_id": str(r[1]),
        "object_entity_id": str(r[2]),
        "relationship_type": r[3],
        "relationship_family": r[4],
        "status": r[5],
        "confidence": float(r[6]) if r[6] is not None else None,
        "observed_at": iso(r[7]),
        "published_at": iso(r[8]),
        "qualifiers_json": qualifiers_json(r[9]),
    }


def map_relationship_evidence(r: tuple) -> dict[str, Any]:
    return {
        "relationship_id": str(r[0]),
        "source_document_id": str(r[1]),
        "role": r[2],
        "locator": r[3],
        "support_excerpt": r[4],
        "source_url": r[5],
        "source_title": r[6],
        "publisher": r[7],
        "document_date": iso(r[8]),
    }


def map_event(r: tuple) -> dict[str, Any]:
    return {
        "id": str(r[0]),
        "event_type": r[1],
        "title": r[2],
        "status": r[3],
        "announced_at": iso(r[4]),
        "effective_at": iso(r[5]),
        "period_start": iso(r[6]),
        "period_end": iso(r[7]),
        "observed_at": iso(r[8]),
        "amount": float(r[9]) if r[9] is not None else None,
        "currency": r[10].strip() if r[10] else None,
        "amount_kind": r[11],
        "description": r[12],
        "qualifiers_json": qualifiers_json(r[13]),
    }


def map_event_participant(r: tuple) -> dict[str, Any]:
    return {
        "event_id": str(r[0]),
        "entity_id": str(r[1]),
        "entity_name": r[2],
        "role": r[3],
        "direction": r[4],
    }


def map_event_evidence(r: tuple) -> dict[str, Any]:
    return {
        "event_id": str(r[0]),
        "source_document_id": str(r[1]),
        "role": r[2],
        "locator": r[3],
        "support_excerpt": r[4],
        "source_url": r[5],
        "source_title": r[6],
        "publisher": r[7],
        "document_date": iso(r[8]),
    }


ENTITY_COLUMNS = ("id", "canonical_name", "entity_type", "status")
RELATIONSHIP_COLUMNS = (
    "id", "subject_entity_id", "object_entity_id", "relationship_type",
    "relationship_family", "status", "confidence", "observed_at",
    "published_at", "qualifiers_json",
)
RELATIONSHIP_EVIDENCE_COLUMNS = (
    "relationship_id", "source_document_id", "role", "locator",
    "support_excerpt", "source_url", "source_title", "publisher",
    "document_date",
)
EVENT_COLUMNS = (
    "id", "event_type", "title", "status", "announced_at", "effective_at",
    "period_start", "period_end", "observed_at", "amount", "currency",
    "amount_kind", "description", "qualifiers_json",
)
EVENT_PARTICIPANT_COLUMNS = ("event_id", "entity_id", "entity_name", "role", "direction")
EVENT_EVIDENCE_COLUMNS = (
    "event_id", "source_document_id", "role", "locator", "support_excerpt",
    "source_url", "source_title", "publisher", "document_date",
)


def stream_table(
    conn: Any,
    *,
    cursor_name: str,
    sql: str,
    params: tuple,
    table: str,
    columns: tuple[str, ...],
    mapper: Any,
    chunk: int,
    counts: dict[str, int],
) -> Iterator[str]:
    """Server-side cursor -> bounded multi-row INSERTs. Holds <= chunk rows."""
    buf: list[dict[str, Any]] = []
    with conn.cursor(name=cursor_name) as cur:
        cur.itersize = 1000
        cur.execute(sql, params)
        for raw in cur:
            buf.append(mapper(raw))
            counts[table] += 1
            if len(buf) >= chunk:
                yield insert_statement(table, columns, buf)
                buf = []
    if buf:
        yield insert_statement(table, columns, buf)


def active_analysis_context_payload(conn: Any) -> dict[str, Any] | None:
    context_row = conn.execute(
        """
        SELECT aac.context_key, aac.active_scoring_profile_version_id,
               ds.snapshot_key, aac.active_scoring_run_id, aac.refresh_token,
               aac.refresh_generation, aac.status, aac.activated_at,
               aac.affected_modules,
               sp.profile_key, spv.version, sm.model_key, sm.version
        FROM active_analysis_contexts aac
        JOIN scoring_profile_versions spv
          ON spv.id = aac.active_scoring_profile_version_id
        JOIN scoring_profiles sp ON sp.id = spv.profile_id
        JOIN scoring_models sm ON sm.id = spv.model_id
        LEFT JOIN data_snapshots ds ON ds.id = aac.active_data_snapshot_id
        WHERE aac.context_key = 'global'
        """
    ).fetchone()
    if not context_row:
        return None
    return {
        "schema_version": "active-analysis-context-v1",
        "context_key": context_row[0],
        "active_scoring_profile_version_id": str(context_row[1]),
        "active_data_snapshot_key": context_row[2],
        "active_scoring_run_id": str(context_row[3]) if context_row[3] else None,
        "refresh_token": str(context_row[4]),
        "refresh_generation": int(context_row[5]),
        "status": context_row[6],
        "activated_at": iso(context_row[7]),
        "affected_modules": list(context_row[8] or []),
        "model_version": f"{context_row[11]}@{context_row[12]}",
        "profile_version": f"{context_row[9]}@{context_row[10]}",
    }


def stream_statements(conn: Any, counts: dict[str, int]) -> Iterator[str]:
    """The full publication surface as an ordered statement stream."""
    rules = list(PUBLISHED_RULES)
    for table in DELETE_ORDER:
        yield f"DELETE FROM {table};"
    yield from stream_table(
        conn, cursor_name="pub_entities", sql=ENTITIES_SQL, params=(rules, rules),
        table="entities", columns=ENTITY_COLUMNS, mapper=map_entity, chunk=200,
        counts=counts,
    )
    # events/event_evidence carry free text (titles, SEC excerpts); a smaller
    # chunk keeps every INSERT well under D1's per-statement size cap.
    yield from stream_table(
        conn, cursor_name="pub_events", sql=EVENTS_SQL, params=(rules,),
        table="events", columns=EVENT_COLUMNS, mapper=map_event, chunk=100,
        counts=counts,
    )
    yield from stream_table(
        conn, cursor_name="pub_event_participants", sql=EVENT_PARTICIPANTS_SQL,
        params=(rules,), table="event_participants",
        columns=EVENT_PARTICIPANT_COLUMNS, mapper=map_event_participant,
        chunk=200, counts=counts,
    )
    yield from stream_table(
        conn, cursor_name="pub_event_evidence", sql=EVENT_EVIDENCE_SQL,
        params=(rules,), table="event_evidence", columns=EVENT_EVIDENCE_COLUMNS,
        mapper=map_event_evidence, chunk=100, counts=counts,
    )
    yield from stream_table(
        conn, cursor_name="pub_relationships", sql=RELATIONSHIPS_SQL,
        params=(rules,), table="relationships", columns=RELATIONSHIP_COLUMNS,
        mapper=map_relationship, chunk=200, counts=counts,
    )
    yield from stream_table(
        conn, cursor_name="pub_relationship_evidence",
        sql=RELATIONSHIP_EVIDENCE_SQL, params=(rules,),
        table="relationship_evidence", columns=RELATIONSHIP_EVIDENCE_COLUMNS,
        mapper=map_relationship_evidence, chunk=200, counts=counts,
    )

    # Small reference/meta tables (a handful of rows each; plain fetch).
    #
    # as_of/activated_at are recomputed at publish time. The stored
    # data_snapshots row is a governance record created when the analysis
    # context was activated; publishing it verbatim made the UI announce a
    # "数据版本" that stayed frozen while facts kept arriving daily. The honest
    # answer to "data as of when?" is the newest fact in the published corpus.
    as_of_row = conn.execute(PULSE_DATA_AS_OF_SQL).fetchone()
    data_as_of = (as_of_row[0] if as_of_row and as_of_row[0] else None) or utc_now_iso()
    published_at = utc_now_iso()
    for r in conn.execute(
        """
        SELECT snapshot_key, scope, record_mode, status
        FROM data_snapshots WHERE status = 'active'
        """
    ).fetchall():
        counts["snapshot_meta"] += 1
        yield (
            "INSERT INTO snapshot_meta(snapshot_key, scope, record_mode, status,"
            " as_of, activated_at) VALUES ("
            + ", ".join(
                sql_quote(v)
                for v in (r[0], r[1], r[2], r[3], data_as_of, published_at)
            )
            + ");"
        )
    # S12PB: per-year official filing depth for the cloud vertical timeline.
    # Aggregate counts only - no titles, URLs or raw content leave the machine.
    for r in conn.execute(
        """
        SELECT extract(year FROM sd.document_date)::int AS year,
               count(*)::int AS filings
        FROM source_documents sd
        JOIN sources src ON src.id = sd.source_id AND src.code = 'sec_edgar'
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall():
        counts["filing_year_counts"] += 1
        yield (
            "INSERT INTO filing_year_counts(year, filings) VALUES ("
            f"{int(r[0])}, {int(r[1])});"
        )
    # EEI-F01: static supply-chain stage rail (reference data, no facts).
    for r in conn.execute(
        """
        SELECT stage_id, stage_order, slug, name_zh, name_en,
               default_direction, examples
        FROM supply_chain_stages ORDER BY stage_order
        """
    ).fetchall():
        counts["supply_chain_stages"] += 1
        yield (
            "INSERT INTO supply_chain_stages(stage_id, stage_order, slug, name_zh,"
            " name_en, default_direction, examples) VALUES ("
            + ", ".join(
                sql_quote(v)
                for v in (r[0], int(r[1]), r[2], r[3], r[4], r[5], r[6])
            )
            + ");"
        )

    # EEI-PULSE: daily arrival series + composition + live signals.
    pulse = pulse_rows(conn)
    counts["pulse_daily"] += len(pulse["series"])
    counts["pulse_composition"] += len(pulse["composition"])
    for statement in pulse_statements(pulse, replace=False):
        yield statement

    counts["_meta_rows"] = counts.get("_meta_rows", 0) + 2
    yield (
        "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
        f" ('published_at', {sql_quote(published_at)});"
    )
    yield (
        "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
        f" ('publisher_version', {sql_quote(SCHEMA_VERSION)});"
    )
    # EEI-F01/F02: one atomic analysis-context identity per publish so every
    # cloud screen reads the same snapshot/model identity. Identity fields
    # only - no activated_by contact detail beyond the system tag.
    context = active_analysis_context_payload(conn)
    if context:
        counts["_meta_rows"] = counts.get("_meta_rows", 0) + 1
        yield (
            "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
            " ('active_analysis_context',"
            f" {sql_quote(json.dumps(context, ensure_ascii=False))});"
        )


# ---------------------------------------------------------------------------
# Transports.
# ---------------------------------------------------------------------------


def wrangler(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["npx", "wrangler", *args], capture_output=True, text=True, cwd=str(cwd)
    )


def d1_execute(*, file: Path | None = None, command: str | None = None,
               cwd: Path) -> dict[str, Any]:
    args = ["d1", "execute", D1_DATABASE, "--remote", "--json"]
    if file is not None:
        args += ["--file", str(file)]
    if command is not None:
        args += ["--command", command]
    proc = wrangler(args, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"wrangler d1 execute failed: {proc.stderr[-400:]}")
    # wrangler prefixes --json output with progress lines; slice to the payload.
    stdout = proc.stdout
    start = min(
        (idx for idx in (stdout.find("["), stdout.find("{")) if idx >= 0),
        default=-1,
    )
    if start < 0:
        raise RuntimeError(f"wrangler produced no JSON payload: {stdout[-200:]}")
    return json.loads(stdout[start:])


def wrangler_remote_counts(cwd: Path) -> dict[str, int]:
    # Remote D1 rejects wide compound SELECTs ("too many terms in compound
    # SELECT", SQLITE_ERROR 7500, observed at 6 UNION ALL terms on the first
    # v2 publish), so count each table with its own query.
    counts: dict[str, int] = {}
    for table in COUNT_TABLES:
        result = d1_execute(
            command=f"SELECT count(*) AS n FROM {table}",
            cwd=cwd,
        )
        counts[table] = int(result[0]["results"][0]["n"])
    return counts


def r2_status(cwd: Path) -> dict[str, Any]:
    proc = wrangler(["r2", "bucket", "list"], cwd=cwd)
    if proc.returncode != 0:
        blocked = "10042" in (proc.stderr + proc.stdout)
        return {
            "enabled": False,
            "blocked_on": (
                "R2 must be enabled by the account owner in the Cloudflare "
                "Dashboard (error 10042). Raw-archive leg of the drill is "
                "honestly deferred; publish script supports it once enabled."
                if blocked
                else proc.stderr[-200:]
            ),
        }
    return {"enabled": True, "buckets_output": proc.stdout[-400:]}


def schema_statements() -> list[str]:
    """Split the D1 schema (plain CREATE TABLE/INDEX DDL, no triggers).

    Full-line comments are dropped BEFORE splitting on ';' — a semicolon
    inside a comment must not cut the following statement in half (bit the
    first live run: '-- (aggregate counts only; publication-surface ...)').
    """
    sql_lines = [
        line
        for line in SCHEMA_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    statements: list[str] = []
    for fragment in "\n".join(sql_lines).split(";"):
        if fragment.strip():
            statements.append(fragment.strip() + ";")
    return statements


class WorkerApiTransport:
    """Chunked HTTPS transport to the worker's authenticated publish channel."""

    name = "worker-api"
    max_statements = 300
    max_bytes = 900_000

    def __init__(self, url: str, token: str) -> None:
        import httpx

        self._httpx = httpx
        self._url = url
        self._client = httpx.Client(
            timeout=httpx.Timeout(180.0, connect=20.0),
            headers={
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "user-agent": "eei-publisher/streaming-v3",
            },
        )
        self.requests = 0
        self.bytes_sent = 0

    def close(self) -> None:
        self._client.close()

    def execute(self, statements: list[str]) -> list[dict[str, Any]]:
        body = json.dumps({"statements": statements}, ensure_ascii=False).encode("utf-8")
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client.post(self._url, content=body)
            except self._httpx.HTTPError as exc:
                last_err = exc
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code >= 500:
                last_err = RuntimeError(
                    f"publish channel {resp.status_code}: {resp.text[:200]}"
                )
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code != 200:
                raise RuntimeError(
                    f"publish channel {resp.status_code}: {resp.text[:300]}"
                )
            payload = resp.json()
            if not payload.get("ok"):
                raise RuntimeError(f"publish channel rejected batch: {payload}")
            self.requests += 1
            self.bytes_sent += len(body)
            return payload.get("results", [])
        raise RuntimeError(f"publish channel unreachable after retries: {last_err}")

    def apply_statements(self, statements: Iterable[str]) -> None:
        buf: list[str] = []
        size = 0
        for stmt in statements:
            if buf and (
                len(buf) >= self.max_statements or size + len(stmt) > self.max_bytes
            ):
                self.execute(buf)
                buf, size = [], 0
            buf.append(stmt)
            size += len(stmt)
        if buf:
            self.execute(buf)

    def apply_schema(self) -> None:
        self.apply_statements(schema_statements())

    def remote_counts(self) -> dict[str, int]:
        results = self.execute(
            [f"SELECT count(*) AS n FROM {table}" for table in COUNT_TABLES]
        )
        counts: dict[str, int] = {}
        for table, result in zip(COUNT_TABLES, results, strict=True):
            rows = result.get("rows") or []
            counts[table] = int(rows[0]["n"]) if rows else -1
        return counts


# ---------------------------------------------------------------------------
# Incremental real-time path (used by the recent-filings watcher).
#
# The full publisher DELETEs + re-INSERTs the entire surface (~29k rows) — safe
# once/day but far over D1's 100k-writes/day free tier if run every minute. The
# watcher instead upserts ONLY the rows touched by a just-filed company:
# INSERT OR REPLACE (every D1 table has a PK) so it is idempotent and writes a
# few rows per new filing. No DELETE, so it never disturbs the rest of D1.
# ---------------------------------------------------------------------------

INCR_ENTITIES_SQL = (
    "SELECT id, canonical_name, entity_type, status FROM entities"
    " WHERE id = ANY(%s::uuid[])"
)
INCR_EVENTS_SQL = """
    SELECT DISTINCT ev.id, ev.event_type, ev.title, ev.status::text,
           ev.announced_at, ev.effective_at, ev.period_start, ev.period_end,
           ev.observed_at, ev.amount, ev.currency, ev.amount_kind,
           ev.description, ev.qualifiers
    FROM events ev
    JOIN event_participants ep ON ep.event_id = ev.id
    WHERE ep.entity_id = ANY(%s::uuid[])
      AND ev.derivation_rule = ANY(%s)
      AND ev.status NOT IN ('superseded', 'revoked')
"""
INCR_EVENT_PARTICIPANTS_SQL = """
    SELECT ep.event_id, ep.entity_id, e.canonical_name, ep.role, ep.direction
    FROM event_participants ep
    JOIN entities e ON e.id = ep.entity_id
    WHERE ep.event_id = ANY(%s::uuid[])
"""
INCR_EVENT_EVIDENCE_SQL = """
    SELECT ee.event_id, ee.source_document_id, ee.role::text, ee.locator,
           ee.support_excerpt, sd.url, sd.title, sd.publisher, sd.document_date
    FROM event_evidence ee
    JOIN source_documents sd ON sd.id = ee.source_document_id
    WHERE ee.event_id = ANY(%s::uuid[])
"""


# 列必须与 map_relationship 严格一一对应（D1 relationships 只有这 10 列）：
# id, subject, object, type, family, status, confidence, observed_at,
# published_at(=Postgres 的 created_at), qualifiers_json
# 历史错误：这里曾选 13 列且含 r.effective_from / r.effective_to —— Postgres 的
# relationships 用的是 valid_from / valid_to，这两个列名根本不存在，于是增量发布
# **从上线起就没成功过一次**，每小时报
# `column r.effective_from does not exist`，站点因此长期停在旧数据上。
INCR_RELATIONSHIPS_SQL = """
    SELECT r.id, r.subject_entity_id, r.object_entity_id, r.relationship_type::text,
           r.relationship_family::text, r.status::text, r.confidence,
           r.observed_at, r.created_at, r.qualifiers
    FROM relationships r
    JOIN entities subject ON subject.id = r.subject_entity_id
    JOIN entities object ON object.id = r.object_entity_id
    WHERE r.derivation_rule = ANY(%s)
      AND (r.subject_entity_id = ANY(%s::uuid[]) OR r.object_entity_id = ANY(%s::uuid[]))
"""
INCR_RELATIONSHIP_EVIDENCE_SQL = """
    SELECT re.relationship_id, re.source_document_id, re.role::text, re.locator,
           re.support_excerpt, sd.url, sd.title, sd.publisher, sd.document_date
    FROM relationship_evidence re
    JOIN source_documents sd ON sd.id = re.source_document_id
    WHERE re.relationship_id = ANY(%s::uuid[])
"""


def push_incremental(
    entity_ids: list[str], *, publish_url: str, publish_token: str,
    include_relationships: bool = True,
) -> dict[str, Any]:
    """Upsert only the surface touched by the given entities to live D1.

    Returns {upserted: {table: n}, requests, bytes_sent}. Small by construction.
    """
    if not entity_ids:
        return {"upserted": {}, "requests": 0, "bytes_sent": 0}
    rules = list(PUBLISHED_RULES)
    with connect_database() as conn:
        entities = [
            map_entity(r)
            for r in conn.execute(INCR_ENTITIES_SQL, (entity_ids,)).fetchall()
        ]
        events = [
            map_event(r)
            for r in conn.execute(INCR_EVENTS_SQL, (entity_ids, rules)).fetchall()
        ]
        event_ids = [e["id"] for e in events]
        participants = (
            [map_event_participant(r)
             for r in conn.execute(INCR_EVENT_PARTICIPANTS_SQL, (event_ids,)).fetchall()]
            if event_ids else []
        )
        evidence = (
            [map_event_evidence(r)
             for r in conn.execute(INCR_EVENT_EVIDENCE_SQL, (event_ids,)).fetchall()]
            if event_ids else []
        )
        relationships: list[dict[str, Any]] = []
        relationship_evidence: list[dict[str, Any]] = []
        if include_relationships:
            relationships = [
                map_relationship(r)
                for r in conn.execute(
                    INCR_RELATIONSHIPS_SQL, (rules, entity_ids, entity_ids)
                ).fetchall()
            ]
            rel_ids = [r["id"] for r in relationships]
            if rel_ids:
                relationship_evidence = [
                    map_relationship_evidence(r)
                    for r in conn.execute(
                        INCR_RELATIONSHIP_EVIDENCE_SQL, (rel_ids,)
                    ).fetchall()
                ]

    statements: list[str] = []
    # Entities first (FK-ish ordering mirrors the full publisher); events and
    # relationships before their participants/evidence. All INSERT OR REPLACE
    # (every table has a PK) => idempotent upsert, no DELETE.
    for table, columns, rows, chunk in (
        ("entities", ENTITY_COLUMNS, entities, 200),
        ("events", EVENT_COLUMNS, events, 100),
        ("event_participants", EVENT_PARTICIPANT_COLUMNS, participants, 200),
        ("event_evidence", EVENT_EVIDENCE_COLUMNS, evidence, 100),
        ("relationships", RELATIONSHIP_COLUMNS, relationships, 200),
        ("relationship_evidence", RELATIONSHIP_EVIDENCE_COLUMNS,
         relationship_evidence, 200),
    ):
        for start in range(0, len(rows), chunk):
            statements.append(
                insert_statement(table, columns, rows[start:start + chunk],
                                 verb="INSERT OR REPLACE")
            )
    statements.append(
        "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
        f" ('published_at', {sql_quote(utc_now_iso())});"
    )

    channel = WorkerApiTransport(publish_url, publish_token)
    try:
        channel.apply_statements(statements)
    finally:
        channel.close()
    return {
        "upserted": {
            "entities": len(entities),
            "events": len(events),
            "event_participants": len(participants),
            "event_evidence": len(evidence),
            "relationships": len(relationships),
            "relationship_evidence": len(relationship_evidence),
        },
        "requests": channel.requests,
        "bytes_sent": channel.bytes_sent,
    }


# Rows that actually arrived since a timestamp — NOT "every row belonging to an
# entity that gained a row". The difference matters once the deep-history sweep
# runs: a company whose archive was just walked back to 1994 holds hundreds of
# events, and re-pushing all of them every cycle would cost hundreds of writes
# per company per hour for no new information.
DELTA_EVENTS_SQL = """
    SELECT ev.id, ev.event_type, ev.title, ev.status::text,
           ev.announced_at, ev.effective_at, ev.period_start,
           ev.period_end, ev.observed_at, ev.amount, ev.currency,
           ev.amount_kind, ev.description, ev.qualifiers
    FROM events ev
    WHERE ev.observed_at >= %s AND ev.derivation_rule = ANY(%s)
      AND ev.status NOT IN ('superseded', 'revoked')
    LIMIT %s
"""
# 列必须与 map_relationship 严格一一对应（D1 relationships 只有这 10 列）：
# id, subject, object, type, family, status, confidence, observed_at,
# published_at(=Postgres 的 created_at), qualifiers_json
# 历史错误：这里曾选 13 列且含 r.effective_from / r.effective_to —— Postgres 的
# relationships 用的是 valid_from / valid_to，这两个列名根本不存在，于是增量发布
# **从上线起就没成功过一次**，每小时报
# `column r.effective_from does not exist`，站点因此长期停在旧数据上。
DELTA_RELATIONSHIPS_SQL = """
    SELECT r.id, r.subject_entity_id, r.object_entity_id, r.relationship_type::text,
           r.relationship_family::text, r.status::text, r.confidence,
           r.observed_at, r.created_at, r.qualifiers
    FROM relationships r
    JOIN entities subject ON subject.id = r.subject_entity_id
    JOIN entities object ON object.id = r.object_entity_id
    WHERE r.created_at >= %s AND r.derivation_rule = ANY(%s)
    LIMIT %s
"""


def push_recent(
    since: str, *, publish_url: str, publish_token: str, cap: int = 20000
) -> dict[str, Any]:
    """Upsert exactly the rows that arrived since `since` (ISO).

    This is what makes an hourly collector visible hourly: without it, new
    ownership edges and newly deepened filing history sit in the local
    system-of-record until the next full republish. Scoped to the delta, so the
    write cost tracks what actually arrived rather than the size of the
    entities it arrived for.
    """
    rules = list(PUBLISHED_RULES)
    with connect_database() as conn:
        events = [
            map_event(r)
            for r in conn.execute(DELTA_EVENTS_SQL, (since, rules, cap)).fetchall()
        ]
        event_ids = [e["id"] for e in events]
        participants = (
            [map_event_participant(r)
             for r in conn.execute(INCR_EVENT_PARTICIPANTS_SQL, (event_ids,)).fetchall()]
            if event_ids else []
        )
        evidence = (
            [map_event_evidence(r)
             for r in conn.execute(INCR_EVENT_EVIDENCE_SQL, (event_ids,)).fetchall()]
            if event_ids else []
        )
        relationships = [
            map_relationship(r)
            for r in conn.execute(DELTA_RELATIONSHIPS_SQL, (since, rules, cap)).fetchall()
        ]
        rel_ids = [r["id"] for r in relationships]
        relationship_evidence = (
            [map_relationship_evidence(r)
             for r in conn.execute(INCR_RELATIONSHIP_EVIDENCE_SQL, (rel_ids,)).fetchall()]
            if rel_ids else []
        )
        # Endpoint entities for whatever we are about to push, so a brand-new
        # company never lands as an event with a dangling participant. One row
        # each, and INSERT OR REPLACE keeps it idempotent.
        entity_ids = sorted(
            {p["entity_id"] for p in participants}
            | {r["subject_entity_id"] for r in relationships}
            | {r["object_entity_id"] for r in relationships}
        )
        entities = (
            [map_entity(r)
             for r in conn.execute(INCR_ENTITIES_SQL, (entity_ids,)).fetchall()]
            if entity_ids else []
        )

    if not (events or relationships):
        return {"upserted": {}, "requests": 0, "bytes_sent": 0, "delta_rows": 0}

    statements: list[str] = []
    for table, columns, rows, chunk in (
        ("entities", ENTITY_COLUMNS, entities, 200),
        ("events", EVENT_COLUMNS, events, 100),
        ("event_participants", EVENT_PARTICIPANT_COLUMNS, participants, 200),
        ("event_evidence", EVENT_EVIDENCE_COLUMNS, evidence, 100),
        ("relationships", RELATIONSHIP_COLUMNS, relationships, 200),
        ("relationship_evidence", RELATIONSHIP_EVIDENCE_COLUMNS,
         relationship_evidence, 200),
    ):
        for start in range(0, len(rows), chunk):
            statements.append(
                insert_statement(table, columns, rows[start:start + chunk],
                                 verb="INSERT OR REPLACE")
            )
    statements.append(
        "INSERT OR REPLACE INTO publication_meta(key, value) VALUES"
        f" ('published_at', {sql_quote(utc_now_iso())});"
    )

    channel = WorkerApiTransport(publish_url, publish_token)
    try:
        channel.apply_statements(statements)
    finally:
        channel.close()
    upserted = {
        "entities": len(entities),
        "events": len(events),
        "event_participants": len(participants),
        "event_evidence": len(evidence),
        "relationships": len(relationships),
        "relationship_evidence": len(relationship_evidence),
    }
    return {
        "upserted": upserted,
        "delta_rows": sum(upserted.values()),
        "capped": len(events) >= cap or len(relationships) >= cap,
        "requests": channel.requests,
        "bytes_sent": channel.bytes_sent,
    }


# ---------------------------------------------------------------------------
# EEI-PULSE: the "is anything actually arriving" surface.
# ---------------------------------------------------------------------------

# Daily arrival series, derived straight from the ingestion timestamps we
# already store, so the growth curve is real history — no metrics table to
# migrate, backfill or keep in sync.
PULSE_ENTITIES_DAILY_SQL = """
    SELECT to_char(date(created_at), 'YYYY-MM-DD') AS day, count(*)::int
    FROM entities
    WHERE status = 'research_target'
       OR id IN (
            SELECT subject_entity_id FROM relationships WHERE derivation_rule = ANY(%s)
            UNION
            SELECT object_entity_id FROM relationships WHERE derivation_rule = ANY(%s)
       )
    GROUP BY 1
"""
PULSE_RELATIONSHIPS_DAILY_SQL = """
    SELECT to_char(date(created_at), 'YYYY-MM-DD') AS day, count(*)::int
    FROM relationships WHERE derivation_rule = ANY(%s) GROUP BY 1
"""
PULSE_EVENTS_DAILY_SQL = """
    SELECT to_char(date(observed_at), 'YYYY-MM-DD') AS day, count(*)::int
    FROM events
    WHERE derivation_rule = ANY(%s) AND status NOT IN ('superseded', 'revoked')
    GROUP BY 1
"""
PULSE_EVENT_TYPES_SQL = """
    SELECT event_type::text, count(*)::int FROM events
    WHERE derivation_rule = ANY(%s) AND status NOT IN ('superseded', 'revoked')
    GROUP BY 1 ORDER BY 2 DESC
"""
PULSE_RELATIONSHIP_FAMILIES_SQL = """
    SELECT relationship_family::text, count(*)::int FROM relationships
    WHERE derivation_rule = ANY(%s) GROUP BY 1 ORDER BY 2 DESC
"""
PULSE_SOURCES_SQL = """
    SELECT src.code, src.name,
           count(*)::int AS documents,
           to_char(max(sd.retrieved_at), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_seen
    FROM source_documents sd
    JOIN sources src ON src.id = sd.source_id
    GROUP BY 1, 2 ORDER BY 3 DESC
"""
# The newest fact we hold — the honest answer to "data as of when?".
PULSE_DATA_AS_OF_SQL = """
    SELECT to_char(max(t), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') FROM (
        SELECT max(observed_at) t FROM events
        UNION ALL SELECT max(observed_at) FROM relationships
        UNION ALL SELECT max(updated_at) FROM entities
    ) s
"""


def _daily_map(conn: Any, sql: str, params: tuple) -> dict[str, int]:
    return {row[0]: int(row[1]) for row in conn.execute(sql, params).fetchall() if row[0]}


def pulse_rows(conn: Any) -> dict[str, Any]:
    """Compute the full pulse payload from the local system of record."""
    rules = list(PUBLISHED_RULES)
    ents = _daily_map(conn, PULSE_ENTITIES_DAILY_SQL, (rules, rules))
    rels = _daily_map(conn, PULSE_RELATIONSHIPS_DAILY_SQL, (rules,))
    evs = _daily_map(conn, PULSE_EVENTS_DAILY_SQL, (rules,))

    days = sorted(set(ents) | set(rels) | set(evs))
    series: list[dict[str, Any]] = []
    ce = cr = cv = 0
    for day in days:
        de, dr, dv = ents.get(day, 0), rels.get(day, 0), evs.get(day, 0)
        ce += de
        cr += dr
        cv += dv
        series.append({
            "day": day, "entities": ce, "relationships": cr, "events": cv,
            "entities_added": de, "relationships_added": dr, "events_added": dv,
        })

    composition: list[dict[str, Any]] = []
    for kind, sql in (("event_type", PULSE_EVENT_TYPES_SQL),
                      ("relationship_family", PULSE_RELATIONSHIP_FAMILIES_SQL)):
        for bucket, count in conn.execute(sql, (rules,)).fetchall():
            if bucket:
                composition.append({"bucket_kind": kind, "bucket": str(bucket),
                                    "label": None, "count": int(count)})
    for code, name, documents, last_seen in conn.execute(PULSE_SOURCES_SQL).fetchall():
        composition.append({
            "bucket_kind": "source", "bucket": str(code),
            "label": json.dumps({"name": name, "last_seen_at": last_seen},
                                ensure_ascii=False),
            "count": int(documents),
        })

    row = conn.execute(PULSE_DATA_AS_OF_SQL).fetchone()
    data_as_of = row[0] if row and row[0] else None
    return {"series": series, "composition": composition, "data_as_of": data_as_of}


PULSE_DAILY_COLUMNS = ("day", "entities", "relationships", "events",
                       "entities_added", "relationships_added", "events_added")
PULSE_COMPOSITION_COLUMNS = ("bucket_kind", "bucket", "label", "count")


def pulse_statements(payload: dict[str, Any], *, replace: bool = True) -> list[str]:
    """SQL for the pulse tables. Tiny: one row per day plus a few buckets."""
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    out: list[str] = []
    series, composition = payload["series"], payload["composition"]
    for start in range(0, len(series), 200):
        out.append(insert_statement("pulse_daily", PULSE_DAILY_COLUMNS,
                                    series[start:start + 200], verb=verb))
    for start in range(0, len(composition), 200):
        out.append(insert_statement("pulse_composition", PULSE_COMPOSITION_COLUMNS,
                                    composition[start:start + 200], verb=verb))
    latest = series[-1] if series else {"entities": 0, "relationships": 0, "events": 0}
    now = utc_now_iso()
    for key, value in (
        ("totals", json.dumps({k: latest.get(k, 0)
                               for k in ("entities", "relationships", "events")})),
        ("data_as_of", payload.get("data_as_of") or now),
        ("last_full_publish_at", now),
    ):
        out.append(
            "INSERT OR REPLACE INTO pulse_now(key, value, updated_at) VALUES ("
            f"{sql_quote(key)}, {sql_quote(value)}, {sql_quote(now)});"
        )
    return out


def push_pulse(*, publish_url: str, publish_token: str) -> dict[str, Any]:
    """Recompute and upsert the pulse tables only (cheap: ~1 request)."""
    with connect_database() as conn:
        payload = pulse_rows(conn)
    data_as_of = payload.get("data_as_of") or utc_now_iso()
    statements = [
        "DELETE FROM pulse_composition;",
        *pulse_statements(payload),
        # The header's "数据版本" reads snapshot_meta.as_of. Only the full
        # republish rewrites that table, so between republishes the site showed
        # a date up to a day stale — and before this whole change, ten days
        # stale. Refresh it on every pulse beat instead, so the date on screen
        # is never more than one cycle behind the newest fact we hold.
        "UPDATE snapshot_meta SET as_of = "
        f"{sql_quote(data_as_of)}, activated_at = {sql_quote(utc_now_iso())}"
        " WHERE status = 'active';",
    ]
    channel = WorkerApiTransport(publish_url, publish_token)
    try:
        channel.apply_statements(statements)
    finally:
        channel.close()
    return {"days": len(payload["series"]), "buckets": len(payload["composition"]),
            "requests": channel.requests, "bytes_sent": channel.bytes_sent}


def push_heartbeat(
    *, publish_url: str, publish_token: str, collector: str, detail: dict[str, Any]
) -> None:
    """One-row liveness beat. Called every collector poll so a stalled pipeline
    shows up within a minute instead of at the next full publish."""
    now = utc_now_iso()
    payload = json.dumps({"collector": collector, "at": now, **detail},
                         ensure_ascii=False)
    channel = WorkerApiTransport(publish_url, publish_token)
    try:
        channel.apply_statements([
            "INSERT OR REPLACE INTO pulse_now(key, value, updated_at) VALUES ("
            f"{sql_quote('heartbeat:' + collector)}, {sql_quote(payload)},"
            f" {sql_quote(now)});"
        ])
    finally:
        channel.close()


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--sql-out", type=Path, default=None,
        help="SQL artifact path (required for the wrangler transport; the"
             " worker-api transport streams and writes no file)",
    )
    parser.add_argument("--apply", action="store_true", help="push to remote D1")
    parser.add_argument(
        "--transport", choices=("auto", "wrangler", "worker-api"), default="auto",
        help="auto = worker-api when EEI_PUBLISH_URL/EEI_PUBLISH_TOKEN are set",
    )
    args = parser.parse_args()

    publish_url = os.environ.get(PUBLISH_URL_ENV, "").strip()
    publish_token = os.environ.get(PUBLISH_TOKEN_ENV, "").strip()
    transport = args.transport
    if transport == "auto":
        transport = "worker-api" if (publish_url and publish_token) else "wrangler"

    cf_dir = ROOT / "apps" / "cloudflare-public"
    counts: dict[str, int] = {table: 0 for table in COUNT_TABLES}
    sql_statements = 0
    sql_bytes = 0
    worker_api_stats: dict[str, int] | None = None
    remote: dict[str, int] | None = None
    sql_file: str | None = None

    def counted(gen: Iterator[str]) -> Iterator[str]:
        nonlocal sql_statements, sql_bytes
        for stmt in gen:
            sql_statements += 1
            sql_bytes += len(stmt) + 1
            yield stmt

    if transport == "wrangler":
        if args.sql_out is None:
            parser.error("--sql-out is required for the wrangler transport")
        args.sql_out.parent.mkdir(parents=True, exist_ok=True)
        with connect_database() as conn, args.sql_out.open("w", encoding="utf-8") as f:
            for stmt in counted(stream_statements(conn, counts)):
                f.write(stmt + "\n")
        sql_file = str(args.sql_out)
        if args.apply:
            d1_execute(file=SCHEMA_FILE, cwd=cf_dir)
            d1_execute(file=args.sql_out, cwd=cf_dir)
            remote = wrangler_remote_counts(cf_dir)
        r2 = r2_status(cf_dir)
    else:
        if args.apply and not (publish_url and publish_token):
            parser.error(
                f"worker-api transport needs {PUBLISH_URL_ENV} and {PUBLISH_TOKEN_ENV}"
            )
        channel: WorkerApiTransport | None = None
        try:
            with connect_database() as conn:
                stream = counted(stream_statements(conn, counts))
                if args.apply:
                    channel = WorkerApiTransport(publish_url, publish_token)
                    channel.apply_schema()
                    channel.apply_statements(stream)
                else:
                    for _ in stream:
                        pass
            if channel is not None:
                remote = channel.remote_counts()
                worker_api_stats = {
                    "requests": channel.requests,
                    "bytes_sent": channel.bytes_sent,
                }
        finally:
            if channel is not None:
                channel.close()
        # R2 probing is a wrangler-only leg; recorded honestly as skipped.
        r2 = {"enabled": None, "skipped": "worker-api transport (wrangler-only probe)"}

    local_counts = {table: counts[table] for table in COUNT_TABLES}
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now_iso(),
        "d1_database": D1_DATABASE,
        "transport": transport,
        "publication_boundary": {
            "included": [
                "owner-signed published relationships",
                "endpoint entities",
                "evidence index (locator + excerpt + official URL)",
                "first-hand published events + participants + event evidence"
                " (Capital River / vertical timeline)",
                "active snapshot metadata",
                "per-year official filing counts (aggregates only)",
                "supply-chain stage reference rail (static, no facts)",
                "active analysis-context identity (allowlisted, no contacts)",
            ],
            "excluded": [
                "relationship candidates and review queues",
                "raw source texts and archives (R2 scope)",
                "scoring internals and model parameters",
                "background jobs / scheduler state",
                "contact identifiers and review/signature internals"
                " (EEI-F05 qualifier allowlist)",
            ],
            "direction": "one-way local->cloud; no cloud read-back",
        },
        "local_export_counts": local_counts,
        "sql_file": sql_file,
        "sql_statements": sql_statements,
        "applied": bool(args.apply),
    }
    if worker_api_stats is not None:
        report["worker_api"] = worker_api_stats
    if args.apply and remote is not None:
        report["remote_counts"] = remote
        report["count_parity"] = {
            table: remote.get(table) == local_counts[table] for table in local_counts
        }
        report["drill_passed"] = all(report["count_parity"].values())
    report["r2"] = r2
    meta_rows = counts.get("_meta_rows", 0)
    rows_written = sum(local_counts.values()) + meta_rows
    report["free_tier_quota_accounting"] = {
        "d1_free_tier": D1_FREE_TIER,
        "rows_written_this_publish": rows_written,
        "daily_write_budget_used_pct": round(
            rows_written / D1_FREE_TIER["rows_written_per_day"] * 100, 4
        ),
        "estimated_publication_size_kb": round(sql_bytes / 1024, 1),
        "headroom_note": (
            "Publication surface is orders of magnitude inside the free tier; "
            "even a 1000x larger fact base stays under daily write limits with "
            "one full republish per day."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "applied": report["applied"],
                "transport": transport,
                "local": local_counts,
                "remote": report.get("remote_counts"),
                "drill_passed": report.get("drill_passed"),
                "r2_enabled": report["r2"]["enabled"],
            },
            indent=2,
        )
    )
    if args.apply and not report.get("drill_passed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
