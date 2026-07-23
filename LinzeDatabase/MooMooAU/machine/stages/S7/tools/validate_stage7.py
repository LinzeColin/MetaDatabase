#!/usr/bin/env python3
"""Read-only cumulative Stage 7 implementation and protected-oracle validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
STAGE6_TOOLS = PROJECT_ROOT / "machine/stages/S6/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
STAGE7_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage7-ci.yml"
BETA_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-beta.yml"
PATCH_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-patch-lifecycle.yml"
PRODUCTION_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-production.yml"
BASELINE_COMMIT = "be8e196b03dcc475ed6261fbe20593b08bd26bcf"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
GOVERNANCE_PIN = "ebc6c2e4884edc959118cfc56d0e18a86c49460f"  # pragma: allowlist secret
STAGE7_TASKS = [f"T070{index}" for index in range(1, 9)]
STAGE7_ACCEPTANCES = [f"S7AC-00{index}" for index in range(1, 9)]
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")
EVIDENCE_PATH = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:json|md|py|ya?ml)")
IGNORED_PARTS = {
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}

for import_path in (STAGE6_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_production_composition import validate as validate_composition  # noqa: E402
from validate_publication import scan_tree  # noqa: E402
from validate_stage6 import evaluate_stage6  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_auth,
    validate_governance_dependency_workflow,
    validate_workflow_expression_contexts,
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
    paths.extend(
        path
        for path in (STAGE7_WORKFLOW, BETA_WORKFLOW, PATCH_WORKFLOW, PRODUCTION_WORKFLOW)
        if path.is_file()
    )
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
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S7"}
    dependencies = {
        "T0701": ["T0608"],
        "T0702": ["T0701"],
        "T0703": ["T0702"],
        "T0704": ["T0703"],
        "T0705": ["T0704"],
        "T0706": ["T0705"],
        "T0707": ["T0706"],
        "T0708": ["T0707"],
    }
    if set(graph_tasks) != set(STAGE7_TASKS) or any(
        graph_tasks[task_id].get("dependencies") != expected
        for task_id, expected in dependencies.items()
    ):
        errors.append("Stage 7 dependency chain drifts from the frozen task graph")

    local = _load(root / "machine/stages/S7/contracts/stage7_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE7_ACCEPTANCES:
        errors.append("Stage 7 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE7_TASKS:
        errors.append("Stage 7 acceptance-to-task mapping must be one-to-one")
    if (
        local.get("overall_status") != "BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES"
        or local.get("final_acceptances_passed") != 0
        or "Local implementation preflight" not in local.get("final_acceptance_policy", "")
    ):
        errors.append("Stage 7 acceptance policy overstates current completion")
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
            errors.append("Stage 7 final acceptance links drift from the frozen graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 7 acceptance contract is incomplete")

    run = _load(root / "machine/stages/S7/contracts/run_contract.json")
    prohibitions = run.get("prohibitions", {})
    if (
        run.get("stage_id") != "S7"
        or run.get("baseline_commit") != BASELINE_COMMIT
        or run.get("baseline_manifest_sha256") != BASELINE_MANIFEST_SHA256
        or not isinstance(prohibitions, dict)
        or any(value != 0 for value in prohibitions.values())
        or not run.get("protected_oracles")
        or "intermediate GitHub upload" not in run.get("non_goals", [])
        or "ordering_blocker" not in run
    ):
        errors.append("Stage 7 run contract is incomplete or grants production authority")

    status = _load(root / "machine/stages/S7/contracts/task_status.json")
    task_items = status.get("tasks", [])
    if (
        [item.get("id") for item in task_items] != STAGE7_TASKS
        or any(item.get("status") == "completed" for item in task_items)
        or status.get("stage_status") != "BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES"
        or status.get("scoped_preflight_task_oracle_file_count") != 8
        or status.get("implementation_completion_status") != "LOCAL_MECHANISMS_READY"
        or status.get("completed_task_count") != 0
        or status.get("protected_oracles_executed") != 0
        or status.get("final_acceptances_passed") != 0
        or status.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
    ):
        errors.append("Stage 7 task status is not truthfully blocked")

    semantic = _load(root / "machine/stages/S7/contracts/semantic_gate.json")
    semantic_statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("status") != "BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or "CONTROLLED_NOT_RUN" not in semantic_statuses
        or "BLOCKED_OWNER_ORDERING" not in semantic_statuses
        or "BLOCKED_IMPLEMENTATION" not in semantic_statuses
    ):
        errors.append("Stage 7 semantic gate is incomplete or overstates production evidence")
    return errors


def _validate_source_and_tests(root: Path) -> list[str]:
    errors: list[str] = []
    required_tokens: dict[str, tuple[str, ...]] = {
        "release_control.py": (
            'ALPHA = "ALPHA"',
            'BETA_RAW_ONLY = "BETA_RAW_ONLY"',
            "M3_SEVEN_DAY_WINDOW_INCOMPLETE",
            "M3_NO_PROCESSED_OR_SAFE_DEFERRED_MESSAGE",
            "BETA_RAW_RECOVERY_NOT_ONE_HUNDRED_PERCENT",
            "BLUE_GREEN_FOURTEEN_DAY_WINDOW_INCOMPLETE",
            "GA_0430_SCHEDULE_NOT_OBSERVED",
            "TARGET_FEATURE_CONFIGURATION_INCOMPLETE",
            "GA_CAPACITY_AUTHORIZATION_MISSING",
            "mutation_budget_per_run",
            "source mutations exceed the per-run budget",
            "BLUE_GREEN_NO_PARSER_COMPARISON_OBSERVED",
            "BLUE_GREEN_FULL_RECONCILIATION_NOT_OBSERVED",
            "GA_NO_PROCESSED_MESSAGE_OBSERVED",
            "GA_NO_TIMELINE_PUBLISH_OBSERVED",
            "evaluate_completed_phase",
        ),
        "http_transport.py": (
            "_NoRedirect",
            "maximum_request_bytes",
            "maximum_response_bytes",
            'parsed.scheme != "https"',
        ),
        "oauth.py": (
            "GOOGLE_TOKEN_ENDPOINT",
            "GMAIL_MODIFY_SCOPE",
            'parsed.hostname != "gmail.googleapis.com"',
            'payload.get("token_type") != "Bearer"',
        ),
        "protected_beta.py": (
            "ProtectedBetaBootstrap",
            "ProtectedBetaRuntime",
            "BETA_CONFIG_SECRET_NAME",
            "SENDER_REGISTRY_SECRET_NAME",
            "GITHUB_APP_PRIVATE_KEY_SECRET_NAME",
            "AGE_IDENTITY_SECRET_NAME",
            "OPAQUE_ID_KEY_SECRET_NAME",
            "Stage7ReleaseGate().evaluate_promotion",
            "RepositoryResolver",
            "GmailOAuthTokenClient",
            "OfficialAgeDecryptor",
            "RawOnlyCanaryRunner",
            "_CAPACITY_MAX_AGE",
            "approved_tmpfs_root",
            "_is_linux_dev_shm_tmpfs",
            "allow_synthetic_ephemeral_root: bool = False",
        ),
        "protected_beta_entrypoint.py": (
            "ExactBetaEnvironmentSecretSource",
            "ProtectedGitHubContext",
            "ProtectedBetaExecutionEvidence",
            "CONTROL_REPOSITORY_ID = 1_300_525_906",
            "CONTROL_OWNER_ID = 68_840_188",
            'CONTROL_REF = "refs/heads/main"',
            'PROTECTED_ENVIRONMENT = "moomooau-beta"',
            'RAW_ONLY_CONFIRMATION = "BETA_RAW_ONLY"',
            "runner_environment",
            '"required_actor_id": CONTROL_OWNER_ID',
            '"required_run_attempt": 1',
            "BETA_SECRET_NAMES",
            "alpha_gate_sha256",
            "Stage7ReleaseGate().evaluate_completed_phase",
            '"m3_executed": False',
            '"production_health_claimed": False',
            '"final_acceptance_claimed": False',
            "--contract-only",
            "--execute-protected",
        ),
        "stage7_ops.py": (
            'RAW = "RAW"',
            'PROCESSED = "PROCESSED"',
            'TIMELINE = "TIMELINE"',
            "HIGH_OR_CRITICAL_FINDING_OPEN",
            "PROTECTED_PATCH_CANARY_NOT_PASSED",
        ),
        "canary_runtime.py": (
            "RawOnlyCanaryRunner",
            "M3CanaryRunner",
            "CurrentProcessedPlanFactory",
            "FullMailboxDiscoverer",
            "VerificationPhase.PRE_RAW",
            "VerificationPhase.PRE_M3",
            "verify_raw_only",
            "SensitiveOperation.RAW_WRITE",
            "SensitiveOperation.PROCESSED_WRITE",
            "SensitiveOperation.M3",
            "MutationBudget.for_phase(MutationPhase.CANARY)",
            "Stage7ReleaseGate().evaluate_promotion",
            "phase is not ReleasePhase.BETA_RAW_ONLY",
            "BETA_RAW_ONLY_COMPLETED_NOT_FINAL",
            "M3_CANARY_RUN_COMPLETED_NOT_FINAL",
        ),
        "remote_recovery_gate.py": (
            'RAW_ONLY = "RAW_ONLY"',
            'RAW_AND_PROCESSED = "RAW_AND_PROCESSED"',
            "RepositoryCiphertextReader",
            "raw_ciphertext_sha256",
            "_validate_processed_manifest",
        ),
        "timeline_event.py": (
            "def from_bytes",
            "allow_nan=False",
            "Timeline Event payload is not canonical",
            '"Australia/Sydney"',
        ),
        "timeline_snapshot.py": (
            "TimelineSnapshotPlanner",
            "TimelineSnapshotCommitSaga",
            "TimelineSnapshotRecoveryGate",
            "moomooau.timeline-snapshot-root.v1",
            "CurrentProcessedPointer.from_bytes",
            "TimelineEvent.from_bytes",
            "recover_root",
        ),
        "timeline_publish.py": (
            "recover_committed_snapshot_root",
            "Timeline Asset exists without a recoverable private snapshot head",
            "committed Timeline snapshot head is not healthy",
        ),
        "blue_green_runtime.py": (
            "BlueGreenTimelineRunner",
            "RemoteCurrentProcessedPointerSource",
            "Stage7ReleaseGate().evaluate_promotion",
            "candidate shadow unexpectedly contains a current pointer",
            "current pointer changed during candidate shadow commit",
            "recover_committed_snapshot_root",
            "SensitiveOperation.TIMELINE_WRITE",
            "self._timeline_publisher.publish",
        ),
        "gmail_sync_checkpoint.py": (
            "EncryptedGmailSyncCheckpoint",
            "GitHubGmailSyncStateStore",
            "moomooau.gmail-run-checkpoint.v1",
            "moomooau.gmail-run-checkpoint.v2",
            "last_successful_run_date_sydney",
            "GMAIL_SYNC_STATE_PATH",
            "Gmail sync checkpoint remote recovery differs",
        ),
        "ga_runtime.py": (
            "GAFullPipelineRunner",
            "Stage7ReleaseGate().evaluate_promotion",
            "MutationPhase.STABLE",
            "reconcile_for_run",
            "VerificationPhase.PRE_RAW",
            "VerificationPhase.PRE_M3",
            "verify_raw_only",
            "SensitiveOperation.M3",
            "Full Reconciliation candidate set differs from full truth",
            "self._timeline_publisher.publish",
            "self._sync_checkpoint.commit",
        ),
        "production_adapters.py": (
            "OfficialAgeCrypto",
            "RemoteFirstImportTimestampSource",
            "current Processed manifest recovery failed",
            "first-import timestamp is after the observation",
        ),
        "production.py": (
            "ProductionBootstrap",
            "ProductionRuntime",
            "ExactEnvironmentSecretSource",
            "PRODUCTION_SECRET_NAMES",
            "Stage7ReleaseGate().evaluate_promotion",
            "EncryptedGmailSyncCheckpoint",
            "GAFullPipelineRunner",
            "RemoteFirstImportTimestampSource",
            "--contract-only",
            "--execute-protected",
            "production scheduling watermark did not commit",
            '"production_health_claimed": False',
        ),
        "github_guard.py": (
            "GMAIL_SYNC_STATE_PATH",
            "CONTENT_GMAIL_SYNC_STATE_MESSAGE",
            "Gmail sync state write is not strict CAS",
        ),
        "model_boundary.py": (
            "PassiveCodexAutoContract",
            "PublicHealthObservation",
            "LinzeDatabase/MooMooAU/evidence/ops/latest.json",
            "maximum_evidence_age: timedelta = timedelta(hours=48)",
            "PUBLIC_HEALTH_STALE_SINGLE_ISSUE_BUDGET",
            '"workflow_dispatches": 0',
            '"conversation_continuations": 0',
            '"data_plane_dependency": False',
        ),
        "recovery_drill.py": (
            "RecoveryDrillRunner",
            "OWNER_RECOVERY_KEY_FILE",
            "maximum_samples_per_role: int = 1",
            "private_repository_reads_allowed: bool = False",
            "OfficialRecoveryStreamDecryptor",
            '"MooMooAU-Recovery-Key.agekey"',
            'Path("/dev/shm").resolve(strict=True)',
            "plaintext_sink = _DigestSink()",
            "RecoveryDrillSafetyAudit",
            "KillId.KILL_005",
            '"private_repository_writes": 0',
            '"final_stage7_claimed": False',
        ),
        "patch_lifecycle.py": (
            "PatchLifecycleRunContract",
            "PatchLifecycleRunner",
            "PatchChangeSet",
            "OperationsReadinessSnapshot",
            "FREEZE_KEEP_LAST_VERIFIED",
            "READY_FOR_OWNER_APPROVED_PROMOTION",
            "T0707_PROTECTED_PREDECESSOR_NOT_READY",
            "PATCH_PATH_OUTSIDE_MOOMOOAU_SCOPE",
            '"patch_applied": False',
            '"rollback_executions": 0',
            '"stage7_completion_claimed": False',
        ),
    }
    source_root = root / "src/moomooau_archive"
    for name, tokens in required_tokens.items():
        path = source_root / name
        if not path.is_file() or any(
            token not in path.read_text(encoding="utf-8") for token in tokens
        ):
            errors.append(f"Stage 7 source invariant is missing from {name}")
    protected_beta = source_root / "protected_beta.py"
    if protected_beta.is_file() and "os.environ" in protected_beta.read_text(encoding="utf-8"):
        errors.append("protected Beta bootstrap performs implicit environment discovery")
    tests = [root / "tests/tasks" / f"test_{task.casefold()}.py" for task in STAGE7_TASKS]
    if not all(path.is_file() for path in tests):
        errors.append("Stage 7 task tests are incomplete")
    for index, path in enumerate(tests, start=1):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if f"test_t070{index}" not in text:
            errors.append(f"T070{index} test file has no executable task oracle")
    remediation_paths = (
        root / "tests/remediation/test_rmd04.py",
        root / "machine/contracts/production_composition.json",
        root / "schemas/production-composition-v1.schema.json",
        root / "schemas/production-config-v1.schema.json",
        root / "machine/tools/validate_production_composition.py",
    )
    if not all(path.is_file() and not path.is_symlink() for path in remediation_paths):
        errors.append("RMD-04 production composition evidence closure is incomplete")
    runbook = root / "operations/STAGE7_RUNBOOK.md"
    runbook_text = runbook.read_text(encoding="utf-8") if runbook.is_file() else ""
    for token in (
        "BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES",
        "至少 7 天",
        "至少 14 天",
        "04:30 Australia/Sydney",
        "Mutation Budget",
        "Recovery Drill",
        "Patch Lifecycle",
        "High/Critical",
    ):
        if token not in runbook_text:
            errors.append("Stage 7 operations runbook is incomplete")
            break
    return errors


def _action_uses(workflow: str) -> list[str]:
    return re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)


def _validate_workflow(root: Path) -> list[str]:
    if not STAGE7_WORKFLOW.is_file() or not BETA_WORKFLOW.is_file() or not PATCH_WORKFLOW.is_file():
        return ["Stage 7 preflight, protected Beta or Patch Lifecycle workflow is missing"]
    errors: list[str] = []
    text = STAGE7_WORKFLOW.read_text(encoding="utf-8")
    uses = _action_uses(text)
    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    if not uses or any(PINNED_ACTION.fullmatch(item) is None for item in uses):
        errors.append("Stage 7 preflight workflow contains an unpinned Action")
    for item in uses:
        action, digest = item.rsplit("@", 1)
        expected = pins["actions"].get(action, {}).get("commit_sha")
        if digest != expected:
            errors.append("Stage 7 preflight Action drifts from the pin catalog")
    lowered = text.casefold()
    forbidden = (
        "schedule:",
        "workflow_dispatch",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_production_enabled",
    )
    if any(token in lowered for token in forbidden):
        errors.append("Stage 7 preflight workflow adds Secret, persistence or production authority")
    required = (
        "requirements/stage6.lock",
        "--require-hashes",
        "test_t07*.py",
        "validate_stage7.py",
        "ga_runtime.py",
        "production.py",
        "production_adapters.py",
        "gmail_sync_checkpoint.py",
        "model_boundary.py",
        "recovery_drill.py",
        "patch_lifecycle.py",
        "test_rmd04.py",
        "validate_production_composition.py",
        "production_composition.json",
        "production-composition-v1.schema.json",
        "production-config-v1.schema.json",
        "moomooau-production.yml",
        "moomooau-patch-lifecycle.yml",
        "--preflight",
        "persist-credentials: false",
        "LinzeColin/Governance",
        GOVERNANCE_PIN,
        pins["age"]["linux_amd64_archive_sha256"],
    )
    if any(token not in text for token in required):
        errors.append("Stage 7 preflight command closure is incomplete")
    errors.extend(
        validate_governance_dependency_workflow(
            STAGE7_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )
    beta = BETA_WORKFLOW.read_text(encoding="utf-8")
    beta_uses = _action_uses(beta)
    expected_beta_secret_names = {
        "MOOMOOAU_BETA_CONFIG",
        "MOOMOOAU_SENDER_REGISTRY",
        "MOOMOOAU_GITHUB_APP_PRIVATE_KEY",
        "MOOMOOAU_AGE_IDENTITY",
        "MOOMOOAU_OPAQUE_ID_KEY",
        "MOOMOOAU_GMAIL_OAUTH",
    }
    actual_beta_secret_names = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", beta))
    try:
        beta_value = yaml.load(beta, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        beta_value = None
    beta_required = (
        "workflow_dispatch:",
        "expected_head_sha:",
        "confirm_raw_only:",
        "permissions:\n  contents: read",
        "group: moomooau-beta-raw-only-single-writer",
        "cancel-in-progress: false",
        "Fail closed on invalid protected dispatch context",
        'test "$GITHUB_REPOSITORY_ID" = "1300525906"',
        'test "$GITHUB_REPOSITORY_OWNER_ID" = "68840188"',
        'test "$GITHUB_ACTOR_ID" = "68840188"',
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        'test "$RUNNER_ENVIRONMENT" = "github-hosted"',
        'test "$GITHUB_REF" = "refs/heads/main"',
        'test "$EXPECTED_HEAD_SHA" = "$GITHUB_SHA"',
        'test "$RAW_ONLY_CONFIRMATION" = "BETA_RAW_ONLY"',
        "needs: alpha-gate",
        "environment: moomooau-beta",
        "runs-on: ubuntu-24.04",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        "test_t0701.py tests/tasks/test_t0702.py",
        "validate_package.py",
        "validate_delivery_status.py",
        "validate_publication.py",
        "protected_beta_entrypoint",
        "--contract-only",
        "--execute-protected",
        "alpha_gate_sha256",
        "moomooau-protected-beta-*",
        "persist-credentials: false",
        pins["age"]["linux_amd64_archive_sha256"],
    )
    beta_forbidden = (
        "schedule:",
        "pull_request:",
        "\n  push:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "moomooau_production_enabled",
        "python -m moomooau_archive.production",
        "moomooau_classification_registry",
        "moomooau_parser_registry",
        "moomooau_governance_deploy_key",
    )
    beta_workflow_triggers = (
        set(beta_value.get("on", {}))
        if isinstance(beta_value, dict) and isinstance(beta_value.get("on"), dict)
        else set()
    )
    if (
        beta_workflow_triggers != {"workflow_dispatch"}
        or any(token not in beta for token in beta_required)
        or any(token in beta.casefold() for token in beta_forbidden)
        or actual_beta_secret_names != expected_beta_secret_names
        or beta.count("${{ secrets.") != len(expected_beta_secret_names)
        or beta.count('test "$RUNNER_ENVIRONMENT" = "github-hosted"') != 2
        or beta.count(pins["age"]["linux_amd64_archive_sha256"]) != 2
        or len(beta_uses) != 4
        or any(PINNED_ACTION.fullmatch(item) is None for item in beta_uses)
        or any(
            item.rsplit("@", 1)[1]
            != pins["actions"].get(item.rsplit("@", 1)[0], {}).get("commit_sha")
            for item in beta_uses
        )
    ):
        errors.append("protected Beta workflow drifts from the Raw-only execution contract")
    errors.extend(
        validate_workflow_expression_contexts(
            beta_value,
            label=".github/workflows/moomooau-beta.yml",
        )
    )
    errors.extend(
        validate_governance_dependency_auth(
            beta_value,
            label=".github/workflows/moomooau-beta.yml",
            required=False,
        )
    )
    patch_text = PATCH_WORKFLOW.read_text(encoding="utf-8")
    patch_uses = _action_uses(patch_text)
    if not patch_uses or any(PINNED_ACTION.fullmatch(item) is None for item in patch_uses):
        errors.append("Patch Lifecycle workflow contains an unpinned Action")
    for item in patch_uses:
        action, digest = item.rsplit("@", 1)
        expected = pins["actions"].get(action, {}).get("commit_sha")
        if digest != expected:
            errors.append("Patch Lifecycle Action drifts from the pin catalog")
    patch_lowered = patch_text.casefold()
    patch_forbidden = (
        "schedule:",
        "contents: write",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "self-hosted",
        "git push",
        "environment:",
        "moomooau_production_enabled",
    )
    if any(token in patch_lowered for token in patch_forbidden):
        errors.append("Patch Lifecycle policy workflow adds Secret or mutation authority")
    patch_required = (
        "workflow_dispatch:",
        "permissions:\n  contents: read",
        "patch-policy-preflight",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-deps --disable-pip",
        "python -m pytest -q tests/tasks",
        "validate_stage7.py",
        "--preflight",
        "stage7-patch-sbom.cdx.json",
        "patch_lifecycle.py",
        "MOOMOOAU_PATCH_APPLIED:-false",
        "MOOMOOAU_ROLLBACK_EXECUTED:-false",
        "persist-credentials: false",
        "LinzeColin/Governance",
        GOVERNANCE_PIN,
        pins["age"]["linux_amd64_archive_sha256"],
    )
    if any(token not in patch_text for token in patch_required):
        errors.append("Patch Lifecycle policy workflow command closure is incomplete")
    errors.extend(
        validate_governance_dependency_workflow(
            PATCH_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )
    production = (
        PRODUCTION_WORKFLOW.read_text(encoding="utf-8") if PRODUCTION_WORKFLOW.is_file() else ""
    )
    production_uses = _action_uses(production)
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
    actual_secret_names = set(re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", production))
    production_required = (
        'cron: "30 4 * * *"',
        'timezone: "Australia/Sydney"',
        "workflow_dispatch:",
        "permissions:\n  contents: read",
        "MOOMOOAU_PRODUCTION_ENABLED == 'true'",
        "environment: moomooau-production",
        "concurrency:",
        "cancel-in-progress: false",
        "runs-on: ubuntu-24.04",
        "requirements/stage6.lock",
        "--require-hashes",
        "--no-build-isolation --no-deps .",
        pins["age"]["linux_amd64_archive_sha256"],
        "python -m moomooau_archive.production",
        "--execute-protected",
        '--event-name "$EVENT_NAME"',
        "persist-credentials: false",
    )
    production_forbidden = (
        "self-hosted",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "git push",
        "contents: write",
        "MOOMOOAU_STAGE5_PROTECTED_ORACLE",
    )
    if (
        not PRODUCTION_WORKFLOW.is_file()
        or any(token not in production for token in production_required)
        or any(token.casefold() in production.casefold() for token in production_forbidden)
        or actual_secret_names != expected_secret_names
        or production.count("${{ secrets.") != len(expected_secret_names)
        or len(production_uses) != 2
        or any(PINNED_ACTION.fullmatch(item) is None for item in production_uses)
        or any(
            item.rsplit("@", 1)[1]
            != pins["actions"].get(item.rsplit("@", 1)[0], {}).get("commit_sha")
            for item in production_uses
        )
    ):
        errors.append("protected production workflow drifts from the RMD-04 composition")
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S7/schemas/stage7-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S7"}
    required_blockers = {
        "T0702": {
            "PROTECTED_BETA_ENVIRONMENT_NOT_PROVISIONED",
            "PROTECTED_BETA_SECRETS_NOT_PROVISIONED",
            "PROTECTED_SENDER_REGISTRY_NOT_PROVISIONED",
            "BETA_MESSAGE_BUDGET_NOT_PROVISIONED",
            "PRIVATE_DATA_REPOSITORY_NOT_PROVISIONED",
            "GITHUB_APP_INSTALLATION_NOT_VERIFIED",
            "INTERMEDIATE_UPLOAD_FORBIDDEN_BUT_GITHUB_HOSTED_OBSERVATION_REQUIRED",
        },
        "T0704": {
            "PROTECTED_CLASSIFICATION_AND_PARSER_REGISTRIES_NOT_PROVISIONED",
        },
        "T0706": {
            "GA_NOT_COMPLETE",
            "CODEX_AUTOMATION_NOT_CREATED",
        },
        "T0707": {
            "CODEX_AUTOMATION_TASK_PREDECESSOR_NOT_COMPLETE",
            "PROTECTED_RECOVERY_SAMPLE_ADAPTERS_NOT_PROVISIONED",
            "OWNER_RECOVERY_KEY_FILE_NOT_PROVIDED",
            "REAL_RECOVERY_KEY_DRILL_NOT_RUN",
        },
        "T0708": {
            "RECOVERY_DRILL_TASK_PREDECESSOR_NOT_COMPLETE",
            "PROTECTED_PATCH_CANDIDATE_NOT_PROVISIONED",
            "PROTECTED_PATCH_CANARY_ADAPTER_NOT_PROVISIONED",
            "PROTECTED_OPERATIONS_NOT_RUN",
        },
    }
    resolved_local_blockers = {
        "T0702": {"PROTECTED_RUNTIME_BOOTSTRAP_NOT_IMPLEMENTED"},
        "T0703": {"M3_PROCESSED_CANARY_RUNTIME_NOT_IMPLEMENTED"},
        "T0704": {"BLUE_GREEN_AND_TIMELINE_AGGREGATION_RUNTIME_NOT_IMPLEMENTED"},
        "T0705": {"GA_FULL_PIPELINE_ENTRY_NOT_IMPLEMENTED"},
        "T0707": {"PROTECTED_RECOVERY_DRILL_ENTRY_NOT_IMPLEMENTED"},
        "T0708": {"PROTECTED_PATCH_LIFECYCLE_WORKFLOW_NOT_IMPLEMENTED"},
    }
    for index, task_id in enumerate(STAGE7_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid Stage 7 evidence schema for {task_id}")
            continue
        for check in record["checks"]:
            evidence_ref = check["evidence_ref"]
            matches = EVIDENCE_PATH.findall(evidence_ref)
            if "../" in evidence_ref or not matches:
                errors.append(f"invalid evidence reference for {task_id}")
                continue
            for relative in matches:
                unresolved = root / relative
                resolved = unresolved.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    errors.append(f"evidence reference escapes root for {task_id}")
                    continue
                if unresolved.is_symlink() or not resolved.is_file():
                    errors.append(f"missing or unsafe evidence reference for {task_id}")
        expected_status = "READY" if task_id == "T0701" else "BLOCKED"
        if (
            record["stage_acceptance_id"] != f"S7AC-00{index}"
            or record["record_status"] != expected_status
            or any(item["status"] != "PASS" for item in record["checks"])
        ):
            errors.append(f"Stage 7 implementation status mismatch for {task_id}")
        if [item["id"] for item in record["linked_final_acceptance"]] != graph_tasks[task_id][
            "acceptance_ids"
        ] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"}
            for item in record["linked_final_acceptance"]
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        if any(item["status"] != "NOT_RUN" for item in record["production_oracles"]):
            errors.append(f"production oracle is overstated for {task_id}")
        if (
            not record["blockers"]
            or not required_blockers.get(task_id, set()).issubset(record["blockers"])
            or resolved_local_blockers.get(task_id, set()).intersection(record["blockers"])
            or any(record["prohibition_counters"].values())
        ):
            errors.append(f"Stage 7 blocker or prohibition counters are invalid for {task_id}")

    latest = _load(root / "evidence/stage7/latest.json")
    observation = latest.get("observation", {})
    aggregate_required_blockers = set().union(*required_blockers.values()) | {
        "INTERMEDIATE_UPLOAD_FORBIDDEN_BUT_GITHUB_HOSTED_OBSERVATION_REQUIRED"
    }
    aggregate_resolved_blockers = set().union(*resolved_local_blockers.values())
    not_run = (
        "alpha_remote_preflight",
        "beta_real_raw_only",
        "m3_seven_day_canary",
        "blue_green_fourteen_day",
        "ga_0430_schedule",
        "codex_automation_created",
        "real_recovery_key_drill",
        "protected_patch_lifecycle",
        "maximum_observed_live_timeline_assets",
    )
    if (
        latest.get("stage_id") != "S7"
        or latest.get("status") != "BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES"
        or latest.get("scoped_preflight")
        != "PASS_CONTROL_BETA_M3_BLUE_GREEN_TIMELINE_GA_CODEX_AUTO_RECOVERY_AND_PATCH_POLICY"
        or latest.get("implementation_completion_status") != "LOCAL_MECHANISMS_READY"
        or latest.get("scope") != "LOCAL_SYNTHETIC_PREFLIGHT"
        or latest.get("mechanism_task_oracle_files_passed") != 8
        or latest.get("task_total") != 8
        or latest.get("completed_task_count") != 0
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or latest.get("production_workflow_runs") != 0
        or observation.get("alpha_local_synthetic") != "PASS"
        or observation.get("beta_local_bootstrap_mechanism") != "PASS"
        or observation.get("m3_local_synthetic_mechanism") != "PASS"
        or observation.get("blue_green_timeline_local_mechanism") != "PASS"
        or observation.get("ga_full_pipeline_local_mechanism") != "PASS"
        or observation.get("codex_auto_local_policy") != "PASS"
        or observation.get("recovery_drill_local_mechanism") != "PASS"
        or observation.get("patch_lifecycle_local_policy") != "PASS"
        or any(observation.get(key) != "NOT_RUN" for key in not_run)
        or any(
            observation.get(key) != 0
            for key in (
                "real_gmail_calls",
                "gmail_mutations",
                "private_repository_calls",
                "real_secrets_read",
                "external_writes",
                "remote_publication",
            )
        )
        or not aggregate_required_blockers.issubset(latest.get("blocking_conditions", []))
        or aggregate_resolved_blockers.intersection(latest.get("blocking_conditions", []))
        or latest.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
    ):
        errors.append("Stage 7 aggregate evidence is not truthfully blocked")
    return errors


def evaluate_stage7(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
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
    stage6 = evaluate_stage6(root, governance_root, allow_stage7=True)
    checks.append(
        _check(
            "baseline.cumulative_stage6",
            stage6["status"] == "PASS",
            f"Stage 6 failed checks {len(stage6['failed_check_ids'])}",
        )
    )
    contract_errors = _validate_contracts(root)
    checks.append(
        _check(
            "contracts.stage7_fail_closed_overlay",
            not contract_errors,
            f"Stage 7 contract errors {len(contract_errors)}",
        )
    )
    source_errors = _validate_source_and_tests(root)
    checks.append(
        _check(
            "implementation.release_transport_ops",
            not source_errors,
            f"Stage 7 source or test errors {len(source_errors)}",
        )
    )
    workflow_errors = _validate_workflow(root)
    checks.append(
        _check(
            "security.no_secret_stage7_preflight",
            not workflow_errors,
            f"Stage 7 workflow errors {len(workflow_errors)}",
        )
    )
    composition = validate_composition(root)
    checks.append(
        _check(
            "implementation.production_composition",
            composition["status"] == "PASS",
            f"RMD-04 composition failures {len(composition['failures'])}",
        )
    )
    evidence_errors = _validate_evidence(root)
    checks.append(
        _check(
            "evidence.truthful_protected_not_run",
            not evidence_errors,
            f"Stage 7 evidence errors {len(evidence_errors)}",
        )
    )
    publication = scan_tree(root)
    checks.append(
        _check(
            "security.publication",
            publication["status"] == "PASS",
            f"publication findings {publication['total_matches']}",
        )
    )
    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    scoped_preflight_status = "PASS" if not failed else "BLOCKED"
    implementation_status = "LOCAL_MECHANISMS_READY" if not failed else "BLOCKED"
    latest = _load(root / "evidence/stage7/latest.json")
    protected_blockers = tuple(latest.get("blocking_conditions", []))
    overall_status = "BLOCKED_IMPLEMENTATION_AND_PROTECTED_ORACLES"
    return {
        "schema_version": "moomooau.stage7-verification.v1",
        "stage_id": "S7",
        "status": overall_status,
        "scoped_preflight_status": scoped_preflight_status,
        "implementation_status": implementation_status,
        "checks": checks,
        "failed_check_ids": failed,
        "blocking_conditions": list(protected_blockers),
        "signals": {
            "stage7_task_oracle_files": 8,
            "stage7_local_implementation_complete": not failed,
            "stage7_protected_integration_complete": False,
            "stage7_completed_tasks": 0,
            "protected_oracles_executed": 0,
            "production_workflow_runs": 0,
            "real_gmail_calls": 0,
            "gmail_mutations": 0,
            "private_repository_calls": 0,
            "real_secrets_read": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "final_acceptances_passed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "return success only for the scoped control, protected Beta bootstrap/Raw-only, "
            "local synthetic M3, Blue-Green/Timeline, GA full-pipeline and passive Codex Auto "
            "policy, Recovery Drill and Patch Lifecycle mechanism preflight"
        ),
    )
    args = parser.parse_args()
    result = evaluate_stage7(args.root, args.governance_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.preflight:
        return 0 if result["scoped_preflight_status"] == "PASS" else 1
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
