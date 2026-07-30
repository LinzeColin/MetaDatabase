#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.formal_identity import verify_subject_against_root
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file, canonical_json_bytes

CHECKS = (
    ("unit_tests", ["bash", "scripts/run_tests.sh"], 900),
    ("dual_plane", ["python3", "machine/tools/check_dual_plane_ci.py", "--root", ".", "--projects", ".", "--require-projects"], 180),
    ("canonical_state", ["python3", "scripts/verify_canonical_state.py"], 120),
    ("package_guard", ["python3", "scripts/verify_package.py", "--root", ".", "--manifest", "MANIFEST.json"], 300),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--review-chain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    subject_path = root / "SUBJECT_LOCK.json"
    required = {
        "subject": subject_path,
        "upstream": root / "evidence/upstream/upstream_seal.json",
        "quant": root / "evidence/quant/quant_seal.json",
        "review_chain": args.review_chain,
        "manifest": root / "MANIFEST.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        payload = {"schema_version": "1.0.0", "state": "BLOCKED", "reason": "FROZEN_REPLAY_INPUT_MISSING", "missing": missing}
        atomic_json(args.output, payload)
        print(json.dumps(payload, sort_keys=True))
        return 2
    subject = json.loads(subject_path.read_text(encoding="utf-8"))
    upstream = load_self_hashed(required["upstream"])
    quant = load_self_hashed(required["quant"])
    review = load_self_hashed(required["review_chain"])
    findings: list[str] = []
    findings.extend(verify_subject_against_root(subject, root, require_frozen=True))
    if upstream.get("state") != "PASS":
        findings.append("UPSTREAM_NOT_PASS")
    if quant.get("state") != "PASS":
        findings.append("QUANT_NOT_PASS")
    if review.get("state") != "PASS" or review.get("subject_sha256") != subject.get("subject_sha256"):
        findings.append("REVIEW_CHAIN_NOT_PASS")
    results = []
    env = {k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "PYTHONHOME"}}
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONHASHSEED"] = "0"
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    for check_id, command, timeout in CHECKS:
        completed = subprocess.run(command, cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        results.append({"check_id": check_id, "returncode": completed.returncode})
        if completed.returncode != 0:
            findings.append("CHECK_FAILED:" + check_id)
    stable = {
        "subject_sha256": subject.get("subject_sha256"),
        "bindings": {name: sha256_file(path) for name, path in required.items()},
        "checks": results,
    }
    fingerprint = hashlib.sha256(canonical_json_bytes(stable)).hexdigest()
    state = "PASS" if not findings else "BLOCKED"
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "subject_sha256": subject.get("subject_sha256"),
        "gate_fingerprint": fingerprint,
        "checks": results,
        "bindings": stable["bindings"],
        "findings": findings,
    }
    atomic_json(args.output, payload)
    print(json.dumps({"state": state, "gate_fingerprint": fingerprint, "findings": findings}, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
