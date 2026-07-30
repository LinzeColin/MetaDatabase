#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.formal_identity import subject_identity_sha256, subject_rows


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"REQUIRED_BINDING_MISSING:{path}")
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        raise SystemExit(f"REQUIRED_BINDING_INVALID:{path}:{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"REQUIRED_BINDING_NOT_OBJECT:{path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", choices=["PREPARED", "FROZEN"], default="PREPARED")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    seal = root / "evidence/upstream/upstream_seal.json"
    precheck = root / "evidence/upstream/upstream_precheck.json"
    if seal.is_file():
        upstream_data = require_json(seal)
        if upstream_data.get("state") != "PASS":
            raise SystemExit("UPSTREAM_SEAL_NOT_PASS")
        upstream_binding = seal
    elif args.state == "PREPARED":
        upstream_data = require_json(precheck)
        if upstream_data.get("state") != "BLOCKED" or upstream_data.get("formal_seal_present") is not False:
            raise SystemExit("UPSTREAM_PRECHECK_NOT_FAIL_CLOSED")
        upstream_binding = precheck
    else:
        raise SystemExit("FROZEN_SUBJECT_REQUIRES_UPSTREAM_SEAL")

    required_bindings = {
        "upstream": upstream_binding,
        "quant": root / "evidence/quant/quant_seal.json",
        "acceptance": root / "machine/facts/acceptance_contract.json",
        "requirements": root / "machine/facts/requirements.json",
        "task_dag": root / "machine/facts/task_dag.json",
        "traceability": root / "machine/facts/traceability.json",
        "definition_of_done": root / "machine/facts/definition_of_done.json",
        "release_boundary": root / "machine/facts/release_boundary.json",
    }
    if args.state == "FROZEN":
        required_bindings["candidate_contract_snapshot"] = root / "machine/facts/candidate_contract_snapshot.json"
        freeze_receipt = root / "evidence/owner_gate/candidate_freeze.json"
        freeze_data = require_json(freeze_receipt)
        from signal_lattice.receipts import verify_self_hash
        if freeze_data.get("state") != "PASS" or not verify_self_hash(freeze_data):
            raise SystemExit("FROZEN_SUBJECT_REQUIRES_VALID_FREEZE_RECEIPT")
        for name in ("requirements", "task_dag", "traceability", "acceptance", "definition_of_done", "release_boundary"):
            data = require_json(required_bindings[name])
            if data.get("frozen") is not True:
                raise SystemExit("FROZEN_CONTRACT_REQUIRED:" + name)
        required_bindings["freeze_receipt"] = freeze_receipt
    else:
        required_bindings["canonical_state_prepared"] = root / "CANONICAL_STATE.json"
    bindings = {name: sha(path) for name, path in required_bindings.items() if require_json(path) is not None}

    rows = subject_rows(root)

    identity = {"files": rows, "bindings": bindings}
    body = {
        "schema_version": "1.1.0",
        "version": "0.0.0.1.39",
        "state": args.state,
        "upstream_binding_kind": "formal_seal" if seal.is_file() else "blocked_precheck",
        "files": rows,
        "bindings": bindings,
        "subject_sha256": subject_identity_sha256(rows, bindings),
    }
    args.output.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"state": args.state, "subject_sha256": body["subject_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
