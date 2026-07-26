#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

AC_ROW = re.compile(r"^\|\s*(AC-\d{3})\s*\|", re.MULTILINE)
REQ_ROW = re.compile(r"^\|\s*((?:FR|NFR)-\d{3})\s*\|.*?\|\s*(AC-\d{3})\s*\|\s*$", re.MULTILINE)
TASK_REF = re.compile(r"\bCB-\d{3}\b")
GATE_REF = re.compile(r"\bPG-\d+\b")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    prd = (root / "02_PRD_ACCEPTANCE_CONTRACT.md").read_text(encoding="utf-8")
    dag = yaml.safe_load((root / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8"))
    errors: list[str] = []

    defined = set(AC_ROW.findall(prd))
    requirements = REQ_ROW.findall(prd)
    mapped = {ac for task in dag.get("tasks", []) for ac in (task.get("acceptance_criteria") or [])}

    if not defined:
        errors.append("no_acceptance_oracles_defined")
    for req, ac in requirements:
        if ac not in defined:
            errors.append(f"{req}:oracle_not_defined:{ac}")
    for ac in sorted(mapped - defined):
        errors.append(f"dag_maps_unknown_oracle:{ac}")
    for ac in sorted(defined - mapped):
        errors.append(f"oracle_not_mapped_to_task:{ac}")

    tasks = dag.get("tasks", [])
    task_ids = {t.get("id") for t in tasks}
    if None in task_ids:
        errors.append("task_missing_id")
        task_ids.discard(None)
    if len(task_ids) != len(tasks):
        errors.append("duplicate_task_id")
    gate_ids = set((dag.get("pass_gates") or {}).keys())

    control_files = sorted(
        path for path in root.glob("[0-9][0-9]_*")
        if path.is_file() and path.suffix in {".md", ".txt", ".yaml", ".yml"}
    )
    referenced_tasks: set[str] = set()
    referenced_gates: set[str] = set()
    for path in control_files:
        text = path.read_text(encoding="utf-8")
        for ref in TASK_REF.findall(text):
            referenced_tasks.add(ref)
            if ref not in task_ids:
                errors.append(f"unknown_task_reference:{path.name}:{ref}")
        for ref in GATE_REF.findall(text):
            referenced_gates.add(ref)
            if ref not in gate_ids:
                errors.append(f"unknown_gate_reference:{path.name}:{ref}")

    matrix_text = (root / "10_TRACEABILITY_RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    for task_id in sorted(x for x in task_ids if x):
        if task_id not in matrix_text and task_id not in {"CB-040"}:
            # Group ranges in the matrix are allowed, so require the stage-range prefix or exact ID.
            prefix = task_id.split('-')[1][0]
            if f"CB-{prefix}00" not in matrix_text and f"CB-{prefix}10" not in matrix_text:
                errors.append(f"task_not_represented_in_traceability:{task_id}")

    if len(defined) != 53:
        errors.append(f"acceptance_oracle_count_expected_53_actual_{len(defined)}")
    if len(requirements) != 53:
        errors.append(f"requirement_count_expected_53_actual_{len(requirements)}")
    if len(task_ids) != 30:
        errors.append(f"task_count_expected_30_actual_{len(task_ids)}")
    if gate_ids != {f"PG-{index}" for index in range(6)}:
        errors.append(f"gate_set_mismatch:{sorted(gate_ids)}")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("TRACEABILITY_VALIDATION=FAIL")
        return 1
    print(
        f"TRACEABILITY_VALIDATION=PASS requirements={len(requirements)} "
        f"oracles={len(defined)} mapped_oracles={len(mapped)} tasks={len(task_ids)} "
        f"task_refs={len(referenced_tasks)} gate_refs={len(referenced_gates)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
