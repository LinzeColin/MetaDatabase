#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file

EXPECTED = {
    "VERIFIER": 3,
    "TELEIOSIS_SCOPED": 3,
    "PERSONA_GROUP_SCOPED": 3,
    "PANEL_ROUND_1": 6,
    "PANEL_ROUND_2": 6,
    "SECOND_MODEL": 1,
    "FINAL_INDEPENDENT": 1,
    "FRESH_BUILDER": 1,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-lock", type=Path, required=True)
    parser.add_argument("--review-input", type=Path, required=True)
    parser.add_argument("--receipts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    findings: list[str] = []
    try:
        subject = json.loads(args.subject_lock.read_text(encoding="utf-8"))
        review_input = load_self_hashed(args.review_input)
    except Exception as exc:
        payload = {"schema_version": "1.0.0", "state": "BLOCKED", "reason": type(exc).__name__, "findings": [str(exc)]}
        atomic_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    subject_sha = subject.get("subject_sha256")
    input_sha = sha256_file(args.review_input)
    if subject.get("state") != "FROZEN":
        findings.append("SUBJECT_NOT_FROZEN")
    if review_input.get("state") != "PASS" or review_input.get("subject_sha256") != subject_sha:
        findings.append("REVIEW_INPUT_SUBJECT_MISMATCH")
    receipts: list[dict] = []
    if not args.receipts_dir.is_dir():
        findings.append("RECEIPTS_DIR_MISSING")
    else:
        for path in sorted(args.receipts_dir.glob("*.json")):
            try:
                row = load_self_hashed(path)
                row["path"] = path.name
                receipts.append(row)
            except Exception:
                findings.append("RECEIPT_INVALID:" + path.name)
    counts = Counter(str(row.get("review_type")) for row in receipts)
    if dict(counts) != EXPECTED:
        findings.append("REVIEW_TYPE_COUNT_MISMATCH")
    ids = [str(row.get("review_id")) for row in receipts]
    runs = [str(row.get("provider_run_id")) for row in receipts]
    if len(ids) != len(set(ids)):
        findings.append("DUPLICATE_REVIEW_ID")
    if len(runs) != len(set(runs)):
        findings.append("DUPLICATE_PROVIDER_RUN_ID")
    panel_identities = [str(row.get("reviewer_identity")) for row in receipts if str(row.get("review_type", "")).startswith("PANEL_ROUND_")]
    if len(panel_identities) != len(set(panel_identities)):
        findings.append("DUPLICATE_PANEL_REVIEWER_IDENTITY")
    special_identities = [str(row.get("reviewer_identity")) for row in receipts if row.get("review_type") in {"SECOND_MODEL", "FINAL_INDEPENDENT"}]
    if set(panel_identities) & set(special_identities):
        findings.append("SPECIAL_REVIEWER_REUSED_FROM_PANEL")
    open_p0 = open_p1 = 0
    normalized: list[dict] = []
    for row in receipts:
        if row.get("subject_sha256") != subject_sha:
            findings.append("RECEIPT_SUBJECT_MISMATCH:" + str(row.get("review_id")))
        if row.get("input_sha256") != input_sha:
            findings.append("RECEIPT_INPUT_MISMATCH:" + str(row.get("review_id")))
        if row.get("context_isolation") != "ISOLATED" or row.get("independent_from_builder") is not True:
            findings.append("RECEIPT_INDEPENDENCE_INVALID:" + str(row.get("review_id")))
        if row.get("verdict") != "PASS":
            findings.append("RECEIPT_VERDICT_NOT_PASS:" + str(row.get("review_id")))
        for finding in row.get("findings", []):
            if finding.get("state") == "OPEN" and finding.get("severity") == "P0":
                open_p0 += 1
            if finding.get("state") == "OPEN" and finding.get("severity") == "P1":
                open_p1 += 1
        normalized.append({
            "path": row.get("path"),
            "review_id": row.get("review_id"),
            "review_type": row.get("review_type"),
            "reviewer_identity": row.get("reviewer_identity"),
            "provider_run_id": row.get("provider_run_id"),
            "verdict": row.get("verdict"),
            "receipt_sha256": row.get("receipt_sha256"),
        })
    if open_p0:
        findings.append("OPEN_P0_FINDINGS")
    if open_p1:
        findings.append("OPEN_P1_FINDINGS")
    state = "PASS" if not findings else "BLOCKED"
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "subject_sha256": subject_sha,
        "input_sha256": input_sha,
        "counts": dict(sorted(counts.items())),
        "receipt_count": len(receipts),
        "open_p0": open_p0,
        "open_p1": open_p1,
        "receipts": normalized,
        "findings": sorted(set(findings)),
        "formal_independence": state == "PASS",
    }
    atomic_json(args.output, payload)
    print(json.dumps({"state": state, "receipt_count": len(receipts), "findings": payload["findings"]}, ensure_ascii=False, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
