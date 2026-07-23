"""Shared helpers for authoritative first-hand ingestion.

Design goals:
- First-hand only: every fact traces to an official registry/filing URL.
- Idempotent: deterministic entity/relationship/event ids so re-runs converge.
- Provenance-bound: relationships and events carry evidence rows joined to a
  source_documents row (the official source URL + content hash).
- Standalone: safe to run as an unattended background job; reuses the app's
  DB helper but keeps its own small, rate-limited SEC HTTP client.

Provenance note: HTTP discipline (host allowlist, <=10 req/s ceiling, contact
User-Agent) mirrors apps/api/app/ingest/sec_client.py; kept local here so the
batch collectors have no async/app coupling.
"""
from __future__ import annotations

import hashlib
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]  # .../EEI
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

from scripts.db_tools import connect_database, load_env_file  # noqa: E402

# Deterministic namespace for EEI entity ids derived from first-hand keys.
EEI_ENTITY_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://eei.linzezhang.com/entity")
EEI_FACT_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://eei.linzezhang.com/fact")

SEC_ALLOWED_HOSTS = frozenset({"data.sec.gov", "www.sec.gov"})
# SEC fair-access ceiling is 10 req/s; stay comfortably under it.
SEC_MIN_INTERVAL_SECONDS = 1.0 / 6.0

# derivation_rule tag marking automated, provenance-bound first-hand facts.
AUTHORITATIVE_RULE = "authoritative_first_hand_ingestion"
AUTHORITATIVE_VERSION = "auth-v1"


def sec_user_agent() -> str:
    load_env_file()
    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        # A contact email is mandatory for SEC fair access; never hardcode a
        # personal address in this (public) repo - operators set it in .env.
        raise RuntimeError(
            "SEC_USER_AGENT must be set to a descriptive User-Agent that "
            "includes a contact email (SEC fair-access policy)."
        )
    return ua


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_cik(value: str | int) -> str:
    raw = str(value).strip()
    if raw.upper().startswith("CIK"):
        raw = raw[3:]
    if not raw.isascii() or not raw.isdigit():
        raise ValueError(f"CIK must be digits: {value!r}")
    if len(raw) > 10:
        raise ValueError(f"CIK too long: {value!r}")
    return raw.zfill(10)


def entity_uuid(cik10: str) -> str:
    return str(uuid.uuid5(EEI_ENTITY_NS, f"cik:{cik10}"))


def fact_uuid(*parts: Any) -> str:
    return str(uuid.uuid5(EEI_FACT_NS, "|".join("" if p is None else str(p) for p in parts)))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class SecClient:
    """Minimal rate-limited SEC JSON client (host-allowlisted, retrying)."""

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or sec_user_agent()
        self._last = 0.0
        self._client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
        )

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < SEC_MIN_INTERVAL_SECONDS:
            time.sleep(SEC_MIN_INTERVAL_SECONDS - gap)
        self._last = time.monotonic()

    def get(self, url: str, *, retries: int = 5) -> tuple[int, bytes]:
        host = httpx.URL(url).host
        if host not in SEC_ALLOWED_HOSTS:
            raise ValueError(f"host not allowlisted: {host}")
        last_status = 0
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self._client.get(url)
            except httpx.HTTPError:
                time.sleep(1.0 * (attempt + 1))
                continue
            last_status = resp.status_code
            if resp.status_code in (429, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            return resp.status_code, resp.content
        return last_status, b""

    def get_json(self, url: str, *, retries: int = 5) -> Any | None:
        status, body = self.get(url, retries=retries)
        if status != 200 or not body:
            return None
        import json

        try:
            return json.loads(body)
        except ValueError:
            return None

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# DB upsert helpers (all idempotent)
# ---------------------------------------------------------------------------

def source_id_for(conn, code: str) -> str:
    row = conn.execute("SELECT id FROM sources WHERE code = %s", (code,)).fetchone()
    if not row:
        raise RuntimeError(f"source code not found: {code}")
    return str(row[0])


def resolve_entity_id(conn, cik10: str) -> str:
    """Reuse an existing entity if one already carries this CIK; else mint."""
    row = conn.execute(
        "SELECT entity_id FROM entity_identifiers WHERE scheme = 'cik' AND value = %s",
        (cik10,),
    ).fetchone()
    return str(row[0]) if row else entity_uuid(cik10)


def upsert_entity(
    conn,
    entity_id: str,
    canonical_name: str,
    *,
    entity_type: str = "legal_entity",
    status: str = "research_target",
    jurisdiction: str | None = None,
    description: str | None = None,
    overwrite_name: bool = False,
) -> None:
    if overwrite_name:
        conn.execute(
            """
            INSERT INTO entities
              (id, canonical_name, entity_type, status, jurisdiction, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
              SET canonical_name = EXCLUDED.canonical_name,
                  jurisdiction = COALESCE(EXCLUDED.jurisdiction, entities.jurisdiction),
                  updated_at = now()
            """,
            (entity_id, canonical_name, entity_type, status, jurisdiction, description),
        )
    else:
        conn.execute(
            """
            INSERT INTO entities
              (id, canonical_name, entity_type, status, jurisdiction, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
              SET status = CASE WHEN entities.status = 'fixture'
                                THEN EXCLUDED.status ELSE entities.status END,
                  jurisdiction = COALESCE(entities.jurisdiction, EXCLUDED.jurisdiction),
                  updated_at = now()
            """,
            (entity_id, canonical_name, entity_type, status, jurisdiction, description),
        )


def upsert_identifier(conn, entity_id: str, scheme: str, value: str, issuer: str) -> None:
    if value is None or str(value).strip() == "":
        return
    conn.execute(
        """
        INSERT INTO entity_identifiers (entity_id, scheme, value, issuer)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (scheme, value) DO NOTHING
        """,
        (entity_id, scheme, str(value), issuer),
    )


def upsert_source_document(
    conn,
    *,
    source_id: str,
    external_id: str,
    url: str,
    title: str,
    publisher: str,
    document_date: datetime | None,
    content_hash: str,
    media_type: str = "application/json",
    parser_version: str = AUTHORITATIVE_VERSION,
) -> str:
    row = conn.execute(
        """
        INSERT INTO source_documents
          (source_id, external_id, url, title, publisher, document_date,
           observed_at, content_hash, media_type, parser_version)
        VALUES (%s, %s, %s, %s, %s, %s, now(), %s, %s, %s)
        ON CONFLICT (source_id, external_id, content_hash) DO UPDATE
          SET title = EXCLUDED.title
        RETURNING id
        """,
        (source_id, external_id, url, title, publisher, document_date,
         content_hash, media_type, parser_version),
    ).fetchone()
    return str(row[0])


def insert_relationship(
    conn,
    *,
    subject_id: str,
    object_id: str,
    relationship_type: str,
    relationship_family: str,
    status: str = "reported",
    confidence: float | None = None,
    percentage: float | None = None,
    valid_from: datetime | None = None,
    announced_at: datetime | None = None,
    filed_at: datetime | None = None,
    qualifiers_json: str | None = None,
    evidence_source_document_id: str | None = None,
    evidence_locator: str | None = None,
    evidence_excerpt: str | None = None,
) -> str | None:
    """Insert a provenance-bound relationship. Idempotent by (subject,type,object,source)."""
    rel_id = fact_uuid("rel", subject_id, relationship_type, object_id, evidence_source_document_id)
    inserted = conn.execute(
        """
        INSERT INTO relationships
          (id, subject_entity_id, object_entity_id, relationship_type, relationship_family,
           status, confidence, percentage, valid_from, announced_at, filed_at, observed_at,
           qualifiers, derivation_rule, derivation_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(),
                COALESCE(%s::jsonb, '{}'::jsonb), %s, %s)
        ON CONFLICT (id) DO NOTHING
        RETURNING id
        """,
        (rel_id, subject_id, object_id, relationship_type, relationship_family,
         status, confidence, percentage, valid_from, announced_at, filed_at,
         qualifiers_json, AUTHORITATIVE_RULE, AUTHORITATIVE_VERSION),
    ).fetchone()
    if inserted and evidence_source_document_id:
        conn.execute(
            """
            INSERT INTO relationship_evidence
              (relationship_id, source_document_id, role, locator, support_excerpt)
            VALUES (%s, %s, 'supports', %s, %s)
            ON CONFLICT (relationship_id, source_document_id, role) DO NOTHING
            """,
            (rel_id, evidence_source_document_id, evidence_locator, evidence_excerpt),
        )
    return rel_id if inserted else None


def insert_event(
    conn,
    *,
    event_type: str,
    title: str,
    status: str = "reported",
    announced_at: datetime | None = None,
    effective_at: datetime | None = None,
    amount: float | None = None,
    currency: str | None = None,
    amount_kind: str | None = None,
    description: str | None = None,
    qualifiers_json: str | None = None,
    participants: list[tuple[str, str, str | None]] | None = None,
    evidence_source_document_id: str | None = None,
    evidence_locator: str | None = None,
    evidence_excerpt: str | None = None,
    dedupe_key: str | None = None,
) -> str | None:
    """Insert a provenance-bound event with participants + evidence. Idempotent."""
    event_id = fact_uuid("event", event_type, dedupe_key or title, evidence_source_document_id)
    inserted = conn.execute(
        """
        INSERT INTO events
          (id, event_type, title, status, announced_at, effective_at, observed_at,
           amount, currency, amount_kind, description, qualifiers,
           derivation_rule, derivation_version)
        VALUES (%s, %s, %s, %s, %s, %s, now(), %s, %s, %s, %s,
                COALESCE(%s::jsonb, '{}'::jsonb), %s, %s)
        ON CONFLICT (id) DO NOTHING
        RETURNING id
        """,
        (event_id, event_type, title, status, announced_at, effective_at,
         amount, currency, amount_kind, description, qualifiers_json,
         AUTHORITATIVE_RULE, AUTHORITATIVE_VERSION),
    ).fetchone()
    if not inserted:
        return None
    for entity_id, role, direction in (participants or []):
        conn.execute(
            """
            INSERT INTO event_participants (event_id, entity_id, role, direction)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (event_id, entity_id, role) DO NOTHING
            """,
            (event_id, entity_id, role, direction),
        )
    if evidence_source_document_id:
        conn.execute(
            """
            INSERT INTO event_evidence
              (event_id, source_document_id, role, locator, support_excerpt)
            VALUES (%s, %s, 'supports', %s, %s)
            ON CONFLICT (event_id, source_document_id, role) DO NOTHING
            """,
            (event_id, evidence_source_document_id, evidence_locator, evidence_excerpt),
        )
    return event_id


__all__ = [
    "connect_database",
    "SecClient",
    "AUTHORITATIVE_RULE",
    "normalize_cik",
    "entity_uuid",
    "fact_uuid",
    "sha256_hex",
    "utcnow",
    "source_id_for",
    "resolve_entity_id",
    "upsert_entity",
    "upsert_identifier",
    "upsert_source_document",
    "insert_relationship",
    "insert_event",
]
