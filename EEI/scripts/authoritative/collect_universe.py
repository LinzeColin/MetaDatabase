#!/usr/bin/env python3
"""Load the authoritative SEC company universe as real entities.

Source (first-hand): https://www.sec.gov/files/company_tickers.json — the SEC's
own registry of every company with an assigned ticker (~10.4k rows), each with
CIK + ticker + registered title. We materialize one legal_entity per company
with cik/ticker/registry-title identifiers. Existing entities that already
carry a CIK are reused (never duplicated); curated display names are preserved.

Idempotent: safe to re-run. Usage:
  python -m scripts.authoritative.collect_universe [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json

from scripts.authoritative.common import (
    SecClient,
    connect_database,
    resolve_entity_id,
    sha256_hex,
    source_id_for,
    upsert_entity,
    upsert_identifier,
    upsert_source_document,
    utcnow,
)

REGISTRY_URL = "https://www.sec.gov/files/company_tickers.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="cap companies (testing)")
    parser.add_argument("--dry-run", action="store_true", help="fetch + parse only, no writes")
    args = parser.parse_args()

    sec = SecClient()
    print(f"[universe] fetching {REGISTRY_URL}")
    status, body = sec.get(REGISTRY_URL)
    if status != 200 or not body:
        print(f"[universe] FAILED to fetch registry (status={status})")
        return 1
    registry = json.loads(body)
    rows = list(registry.values())
    print(f"[universe] registry has {len(rows)} companies (hash={sha256_hex(body)[:12]})")

    if args.dry_run:
        for r in rows[:5]:
            print("  sample:", r)
        return 0

    limit = args.limit or len(rows)
    created = reused = identifiers = 0
    with connect_database() as conn:
        src = source_id_for(conn, "sec_edgar")
        # Registry provenance document (one row for the whole snapshot).
        reg_doc = upsert_source_document(
            conn,
            source_id=src,
            external_id="company_tickers.json",
            url=REGISTRY_URL,
            title="SEC company tickers registry",
            publisher="U.S. Securities and Exchange Commission",
            document_date=utcnow(),
            content_hash=sha256_hex(body),
        )
        print(f"[universe] registry source_document={reg_doc}")

        for i, row in enumerate(rows[:limit]):
            try:
                cik10 = str(row["cik_str"]).zfill(10)
            except (KeyError, TypeError):
                continue
            ticker = str(row.get("ticker", "")).strip()
            title = str(row.get("title", "")).strip() or ticker or f"CIK {cik10}"

            eid = resolve_entity_id(conn, cik10)
            existing = conn.execute(
                "SELECT 1 FROM entities WHERE id = %s", (eid,)
            ).fetchone()
            # Preserve curated names; only set name when creating fresh.
            upsert_entity(conn, eid, title, status="research_target", overwrite_name=False)
            if existing:
                reused += 1
            else:
                created += 1

            before = identifiers
            for scheme, value in (
                ("cik", cik10),
                ("ticker", ticker),
                ("sec_registry_title", title),
            ):
                if value:
                    upsert_identifier(conn, eid, scheme, value, issuer="sec_edgar")
                    identifiers += 1
            _ = before

            if (i + 1) % 1000 == 0:
                conn.commit()
                print(f"[universe] {i + 1}/{limit} processed "
                      f"(created={created} reused={reused})")
        conn.commit()

        total = conn.execute(
            "SELECT count(*) FROM entities WHERE status = 'research_target'"
        ).fetchone()[0]
    sec.close()
    print(f"[universe] DONE created={created} reused={reused} "
          f"identifier_upserts~={identifiers}")
    print(f"[universe] entities(status=research_target) now = {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
