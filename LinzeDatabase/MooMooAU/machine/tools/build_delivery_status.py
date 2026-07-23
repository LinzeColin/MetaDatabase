#!/usr/bin/env python3
"""Build the sole cross-dimensional MooMooAU delivery status deterministically."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validate_assurance_reviews import evaluate_immutable_predecessor  # noqa: E402
from validate_evidence import (  # noqa: E402
    validate_record,
    validate_stage6_candidate_bundle,
)
from validate_production_composition import validate as validate_composition  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    MATRIX_PATH as WORKFLOW_MATRIX_PATH,
)
from validate_workflow_matrix import (  # noqa: E402
    validate_contract as validate_workflow_contract,
)

from machine.acceptance.evidence import validate_bundle  # noqa: E402

sys.dont_write_bytecode = True

MODEL_PATH = Path("machine/contracts/delivery_status_model.json")
STATUS_PATH = Path("machine/status/latest.json")
ACCEPTANCE_SUMMARY_PATH = Path("evidence/acceptance/latest.json")
PRODUCTION_COMPOSITION_PATH = Path("machine/contracts/production_composition.json")
ASSURANCE_REVIEW_ROOT = Path("machine/stages/S6/reviews")
PROTECTED_BETA_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0702/execution-receipt.json")
PROTECTED_BETA_RECEIPT_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-beta-execution-receipt-v1.schema.json"
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _tree_digest(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _select_transition_state(
    model: dict[str, Any],
    assurance_result: dict[str, Any],
    protected_beta_receipt: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    states = model.get("states")
    if not isinstance(states, dict) or set(states) != {
        "PRE_CLOSURE",
        "DEPENDENCY_AUTH_READY",
        "PROTECTED_BETA_ATTEMPT_FAILED",
    }:
        raise ValueError("delivery status transition states differ")
    if assurance_result.get("status") != "PASS":
        state_name = "PRE_CLOSURE"
    elif protected_beta_receipt is not None:
        state_name = "PROTECTED_BETA_ATTEMPT_FAILED"
    else:
        state_name = "DEPENDENCY_AUTH_READY"
    state = states.get(state_name)
    if not isinstance(state, dict):
        raise ValueError("delivery status transition state is invalid")
    return state_name, cast(dict[str, Any], state)


def _protected_beta_receipt(root: Path) -> dict[str, Any] | None:
    path = root / PROTECTED_BETA_RECEIPT_PATH
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError("protected Beta receipt path is unsafe")
    schema = _load(root / PROTECTED_BETA_RECEIPT_SCHEMA_PATH)
    receipt = _load(path)
    if list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(receipt)
    ):
        raise ValueError("protected Beta receipt violates its exact schema")
    return cast(dict[str, Any], receipt)


def _assurance_result(root: Path) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            evaluate_immutable_predecessor(root, root.parents[1]),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"status": "BLOCKED", "errors": ["assurance provenance evaluation failed"]}


def _validate_composition_for_state(
    root: Path,
    state: dict[str, Any],
) -> dict[str, object]:
    # Historical cumulative jobs do not install later-stage runtime dependencies. The exact
    # v1.0.6 source/workflow hashes remain mandatory here; Stage 7 still executes the CLI.
    return cast(
        dict[str, object],
        validate_composition(
            root,
            verify_contract_cli=state.get("package_version") != "1.0.6",
        ),
    )


def _assurance_paths(root: Path) -> list[Path]:
    review_root = root / ASSURANCE_REVIEW_ROOT
    paths = [path for path in review_root.glob("*.json") if path.is_file()]
    rmd05 = review_root / "rmd05"
    paths.extend(path for path in rmd05.rglob("*") if path.is_file())
    if not paths:
        raise ValueError("RMD-05 assurance provenance is missing")
    return paths


def _verify_inherited_contracts(root: Path, model: dict[str, Any]) -> None:
    for relative, expected in model["inherited_contract_hashes"].items():
        path = root / relative
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise ValueError(f"inherited contract drift: {relative}")
    legacy = model["legacy_manifest"]
    legacy_path = root / legacy["path"]
    if (
        not legacy_path.is_file()
        or legacy_path.is_symlink()
        or _sha256(legacy_path) != legacy["sha256"]
    ):
        raise ValueError("legacy v1.0.1 manifest drift")


def _validate_final_summary(
    root: Path, summary: dict[str, Any], acceptance_contract: dict[str, Any]
) -> None:
    expected_ids = [item["id"] for item in acceptance_contract["acceptance_contracts"]]
    passed = summary.get("passed_acceptance_ids")
    blocked = summary.get("blocked_acceptance_ids")
    if (
        summary.get("schema_version") != "moomooau.acceptance-summary.v1"
        or summary.get("status") != "BLOCKED"
        or summary.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
        or summary.get("total_acceptances") != len(expected_ids)
        or summary.get("final_acceptances_passed") != 0
        or summary.get("final_acceptances_blocked") != len(expected_ids)
        or passed != []
        or blocked != expected_ids
    ):
        raise ValueError("final Acceptance summary is not the exact blocked 0/34 state")
    records = sorted((root / "evidence/acceptance").glob("AC-*.json"))
    if len(records) != len(expected_ids):
        raise ValueError("final Acceptance record count mismatch")
    counters = summary.get("prohibition_counters")
    if not isinstance(counters, dict) or any(
        type(value) is not int or value != 0 for value in counters.values()
    ):
        raise ValueError("final Acceptance prohibition counters are not zero")


def _mechanism_status(
    root: Path,
    stage_id: str,
    stage_tasks: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> str:
    if stage_id == "S0":
        if any(task["status"] != "completed" for task in stage_tasks) or any(
            record.get("record_status") != "VALID" or record.get("delivery_status") != "PASS"
            for record in records
        ):
            raise ValueError("Stage 0 baseline is not complete")
        return "BASELINE_COMPLETE"

    stage_number = stage_id.removeprefix("S")
    legacy_path = root / f"machine/stages/{stage_id}/contracts/task_status.json"
    legacy = _load(legacy_path)
    expected_task_ids = [task["id"] for task in stage_tasks]
    legacy_tasks = legacy.get("tasks", [])
    if [item.get("id") for item in legacy_tasks] != expected_task_ids:
        raise ValueError(f"{stage_id} mechanism source task binding mismatch")

    if stage_id in {"S1", "S2", "S3", "S4", "S5", "S6"}:
        if any(item.get("status") != "completed" for item in legacy_tasks) or any(
            record.get("record_status") != "PASS" for record in records
        ):
            raise ValueError(f"{stage_id} local mechanism evidence is incomplete")
        return "LOCAL_SYNTHETIC_MECHANISMS_EVIDENCED"

    if (
        stage_number != "7"
        or legacy.get("implementation_completion_status") != "LOCAL_MECHANISMS_READY"
        or any(record.get("record_status") not in {"READY", "BLOCKED"} for record in records)
        or any(
            check.get("status") != "PASS"
            for record in records
            for check in record.get("checks", [])
        )
    ):
        raise ValueError("Stage 7 local preflight mechanism evidence is incomplete")
    return "LOCAL_PREFLIGHT_MECHANISMS_EVIDENCED"


def _validate_stage6_evidence_transition(
    root: Path,
    state: dict[str, Any],
    records_by_task: dict[str, dict[str, Any]],
    *,
    repository_root: Path | None = None,
) -> None:
    stage6_records = [records_by_task[f"T060{index}"] for index in range(1, 9)]
    versions = {record.get("schema_version") for record in stage6_records}
    package_version = state.get("package_version")
    if package_version == "1.0.4":
        if versions != {"moomooau.stage6-evidence.v1"}:
            raise ValueError("pre-closure delivery state requires Stage 6 v1 evidence")
        return
    if package_version not in {"1.0.5", "1.0.6"} or versions != {"moomooau.stage6-evidence.v2"}:
        raise ValueError("closed delivery state requires Stage 6 v2 evidence")
    # v1.0.5 itself remains Git-anchored. Its v1.0.6 control successor is portable:
    # evaluate_immutable_predecessor has already verified the exact frozen authority
    # bytes against the immutable v1.0.5 Manifest, while this call verifies bindings.
    bundle_repository_root = repository_root if package_version == "1.0.5" else None
    bundle_errors = validate_stage6_candidate_bundle(root, bundle_repository_root)
    if bundle_errors:
        raise ValueError("closed delivery state lacks candidate-bound Stage 6 evidence")


def build_status(
    root: Path = PROJECT_ROOT,
    *,
    assurance_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    model = _load(root / MODEL_PATH)
    if (
        model.get("schema_version") != "moomooau.delivery-status-model.v3"
        or model.get("transition") != "RMD-06_PROTECTED_ACCEPTANCE_PREPARATION"
        or model.get("authority", {}).get("current_status") != STATUS_PATH.as_posix()
    ):
        raise ValueError("delivery status model identity mismatch")
    _verify_inherited_contracts(root, model)
    protected_receipt = _protected_beta_receipt(root)
    state_name, state = _select_transition_state(
        model,
        _assurance_result(root) if assurance_result is None else assurance_result,
        protected_receipt,
    )

    workflow_matrix = _load(root / WORKFLOW_MATRIX_PATH)
    matrix_errors = validate_workflow_contract(root, workflow_matrix)
    observation = workflow_matrix.get("observation", {})
    if (
        matrix_errors
        or "REV-P1-004" not in state.get("resolved_review_findings", [])
        or not isinstance(observation, dict)
        or observation.get("status") != "PASS"
        or observation.get("cumulative_passed") != 4
        or observation.get("historical_fail_closed") != 4
        or observation.get("tree_mutations") != 0
        or observation.get("protected_oracles_executed") != 0
        or observation.get("production_workflow_runs") != 0
        or observation.get("remote_workflow_runs") != 0
        or observation.get("external_writes") != 0
        or observation.get("remote_publications") != 0
    ):
        raise ValueError("RMD-03 Workflow command matrix is incomplete or overstated")

    composition = _load(root / PRODUCTION_COMPOSITION_PATH)
    composition_result = _validate_composition_for_state(root, state)
    composition_observation = composition.get("observation", {})
    if (
        composition_result.get("status") != "PASS"
        or composition.get("finding_id") != "REV-P0-002"
        or "REV-P0-002" not in state.get("resolved_review_findings", [])
        or not isinstance(composition_observation, dict)
        or any(
            composition_observation.get(key) != 0
            for key in (
                "real_gmail_calls",
                "private_repository_calls",
                "protected_oracles_executed",
                "production_workflow_runs",
                "external_writes",
                "remote_publications",
            )
        )
        or composition_observation.get("production_health_claimed") is not False
    ):
        raise ValueError("RMD-04 production composition is incomplete or overstated")

    graph = _load(root / "machine/contracts/task_graph.json")
    requirements = _load(root / "machine/contracts/requirements.json")
    acceptance_contract = _load(root / "machine/contracts/acceptance_contract.json")
    if (
        len(requirements["requirements"]) != 34
        or len(acceptance_contract["acceptance_contracts"]) != 34
    ):
        raise ValueError("the inherited product contract is not 34 RQ / 34 AC")
    tasks = graph["tasks"]
    if len(tasks) != 58:
        raise ValueError("task graph must contain exactly 58 tasks")

    task_paths = [root / "evidence/tasks" / f"{task['id']}.json" for task in tasks]
    records_by_task: dict[str, dict[str, Any]] = {}
    for task, path in zip(tasks, task_paths, strict=True):
        errors = validate_record(path, root)
        if errors:
            raise ValueError(f"invalid task evidence: {task['id']}")
        record = _load(path)
        if record.get("task_id") != task["id"]:
            raise ValueError(f"task evidence identity mismatch: {task['id']}")
        records_by_task[task["id"]] = record

    _validate_stage6_evidence_transition(
        root,
        state,
        records_by_task,
        repository_root=root.parents[1],
    )

    summary = _load(root / ACCEPTANCE_SUMMARY_PATH)
    bundle_errors = validate_bundle(root)
    if bundle_errors:
        raise ValueError("final Acceptance evidence bundle failed deterministic validation")
    _validate_final_summary(root, summary, acceptance_contract)

    observed_at = [str(record["observed_at_utc"]) for record in records_by_task.values()]
    observed_at.append(str(summary["observed_at_utc"]))
    observed_at.append(str(observation["observed_at_utc"]))
    observed_at.append(str(composition["observed_at_utc"]))
    if protected_receipt is not None:
        observed_at.append(str(protected_receipt["observed_at_utc"]))
    formal_counts = Counter(task["status"] for task in tasks)
    if formal_counts != Counter({"completed": 7, "planned": 51}):
        raise ValueError("formal task status is not the inherited 7 completed / 51 planned state")

    prohibition_totals: Counter[str] = Counter()
    protected_statuses: list[str] = []
    mechanism_evidenced = 0
    stage_summary = []
    for stage in graph["stages"]:
        stage_id = stage["id"]
        stage_tasks = [task for task in tasks if task["stage_id"] == stage_id]
        stage_records = [records_by_task[task["id"]] for task in stage_tasks]
        mechanism_status = _mechanism_status(root, stage_id, stage_tasks, stage_records)
        mechanism_evidenced += len(stage_records)

        record_statuses = Counter(str(record["record_status"]) for record in stage_records)
        linked_statuses: Counter[str] = Counter()
        stage_protected: list[str] = []
        for record in stage_records:
            for claim in record.get("linked_final_acceptance", []):
                linked_statuses[str(claim["status"])] += 1
            for oracle in record.get("production_oracles", []):
                status = str(oracle["status"])
                stage_protected.append(status)
                protected_statuses.append(status)
            for key, value in record.get("prohibition_counters", {}).items():
                if type(value) is not int or value != 0:
                    raise ValueError(f"non-zero prohibition counter in {record['task_id']}")
                prohibition_totals[key] += value

        stage_summary.append(
            {
                "stage_id": stage_id,
                "evidence_validation_status": "PASS",
                "evidence_records": len(stage_records),
                "mechanism_status": mechanism_status,
                "formal_completed": sum(task["status"] == "completed" for task in stage_tasks),
                "formal_planned": sum(task["status"] == "planned" for task in stage_tasks),
                "record_status_counts": dict(sorted(record_statuses.items())),
                "linked_final_claim_counts": dict(sorted(linked_statuses.items())),
                "protected_oracles_executed": sum(
                    status != "NOT_RUN" for status in stage_protected
                ),
            }
        )

    for key, value in summary["prohibition_counters"].items():
        prohibition_totals[key] += value
    if any(prohibition_totals.values()):
        raise ValueError("aggregate prohibition counters are not zero")
    if mechanism_evidenced != 58:
        raise ValueError("not every mechanism task is evidenced")

    protected_executed = sum(status != "NOT_RUN" for status in protected_statuses)
    protected_passed = sum(status == "PASS" for status in protected_statuses)
    protected_failed = sum(status == "FAILED" for status in protected_statuses)
    failed_beta_state = state_name == "PROTECTED_BETA_ATTEMPT_FAILED"
    if failed_beta_state:
        if (
            protected_receipt is None
            or protected_executed != 2
            or protected_passed != 1
            or protected_failed != 1
        ):
            raise ValueError("failed protected Beta state lacks its exact Oracle receipt")
        production_reasons = [
            "FORMAL_TASKS_INCOMPLETE",
            "PROTECTED_BETA_FAILED",
            "FINAL_ACCEPTANCE_BLOCKED",
            "PRODUCTION_WORKFLOW_NOT_RUN",
        ]
        overall_status = "PROTECTED_BETA_FAILED_FINAL_ACCEPTANCE_BLOCKED"
        protected_status = "FAILED"
        production_workflow_runs = 0
        publication_status = "CONTROLLED_BETA_DELIVERY_NOT_FINAL"
        mechanism_scope = "LOCAL_OR_SYNTHETIC_PLUS_PROTECTED_RECEIPT"
    else:
        if protected_executed != 0 or protected_passed != 0 or protected_failed != 0:
            raise ValueError("pre-Beta state cannot contain protected Oracle execution")
        production_reasons = [
            "FORMAL_TASKS_INCOMPLETE",
            "PROTECTED_ORACLES_NOT_RUN",
            "FINAL_ACCEPTANCE_BLOCKED",
            "PRODUCTION_WORKFLOW_NOT_RUN",
        ]
        overall_status = "LOCAL_MECHANISMS_EVIDENCED_FINAL_ACCEPTANCE_BLOCKED"
        protected_status = "NOT_RUN"
        production_workflow_runs = 0
        publication_status = "LOCAL_ONLY_NOT_PUBLISHED"
        mechanism_scope = "LOCAL_OR_SYNTHETIC_ONLY"
    blockers = list(dict.fromkeys(production_reasons + list(state["current_remediation_blockers"])))
    source_digests = {
        "acceptance_contract_sha256": _sha256(root / "machine/contracts/acceptance_contract.json"),
        "acceptance_summary_sha256": _sha256(root / ACCEPTANCE_SUMMARY_PATH),
        "canonical_facts_sha256": _sha256(root / "machine/facts/canonical_facts.json"),
        "delivery_status_model_sha256": _sha256(root / MODEL_PATH),
        "kill_criteria_sha256": _sha256(root / "machine/contracts/kill_criteria.json"),
        "legacy_manifest_v1_0_1_sha256": _sha256(root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"),
        "production_composition_sha256": _sha256(root / PRODUCTION_COMPOSITION_PATH),
        "requirements_sha256": _sha256(root / "machine/contracts/requirements.json"),
        "stage6_aggregate_sha256": _sha256(root / "evidence/stage6/latest.json"),
        "task_evidence_root_sha256": _tree_digest(root, task_paths),
        "task_graph_sha256": _sha256(root / "machine/contracts/task_graph.json"),
        "traceability_sha256": _sha256(root / "machine/contracts/traceability_matrix.csv"),
        "workflow_command_matrix_sha256": _sha256(root / WORKFLOW_MATRIX_PATH),
        "assurance_provenance_root_sha256": _tree_digest(root, _assurance_paths(root)),
    }
    if protected_receipt is not None:
        source_digests["protected_beta_execution_receipt_sha256"] = _sha256(
            root / PROTECTED_BETA_RECEIPT_PATH
        )

    return {
        "schema_version": "moomooau.delivery-status.v1",
        "status_model_version": model["schema_version"],
        "package_version": state["package_version"],
        "status_as_of_utc": max(observed_at),
        "authority": {
            "path": model["authority"]["current_status"],
            "precedence": model["authority"]["precedence"],
        },
        "overall_status": overall_status,
        "dimensions": {
            "evidence_integrity": {
                "status": "PASS",
                "verified_records": 58,
                "total_records": 58,
                "failures": 0,
            },
            "mechanism_implementation": {
                "status": "LOCAL_MECHANISMS_EVIDENCED",
                "evidenced_tasks": mechanism_evidenced,
                "total_tasks": 58,
                "scope": mechanism_scope,
            },
            "formal_task_completion": {
                "status": "INCOMPLETE",
                "completed": formal_counts["completed"],
                "planned": formal_counts["planned"],
                "total": len(tasks),
                "contract_version": graph["version"],
            },
            "protected_oracles": {
                "status": protected_status,
                "declared": len(protected_statuses),
                "executed": protected_executed,
                "passed": protected_passed,
                "failed": protected_failed,
                "not_run": protected_statuses.count("NOT_RUN"),
            },
            "final_acceptance": {
                "status": summary["status"],
                "passed": summary["final_acceptances_passed"],
                "blocked": summary["final_acceptances_blocked"],
                "total": summary["total_acceptances"],
            },
            "production_readiness": {
                "status": "BLOCKED",
                "workflow_runs": production_workflow_runs,
                "reason_codes": production_reasons,
            },
            "publication": {
                "status": publication_status,
                "controlled_main_deliveries": 1 if failed_beta_state else 0,
                "remote_publications": prohibition_totals["remote_publication"],
            },
        },
        "stage_summary": stage_summary,
        "prohibition_counter_scope": (
            "LOCAL_EVIDENCE_GENERATION_ONLY_EXCLUDES_PROTECTED_EXECUTION_RECEIPT"
        ),
        "prohibition_counters": dict(sorted(prohibition_totals.items())),
        "blockers": blockers,
        "resolved_review_findings": state["resolved_review_findings"],
        "next_action": state["next_action"],
        "source_digests": source_digests,
    }


def write_or_check(root: Path, *, write: bool) -> bool:
    root = root.resolve()
    expected = _render(build_status(root))
    path = root / STATUS_PATH
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
        return True
    return path.is_file() and path.read_text(encoding="utf-8") == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        matched = write_or_check(args.root, write=args.write)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(json.dumps({"status": "FAIL", "reason": type(exc).__name__}, sort_keys=True))
        return 1
    result = {
        "status": "PASS" if matched else "FAIL",
        "mode": "write" if args.write else "check",
        "status_path": STATUS_PATH.as_posix(),
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
