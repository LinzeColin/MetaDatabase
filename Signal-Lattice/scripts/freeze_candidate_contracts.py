#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.constants import VERSION
from signal_lattice.receipts import atomic_json, load_self_hashed, sha256_file

CONTRACTS = (
    "machine/facts/requirements.json",
    "machine/facts/task_dag.json",
    "machine/facts/traceability.json",
    "machine/facts/acceptance_contract.json",
    "machine/facts/definition_of_done.json",
    "machine/facts/release_boundary.json",
)
SNAPSHOT = "machine/facts/candidate_contract_snapshot.json"
SNAPSHOT_KEYS = (
    "project_id", "project_name", "product_version", "taskpack_version",
    "target_repository", "target_area", "target_domain", "runtime_node",
    "owner_approved_scope", "scope_state", "resource_ceiling", "cost_ceiling",
    "required_integrations", "forbidden_dependencies", "production_side_effect_authorization",
    "runtime_contract",
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("evidence/owner_gate/candidate_freeze.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    upstream = load_self_hashed(root / "evidence/upstream/upstream_seal.json")
    quant = load_self_hashed(root / "evidence/quant/quant_seal.json")
    if upstream.get("state") != "PASS":
        raise SystemExit("UPSTREAM_SEAL_NOT_PASS")
    if quant.get("state") != "PASS" or quant.get("live_action_enabled") is not False:
        raise SystemExit("QUANT_SEAL_NOT_PASS_OR_LIVE_ACTION_ENABLED")
    canonical_path = root / "CANONICAL_STATE.json"
    state = json.loads(canonical_path.read_text())
    latest = state.get("latest_iteration", {})
    if latest.get("open_p0") != 0 or latest.get("open_p1") != 0:
        raise SystemExit("OPEN_P0_P1_PREVENTS_FREEZE")
    scope_state = state.get("scope_state")
    if scope_state not in {"FROZEN_FOR_PREPACKAGE", "OWNER_APPROVED_SEALED_TASKPACK"}:
        raise SystemExit("SCOPE_NOT_FROZEN_FOR_PREPACKAGE")
    if scope_state == "OWNER_APPROVED_SEALED_TASKPACK":
        owner_gate = state.get("owner_gate", {})
        if state.get("current_phase") != "SEALED_TASKPACK":
            raise SystemExit("SEALED_TASKPACK_PHASE_REQUIRED")
        if owner_gate.get("owner_override_authorized") is not True:
            raise SystemExit("TASKPACK_OWNER_OVERRIDE_REQUIRED")
        if owner_gate.get("owner_override_scope") != "TASKPACK_SEAL_ONLY_NOT_RELEASE_PASS":
            raise SystemExit("TASKPACK_OWNER_OVERRIDE_SCOPE_INVALID")
    if state.get("product_version") != VERSION or state.get("taskpack_version") != VERSION:
        raise SystemExit("CANONICAL_VERSION_MISMATCH")

    originals: dict[Path, bytes | None] = {}
    staged: dict[Path, bytes] = {}
    before: dict[str, str | None] = {}
    for rel in CONTRACTS:
        path = root / rel
        originals[path] = path.read_bytes()
        before[rel] = sha256_file(path)
        data = json.loads(originals[path])
        data["frozen"] = True
        data["frozen_version"] = VERSION
        data["freeze_contract"] = "NO_DYNAMIC_SCOPE_ACCEPTANCE_OR_TEST_EXPANSION"
        staged[path] = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

    snapshot_path = root / SNAPSHOT
    originals[snapshot_path] = snapshot_path.read_bytes() if snapshot_path.exists() else None
    before[SNAPSHOT] = sha256_file(snapshot_path) if snapshot_path.exists() else None
    snapshot = {
        "schema_version": "1.0.0",
        "frozen": True,
        "frozen_version": VERSION,
        "source_canonical_state_sha256": sha256_file(canonical_path),
        "contract": {key: state.get(key) for key in SNAPSHOT_KEYS},
        "mutable_operational_fields_excluded": ["current_phase", "owner_gate", "latest_iteration", "root_blockers", "context_calibration"],
    }
    staged[snapshot_path] = (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

    try:
        for path, body in staged.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        after = {path.relative_to(root).as_posix(): sha256_file(path) for path in staged}
        payload = {
            "schema_version": "1.0.0",
            "state": "PASS",
            "version": VERSION,
            "upstream_seal_sha256": sha256_file(root / "evidence/upstream/upstream_seal.json"),
            "quant_seal_sha256": sha256_file(root / "evidence/quant/quant_seal.json"),
            "canonical_state_sha256_at_freeze": sha256_file(canonical_path),
            "before_sha256": before,
            "after_sha256": after,
            "contract_count": len(staged),
            "dynamic_scope_expansion_allowed": False,
            "dynamic_acceptance_expansion_allowed": False,
            "runtime_agent_dependency": 0,
            "runtime_llm_token_budget": 0,
        }
        atomic_json(output, payload)
    except Exception:
        for path, body in originals.items():
            if body is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(body)
        raise
    print(json.dumps({"state": "PASS", "contract_count": len(staged), "output": output.as_posix()}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
