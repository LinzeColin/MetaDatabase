#!/usr/bin/env python3
"""Sync EEI's long-term structured facts to the authoritative store.

Data-layer contract (Owner, 2026-07-26):

    GitHub `LinzeColin/Private-Database`  authoritative long-term structured
                                          facts, publication records, failure
                                          conclusions, recovery facts.
                                          Batch daily; immediate on a major
                                          release / failure / recovery.
    OVH                                   compute node. Local storage is a
                                          REBUILDABLE transaction cache, queue,
                                          cursor set and runtime journal only —
                                          never the authoritative copy.
    Cloudflare D1                         rebuildable cold index for the public
                                          site; not an authoritative database.
    Cloudflare R2                         cold backup + large/binary objects.
    OCI                                   offsite backup of the R2 cold copy.

So EEI's postgres on the box is a working cache. The facts it holds — entities,
relationships, events and their evidence, each already provenance-bound to an
official source document — are the long-term record, and they live here.

What is deliberately NOT synced:
  * the runtime journal (poll logs, seen-accession ring, refresh cursors) —
    rebuildable by definition, and high-frequency;
  * raw filing bodies and any blob — those belong in R2, with only a reference
    and hash recorded as a fact;
  * anything the red lines in private_db_client reject.

Idempotence: each day partition is content-addressed. Re-running with no new
facts uploads nothing and appends nothing — no empty commits, per the contract.

Usage:
  python -m scripts.sync_facts_to_private_db --dry-run
  python -m scripts.sync_facts_to_private_db --since 2026-07-01
  python -m scripts.sync_facts_to_private_db --reason release
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402
from scripts.private_db_client import ingest, sha256_hex  # noqa: E402

ZONE = "Private-MetaDatabase"
DOMAIN = "EEI"
SCHEMA_VERSION = "eei-authoritative-facts-v1"

PUBLISHED_RULES = (
    "reviewed_relationship_fact_publication",
    "authoritative_first_hand_ingestion",
)

# One partition per ingestion day, so a re-sync only rewrites days that changed
# and a single file never approaches the 95MB ceiling.
ENTITIES_SQL = """
    SELECT to_char(date(e.created_at), 'YYYY-MM-DD') AS day,
           e.id::text, e.canonical_name, e.entity_type::text, e.status::text,
           e.jurisdiction,
           to_char(e.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           (SELECT ei.value FROM entity_identifiers ei
             WHERE ei.entity_id = e.id AND ei.scheme = 'cik' LIMIT 1),
           (SELECT ei.value FROM entity_identifiers ei
             WHERE ei.entity_id = e.id AND ei.scheme = 'lei' LIMIT 1)
    FROM entities e
    WHERE date(e.created_at) = %s
    ORDER BY e.id
"""
RELATIONSHIPS_SQL = """
    SELECT r.id::text, r.subject_entity_id::text, r.object_entity_id::text,
           r.relationship_type::text, r.relationship_family::text, r.status::text,
           r.confidence, r.derivation_rule,
           to_char(r.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           (SELECT json_agg(json_build_object(
                'source_document_id', re.source_document_id::text,
                'locator', re.locator, 'url', sd.url, 'publisher', sd.publisher))
              FROM relationship_evidence re
              JOIN source_documents sd ON sd.id = re.source_document_id
             WHERE re.relationship_id = r.id)
    FROM relationships r
    WHERE date(r.created_at) = %s AND r.derivation_rule = ANY(%s)
    ORDER BY r.id
"""
EVENTS_SQL = """
    SELECT ev.id::text, ev.event_type::text, ev.title, ev.status::text,
           to_char(ev.announced_at, 'YYYY-MM-DD'),
           to_char(ev.observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           ev.amount, ev.currency, ev.amount_kind, ev.derivation_rule,
           (SELECT json_agg(json_build_object(
                'entity_id', ep.entity_id::text, 'role', ep.role))
              FROM event_participants ep WHERE ep.event_id = ev.id),
           (SELECT json_agg(json_build_object(
                'source_document_id', ee.source_document_id::text,
                'locator', ee.locator, 'url', sd.url, 'publisher', sd.publisher))
              FROM event_evidence ee
              JOIN source_documents sd ON sd.id = ee.source_document_id
             WHERE ee.event_id = ev.id)
    FROM events ev
    WHERE date(ev.observed_at) = %s AND ev.derivation_rule = ANY(%s)
      AND ev.status NOT IN ('superseded', 'revoked')
    ORDER BY ev.id
"""

DAYS_SQL = """
    SELECT DISTINCT day FROM (
        SELECT to_char(date(created_at), 'YYYY-MM-DD') AS day FROM entities
        UNION SELECT to_char(date(created_at), 'YYYY-MM-DD') FROM relationships
              WHERE derivation_rule = ANY(%(rules)s)
        UNION SELECT to_char(date(observed_at), 'YYYY-MM-DD') FROM events
              WHERE derivation_rule = ANY(%(rules)s)
    ) d WHERE day IS NOT NULL AND day >= %(since)s ORDER BY day
"""


def _entity_row(r: tuple) -> dict:
    return {"id": r[1], "canonical_name": r[2], "entity_type": r[3],
            "status": r[4], "jurisdiction": r[5], "created_at": r[6],
            "cik": r[7], "lei": r[8]}


def _relationship_row(r: tuple) -> dict:
    return {"id": r[0], "subject_entity_id": r[1], "object_entity_id": r[2],
            "relationship_type": r[3], "relationship_family": r[4],
            "status": r[5], "confidence": float(r[6]) if r[6] is not None else None,
            "derivation_rule": r[7], "created_at": r[8], "evidence": r[9] or []}


def _event_row(r: tuple) -> dict:
    return {"id": r[0], "event_type": r[1], "title": r[2], "status": r[3],
            "announced_at": r[4], "observed_at": r[5],
            "amount": float(r[6]) if r[6] is not None else None,
            "currency": r[7], "amount_kind": r[8], "derivation_rule": r[9],
            "participants": r[10] or [], "evidence": r[11] or []}


def build_partition(conn, day: str) -> tuple[bytes, dict] | None:
    """One day of facts as gzipped NDJSON, or None when the day holds nothing."""
    rules = list(PUBLISHED_RULES)
    entities = [_entity_row(r) for r in conn.execute(ENTITIES_SQL, (day,)).fetchall()]
    relationships = [
        _relationship_row(r)
        for r in conn.execute(RELATIONSHIPS_SQL, (day, rules)).fetchall()
    ]
    events = [_event_row(r) for r in conn.execute(EVENTS_SQL, (day, rules)).fetchall()]
    if not (entities or relationships or events):
        return None

    lines = [json.dumps({"_meta": {"schema_version": SCHEMA_VERSION, "day": day,
                                   "counts": {"entities": len(entities),
                                              "relationships": len(relationships),
                                              "events": len(events)}}},
                        ensure_ascii=False, sort_keys=True)]
    for kind, rows in (("entity", entities), ("relationship", relationships),
                       ("event", events)):
        for row in rows:
            lines.append(json.dumps({"kind": kind, **row}, ensure_ascii=False,
                                    sort_keys=True))
    body = ("\n".join(lines) + "\n").encode("utf-8")
    # mtime=0 so identical facts always produce identical bytes — that is what
    # makes "no new facts => no upload, no manifest line, no commit" hold.
    payload = gzip.compress(body, compresslevel=9, mtime=0)
    stats = {"day": day, "entities": len(entities),
             "relationships": len(relationships), "events": len(events),
             "bytes": len(payload), "sha256": sha256_hex(payload)}
    return payload, stats


def run(args) -> dict:
    started = datetime.now(UTC).isoformat()
    result: dict = {"started_at": started, "zone": ZONE, "domain": DOMAIN,
                    "reason": args.reason, "partitions": [], "uploaded": 0,
                    "skipped_unchanged": 0}
    batch = f"{DOMAIN}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{args.reason}"

    with connect_database() as conn:
        days = [r[0] for r in conn.execute(
            DAYS_SQL, {"rules": list(PUBLISHED_RULES), "since": args.since}
        ).fetchall()]
        result["days_considered"] = len(days)

        for day in days:
            built = build_partition(conn, day)
            if built is None:
                continue
            payload, stats = built
            result["partitions"].append(stats)
            if args.dry_run:
                continue
            name = f"eei_facts_{day}.ndjson.gz"
            tmp = Path(args.workdir) / name
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(payload)
            if args.export_only:
                # The compute node must never hold a GitHub credential — same
                # rule that keeps account-level Cloudflare keys off it. So the
                # box only ever *builds* partitions; the upload runs where auth
                # already lives, and the files are deleted on both sides.
                result["exported"] = result.get("exported", 0) + 1
                continue
            try:
                out = ingest(ZONE, tmp, domain=DOMAIN, batch=batch)
                # The contract forbids manufacturing commits for unchanged
                # facts, so count what actually hit the repo — a ledger append
                # is a commit even when the object was already there.
                if out.get("created_commit"):
                    result["uploaded"] += 1
                else:
                    result["skipped_unchanged"] += 1
            finally:
                tmp.unlink(missing_ok=True)

    result["finished_at"] = datetime.now(UTC).isoformat()
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", default="1970-01-01",
                   help="only sync ingestion days on or after this date")
    p.add_argument("--reason", default="daily",
                   choices=["daily", "release", "failure", "recovery", "manual"],
                   help="daily batch, or an immediate sync triggered by a major"
                        " release / failure / recovery (contract §GitHub)")
    p.add_argument("--workdir", default="/tmp/eei-private-db-sync",
                   help="scratch path for the partition being uploaded; each"
                        " file is deleted immediately after upload (nothing"
                        " lands locally, per iron rule 3)")
    p.add_argument("--export-only", action="store_true",
                   help="build partitions into --workdir and stop (no GitHub"
                        " credential needed, so this is what runs on the box)")
    p.add_argument("--dry-run", action="store_true",
                   help="build and hash partitions, upload nothing")
    args = p.parse_args()

    result = run(args)
    totals = {
        "entities": sum(x["entities"] for x in result["partitions"]),
        "relationships": sum(x["relationships"] for x in result["partitions"]),
        "events": sum(x["events"] for x in result["partitions"]),
        "bytes": sum(x["bytes"] for x in result["partitions"]),
    }
    result["totals"] = totals
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
