#!/usr/bin/env python3
"""Fetch the S7PCT01 production gold-label corpus sources (T904 / A026-A027).

Retrieves the vetted official sources used for gold labeling and stores the
FULL extracted text outside the repository (runtime evidence area), keeping
only sha256 hashes in the on-disk manifest. Fail-closed: any fetch failure is
recorded and the manifest marks the corpus incomplete; nothing is masked.

Sources: the registered official-source anchors (registry CSV), the
golden-vertical snapshot URLs, and the SEC official company_tickers.json
registry (entity-resolution gold vocabulary).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import fetch_official_source_full_text as official_source  # noqa: E402

SCHEMA_VERSION = "eei-gold-corpus-fetch-v1"
TASK_ID = "S7PCT01"
LEGACY_TASK_ID = "T904"
ACCEPTANCE_IDS = ["A026", "A027"]

GOLDEN_VERTICAL_SOURCES = [
    {
        "source_id": "GV-SNAPSHOT-001",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/1045810/"
            "000104581026000021/nvda-20260125.htm"
        ),
        "title": "NVIDIA Corporation FY2026 Form 10-K",
        "official_publisher": "SEC EDGAR / NVIDIA Form 10-K",
    },
    {
        "source_id": "GV-SNAPSHOT-002",
        "url": "https://www.asml.com/news/stories/2022/busting-asml-myths",
        "title": "Busting ASML myths",
        "official_publisher": "ASML Stories",
    },
    {
        "source_id": "GV-SNAPSHOT-003",
        "url": "https://pr.tsmc.com/english/news/1408",
        "title": "NVIDIA and TSMC Celebrate New Milestone: 500 Million Processors",
        "official_publisher": "TSMC Press Center",
    },
    {
        "source_id": "GV-SNAPSHOT-004",
        "url": "https://pr.tsmc.com/english/news/1734",
        "title": (
            "TSMC and ASML Reach Agreement to Develop Next Generation "
            "Lithography Technologies"
        ),
        "official_publisher": "TSMC Press Center",
    },
]

SEC_COMPANY_TICKERS = {
    "source_id": "SEC-COMPANY-TICKERS",
    "url": "https://www.sec.gov/files/company_tickers.json",
    "title": "SEC EDGAR company_tickers.json official registry",
    "official_publisher": "U.S. Securities and Exchange Commission",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_client(timeout_seconds: float) -> httpx.Client:
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit("SEC_USER_AGENT is required (operator contact identity)")
    return httpx.Client(
        timeout=timeout_seconds,
        headers={"User-Agent": user_agent},
        follow_redirects=True,
    )


def fetch_one(client: httpx.Client, source: dict[str, str], out_dir: Path) -> dict[str, object]:
    record: dict[str, object] = {
        "source_id": source["source_id"],
        "url": source["url"],
        "title": source["title"],
        "official_publisher": source["official_publisher"],
        "fetched_at": utc_now_iso(),
    }
    try:
        response = client.get(source["url"])
        content_type = response.headers.get("content-type", "")
        record["http_status"] = response.status_code
        response.raise_for_status()
        if source["source_id"] == "SEC-COMPANY-TICKERS":
            text = response.text
        else:
            text = official_source.extract_text_from_response(
                url=source["url"],
                content_type=content_type,
                body=response.content,
            )
        text_path = out_dir / f"{source['source_id']}.txt"
        text_path.write_text(text, encoding="utf-8")
        record.update(
            {
                "status": "fetched",
                "text_char_count": len(text),
                "source_text_sha256": official_source.sha256_text(text),
                "text_path": str(text_path),
            }
        )
    except Exception as exc:  # record, never mask
        record.update(
            {
                "status": "failed",
                "error_class": type(exc).__name__,
                "error_message": str(exc)[:300],
            }
        )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live-network", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    if not args.allow_live_network:
        print("gold corpus fetch requires --allow-live-network", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    registry_rows = official_source.read_csv(official_source.ANCHOR_PATH)
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for row in registry_rows:
        sources.append(
            {
                "source_id": row["anchor_id"],
                "url": row["url"],
                "title": row["title"],
                "official_publisher": row["official_publisher"],
            }
        )
        seen_urls.add(row["url"])
    for source in GOLDEN_VERTICAL_SOURCES:
        if source["url"] not in seen_urls:
            sources.append(dict(source))
            seen_urls.add(source["url"])
    sources.append(dict(SEC_COMPANY_TICKERS))

    records = []
    with build_client(args.timeout_seconds) as client:
        for source in sources:
            record = fetch_one(client, source, args.output_dir)
            records.append(record)
            print(
                json.dumps(
                    {
                        "source_id": record["source_id"],
                        "status": record["status"],
                        "chars": record.get("text_char_count"),
                    }
                ),
                flush=True,
            )

    fetched = [r for r in records if r["status"] == "fetched"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "legacy_task_id": LEGACY_TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now_iso(),
        "sources_total": len(records),
        "sources_fetched": len(fetched),
        "corpus_complete": len(fetched) == len(records),
        "user_agent_sha256": official_source.sha256_text(
            os.environ.get("SEC_USER_AGENT", "")
        ),
        "records": records,
        "release_scope": {
            "a026_closed_by_fetch": False,
            "a027_closed_by_fetch": False,
            "relationship_publication_performed": False,
            "release_clearance": False,
        },
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if manifest["corpus_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
