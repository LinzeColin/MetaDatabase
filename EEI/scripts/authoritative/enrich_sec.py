#!/usr/bin/env python3
"""Enrich companies with first-hand SEC facts: filing events + industry.

For each target company (resolved by CIK) we pull the SEC submissions feed
(data.sec.gov/submissions/CIK{cik}.json) and materialize:
  - real business EVENTS from material filings (8-K, 10-K, S-1, DEF 14A,
    SC 13D/G, S-4 ...), each anchored to its official EDGAR document URL;
  - the company's SIC INDUSTRY membership (authoritative classification);
  - state/country of incorporation as the entity jurisdiction.

Routine high-frequency forms (ownership Forms 3/4/5) are skipped to keep the
event stream meaningful. Idempotent and rerunnable.

Usage:
  python -m scripts.authoritative.enrich_sec --universe          # curated set
  python -m scripts.authoritative.enrich_sec --limit 200 --offset 0
  python -m scripts.authoritative.enrich_sec --tickers NVDA,AAPL
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from scripts.authoritative.common import (
    SecClient,
    connect_database,
    fact_uuid,
    insert_event,
    sha256_hex,
    source_id_for,
    upsert_source_document,
)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# Material form -> (event_type, human label). Routine 3/4/5 ownership forms and
# amendments-of-amendments are excluded to keep the stream signal-rich.
FORM_EVENTS: dict[str, tuple[str, str]] = {
    "8-K": ("material_disclosure", "Material event (8-K)"),
    "8-K/A": ("material_disclosure", "Material event (8-K/A)"),
    "10-K": ("annual_report", "Annual report (10-K)"),
    "20-F": ("annual_report", "Annual report (20-F)"),
    "40-F": ("annual_report", "Annual report (40-F)"),
    "10-Q": ("quarterly_report", "Quarterly report (10-Q)"),
    "S-1": ("securities_registration", "Securities registration (S-1)"),
    "S-1/A": ("securities_registration", "Securities registration (S-1/A)"),
    "F-1": ("securities_registration", "Securities registration (F-1)"),
    "S-3": ("securities_registration", "Shelf registration (S-3)"),
    "424B4": ("prospectus_filed", "Prospectus (424B4)"),
    "424B5": ("prospectus_filed", "Prospectus (424B5)"),
    "DEF 14A": ("proxy_statement", "Proxy statement (DEF 14A)"),
    "DEFM14A": ("merger_proxy", "Merger proxy (DEFM14A)"),
    "S-4": ("ma_registration", "M&A registration (S-4)"),
    "SC 13D": ("beneficial_ownership_stake", "Beneficial ownership >5% (SC 13D)"),
    "SC 13G": ("beneficial_ownership_stake", "Beneficial ownership >5% (SC 13G)"),
    "SC 14D9": ("tender_offer", "Tender offer solicitation (SC 14D9)"),
    "SC TO-T": ("tender_offer", "Third-party tender offer (SC TO-T)"),
    "25-NSE": ("delisting", "Delisting notification (25-NSE)"),
}

MAX_EVENTS_PER_COMPANY = 30


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def target_companies(conn, args) -> list[tuple[str, str, str]]:
    """Return (entity_id, canonical_name, cik10) triples to enrich."""
    if args.tickers:
        wanted = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        rows = conn.execute(
            """
            SELECT e.id, e.canonical_name, cik.value
            FROM entities e
            JOIN entity_identifiers cik ON cik.entity_id = e.id AND cik.scheme = 'cik'
            JOIN entity_identifiers tk ON tk.entity_id = e.id AND tk.scheme = 'ticker'
            WHERE tk.value = ANY(%s)
            """,
            (wanted,),
        ).fetchall()
        return [(str(r[0]), r[1], r[2]) for r in rows]
    if args.universe:
        rows = conn.execute(
            """
            SELECT DISTINCT e.id, e.canonical_name, cik.value
            FROM entities e
            JOIN entity_identifiers cik ON cik.entity_id = e.id AND cik.scheme = 'cik'
            JOIN company_research_universe u ON u.canonical_name = e.canonical_name
            ORDER BY e.canonical_name
            """
        ).fetchall()
        return [(str(r[0]), r[1], r[2]) for r in rows]
    rows = conn.execute(
        """
        SELECT e.id, e.canonical_name, cik.value
        FROM entities e
        JOIN entity_identifiers cik ON cik.entity_id = e.id AND cik.scheme = 'cik'
        WHERE e.status = 'research_target'
        ORDER BY e.canonical_name
        LIMIT %s OFFSET %s
        """,
        (args.limit, args.offset),
    ).fetchall()
    return [(str(r[0]), r[1], r[2]) for r in rows]


def upsert_sic_industry(conn, sic: str, description: str) -> str | None:
    if not sic or not description:
        return None
    industry_id = fact_uuid("sic-industry", sic)
    conn.execute(
        """
        INSERT INTO industries (id, external_id, slug, name_zh, name_en, kind, taxonomy_version)
        VALUES (%s, %s, %s, %s, %s, 'industry', 'sec_sic')
        ON CONFLICT (external_id) DO NOTHING
        """,
        (industry_id, f"sic:{sic}", f"sic-{sic}", description, description),
    )
    row = conn.execute(
        "SELECT id FROM industries WHERE external_id = %s", (f"sic:{sic}",)
    ).fetchone()
    return str(row[0]) if row else None


def link_industry(conn, entity_id: str, industry_id: str) -> None:
    conn.execute(
        """
        INSERT INTO entity_industry_memberships
          (entity_id, industry_id, role, confidence, valid_from, evidence_required)
        VALUES (%s, %s, 'primary', 1.0, now(), false)
        ON CONFLICT (entity_id, industry_id, role, valid_from) DO NOTHING
        """,
        (entity_id, industry_id),
    )


def enrich_one(conn, sec: SecClient, sec_src: str, entity_id: str, name: str,
               cik10: str) -> tuple[int, bool]:
    url = SUBMISSIONS_URL.format(cik=cik10)
    status, body = sec.get(url)
    if status != 200 or not body:
        return 0, False
    data = json.loads(body)

    # Jurisdiction + SIC industry.
    juris = (data.get("stateOfIncorporation") or "").strip() or None
    if juris:
        conn.execute(
            "UPDATE entities SET jurisdiction = COALESCE(jurisdiction, %s), updated_at = now()"
            " WHERE id = %s",
            (juris, entity_id),
        )
    sic = str(data.get("sic") or "").strip()
    sic_desc = (data.get("sicDescription") or "").strip()
    industry_ok = False
    if sic and sic_desc:
        ind = upsert_sic_industry(conn, sic, sic_desc)
        if ind:
            link_industry(conn, entity_id, ind)
            industry_ok = True

    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []

    events = 0
    for i, form in enumerate(forms):
        if events >= MAX_EVENTS_PER_COMPANY:
            break
        mapped = FORM_EVENTS.get(form)
        if not mapped:
            continue
        event_type, label = mapped
        filing_date = parse_date(dates[i] if i < len(dates) else None)
        accession = accessions[i] if i < len(accessions) else ""
        acc_nodash = accession.replace("-", "")
        primary = primary_docs[i] if i < len(primary_docs) else ""
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc_nodash}/{primary}"
            if acc_nodash and primary
            else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik10}"
        )
        doc = upsert_source_document(
            conn,
            source_id=sec_src,
            external_id=f"{accession}:{form}",
            url=filing_url,
            title=f"{name} — {label} {dates[i] if i < len(dates) else ''}".strip(),
            publisher="U.S. Securities and Exchange Commission",
            document_date=filing_date,
            content_hash=sha256_hex(f"{cik10}|{accession}|{form}"),
            media_type="text/html",
        )
        made = insert_event(
            conn,
            event_type=event_type,
            title=f"{name} — {label}",
            announced_at=filing_date,
            effective_at=filing_date,
            description=f"{label} filed with the SEC on {dates[i] if i < len(dates) else 'n/a'}.",
            participants=[(entity_id, "filer", None)],
            evidence_source_document_id=doc,
            evidence_locator=f"EDGAR accession {accession}",
            evidence_excerpt=f"{name} filed {form} on {dates[i] if i < len(dates) else 'n/a'}.",
            dedupe_key=f"{cik10}:{accession}:{form}",
        )
        if made:
            events += 1
    return events, industry_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--universe", action="store_true", help="only curated universe companies")
    parser.add_argument("--tickers", type=str, default=None, help="comma-separated tickers")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sec = SecClient()
    with connect_database() as conn:
        sec_src = source_id_for(conn, "sec_edgar")
        targets = target_companies(conn, args)
        print(f"[enrich] {len(targets)} companies to enrich")
        if args.dry_run:
            for t in targets[:10]:
                print("  ", t)
            return 0
        total_events = industries = done = 0
        for entity_id, name, cik10 in targets:
            try:
                ev, ind = enrich_one(conn, sec, sec_src, entity_id, name, cik10)
                total_events += ev
                industries += 1 if ind else 0
                done += 1
                if done % 25 == 0:
                    conn.commit()
                    print(f"[enrich] {done}/{len(targets)} "
                          f"(events={total_events} industries={industries})")
            except Exception as exc:  # noqa: BLE001 - never abort the batch
                print(f"[enrich] WARN {name} ({cik10}): {exc}")
        conn.commit()
    sec.close()
    print(f"[enrich] DONE companies={done} events={total_events} industries={industries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
