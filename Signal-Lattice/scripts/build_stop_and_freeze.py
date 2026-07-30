#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-lock", type=Path, required=True)
    parser.add_argument("--review-chain", type=Path, required=True)
    parser.add_argument("--replay-comparison", type=Path, required=True)
    parser.add_argument("--round-receipt", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    subject = json.loads(args.subject_lock.read_text(encoding="utf-8"))
    review = load_self_hashed(args.review_chain)
    replay = load_self_hashed(args.replay_comparison)
    rounds = [load_self_hashed(path) for path in args.round_receipt]
    findings: list[str] = []
    subject_sha = subject.get("subject_sha256")
    if subject.get("state") != "FROZEN":
        findings.append("SUBJECT_NOT_FROZEN")
    if review.get("state") != "PASS" or review.get("subject_sha256") != subject_sha:
        findings.append("REVIEW_CHAIN_NOT_PASS")
    if review.get("open_p0") != 0 or review.get("open_p1") != 0:
        findings.append("OPEN_P0_P1_FINDINGS")
    if replay.get("state") != "PASS" or replay.get("frozen_replays_identical") is not True:
        findings.append("FROZEN_REPLAYS_NOT_IDENTICAL")
    if len(rounds) != 2:
        findings.append("EXACTLY_TWO_QUALIFYING_ROUNDS_REQUIRED")
    if len({row.get("round_id") for row in rounds}) != len(rounds):
        findings.append("DUPLICATE_ROUND_ID")
    qualifying = [row for row in rounds if row.get("subject_sha256") == subject_sha and row.get("qualifying_no_change_round") is True]
    if len(qualifying) != 2:
        findings.append("QUALIFYING_NO_CHANGE_ROUNDS_INSUFFICIENT")
    if len(rounds) == 2:
        first, second = rounds
        if not isinstance(first.get("sequence"), int) or second.get("sequence") != first.get("sequence") + 1:
            findings.append("NO_CHANGE_ROUNDS_NOT_CONSECUTIVE")
        expected_previous = sha256_file(args.round_receipt[0])
        if second.get("previous_receipt_sha256") != expected_previous:
            findings.append("NO_CHANGE_ROUND_CHAIN_BROKEN")
    state = "PASS" if not findings else "BLOCKED"
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "subject_sha256": subject_sha,
        "qualifying_round_count": len(qualifying),
        "open_p0": review.get("open_p0", -1),
        "open_p1": review.get("open_p1", -1),
        "frozen_replays_identical": replay.get("frozen_replays_identical") is True,
        "decision": "STOP_AND_FREEZE" if state == "PASS" else "CONTINUE_REMEDIATION",
        "negative_marginal_value": state == "PASS",
        "scope_pollution_risk": state == "PASS",
        "findings": findings,
    }
    atomic_json(args.output, payload)
    print(json.dumps({"state": state, "decision": payload["decision"], "findings": findings}, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
