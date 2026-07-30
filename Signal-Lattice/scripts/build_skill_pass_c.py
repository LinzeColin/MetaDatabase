#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.formal_identity import verify_subject_against_root
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("evidence/skill_router/pass_c.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    findings: list[str] = []
    try:
        canonical = json.loads((root / "CANONICAL_STATE.json").read_text(encoding="utf-8"))
        subject = json.loads((root / "SUBJECT_LOCK.json").read_text(encoding="utf-8"))
    except Exception as exc:
        canonical, subject = {}, {}
        findings.append("FORMAL_INPUT_INVALID:" + type(exc).__name__)
    findings.extend(verify_subject_against_root(subject, root, require_frozen=True))
    if canonical.get("current_phase") != "OWNER_GATE":
        findings.append("CURRENT_PHASE_NOT_OWNER_GATE")
    gate = canonical.get("owner_gate", {})
    if gate.get("eligible") is not True or gate.get("qualifying_no_change_rounds", 0) < 2:
        findings.append("OWNER_GATE_NOT_ELIGIBLE")

    bindings: dict[str, str] = {}
    required = {
        "upstream_seal": root / "evidence/upstream/upstream_seal.json",
        "quant_seal": root / "evidence/quant/quant_seal.json",
        "review_chain": root / "evidence/formal_review/review_chain.json",
        "replay_comparison": root / "evidence/owner_gate/frozen_replay_comparison.json",
        "stop_and_freeze": root / "evidence/owner_gate/stop_and_freeze.json",
    }
    for name, path in required.items():
        try:
            data = load_self_hashed(path)
            if data.get("state") != "PASS":
                findings.append(name.upper() + "_NOT_PASS")
            if name in {"review_chain", "stop_and_freeze"} and data.get("subject_sha256") != subject.get("subject_sha256"):
                findings.append(name.upper() + "_SUBJECT_MISMATCH")
            bindings[name] = sha256_file(path)
        except Exception:
            findings.append(name.upper() + "_MISSING_OR_INVALID")

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(root / "src"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
    }
    formal = subprocess.run(
        [sys.executable, "scripts/verify_formal_gate.py", "--root", str(root)],
        cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
    )
    if formal.returncode != 0:
        findings.append("FORMAL_GATE_NOT_PASS")
    package = subprocess.run(
        [sys.executable, "scripts/verify_package.py", "--root", str(root), "--manifest", str(root / "MANIFEST.json")],
        cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300,
    )
    if package.returncode != 0:
        findings.append("PACKAGE_GUARD_NOT_PASS")

    state = "PASS" if not findings else "BLOCKED_NOT_READY"
    payload = {
        "schema_version": "1.0.0",
        "candidate_version": VERSION,
        "pass": "C",
        "scope": "FROZEN_FINAL",
        "state": state,
        "formal_pass_claimed": state == "PASS",
        "subject_sha256": subject.get("subject_sha256"),
        "bindings": bindings,
        "selected_methods": ["verifier", "teleiosis-scoped", "persona-distiller-group-scoped", "fresh-builder"],
        "open_p0": 0 if state == "PASS" else None,
        "open_p1": 0 if state == "PASS" else None,
        "findings": sorted(set(findings)),
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
    }
    atomic_json(output, payload)
    print(json.dumps({"state": state, "findings": payload["findings"], "output": output.as_posix()}, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
