#!/usr/bin/env python3
"""Fail-closed, read-only cumulative validator for MooMooAU Stage 5."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
STAGE4_TOOLS = PROJECT_ROOT / "machine/stages/S4/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
STAGE5_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage5-ci.yml"
PRODUCTION_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-production.yml"
BASELINE_COMMIT = "9394585329a52c4d269da220bd66ce8ec9b820b3"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
STAGE5_LOCK_SHA256 = "4bc092e4f76e977a8299bc94beb4a195aa124d092516669e20d59bc9aba3d75c"
STAGE5_SBOM_SHA256 = "eb3ab4dfc43f645badd92a3b9409339e843ec986947330e2324af9fcde0872c1"
STAGE5_TASKS = [f"T050{i}" for i in range(1, 8)]
STAGE5_ACCEPTANCES = [f"S5AC-00{i}" for i in range(1, 8)]
IGNORED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")

for import_path in (STAGE4_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_publication import (  # noqa: E402
    EMAIL,
    LOCAL_PATH,
    SECRET_PATTERNS,
    scan_tree,
)
from validate_stage4 import evaluate_stage4  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_workflow,
)

from moomooau_archive.github_guard import (  # noqa: E402
    GITHUB_API_VERSION,
    LIVE_ASSET_NAME,
    LIVE_RELEASE_TAG,
    TIMELINE_STATE_PATH,
)
from moomooau_archive.run_schedule import TARGET_CRON, TARGET_TIMEZONE  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(check_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and not (set(path.parts) & IGNORED_PARTS)
    ]
    for workflow in (
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage1-ci.yml",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage2-security.yml",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage3-ci.yml",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage4-ci.yml",
        STAGE5_WORKFLOW,
        PRODUCTION_WORKFLOW,
    ):
        if workflow.is_file():
            paths.append(workflow)
    for path in sorted(set(paths), key=str):
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else path.relative_to(REPOSITORY_ROOT).as_posix()
        )
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _validate_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S5"}
    expected_dependencies = {
        "T0501": ["T0407"],
        "T0502": ["T0501"],
        "T0503": ["T0502"],
        "T0504": ["T0503"],
        "T0505": ["T0504"],
        "T0506": ["T0505"],
        "T0507": ["T0506"],
    }
    expected_links = {task_id: graph_tasks[task_id]["acceptance_ids"] for task_id in STAGE5_TASKS}
    if len(graph_tasks) != 7 or any(
        graph_tasks[task_id].get("dependencies") != dependencies
        for task_id, dependencies in expected_dependencies.items()
    ):
        errors.append("Stage 5 dependency chain drifts from the frozen task graph")

    local = _load(root / "machine/stages/S5/contracts/stage5_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE5_ACCEPTANCES:
        errors.append("Stage 5 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE5_TASKS:
        errors.append("Stage 5 acceptance to task mapping must be one-to-one")
    required_fields = {
        "title",
        "environment",
        "input",
        "oracle",
        "threshold",
        "evidence_required",
        "verification",
        "failure_action",
    }
    for item in items:
        task_id = item.get("task_id")
        if (
            task_id not in expected_links
            or item.get("linked_final_acceptance_ids") != expected_links[task_id]
        ):
            errors.append("Stage 5 final acceptance links drift from the frozen task graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 5 acceptance contract is incomplete")

    run_contract = _load(root / "machine/stages/S5/contracts/run_contract.json")
    prohibitions = run_contract.get("prohibitions", {})
    non_goals = run_contract.get("non_goals", [])
    if (
        run_contract.get("stage_id") != "S5"
        or run_contract.get("baseline_commit") != BASELINE_COMMIT
        or run_contract.get("baseline_manifest_sha256") != BASELINE_MANIFEST_SHA256
        or not run_contract.get("protected_oracles")
        or not isinstance(prohibitions, dict)
        or any(value != 0 for value in prohibitions.values())
        or "Stage 6 or later tasks" not in non_goals
        or "intermediate GitHub upload" not in non_goals
        or "enabling or deploying the protected production workflow" not in non_goals
    ):
        errors.append("Stage 5 run contract is incomplete or grants production authority")

    status = _load(root / "machine/stages/S5/contracts/task_status.json")
    if (
        [item.get("id") for item in status.get("tasks", [])] != STAGE5_TASKS
        or any(item.get("status") != "completed" for item in status.get("tasks", []))
        or status.get("baseline_commit") != BASELINE_COMMIT
        or status.get("later_stage_status") != "planned_unchanged"
        or status.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
    ):
        errors.append("Stage 5 task status overlay is incomplete")

    semantic = _load(root / "machine/stages/S5/contracts/semantic_gate.json")
    semantic_statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("stage_id") != "S5"
        or semantic.get("status") != "PASS"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or not semantic_statuses.issubset({"RESOLVED", "CONTROLLED_NOT_RUN"})
        or "CONTROLLED_NOT_RUN" not in semantic_statuses
    ):
        errors.append("Stage 5 semantic gate is incomplete or overstates protected oracles")
    return errors


def _validate_schema(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator

    path = root / "machine/stages/S5/public-schemas/timeline-event-complete-v1.schema.json"
    try:
        schema = _load(path)
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [f"Stage 5 complete Timeline schema is invalid: {type(exc).__name__}"]
    required = set(schema.get("required", []))
    expected = {
        "email_internal_date_utc",
        "email_received_at_sydney",
        "statement_label_date",
        "us_market_session_lag",
        "expectation_state",
        "expectation_reason_code",
        "m3_state",
        "parser_state",
    }
    if not expected.issubset(required) or schema.get("additionalProperties") is not False:
        return ["Stage 5 Timeline schema is incomplete or open-ended"]
    return []


def _validate_source_boundaries(root: Path) -> list[str]:
    errors: list[str] = []
    paths = {
        name: root / "src/moomooau_archive" / f"{name}.py"
        for name in (
            "remote_recovery_gate",
            "m3",
            "market_calendar",
            "timeline_event",
            "timeline_render",
            "timeline_publish",
            "run_schedule",
            "gmail_guard",
            "github_guard",
        )
    }
    source = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    required: dict[str, tuple[str, ...]] = {
        "remote_recovery_gate": (
            "OfficialAgeDecryptor",
            "remote ciphertext is missing or differs from the commit",
            "remote plaintext digest does not match",
            "processed_state",
            "not in _SAFE_PROCESSED_STATES",
        ),
        "m3": (
            "double_verification_matches",
            "recovery_proof",
            "MutationBudget",
            "trash_message_request",
            "TRASH_LABEL_NOT_CONFIRMED",
            "TRASH_CALL_OUTCOME_UNKNOWN",
        ),
        "market_calendar": (
            "xcals.get_calendar(self.calendar_name)",
            "NOT_EXPECTED",
            "NOT_OBSERVED",
            "MISSING",
            "independent_activity_evidence",
        ),
        "timeline_event": (
            '"Australia/Sydney"',
            "email_internal_date_utc",
            "email_received_at_sydney",
            "expectation_reason_code",
            "m3_state",
        ),
        "timeline_render": (
            "width = 1200",
            "height = 720",
            "ImageFont.load_default()",
            'format="PNG"',
            "compress_level=9",
        ),
        "timeline_publish": (
            "LIVE_ASSET_NAME",
            "LIVE_RELEASE_TAG",
            "TIMELINE_REPAIR_REQUIRED",
            "processed_snapshot_root",
            "delete(",
            "upload(",
        ),
        "run_schedule": (
            'TARGET_CRON = "30 4 * * *"',
            'TARGET_TIMEZONE = "Australia/Sydney"',
            "FULL_SUNDAY",
            "FULL_MANUAL",
            '"platform_sla_claimed": False',
        ),
    }
    for name, tokens in required.items():
        if any(token not in source[name] for token in tokens):
            errors.append(f"Stage 5 {name} invariant is missing")

    gmail = source["gmail_guard"]
    if (
        'GmailOperation.MESSAGE_TRASH = "messages.trash"' in gmail
        or "/gmail/v1/users/me/threads" in gmail
        or "/delete" in gmail
        or "/batchDelete" in gmail
        or 'request.method not in {"GET", "POST"}' not in gmail
        or "messages.trash requires an empty body" not in gmail
    ):
        errors.append(
            "Gmail boundary permits a thread, permanent-delete or invalid mutation surface"
        )
    if (
        GITHUB_API_VERSION != "2026-03-10"
        or LIVE_RELEASE_TAG != "moomooau-live"
        or LIVE_ASSET_NAME != "timeline-latest.png.age"
        or TIMELINE_STATE_PATH != "MooMooAU/State/timeline-current.json.age"
        or TARGET_CRON != "30 4 * * *"
        or TARGET_TIMEZONE != "Australia/Sydney"
    ):
        errors.append("fixed GitHub or schedule constants drifted")

    combined = "\n".join(source.values()).casefold()
    forbidden_runtime = (
        "moomoo.com",
        "openapi.moomoo.com",
        "import socket",
        "import tempfile",
        "launchd",
        "crontab",
        "apscheduler",
        "extractall(",
        "eval(",
        "exec(",
    )
    if any(token in combined for token in forbidden_runtime):
        errors.append("Stage 5 runtime contains Portal, local scheduler or unsafe execution scope")
    return errors


def _validate_lock(root: Path) -> list[str]:
    errors: list[str] = []
    lock = root / "requirements/stage5.lock"
    if not lock.is_file() or _sha256(lock) != STAGE5_LOCK_SHA256:
        return ["Stage 5 lock digest is missing or drifted"]
    text = lock.read_text(encoding="utf-8")
    required = (
        "exchange-calendars==4.13.2",
        "pillow==12.3.0",
        "cryptography==49.0.0",
        "pikepdf==10.10.0",
        "pyarrow==25.0.0",
        "--hash=sha256:",
    )
    if any(token not in text for token in required):
        errors.append("Stage 5 lock is missing an exact dependency or hashes")
    if "--index-url" in text or "--extra-index-url" in text or "file://" in text:
        errors.append("Stage 5 lock contains a non-default or local package source")
    package_starts = [
        index
        for index, line in enumerate(text.splitlines())
        if line and not line[0].isspace() and not line.startswith("#") and "==" in line
    ]
    lines = text.splitlines()
    for position, start in enumerate(package_starts):
        end = package_starts[position + 1] if position + 1 < len(package_starts) else len(lines)
        if not any("--hash=sha256:" in line for line in lines[start:end]):
            errors.append("Stage 5 lock contains an unhashed package block")
            break

    sbom_path = root / "machine/stages/S5/supply-chain/sbom.cdx.json"
    if not sbom_path.is_file() or _sha256(sbom_path) != STAGE5_SBOM_SHA256:
        errors.append("Stage 5 reproducible SBOM is missing or drifted")
    else:
        sbom = _load(sbom_path)
        components = {
            item.get("name"): item.get("version")
            for item in sbom.get("components", [])
            if isinstance(item, dict)
        }
        expected = {"exchange-calendars": "4.13.2", "pillow": "12.3.0"}
        if any(components.get(name) != version for name, version in expected.items()):
            errors.append("Stage 5 SBOM does not bind the exact calendar and renderer dependencies")
        if '"purl"' in sbom_path.read_text(encoding="utf-8"):
            errors.append("Stage 5 public-safe SBOM still contains package URL locators")
    return errors


def _action_uses(workflow: str) -> list[str]:
    return re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)


def _validate_workflows(root: Path) -> list[str]:
    errors: list[str] = []
    if not STAGE5_WORKFLOW.is_file() or not PRODUCTION_WORKFLOW.is_file():
        return ["Stage 5 CI or protected production workflow is missing"]
    ci = STAGE5_WORKFLOW.read_text(encoding="utf-8")
    production = PRODUCTION_WORKFLOW.read_text(encoding="utf-8")
    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    uses = _action_uses(ci)
    if len(uses) != 8 or any(PINNED_ACTION.fullmatch(item) is None for item in uses):
        errors.append("all eight Stage 5 CI Action uses must be immutable commit SHAs")
    for action, metadata in pins.get("actions", {}).items():
        expected = metadata.get("commit_sha") if isinstance(metadata, dict) else None
        if not any(
            item.rsplit("@", 1)[1] == expected
            and (
                item.rsplit("@", 1)[0] == action or item.rsplit("@", 1)[0].startswith(action + "/")
            )
            for item in uses
        ):
            errors.append("Stage 5 CI drifts from the immutable Action pin catalog")
    required_ci = (
        "--require-hashes",
        "--cumulative-final",
        "requirements/stage5.lock",
        "test_t05*.py",
        "validate_stage5.py",
        "pip_audit",
        "detect-secrets",
        "dependency-review-action",
        "codeql-action/init",
        "codeql-action/analyze",
        "docker build --no-cache",
        "--network none",
        "--read-only",
        "python -m build",
        "machine/stages/S5/supply-chain/sbom.cdx.json",
        "--exclude-files 'machine/stages/S5/supply-chain/sbom\\.cdx\\.json'",
    )
    forbidden_ci = (
        "self-hosted",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "schedule:",
        "workflow_dispatch",
        "git push",
        "contents: write",
    )
    if any(token not in ci for token in required_ci) or any(
        token in ci.casefold() for token in forbidden_ci
    ):
        errors.append("Stage 5 CI is missing a gate or adds persistence, schedule or authority")
    errors.extend(
        validate_governance_dependency_workflow(
            STAGE5_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )
    age_digest = pins.get("age", {}).get("linux_amd64_archive_sha256")
    if not isinstance(age_digest, str) or age_digest not in ci:
        errors.append("Stage 5 CI does not pin the official age archive")

    legacy_required_production = (
        'cron: "30 4 * * *"',
        'timezone: "Australia/Sydney"',
        "workflow_dispatch:",
        "runs-on: ubuntu-24.04",
        "MOOMOOAU_PRODUCTION_ENABLED == 'true'",
        "cancel-in-progress: false",
        "requirements/stage5.lock",
        "MOOMOOAU_STAGE5_PROTECTED_ORACLE:-NOT_RUN",
    )
    common_forbidden_production = (
        "self-hosted",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "git push",
        "contents: write",
    )
    production_uses = _action_uses(production)
    legacy_valid = (
        all(token in production for token in legacy_required_production)
        and "${{ secrets." not in production
        and not any(token in production.casefold() for token in common_forbidden_production)
        and all(PINNED_ACTION.fullmatch(item) is not None for item in production_uses)
    )
    production_secret_names = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", production))
    expected_secret_names = {
        "MOOMOOAU_PRODUCTION_CONFIG",
        "MOOMOOAU_SENDER_REGISTRY",
        "MOOMOOAU_CLASSIFICATION_REGISTRY",
        "MOOMOOAU_PARSER_REGISTRY",
        "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
        "MOOMOOAU_AGE_IDENTITY",
        "MOOMOOAU_OPAQUE_ID_KEY",
        "MOOMOOAU_GMAIL_OAUTH",
    }
    composition_required = (
        'cron: "30 4 * * *"',
        'timezone: "Australia/Sydney"',
        "workflow_dispatch:",
        "runs-on: ubuntu-24.04",
        "MOOMOOAU_PRODUCTION_ENABLED == 'true'",
        "cancel-in-progress: false",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        "bdc69c09cbdd6cf8b1f333d372a1f58247b3a33146406333e30c0f26e8f51377",  # pragma: allowlist secret  # noqa: E501
        "python -m moomooau_archive.production",
        "--execute-protected",
        '--event-name "$EVENT_NAME"',
        "persist-credentials: false",
        "environment: moomooau-production",
        "permissions:\n  contents: read",
    )
    composition_valid = (
        (root / "src/moomooau_archive/production.py").is_file()
        and all(token in production for token in composition_required)
        and production_secret_names == expected_secret_names
        and production.count("${{ secrets.") == len(expected_secret_names)
        and not any(token in production.casefold() for token in common_forbidden_production)
        and len(production_uses) == 2
        and all(PINNED_ACTION.fullmatch(item) is not None for item in production_uses)
    )
    if not (legacy_valid or composition_valid):
        errors.append(
            "protected production workflow is neither the Stage 5 hold nor the later "
            "fail-closed composition"
        )

    dockerfile = (root / "container/Dockerfile.stage5-ci").read_text(encoding="utf-8")
    container_digest = pins.get("container", {}).get("oci_index_digest")
    if (
        not isinstance(container_digest, str)
        or "@" + container_digest not in dockerfile
        or "--require-hashes" not in dockerfile
        or "requirements/stage5.lock" not in dockerfile
        or "not a production runtime image" not in dockerfile
    ):
        errors.append("Stage 5 validation container is mutable or overstated")
    return errors


def _validate_public_surfaces(root: Path) -> list[str]:
    errors: list[str] = []
    publication = scan_tree(root)
    if publication["status"] != "PASS":
        errors.append("project publication scan found forbidden values")
    for path in (STAGE5_WORKFLOW, PRODUCTION_WORKFLOW):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if (
            EMAIL.search(text)
            or LOCAL_PATH.search(text)
            or any(pattern.search(text) for pattern in SECRET_PATTERNS)
        ):
            errors.append(f"{path.name} contains a forbidden sensitive pattern")
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S5/schemas/stage5-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S5"}
    for index, task_id in enumerate(STAGE5_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid evidence schema for {task_id}")
            continue
        if record["stage_acceptance_id"] != f"S5AC-00{index}" or record["record_status"] != "PASS":
            errors.append(f"evidence identity or status mismatch for {task_id}")
        if any(item["status"] != "PASS" for item in record["checks"]):
            errors.append(f"non-passing Stage 5 check for {task_id}")
        linked = record["linked_final_acceptance"]
        if [item["id"] for item in linked] != graph_tasks[task_id]["acceptance_ids"] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"} for item in linked
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        if any(item["status"] != "NOT_RUN" for item in record["production_oracles"]):
            errors.append(f"production oracle is overstated for {task_id}")
        if any(record["prohibition_counters"].values()):
            errors.append(f"prohibition counter is nonzero for {task_id}")

    latest = _load(root / "evidence/stage5/latest.json")
    observation = latest.get("stage5_observation", {})
    expected_not_run = (
        "private_remote_recovery",
        "real_source_message_trash",
        "real_live_release_replacement",
        "remote_stage5_ci",
        "protected_schedule_execution",
    )
    if (
        latest.get("stage_id") != "S5"
        or latest.get("status") != "PASS"
        or latest.get("scope") != "LOCAL_SYNTHETIC_ONLY"
        or latest.get("task_pass_count") != 7
        or latest.get("task_total") != 7
        or latest.get("stage5_task_tests_passed") != 21
        or latest.get("cumulative_task_tests_passed") != 116
        or latest.get("final_acceptance_policy") != "NOT_FINAL"
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or any(latest.get("prohibition_counters", {}).values())
        or observation.get("synthetic_recovery_proofs_issued") != 2
        or observation.get("synthetic_corrupt_recovery_authorizations") != 0
        or observation.get("synthetic_gmail_mutations") != 2
        or observation.get("real_gmail_calls") != 0
        or observation.get("real_gmail_mutations") != 0
        or observation.get("private_repository_calls") != 0
        or observation.get("thread_trash_calls") != 0
        or observation.get("permanent_delete_calls") != 0
        or observation.get("persistent_plaintext_objects") != 0
        or observation.get("release_assets_above_one") != 0
        or observation.get("stranded_uncertain_or_corrupt_assets") != 0
        or observation.get("production_workflow_runs") != 0
        or observation.get("dependency_advisory_scan") != "PASS"
        or observation.get("known_vulnerabilities_observed") != 0
        or observation.get("local_secret_scan_findings") != 0
        or observation.get("package_build_smoke") != "PASS"
        or observation.get("taskpack_validation") != "PASS"
        or observation.get("governance_validation") != "PASS"
        or observation.get("digest_pinned_container_build") != "PASS"
        or observation.get("network_none_read_only_container_smoke") != "PASS"
        or any(observation.get(key) != "NOT_RUN" for key in expected_not_run)
        or latest.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
        or latest.get("next_stage") != "S6"
        or latest.get("next_stage_status") != "NOT_STARTED"
    ):
        errors.append("Stage 5 aggregate evidence is not a fail-closed local PASS record")
    return errors


def evaluate_stage5(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
    *,
    include_delivery_records: bool = True,
    allow_stage6: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    before = _tree_digest(root)
    checks: list[dict[str, str]] = []
    manifest = root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"
    checks.append(
        _check(
            "baseline.manifest_identity",
            _sha256(manifest) == BASELINE_MANIFEST_SHA256,
            "frozen Stage 0 manifest digest matches the verified handoff",
        )
    )
    stage4 = evaluate_stage4(root, governance_root, allow_stage5=True)
    checks.append(
        _check(
            "baseline.cumulative_stage4",
            stage4["status"] == "PASS",
            f"Stage 4 failed checks {len(stage4['failed_check_ids'])}",
        )
    )
    contract_errors = _validate_contracts(root)
    checks.append(
        _check(
            "contracts.stage5_overlay",
            not contract_errors,
            f"Stage 5 contract errors {len(contract_errors)}",
        )
    )
    required = [
        root / "src/moomooau_archive/remote_recovery_gate.py",
        root / "src/moomooau_archive/m3.py",
        root / "src/moomooau_archive/market_calendar.py",
        root / "src/moomooau_archive/timeline_event.py",
        root / "src/moomooau_archive/timeline_render.py",
        root / "src/moomooau_archive/timeline_publish.py",
        root / "src/moomooau_archive/run_schedule.py",
        root / "tests/stage5_support.py",
        root / "requirements/stage5.lock",
        root / "container/Dockerfile.stage5-ci",
        root / "machine/stages/S5/supply-chain/sbom.cdx.json",
        STAGE5_WORKFLOW,
        PRODUCTION_WORKFLOW,
    ] + [root / "tests/tasks" / f"test_{task_id.casefold()}.py" for task_id in STAGE5_TASKS]
    checks.append(
        _check(
            "package.stage5_structure",
            all(path.is_file() for path in required),
            f"required Stage 5 paths {len(required)}",
        )
    )
    schema_errors = _validate_schema(root)
    checks.append(
        _check(
            "timeline.complete_schema",
            not schema_errors,
            f"Timeline schema errors {len(schema_errors)}",
        )
    )
    source_errors = _validate_source_boundaries(root)
    checks.append(
        _check(
            "security.stage5_source_boundaries",
            not source_errors,
            f"source boundary errors {len(source_errors)}",
        )
    )
    lock_errors = _validate_lock(root)
    checks.append(
        _check(
            "security.stage5_hash_lock",
            not lock_errors,
            f"Stage 5 lock errors {len(lock_errors)}",
        )
    )
    workflow_errors = _validate_workflows(root)
    checks.append(
        _check(
            "security.no_secret_stage5_ci_and_disabled_schedule",
            not workflow_errors,
            f"Stage 5 workflow errors {len(workflow_errors)}",
        )
    )
    publication_errors = _validate_public_surfaces(root)
    checks.append(
        _check(
            "security.publication",
            not publication_errors,
            f"publication errors {len(publication_errors)}",
        )
    )
    stage6_paths = (
        root / "machine/stages/S6",
        root / "tests/tasks/test_t0601.py",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage6-ci.yml",
    )
    checks.append(
        _check(
            "scope.no_stage6_or_production_execution",
            allow_stage6 or not any(path.exists() for path in stage6_paths),
            (
                "Stage 6 paths explicitly allowed only for cumulative validation; "
                "real production execution counters 0"
                if allow_stage6
                else "Stage 6 implementation paths 0; real production execution counters 0"
            ),
        )
    )
    if include_delivery_records:
        evidence_errors = _validate_evidence(root)
        checks.append(
            _check(
                "evidence.stage5_records",
                not evidence_errors,
                f"Stage 5 evidence errors {len(evidence_errors)}",
            )
        )
    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "moomooau.stage5-verification.v1",
        "stage_id": "S5",
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_check_ids": failed,
        "signals": {
            "stage5_tasks": 7,
            "stage5_local_acceptances": 7,
            "stage5_synthetic_tests": 21,
            "cumulative_task_tests": 116,
            "real_gmail_calls": 0,
            "gmail_mutations": 0,
            "private_repository_calls": 0,
            "real_secrets_read": 0,
            "protected_key_deliveries": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "moomoo_portal_calls": 0,
            "persistent_plaintext_objects": 0,
            "thread_trash_calls": 0,
            "permanent_delete_calls": 0,
            "release_assets_above_one": 0,
            "production_workflow_runs": 0,
            "protected_oracles_executed": 0,
            "final_acceptances_passed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    parser.add_argument(
        "--cumulative-final",
        action="store_true",
        help=(
            "allow later-stage implementation paths in a cumulative final-tree validation; "
            "all production execution and external-effect checks remain fail closed"
        ),
    )
    args = parser.parse_args()
    result = evaluate_stage5(
        args.root,
        args.governance_root,
        allow_stage6=args.cumulative_final,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
