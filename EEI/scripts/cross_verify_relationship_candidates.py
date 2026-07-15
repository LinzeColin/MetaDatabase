#!/usr/bin/env python3
"""Second-source cross-verification for golden-vertical relationship candidates.

S7PAT02 / T1301 / ACC-A202.

For every relationship candidate this pipeline captures each referenced
official source (reusing the audited T1301 live-capture machinery and its
token/alias engine) and decides, deterministically:

- a source *supports* a candidate when transport succeeded, extracted text is
  long enough, the subject AND object entity tokens both matched, and at least
  one relationship-type keyword matched;
- a candidate is ``CORROBORATED`` only when >= ``source_threshold_min``
  supporting sources come from publisher-independent origins;
- non-empty ``counter_evidence`` forces ``CONFLICTED``;
- every non-corroborated candidate is routed to ``manual_review_queue``.

Nothing here publishes relationship facts; all release gates stay fail-closed.

Modes: ``--generate-contract`` / ``--validate-contract`` (no network),
``--capture-live --allow-live-network`` (real captures), ``--captures PATH``
(offline re-verification of a prior capture payload), ``--enqueue`` (write
manual_review_queue rows; requires DATABASE_URL; idempotent via queue_key).
"""

from __future__ import annotations

import argparse
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

from scripts import fetch_official_source_full_text as official_source  # noqa: E402

SCHEMA_VERSION = "eei-second-source-cross-verification-v1"
TASK_ID = "S7PAT02"
LEGACY_TASK_ID = "T1301"
ACCEPTANCE_IDS = ["A202"]
CANDIDATES_PATH = ROOT / "data/golden_vertical_fact_candidates.json"
CONTRACT_ARTIFACT = (
    ROOT / "artifacts/tests/a202/t1301_second_source_cross_verification_contract.json"
)

# Relationship-type keyword policy: a supporting source must match at least one
# keyword for the candidate's relationship_type (entity tokens are mandatory).
RELATION_KEYWORDS: dict[str, list[str]] = {
    "wafer_foundry_for": ["foundry", "foundries", "wafer"],
    "equipment_provider_to": ["lithography", "EUV", "DUV", "equipment"],
}

CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE_SOURCE"
CONFLICTED = "CONFLICTED"
UNVERIFIED = "UNVERIFIED"
QUEUE_PRIORITY = {SINGLE_SOURCE: "P1", CONFLICTED: "P0", UNVERIFIED: "P0"}

ROW_ID_SEPARATOR = "@"


class CrossVerificationError(ValueError):
    pass


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def load_candidates(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("source_snapshots", "relationship_candidates", "source_threshold_min"):
        if key not in payload:
            raise CrossVerificationError(f"candidates file missing key: {key}")
    return payload


def policy_fingerprint() -> str:
    canonical = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "relation_keywords": RELATION_KEYWORDS,
            "queue_priority": QUEUE_PRIORITY,
            "support_rule": "transport_ok AND subject AND object AND any(relation_keyword)",
            "token_alias_policy_version": official_source.TOKEN_ALIAS_POLICY_VERSION,
            "min_text_chars": official_source.MIN_TEXT_CHARS,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def relation_keywords_for(relationship_type: str) -> list[str]:
    keywords = RELATION_KEYWORDS.get(relationship_type)
    if not keywords:
        raise CrossVerificationError(
            f"no keyword policy registered for relationship_type {relationship_type!r};"
            " extend RELATION_KEYWORDS before verifying this candidate"
        )
    return keywords


def capture_rows_for_candidates(candidates_payload: dict[str, Any]) -> list[dict[str, str]]:
    """One capture row per (candidate, referenced source) with the candidate's
    entity pair and relation keywords as expected tokens."""
    snapshots = {str(s["anchor_id"]): s for s in candidates_payload["source_snapshots"]}
    rows: list[dict[str, str]] = []
    for candidate in candidates_payload["relationship_candidates"]:
        candidate_key = str(candidate["candidate_key"])
        expected = [
            str(candidate["subject_candidate_name"]),
            str(candidate["object_candidate_name"]),
            *relation_keywords_for(str(candidate["relationship_type"])),
        ]
        referenced = [str(candidate["source_anchor_id"])] + [
            str(x) for x in candidate.get("supporting_source_anchor_ids", [])
        ]
        for anchor_id in referenced:
            snapshot = snapshots.get(anchor_id)
            if snapshot is None:
                raise CrossVerificationError(
                    f"candidate {candidate_key} references unknown snapshot {anchor_id}"
                )
            rows.append(
                {
                    "anchor_id": f"{candidate_key}{ROW_ID_SEPARATOR}{anchor_id}",
                    "url": str(snapshot["url"]),
                    "source_date": str(snapshot.get("source_date", "")),
                    "title": str(snapshot.get("title", "")),
                    "official_publisher": str(snapshot.get("official_publisher", "")),
                    "expected_entities_or_stages": "; ".join(expected),
                    "evidence_scope": str(snapshot.get("evidence_scope", "")),
                    "validation_status": str(snapshot.get("validation_status", "")),
                    "notes": "cross-verification probe row (S7PAT02); no publication",
                }
            )
    return rows


def anchors_by_row_id(capture_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    anchors = capture_payload.get("anchors")
    if not isinstance(anchors, list):
        raise CrossVerificationError("capture payload missing anchors list")
    return {str(anchor.get("anchor_id")): anchor for anchor in anchors}


def source_verdict(
    anchor: dict[str, Any] | None,
    *,
    subject: str,
    object_: str,
    keywords: list[str],
) -> dict[str, Any]:
    if anchor is None:
        return {
            "captured": False,
            "transport_ok": False,
            "subject_matched": False,
            "object_matched": False,
            "keyword_matched": False,
            "supports_relationship": False,
        }
    health = anchor.get("source_health") or {}
    missing = {str(t).casefold() for t in health.get("missing_tokens", [])}
    http_status = int(health.get("http_status") or 0)
    text_chars = int(health.get("text_char_count") or 0)
    transport_ok = 0 < http_status < 400 and text_chars >= official_source.MIN_TEXT_CHARS
    subject_matched = subject.casefold() not in missing
    object_matched = object_.casefold() not in missing
    keyword_matched = any(k.casefold() not in missing for k in keywords)
    supports = transport_ok and subject_matched and object_matched and keyword_matched
    return {
        "captured": True,
        "transport_ok": transport_ok,
        "http_status": http_status,
        "text_char_count": text_chars,
        "health_status": health.get("status"),
        "subject_matched": subject_matched,
        "object_matched": object_matched,
        "keyword_matched": keyword_matched,
        "missing_tokens": sorted(missing),
        "source_text_sha256": anchor.get("source_text_sha256"),
        "supports_relationship": supports,
    }


def normalize_publisher(publisher: str) -> str:
    return publisher.split("/")[-1].strip().casefold() or publisher.strip().casefold()


def cross_verify(
    candidates_payload: dict[str, Any],
    capture_payload: dict[str, Any],
) -> dict[str, Any]:
    snapshots = {str(s["anchor_id"]): s for s in candidates_payload["source_snapshots"]}
    anchors = anchors_by_row_id(capture_payload)
    threshold = int(candidates_payload["source_threshold_min"])
    results = []
    for candidate in candidates_payload["relationship_candidates"]:
        candidate_key = str(candidate["candidate_key"])
        subject = str(candidate["subject_candidate_name"])
        object_ = str(candidate["object_candidate_name"])
        relationship_type = str(candidate["relationship_type"])
        keywords = relation_keywords_for(relationship_type)
        referenced = [str(candidate["source_anchor_id"])] + [
            str(x) for x in candidate.get("supporting_source_anchor_ids", [])
        ]
        source_reports = []
        supporting_publishers: set[str] = set()
        for anchor_id in referenced:
            snapshot = snapshots.get(anchor_id, {})
            verdict = source_verdict(
                anchors.get(f"{candidate_key}{ROW_ID_SEPARATOR}{anchor_id}"),
                subject=subject,
                object_=object_,
                keywords=keywords,
            )
            verdict["anchor_id"] = anchor_id
            verdict["official_publisher"] = snapshot.get("official_publisher")
            source_reports.append(verdict)
            if verdict["supports_relationship"]:
                supporting_publishers.add(
                    normalize_publisher(str(snapshot.get("official_publisher", "")))
                )

        supporting_count = sum(1 for r in source_reports if r["supports_relationship"])
        independent_publishers = len(supporting_publishers)
        counter_evidence = candidate.get("counter_evidence") or []
        if counter_evidence:
            status = CONFLICTED
        elif supporting_count >= threshold and independent_publishers >= threshold:
            status = CORROBORATED
        elif supporting_count >= 1:
            # Includes the same-publisher case: multiple supporting captures from
            # one origin still count as a single independent source.
            status = SINGLE_SOURCE
        else:
            status = UNVERIFIED
        results.append(
            {
                "candidate_key": candidate_key,
                "subject": subject,
                "object": object_,
                "relationship_type": relationship_type,
                "referenced_anchor_ids": referenced,
                "supporting_source_count": supporting_count,
                "independent_publisher_count": independent_publishers,
                "required_threshold": threshold,
                "counter_evidence_present": bool(counter_evidence),
                "corroboration_status": status,
                "queue_required": status != CORROBORATED,
                "queue_priority": QUEUE_PRIORITY.get(status),
                "sources": source_reports,
            }
        )
    corroborated = sum(1 for r in results if r["corroboration_status"] == CORROBORATED)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "legacy_task_id": LEGACY_TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now_iso(),
        "policy_fingerprint": policy_fingerprint(),
        "capture_status": capture_payload.get("status"),
        "counts": {
            "candidates_total": len(results),
            "corroborated": corroborated,
            "queue_required": len(results) - corroborated,
        },
        "release_scope": {
            "relationship_publication_performed": False,
            "release_clearance": False,
            "a202_closed_by_cross_verification": False,
            "mvp_release_ready": False,
        },
        "results": results,
    }


def build_queue_rows(verification: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for result in verification["results"]:
        if not result["queue_required"]:
            continue
        rows.append(
            {
                "queue_key": f"second-source:{result['candidate_key']}",
                "object_type": "relationship_fact_candidate",
                "candidate_key": result["candidate_key"],
                "reason": (
                    "second-source cross-verification status "
                    f"{result['corroboration_status']}: supporting_sources="
                    f"{result['supporting_source_count']}, independent_publishers="
                    f"{result['independent_publisher_count']}, required_threshold="
                    f"{result['required_threshold']}"
                ),
                "priority": result["queue_priority"],
                "requested_by": "cross_verify_relationship_candidates",
            }
        )
    return rows


def enqueue_rows(
    rows: list[dict[str, str]],
    database_url: str,
    *,
    corroborated_candidate_keys: list[str] | None = None,
) -> dict[str, Any]:
    import psycopg

    inserted, skipped, missing, auto_resolved = [], [], [], []
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        # Machine-opened second-source queue items whose condition has cleared
        # are auto-resolved; human-opened items are never touched.
        for candidate_key in corroborated_candidate_keys or []:
            cur.execute(
                """
                UPDATE manual_review_queue
                SET status = 'resolved',
                    resolved_at = now(),
                    reviewer = 'cross_verify_relationship_candidates',
                    decision = 'auto_resolved_second_source_corroborated'
                WHERE queue_key = %s
                  AND status = 'open'
                  AND requested_by = 'cross_verify_relationship_candidates'
                RETURNING queue_key
                """,
                (f"second-source:{candidate_key}",),
            )
            if cur.fetchone():
                auto_resolved.append(f"second-source:{candidate_key}")
        for row in rows:
            cur.execute(
                "SELECT id FROM relationship_fact_candidates WHERE candidate_key = %s",
                (row["candidate_key"],),
            )
            found = cur.fetchone()
            if not found:
                missing.append(row["candidate_key"])
                continue
            cur.execute(
                """
                INSERT INTO manual_review_queue
                  (queue_key, object_type, object_id, reason, priority, status, requested_by)
                VALUES (%s, %s, %s, %s, %s, 'open', %s)
                ON CONFLICT (queue_key) DO NOTHING
                RETURNING queue_key
                """,
                (
                    row["queue_key"],
                    row["object_type"],
                    found[0],
                    row["reason"],
                    row["priority"],
                    row["requested_by"],
                ),
            )
            if cur.fetchone():
                inserted.append(row["queue_key"])
            else:
                skipped.append(row["queue_key"])
        conn.commit()
    return {
        "database_write_performed": bool(inserted or auto_resolved),
        "queue_inserted": inserted,
        "queue_already_present": skipped,
        "queue_auto_resolved": auto_resolved,
        "db_candidate_missing": missing,
    }


def build_contract_artifact() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "legacy_task_id": LEGACY_TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "status": "CONTRACT_ONLY_NO_NETWORK",
        "generated_at": utc_now_iso(),
        "policy_fingerprint": policy_fingerprint(),
        "method": {
            "support_rule": (
                "a source supports a candidate only when transport succeeded, extracted "
                "text length >= min_text_chars, subject and object entity tokens both "
                "matched through the audited token/alias engine, and at least one "
                "relationship-type keyword matched"
            ),
            "corroboration_rule": (
                "CORROBORATED requires >= source_threshold_min supporting sources from "
                "publisher-independent origins"
            ),
            "conflict_rule": "non-empty counter_evidence forces CONFLICTED",
            "queue_rule": "every non-CORROBORATED candidate is enqueued to manual_review_queue",
            "publication_rule": "this pipeline never publishes; all release gates stay closed",
        },
        "relation_keywords": RELATION_KEYWORDS,
        "token_alias_policy_version": official_source.TOKEN_ALIAS_POLICY_VERSION,
        "min_text_chars": official_source.MIN_TEXT_CHARS,
        "statuses": [CORROBORATED, SINGLE_SOURCE, CONFLICTED, UNVERIFIED],
        "queue_priority": QUEUE_PRIORITY,
        "candidates_registry": CANDIDATES_PATH.relative_to(ROOT).as_posix(),
        "release_scope": {
            "live_network_performed": False,
            "database_write_performed": False,
            "relationship_publication_performed": False,
            "a202_closed_by_contract": False,
            "mvp_release_ready": False,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_PATH)
    parser.add_argument("--generate-contract", action="store_true")
    parser.add_argument("--validate-contract", action="store_true")
    parser.add_argument("--capture-live", action="store_true")
    parser.add_argument("--allow-live-network", action="store_true")
    parser.add_argument("--captures", type=Path, default=None)
    parser.add_argument("--enqueue", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.generate_contract:
        payload = build_contract_artifact()
        write_json(args.output or CONTRACT_ARTIFACT, payload)
        if not args.quiet:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.validate_contract:
        if not CONTRACT_ARTIFACT.exists():
            print("Cross-verification contract validation: FAIL - artifact missing")
            return 1
        committed = json.loads(CONTRACT_ARTIFACT.read_text(encoding="utf-8"))
        ok = (
            committed.get("schema_version") == SCHEMA_VERSION
            and committed.get("policy_fingerprint") == policy_fingerprint()
            and committed.get("release_scope", {}).get("mvp_release_ready") is False
        )
        print(
            "Cross-verification contract validation: "
            + ("PASS" if ok else "FAIL - policy fingerprint or schema drift")
        )
        return 0 if ok else 1

    candidates_payload = load_candidates(args.candidates)

    if args.capture_live:
        if not args.allow_live_network:
            print(
                json.dumps(
                    {
                        "status": "LIVE_NETWORK_NOT_ALLOWED",
                        "reason": "--capture-live requires --allow-live-network",
                    },
                    indent=2,
                )
            )
            return 2
        rows = capture_rows_for_candidates(candidates_payload)
        # SEC (and good citizenship generally) requires a descriptive User-Agent
        # with a contact address; reuse the operator's SEC_USER_AGENT when set.
        user_agent = os.environ.get("SEC_USER_AGENT", "").strip() or (
            "EEI/0.1 official-source-retrieval "
            "(Enterprise Ecosystem Intelligence; contact=operator)"
        )
        with httpx.Client(
            timeout=official_source.DEFAULT_LIVE_TIMEOUT_SECONDS,
            headers={"User-Agent": user_agent},
        ) as live_client:
            capture_payload = official_source.capture_live_official_sources(
                rows=rows, client=live_client
            )
        capture_payload["user_agent_evidence"] = {
            "value_recorded": False,
            "sha256": hashlib.sha256(user_agent.encode("utf-8")).hexdigest(),
            "contact_email_present": "@" in user_agent,
        }
    elif args.captures:
        capture_payload = json.loads(args.captures.read_text(encoding="utf-8"))
    else:
        parser.error(
            "one of --capture-live, --captures, --generate-contract,"
            " --validate-contract is required"
        )
        return 2

    verification = cross_verify(candidates_payload, capture_payload)
    verification["queue_rows_planned"] = build_queue_rows(verification)

    if args.enqueue:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise CrossVerificationError("--enqueue requires DATABASE_URL")
        verification["queue_execution"] = enqueue_rows(
            verification["queue_rows_planned"],
            database_url,
            corroborated_candidate_keys=[
                r["candidate_key"]
                for r in verification["results"]
                if r["corroboration_status"] == CORROBORATED
            ],
        )
    else:
        verification["queue_execution"] = {
            "database_write_performed": False,
            "note": "dry-run: pass --enqueue to write manual_review_queue",
        }

    if args.output:
        write_json(args.output, verification)
    if not args.quiet:
        print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
