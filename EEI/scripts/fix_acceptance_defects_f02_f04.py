#!/usr/bin/env python3
"""Governed data correction for acceptance defects EEI-F04 and EEI-F02.

EEI-F04 - evidence locator/excerpt mismatch: the golden-vertical loader
copied the candidate-level locator and support excerpt onto every evidence
row, so supporting documents (the two TSMC Press Center releases) carried
the primary document's locator. This script rewrites each affected
relationship_evidence and relationship_fact_candidate_evidence row with the
per-document locator/excerpt now recorded in
data/golden_vertical_fact_candidates.json (sourced from the signed
2026-07-15 review bundle's per-snapshot passage descriptions). No new facts
are introduced; the documents, relationships and review decisions are
unchanged.

EEI-F02 - stale fixture identity on published endpoint entities: NVIDIA
Corporation kept status='fixture' and an "MVP fixture identity" notice from
the pre-publication seed, while its relationships were later published
through the owner-signed pipeline against official sources. Endpoint
entities of owner-signed published relationships are upgraded to
'research_target' and their stale fixture notices removed.

Every mutation writes an operation_logs row (old/new value + reason), so
this is an audited correction, not a silent backfill. Idempotent: rerunning
after success changes nothing and logs nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402

ACTOR = "eei-acceptance-fix-agent"
REASON_F04 = (
    "EEI-F04: evidence locator/excerpt must identify its own source document;"
    " corrected from per-candidate copy to per-document values recorded in the"
    " signed 2026-07-15 review bundle."
)
REASON_F02 = (
    "EEI-F02: endpoint entity of owner-signed published relationships carried a"
    " stale pre-publication fixture identity; upgraded to research_target and"
    " stale fixture notice removed."
)
PUBLISHED_RULE = "reviewed_relationship_fact_publication"


def log_operation(
    conn: Any,
    *,
    action_type: str,
    object_type: str,
    object_id: str,
    old_value: dict[str, Any],
    new_value: dict[str, Any],
    reason: str,
) -> None:
    conn.execute(
        """
        INSERT INTO operation_logs(
          actor, action_type, object_type, object_id, old_value, new_value,
          reason, result_status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'succeeded')
        """,
        (
            ACTOR,
            action_type,
            object_type,
            object_id,
            Jsonb(old_value),
            Jsonb(new_value),
            reason,
        ),
    )


def fix_evidence_locators(conn: Any) -> list[dict[str, Any]]:
    config = json.loads(
        (ROOT / "data" / "golden_vertical_fact_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    corrections: list[dict[str, Any]] = []
    for snapshot in config["source_snapshots"]:
        url = snapshot["url"]
        want_locator = snapshot["locator"]
        want_excerpt = snapshot["support_excerpt"]
        rows = conn.execute(
            """
            SELECT re.relationship_id, re.source_document_id, re.role::text,
                   re.locator, re.support_excerpt
            FROM relationship_evidence re
            JOIN source_documents sd ON sd.id = re.source_document_id
            JOIN relationships r ON r.id = re.relationship_id
            WHERE sd.url = %s AND r.derivation_rule = %s
            """,
            (url, PUBLISHED_RULE),
        ).fetchall()
        for rel_id, doc_id, role, old_locator, old_excerpt in rows:
            if old_locator == want_locator and old_excerpt == want_excerpt:
                continue
            conn.execute(
                """
                UPDATE relationship_evidence
                SET locator = %s, support_excerpt = %s
                WHERE relationship_id = %s AND source_document_id = %s
                  AND role = %s
                """,
                (want_locator, want_excerpt, rel_id, doc_id, role),
            )
            conn.execute(
                """
                UPDATE relationship_fact_candidate_evidence
                SET locator = %s, support_excerpt = %s
                WHERE source_document_id = %s
                """,
                (want_locator, want_excerpt, doc_id),
            )
            log_operation(
                conn,
                action_type="evidence_locator_correction",
                object_type="relationship_evidence",
                object_id=str(rel_id),
                old_value={
                    "source_document_id": str(doc_id),
                    "locator": old_locator,
                    "support_excerpt": old_excerpt,
                },
                new_value={
                    "source_document_id": str(doc_id),
                    "locator": want_locator,
                    "support_excerpt": want_excerpt,
                },
                reason=REASON_F04,
            )
            corrections.append(
                {
                    "relationship_id": str(rel_id),
                    "source_url": url,
                    "old_locator": old_locator,
                    "new_locator": want_locator,
                }
            )
    return corrections


def fix_published_entity_identity(conn: Any) -> list[dict[str, Any]]:
    corrections: list[dict[str, Any]] = []
    rows = conn.execute(
        """
        SELECT DISTINCT e.id, e.canonical_name, e.status
        FROM entities e
        JOIN relationships r
          ON e.id IN (r.subject_entity_id, r.object_entity_id)
        WHERE r.derivation_rule = %s AND e.status = 'fixture'
        """,
        (PUBLISHED_RULE,),
    ).fetchall()
    for entity_id, name, old_status in rows:
        conn.execute(
            "UPDATE entities SET status = 'research_target' WHERE id = %s",
            (entity_id,),
        )
        notice = conn.execute(
            "SELECT fixture_notice FROM fixture_entity_notices WHERE entity_id = %s",
            (entity_id,),
        ).fetchone()
        if notice:
            conn.execute(
                "DELETE FROM fixture_entity_notices WHERE entity_id = %s",
                (entity_id,),
            )
        log_operation(
            conn,
            action_type="published_entity_identity_correction",
            object_type="entity",
            object_id=str(entity_id),
            old_value={
                "status": old_status,
                "fixture_notice": notice[0] if notice else None,
            },
            new_value={"status": "research_target", "fixture_notice": None},
            reason=REASON_F02,
        )
        corrections.append(
            {"entity_id": str(entity_id), "canonical_name": name,
             "old_status": old_status, "new_status": "research_target"}
        )
    return corrections


def main() -> int:
    with connect_database() as conn:
        evidence_fixes = fix_evidence_locators(conn)
        entity_fixes = fix_published_entity_identity(conn)
        conn.commit()
    print(
        json.dumps(
            {
                "f04_evidence_corrections": evidence_fixes,
                "f02_entity_corrections": entity_fixes,
                "audited": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
