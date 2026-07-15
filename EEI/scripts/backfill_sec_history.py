#!/usr/bin/env python3
"""S7PDT01: backfill 2016+ SEC filing history for the golden vertical + adjacency.

For every mapped universe company with a SEC CIK this fetches the official
EDGAR submissions index (recent block plus older pagination files until the
cutoff is covered), filters annual/quarterly/current-report forms
(10-K/10-Q/8-K and foreign-issuer 20-F/6-K families, amendments included)
filed on or after the cutoff, and persists one source_documents +
raw_source_snapshots row per filing under a dedicated `sec_edgar` source and
one live ingestion_run per company. Company facts (XBRL, all historical
periods) are archived out of git with sha256 pinned in the report and counted
through the audited normalizer.

Raw discipline: the database keeps index metadata and content hashes only;
full submissions / companyfacts JSON archives live outside the repository.
Idempotent: existing (source, accession, hash) documents and
(anchor, hash) snapshots are skipped. Fail-closed per company; failures are
recorded, never masked. Sample spot-checks fetch real primary documents and
record HTTP status + sha256 so the index provably points at retrievable
official filings.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ingest.sec_client import SecEdgarClient, normalize_cik  # noqa: E402
from app.ingest.sec_normalizer import normalize_sec_company_facts  # noqa: E402
from scripts.db_tools import connect_database  # noqa: E402
from scripts.load_official_ticker_identifiers import RESEARCH_CIK_MAP  # noqa: E402

SCHEMA_VERSION = "eei-sec-history-backfill-v1"
TASK_ID = "S7PDT01"
ACCEPTANCE_IDS = ["ACC-S7PDT01"]
CONNECTOR_VERSION = "sec-backfill-2016-v1"
PARSER_VERSION = "sec-backfill-2016-v1"
DEFAULT_SINCE = "2016-01-01"
BACKFILL_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A",
    "20-F", "20-F/A", "6-K", "6-K/A",
}
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
SOURCE_CODE = "sec_edgar"
SOURCE_NAME = "SEC EDGAR official filings"
SOURCE_TIER = 1


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def recent_block_entries(recent: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = [
        "accessionNumber", "filingDate", "form", "primaryDocument",
        "primaryDocDescription", "act", "size", "isXBRL",
    ]
    count = len(recent.get("accessionNumber", []))
    entries = []
    for index in range(count):
        entries.append(
            {key: (recent.get(key) or [None] * count)[index] for key in keys}
        )
    return entries


def filter_filing_entries(
    entries: list[dict[str, Any]],
    *,
    since: str,
    forms: set[str] = frozenset(BACKFILL_FORMS),
) -> list[dict[str, Any]]:
    kept = []
    for entry in entries:
        form = str(entry.get("form") or "").strip()
        filing_date = str(entry.get("filingDate") or "")
        if form in forms and filing_date >= since and entry.get("accessionNumber"):
            kept.append(entry)
    return kept


def build_primary_document_url(cik: int, accession: str, primary_document: str | None) -> str:
    accession_nodash = accession.replace("-", "")
    if primary_document:
        return (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accession_nodash}/{primary_document}"
        )
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{accession}-index.htm"


def entry_content_hash(cik: int, entry: dict[str, Any]) -> str:
    return sha256_text(canonical_json({"cik": cik, **entry}))


async def collect_submission_pages(
    client: SecEdgarClient, cik: int, *, since: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (all candidate entries, page evidence records) covering the cutoff."""
    root = await client.get_submissions(cik)
    pages = [
        {
            "url": root.url,
            "content_sha256": root.content_sha256,
            "kind": "submissions_root",
        }
    ]
    filings = root.payload.get("filings") or {}
    entries = recent_block_entries(filings.get("recent") or {})
    for page in filings.get("files") or []:
        filing_to = str(page.get("filingTo") or "")
        if filing_to and filing_to < since:
            continue
        page_response = await client.get_json(
            SUBMISSIONS_PAGE_URL.format(name=page["name"])
        )
        pages.append(
            {
                "url": page_response.url,
                "content_sha256": page_response.content_sha256,
                "kind": "submissions_page",
            }
        )
        entries.extend(recent_block_entries(page_response.payload))
    return entries, pages


def archive_json(archive_dir: Path, name: str, payload: Any) -> dict[str, str]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path = archive_dir / name
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "sha256": sha256_text(text), "chars": str(len(text))}


def ensure_sec_source(connection: Any) -> str:
    row = connection.execute(
        "SELECT id::text FROM sources WHERE code = %s", (SOURCE_CODE,)
    ).fetchone()
    if row:
        return row[0]
    return connection.execute(
        """
        INSERT INTO sources(code, name, base_url, source_tier, active)
        VALUES (%s, %s, %s, %s, true)
        RETURNING id::text
        """,
        (SOURCE_CODE, SOURCE_NAME, "https://www.sec.gov/", SOURCE_TIER),
    ).fetchone()[0]


def persist_company_backfill(
    *,
    research_id: str,
    cik: int,
    canonical_name: str,
    entries: list[dict[str, Any]],
    retrieved_at: datetime,
) -> dict[str, Any]:
    from psycopg.types.json import Jsonb  # noqa: PLC0415

    inserted_documents = 0
    skipped_documents = 0
    inserted_snapshots = 0
    skipped_snapshots = 0
    with connect_database() as connection:
        source_id = ensure_sec_source(connection)
        run_id = connection.execute(
            """
            INSERT INTO ingestion_runs(
              source_id, connector_version, mode, checkpoint, started_at, status, counts
            )
            VALUES (%s, %s, 'live', %s, %s, 'running', %s)
            RETURNING id::text
            """,
            (
                source_id,
                CONNECTOR_VERSION,
                Jsonb({"research_id": research_id, "cik": cik}),
                retrieved_at,
                Jsonb({}),
            ),
        ).fetchone()[0]
        for entry in entries:
            accession = entry["accessionNumber"]
            content_hash = entry_content_hash(cik, entry)
            url = build_primary_document_url(cik, accession, entry.get("primaryDocument"))
            title = (
                f"{canonical_name} {entry.get('form')} {entry.get('filingDate')}"
                f" ({accession})"
            )
            media_type = (
                "text/html"
                if str(entry.get("primaryDocument") or "").endswith((".htm", ".html"))
                else "application/octet-stream"
            )
            doc_row = connection.execute(
                """
                INSERT INTO source_documents(
                  source_id, external_id, url, title, publisher, document_date,
                  observed_at, retrieved_at, content_hash, media_type, parser_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id, external_id, content_hash) DO NOTHING
                RETURNING id::text
                """,
                (
                    source_id,
                    accession,
                    url,
                    title,
                    "U.S. Securities and Exchange Commission (EDGAR)",
                    entry.get("filingDate"),
                    entry.get("filingDate"),
                    retrieved_at,
                    content_hash,
                    media_type,
                    PARSER_VERSION,
                ),
            ).fetchone()
            if doc_row:
                document_id = doc_row[0]
                inserted_documents += 1
            else:
                document_id = connection.execute(
                    """
                    SELECT id::text FROM source_documents
                    WHERE source_id = %s AND external_id = %s AND content_hash = %s
                    """,
                    (source_id, accession, content_hash),
                ).fetchone()[0]
                skipped_documents += 1
            snapshot_row = connection.execute(
                """
                INSERT INTO raw_source_snapshots(
                  ingestion_run_id, source_document_id, anchor_id, source_url,
                  source_date, publisher, title, evidence_scope, record_mode,
                  validation_status, parser_version, content_hash, raw_payload,
                  retrieved_at, review_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'live', %s, %s, %s, %s, %s,
                        'machine_verified')
                ON CONFLICT (anchor_id, content_hash) DO NOTHING
                RETURNING id
                """,
                (
                    run_id,
                    document_id,
                    f"SEC-BF-{normalize_cik(cik)}-{accession}",
                    url,
                    entry.get("filingDate"),
                    "U.S. Securities and Exchange Commission (EDGAR)",
                    title,
                    "sec filing index metadata (2016+ history backfill)",
                    "verified_official_index",
                    PARSER_VERSION,
                    content_hash,
                    Jsonb({"cik": cik, "research_id": research_id, **entry}),
                    retrieved_at,
                ),
            ).fetchone()
            if snapshot_row:
                inserted_snapshots += 1
            else:
                skipped_snapshots += 1
        counts = {
            "filings_selected": len(entries),
            "documents_inserted": inserted_documents,
            "documents_skipped_existing": skipped_documents,
            "snapshots_inserted": inserted_snapshots,
            "snapshots_skipped_existing": skipped_snapshots,
        }
        connection.execute(
            """
            UPDATE ingestion_runs
            SET status = 'succeeded', finished_at = %s, counts = %s
            WHERE id = %s
            """,
            (utc_now(), Jsonb(counts), run_id),
        )
    return {"ingestion_run_id": run_id, **counts}


def sample_spot_checks(
    entries: list[dict[str, Any]], cik: int, *, per_company: int, user_agent: str
) -> list[dict[str, Any]]:
    if not entries:
        return []
    ordered = sorted(entries, key=lambda e: str(e.get("filingDate")))
    picks: list[dict[str, Any]] = [ordered[0], ordered[-1]][:per_company]
    checks = []
    with httpx.Client(
        headers={"User-Agent": user_agent}, timeout=30.0, follow_redirects=True
    ) as client:
        for entry in picks:
            url = build_primary_document_url(
                cik, entry["accessionNumber"], entry.get("primaryDocument")
            )
            record = {
                "accession": entry["accessionNumber"],
                "form": entry.get("form"),
                "filing_date": entry.get("filingDate"),
                "url": url,
            }
            try:
                response = client.get(url)
                record.update(
                    {
                        "http_status": response.status_code,
                        "content_sha256": hashlib.sha256(response.content).hexdigest(),
                        "content_bytes": len(response.content),
                        "retrievable": 200 <= response.status_code < 300,
                    }
                )
            except Exception as exc:  # record, never mask
                record.update(
                    {
                        "retrievable": False,
                        "error_class": type(exc).__name__,
                        "error_message": str(exc)[:200],
                    }
                )
            checks.append(record)
    return checks


async def backfill_company(
    client: SecEdgarClient,
    *,
    research_id: str,
    cik: int,
    canonical_name: str,
    since: str,
    archive_dir: Path,
    apply_db: bool,
    sample_per_company: int,
    user_agent: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "research_id": research_id,
        "cik": cik,
        "canonical_name": canonical_name,
    }
    try:
        entries, pages = await collect_submission_pages(client, cik, since=since)
        selected = filter_filing_entries(entries, since=since)
        dates = sorted(str(e["filingDate"]) for e in selected)
        company_dir = archive_dir / normalize_cik(cik)
        result["submissions_pages"] = pages
        result["submissions_archive"] = archive_json(
            company_dir, "submissions_selected.json", selected
        )
        facts_counts: dict[str, Any]
        facts = await client.get_company_facts(cik)
        result["companyfacts_archive"] = archive_json(
            company_dir, "companyfacts.json", facts.payload
        )
        try:
            normalized = normalize_sec_company_facts(facts.payload, record_mode="live")
            facts_counts = {
                "normalized_fact_count": len(normalized.facts),
                "normalization": "ok",
            }
        except Exception as exc:  # record, never mask
            facts_counts = {
                "normalization": "failed",
                "error_class": type(exc).__name__,
                "error_message": str(exc)[:300],
            }
        result["companyfacts"] = facts_counts
        result["filings_total_seen"] = len(entries)
        result["filings_selected"] = len(selected)
        result["earliest_selected"] = dates[0] if dates else None
        result["latest_selected"] = dates[-1] if dates else None
        result["covers_2016"] = bool(dates and dates[0] <= f"{since[:4]}-12-31")
        if apply_db:
            result["persistence"] = await asyncio.to_thread(
                persist_company_backfill,
                research_id=research_id,
                cik=cik,
                canonical_name=canonical_name,
                entries=selected,
                retrieved_at=utc_now(),
            )
        result["sample_spot_checks"] = await asyncio.to_thread(
            sample_spot_checks,
            selected,
            cik,
            per_company=sample_per_company,
            user_agent=user_agent,
        )
        result["status"] = "succeeded"
    except Exception as exc:  # fail-closed per company
        result["status"] = "failed"
        result["error_class"] = type(exc).__name__
        result["error_message"] = str(exc)[:400]
    return result


async def run(args: argparse.Namespace, user_agent: str) -> dict[str, Any]:
    with connect_database() as conn:
        names = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT research_id, canonical_name FROM company_research_universe"
            ).fetchall()
        }
    companies = [
        (research_id, cik, names.get(research_id, research_id))
        for research_id, cik in sorted(RESEARCH_CIK_MAP.items())
    ]
    if args.ciks:
        wanted = {int(c) for c in args.ciks.split(",")}
        companies = [c for c in companies if c[1] in wanted]
    results = []
    async with SecEdgarClient(user_agent=user_agent) as client:
        for research_id, cik, name in companies:
            result = await backfill_company(
                client,
                research_id=research_id,
                cik=cik,
                canonical_name=name,
                since=args.since,
                archive_dir=args.archive_dir,
                apply_db=args.apply,
                sample_per_company=args.sample_per_company,
                user_agent=user_agent,
            )
            print(
                json.dumps(
                    {
                        "company": name,
                        "status": result["status"],
                        "selected": result.get("filings_selected"),
                        "earliest": result.get("earliest_selected"),
                    }
                ),
                flush=True,
            )
            results.append(result)
    succeeded = [r for r in results if r["status"] == "succeeded"]
    samples = [
        check
        for r in results
        for check in r.get("sample_spot_checks", [])
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now().replace(microsecond=0).isoformat(),
        "since": args.since,
        "forms": sorted(BACKFILL_FORMS),
        "companies_total": len(results),
        "companies_succeeded": len(succeeded),
        "filings_selected_total": sum(r.get("filings_selected") or 0 for r in results),
        "earliest_selected_overall": min(
            (r["earliest_selected"] for r in succeeded if r.get("earliest_selected")),
            default=None,
        ),
        "samples_total": len(samples),
        "samples_retrievable": sum(1 for s in samples if s.get("retrievable")),
        "user_agent_sha256": sha256_text(user_agent),
        "applied": bool(args.apply),
        "companies": results,
        "release_scope": {
            "relationship_publication_performed": False,
            "release_clearance": False,
            "production_pointer_switched": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live-network", action="store_true")
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--ciks", help="comma-separated CIK filter (default: all mapped)")
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sample-per-company", type=int, default=2)
    parser.add_argument("--apply", action="store_true", help="persist to the database")
    args = parser.parse_args()

    if not args.allow_live_network:
        print("sec history backfill requires --allow-live-network", file=sys.stderr)
        return 2
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        print("SEC_USER_AGENT is required", file=sys.stderr)
        return 2

    report = asyncio.run(run(args, user_agent))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "companies_total",
                    "companies_succeeded",
                    "filings_selected_total",
                    "earliest_selected_overall",
                    "samples_retrievable",
                    "applied",
                )
            },
            indent=2,
        )
    )
    return 0 if report["companies_succeeded"] == report["companies_total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
