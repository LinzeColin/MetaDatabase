#!/usr/bin/env python3
"""Replay the final-tree S3-S6 Workflow entrypoints without remote effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = Path("machine/contracts/workflow_command_matrix.json")
SCHEMA_PATH = Path("schemas/workflow-command-matrix-v1.schema.json")
GOVERNANCE_PIN = "ebc6c2e4884edc959118cfc56d0e18a86c49460f"
GOVERNANCE_REPOSITORY = "LinzeColin/Governance"
GOVERNANCE_DEPLOY_KEY_EXPRESSION = "${{ secrets.MOOMOOAU_GOVERNANCE_DEPLOY_KEY }}"
GOVERNANCE_DEPENDENCY_WORKFLOWS = frozenset(
    {
        ".github/workflows/moomooau-patch-lifecycle.yml",
        ".github/workflows/moomooau-stage1-ci.yml",
        ".github/workflows/moomooau-stage2-security.yml",
        ".github/workflows/moomooau-stage3-ci.yml",
        ".github/workflows/moomooau-stage4-ci.yml",
        ".github/workflows/moomooau-stage5-ci.yml",
        ".github/workflows/moomooau-stage6-ci.yml",
        ".github/workflows/moomooau-stage7-ci.yml",
    }
)
FORK_REJECTION_STEP_NAME = "Reject fork pull requests before protected dependency checkout"
FORK_REJECTION_CONDITION = (
    "github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name != github.repository"
)
FORK_REJECTION_COMMAND = (
    'echo "::error::Fork pull requests cannot access the protected read-only '
    'Governance dependency." exit 1'
)
EXPECTED_GOVERNANCE_AUTH_POLICY = {
    "policy": "DEPENDENCY_AUTH_ONLY_ZERO_PRODUCTION_SECRET",
    "credential_kind": "GITHUB_READ_ONLY_DEPLOY_KEY",
    "actions_secret_name": "MOOMOOAU_GOVERNANCE_DEPLOY_KEY",
    "repository_scope": GOVERNANCE_REPOSITORY,
    "allowed_consumer": "actions/checkout with.ssh-key only",
    "write_access": False,
    "persist_credentials": False,
    "fork_pull_request_policy": ("FAIL_CLOSED_BEFORE_PROTECTED_DEPENDENCY_CHECKOUT"),
    "pull_request_target_allowed": False,
    "production_secret_reads": 0,
    "project_runtime_secret_reads": 0,
}
IGNORED_PARTS = {
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
}
COMMON_ZERO_SIGNALS = {
    "real_gmail_calls",
    "gmail_mutations",
    "private_repository_calls",
    "real_secrets_read",
    "external_writes",
    "remote_publication",
    "protected_oracles_executed",
    "final_acceptances_passed",
}
OPTIONAL_ZERO_SIGNALS = {
    "production_workflow_runs",
    "thread_trash_calls",
    "permanent_delete_calls",
    "model_real_data_calls",
    "model_secret_requests",
}
EXPECTED_ENTRIES = {
    f"S{stage}": {
        "workflow": f".github/workflows/moomooau-stage{stage}-ci.yml",
        "validator": f"machine/stages/S{stage}/tools/validate_stage{stage}.py",
        "scope_failure": {
            3: "scope.no_stage4_or_production_authority",
            4: "scope.no_stage5_or_production_authority",
            5: "scope.no_stage6_or_production_execution",
            6: "scope.no_stage7_or_production_execution",
        }[stage],
    }
    for stage in range(3, 7)
}
WORKFLOW_EXPRESSION = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
KNOWN_CONTEXT_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"(?P<context>github|env|vars|job|jobs|steps|runner|secrets|strategy|matrix|needs|inputs)"
    r"\s*(?:\.|\[)"
)
HASH_FILES_CALL = re.compile(r"(?<![A-Za-z0-9_-])hashFiles\s*\(")
TOP_LEVEL_ENV_CONTEXTS = frozenset({"github", "secrets", "inputs", "vars"})
JOB_ENV_CONTEXTS = frozenset({"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"})


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_command(value: str) -> str:
    return " ".join(value.split())


def _string_values(
    value: object,
    *,
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        values: list[tuple[tuple[str, ...], str]] = []
        for key, child in value.items():
            values.extend(_string_values(child, path=(*path, str(key))))
        return values
    if isinstance(value, list):
        values = []
        for index, child in enumerate(value):
            values.extend(_string_values(child, path=(*path, str(index))))
        return values
    return [(path, value)] if isinstance(value, str) else []


def _moomooau_workflow_paths(repository_root: Path) -> list[Path]:
    return sorted(
        (repository_root / ".github/workflows").glob("moomooau-*.yml"),
        key=lambda path: path.as_posix(),
    )


def _expression_contexts(value: object) -> tuple[set[str], bool]:
    if not isinstance(value, str):
        return set(), False
    contexts: set[str] = set()
    uses_hash_files = False
    for expression in WORKFLOW_EXPRESSION.finditer(value):
        body = expression.group("body")
        contexts.update(match.group("context") for match in KNOWN_CONTEXT_REFERENCE.finditer(body))
        uses_hash_files = uses_hash_files or HASH_FILES_CALL.search(body) is not None
    return contexts, uses_hash_files


def _validate_env_contexts(
    env: object,
    *,
    label: str,
    allowed_contexts: frozenset[str],
) -> list[str]:
    if env is None:
        return []
    if not isinstance(env, dict):
        return [f"{label} must be a mapping"]
    errors: list[str] = []
    for env_id, value in sorted(env.items(), key=lambda item: str(item[0])):
        contexts, uses_hash_files = _expression_contexts(value)
        disallowed = sorted(contexts - allowed_contexts)
        if disallowed:
            errors.append(f"{label}.{env_id} uses unavailable contexts: {','.join(disallowed)}")
        if uses_hash_files:
            errors.append(f"{label}.{env_id} uses unavailable function: hashFiles")
    return errors


def validate_workflow_expression_contexts(
    workflow: object,
    *,
    label: str,
) -> list[str]:
    """Validate expression contexts that GitHub resolves before a runner exists."""

    if not isinstance(workflow, dict):
        return [f"{label} workflow root must be a mapping"]
    errors = _validate_env_contexts(
        workflow.get("env"),
        label=f"{label}.env",
        allowed_contexts=TOP_LEVEL_ENV_CONTEXTS,
    )
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return errors + [f"{label}.jobs must be a non-empty mapping"]
    for job_id, job in sorted(jobs.items(), key=lambda item: str(item[0])):
        if not isinstance(job, dict):
            errors.append(f"{label}.jobs.{job_id} must be a mapping")
            continue
        errors.extend(
            _validate_env_contexts(
                job.get("env"),
                label=f"{label}.jobs.{job_id}.env",
                allowed_contexts=JOB_ENV_CONTEXTS,
            )
        )
    return errors


def _has_trigger(workflow: dict[str, object], trigger: str) -> bool:
    configured = workflow.get("on")
    if isinstance(configured, str):
        return configured == trigger
    if isinstance(configured, list):
        return trigger in configured
    return isinstance(configured, dict) and trigger in configured


def _governance_checkout_steps(
    workflow: dict[str, object],
) -> list[tuple[str, int, dict[str, object]]]:
    matches: list[tuple[str, int, dict[str, object]]] = []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return matches
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            inputs = step.get("with")
            if isinstance(inputs, dict) and inputs.get("repository") == GOVERNANCE_REPOSITORY:
                matches.append((str(job_id), index, step))
    return matches


def _validate_fork_rejection(
    workflow: dict[str, object],
    *,
    label: str,
    job_id: str,
) -> list[str]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return [f"{label}.jobs is not a mapping"]
    job = jobs.get(job_id)
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return [f"{label}.jobs.{job_id} has no first-step fork rejection"]
    first = steps[0]
    errors: list[str] = []
    if first.get("name") != FORK_REJECTION_STEP_NAME:
        errors.append(f"{label}.jobs.{job_id} fork rejection is not the first step")
    if _normalize_command(str(first.get("if", ""))) != FORK_REJECTION_CONDITION:
        errors.append(f"{label}.jobs.{job_id} fork rejection condition drift")
    if first.get("shell") != "bash":
        errors.append(f"{label}.jobs.{job_id} fork rejection shell drift")
    if _normalize_command(str(first.get("run", ""))) != FORK_REJECTION_COMMAND:
        errors.append(f"{label}.jobs.{job_id} fork rejection command drift")
    return errors


def validate_governance_dependency_auth(
    workflow: object,
    *,
    label: str,
    required: bool,
) -> list[str]:
    """Enforce one checkout-only deploy key and fail-closed fork PR handling."""

    if not isinstance(workflow, dict):
        return [f"{label} workflow root must be a mapping"]
    errors: list[str] = []
    if _has_trigger(workflow, "pull_request_target"):
        errors.append(f"{label} must not use pull_request_target")

    checkouts = _governance_checkout_steps(workflow)
    if not required:
        if checkouts:
            errors.append(f"{label} has an unauthorized Governance checkout")
        for path, value in _string_values(workflow):
            if "MOOMOOAU_GOVERNANCE_DEPLOY_KEY" in value:
                errors.append(f"{label}.{'.'.join(path)} has an unauthorized Governance deploy key")
        return errors

    if not _has_trigger(workflow, "pull_request"):
        errors.append(f"{label} must retain the pull_request trigger")
    if len(checkouts) != 1:
        errors.append(
            f"{label} must have exactly one pinned Governance checkout; found {len(checkouts)}"
        )
        return errors

    job_id, step_index, checkout = checkouts[0]
    errors.extend(_validate_fork_rejection(workflow, label=label, job_id=job_id))
    action = checkout.get("uses")
    if (
        not isinstance(action, str)
        or re.fullmatch(r"actions/checkout@[0-9a-f]{40}", action) is None
    ):
        errors.append(f"{label}.jobs.{job_id} Governance checkout is not SHA pinned")
    inputs = checkout.get("with")
    if not isinstance(inputs, dict):
        errors.append(f"{label}.jobs.{job_id} Governance checkout inputs are missing")
        return errors
    expected_inputs = {
        "repository": GOVERNANCE_REPOSITORY,
        "ref": GOVERNANCE_PIN,
        "path": ".governance",
        "persist-credentials": "false",
        "ssh-key": GOVERNANCE_DEPLOY_KEY_EXPRESSION,
    }
    for key, expected in expected_inputs.items():
        if inputs.get(key) != expected:
            errors.append(f"{label}.jobs.{job_id}.steps.{step_index}.with.{key} drift")

    allowed_secret_path = (
        "jobs",
        job_id,
        "steps",
        str(step_index),
        "with",
        "ssh-key",
    )
    secret_references = [
        (path, value)
        for path, value in _string_values(workflow)
        if "secrets" in _expression_contexts(value)[0]
    ]
    if secret_references != [(allowed_secret_path, GOVERNANCE_DEPLOY_KEY_EXPRESSION)]:
        rendered = [f"{'.'.join(path)}={value}" for path, value in secret_references]
        errors.append(f"{label} secret references must be checkout-only: {rendered}")
    return errors


def validate_governance_dependency_contract(repository_root: Path) -> list[str]:
    path = repository_root / "LinzeDatabase/MooMooAU/machine/contracts/governance_binding.json"
    try:
        binding = _load(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ["Governance dependency authentication contract is missing or invalid"]
    errors: list[str] = []
    if (
        not isinstance(binding, dict)
        or binding.get("version") != "1.0.2"
        or binding.get("repository") != GOVERNANCE_REPOSITORY
        or binding.get("commit") != GOVERNANCE_PIN
        or binding.get("consumption_mode") != "external pinned read-only deploy-key checkout"
    ):
        errors.append("Governance dependency binding identity drift")
    if (
        not isinstance(binding, dict)
        or binding.get("workflow_authentication") != EXPECTED_GOVERNANCE_AUTH_POLICY
    ):
        errors.append("Governance dependency authentication policy drift")
    return errors


def validate_governance_dependency_workflow(
    path: Path,
    *,
    repository_root: Path,
) -> list[str]:
    """Validate one workflow that consumes the protected Governance dependency."""

    try:
        label = (
            path.resolve(strict=True).relative_to(repository_root.resolve(strict=True)).as_posix()
        )
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
        return [f"{path.name} is not a safe readable workflow"]
    return validate_workflow_expression_contexts(
        workflow,
        label=label,
    ) + validate_governance_dependency_auth(
        workflow,
        label=label,
        required=True,
    )


def validate_repository_workflow_contexts(repository_root: Path) -> list[str]:
    """Validate pre-runner contexts and the checkout-only dependency credential."""

    errors = validate_governance_dependency_contract(repository_root)
    workflow_paths = _moomooau_workflow_paths(repository_root)
    if not workflow_paths:
        return ["no MooMooAU workflows are present"]
    labels: set[str] = set()
    for path in workflow_paths:
        label = path.relative_to(repository_root).as_posix()
        labels.add(label)
        try:
            workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            errors.append(f"{label} is not readable YAML")
            continue
        errors.extend(validate_workflow_expression_contexts(workflow, label=label))
        errors.extend(
            validate_governance_dependency_auth(
                workflow,
                label=label,
                required=label in GOVERNANCE_DEPENDENCY_WORKFLOWS,
            )
        )
    missing = sorted(GOVERNANCE_DEPENDENCY_WORKFLOWS - labels)
    if missing:
        errors.append(f"Governance dependency workflows are missing: {missing}")
    return errors


def _tree_digest(root: Path, repository_root: Path, workflow_paths: list[Path]) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not (set(path.parts) & IGNORED_PARTS)
        and path.suffix != ".pyc"
    ]
    paths.extend(workflow_paths)
    for path in sorted(set(paths), key=str):
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else path.relative_to(repository_root).as_posix()
        )
        digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _schema_errors(value: object, root: Path) -> list[str]:
    try:
        schema = _load(root / SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError):
        return ["workflow command matrix schema is missing or invalid"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        "schema violation at "
        + (".".join(str(part) for part in error.absolute_path) or "<root>")
        + f": {error.validator}"
        for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
    ]


def _expected_command(stage_id: str) -> str:
    validator = EXPECTED_ENTRIES[stage_id]["validator"]
    return (
        f'python {validator} --governance-root "$GITHUB_WORKSPACE/.governance" --cumulative-final'
    )


def validate_contract(
    root: Path = PROJECT_ROOT,
    value: object | None = None,
) -> list[str]:
    """Validate exact matrix/workflow binding without executing a subprocess."""

    root = root.resolve()
    repository_root = root.parents[1]
    if value is None:
        try:
            value = _load(root / MATRIX_PATH)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ["workflow command matrix is missing or invalid"]
    errors = _schema_errors(value, root)
    errors.extend(validate_repository_workflow_contexts(repository_root))
    if errors or not isinstance(value, dict):
        return errors
    if value.get("governance_pin") != GOVERNANCE_PIN:
        errors.append("workflow command matrix Governance pin drift")
    entries = value.get("entries")
    if not isinstance(entries, list):
        return errors + ["workflow command matrix entries must be a list"]
    if [entry.get("stage_id") for entry in entries if isinstance(entry, dict)] != list(
        EXPECTED_ENTRIES
    ):
        errors.append("workflow command matrix stages must be exact and ordered S3-S6")
        return errors

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        stage_id = str(entry.get("stage_id"))
        expected = EXPECTED_ENTRIES[stage_id]
        expected_command = _expected_command(stage_id)
        cumulative = entry.get("cumulative_expectation")
        historical = entry.get("historical_default_expectation")
        if (
            entry.get("workflow") != expected["workflow"]
            or entry.get("working_directory") != "LinzeDatabase/MooMooAU"
            or entry.get("workflow_command") != expected_command
            or cumulative != {"exit_code": 0, "status": "PASS", "failed_check_ids": []}
            or historical
            != {
                "exit_code": 1,
                "status": "BLOCKED",
                "failed_check_ids": [expected["scope_failure"]],
            }
        ):
            errors.append(f"{stage_id} command or expectation drift")
            continue
        workflow_path = repository_root / str(entry["workflow"])
        try:
            resolved = workflow_path.resolve(strict=True)
            resolved.relative_to(repository_root)
        except (OSError, ValueError):
            errors.append(f"{stage_id} workflow path is missing or escapes the repository")
            continue
        if workflow_path.is_symlink() or not workflow_path.is_file():
            errors.append(f"{stage_id} workflow path is unsafe")
            continue
        workflow_text = workflow_path.read_text(encoding="utf-8")
        normalized = _normalize_command(workflow_text)
        if normalized.count(expected_command) != 1:
            errors.append(f"{stage_id} cumulative command is not present exactly once")
        if workflow_text.count('"LinzeDatabase/MooMooAU/**"') != 2:
            errors.append(f"{stage_id} project trigger binding drift")
        if _sha256(workflow_path) != entry.get("workflow_sha256"):
            errors.append(f"{stage_id} workflow byte digest drift")
    return errors


def _local_argv(entry: dict[str, Any], governance_root: Path, *, cumulative: bool) -> list[str]:
    argv = shlex.split(str(entry["workflow_command"]))
    if argv[0] != "python" or argv[-1] != "--cumulative-final":
        raise ValueError("unsafe or non-canonical workflow command")
    argv[0] = sys.executable
    argv[argv.index("$GITHUB_WORKSPACE/.governance")] = str(governance_root)
    if not cumulative:
        argv.remove("--cumulative-final")
    return argv


def _run_command(
    entry: dict[str, Any],
    root: Path,
    governance_root: Path,
    *,
    cumulative: bool,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        _local_argv(entry, governance_root, cumulative=cumulative),
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = {}
    expected = (
        entry["cumulative_expectation"] if cumulative else entry["historical_default_expectation"]
    )
    signals = result.get("signals", {}) if isinstance(result, dict) else {}
    zero_names = COMMON_ZERO_SIGNALS | (OPTIONAL_ZERO_SIGNALS & set(signals))
    zero_signals = (
        isinstance(signals, dict)
        and COMMON_ZERO_SIGNALS.issubset(signals)
        and all(signals.get(name) == 0 for name in zero_names)
    )
    matched = (
        completed.returncode == expected["exit_code"]
        and result.get("stage_id") == entry["stage_id"]
        and result.get("status") == expected["status"]
        and result.get("failed_check_ids") == expected["failed_check_ids"]
        and zero_signals
    )
    return {
        "stage_id": entry["stage_id"],
        "mode": "CUMULATIVE_FINAL" if cumulative else "HISTORICAL_DEFAULT",
        "status": "PASS" if matched else "FAIL",
        "exit_code": completed.returncode,
        "validator_status": result.get("status"),
        "failed_check_ids": result.get("failed_check_ids"),
        "zero_external_effect_signals": zero_signals,
    }


def validate(
    root: Path,
    governance_root: Path,
    *,
    execute: bool,
) -> dict[str, Any]:
    root = root.resolve()
    repository_root = root.parents[1]
    governance_root = governance_root.resolve()
    try:
        value = _load(root / MATRIX_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        value = None
    contract_errors = validate_contract(root, value)
    if not governance_root.is_dir() or governance_root.is_symlink():
        contract_errors.append("pinned Governance root is missing or unsafe")
    entries = value.get("entries", []) if isinstance(value, dict) else []
    workflow_paths = _moomooau_workflow_paths(repository_root)
    before = _tree_digest(root, repository_root, workflow_paths) if not contract_errors else ""
    results: list[dict[str, Any]] = []
    if not contract_errors and execute:
        for entry in entries:
            results.append(_run_command(entry, root, governance_root, cumulative=True))
            results.append(_run_command(entry, root, governance_root, cumulative=False))
    after = _tree_digest(root, repository_root, workflow_paths) if not contract_errors else ""
    read_only = before == after and bool(before)
    execution_ok = not execute or (
        len(results) == 8 and all(item["status"] == "PASS" for item in results)
    )
    status = "PASS" if not contract_errors and read_only and execution_ok else "FAIL"
    return {
        "schema_version": "moomooau.workflow-command-matrix-result.v1",
        "status": status,
        "mode": "EXECUTE" if execute else "CONTRACT_ONLY",
        "matrix": MATRIX_PATH.as_posix(),
        "contract_errors": contract_errors,
        "tree_unchanged": read_only,
        "results": results,
        "protected_oracles_executed": 0,
        "production_workflow_runs": 0,
        "remote_workflow_runs": 0,
        "external_writes": 0,
        "remote_publications": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()
    result = validate(args.root, args.governance_root, execute=not args.contract_only)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
