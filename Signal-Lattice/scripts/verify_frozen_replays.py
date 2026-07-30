#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.receipts import atomic_json, load_self_hashed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    first = load_self_hashed(args.first)
    second = load_self_hashed(args.second)
    findings = []
    if first.get("state") != "PASS" or second.get("state") != "PASS":
        findings.append("REPLAY_NOT_PASS")
    if first.get("subject_sha256") != second.get("subject_sha256"):
        findings.append("REPLAY_SUBJECT_MISMATCH")
    if first.get("gate_fingerprint") != second.get("gate_fingerprint"):
        findings.append("REPLAY_FINGERPRINT_MISMATCH")
    state = "PASS" if not findings else "BLOCKED"
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "subject_sha256": first.get("subject_sha256"),
        "frozen_replays_identical": not findings,
        "first_fingerprint": first.get("gate_fingerprint"),
        "second_fingerprint": second.get("gate_fingerprint"),
        "findings": findings,
    }
    atomic_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
