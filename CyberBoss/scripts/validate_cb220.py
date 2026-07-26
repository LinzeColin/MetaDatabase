#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P2.3 / CB-220."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-220"
BASE_COMMIT = "e5995d0967e789c99ce06b5b76fa794e5d455f68"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
EXPECTED_ACCEPTANCE = [
    "AC-012",
    "AC-013",
    "AC-014",
    "AC-015",
    "AC-045",
    "AC-064",
]

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/migrations/003_cb220_scheduler_control.sql",
    "CyberBoss/app/package.json",
    "CyberBoss/app/scripts/job-scheduler-acceptance.js",
    "CyberBoss/app/src/adapters/runtime/codex/events.js",
    "CyberBoss/app/src/adapters/runtime/codex/index.js",
    "CyberBoss/app/src/adapters/runtime/claudecode/events.js",
    "CyberBoss/app/src/adapters/runtime/claudecode/index.js",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/services/db/database-adapter.js",
    "CyberBoss/app/src/services/inbox/durable-inbox.js",
    "CyberBoss/app/src/services/jobs/job-scheduler.js",
    "CyberBoss/app/src/services/jobs/resource-readiness-gate.js",
    "CyberBoss/app/test/job-scheduler.test.js",
    "CyberBoss/app/test/resource-readiness-gate.test.js",
    "CyberBoss/app/test/runtime-spool.test.js",
    "CyberBoss/app/test/turn-gate-store.test.js",
    "CyberBoss/app/test/workspace-scope.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P2_3_CB_220.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-job-scheduler.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-job-scheduler-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-job-scheduler.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb220.py",
    "CyberBoss/tests/job-scheduler.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {
    "VALIDATION_REPORT.md",
    "artifact-checksums.txt",
    "artifact-manifest.json",
    "cgroup-pressure.redacted.json",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "publication-check.json",
    "recovery-matrix.redacted.json",
    "resource-gate-report.json",
    "rollback-plan.json",
    "runtime-error-classification.json",
    "scheduler-timeline.redacted.json",
    "security-report.json",
    "source-modification-record.json",
    "stop-matrix.redacted.json",
    "target-preflight.redacted.json",
    "validation.txt",
    "workspace-matrix.redacted.json",
}
FROZEN_PATHS = [
    "CyberBoss/vendor",
    "CyberBoss/docs/evidence/CB-000",
    "CyberBoss/docs/evidence/CB-010",
    "CyberBoss/docs/evidence/CB-020",
    "CyberBoss/docs/evidence/CB-030",
    "CyberBoss/docs/evidence/CB-040",
    "CyberBoss/docs/evidence/CB-100",
    "CyberBoss/docs/evidence/CB-110",
    "CyberBoss/docs/evidence/CB-120",
    "CyberBoss/docs/evidence/CB-130",
    "CyberBoss/docs/evidence/CB-140",
    "CyberBoss/docs/evidence/CB-200",
    "CyberBoss/docs/evidence/CB-210",
    "CyberBoss/docs/evidence/PG-0",
    "CyberBoss/docs/evidence/PG-1",
    "CyberBoss/docs/product_design/v0.0.0.4/00_README_FIRST.md",
    "CyberBoss/docs/product_design/v0.0.0.4/01_PRFAQ_STRATEGY_OKR.md",
    "CyberBoss/docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
    "CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
    "CyberBoss/docs/product_design/v0.0.0.4/05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md",
    "CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md",
    "CyberBoss/docs/product_design/v0.0.0.4/07_RESEARCH_COMPETITOR_UPSTREAM_FINDINGS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/08_UPSTREAM_CODE_CHANGE_MAP.md",
    "CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/10_TRACEABILITY_RELEASE_CHECKLIST.md",
    "CyberBoss/docs/product_design/v0.0.0.4/11_AGENT_EXECUTION_PROMPTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/12_CURRENT_ROADMAP.md",
    "CyberBoss/docs/product_design/v0.0.0.4/13_STAGE2B_STAGE3_UPGRADES.md",
    "CyberBoss/docs/product_design/v0.0.0.4/14_PURSUING_GOAL.txt",
    "CyberBoss/machine/source-lock.json",
    "CyberBoss/LICENSE",
    "CyberBoss/THIRD_PARTY_NOTICES.md",
    "CyberBoss/UPSTREAM_PROVENANCE.md",
]
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bwxid_[A-Za-z0-9_-]+\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str, check: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.strip()[:180]}"
        )
    return result.returncode, result.stdout.rstrip()


def changed_paths() -> set[str]:
    paths = set(
        filter(None, git("diff", "--name-only", BASE_COMMIT, "HEAD")[1].splitlines())
    )
    status = git("status", "--porcelain=v1", "--untracked-files=all")[1]
    for raw in status.splitlines():
        value = raw[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if value:
            paths.add(value)
    return paths


def verify_manifest(path: Path, errors: list[str]) -> None:
    root = path.parent
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"manifest_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if relative in entries or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"manifest_path:{path.relative_to(REPO)}:{relative}")
            continue
        entries[relative] = digest
    actual = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file()
        and candidate != path
        and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def run_command(
    name: str,
    args: list[str],
    errors: list[str],
    *,
    cwd: Path = REPO,
    required: tuple[str, ...] = (),
    timeout: int = 600,
) -> None:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"command_exception:{name}:{type(error).__name__}")
        return
    if result.returncode != 0:
        tail = result.stdout.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command:{name}:{result.returncode}:{tail[0][:180]}")
    for marker in required:
        if marker not in result.stdout:
            errors.append(f"command_marker:{name}:{marker}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row["id"]: row["status"] for row in state["tasks"]}
    passed = {
        "CB-000",
        "CB-010",
        "CB-020",
        "CB-030",
        "CB-040",
        "CB-100",
        "CB-110",
        "CB-120",
        "CB-130",
        "CB-140",
        "CB-200",
        "CB-210",
    }
    if final:
        passed.add("CB-220")
    for task_id, status in statuses.items():
        expected = "passed" if task_id in passed else "not_started"
        if status != expected:
            errors.append(f"task_state:{task_id}:{status}:{expected}")
    gates = state.get("pass_gates") or {}
    if gates.get("PG-0") != "passed" or gates.get("PG-1") != "passed":
        errors.append("prior_gates")
    for gate in ("PG-2", "PG-3", "PG-4", "PG-5"):
        if gates.get(gate) != "not_started":
            errors.append(f"later_gate:{gate}")
    expected_current = (
        {
            "run_id": "P2.3",
            "gate_id": None,
            "task_id": "CB-220",
            "scope": "scheduler_resource_workspace_runtime_control",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P2.2",
            "gate_id": None,
            "task_id": "CB-210",
            "scope": "durable_inbox_before_weixin_cursor",
            "status": "passed",
        }
    )
    if state.get("current_run") != expected_current:
        errors.append("current_run")


def validate_final_evidence(errors: list[str]) -> None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_missing")
        return
    inventory = {path.name for path in EVIDENCE.iterdir() if path.is_file()}
    if inventory != FINAL_EVIDENCE:
        errors.append(
            "evidence_inventory:"
            f"missing={sorted(FINAL_EVIDENCE - inventory)}:"
            f"extra={sorted(inventory - FINAL_EVIDENCE)}"
        )
        return

    implementation = load_json(EVIDENCE / "implementation-commit.json")
    implementation_commit = implementation.get("implementation_commit")
    if (
        implementation.get("task_id") != "CB-220"
        or implementation.get("phase") != "P2.3"
        or implementation.get("base_commit") != BASE_COMMIT
        or not re.fullmatch(r"[0-9a-f]{40}", str(implementation_commit))
        or git("rev-parse", f"{implementation_commit}^")[1] != BASE_COMMIT
        or git(
            "diff",
            "--quiet",
            implementation_commit,
            "HEAD",
            "--",
            *sorted(IMPLEMENTATION_PATHS),
            check=False,
        )[0]
        != 0
    ):
        errors.append("evidence_implementation")

    scheduler = load_json(EVIDENCE / "scheduler-timeline.redacted.json")
    if (
        scheduler.get("task_id") != "CB-220"
        or scheduler.get("phase") != "P2.3"
        or scheduler.get("queued_runtime_jobs") != 5
        or scheduler.get("max_active_runtime_leases") != 1
        or scheduler.get("fifo_dispatch_order") is not True
        or scheduler.get("command_runtime_planes_separated") is not True
        or scheduler.get("result") != "passed"
    ):
        errors.append("evidence_scheduler")

    workspace = load_json(EVIDENCE / "workspace-matrix.redacted.json")
    if (
        workspace.get("allowlisted_alias_dispatched") is not True
        or workspace.get("absolute_path_dispatched") is not False
        or workspace.get("unknown_alias_dispatched") is not False
        or workspace.get("symlink_escape_dispatched") is not False
        or workspace.get("filesystem_changed_on_rejection") is not False
        or workspace.get("result") != "passed"
    ):
        errors.append("evidence_workspace")

    resource = load_json(EVIDENCE / "resource-gate-report.json")
    expected_reasons = {
        "poll_stale": "restart_channel_adapter",
        "runtime_unhealthy": "restart_runtime_process_family",
        "disk_pressure": "pause_mutations_and_cleanup_reconstructable_data",
        "load_pressure": "hold_new_runtime_jobs",
        "queue_stuck": "inspect_active_lease_and_runtime",
    }
    if (
        resource.get("reason_action_matrix") != expected_reasons
        or resource.get("protect_blocks_mutation") is not True
        or resource.get("recover_allows_dispatch") is not True
        or resource.get("no_real_time_soak") is not True
        or resource.get("result") != "passed"
    ):
        errors.append("evidence_resource")

    pressure = load_json(EVIDENCE / "cgroup-pressure.redacted.json")
    if (
        pressure.get("guard_ladder") != [
            "recover",
            "warn",
            "protect",
            "protect",
            "protect",
            "recover",
        ]
        or pressure.get("oom_kill_delta") != 0
        or pressure.get("bounded_fixture") is not True
        or pressure.get("real_time_soak") is not False
        or pressure.get("result") != "passed"
    ):
        errors.append("evidence_pressure")

    stop = load_json(EVIDENCE / "stop-matrix.redacted.json")
    if (
        stop.get("cancel_call_count") != 3
        or stop.get("terminal_by_runtime_status")
        != {
            "completed": "succeeded",
            "failed": "failed_terminal",
            "interrupted": "cancelled",
        }
        or stop.get("ack_claimed_terminal") is not False
        or stop.get("false_success_count") != 0
        or stop.get("result") != "passed"
    ):
        errors.append("evidence_stop")

    recovery = load_json(EVIDENCE / "recovery-matrix.redacted.json")
    if (
        recovery.get("pre_dispatch_requeued") is not True
        or recovery.get("ambiguous_mutation_replayed") is not False
        or recovery.get("stale_owner_heartbeat_succeeded") is not False
        or recovery.get("late_event_released_new_lease") is not False
        or recovery.get("result") != "passed"
    ):
        errors.append("evidence_recovery")

    classifications = load_json(EVIDENCE / "runtime-error-classification.json")
    if (
        set(classifications.get("covered_classes") or [])
        != {
            "auth_required",
            "cancelled",
            "runtime_overloaded",
            "runtime_terminal",
            "transport_unavailable",
        }
        or classifications.get("bounded_mutation_auto_replay") is not False
        or classifications.get("result") != "passed"
    ):
        errors.append("evidence_runtime_classification")

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    source = artifact.get("source") or {}
    scheduler_contract = artifact.get("job_scheduler") or {}
    if (
        artifact.get("task_id") != "CB-220"
        or artifact.get("phase") != "P2.3"
        or artifact.get("release_commit") != implementation_commit
        or source.get("license_expression") != STRICT_LICENSE
        or source.get("upstream_clarification_received") is not False
        or scheduler_contract.get("single_runtime_lease") is not True
        or scheduler_contract.get("heartbeat_and_expiry") is not True
        or scheduler_contract.get("workspace_alias_gate") is not True
        or scheduler_contract.get("resource_readiness_gate") is not True
        or scheduler_contract.get("truthful_stop_terminal") is not True
        or scheduler_contract.get("unsafe_mutation_auto_replay") is not False
        or scheduler_contract.get("outbox_worker_integrated") is not False
        or scheduler_contract.get("real_wechat") is not False
        or scheduler_contract.get("real_runtime") is not False
        or scheduler_contract.get("pg_2_executed") is not False
    ):
        errors.append("evidence_artifact")

    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    install = load_json(EVIDENCE / "install-apply.redacted.json")
    for name, document in (("preflight", preflight), ("install", install)):
        if (
            document.get("target_id_sha256") != EXPECTED_TARGET_HASH
            or document.get("current_release_before") != EXPECTED_CURRENT
            or document.get("current_release_after") != EXPECTED_CURRENT
            or document.get("workspace_release_before") != EXPECTED_WORKSPACE
            or document.get("workspace_release_after") != EXPECTED_WORKSPACE
            or document.get("service_enabled") is not False
            or document.get("service_active") is not False
            or document.get("process_count") != 0
            or document.get("listener_count") != 0
            or document.get("incoming_count") != 0
            or document.get("canonical_runtime_db_present") is not False
            or document.get("result") != "passed"
        ):
            errors.append(f"evidence_target_{name}")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("plaintext_scan_hits") != 0
        or security.get("secret_scan_hits") != 0
        or security.get("workspace_escape_count") != 0
        or security.get("real_credentials_used") is not False
        or security.get("real_provider_used") is not False
        or security.get("result") != "passed"
    ):
        errors.append("evidence_security")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("remote_branch_count") != 0
        or publication.get("pr_count") != 0
        or publication.get("tag_count") != 0
        or publication.get("release_count") != 0
        or publication.get("push_performed") is not False
        or publication.get("result") != "passed"
    ):
        errors.append("evidence_publication")

    report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "CB-220 Validation Report",
        "Task state: `passed`",
        "CB-230: `not_started`",
        "PG-2: `not_started`",
        "max active Runtime lease: `1`",
        "activation_pending",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
    ):
        if marker not in report:
            errors.append(f"evidence_report:{marker}")

    for path in EVIDENCE.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            errors.append(f"evidence_secret:{path.name}")
        ipv4_values = re.findall(
            r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])",
            text,
        )
        if any(value != "127.0.0.1" for value in ipv4_values):
            errors.append(f"evidence_ipv4:{path.name}")


def validate(final: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    reports: list[str] = []
    if git("branch", "--show-current")[1] != EXPECTED_BRANCH:
        errors.append("branch")
    if git("remote")[1].splitlines() != ["origin"]:
        errors.append("remotes")
    if git("remote", "get-url", "origin")[1] != EXPECTED_ORIGIN:
        errors.append("origin")
    remote_code, remote = git(
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        f"refs/heads/{EXPECTED_BRANCH}",
        check=False,
    )
    if remote_code != 2 or remote:
        errors.append("remote_publication")
    if git("merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False)[0] != 0:
        errors.append("base_not_ancestor")

    allowed = IMPLEMENTATION_PATHS | CLOSURE_PATHS
    unexpected = sorted(
        path
        for path in changed_paths()
        if path not in allowed
        and not path.startswith("CyberBoss/docs/evidence/CB-220/")
    )
    errors.extend(f"unexpected_path:{path}" for path in unexpected)
    for frozen in FROZEN_PATHS:
        if git("diff", "--quiet", BASE_COMMIT, "--", frozen, check=False)[0] != 0:
            errors.append(f"frozen_path:{frozen}")
    if list(PROJECT.rglob(".git")):
        errors.append("nested_git_repository")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        if row.startswith("160000 "):
            errors.append(f"gitlink:{row}")

    contract = (
        PROJECT / "docs/governance/RUN_CONTRACT_P2_3_CB_220.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P2.3 / CB-220",
        BASE_COMMIT,
        "AC-012",
        "AC-013",
        "AC-014",
        "AC-015",
        "AC-045",
        "AC-064",
        "INV-005",
        "INV-007",
        "created_at,id",
        "heartbeat",
        "ambiguous",
        "CB-230",
        "PG-2",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "不创建新 repo",
        "不 push",
    ):
        if marker not in contract:
            errors.append(f"contract:{marker}")

    dag = yaml.safe_load(
        (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
    )
    task = next((row for row in dag["tasks"] if row.get("id") == "CB-220"), {})
    if (
        task.get("phase") != "P2.3"
        or task.get("stage") != "S2"
        or task.get("dependencies") != ["CB-200", "CB-120"]
        or task.get("acceptance_criteria") != EXPECTED_ACCEPTANCE
        or task.get("pass_gate") != "PG-2"
    ):
        errors.append("task_contract")

    source = load_json(PROJECT / "machine/source-lock.json")
    conflict = source["whereabouts_license_conflict"]
    if {
        item.strip() for item in conflict["compliance_expression"].split("AND")
    } != {"AGPL-3.0-only", "GPL-3.0-only"}:
        errors.append("license")
    if (
        conflict.get("preserve_original_license_and_source") is not True
        or conflict.get("upstream_clarification_received") is not False
        or any(source["upstream_relationship"].values())
        or source.get("repository") != "LinzeColin/MetaDatabase"
    ):
        errors.append("source_boundary")

    ledger = load_json(PROJECT / "machine/facts/post-baseline-change-ledger.json")
    entries = [
        row for row in ledger.get("entries", []) if row.get("task_id") == "CB-220"
    ]
    implementation_present = (
        PROJECT / "app/src/services/jobs/job-scheduler.js"
    ).is_file()
    if final or implementation_present:
        if len(entries) != 1 or entries[0].get("base_commit") != BASE_COMMIT:
            errors.append("modification_ledger")
    elif entries:
        errors.append("premature_modification_ledger")
    if (
        ledger.get("strict_compliance_expression") != STRICT_LICENSE
        or ledger.get("upstream_clarification_received") is not False
    ):
        errors.append("ledger_license")

    try:
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        verify_manifest(KIT / "MANIFEST.sha256", errors)
    except (OSError, ValueError) as error:
        errors.append(f"manifest_exception:{type(error).__name__}")

    validate_state(final, errors)
    if final:
        validate_final_evidence(errors)

    implementation_ready = all(
        (REPO / path).is_file()
        for path in (
            "CyberBoss/app/src/services/jobs/job-scheduler.js",
            "CyberBoss/app/src/services/jobs/resource-readiness-gate.js",
            "CyberBoss/app/test/job-scheduler.test.js",
            "CyberBoss/app/test/resource-readiness-gate.test.js",
            "CyberBoss/tests/job-scheduler.test.js",
        )
    )
    if implementation_ready:
        commands = [
            (
                "scheduler",
                ["node", "--test", "test/job-scheduler.test.js"],
                PROJECT / "app",
                ("fail 0",),
                600,
            ),
            (
                "resource_gate",
                ["node", "--test", "test/resource-readiness-gate.test.js"],
                PROJECT / "app",
                ("fail 0",),
                240,
            ),
            (
                "workspace",
                ["node", "--test", "test/workspace-scope.test.js"],
                PROJECT / "app",
                ("fail 0",),
                240,
            ),
            (
                "root_contract",
                ["node", "--test", "tests/job-scheduler.test.js"],
                PROJECT,
                ("fail 0",),
                300,
            ),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_test", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
        ]
        for name, args, cwd, required, timeout in commands:
            run_command(
                name, args, errors, cwd=cwd, required=required, timeout=timeout
            )
    elif final:
        errors.append("implementation_missing")

    for name, args, required, timeout in (
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            ("PRESTAGE0_VALIDATION=PASS",),
            300,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            ("TASKPACK_VALIDATION=PASS",),
            300,
        ),
    ):
        run_command(name, args, errors, required=required, timeout=timeout)

    reports.extend(
        [
            f"mode={'final' if final else 'prepare'}",
            f"base_commit={BASE_COMMIT}",
            f"changed_paths={len(changed_paths())}",
            f"errors={len(errors)}",
        ]
    )
    return errors, reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Validate the frozen CB-210 state before CB-220 closure.",
    )
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for report in reports:
        print(report)
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB220_VALIDATION=FAIL")
        return 1
    print("CB220_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
