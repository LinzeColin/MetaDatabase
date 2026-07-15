#!/usr/bin/env python3
"""S7PCT02 calibration action: load official SEC ticker identifiers.

The S7PCT01 gold evaluation exposed an entity-resolution recall gap: the
/v1/entities identifier match path exists, but entities carry no ticker /
registry-title identifiers. This loader closes that DATA gap from the official
SEC EDGAR company_tickers.json registry (fetched in the gold corpus, sha256
pinned in the manifest), using an EXPLICIT research_id <-> CIK map for the
universe companies that already have entities. No fuzzy matching; fail-closed
if a mapped company is missing from the registry or resolves ambiguously.

Idempotent: existing (entity_id, scheme, value) rows are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402

# Explicit official mapping: research_id -> SEC CIK (int, as in company_tickers.json).
# Only universe companies with production entities; OpenAI (P0-007) is private - no ticker.
RESEARCH_CIK_MAP = {
    "P0-001": 1652044,  # Alphabet Inc.
    "P0-002": 789019,   # Microsoft Corporation
    "P0-003": 1018724,  # Amazon.com, Inc.
    "P0-004": 1326801,  # Meta Platforms, Inc.
    "P0-005": 320193,   # Apple Inc.
    "P0-006": 1045810,  # NVIDIA Corporation
    "P0-012": 1318605,  # Tesla, Inc.
    "P0-013": 1341439,  # Oracle Corporation
    "P0-014": 1730168,  # Broadcom Inc.
    "P0-017": 1769628,  # CoreWeave, Inc.
    "P0-018": 1321655,  # Palantir Technologies Inc.
    "X-001": 1046179,   # TSMC
    "X-002": 937966,    # ASML Holding N.V.
}
ISSUER = "SEC EDGAR company_tickers.json"


def sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--corpus-manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()

    registry_text = args.registry.read_text(encoding="utf-8")
    manifest = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    pinned = {
        r["source_id"]: r["source_text_sha256"] for r in manifest["records"]
    }.get("SEC-COMPANY-TICKERS")
    if sha256_text(registry_text) != pinned:
        raise SystemExit("FAIL-CLOSED: registry text does not match gold-corpus manifest hash")
    registry = json.loads(registry_text)
    by_cik: dict[int, dict[str, str]] = {}
    for row in registry.values():
        by_cik.setdefault(int(row["cik_str"]), row)

    planned: list[dict[str, str]] = []
    with connect_database() as conn:
        universe = {
            r[0]: {"canonical_name": r[1], "entity_id": r[2]}
            for r in conn.execute(
                "SELECT research_id, canonical_name, entity_id::text"
                " FROM company_research_universe"
            ).fetchall()
        }
        entity_by_name = {
            r[1]: r[0]
            for r in conn.execute("SELECT id::text, canonical_name FROM entities").fetchall()
        }
        for research_id, cik in sorted(RESEARCH_CIK_MAP.items()):
            if research_id not in universe:
                raise SystemExit(f"FAIL-CLOSED: {research_id} not in research universe")
            reg = by_cik.get(cik)
            if reg is None:
                raise SystemExit(f"FAIL-CLOSED: CIK {cik} not in official registry")
            entity_id = universe[research_id]["entity_id"] or entity_by_name.get(
                universe[research_id]["canonical_name"]
            )
            if not entity_id:
                raise SystemExit(
                    f"FAIL-CLOSED: {research_id} has no production entity to attach identifiers"
                )
            for scheme, value in (
                ("ticker", reg["ticker"]),
                ("cik", f"{cik:010d}"),
                ("sec_registry_title", reg["title"]),
            ):
                planned.append(
                    {
                        "research_id": research_id,
                        "entity_id": entity_id,
                        "scheme": scheme,
                        "value": value,
                    }
                )

        inserted = 0
        skipped = 0
        if args.apply:
            for row in planned:
                result = conn.execute(
                    """
                    INSERT INTO entity_identifiers(entity_id, scheme, value, issuer)
                    SELECT %s, %s, %s, %s
                    WHERE NOT EXISTS (
                      SELECT 1 FROM entity_identifiers
                      WHERE entity_id = %s AND scheme = %s AND value = %s
                    )
                    """,
                    (
                        row["entity_id"],
                        row["scheme"],
                        row["value"],
                        ISSUER,
                        row["entity_id"],
                        row["scheme"],
                        row["value"],
                    ),
                )
                if result.rowcount:
                    inserted += 1
                else:
                    skipped += 1

    report = {
        "schema_version": "eei-official-ticker-identifier-load-v1",
        "task_id": "S7PCT02",
        "acceptance_ids": ["A026", "A027"],
        "registry_sha256": pinned,
        "issuer": ISSUER,
        "companies_mapped": len(RESEARCH_CIK_MAP),
        "identifiers_planned": len(planned),
        "applied": bool(args.apply),
        "identifiers_inserted": inserted,
        "identifiers_skipped_existing": skipped,
        "planned": planned,
        "release_scope": {
            "gold_labels_modified": False,
            "relationship_publication_performed": False,
            "release_clearance": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: report[k] for k in ("applied", "identifiers_planned", "identifiers_inserted", "identifiers_skipped_existing")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
