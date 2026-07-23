#!/usr/bin/env python3
"""Fail-closed, read-only cumulative validator for MooMooAU Stage 6."""

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
STAGE5_TOOLS = PROJECT_ROOT / "machine/stages/S5/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
SOFTWARE_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage6-ci.yml"
MODEL_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage6-model-assurance.yml"
BASELINE_COMMIT = "2b8625a83e69093b9dce989f4eb964556e1b5fa2"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
RMD05_MANIFEST_SHA256 = "f99413b9c1fb67369ba3039a7acfeb437004d1aad8cb54dc3697f87f38e35cb3"
STAGE6_LOCK_SHA256 = "bed62218c229318cb95575b7880bc5ed78558d6014e299582f62d32ba0a05eb7"
STAGE6_SBOM_SHA256 = "8e4e03817926857d1ffd8f131b108bcaac48238461749cbe9b0f4a78af00a197"
STAGE6_TASKS = [f"T060{i}" for i in range(1, 9)]
STAGE6_ACCEPTANCES = [f"S6AC-00{i}" for i in range(1, 9)]
IGNORED_PARTS = {
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")

for import_path in (STAGE5_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_assurance_reviews import evaluate_assurance_reviews  # noqa: E402
from validate_evidence import (  # noqa: E402
    STAGE6_CANDIDATE_RECEIPT_PATH,
    STAGE6_TASK_COMMAND_IDS,
    validate_record,
    validate_stage6_candidate_bundle,
)
from validate_publication import EMAIL, LOCAL_PATH, SECRET_PATTERNS, scan_tree  # noqa: E402
from validate_stage5 import evaluate_stage5  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_workflow,
)


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
    paths.extend(path for path in (SOFTWARE_WORKFLOW, MODEL_WORKFLOW) if path.is_file())
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
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S6"}
    expected_dependencies = {
        "T0601": ["T0507"],
        "T0602": ["T0601"],
        "T0603": ["T0602"],
        "T0604": ["T0603"],
        "T0605": ["T0604"],
        "T0606": ["T0605"],
        "T0607": ["T0606"],
        "T0608": ["T0607"],
    }
    if set(graph_tasks) != set(STAGE6_TASKS) or any(
        graph_tasks[task_id].get("dependencies") != dependencies
        for task_id, dependencies in expected_dependencies.items()
    ):
        errors.append("Stage 6 dependency chain drifts from the frozen task graph")

    local = _load(root / "machine/stages/S6/contracts/stage6_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE6_ACCEPTANCES:
        errors.append("Stage 6 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE6_TASKS:
        errors.append("Stage 6 acceptance to task mapping must be one-to-one")
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
            task_id not in graph_tasks
            or item.get("linked_final_acceptance_ids") != graph_tasks[task_id]["acceptance_ids"]
        ):
            errors.append("Stage 6 final acceptance links drift from the frozen task graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 6 acceptance contract is incomplete")

    run_contract = _load(root / "machine/stages/S6/contracts/run_contract.json")
    prohibitions = run_contract.get("prohibitions", {})
    non_goals = run_contract.get("non_goals", [])
    if (
        run_contract.get("stage_id") != "S6"
        or run_contract.get("baseline_commit") != BASELINE_COMMIT
        or run_contract.get("baseline_manifest_sha256") != BASELINE_MANIFEST_SHA256
        or not run_contract.get("protected_oracles")
        or not isinstance(prohibitions, dict)
        or any(value != 0 for value in prohibitions.values())
        or "Stage 7 or later tasks" not in non_goals
        or "intermediate GitHub upload" not in non_goals
        or "enabling, dispatching or deploying the protected production workflow" not in non_goals
    ):
        errors.append("Stage 6 run contract is incomplete or grants production authority")

    status = _load(root / "machine/stages/S6/contracts/task_status.json")
    if (
        [item.get("id") for item in status.get("tasks", [])] != STAGE6_TASKS
        or any(item.get("status") != "completed" for item in status.get("tasks", []))
        or status.get("baseline_commit") != BASELINE_COMMIT
        or status.get("later_stage_status") != "planned_unchanged"
        or status.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
    ):
        errors.append("Stage 6 task status overlay is incomplete")

    semantic = _load(root / "machine/stages/S6/contracts/semantic_gate.json")
    semantic_statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("stage_id") != "S6"
        or semantic.get("status") != "PASS"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or not semantic_statuses.issubset({"RESOLVED", "CONTROLLED_NOT_RUN"})
        or "CONTROLLED_NOT_RUN" not in semantic_statuses
    ):
        errors.append("Stage 6 semantic gate is incomplete or overstates protected oracles")
    return errors


def _test_ref_exists(root: Path, value: object) -> bool:
    if not isinstance(value, str) or "::" not in value:
        return False
    path_text, function = value.split("::", 1)
    path = root / path_text
    return path.is_file() and f"def {function}(" in path.read_text(encoding="utf-8")


def _validate_matrices(root: Path) -> list[str]:
    errors: list[str] = []
    base = root / "machine/stages/S6/matrices"
    chaos = _load(base / "mandatory-chaos.v1.json")
    scenarios = chaos.get("scenarios", [])
    if (
        [item.get("id") for item in scenarios] != [f"CH-{index:02d}" for index in range(1, 19)]
        or any(item.get("status") != "PASS" for item in scenarios)
        or any(not _test_ref_exists(root, item.get("test_ref")) for item in scenarios)
    ):
        errors.append("mandatory chaos is incomplete, unordered or marker-only")

    kills = _load(base / "kill-drills.v1.json").get("drills", [])
    if (
        [item.get("id") for item in kills] != [f"KILL-{index:03d}" for index in range(1, 11)]
        or any(item.get("status") != "PASS" for item in kills)
        or any(not item.get("resume_gates") for item in kills)
        or any(not _test_ref_exists(root, item.get("test_ref")) for item in kills)
    ):
        errors.append("Kill Criterion drills are incomplete or lack exact recovery tests")

    load = _load(base / "load-profiles.v1.json")
    profiles = load.get("profiles", [])
    l3: dict[str, Any] = next((item for item in profiles if item.get("id") == "L3"), {})
    if (
        load.get("status") != "PASS"
        or load.get("maximum_stream_batch") != 500
        or l3.get("messages") != 100_000
        or l3.get("attachments") != 200_000
        or l3.get("concurrency") != 8
        or len(load.get("required_boundaries", [])) != 10
    ):
        errors.append("L3 load profile or boundary catalog is incomplete")

    capacity = _load(base / "capacity-policy.v1.json")
    official = capacity.get("official_limits", {})
    if (
        official.get("repository_recommended_bytes") != 10_000_000_000
        or official.get("git_object_recommended_bytes") != 1_000_000
        or official.get("git_object_enforced_bytes") != 100_000_000
        or official.get("release_asset_maximum_bytes_exclusive") != 2_147_483_648
        or official.get("gmail_page_maximum") != 500
        or capacity.get("lfs_policy", {}).get("unknown_write_allowed") is not False
        or len(capacity.get("sources", [])) < 5
    ):
        errors.append("official capacity facts or fail-closed LFS policy drifted")
    return errors


def _validate_source_boundaries(root: Path) -> list[str]:
    errors: list[str] = []
    source_root = root / "src/moomooau_archive"
    required: dict[str, tuple[str, ...]] = {
        "retry.py": ("maximum_attempts", "RetryOperation.GMAIL_TRASH", "sleep", "429"),
        "publication_saga.py": (
            "PrivateState.RECOVERY_VERIFIED",
            "PENDING_RECONCILIATION",
            "source_mutation_attempts",
        ),
        "attachment_inspector.py": (
            "pikepdf.Pdf.open",
            "pdf_has_active_objects",
            "document.objects",
            "PDF_ENCRYPTED_DEFERRED",
        ),
        "capacity.py": (
            "GITHUB_REPOSITORY_RECOMMENDED_BYTES",
            "GITHUB_RELEASE_ASSET_MAXIMUM_BYTES",
            "CapacityState.UNKNOWN",
        ),
        "operation_gate.py": (
            "SensitiveOperation.RAW_WRITE",
            "SensitiveOperation.M3",
            "backfill_allowed",
            "action()",
        ),
        "load_probe.py": (
            "ThreadPoolExecutor",
            "duplicate_race",
            "LogicalObjectIndex",
            "batch_size <= 500",
        ),
        "kill_switch.py": (
            "KILL_010",
            "canonical_audit_bytes",
            "_RESUME_GATES[kill_id] == passing_gates",
        ),
        "model_boundary.py": (
            'REAL_EMAIL = "REAL_EMAIL"',
            'PRINT_RECOVERY_SECRET = "PRINT_RECOVERY_SECRET"',  # pragma: allowlist secret
            "CodexAutoMonitor",
        ),
    }
    for filename, tokens in required.items():
        text = (source_root / filename).read_text(encoding="utf-8")
        if any(token not in text for token in tokens):
            errors.append(f"Stage 6 source invariant is missing from {filename}")

    runtime = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))
    if any(token in runtime for token in ("ModelPort", "def dispatch(", "def invoke(")):
        errors.append("application runtime exposes a model dispatch surface")
    ephemeral = (source_root / "ephemeral.py").read_text(encoding="utf-8")
    if any(token in ephemeral for token in ("open(", "tempfile", "NamedTemporaryFile")):
        errors.append("ephemeral plaintext arena exposes a filesystem persistence primitive")
    if "os._exit" in runtime or "SIGKILL" in runtime:
        errors.append("Stage 6 runtime claims or simulates hard-kill memory erasure")
    return errors


def _validate_lock(root: Path) -> list[str]:
    errors: list[str] = []
    lock = root / "requirements/stage6.lock"
    if not lock.is_file() or _sha256(lock) != STAGE6_LOCK_SHA256:
        return ["Stage 6 lock digest is missing or drifted"]
    text = lock.read_text(encoding="utf-8")
    required = (
        "hypothesis==6.156.7",
        "pip-audit==2.10.1",
        "pikepdf==10.10.0",
        "ruff==0.15.22",
        "mypy==2.3.0",
        "--hash=sha256:",
    )
    if any(token not in text for token in required):
        errors.append("Stage 6 lock is missing an exact assurance dependency or hashes")
    if "--index-url" in text or "--extra-index-url" in text or "file://" in text:
        errors.append("Stage 6 lock contains a non-default or local package source")
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line and not line[0].isspace() and not line.startswith("#") and "==" in line
    ]
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        if not any("--hash=sha256:" in line for line in lines[start:end]):
            errors.append("Stage 6 lock contains an unhashed package block")
            break

    sbom_path = root / "machine/stages/S6/supply-chain/sbom.cdx.json"
    if not sbom_path.is_file() or _sha256(sbom_path) != STAGE6_SBOM_SHA256:
        errors.append("Stage 6 reproducible SBOM is missing or drifted")
    else:
        sbom = _load(sbom_path)
        components = {
            item.get("name"): item.get("version")
            for item in sbom.get("components", [])
            if isinstance(item, dict)
        }
        if components.get("hypothesis") != "6.156.7" or components.get("pip-audit") != "2.10.1":
            errors.append("Stage 6 SBOM does not bind the exact assurance dependencies")
        if len(components) != 91 or '"purl"' in sbom_path.read_text(encoding="utf-8"):
            errors.append("Stage 6 public-safe SBOM component set or locator stripping drifted")
    return errors


def _action_uses(workflow: str) -> list[str]:
    return re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)


def _validate_workflows(root: Path) -> list[str]:
    errors: list[str] = []
    if not SOFTWARE_WORKFLOW.is_file() or not MODEL_WORKFLOW.is_file():
        return ["Stage 6 software or model assurance workflow is missing"]
    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    for path in (SOFTWARE_WORKFLOW, MODEL_WORKFLOW):
        text = path.read_text(encoding="utf-8")
        uses = _action_uses(text)
        if not uses or any(PINNED_ACTION.fullmatch(item) is None for item in uses):
            errors.append(f"{path.name} contains an unpinned Action")
        for item in uses:
            action, digest = item.rsplit("@", 1)
            owner_action = action if action in pins["actions"] else action.rsplit("/", 1)[0]
            expected = pins["actions"].get(owner_action, {}).get("commit_sha")
            if digest != expected:
                errors.append(f"{path.name} drifts from the Action pin catalog")
        lowered = text.casefold()
        forbidden = (
            "self-hosted",
            "actions/cache",
            "upload-artifact",
            "download-artifact",
            "schedule:",
            "workflow_dispatch",
            "git push",
            "contents: write",
        )
        if any(token in lowered for token in forbidden):
            errors.append(f"{path.name} adds persistence, schedule or write authority")
    errors.extend(
        validate_governance_dependency_workflow(
            SOFTWARE_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )

    software = SOFTWARE_WORKFLOW.read_text(encoding="utf-8")
    required_software = (
        "--require-hashes",
        "--cumulative-final",
        "requirements/stage6.lock",
        "test_t06*.py",
        "validate_stage6.py",
        "pip_audit",
        "detect-secrets",
        "dependency-review-action",
        "codeql-action/init",
        "codeql-action/analyze",
        "security-events: write",
        "docker build --no-cache",
        "--network none",
        "--read-only",
        "machine/stages/S6/supply-chain/sbom.cdx.json",
    )
    if any(token not in software for token in required_software):
        errors.append("Stage 6 software CI command closure is incomplete")
    if pins["age"]["linux_amd64_archive_sha256"] not in software:
        errors.append("Stage 6 software CI does not pin the official age archive")

    model = MODEL_WORKFLOW.read_text(encoding="utf-8")
    required_model = (
        "requirements/stage6.lock",
        "--require-hashes",
        "machine/stages/S6/model/**",
        "machine/stages/S6/reviews/**",
        "machine/tools/validate_assurance_reviews.py",
        "tests/tasks/test_t0605.py",
        "tests/tasks/test_t0606.py",
    )
    if any(token not in model for token in required_model):
        errors.append("Stage 6 model assurance command closure is incomplete")

    dockerfile = (root / "container/Dockerfile.stage6-ci").read_text(encoding="utf-8")
    digest = pins["container"]["oci_index_digest"]
    if (
        "@" + digest not in dockerfile
        or "--require-hashes" not in dockerfile
        or "requirements/stage6.lock" not in dockerfile
        or "not a production runtime image" not in dockerfile
    ):
        errors.append("Stage 6 validation container is mutable or overstated")
    return errors


def _validate_reviews(root: Path) -> list[str]:
    result = evaluate_assurance_reviews(
        root,
        REPOSITORY_ROOT,
        verify_git=False,
        verify_anchor=True,
    )
    predecessor = root / "taskpack/PACKAGE_MANIFEST.v1.0.5.json"
    if (
        result["status"] == "PASS"
        and predecessor.is_file()
        and not predecessor.is_symlink()
        and _sha256(predecessor) == RMD05_MANIFEST_SHA256
    ):
        return []
    return ["immutable RMD-05 assurance predecessor or its provenance chain is invalid"]


def _validate_review_input_history(root: Path) -> list[str]:
    result = evaluate_assurance_reviews(
        root,
        REPOSITORY_ROOT,
        verify_git=False,
        verify_anchor=True,
    )
    if (
        result.get("status") == "BLOCKED"
        and result.get("history_integrity") == "PASS"
        and result.get("pending_final_review") is True
        and result.get("errors") == []
    ):
        return []
    return ["RMD-05 pre-final review history is not integral and honestly blocked"]


def _validate_review_input_evidence(root: Path) -> list[str]:
    errors: list[str] = []
    for task_id in STAGE6_TASKS:
        path = root / "evidence/tasks" / f"{task_id}.json"
        try:
            record = _load(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"invalid pre-final evidence for {task_id}")
            continue
        if record.get("schema_version") != "moomooau.stage6-evidence.v1":
            errors.append(f"pre-final evidence version differs for {task_id}")
        errors.extend(f"{task_id}: {item}" for item in validate_record(path, root))
    latest = _load(root / "evidence/stage6/latest.json")
    if (
        latest.get("schema_version") != "moomooau.stage6-verification.v1"
        or latest.get("stage_id") != "S6"
        or latest.get("status") != "PASS"
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or any(latest.get("prohibition_counters", {}).values())
    ):
        errors.append("pre-final Stage 6 aggregate is not the exact fail-closed v1 record")
    return errors


def _validate_public_surfaces(root: Path) -> list[str]:
    errors: list[str] = []
    publication = scan_tree(root)
    if publication["status"] != "PASS":
        errors.append("project publication scan found forbidden values")
    for path in (SOFTWARE_WORKFLOW, MODEL_WORKFLOW):
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

    errors: list[str] = validate_stage6_candidate_bundle(root, REPOSITORY_ROOT)
    if errors:
        return errors
    schema = _load(root / "machine/stages/S6/schemas/stage6-evidence-v2.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S6"}
    receipt_path = root / STAGE6_CANDIDATE_RECEIPT_PATH
    if not receipt_path.is_file():
        return ["candidate-bound Stage 6 execution receipt is missing"]
    receipt = _load(receipt_path)
    receipt_sha256 = _sha256(receipt_path)
    receipt_subject = receipt.get("subject", {})
    receipt_commands = {
        item.get("id")
        for item in receipt.get("commands", [])
        if isinstance(item, dict) and item.get("exit_code") == 0
    }
    for index, task_id in enumerate(STAGE6_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid evidence schema for {task_id}")
            continue
        if record["stage_acceptance_id"] != f"S6AC-00{index}" or record["record_status"] != "PASS":
            errors.append(f"evidence identity or status mismatch for {task_id}")
        binding = record["execution_binding"]
        if (
            record["candidate_commit"] != receipt_subject.get("candidate_commit")
            or record["candidate_tree"] != receipt_subject.get("candidate_tree")
            or binding["path"] != STAGE6_CANDIDATE_RECEIPT_PATH.as_posix()
            or binding["sha256"] != receipt_sha256
            or set(binding["command_ids"]) != STAGE6_TASK_COMMAND_IDS[task_id]
            or not set(binding["command_ids"]).issubset(receipt_commands)
        ):
            errors.append(f"candidate execution binding is stale or incomplete for {task_id}")
        if any(item["status"] != "PASS" for item in record["checks"]):
            errors.append(f"non-passing Stage 6 check for {task_id}")
        linked = record["linked_final_acceptance"]
        if [item["id"] for item in linked] != graph_tasks[task_id]["acceptance_ids"] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"} for item in linked
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        if any(item["status"] != "NOT_RUN" for item in record["production_oracles"]):
            errors.append(f"production oracle is overstated for {task_id}")
        if any(record["prohibition_counters"].values()):
            errors.append(f"prohibition counter is nonzero for {task_id}")

    latest_path = root / "evidence/stage6/latest.json"
    if not latest_path.is_file():
        errors.append("missing Stage 6 aggregate evidence")
        return errors
    latest = _load(latest_path)
    observation = latest.get("stage6_observation", {})
    expected_not_run = (
        "real_gmail_faults",
        "private_repository_faults",
        "protected_load",
        "remote_stage6_ci",
        "production_schedule_execution",
        "quarterly_recovery_drill",
    )
    if (
        latest.get("schema_version") != "moomooau.stage6-verification.v2"
        or latest.get("stage_id") != "S6"
        or latest.get("status") != "PASS"
        or latest.get("candidate_commit") != receipt_subject.get("candidate_commit")
        or latest.get("candidate_tree") != receipt_subject.get("candidate_tree")
        or latest.get("execution_receipt", {}).get("path")
        != STAGE6_CANDIDATE_RECEIPT_PATH.as_posix()
        or latest.get("execution_receipt", {}).get("sha256") != receipt_sha256
        or set(latest.get("local_gate_command_ids", [])) != receipt_commands
        or latest.get("scope") != "LOCAL_SYNTHETIC_ONLY"
        or latest.get("task_pass_count") != 8
        or latest.get("task_total") != 8
        or latest.get("final_acceptance_policy") != "NOT_FINAL"
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or any(latest.get("prohibition_counters", {}).values())
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
        or latest.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
        or latest.get("next_stage") != "S7"
        or latest.get("next_stage_status") != "NOT_STARTED"
    ):
        errors.append("Stage 6 aggregate evidence is not a fail-closed local PASS record")
    return errors


def evaluate_stage6(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
    *,
    include_delivery_records: bool = True,
    allow_stage7: bool = False,
    review_input: bool = False,
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
    if review_input:
        delivery = _load(root / "machine/status/latest.json")
        pre_final = (
            delivery.get("package_version") == "1.0.4"
            and "RMD-05_ASSURANCE_PROVENANCE_PENDING" in delivery.get("blockers", [])
            and delivery.get("dimensions", {}).get("production_readiness", {}).get("status")
            == "BLOCKED"
        )
        checks.append(
            _check(
                "baseline.pre_final_delivery_state",
                pre_final,
                "delivery authority remains the exact fail-closed v1.0.4 state",
            )
        )
    else:
        stage5 = evaluate_stage5(root, governance_root, allow_stage6=True)
        checks.append(
            _check(
                "baseline.cumulative_stage5",
                stage5["status"] == "PASS",
                f"Stage 5 failed checks {len(stage5['failed_check_ids'])}",
            )
        )
    contract_errors = _validate_contracts(root)
    checks.append(
        _check(
            "contracts.stage6_overlay",
            not contract_errors,
            f"Stage 6 contract errors {len(contract_errors)}",
        )
    )
    required = [
        root / "src/moomooau_archive/retry.py",
        root / "src/moomooau_archive/publication_saga.py",
        root / "src/moomooau_archive/capacity.py",
        root / "src/moomooau_archive/ephemeral.py",
        root / "src/moomooau_archive/load_probe.py",
        root / "src/moomooau_archive/kill_switch.py",
        root / "src/moomooau_archive/operation_gate.py",
        root / "src/moomooau_archive/model_boundary.py",
        root / "tests/stage6_support.py",
        root / "requirements/stage6.lock",
        root / "container/Dockerfile.stage6-ci",
        root / "machine/stages/S6/supply-chain/sbom.cdx.json",
        root / "machine/stages/S6/schemas/review-reply-v2.schema.json",
        root / "machine/stages/S6/schemas/review-provenance-v2.schema.json",
        root / "machine/stages/S6/schemas/execution-receipt-v1.schema.json",
        root / "machine/stages/S6/schemas/stage6-evidence-v2.schema.json",
        root / "machine/tools/validate_assurance_reviews.py",
        SOFTWARE_WORKFLOW,
        MODEL_WORKFLOW,
    ] + [root / "tests/tasks" / f"test_{task_id.casefold()}.py" for task_id in STAGE6_TASKS]
    checks.append(
        _check(
            "package.stage6_structure",
            all(path.is_file() for path in required),
            f"required Stage 6 paths {len(required)}",
        )
    )
    matrix_errors = _validate_matrices(root)
    checks.append(
        _check(
            "assurance.load_chaos_kill_matrices",
            not matrix_errors,
            f"matrix errors {len(matrix_errors)}",
        )
    )
    source_errors = _validate_source_boundaries(root)
    checks.append(
        _check(
            "security.stage6_source_boundaries",
            not source_errors,
            f"source boundary errors {len(source_errors)}",
        )
    )
    lock_errors = _validate_lock(root)
    checks.append(
        _check(
            "security.stage6_hash_lock_and_sbom",
            not lock_errors,
            f"Stage 6 supply-chain errors {len(lock_errors)}",
        )
    )
    workflow_errors = _validate_workflows(root)
    checks.append(
        _check(
            "security.dual_no_secret_stage6_ci",
            not workflow_errors,
            f"Stage 6 workflow errors {len(workflow_errors)}",
        )
    )
    review_errors = (
        _validate_review_input_history(root) if review_input else _validate_reviews(root)
    )
    checks.append(
        _check(
            (
                "assurance.materialized_review_history"
                if review_input
                else "assurance.two_independent_model_reviews"
            ),
            not review_errors,
            f"independent review errors {len(review_errors)}",
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
    stage7_paths = (
        root / "machine/stages/S7",
        root / "tests/tasks/test_t0701.py",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage7-ci.yml",
    )
    checks.append(
        _check(
            "scope.no_stage7_or_production_execution",
            allow_stage7 or not any(path.exists() for path in stage7_paths),
            (
                "Stage 7 paths allowed only for cumulative Stage 7 validation; "
                "Stage 6 production execution counters remain 0"
                if allow_stage7
                else "Stage 7 implementation paths 0; real production execution counters 0"
            ),
        )
    )
    if include_delivery_records:
        evidence_errors = (
            _validate_review_input_evidence(root) if review_input else _validate_evidence(root)
        )
        checks.append(
            _check(
                "evidence.stage6_records",
                not evidence_errors,
                f"Stage 6 evidence errors {len(evidence_errors)}",
            )
        )
    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "moomooau.stage6-verification.v1",
        "stage_id": "S6",
        "validation_mode": "REVIEW_INPUT" if review_input else "CLOSURE",
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_check_ids": failed,
        "signals": {
            "stage6_tasks": 8,
            "stage6_local_acceptances": 8,
            "l3_messages": 100_000,
            "l3_attachments": 200_000,
            "mandatory_chaos": 18,
            "kill_drills": 10,
            "independent_model_reviews": 2,
            "materialized_review_passes": 2,
            "final_review_pending": review_input,
            "real_gmail_calls": 0,
            "gmail_mutations": 0,
            "private_repository_calls": 0,
            "real_secrets_read": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "model_real_data_calls": 0,
            "model_secret_requests": 0,
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
            "allow Stage 7 implementation paths in a cumulative final-tree validation; "
            "all production execution and external-effect checks remain fail closed"
        ),
    )
    parser.add_argument(
        "--review-input",
        action="store_true",
        help=(
            "validate the materialized seventeen-attempt superseded history without claiming "
            "final closure"
        ),
    )
    args = parser.parse_args()
    result = evaluate_stage6(
        args.root,
        args.governance_root,
        allow_stage7=args.cumulative_final,
        review_input=args.review_input,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
