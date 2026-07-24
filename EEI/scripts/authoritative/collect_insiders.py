#!/usr/bin/env python3
"""Collect SEC Form 3/4/5 insiders -> governance_people (+ 10% owners -> ownership).

For each target company (resolved by CIK) we read the SEC submissions feed
(``data.sec.gov/submissions/CIK{cik}.json``), scan its most recent ownership
filings (Forms 3/4/5 and their amendments), and for every *distinct reporting
owner* fetch that filing's raw ownership XML
(``www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}.xml``).

From the XML's ``reportingOwnerRelationship`` we materialize, subject=owner ->
object=issuer, each provenance-bound to the filing URL:
  - ``isOfficer``          -> ``executive_of``    (governance_people) [+ title]
  - ``isDirector``         -> ``director_of``      (governance_people)
  - ``isTenPercentOwner``  -> ``beneficial_owner`` (ownership_control)

Why this is the cleanest first-hand win: a reporting owner carries their own SEC
CIK, so entity resolution is *exact* (no name matching). Directors and officers
are natural persons by law, so they are minted as ``entity_type='person'``.

Each ``(owner, issuer)`` pair is anchored to ONE stable evidence document keyed
on both CIKs, so re-runs and additional future filings never duplicate an edge:
we keep one ``director_of`` edge per person-company, not one per transaction.

First-hand only. Free SEC sources only (no login, no paid data). Idempotent.

Usage:
  python -m scripts.authoritative.collect_insiders --tickers NVDA,AAPL
  python -m scripts.authoritative.collect_insiders --universe --max-filings 25
  python -m scripts.authoritative.collect_insiders --limit 20 --offset 0
"""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from scripts.authoritative.common import (
    SecClient,
    connect_database,
    insert_relationship,
    normalize_cik,
    resolve_entity_id,
    sha256_hex,
    source_id_for,
    upsert_entity,
    upsert_identifier,
    upsert_source_document,
)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

# Ownership forms and their amendments. Form 3 (initial), 4 (changes),
# 5 (annual) all share the ``ownershipDocument`` / reportingOwner schema.
OWNERSHIP_FORMS = frozenset({"3", "4", "5", "3/A", "4/A", "5/A"})

# A signed Form 3/4/5 is a first-hand legal attestation of the reporting owner's
# relationship to the issuer -> high confidence (a shade under GLEIF-registry 0.9
# is not warranted; this is a direct, self-reported role, not an inference).
SEC_FORM345_CONFIDENCE = 0.95
PERSON_STATUS = "active"

# Fetch ceiling per company (each fetch is one raw ownership XML). Bounds SEC
# load during tests; raise for fuller history in production.
MAX_FILINGS_PER_COMPANY = 25
# Ownership XMLs are tiny (< ~100 KB). Guard against oversized/hostile payloads
# before handing bytes to the XML parser.
MAX_XML_BYTES = 2_000_000
PUBLISHER = "U.S. Securities and Exchange Commission"

# Tokens used ONLY to type a pure 10%-owner reporting entity (never a director/
# officer, who is always a natural person). Word-boundary matched.
COMPANY_TOKENS = frozenset({
    "LLC", "LLP", "LP", "L.L.C", "L.P", "INC", "CORP", "CO", "COMPANY", "TRUST",
    "PARTNERS", "PARTNERSHIP", "CAPITAL", "MANAGEMENT", "MGMT", "FUND", "FUNDS",
    "HOLDINGS", "HOLDING", "GROUP", "VENTURES", "ADVISORS", "ADVISERS",
    "ASSOCIATES", "BANCORP", "BANK", "PLC", "GMBH", "LTD", "LIMITED", "NV",
    "SA", "AG", "SE", "ULC",
})


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _text(parent: ET.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    el = parent.find(tag)
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def _flag(rel: ET.Element | None, tag: str) -> bool:
    if rel is None:
        return False
    el = rel.find(tag)
    if el is None or el.text is None:
        return False
    return el.text.strip().lower() in ("1", "true", "yes")


def _looks_like_company(name: str) -> bool:
    tokens = name.upper().replace(",", " ").replace(".", " ").replace("/", " ").split()
    return any(tok in COMPANY_TOKENS for tok in tokens)


def parse_ownership_xml(body: bytes) -> tuple[str | None, list[dict]]:
    """Parse a Form 3/4/5 ``ownershipDocument`` -> (issuer_cik, [owner dicts])."""
    root = ET.fromstring(body)  # noqa: S314 - trusted, host-allowlisted SEC XML
    issuer_cik = _text(root.find("issuer"), "issuerCik")
    owners: list[dict] = []
    for ro in root.findall("reportingOwner"):
        rid = ro.find("reportingOwnerId")
        rel = ro.find("reportingOwnerRelationship")
        owners.append({
            "cik": _text(rid, "rptOwnerCik"),
            "name": _text(rid, "rptOwnerName"),
            "is_director": _flag(rel, "isDirector"),
            "is_officer": _flag(rel, "isOfficer"),
            "is_ten": _flag(rel, "isTenPercentOwner"),
            "title": _text(rel, "officerTitle"),
        })
    return issuer_cik, owners


def _ingest_owner(
    conn,
    sec_src: str,
    *,
    issuer_id: str,
    issuer_name: str,
    issuer_cik10: str,
    owner_cik10: str,
    owner: dict,
    form: str,
    accession: str,
    doc_name: str,
    filed: datetime | None,
    xml_url: str,
) -> dict:
    """Create the entity, identifier, evidence doc and up to three edges."""
    name = owner["name"]
    is_dir, is_off, is_ten = owner["is_director"], owner["is_officer"], owner["is_ten"]
    result = {"person": 0, "director": 0, "exec": 0, "beneficial": 0}
    # Only materialize edges we can type precisely; skip pure "other" relationships.
    if not (is_dir or is_off or is_ten):
        return result

    # Directors/officers are natural persons by law; a bare 10%-owner may be an
    # entity -> fall back to a conservative name heuristic for that case only.
    etype = "person" if (is_dir or is_off) else (
        "legal_entity" if _looks_like_company(name) else "person"
    )
    owner_id = resolve_entity_id(conn, owner_cik10)
    upsert_entity(conn, owner_id, name, entity_type=etype, status=PERSON_STATUS)
    upsert_identifier(conn, owner_id, "cik", owner_cik10, "SEC")
    result["person"] = 1

    # ONE stable evidence doc per (issuer, owner): stable external_id + content
    # hash => stable source_documents.id => stable relationship id. This is what
    # keeps the graph at one edge per person-company regardless of filing count.
    doc_id = upsert_source_document(
        conn,
        source_id=sec_src,
        external_id=f"form345-position:{issuer_cik10}:{owner_cik10}",
        url=xml_url,
        title=f"{name} - insider position in {issuer_name} (SEC Form {form})",
        publisher=PUBLISHER,
        document_date=filed,
        content_hash=sha256_hex(f"{issuer_cik10}|{owner_cik10}|form345_position"),
        media_type="application/xml",
    )
    locator = f"EDGAR accession {accession} ({doc_name})"

    if is_off:
        title = owner["title"]
        edge = insert_relationship(
            conn,
            subject_id=owner_id,
            object_id=issuer_id,
            relationship_type="executive_of",
            relationship_family="governance_people",
            confidence=SEC_FORM345_CONFIDENCE,
            valid_from=filed,
            filed_at=filed,
            qualifiers_json=json.dumps({
                "source_form": f"sec_form_{form}",
                "officer_title": title,
                "accession": accession,
            }),
            evidence_source_document_id=doc_id,
            evidence_locator=locator,
            evidence_excerpt=(
                f"{name} reported as officer"
                f"{f' ({title})' if title else ''} of {issuer_name} on SEC Form {form}."
            ),
        )
        result["exec"] = 1 if edge else 0
    if is_dir:
        edge = insert_relationship(
            conn,
            subject_id=owner_id,
            object_id=issuer_id,
            relationship_type="director_of",
            relationship_family="governance_people",
            confidence=SEC_FORM345_CONFIDENCE,
            valid_from=filed,
            filed_at=filed,
            qualifiers_json=json.dumps({
                "source_form": f"sec_form_{form}",
                "accession": accession,
            }),
            evidence_source_document_id=doc_id,
            evidence_locator=locator,
            evidence_excerpt=f"{name} reported as director of {issuer_name} on SEC Form {form}.",
        )
        result["director"] = 1 if edge else 0
    if is_ten:
        edge = insert_relationship(
            conn,
            subject_id=owner_id,
            object_id=issuer_id,
            relationship_type="beneficial_owner",
            relationship_family="ownership_control",
            confidence=SEC_FORM345_CONFIDENCE,
            valid_from=filed,
            filed_at=filed,
            qualifiers_json=json.dumps({
                "source_form": f"sec_form_{form}",
                "basis": "ten_percent_owner_checkbox",
                "accession": accession,
            }),
            evidence_source_document_id=doc_id,
            evidence_locator=locator,
            evidence_excerpt=(
                f"{name} reported as >10% beneficial owner of {issuer_name} "
                f"on SEC Form {form}."
            ),
        )
        result["beneficial"] = 1 if edge else 0
    return result


def collect_company(
    conn,
    sec: SecClient,
    sec_src: str,
    *,
    issuer_id: str,
    issuer_name: str,
    issuer_cik10: str,
    max_filings: int,
) -> dict:
    """Scan one issuer's recent 3/4/5 filings and ingest distinct owners."""
    totals = {"persons": 0, "director": 0, "exec": 0, "beneficial": 0, "filings": 0}
    data = sec.get_json(SUBMISSIONS_URL.format(cik=issuer_cik10))
    if not data:
        return totals
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accs = recent.get("accessionNumber") or []
    docs = recent.get("primaryDocument") or []
    dates = recent.get("filingDate") or []

    seen: set[str] = set()  # owner CIKs already ingested (newest-first => most recent)
    fetched = 0
    for i, form in enumerate(forms):
        if form not in OWNERSHIP_FORMS:
            continue
        if fetched >= max_filings:
            break
        accession = accs[i] if i < len(accs) else ""
        primary = docs[i] if i < len(docs) else ""
        doc_name = primary.split("/")[-1] if primary else ""
        if not accession or not doc_name.lower().endswith(".xml"):
            continue
        acc_nodash = accession.replace("-", "")
        xml_url = ARCHIVE_DOC_URL.format(
            cik=int(issuer_cik10), acc=acc_nodash, doc=doc_name
        )
        status, body = sec.get(xml_url)
        fetched += 1
        if status != 200 or not body or len(body) > MAX_XML_BYTES:
            continue
        try:
            xml_issuer_cik, owners = parse_ownership_xml(body)
        except ET.ParseError:
            continue
        # Guard: the XML issuer must be the company whose feed we are reading.
        if xml_issuer_cik and normalize_cik(xml_issuer_cik) != issuer_cik10:
            continue
        totals["filings"] += 1
        filed = parse_date(dates[i] if i < len(dates) else None)
        for owner in owners:
            if not owner["cik"] or not owner["name"]:
                continue
            owner_cik10 = normalize_cik(owner["cik"])
            if owner_cik10 in seen:
                continue
            seen.add(owner_cik10)
            r = _ingest_owner(
                conn,
                sec_src,
                issuer_id=issuer_id,
                issuer_name=issuer_name,
                issuer_cik10=issuer_cik10,
                owner_cik10=owner_cik10,
                owner=owner,
                form=form,
                accession=accession,
                doc_name=doc_name,
                filed=filed,
                xml_url=xml_url,
            )
            totals["persons"] += r["person"]
            totals["director"] += r["director"]
            totals["exec"] += r["exec"]
            totals["beneficial"] += r["beneficial"]
    return totals


def target_companies(conn, args) -> list[tuple[str, str, str]]:
    """Return (entity_id, canonical_name, cik10) triples to process."""
    if args.tickers:
        wanted = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        rows = conn.execute(
            """
            SELECT DISTINCT e.id, e.canonical_name, cik.value
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--universe", action="store_true", help="only curated universe companies")
    parser.add_argument("--tickers", type=str, default=None, help="comma-separated tickers")
    parser.add_argument(
        "--max-filings",
        type=int,
        default=MAX_FILINGS_PER_COMPANY,
        help="max recent 3/4/5 filings scanned per company",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sec = SecClient()
    with connect_database() as conn:
        sec_src = source_id_for(conn, "sec_edgar")
        targets = target_companies(conn, args)
        print(f"[insiders] {len(targets)} companies to process (max_filings={args.max_filings})")
        if args.dry_run:
            for t in targets[:10]:
                print("  ", t)
            return 0
        agg = {"persons": 0, "director": 0, "exec": 0, "beneficial": 0, "filings": 0}
        done = 0
        for issuer_id, name, cik10 in targets:
            try:
                t = collect_company(
                    conn,
                    sec,
                    sec_src,
                    issuer_id=issuer_id,
                    issuer_name=name,
                    issuer_cik10=normalize_cik(cik10),
                    max_filings=args.max_filings,
                )
                for k in agg:
                    agg[k] += t[k]
                done += 1
                if done % 10 == 0:
                    conn.commit()
                    print(
                        f"[insiders] {done}/{len(targets)} "
                        f"persons={agg['persons']} director={agg['director']} "
                        f"exec={agg['exec']} beneficial={agg['beneficial']}"
                    )
            except Exception as exc:  # noqa: BLE001 - never abort the batch
                print(f"[insiders] WARN {name} ({cik10}): {exc}")
        conn.commit()
    sec.close()
    print(
        f"[insiders] DONE companies={done} persons={agg['persons']} "
        f"director={agg['director']} exec={agg['exec']} beneficial={agg['beneficial']} "
        f"filings_parsed={agg['filings']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
