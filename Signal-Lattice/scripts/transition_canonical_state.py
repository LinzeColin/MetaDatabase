#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.formal_identity import verify_subject_against_root
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file
from signal_lattice.state_machine import can_transition, load_state, validate_state


def atomic_plain_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def require_pass(path: Path, reason: str) -> dict:
    data = load_self_hashed(path)
    if data.get("state") != "PASS":
        raise SystemExit(reason)
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    state_path = root / "CANONICAL_STATE.json"
    before = load_state(state_path)
    validation = validate_state(before, VERSION)
    if validation.state != "PASS":
        raise SystemExit("CANONICAL_STATE_INVALID:" + ",".join(validation.findings))
    current = str(before.get("current_phase"))
    target = args.target
    if not can_transition(current, target):
        raise SystemExit(f"NON_SEQUENTIAL_STATE_TRANSITION:{current}->{target}")

    subject_path = root / "SUBJECT_LOCK.json"
    subject = json.loads(subject_path.read_text(encoding="utf-8")) if subject_path.is_file() else {}
    subject_sha = subject.get("subject_sha256")
    gate_bindings: dict[str, str] = {}

    if target == "BUILDER_READINESS":
        findings = verify_subject_against_root(subject, root, require_frozen=True)
        if findings:
            raise SystemExit("FROZEN_SUBJECT_INVALID:" + ",".join(findings[:5]))
        freeze = require_pass(root / "evidence/owner_gate/candidate_freeze.json", "CANDIDATE_FREEZE_NOT_PASS")
        review_input = require_pass(root / "evidence/formal_review/review_input.json", "REVIEW_INPUT_NOT_PASS")
        if review_input.get("subject_sha256") != subject_sha:
            raise SystemExit("REVIEW_INPUT_SUBJECT_MISMATCH")
        gate_bindings = {
            "subject_lock": sha256_file(subject_path),
            "candidate_freeze": freeze["receipt_sha256"],
            "review_input": review_input["receipt_sha256"],
        }
    elif target == "OWNER_GATE":
        findings = verify_subject_against_root(subject, root, require_frozen=True)
        if findings:
            raise SystemExit("FROZEN_SUBJECT_INVALID:" + ",".join(findings[:5]))
        review = require_pass(root / "evidence/formal_review/review_chain.json", "REVIEW_CHAIN_NOT_PASS")
        replay = require_pass(root / "evidence/owner_gate/frozen_replay_comparison.json", "FROZEN_REPLAY_NOT_PASS")
        stop = require_pass(root / "evidence/owner_gate/stop_and_freeze.json", "STOP_AND_FREEZE_NOT_PASS")
        if review.get("subject_sha256") != subject_sha or stop.get("subject_sha256") != subject_sha:
            raise SystemExit("OWNER_GATE_SUBJECT_MISMATCH")
        if stop.get("decision") != "STOP_AND_FREEZE" or stop.get("qualifying_round_count", 0) < 2:
            raise SystemExit("OWNER_GATE_STOP_CONTRACT_NOT_MET")
        if replay.get("frozen_replays_identical") is not True:
            raise SystemExit("OWNER_GATE_REPLAY_NOT_IDENTICAL")
        gate_bindings = {
            "subject_lock": sha256_file(subject_path),
            "review_chain": review["receipt_sha256"],
            "frozen_replay_comparison": replay["receipt_sha256"],
            "stop_and_freeze": stop["receipt_sha256"],
        }
    else:
        raise SystemExit("UNSUPPORTED_AUTOMATED_TRANSITION:" + target)

    before_sha = sha256_file(state_path)
    after = json.loads(json.dumps(before))
    after["current_phase"] = target
    if target == "BUILDER_READINESS":
        after["root_blockers"] = [
            row for row in after.get("root_blockers", []) if row.get("id") != "B-UPSTREAM-SEAL"
        ]
    if target == "OWNER_GATE":
        stop = load_self_hashed(root / "evidence/owner_gate/stop_and_freeze.json")
        after["owner_gate"] = {
            "eligible": True,
            "qualifying_no_change_rounds": int(stop.get("qualifying_round_count", 0)),
            "required_rounds": 2,
        }
        after["root_blockers"] = []
    atomic_plain_json(state_path, after)
    post = validate_state(load_state(state_path), VERSION)
    if post.state != "PASS":
        atomic_plain_json(state_path, before)
        raise SystemExit("TRANSITION_RESULT_INVALID:" + ",".join(post.findings))

    output = args.output if args.output.is_absolute() else root / args.output
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "version": VERSION,
        "from_phase": current,
        "to_phase": target,
        "subject_sha256": subject_sha,
        "canonical_state_before_sha256": before_sha,
        "canonical_state_after_sha256": sha256_file(state_path),
        "gate_bindings": gate_bindings,
        "runtime_agent_dependency": 0,
        "runtime_llm_token_budget": 0,
    }
    atomic_json(output, payload)
    print(json.dumps({"state": "PASS", "from": current, "to": target, "output": output.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
