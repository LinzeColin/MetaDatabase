#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.receipts import atomic_json, sha256_file

BINDINGS = {
    "subject_lock": "SUBJECT_LOCK.json",
    "upstream_seal": "evidence/upstream/upstream_seal.json",
    "quant_seal": "evidence/quant/quant_seal.json",
    "candidate_contract_snapshot": "machine/facts/candidate_contract_snapshot.json",
    "requirements": "machine/facts/requirements.json",
    "acceptance_contract": "machine/facts/acceptance_contract.json",
    "task_dag": "machine/facts/task_dag.json",
    "traceability": "machine/facts/traceability.json",
    "definition_of_done": "machine/facts/definition_of_done.json",
    "release_boundary": "machine/facts/release_boundary.json",
    "task_execution_contract": "machine/facts/task_execution_contract.json",
    "freeze_receipt": "evidence/owner_gate/candidate_freeze.json",
    "manifest": "MANIFEST.json",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    missing = [rel for rel in BINDINGS.values() if not (root / rel).is_file()]
    if missing:
        payload = {"schema_version": "1.0.0", "state": "BLOCKED", "reason": "REVIEW_INPUT_BINDING_MISSING", "missing": missing}
        atomic_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    subject = json.loads((root / BINDINGS["subject_lock"]).read_text(encoding="utf-8"))
    if subject.get("state") != "FROZEN":
        payload = {"schema_version": "1.0.0", "state": "BLOCKED", "reason": "SUBJECT_NOT_FROZEN", "subject_state": subject.get("state")}
        atomic_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "subject_sha256": subject["subject_sha256"],
        "bindings": {name: {"path": rel, "sha256": sha256_file(root / rel)} for name, rel in BINDINGS.items()},
        "review_contract": {
            "builder_code_modification_allowed": False,
            "unknown_not_run_waived_are_pass": False,
            "required_review_types": {
                "VERIFIER": 3,
                "TELEIOSIS_SCOPED": 3,
                "PERSONA_GROUP_SCOPED": 3,
                "PANEL_ROUND_1": 6,
                "PANEL_ROUND_2": 6,
                "SECOND_MODEL": 1,
                "FINAL_INDEPENDENT": 1,
                "FRESH_BUILDER": 1
            },
            "open_p0_p1_allowed": False,
            "independent_context_required": True,
            "independent_from_builder_required": True
        }
    }
    atomic_json(args.output, payload)
    print(json.dumps({"state": "PASS", "subject_sha256": payload["subject_sha256"], "output": args.output.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
