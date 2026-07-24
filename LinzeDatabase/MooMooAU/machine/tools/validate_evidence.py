#!/usr/bin/env python3
"""Read-only, stage-aware validator for public task evidence.

Validation PASS means that a record is structurally valid, safely redacted and
cross-bound to the frozen task and stage-local acceptance contracts.  It does
not promote the task, execute a protected Oracle, pass final Acceptance or make
the system production-ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from validate_publication import (
    EMAIL,
    LOCAL_PATH,
    REPOSITORY_TOKEN,
    SECRET_PATTERNS,
)

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_STAGE0_FIELDS = {
    "schema_version",
    "evidence_id",
    "stage_id",
    "task_id",
    "stage_acceptance_id",
    "observed_at_utc",
    "base_commit",
    "source_package_version",
    "record_status",
    "delivery_status",
    "checks",
    "blockers",
    "next_action",
}
CHECK_FIELDS = {"id", "status", "evidence_ref"}
CHECK_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
TASK_ID = re.compile(r"^T[0-9]{4}$")
STAGE0_AC_ID = re.compile(r"^S0AC-[0-9]{3}$")
STAGE0_EVIDENCE_ID = re.compile(r"^S0-(T[0-9]{4}|LATEST)-[0-9]{8}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")

STAGE_CONFIG: dict[str, tuple[Path, Path]] = {
    stage_id: (
        Path(f"machine/stages/{stage_id}/schemas/stage{index}-evidence-v1.schema.json"),
        Path(f"machine/stages/{stage_id}/contracts/stage{index}_acceptance_contract.json"),
    )
    for index, stage_id in enumerate(("S1", "S2", "S3", "S4", "S5", "S6", "S7"), start=1)
}
S6_EVIDENCE_SCHEMAS = {
    "moomooau.stage6-evidence.v1": Path("machine/stages/S6/schemas/stage6-evidence-v1.schema.json"),
    "moomooau.stage6-evidence.v2": Path("machine/stages/S6/schemas/stage6-evidence-v2.schema.json"),
}
STAGE6_CANDIDATE_RECEIPT_PATH = Path("machine/stages/S6/reviews/rmd05/execution-receipt17.json")
STAGE6_REVIEW_PROVENANCE_PATHS = (
    Path("machine/stages/S6/reviews/gpt-5.6-sol.json"),
    Path("machine/stages/S6/reviews/gpt-5.6-terra.json"),
)
EXECUTION_CANDIDATE_TRAILER = "MooMooAU-Execution-Candidate"
EXECUTION_RECEIPT_TRAILER = "MooMooAU-Execution-Receipt-SHA256"
STAGE6_TASK_IDS = tuple(f"T060{index}" for index in range(1, 9))
STAGE6_REQUIRED_COMMAND_IDS = {
    "assurance-history",
    "container-build",
    "container-cleanup",
    "container-smoke",
    "dependency-audit",
    "delivery-status-validation",
    "governance-validation",
    "governance-facts-check",
    "mypy-strict",
    "package-build",
    "publication-scan",
    "remediation-tests",
    "ruff-format",
    "ruff-lint",
    "sbom-reproducibility",
    "secret-scan",
    "stage6-task-tests",
    "stage6-validation",
    "stage7-runtime-regression-tests",
}
STAGE6_TASK_COMMAND_IDS = {
    "T0601": {"stage6-task-tests", "ruff-lint", "mypy-strict"},
    "T0602": {"stage6-task-tests"},
    "T0603": {"stage6-task-tests"},
    "T0604": {
        "container-build",
        "container-cleanup",
        "container-smoke",
        "dependency-audit",
        "governance-validation",
        "package-build",
        "sbom-reproducibility",
        "secret-scan",
        "stage6-task-tests",
    },
    "T0605": {"stage6-task-tests"},
    "T0606": {
        "assurance-history",
        "delivery-status-validation",
        "governance-facts-check",
        "stage6-task-tests",
        "stage6-validation",
    },
    "T0607": {"stage6-task-tests", "stage7-runtime-regression-tests"},
    "T0608": {"stage6-task-tests", "stage7-runtime-regression-tests"},
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_output(repository: Path, *args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode, completed.stdout.strip()


def _stage6_review_subject(root: Path) -> tuple[str, str, list[str]]:
    subjects: list[tuple[str, str]] = []
    errors: list[str] = []
    for relative in STAGE6_REVIEW_PROVENANCE_PATHS:
        path = root / relative
        try:
            record = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"Stage 6 review provenance is invalid: {relative.name}")
            continue
        subject = record.get("subject") if isinstance(record, dict) else None
        if not isinstance(subject, dict):
            errors.append(f"Stage 6 review subject is invalid: {relative.name}")
            continue
        candidate_commit = subject.get("candidate_commit")
        candidate_tree = subject.get("candidate_tree")
        if (
            not isinstance(candidate_commit, str)
            or COMMIT.fullmatch(candidate_commit) is None
            or not isinstance(candidate_tree, str)
            or COMMIT.fullmatch(candidate_tree) is None
        ):
            errors.append(f"Stage 6 review subject identity is invalid: {relative.name}")
            continue
        subjects.append((candidate_commit, candidate_tree))
    if len(subjects) != 2 or len(set(subjects)) != 1:
        errors.append("Stage 6 reviewers do not share one receipt-anchor candidate")
        return "", "", errors
    candidate_commit, candidate_tree = subjects[0]
    return candidate_commit, candidate_tree, errors


def validate_stage6_receipt_anchor(
    root: Path,
    repository_root: Path,
    review_candidate_commit: str,
    review_candidate_tree: str,
    receipt_relative_path: Path = STAGE6_CANDIDATE_RECEIPT_PATH,
) -> tuple[str | None, list[str]]:
    """Verify the empty Git anchor that immutably pins the post-execution receipt digest."""

    root = root.resolve()
    repository_root = repository_root.resolve()
    errors: list[str] = []
    receipt_path = root / receipt_relative_path
    try:
        receipt = _load_json(receipt_path)
        receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, ["Stage 6 receipt anchor cannot read the final execution receipt"]
    subject = receipt.get("subject") if isinstance(receipt, dict) else None
    if not isinstance(subject, dict):
        return None, ["Stage 6 receipt anchor found an invalid execution subject"]
    execution_candidate = subject.get("candidate_commit")
    execution_tree = subject.get("candidate_tree")
    if (
        not isinstance(execution_candidate, str)
        or COMMIT.fullmatch(execution_candidate) is None
        or not isinstance(execution_tree, str)
        or COMMIT.fullmatch(execution_tree) is None
    ):
        return None, ["Stage 6 receipt anchor found an invalid execution identity"]

    review_tree_status, observed_review_tree = _git_output(
        repository_root,
        "rev-parse",
        f"{review_candidate_commit}^{{tree}}",
    )
    execution_tree_status, observed_execution_tree = _git_output(
        repository_root,
        "rev-parse",
        f"{execution_candidate}^{{tree}}",
    )
    parents_status, parents_output = _git_output(
        repository_root,
        "rev-list",
        "--parents",
        "-n",
        "1",
        review_candidate_commit,
    )
    parent_tokens = parents_output.split()
    if (
        review_tree_status != 0
        or execution_tree_status != 0
        or observed_review_tree != review_candidate_tree
        or observed_execution_tree != review_candidate_tree
        or execution_tree != review_candidate_tree
    ):
        errors.append("Stage 6 receipt anchor does not preserve the executed candidate tree")
    if (
        parents_status != 0
        or len(parent_tokens) != 2
        or parent_tokens[0] != review_candidate_commit
        or parent_tokens[1] != execution_candidate
    ):
        errors.append("Stage 6 receipt anchor is not an empty child of the execution candidate")

    message_status, message = _git_output(
        repository_root,
        "show",
        "-s",
        "--format=%B",
        review_candidate_commit,
    )
    trailer_values: dict[str, list[str]] = {}
    for key in (EXECUTION_CANDIDATE_TRAILER, EXECUTION_RECEIPT_TRAILER):
        prefix = f"{key}:"
        trailer_values[key] = [
            line.removeprefix(prefix).strip()
            for line in message.splitlines()
            if line.startswith(prefix)
        ]
    if message_status != 0 or trailer_values[EXECUTION_CANDIDATE_TRAILER] != [execution_candidate]:
        errors.append("Stage 6 receipt anchor execution-candidate trailer differs")
    if trailer_values[EXECUTION_RECEIPT_TRAILER] != [receipt_sha256]:
        errors.append("Stage 6 receipt anchor digest trailer differs from the exact receipt")
    return execution_candidate, errors


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo == UTC


def _task_acceptance_map(root: Path) -> dict[str, str]:
    contract = _load_json(root / "machine/contracts/stage_acceptance_contract.json")
    return {item["task_id"]: item["id"] for item in contract["acceptance_contracts"]}


def _sensitive_errors(record: dict[str, Any], root: Path) -> list[str]:
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
    contract = _load_json(root / "machine/contracts/publication_safety.json")
    forbidden_hashes = set(contract["forbidden_locator_sha256_casefold"])
    errors = []
    if EMAIL.search(serialized):
        errors.append("evidence contains an email address")
    if LOCAL_PATH.search(serialized):
        errors.append("evidence contains a local absolute path")
    if any(pattern.search(serialized) for pattern in SECRET_PATTERNS):
        errors.append("evidence contains secret material")
    if any(
        hashlib.sha256(token.casefold().encode("utf-8")).hexdigest() in forbidden_hashes
        for token in REPOSITORY_TOKEN.findall(serialized)
    ):
        errors.append("evidence contains a private repository locator")
    return errors


def _validate_stage0_record(record: dict[str, Any], root: Path) -> list[str]:
    """Preserve the exact v1.0.1 Stage 0 semantics."""

    errors: list[str] = []
    if set(record) != EXPECTED_STAGE0_FIELDS:
        errors.append("record fields do not match the v1.0.1 Stage 0 evidence contract")
    if record.get("schema_version") != "moomooau.stage0-evidence.v2":
        errors.append("schema_version mismatch")
    if record.get("stage_id") != "S0":
        errors.append("stage_id must be S0")
    if record.get("source_package_version") != "1.0.1":
        errors.append("source_package_version mismatch")
    if record.get("record_status") != "VALID":
        errors.append("record_status must be VALID")
    if record.get("delivery_status") not in {"PASS", "BLOCKED"}:
        errors.append("invalid delivery_status")
    if not _valid_utc_timestamp(record.get("observed_at_utc")):
        errors.append("observed_at_utc must be an RFC 3339 UTC timestamp")
    if COMMIT.fullmatch(str(record.get("base_commit", ""))) is None:
        errors.append("base_commit must be a 40-character lowercase commit id")

    evidence_id = record.get("evidence_id")
    if not isinstance(evidence_id, str) or STAGE0_EVIDENCE_ID.fullmatch(evidence_id) is None:
        errors.append("invalid evidence_id")
    task_id = record.get("task_id")
    stage_acceptance_id = record.get("stage_acceptance_id")
    task_map = _task_acceptance_map(root)
    if task_id is None:
        if stage_acceptance_id is not None or not str(evidence_id).startswith("S0-LATEST-"):
            errors.append("latest record must use null task and stage acceptance ids")
    else:
        if not isinstance(task_id, str) or TASK_ID.fullmatch(task_id) is None:
            errors.append("invalid task_id")
        elif task_map.get(task_id) != stage_acceptance_id:
            errors.append("task and stage acceptance mapping mismatch")
        if (
            not isinstance(stage_acceptance_id, str)
            or STAGE0_AC_ID.fullmatch(stage_acceptance_id) is None
        ):
            errors.append("invalid stage_acceptance_id")
        if not str(evidence_id).startswith(f"S0-{task_id}-"):
            errors.append("evidence_id does not match task_id")

    checks = record.get("checks")
    check_ids: list[str] = []
    if not isinstance(checks, list) or not checks:
        errors.append("checks must be a non-empty array")
    else:
        for check in checks:
            if not isinstance(check, dict) or set(check) != CHECK_FIELDS:
                errors.append("invalid check object")
                continue
            check_id = check.get("id")
            if not isinstance(check_id, str) or not check_id:
                errors.append("check id must be non-empty")
            else:
                check_ids.append(check_id)
            if check.get("status") not in CHECK_STATUSES:
                errors.append("invalid check status")
            evidence_ref = check.get("evidence_ref")
            if not isinstance(evidence_ref, str) or not evidence_ref:
                errors.append("evidence_ref must be non-empty")
                continue
            referenced = (root / evidence_ref).resolve()
            try:
                referenced.relative_to(root)
            except ValueError:
                errors.append("evidence_ref escapes project root")
                continue
            if not referenced.exists() or referenced.is_symlink():
                errors.append("evidence_ref does not exist or is unsafe")
        if len(check_ids) != len(set(check_ids)):
            errors.append("check ids must be unique")
        if task_id is not None and stage_acceptance_id not in check_ids:
            errors.append("task record must include its stage acceptance check")

    gate = _load_json(root / "machine/contracts/stage0_semantic_gate.json")
    known_blockers = {issue["id"] for issue in gate["blocking_issues"]}
    blockers = record.get("blockers")
    if not isinstance(blockers, list) or len(blockers) != len(set(blockers)):
        errors.append("blockers must be a unique array")
    elif any(item not in known_blockers for item in blockers):
        errors.append("unknown blocker reference")
    if record.get("delivery_status") == "BLOCKED" and not blockers:
        errors.append("blocked record must identify at least one blocker")
    if record.get("delivery_status") == "PASS":
        if blockers:
            errors.append("passing record cannot retain blockers")
        if isinstance(checks, list) and any(
            check.get("status") != "PASS" for check in checks if isinstance(check, dict)
        ):
            errors.append("passing record may contain only passing checks")
    if not isinstance(record.get("next_action"), str) or not record["next_action"].strip():
        errors.append("next_action must be non-empty")
    return errors


def _schema_errors(record: dict[str, Any], schema_path: Path) -> list[str]:
    try:
        schema = _load_json(schema_path)
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError):
        return ["stage evidence schema is missing or invalid"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"schema violation at {location}: {error.validator}")
    return errors


def _unsafe_reference(reference: str) -> bool:
    normalized = reference.replace("\\", "/")
    return (
        reference.startswith("/")
        or WINDOWS_ABSOLUTE_PATH.match(reference) is not None
        or any(part == ".." for part in normalized.split("/"))
    )


def _validate_later_stage_record(
    record: dict[str, Any], relative_path: Path, root: Path
) -> list[str]:
    errors: list[str] = []
    stage_id = record.get("stage_id")
    if not isinstance(stage_id, str) or stage_id not in STAGE_CONFIG:
        return ["stage_id must identify one of S1 through S7"]
    schema_relative, contract_relative = STAGE_CONFIG[stage_id]
    if stage_id == "S6":
        selected = S6_EVIDENCE_SCHEMAS.get(str(record.get("schema_version", "")))
        if selected is None:
            errors.append("Stage 6 evidence schema_version is unsupported")
            return errors
        schema_relative = selected
    errors.extend(_schema_errors(record, root / schema_relative))

    graph = _load_json(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"]}
    task_id = record.get("task_id")
    if not isinstance(task_id, str):
        errors.append("task_id must be a string")
        return errors
    task = graph_tasks.get(task_id)
    if task is None:
        errors.append("task_id is absent from the task graph")
        return errors
    if task.get("stage_id") != stage_id:
        errors.append("task and stage mapping mismatch")

    expected_relative = Path("evidence/tasks") / f"{task_id}.json"
    if relative_path != expected_relative:
        errors.append("evidence path does not match the task graph")
    if task.get("evidence") != [expected_relative.as_posix()]:
        errors.append("task graph evidence binding mismatch")
    verification = str(task.get("verification", ""))
    test_path = f"tests/tasks/test_{str(task_id).lower()}.py"
    if test_path not in verification:
        errors.append("task graph verification is not bound to the task test")
    if f"machine/tools/validate_evidence.py {expected_relative.as_posix()}" not in verification:
        errors.append("task graph verification is not bound to this evidence record")

    stage_contract = _load_json(root / contract_relative)
    if stage_contract.get("stage_id") != stage_id or stage_contract.get("policy") != "FAIL_CLOSED":
        errors.append("stage-local acceptance contract identity mismatch")
        return errors
    contracts = {item["task_id"]: item for item in stage_contract["acceptance_contracts"]}
    local_contract = contracts.get(task_id)
    if local_contract is None:
        errors.append("task is absent from the stage-local acceptance contract")
        return errors
    if local_contract.get("id") != record.get("stage_acceptance_id"):
        errors.append("task and stage acceptance mapping mismatch")
    if local_contract.get("evidence_required") != expected_relative.as_posix():
        errors.append("stage acceptance evidence binding mismatch")
    if test_path not in str(local_contract.get("verification", "")):
        errors.append("stage acceptance verification is not bound to the task test")

    expected_final_ids = local_contract.get("linked_final_acceptance_ids")
    if expected_final_ids != task.get("acceptance_ids"):
        errors.append("stage and task graph final Acceptance bindings differ")
    linked = record.get("linked_final_acceptance")
    linked_ids = (
        [item.get("id") for item in linked if isinstance(item, dict)]
        if isinstance(linked, list)
        else []
    )
    if linked_ids != expected_final_ids:
        errors.append("evidence final Acceptance bindings mismatch")
    final_contract = _load_json(root / "machine/contracts/acceptance_contract.json")
    known_final_ids = {item["id"] for item in final_contract["acceptance_contracts"]}
    if any(item not in known_final_ids for item in linked_ids):
        errors.append("evidence references an unknown final Acceptance")
    if isinstance(linked, list) and any(
        item.get("status") not in {"PARTIAL", "NOT_RUN"}
        for item in linked
        if isinstance(item, dict)
    ):
        errors.append("final Acceptance claim is overstated")

    checks = record.get("checks")
    if isinstance(checks, list):
        check_ids = [item.get("id") for item in checks if isinstance(item, dict)]
        if len(check_ids) != len(set(check_ids)):
            errors.append("check ids must be unique")
        for check in checks:
            if not isinstance(check, dict):
                continue
            reference = check.get("evidence_ref")
            if isinstance(reference, str) and _unsafe_reference(reference):
                errors.append("evidence_ref is an unsafe path")

    counters = record.get("prohibition_counters")
    if not isinstance(counters, dict) or not counters:
        errors.append("prohibition counters must be a non-empty object")
    elif any(type(value) is not int or value != 0 for value in counters.values()):
        errors.append("all prohibition counters must be integer zero")

    if record.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED":
        errors.append("later-stage evidence must remain local and unpublished")
    production_oracles = record.get("production_oracles", [])
    expected_protected_status = {
        "T0701": "PASS",
        "T0702": "PASS",
        "T0703": "PASS",
    }.get(task_id, "NOT_RUN")
    if isinstance(production_oracles, list) and any(
        item.get("status") != expected_protected_status
        for item in production_oracles
        if isinstance(item, dict)
    ):
        errors.append("protected production Oracle claim is overstated")
    expected_receipt = (
        "machine/stages/S7/reviews/t0702/execution-receipt.json"
        if task_id in {"T0701", "T0702"}
        else (
            "machine/stages/S7/reviews/t0703/execution-receipt.json" if task_id == "T0703" else None
        )
    )
    if record.get("protected_execution_receipt") != expected_receipt:
        errors.append("protected execution receipt binding differs")

    record_status = record.get("record_status")
    check_statuses = (
        [item.get("status") for item in checks if isinstance(item, dict)]
        if isinstance(checks, list)
        else []
    )
    if stage_id in {"S1", "S2", "S3", "S4", "S5", "S6"}:
        if record_status == "PASS" and any(status != "PASS" for status in check_statuses):
            errors.append("passing mechanism evidence contains a non-passing check")
        if (
            record_status == "FAIL"
            and check_statuses
            and all(status == "PASS" for status in check_statuses)
        ):
            errors.append("failed mechanism evidence has no failing check")
    elif stage_id == "S7":
        blockers = record.get("blockers")
        if record_status in {"READY", "BLOCKED"} and any(
            status != "PASS" for status in check_statuses
        ):
            errors.append("Stage 7 local preflight contains a non-passing check")
        if record_status == "BLOCKED" and not blockers:
            errors.append("blocked Stage 7 evidence must retain a blocker")

    return errors


def validate_record(path: Path, root: Path = PROJECT_ROOT) -> list[str]:
    root = root.resolve()
    if path.is_symlink():
        return ["evidence path is a symlink"]
    path = path.resolve()
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return ["evidence path escapes project root"]
    try:
        record = _load_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"invalid JSON evidence: {type(exc).__name__}"]
    if not isinstance(record, dict):
        return ["evidence root must be an object"]

    if record.get("stage_id") == "S0":
        errors = _validate_stage0_record(record, root)
    else:
        errors = _validate_later_stage_record(record, relative_path, root)
    errors.extend(_sensitive_errors(record, root))
    return list(dict.fromkeys(errors))


def validate_stage6_candidate_bundle(
    root: Path = PROJECT_ROOT,
    repository_root: Path | None = None,
) -> list[str]:
    """Validate the exact receipt-bound Stage 6 v2 task and aggregate evidence bundle."""

    root = root.resolve()
    errors: list[str] = []
    receipt_path = root / STAGE6_CANDIDATE_RECEIPT_PATH
    if not receipt_path.is_file() or receipt_path.is_symlink():
        return ["Stage 6 candidate execution receipt is missing or unsafe"]
    try:
        receipt = _load_json(receipt_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ["Stage 6 candidate execution receipt is invalid"]
    if not isinstance(receipt, dict):
        return ["Stage 6 candidate execution receipt must be an object"]
    errors.extend(
        _schema_errors(
            receipt,
            root / "machine/stages/S6/schemas/execution-receipt-v1.schema.json",
        )
    )
    receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    subject = receipt.get("subject")
    commands = receipt.get("commands")
    if not isinstance(subject, dict):
        errors.append("Stage 6 receipt subject is invalid")
        subject = {}
    if not isinstance(commands, list):
        errors.append("Stage 6 receipt commands are invalid")
        commands = []
    command_ids = [
        item.get("id") for item in commands if isinstance(item, dict) and item.get("exit_code") == 0
    ]
    if len(command_ids) != len(set(command_ids)) or set(command_ids) != STAGE6_REQUIRED_COMMAND_IDS:
        errors.append("Stage 6 receipt command closure is incomplete or duplicated")
    candidate_commit = subject.get("candidate_commit")
    candidate_tree = subject.get("candidate_tree")
    if repository_root is not None:
        review_candidate_commit, review_candidate_tree, subject_errors = _stage6_review_subject(
            root
        )
        errors.extend(subject_errors)
        if review_candidate_commit and review_candidate_tree:
            anchored_execution_candidate, anchor_errors = validate_stage6_receipt_anchor(
                root,
                repository_root,
                review_candidate_commit,
                review_candidate_tree,
            )
            errors.extend(anchor_errors)
            if anchored_execution_candidate != candidate_commit:
                errors.append("Stage 6 receipt subject differs from its immutable Git anchor")

    for task_id in STAGE6_TASK_IDS:
        path = root / "evidence/tasks" / f"{task_id}.json"
        record_errors = validate_record(path, root)
        if record_errors:
            errors.append(f"invalid Stage 6 candidate evidence: {task_id}")
            continue
        record = _load_json(path)
        binding = record.get("execution_binding")
        if not isinstance(binding, dict):
            errors.append(f"Stage 6 execution binding is absent: {task_id}")
            continue
        bound_commands = binding.get("command_ids")
        if (
            record.get("schema_version") != "moomooau.stage6-evidence.v2"
            or record.get("candidate_commit") != candidate_commit
            or record.get("candidate_tree") != candidate_tree
            or binding.get("path") != STAGE6_CANDIDATE_RECEIPT_PATH.as_posix()
            or binding.get("sha256") != receipt_sha256
            or not isinstance(bound_commands, list)
            or set(bound_commands) != STAGE6_TASK_COMMAND_IDS[task_id]
            or not set(bound_commands).issubset(set(command_ids))
        ):
            errors.append(f"Stage 6 candidate binding is stale or incomplete: {task_id}")

    aggregate_path = root / "evidence/stage6/latest.json"
    if not aggregate_path.is_file() or aggregate_path.is_symlink():
        errors.append("Stage 6 candidate aggregate evidence is missing or unsafe")
        return list(dict.fromkeys(errors))
    try:
        aggregate = _load_json(aggregate_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("Stage 6 candidate aggregate evidence is invalid")
        return list(dict.fromkeys(errors))
    if not isinstance(aggregate, dict):
        errors.append("Stage 6 candidate aggregate evidence must be an object")
        return list(dict.fromkeys(errors))
    observation = aggregate.get("stage6_observation")
    counters = aggregate.get("prohibition_counters")
    aggregate_receipt = aggregate.get("execution_receipt")
    if not isinstance(observation, dict):
        observation = {}
    if not isinstance(counters, dict):
        counters = {}
    if not isinstance(aggregate_receipt, dict):
        aggregate_receipt = {}
    expected_not_run = (
        "real_gmail_faults",
        "private_repository_faults",
        "protected_load",
        "remote_stage6_ci",
        "production_schedule_execution",
        "quarterly_recovery_drill",
    )
    if (
        aggregate.get("schema_version") != "moomooau.stage6-verification.v2"
        or aggregate.get("stage_id") != "S6"
        or aggregate.get("status") != "PASS"
        or aggregate.get("candidate_commit") != candidate_commit
        or aggregate.get("candidate_tree") != candidate_tree
        or aggregate_receipt.get("path") != STAGE6_CANDIDATE_RECEIPT_PATH.as_posix()
        or aggregate_receipt.get("sha256") != receipt_sha256
        or set(aggregate.get("local_gate_command_ids", [])) != set(command_ids)
        or aggregate.get("scope") != "LOCAL_SYNTHETIC_ONLY"
        or aggregate.get("task_pass_count") != 8
        or aggregate.get("task_total") != 8
        or aggregate.get("final_acceptance_policy") != "NOT_FINAL"
        or aggregate.get("final_acceptances_passed") != 0
        or aggregate.get("protected_oracles_executed") != 0
        or not counters
        or any(type(value) is not int or value != 0 for value in counters.values())
        or observation.get("l3_messages_exercised") != 100_000
        or observation.get("l3_attachments_exercised") != 200_000
        or observation.get("l3_logical_objects") != 300_000
        or observation.get("mandatory_chaos_passed") != 18
        or observation.get("kill_drills_passed") != 10
        or observation.get("independent_model_reviews_passed") != 2
        or observation.get("model_policy_evals_passed") != 14
        or observation.get("real_gmail_calls") != 0
        or observation.get("real_gmail_mutations") != 0
        or observation.get("private_repository_calls") != 0
        or observation.get("model_real_data_calls") != 0
        or observation.get("model_secret_requests") != 0
        or observation.get("production_workflow_runs") != 0
        or observation.get("dependency_advisory_scan") != "PASS"
        or observation.get("local_secret_scan_findings") != 0
        or observation.get("taskpack_validation") != "PASS"
        or observation.get("governance_validation") != "PASS"
        or any(observation.get(key) != "NOT_RUN" for key in expected_not_run)
        or aggregate.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
        or aggregate.get("next_stage") != "S7"
        or aggregate.get("next_stage_status") != "NOT_STARTED"
    ):
        errors.append("Stage 6 candidate aggregate is stale, incomplete or overstated")
    return list(dict.fromkeys(errors))


def _claim_summary(path: Path, root: Path) -> dict[str, Any]:
    try:
        record = _load_json(path.resolve())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(record, dict):
        return {}
    graph = _load_json(root / "machine/contracts/task_graph.json")
    task = next((item for item in graph["tasks"] if item["id"] == record.get("task_id")), None)
    linked = record.get("linked_final_acceptance", [])
    production = record.get("production_oracles", [])
    return {
        "stage_id": record.get("stage_id"),
        "task_id": record.get("task_id"),
        "declared_record_status": record.get("record_status"),
        "delivery_status": record.get("delivery_status"),
        "formal_task_status": task.get("status") if task else None,
        "linked_final_acceptance_statuses": {
            item.get("id"): item.get("status") for item in linked if isinstance(item, dict)
        },
        "protected_oracle_statuses": {
            item.get("id"): item.get("status") for item in production if isinstance(item, dict)
        },
        "production_ready": False,
    }


def _expand_paths(inputs: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in inputs:
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.json")))
        else:
            expanded.append(path)
    return expanded


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "<outside-project-root>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    results = []
    for path in _expand_paths(args.paths):
        errors = validate_record(path, root)
        results.append(
            {
                "path": _display_path(path, root),
                "validation_status": "PASS" if not errors else "FAIL",
                "claim_state": _claim_summary(path, root),
                "errors": errors,
            }
        )
    status = (
        "PASS"
        if results and all(item["validation_status"] == "PASS" for item in results)
        else "FAIL"
    )
    print(json.dumps({"status": status, "records": results}, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
