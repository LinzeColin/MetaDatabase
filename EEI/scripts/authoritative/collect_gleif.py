#!/usr/bin/env python3
"""Materialize REAL corporate ownership/structure relationships from GLEIF.

Source (first-hand, free, no API key): the Global Legal Entity Identifier
Foundation (GLEIF) Level-2 relationship data, served from the public JSON:API at
``https://api.gleif.org/api/v1/``. GLEIF is the authoritative operator of the
LEI system; its "direct parent" (accounting-consolidation) relationships are
reported by the entities themselves and validated by LEI issuers, making them a
first-hand, provenance-bound source of who-owns-whom.

What this connector does, per US public company already in our universe
(``entities`` carrying a ``ticker`` identifier, status ``research_target``):

1. Resolve the company's LEI by its canonical name (``filter[entity.legalName]``
   first, ``filter[fulltext]`` as fallback). Conservative matcher: only accept an
   ACTIVE / ISSUED record whose normalized name closely matches; prefer US
   jurisdiction. No confident match -> skip and log (never guess).
2. Tag our existing entity with ``lei`` + ``lei_legal_name`` identifiers.
3. Fetch the company's GLEIF ``direct-parent`` and ``direct-children`` and
   materialize, for each edge, a symmetric pair of taxonomy relationships:
     - ``subsidiary_of``  (corporate_structure): child  -> parent
     - ``voting_control`` (ownership_control):   parent -> child
   Every relationship is anchored to a ``source_documents`` row that records the
   exact GLEIF endpoint URL + a content hash of the fetched relationship data.

Design guarantees (mirrors scripts/authoritative/common.py):
- First-hand: every fact traces to an official GLEIF endpoint URL.
- Idempotent / rerunnable: deterministic entity + relationship + source-document
  ids, all writes are ON CONFLICT upserts, so re-runs over the same GLEIF golden
  copy converge without creating duplicates.
- Provenance-bound: relationships join to relationship_evidence -> source_documents.
- Robust: one company failing never aborts the batch; GLEIF is rate-limited
  (~4 req/s) and retried on 429/503; HTTP 404 (no parent/children) is empty,
  not an error.

Usage:
  python -m scripts.authoritative.collect_gleif [--limit N] [--offset N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import httpx

from scripts.authoritative.common import (
    connect_database,
    fact_uuid,
    insert_relationship,
    sec_user_agent,
    sha256_hex,
    source_id_for,
    upsert_entity,
    upsert_identifier,
    upsert_source_document,
    utcnow,
)

# ---------------------------------------------------------------------------
# GLEIF API constants
# ---------------------------------------------------------------------------
GLEIF_BASE = "https://api.gleif.org/api/v1/"
GLEIF_ALLOWED_HOSTS = frozenset({"api.gleif.org"})
# GLEIF asks for polite use; there is no published hard ceiling, so we stay
# comfortably slow at ~4 requests/second.
GLEIF_MIN_INTERVAL_SECONDS = 0.25
GLEIF_SOURCE_CODE = "gleif"
GLEIF_SOURCE_NAME = "Global LEI Foundation"
GLEIF_BASE_URL = "https://api.gleif.org/"
GLEIF_PUBLISHER = "Global LEI Foundation"

# Confidence for GLEIF direct/accounting-consolidation parent relationships.
GLEIF_CONFIDENCE = 0.9

# Name-match acceptance threshold on the normalized-core similarity ratio.
# Calibrated against real company names: correct matches score ~1.0, noise <=0.75.
NAME_MATCH_THRESHOLD = 0.90
# Small additive bonus so that, among equally-similar names, a US-jurisdiction
# record wins for our US-listed universe (e.g. "TESLA, INC." US-TX over "TESLA" FR).
US_JURISDICTION_BONUS = 0.05

# v1 caps to keep a single run bounded.
CHILDREN_CAP = 500
CHILDREN_PAGE_SIZE = 100

# Corporate-form / stopword tokens dropped before name comparison. They are pure
# noise for matching ("Apple Inc." vs "APPLE INC." vs "Apple Incorporated").
CORP_SUFFIX_TOKENS = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "ltd", "limited", "llc", "lc", "lp", "llp", "plc", "sa", "ag", "nv", "bv",
    "gmbh", "spa", "srl", "pte", "pty", "kk", "ab", "as", "oy", "holdings",
    "holding", "group", "grp", "the", "and", "class", "cl", "trust",
})

# Companies to enrich: one row per real public company (distinct entity). The
# raw join on scheme='ticker' yields duplicate rows for multi-class tickers
# (e.g. ONCH / ONCHU / ONCHW), so we GROUP BY the entity to process each company
# exactly once; the ticker is kept only for human-readable logging.
COMPANY_QUERY = """
    SELECT e.id, e.canonical_name, min(ei.value) AS ticker
    FROM entities e
    JOIN entity_identifiers ei
      ON ei.entity_id = e.id AND ei.scheme = 'ticker'
    WHERE e.status = 'research_target'
    GROUP BY e.id, e.canonical_name
    ORDER BY e.canonical_name
    LIMIT %s OFFSET %s
"""


# ---------------------------------------------------------------------------
# GLEIF HTTP client (rate-limited, retrying, host-allowlisted)
# ---------------------------------------------------------------------------
class GleifClient:
    """Minimal polite JSON:API client for GLEIF (no key required)."""

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or sec_user_agent()  # reuse the contact UA
        self._last = 0.0
        self._client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/vnd.api+json",
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < GLEIF_MIN_INTERVAL_SECONDS:
            time.sleep(GLEIF_MIN_INTERVAL_SECONDS - gap)
        self._last = time.monotonic()

    def get(self, url: str, *, params: dict[str, Any] | None = None,
            retries: int = 5) -> tuple[int, bytes]:
        """GET a GLEIF URL. Returns (status_code, raw_body_bytes).

        ``url`` may be a bare endpoint (combined with ``params``) or a fully
        formed ``links.next`` URL (pass ``params=None``). Retries transient
        transport errors and 429/503 with linear backoff.
        """
        host = httpx.URL(url).host
        if host not in GLEIF_ALLOWED_HOSTS:
            raise ValueError(f"host not allowlisted: {host}")
        last_status = 0
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError:
                time.sleep(1.0 * (attempt + 1))
                continue
            last_status = resp.status_code
            if resp.status_code in (429, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            return resp.status_code, resp.content
        return last_status, b""

    def get_json(self, url: str, *, params: dict[str, Any] | None = None,
                 retries: int = 5) -> tuple[int, Any | None]:
        status, body = self.get(url, params=params, retries=retries)
        if status != 200 or not body:
            return status, None
        try:
            return status, json.loads(body)
        except ValueError:
            return status, None

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Name normalization + matching
# ---------------------------------------------------------------------------
def _normalize_core(name: str) -> str:
    """Lowercase ASCII, strip punctuation + corporate suffixes, collapse spaces."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"/[a-z]{2}/", " ", s)          # SEC state suffixes: /MD/ /DE/
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t and t not in CORP_SUFFIX_TOKENS]
    core = " ".join(tokens)
    if core:
        return core
    # All tokens were suffixes/stopwords (rare); fall back to the bare cleaned form.
    return " ".join(t for t in s.split() if t)


def _match_ratio(query_name: str, candidate_name: str) -> float:
    return SequenceMatcher(
        None, _normalize_core(query_name), _normalize_core(candidate_name)
    ).ratio()


def _legal_name(entity: dict[str, Any]) -> str:
    """GLEIF legalName is usually {'name': ..., 'language': ...}; be defensive."""
    ln = entity.get("legalName")
    if isinstance(ln, dict):
        return str(ln.get("name") or "").strip()
    if isinstance(ln, str):
        return ln.strip()
    return ""


def _bic_values(attributes: dict[str, Any]) -> list[str]:
    """GLEIF ``attributes.bic`` may be a list, a string, or null."""
    bic = attributes.get("bic")
    if isinstance(bic, list):
        return [str(b).strip() for b in bic if str(b).strip()]
    if isinstance(bic, str) and bic.strip():
        return [bic.strip()]
    return []


def _record_view(record: dict[str, Any]) -> dict[str, Any] | None:
    """Flatten a GLEIF lei-record into the fields we persist."""
    attrs = record.get("attributes") or {}
    lei = attrs.get("lei")
    if not lei:
        return None
    entity = attrs.get("entity") or {}
    return {
        "lei": str(lei),
        "legal_name": _legal_name(entity),
        "jurisdiction": (entity.get("jurisdiction") or "").strip() or None,
        "bic": _bic_values(attrs),
    }


def resolve_lei(client: GleifClient, company_name: str) -> tuple[dict[str, Any] | None, str]:
    """Resolve a company name to its best GLEIF record.

    Returns (match_view_or_None, note). ``match_view`` carries lei / legal_name /
    jurisdiction / bic / sim. ``note`` explains a skip for logging.
    """
    candidates: list[dict[str, Any]] = []
    for filter_key in ("filter[entity.legalName]", "filter[fulltext]"):
        _, payload = client.get_json(
            GLEIF_BASE + "lei-records",
            params={filter_key: company_name, "page[size]": 5},
        )
        data = (payload or {}).get("data") or []
        if data:
            candidates = data
            break

    if not candidates:
        return None, "no GLEIF candidates"

    best: tuple[float, float, bool, dict[str, Any]] | None = None  # (effective, sim, is_us, view)
    for record in candidates:
        attrs = record.get("attributes") or {}
        entity = attrs.get("entity") or {}
        registration = attrs.get("registration") or {}
        # Only accept live, issued LEIs.
        if entity.get("status") != "ACTIVE" or registration.get("status") != "ISSUED":
            continue
        view = _record_view(record)
        if not view:
            continue
        sim = _match_ratio(company_name, view["legal_name"])
        is_us = (view["jurisdiction"] or "").upper().startswith("US")
        effective = sim + (US_JURISDICTION_BONUS if is_us else 0.0)
        if best is None or effective > best[0]:
            best = (effective, sim, is_us, view)

    if best is None:
        return None, "no ACTIVE/ISSUED candidate"
    if best[1] < NAME_MATCH_THRESHOLD:
        return None, f"best sim {best[1]:.2f} < {NAME_MATCH_THRESHOLD:.2f}"

    # Short-name precision guard: a very short / numeric core (e.g. "111", "3m")
    # matches coincidentally far too easily (e.g. "111, Inc." vs a Maltese
    # "111 LIMITED"). For our US-listed universe, only trust such a match when the
    # jurisdiction corroborates it (US). Distinctive cores (>=4 alnum chars) are
    # accepted on name similarity alone.
    core_len = len(_normalize_core(company_name).replace(" ", ""))
    if core_len < 4 and not best[2]:
        return None, f"short-name guard (core={core_len} chars, non-US jurisdiction)"

    view = dict(best[3])
    view["sim"] = best[1]
    return view, "ok"


def _fetch_related(
    client: GleifClient, lei: str, endpoint: str
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch direct-parent (single) or direct-children (paginated).

    Returns (list_of_record_views, fetched_ok). ``fetched_ok`` is False only on a
    hard transport failure (so we can distinguish "no relatives" from "couldn't
    ask"); HTTP 404 is a normal empty result.
    """
    if endpoint == "direct-parent":
        status, payload = client.get_json(GLEIF_BASE + f"lei-records/{lei}/direct-parent")
        if status == 404:
            return [], True
        if status != 200 or payload is None:
            return [], False
        data = payload.get("data")
        if not isinstance(data, dict):  # parent endpoint returns a single object
            return [], True
        view = _record_view(data)
        return ([view] if view else []), True

    # direct-children: paginate via links.next, capped.
    views: list[dict[str, Any]] = []
    url: str | None = GLEIF_BASE + f"lei-records/{lei}/direct-children"
    params: dict[str, Any] | None = {"page[size]": CHILDREN_PAGE_SIZE}
    fetched_ok = True
    while url and len(views) < CHILDREN_CAP:
        status, payload = client.get_json(url, params=params)
        params = None  # links.next carries its own query string
        if status == 404:
            break
        if status != 200 or payload is None:
            fetched_ok = fetched_ok and not views  # partial page = still usable
            break
        for record in payload.get("data") or []:
            view = _record_view(record)
            if view:
                views.append(view)
            if len(views) >= CHILDREN_CAP:
                break
        url = (payload.get("links") or {}).get("next")
    return views, fetched_ok


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def ensure_gleif_source(conn) -> str:
    """Insert the GLEIF source row if missing, return its id.

    The ``sources.code`` column carries a verified UNIQUE constraint
    (``sources_code_key``), so ON CONFLICT (code) is race-safe and idempotent.
    """
    conn.execute(
        """
        INSERT INTO sources (code, name, base_url, source_tier, active)
        VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (code) DO NOTHING
        """,
        (GLEIF_SOURCE_CODE, GLEIF_SOURCE_NAME, GLEIF_BASE_URL, 1),
    )
    return source_id_for(conn, GLEIF_SOURCE_CODE)


def upsert_gleif_entity(
    conn,
    view: dict[str, Any],
    *,
    prefer_entity_id: str | None = None,
) -> tuple[str, bool]:
    """Resolve/create the EEI entity for a GLEIF record; attach LEI identifiers.

    Resolution order (per spec):
      1. ``prefer_entity_id`` — the already-curated entity we are enriching
         (a company from our universe); keep its identity + curated name.
      2. an existing entity already carrying scheme='lei' value=<LEI>.
      3. else mint a deterministic id = fact_uuid('gleif-entity', lei).

    Returns (entity_id, created_new). ``created_new`` is True only when a brand
    new entity was materialized from GLEIF (a parent/child not in our DB).

    Note (v1 limitation): a parent/child that is itself a US-listed company in our
    universe but not yet LEI-tagged is minted here as a separate gleif-entity;
    full cross-universe name reconciliation is intentionally out of scope for v1
    to avoid speculative merges.
    """
    lei = view["lei"]
    if prefer_entity_id:
        entity_id = prefer_entity_id
    else:
        row = conn.execute(
            "SELECT entity_id FROM entity_identifiers WHERE scheme = 'lei' AND value = %s",
            (lei,),
        ).fetchone()
        entity_id = str(row[0]) if row else fact_uuid("gleif-entity", lei)

    existed = conn.execute("SELECT 1 FROM entities WHERE id = %s", (entity_id,)).fetchone()

    # overwrite_name=False preserves curated display names; jurisdiction is only
    # backfilled when currently NULL (see common.upsert_entity).
    upsert_entity(
        conn,
        entity_id,
        view["legal_name"] or lei,
        jurisdiction=view.get("jurisdiction"),
        overwrite_name=False,
    )
    upsert_identifier(conn, entity_id, "lei", lei, issuer="gleif")
    if view["legal_name"]:
        upsert_identifier(conn, entity_id, "lei_legal_name", view["legal_name"], issuer="gleif")
    for bic in view.get("bic") or []:
        upsert_identifier(conn, entity_id, "bic", bic, issuer="gleif")

    created_new = existed is None and not prefer_entity_id
    return entity_id, created_new


def _relationship_source_document(
    conn,
    *,
    source_id: str,
    subject_lei: str,
    subject_name: str,
    endpoint: str,
    related_leis: list[str],
) -> str:
    """One provenance document per (company, GLEIF relationship endpoint).

    The content hash is computed over a CANONICAL, data-only payload (the sorted
    related LEIs), NOT the raw HTTP bytes. GLEIF wraps every response in a
    ``meta.goldenCopy.publishDate`` that changes daily even when the underlying
    ownership data does not; hashing the data-only payload keeps the document id
    (and therefore the derived relationship ids) stable across re-runs over the
    same underlying relationships -- the idempotency the pipeline requires.
    """
    url = GLEIF_BASE + f"lei-records/{subject_lei}/{endpoint}"
    canonical = json.dumps(
        {"endpoint": endpoint, "subject_lei": subject_lei, "related_leis": sorted(related_leis)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return upsert_source_document(
        conn,
        source_id=source_id,
        external_id=f"gleif:{subject_lei}:{endpoint}",
        url=url,
        title=f"GLEIF relationship for {subject_name}",
        publisher=GLEIF_PUBLISHER,
        document_date=utcnow(),
        content_hash=sha256_hex(canonical),
    )


def _link_pair(
    conn,
    *,
    child_id: str,
    parent_id: str,
    doc_id: str,
    endpoint: str,
    child_lei: str,
    parent_lei: str,
    child_name: str,
    parent_name: str,
) -> int:
    """Create the symmetric subsidiary_of / voting_control pair for one edge.

    subject ``subsidiary_of`` object  == child is a subsidiary OF parent.
    subject ``voting_control`` object == parent has voting control OVER child.
    Returns how many relationship rows were newly inserted (0-2).
    """
    qualifiers = json.dumps({
        "gleif_endpoint": endpoint,
        "gleif_relationship": "accounting_consolidation_direct_parent",
        "child_lei": child_lei,
        "parent_lei": parent_lei,
    })
    locator = f"GLEIF {endpoint} relationship"
    created = 0
    r1 = insert_relationship(
        conn,
        subject_id=child_id,
        object_id=parent_id,
        relationship_type="subsidiary_of",
        relationship_family="corporate_structure",
        confidence=GLEIF_CONFIDENCE,
        qualifiers_json=qualifiers,
        evidence_source_document_id=doc_id,
        evidence_locator=locator,
        evidence_excerpt=f"{child_name} is a direct subsidiary of {parent_name} per GLEIF.",
    )
    r2 = insert_relationship(
        conn,
        subject_id=parent_id,
        object_id=child_id,
        relationship_type="voting_control",
        relationship_family="ownership_control",
        confidence=GLEIF_CONFIDENCE,
        qualifiers_json=qualifiers,
        evidence_source_document_id=doc_id,
        evidence_locator=locator,
        evidence_excerpt=f"{parent_name} exercises voting control over {child_name} per GLEIF.",
    )
    created += 1 if r1 else 0
    created += 1 if r2 else 0
    return created


# ---------------------------------------------------------------------------
# Per-company processing
# ---------------------------------------------------------------------------
def process_company(
    conn,
    client: GleifClient,
    *,
    company_id: str,
    company_name: str,
    ticker: str,
    gleif_source_id: str,
    stats: dict[str, int],
    dry_run: bool,
) -> None:
    match, note = resolve_lei(client, company_name)
    if not match:
        stats["unresolved"] += 1
        print(f"  [skip] {company_name!r} ({ticker}): {note}")
        return

    lei = match["lei"]
    stats["resolved"] += 1
    print(f"  [lei ] {company_name!r} ({ticker}) -> {lei} "
          f"[{match['legal_name']!r}, {match.get('jurisdiction') or '?'}, sim={match['sim']:.2f}]")

    if not dry_run:
        upsert_gleif_entity(conn, match, prefer_entity_id=company_id)

    # --- direct parent ---------------------------------------------------
    parents, _ = _fetch_related(client, lei, "direct-parent")
    if parents:
        stats["parents_found"] += 1
        parent = parents[0]
        print(f"    parent: {parent['legal_name']!r} ({parent['lei']}, "
              f"{parent.get('jurisdiction') or '?'})")
        if not dry_run:
            parent_id, created = upsert_gleif_entity(conn, parent)
            stats["entities_created"] += 1 if created else 0
            doc_id = _relationship_source_document(
                conn, source_id=gleif_source_id, subject_lei=lei,
                subject_name=match["legal_name"] or company_name,
                endpoint="direct-parent", related_leis=[parent["lei"]],
            )
            stats["relationships"] += _link_pair(
                conn, child_id=company_id, parent_id=parent_id, doc_id=doc_id,
                endpoint="direct-parent", child_lei=lei, parent_lei=parent["lei"],
                child_name=match["legal_name"] or company_name, parent_name=parent["legal_name"],
            )

    # --- direct children -------------------------------------------------
    children, _ = _fetch_related(client, lei, "direct-children")
    if children:
        stats["children_found"] += len(children)
        print(f"    children: {len(children)}")
        if not dry_run:
            doc_id = _relationship_source_document(
                conn, source_id=gleif_source_id, subject_lei=lei,
                subject_name=match["legal_name"] or company_name,
                endpoint="direct-children", related_leis=[c["lei"] for c in children],
            )
            for child in children:
                child_id, created = upsert_gleif_entity(conn, child)
                stats["entities_created"] += 1 if created else 0
                stats["relationships"] += _link_pair(
                    conn, child_id=child_id, parent_id=company_id, doc_id=doc_id,
                    endpoint="direct-children", child_lei=child["lei"], parent_lei=lei,
                    child_name=child["legal_name"], parent_name=match["legal_name"] or company_name,
                )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap number of companies to process")
    parser.add_argument("--offset", type=int, default=0,
                        help="skip this many companies (alphabetical by name)")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve LEIs + print relationships; write nothing")
    args = parser.parse_args()

    client = GleifClient()
    stats = {
        "companies": 0, "resolved": 0, "unresolved": 0,
        "parents_found": 0, "children_found": 0,
        "entities_created": 0, "relationships": 0,
    }
    try:
        with connect_database() as conn:
            companies = conn.execute(COMPANY_QUERY, (args.limit, args.offset or 0)).fetchall()
            print(f"[gleif] processing {len(companies)} companies "
                  f"(limit={args.limit} offset={args.offset} dry_run={args.dry_run})")

            gleif_source_id = "" if args.dry_run else ensure_gleif_source(conn)
            if not args.dry_run:
                print(f"[gleif] source '{GLEIF_SOURCE_CODE}' id={gleif_source_id}")

            for idx, (company_id, company_name, ticker) in enumerate(companies, start=1):
                stats["companies"] += 1
                try:
                    process_company(
                        conn, client,
                        company_id=str(company_id), company_name=company_name,
                        ticker=ticker or "?", gleif_source_id=gleif_source_id,
                        stats=stats, dry_run=args.dry_run,
                    )
                except Exception as exc:  # never let one company abort the batch
                    print(f"  [error] {company_name!r}: {type(exc).__name__}: {exc}")
                    if not args.dry_run:
                        conn.rollback()
                    continue
                if not args.dry_run and idx % 50 == 0:
                    conn.commit()
                    print(f"[gleif] committed at {idx}/{len(companies)} "
                          f"(resolved={stats['resolved']} rels={stats['relationships']})")
            if not args.dry_run:
                conn.commit()
    finally:
        client.close()

    print("[gleif] DONE "
          f"companies={stats['companies']} resolved={stats['resolved']} "
          f"unresolved={stats['unresolved']} parents={stats['parents_found']} "
          f"children={stats['children_found']} entities_created={stats['entities_created']} "
          f"relationships={stats['relationships']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
