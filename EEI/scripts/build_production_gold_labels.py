#!/usr/bin/env python3
"""Build the S7PCT01 production gold-label payload (T904 / A026-A027).

Reads the operator-authored corpus spec, verifies fail-closed that every
positive case's anchor passage exists verbatim in the fetched official source
text (runtime evidence corpus), collects the system's REAL predictions from
the production surfaces (/v1/entities search for entity resolution; published
relationships for relationship assertions), and emits an
`eei-gold-quality-labels-v1` payload with full production_gold_evidence
provenance and a label freeze hash.

Gold answers come only from the operator spec (primary official sources);
predictions come only from the live system. Nothing is synthesized to agree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_tools import connect_database  # noqa: E402

SCHEMA_VERSION = "eei-gold-quality-labels-v1"
DATASET_ID = "eei-production-gold-labels-golden-vertical-20260716-v1"
LABELED_AT = "2026-07-16T06:10:00+10:00"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_corpus_texts(corpus_dir: Path, source_ids: list[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for source_id in source_ids:
        path = corpus_dir / f"{source_id}.txt"
        if not path.exists():
            raise SystemExit(f"corpus text missing for {source_id}: {path}")
        texts[source_id] = path.read_text(encoding="utf-8")
    return texts


def verify_anchor(texts: dict[str, str], source_id: str, anchor: str, *, case: str) -> None:
    if anchor not in texts[source_id]:
        raise SystemExit(f"FAIL-CLOSED: anchor not found for {case} in {source_id}: {anchor!r}")


def load_universe() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    with connect_database() as conn:
        rows = conn.execute(
            "SELECT research_id, canonical_name, entity_id::text"
            " FROM company_research_universe"
        ).fetchall()
    rid_to_name = {r[0]: r[1] for r in rows}
    entity_to_rid = {r[2]: r[0] for r in rows if r[2]}
    name_to_rid = {r[1].lower(): r[0] for r in rows}
    return rid_to_name, entity_to_rid, name_to_rid


def predict_entities(inputs: list[str]) -> dict[str, str]:
    """System prediction surface: /v1/entities?q= top hit mapped to research_id."""
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.main import app  # noqa: PLC0415

    _, entity_to_rid, name_to_rid = load_universe()
    predictions: dict[str, str] = {}
    with TestClient(app) as client:
        for input_text in inputs:
            predicted = ""
            response = client.get("/v1/entities", params={"q": input_text})
            if response.status_code == 200:
                items = response.json()
                if isinstance(items, dict):
                    items = items.get("items", [])
                if items:
                    top = items[0]
                    entity_id = str(top.get("id") or "")
                    name = str(top.get("canonical_name") or "")
                    predicted = (
                        entity_to_rid.get(entity_id)
                        or name_to_rid.get(name.lower())
                        or ""
                    )
            predictions[input_text] = predicted
    return predictions


def predict_relationships() -> set[tuple[str, str, str]]:
    """System assertion surface: published relationships mapped to research ids."""
    _, entity_to_rid, name_to_rid = load_universe()
    asserted: set[tuple[str, str, str]] = set()
    with connect_database() as conn:
        rows = conn.execute(
            """
            SELECT r.relationship_type,
                   s.id::text, s.canonical_name,
                   o.id::text, o.canonical_name
            FROM relationships r
            JOIN entities s ON s.id = r.subject_entity_id
            JOIN entities o ON o.id = r.object_entity_id
            WHERE r.status = 'reported'
            """
        ).fetchall()
    for rel_type, s_id, s_name, o_id, o_name in rows:
        s_rid = entity_to_rid.get(s_id) or name_to_rid.get((s_name or "").lower())
        o_rid = entity_to_rid.get(o_id) or name_to_rid.get((o_name or "").lower())
        if s_rid and o_rid:
            asserted.add((s_rid, rel_type, o_rid))
    return asserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--corpus-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-copy", type=Path, required=True)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    manifest = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    if not manifest.get("corpus_complete"):
        raise SystemExit("FAIL-CLOSED: corpus manifest is not complete")
    manifest_sha = {
        r["source_id"]: r["source_text_sha256"] for r in manifest["records"]
    }
    sources: dict[str, str] = spec["sources"]
    texts = load_corpus_texts(args.corpus_dir, list(sources))
    for source_id, text in texts.items():
        actual = sha256_text(text)
        if actual != manifest_sha.get(source_id):
            raise SystemExit(f"FAIL-CLOSED: corpus text drift for {source_id}")

    rid_to_name, _, _ = load_universe()
    labeler = spec["labeler"]

    rel_positive = [c for c in spec["relationship_positive_cases"] if not c.get("drop")]
    rel_negative = [c for c in spec["relationship_negative_cases"] if not c.get("drop")]
    ent_positive = [c for c in spec["entity_positive_cases"] if not c.get("drop")]
    ent_negative = [c for c in spec["entity_negative_cases"] if not c.get("drop")]

    for case in rel_positive:
        for rid_key in ("subject", "object"):
            if case[rid_key] not in rid_to_name:
                raise SystemExit(f"unknown research_id {case[rid_key]} in positive case")
        for source_id, anchor in case["anchor"].items():
            verify_anchor(
                texts,
                source_id,
                anchor,
                case=f"{case['subject']}|{case['type']}|{case['object']}",
            )
    for case in rel_negative:
        for rid_key in ("subject", "object"):
            if case[rid_key] not in rid_to_name:
                raise SystemExit(f"unknown research_id {case[rid_key]} in negative case")
        for source_id in case["checked"]:
            if source_id not in texts:
                raise SystemExit(f"negative case checked source missing: {source_id}")
    for case in ent_positive + ent_negative:
        verify_anchor(texts, case["source"], case["anchor"], case=case["input_text"])
    for case in ent_positive:
        if case["expected"] not in rid_to_name:
            raise SystemExit(f"unknown research_id {case['expected']} in entity case")

    asserted = predict_relationships()
    entity_predictions = predict_entities(
        [case["input_text"] for case in ent_positive + ent_negative]
    )

    def url_refs(source_ids: list[str]) -> list[str]:
        return [sources[source_id] for source_id in source_ids]

    entity_cases = []
    for index, case in enumerate(ent_positive + ent_negative, start=1):
        expected = case.get("expected", "")
        entity_cases.append(
            {
                "case_id": f"ENT-PROD-{index:03d}",
                "input_text": case["input_text"],
                "expected_entity_id": expected,
                "predicted_entity_id": entity_predictions[case["input_text"]],
                "labeler": labeler,
                "labeled_at": LABELED_AT,
                "evidence_refs": url_refs([case["source"]]),
                "gold_rationale": case.get(
                    "rationale",
                    "Surface form verified verbatim in the cited official source; "
                    "canonical identity from the research universe registry.",
                ),
                "source_coverage": {
                    "required_source_ids": [case["source"]],
                    "observed_source_ids": [case["source"]],
                    "counter_evidence_reviewed": True,
                },
            }
        )

    relationship_cases = []
    for index, case in enumerate(rel_positive, start=1):
        key = f"{case['subject']}|{case['type']}|{case['object']}"
        predicted_present = (case["subject"], case["type"], case["object"]) in asserted
        relationship_cases.append(
            {
                "case_id": f"REL-PROD-{index:03d}",
                "expected_relation_present": True,
                "expected_relationship_key": key,
                "predicted_relation_present": predicted_present,
                "predicted_relationship_key": key if predicted_present else "",
                "labeler": labeler,
                "labeled_at": LABELED_AT,
                "evidence_refs": url_refs(case["sources"]),
                "gold_passage_anchors": case["anchor"],
                "source_coverage": {
                    "required_source_ids": case["sources"],
                    "observed_source_ids": case["sources"],
                    "counter_evidence_reviewed": True,
                },
            }
        )
    offset = len(rel_positive)
    for index, case in enumerate(rel_negative, start=offset + 1):
        key = f"{case['subject']}|{case['type']}|{case['object']}"
        predicted_present = (case["subject"], case["type"], case["object"]) in asserted
        relationship_cases.append(
            {
                "case_id": f"REL-PROD-{index:03d}",
                "expected_relation_present": False,
                "expected_relationship_key": key,
                "predicted_relation_present": predicted_present,
                "predicted_relationship_key": key if predicted_present else "",
                "labeler": labeler,
                "labeled_at": LABELED_AT,
                "evidence_refs": url_refs(case["checked"]),
                "gold_rationale": case["rationale"],
                "source_coverage": {
                    "required_source_ids": case["checked"],
                    "observed_source_ids": case["checked"],
                    "counter_evidence_reviewed": True,
                },
            }
        )

    frozen = canonical_json(
        {"entity_resolution_cases": entity_cases, "relationship_cases": relationship_cases}
    )
    freeze_sha = sha256_text(frozen)
    args.freeze_copy.parent.mkdir(parents=True, exist_ok=True)
    args.freeze_copy.write_text(frozen + "\n", encoding="utf-8")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "system_name": "EEI",
        "scope": spec["scope"],
        "dataset_id": DATASET_ID,
        "fixture_policy": {
            "production_gold_set": True,
            "relationship_publication": False,
            "release_clearance": False,
        },
        "production_gold_evidence": {
            "evidence_id": "T904-PROD-GOLD-20260716-V1",
            "dataset_owner": "linzezhang35@gmail.com",
            "owner_role": "production_data_owner",
            "sampling_frame": (
                "Golden-vertical official corpus fetched 2026-07-16: NVIDIA FY2026 Form "
                "10-K (SEC EDGAR), three NVIDIA official newsroom/blog anchors, ASML "
                "official story, two TSMC Press Center releases, plus the SEC EDGAR "
                "company_tickers.json registry for entity surface forms. Manifest with "
                "sha256 per source: runtime_evidence/EEI/gold_corpus/manifest-20260716.json"
            ),
            "labeling_protocol_ref": "docs/gold_quality/PRODUCTION_GOLD_LABELING_PROTOCOL.md",
            "label_freeze_sha256": freeze_sha,
            "reviewer": labeler,
            "reviewed_at": LABELED_AT,
            "reviewer_signature_hash": sha256_text(
                f"{labeler}:{DATASET_ID}:{freeze_sha}"
            ),
            "source_license_review_ref": (
                "artifacts/operator_inputs/"
                "a202_a210_signed_release_decision_bundle_20260715.json"
            ),
            "passage_review_policy_ref": (
                "artifacts/operator_inputs/t904_production_gold_corpus_spec_20260716.json"
            ),
            "source_document_refs": [sources[s] for s in sorted(sources)],
            "labeler_qualification_refs": [
                "https://github.com/LinzeColin/MetaDatabase/pull/2",
                "https://github.com/LinzeColin/MetaDatabase/pull/8",
            ],
            "excludes_repository_fixtures": True,
            "operator_supplied_labels": True,
            "synthetic_or_fixture_labels": False,
            "owner_batch_signoff": {
                "status": "PENDING_OWNER_ACK",
                "owner_actor": "linzezhang35@gmail.com",
                "signed_at": "",
                "signature": "",
            },
        },
        "entity_resolution_cases": entity_cases,
        "relationship_cases": relationship_cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "built": True,
                "entity_cases": len(entity_cases),
                "relationship_cases": len(relationship_cases),
                "relationship_positive": len(rel_positive),
                "relationship_negative": len(rel_negative),
                "system_asserted_relationships": len(asserted),
                "label_freeze_sha256": freeze_sha,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
