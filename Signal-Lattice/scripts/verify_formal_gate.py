#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.formal_identity import verify_subject_against_root
from signal_lattice.receipts import canonical_json_bytes, load_self_hashed, verify_self_hash



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    paths = {
        "upstream": root / "evidence/upstream/upstream_seal.json",
        "quant": root / "evidence/quant/quant_seal.json",
        "subject": root / "SUBJECT_LOCK.json",
        "review": root / "evidence/formal_review/review_chain.json",
        "stop": root / "evidence/owner_gate/stop_and_freeze.json",
    }
    findings: list[str] = []
    missing = [name for name, path in paths.items() if not path.is_file()]
    findings.extend("MISSING:" + name for name in missing)
    payloads: dict[str, dict] = {}
    for name, path in paths.items():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if name == "subject":
                findings.extend(verify_subject_against_root(data, root, require_frozen=True))
            else:
                if not verify_self_hash(data):
                    findings.append("SELF_HASH_INVALID:" + name)
            payloads[name] = data
        except Exception as exc:
            findings.append("INVALID_JSON:" + name + ":" + type(exc).__name__)
    canonical_path = root / "CANONICAL_STATE.json"
    if not canonical_path.is_file():
        findings.append("MISSING:canonical_state")
        canonical = {}
    else:
        try:
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            if canonical.get("current_phase") != "OWNER_GATE":
                findings.append("CURRENT_PHASE_NOT_OWNER_GATE")
            owner_gate = canonical.get("owner_gate", {})
            if owner_gate.get("eligible") is not True or owner_gate.get("qualifying_no_change_rounds", 0) < 2:
                findings.append("OWNER_GATE_NOT_ELIGIBLE")
        except Exception as exc:
            canonical = {}
            findings.append("INVALID_JSON:canonical_state:" + type(exc).__name__)
    freeze_path = root / "evidence/owner_gate/candidate_freeze.json"
    if not freeze_path.is_file():
        findings.append("MISSING:candidate_freeze")
    else:
        try:
            freeze = load_self_hashed(freeze_path)
            if freeze.get("state") != "PASS":
                findings.append("CANDIDATE_FREEZE_NOT_PASS")
        except Exception as exc:
            findings.append("INVALID_CANDIDATE_FREEZE:" + type(exc).__name__)

    baseline_path = root / "machine/facts/upstream_baseline.json"
    if baseline_path.is_file() and "upstream" in payloads:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        upstream = payloads["upstream"]
        if upstream.get("state") != "PASS":
            findings.append("UPSTREAM_NOT_PASS")
        if upstream.get("agent_commit") != baseline["agent_database"]["commit"]:
            findings.append("AGENT_COMMIT_MISMATCH")
        if upstream.get("meta_commit") != baseline["meta_database"]["commit"]:
            findings.append("META_COMMIT_MISMATCH")
        if upstream.get("skill_instance_count") != baseline["agent_database"]["skill_instance_count"]:
            findings.append("SKILL_COUNT_MISMATCH")
        if upstream.get("unique_slug_count") != baseline["agent_database"]["unique_slug_count"]:
            findings.append("SLUG_COUNT_MISMATCH")
        if upstream.get("stock_skill_count") != baseline["meta_database"]["stock_skill_count"]:
            findings.append("STOCK_SKILL_COUNT_MISMATCH")
        if any(value != "PASS" for value in upstream.get("validator_states", {}).values()):
            findings.append("UPSTREAM_VALIDATOR_NOT_PASS")
    if "quant" in payloads:
        if payloads["quant"].get("state") != "PASS":
            findings.append("QUANT_SEAL_NOT_PASS")
        if payloads["quant"].get("live_action_enabled") is not False:
            findings.append("LIVE_ACTION_MUST_REMAIN_DISABLED")
    subject_sha = payloads.get("subject", {}).get("subject_sha256")
    if "review" in payloads:
        review = payloads["review"]
        if review.get("state") != "PASS" or review.get("subject_sha256") != subject_sha:
            findings.append("REVIEW_CHAIN_NOT_PASS")
        if review.get("open_p0") != 0 or review.get("open_p1") != 0:
            findings.append("OPEN_P0_P1")
        if review.get("receipt_count") != 24:
            findings.append("FORMAL_RECEIPT_COUNT_MISMATCH")
    if "stop" in payloads:
        stop = payloads["stop"]
        if stop.get("state") != "PASS" or stop.get("decision") != "STOP_AND_FREEZE":
            findings.append("STOP_AND_FREEZE_NOT_PASS")
        if stop.get("subject_sha256") != subject_sha:
            findings.append("STOP_SUBJECT_MISMATCH")
        if stop.get("qualifying_round_count", 0) < 2:
            findings.append("NO_CHANGE_ROUNDS_INSUFFICIENT")
        if stop.get("frozen_replays_identical") is not True:
            findings.append("FROZEN_REPLAYS_NOT_IDENTICAL")
    state = "PASS" if not findings else "BLOCKED"
    result = {
        "schema_version": "1.0.0",
        "state": state,
        "owner_gate_ready": state == "PASS",
        "subject_sha256": subject_sha,
        "findings": sorted(set(findings)),
        "formal_receipts_required": 24,
        "runtime_agent_dependency": 0,
        "runtime_llm_token_budget": 0,
    }
    result["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
