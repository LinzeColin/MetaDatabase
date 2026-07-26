#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

FORBIDDEN_KEYS = {
    "target_elapsed_hours",
    "soak_hours",
    "soak_days",
    "observation_hours",
    "observation_days",
    "wait_until",
    "not_before",
    "scheduled_after",
}
SHELL_SLEEP = re.compile(r"^\s*(?:command\s+)?sleep(?:\s|$)", re.MULTILINE)
WAIT_DEP = re.compile(r"^(?:ACT|WAIT|CREDENTIAL)-", re.IGNORECASE)


def walk(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_KEYS:
                errors.append(f"forbidden_timing_key:{path}.{key_text}")
            walk(child, f"{path}.{key_text}", errors)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            walk(child, f"{path}[{i}]", errors)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []

    dag_path = root / "04_TASK_DAG_EXECUTION_PACK.yaml"
    if not dag_path.is_file():
        errors.append("task_dag_missing")
    else:
        dag = yaml.safe_load(dag_path.read_text(encoding="utf-8"))
        walk(dag, "dag", errors)
        facts = dag.get("canonical_facts", {})
        if facts.get("real_time_soak_gate") is not False:
            errors.append("real_time_soak_gate_must_be_false")
        if facts.get("credential_wait_blocks_development") is not False:
            errors.append("credential_wait_blocks_development_must_be_false")
        validation = dag.get("dag_validation", {})
        if validation.get("real_time_soak_nodes") != 0:
            errors.append("real_time_soak_nodes_must_equal_0")
        if validation.get("credential_wait_nodes") != 0:
            errors.append("credential_wait_nodes_must_equal_0")
        for task in dag.get("tasks", []):
            task_id = task.get("id", "unknown")
            for dep in task.get("dependencies") or []:
                if WAIT_DEP.match(str(dep)):
                    errors.append(f"{task_id}:external_wait_dependency:{dep}")
            if "effort_points" not in task:
                errors.append(f"{task_id}:missing_effort_points")

    for folder in (root / "implementation-kit" / "scripts", root / "implementation-kit" / "simulators"):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*.sh")):
            text = path.read_text(encoding="utf-8")
            if SHELL_SLEEP.search(text):
                errors.append(f"fixed_sleep_command:{path.relative_to(root)}")

    for filename in ("deploy-release.sh", "rollback-release.sh"):
        path = root / "implementation-kit" / "scripts" / filename
        if path.is_file() and "wait-ready.sh" not in path.read_text(encoding="utf-8"):
            errors.append(f"predicate_readiness_missing:{path.relative_to(root)}")

    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("NO_WAIT_VALIDATION=FAIL")
        return 1
    print("NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
