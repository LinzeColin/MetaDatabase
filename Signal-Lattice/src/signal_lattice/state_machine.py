from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PHASES = (
    "CONTEXT_CAPTURE", "RESEARCH_AND_REUSE", "PREBUILD", "TEN_LENS_REVIEW",
    "REMEDIATION", "BUILDER_READINESS", "OWNER_GATE", "SEALED_TASKPACK",
    "BUILD_LAST_MILE", "FROZEN_CANDIDATE", "VERIFY_AND_RELEASE",
    "POST_DEPLOY_OBSERVATION",
)

@dataclass(frozen=True)
class StateValidation:
    state: str
    findings: tuple[str, ...]
    current_phase: str | None


def load_state(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("CANONICAL_STATE_NOT_OBJECT")
    return data


def validate_state(data: dict[str, Any], expected_version: str) -> StateValidation:
    findings: list[str] = []
    phase = data.get("current_phase")
    if phase not in PHASES:
        findings.append("INVALID_CURRENT_PHASE")
    if tuple(data.get("state_machine", ())) != PHASES:
        findings.append("STATE_MACHINE_DRIFT")
    if data.get("product_version") != expected_version:
        findings.append("PRODUCT_VERSION_DRIFT")
    if data.get("taskpack_version") != expected_version:
        findings.append("TASKPACK_VERSION_DRIFT")
    runtime = data.get("runtime_contract", {})
    expected_runtime = {
        "agent_dependency": 0,
        "model_mode": "DISABLED",
        "token_budget": 0,
        "automatic_trading": False,
        "upstream_writeback": False,
        "macos_runtime": False,
    }
    for key, expected in expected_runtime.items():
        if runtime.get(key) != expected:
            findings.append(f"RUNTIME_CONTRACT_DRIFT:{key}")
    gate = data.get("owner_gate", {})
    rounds = gate.get("qualifying_no_change_rounds")
    required = gate.get("required_rounds")
    if not isinstance(rounds, int) or not isinstance(required, int) or rounds < 0 or required != 2:
        findings.append("OWNER_GATE_COUNTER_INVALID")
    override = gate.get("owner_override_authorized") is True
    if override:
        if gate.get("owner_override_scope") != "TASKPACK_SEAL_ONLY_NOT_RELEASE_PASS":
            findings.append("OWNER_GATE_OVERRIDE_SCOPE_INVALID")
        if gate.get("owner_approval_receipt") != "evidence/owner_gate/taskpack_owner_approval.json":
            findings.append("OWNER_GATE_OVERRIDE_RECEIPT_INVALID")
    expected_eligible = bool(isinstance(rounds, int) and rounds >= 2) or override
    if bool(gate.get("eligible")) != expected_eligible:
        findings.append("OWNER_GATE_ELIGIBILITY_MISMATCH")
    if phase in PHASES[PHASES.index("SEALED_TASKPACK"):] and not expected_eligible:
        findings.append("SEALED_OR_LATER_PHASE_REQUIRES_OWNER_GATE")
    return StateValidation("PASS" if not findings else "FAIL", tuple(findings), phase if isinstance(phase, str) else None)


def can_transition(current: str, target: str) -> bool:
    if current not in PHASES or target not in PHASES:
        return False
    return PHASES.index(target) == PHASES.index(current) + 1
