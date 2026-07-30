#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

OPEN_DECISION = re.compile(r"(?i)(自行研究|自行选择|自行设计|自行决定|choose an approach|research the repository|design the schema)")
FORBIDDEN_SKILLS = {"teleiosis", "persona-distiller", "persona-distiller-group", "verifier", "market-research", "product-definition"}
REQUIRED_FIELDS = {
    "task_id", "title", "mode", "environment_bound", "environment_bound_reason",
    "authorization_required", "authorization_env", "commands", "required_env",
    "timeout_seconds", "allow_degraded", "expected", "failure_branch",
    "stop_condition", "rollback", "evidence_path",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def command_target_exists(root: Path, command: list[str]) -> bool:
    if len(command) < 2:
        return True
    candidate = command[1]
    if candidate.startswith("scripts/") or candidate.startswith("machine/"):
        return (root / candidate).is_file()
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[str] = []

    contract = json.loads((root / "machine/facts/task_execution_contract.json").read_text())
    dag = json.loads((root / "machine/facts/task_dag.json").read_text())
    allowlist = json.loads((root / "machine/facts/build_agent_skill_allowlist.json").read_text())
    tasks = contract.get("tasks", [])
    if {row.get("task_id") for row in tasks} != {row.get("id") for row in dag.get("tasks", [])}:
        findings.append("TASK_SET_MISMATCH")
    for task in tasks:
        missing = sorted(REQUIRED_FIELDS - set(task))
        if missing:
            findings.append(f"TASK_FIELDS_MISSING:{task.get('task_id')}:{','.join(missing)}")
            continue
        text = json.dumps(task, ensure_ascii=False)
        if OPEN_DECISION.search(text):
            findings.append(f"OPEN_DECISION_LANGUAGE:{task['task_id']}")
        if task["environment_bound"] and not task["environment_bound_reason"]:
            findings.append(f"ENVIRONMENT_REASON_MISSING:{task['task_id']}")
        if task["authorization_required"] and task.get("mode") != "AUTHORIZED_SIDE_EFFECT":
            findings.append(f"SIDE_EFFECT_MODE_INVALID:{task['task_id']}")
        if task["authorization_required"] and task.get("authorization_env") != "SIGNAL_LATTICE_APPLY":
            findings.append(f"SIDE_EFFECT_AUTHORIZATION_INVALID:{task['task_id']}")
        if task.get("mode") == "AUTHORIZED_SIDE_EFFECT" and not task["authorization_required"]:
            findings.append(f"SIDE_EFFECT_AUTHORIZATION_MISSING:{task['task_id']}")
        if not task["commands"]:
            findings.append(f"COMMAND_MISSING:{task['task_id']}")
        for command in task["commands"]:
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                findings.append(f"COMMAND_INVALID:{task['task_id']}")
            elif not command_target_exists(root, command):
                findings.append(f"COMMAND_TARGET_MISSING:{task['task_id']}:{command[1]}")
        if not str(task["evidence_path"]).startswith("{ARTIFACT_DIR}/"):
            findings.append(f"EVIDENCE_PATH_NOT_ARTIFACT_BOUND:{task['task_id']}")
    allowed = {row["slug"] for row in allowlist.get("allowed", [])}
    forbidden = set(allowlist.get("forbidden", []))
    if allowed & forbidden:
        findings.append("SKILL_ALLOWLIST_CONFLICT")
    if not FORBIDDEN_SKILLS.issubset(forbidden):
        findings.append("MANDATORY_FORBIDDEN_SKILL_MISSING")

    environment_tasks = [row["task_id"] for row in tasks if row["environment_bound"]]
    preparation_tasks = [row["task_id"] for row in tasks if not row["environment_bound"]]
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "state": "PASS" if not findings else "FAIL",
        "assessment_scope": "DETERMINISTIC_STATIC_BUILDER_READINESS_NOT_FORMAL_FRESH_CONTEXT",
        "task_count": len(tasks),
        "environment_bound_task_count": len(environment_tasks),
        "preparation_task_count": len(preparation_tasks),
        "environment_bound_tasks": environment_tasks,
        "non_environment_unknown_count": 0 if not findings else None,
        "open_decision_count": len([x for x in findings if x.startswith("OPEN_DECISION_LANGUAGE")]),
        "developer_research_required": False if not findings else None,
        "formal_fresh_builder_simulation_required": True,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "findings": sorted(set(findings)),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    print(json.dumps({"state": receipt["state"], "receipt_sha256": receipt["receipt_sha256"]}, ensure_ascii=False))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
