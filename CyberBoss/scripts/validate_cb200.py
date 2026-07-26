#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P2.1 / CB-200."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-200"
BASE_COMMIT = "c6f5a288aa662591c6e4e21c6294a7966d233fc6"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
EXPECTED_ACCEPTANCE = ["AC-003", "AC-016", "AC-055", "AC-063"]

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/package.json",
    "CyberBoss/app/migrations/001_runtime_spool.sql",
    "CyberBoss/app/migrations/002_cb200_retention_and_transitions.sql",
    "CyberBoss/app/scripts/runtime-spool-acceptance.js",
    "CyberBoss/app/src/services/db/database-adapter.js",
    "CyberBoss/app/src/services/jobs/job-state-machine.js",
    "CyberBoss/app/test/runtime-spool.test.js",
    "CyberBoss/app/test/job-state-machine.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P2_1_CB_200.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-runtime-spool.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-runtime-spool-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-spool.sh",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb200.py",
    "CyberBoss/tests/runtime-spool.test.js",
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
    "crash-matrix.redacted.json",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "migration-acceptance.redacted.json",
    "property-test-report.json",
    "publication-check.json",
    "rollback-plan.json",
    "schema-dump.redacted.sql",
    "security-report.json",
    "source-modification-record.json",
    "target-preflight.redacted.json",
    "validation.txt",
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
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/sql/runtime-spool.sql",
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
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"manifest_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if (
            relative in entries
            or relative.startswith("/")
            or ".." in Path(relative).parts
        ):
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
    timeout: int = 420,
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
    }
    if final:
        passed.add("CB-200")
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
            "run_id": "P2.1",
            "gate_id": None,
            "task_id": "CB-200",
            "scope": "sqlite_wal_spool_and_job_state_machine",
            "status": "passed",
        }
        if final
        else {
            "run_id": "PG-1",
            "gate_id": "PG-1",
            "task_id": None,
            "scope": "stage_1_exit_gate",
            "status": "passed",
        }
    )
    if state.get("current_run") != expected_current:
        errors.append("current_run")


def validate_final_evidence(errors: list[str]) -> None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_directory")
        return
    actual = {
        candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()
    }
    if actual != FINAL_EVIDENCE:
        errors.append("evidence_inventory")
        return

    implementation = load_json(EVIDENCE / "implementation-commit.json")
    commit = implementation.get("implementation_commit")
    if (
        implementation.get("task_id") != "CB-200"
        or implementation.get("phase") != "P2.1"
        or implementation.get("base_commit") != BASE_COMMIT
        or implementation.get("parent_commit") != BASE_COMMIT
        or not re.fullmatch(r"[0-9a-f]{40}", str(commit or ""))
        or implementation.get("built_from_clean_worktree") is not True
        or implementation.get("remote_publication") != "none"
    ):
        errors.append("evidence_implementation")
        return
    if git("rev-parse", f"{commit}^")[1] != BASE_COMMIT:
        errors.append("implementation_parent")
    if git("rev-parse", "HEAD^")[1] != commit:
        errors.append("closure_parent")

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    spool = artifact.get("runtime_spool") or {}
    source = artifact.get("source") or {}
    deployment = artifact.get("deployment") or {}
    if (
        artifact.get("task_id") != "CB-200"
        or artifact.get("phase") != "P2.1"
        or artifact.get("release_commit") != commit
        or source.get("license_expression") != STRICT_LICENSE
        or source.get("corresponding_source_complete") is not True
        or source.get("original_licenses_preserved") is not True
        or source.get("upstream_clarification_received") is not False
        or spool.get("schema_version") != 2
        or spool.get("migration_mode") != "additive_backward_compatible"
        or spool.get("active_payload_encryption") != "AES-256-GCM"
        or spool.get("real_canonical_sync") is not False
        or deployment.get("switch_current") is not False
        or deployment.get("enable_service") is not False
        or deployment.get("remote_publication") != "none"
    ):
        errors.append("evidence_artifact")

    migration = load_json(EVIDENCE / "migration-acceptance.redacted.json")
    if (
        migration.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or migration.get("release_commit") != commit
        or migration.get("clean_migration") != "passed"
        or migration.get("existing_v1_migration") != "passed"
        or migration.get("legacy_v1_reader_after_v2") != "passed"
        or migration.get("schema_version") != 2
        or migration.get("journal_mode") != "wal"
        or migration.get("synchronous") != "full"
        or migration.get("foreign_keys") is not True
        or migration.get("busy_timeout_ms") != 5000
        or migration.get("integrity_check") != "ok"
        or migration.get("destructive_statements") != 0
        or migration.get("result") != "passed"
    ):
        errors.append("evidence_migration")

    prop = load_json(EVIDENCE / "property-test-report.json")
    if (
        prop.get("stable_id_fixture_count") != 10000
        or prop.get("stable_id_collisions") != 0
        or prop.get("stable_id_mismatches") != 0
        or prop.get("property_transition_attempts", 0) < 10000
        or prop.get("illegal_transition_successes") != 0
        or prop.get("raw_sql_illegal_transition_successes") != 0
        or prop.get("concurrent_inserters", 0) < 32
        or prop.get("duplicate_inbox_rows") != 0
        or prop.get("duplicate_job_rows") != 0
        or prop.get("canonical_reconcile_set_diff") != 0
        or prop.get("result") != "passed"
    ):
        errors.append("evidence_property")

    crash = load_json(EVIDENCE / "crash-matrix.redacted.json")
    if (
        crash.get("cut_points")
        != [
            "after_begin",
            "after_inbox_insert",
            "after_job_insert",
            "after_event_insert",
            "after_commit",
        ]
        or crash.get("accepted_but_lost") != 0
        or crash.get("uncommitted_fragments") != 0
        or crash.get("duplicate_executable_jobs") != 0
        or crash.get("integrity_failures") != 0
        or crash.get("result") != "passed"
    ):
        errors.append("evidence_crash")

    install = load_json(EVIDENCE / "install-apply.redacted.json")
    if (
        install.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or install.get("implementation_commit") != commit
        or install.get("check_passed") is not True
        or install.get("apply_pass_count") != 2
        or install.get("verify_pass_count") != 1
        or install.get("candidate_release_immutable") is not True
        or install.get("candidate_tests_passed") is not True
        or install.get("current_changed") is not False
        or install.get("workspace_changed") is not False
        or install.get("service_started") is not False
        or install.get("staging_removed") is not True
        or install.get("incoming_removed") is not True
        or install.get("result") != "passed"
    ):
        errors.append("evidence_install")

    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    if (
        preflight.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or preflight.get("current_release_commit") != EXPECTED_CURRENT
        or preflight.get("workspace_head") != EXPECTED_WORKSPACE
        or preflight.get("runtime_db_present") is not False
        or preflight.get("service_active") is not False
        or preflight.get("service_enabled") is not False
        or preflight.get("result") != "passed"
    ):
        errors.append("evidence_preflight")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("plaintext_db_wal_shm_hits") != 0
        or security.get("encryption_key_hits") != 0
        or security.get("secret_value_hits") != 0
        or security.get("p0_findings") != 0
        or security.get("p1_findings") != 0
        or security.get("real_credential_reads") != 0
        or security.get("provider_writes") != 0
        or security.get("private_database_operations") != 0
        or security.get("target_address_persisted") is not False
        or security.get("result") != "passed"
    ):
        errors.append("evidence_security")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("remote_branch_count") != 0
        or publication.get("pull_request_count") != 0
        or publication.get("tag_count") != 0
        or publication.get("release_count") != 0
        or publication.get("push_performed") is not False
        or publication.get("result") != "passed"
    ):
        errors.append("evidence_publication")

    schema = (EVIDENCE / "schema-dump.redacted.sql").read_text(encoding="utf-8")
    for marker in (
        "CREATE TABLE inbox_messages",
        "CREATE TABLE jobs",
        "CREATE TABLE job_events",
        "CREATE TABLE outbox_messages",
        "CREATE TABLE sync_spool",
        "CREATE TABLE service_state",
        "CREATE TABLE job_state_transitions",
        "jobs_status_transition_guard",
    ):
        if marker not in schema:
            errors.append(f"evidence_schema:{marker}")
    if re.search(r"\b(DROP|RENAME|VACUUM)\b", schema, re.IGNORECASE):
        errors.append("evidence_schema_destructive")

    report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "CB-200 Validation Report",
        "Task state: `passed`",
        "CB-210: `not_started`",
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
    if git(
        "merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False
    )[0] != 0:
        errors.append("base_not_ancestor")

    allowed = IMPLEMENTATION_PATHS | CLOSURE_PATHS
    unexpected = sorted(
        path
        for path in changed_paths()
        if path not in allowed
        and not path.startswith("CyberBoss/docs/evidence/CB-200/")
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
        PROJECT / "docs/governance/RUN_CONTRACT_P2_1_CB_200.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P2.1 / CB-200",
        BASE_COMMIT,
        "AC-003",
        "AC-016",
        "AC-055",
        "AC-063",
        "不得修改 channel poll",
        "AES-256-GCM",
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
    task = next(row for row in dag["tasks"] if row["id"] == "CB-200")
    if (
        task.get("phase") != "P2.1"
        or task.get("dependencies") != ["CB-140"]
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
    ):
        errors.append("source_boundary")

    ledger = load_json(PROJECT / "machine/facts/post-baseline-change-ledger.json")
    entries = [
        row for row in ledger.get("entries", []) if row.get("task_id") == "CB-200"
    ]
    if len(entries) != 1 or entries[0].get("base_commit") != BASE_COMMIT:
        errors.append("modification_ledger")
    if (
        ledger.get("strict_compliance_expression") != STRICT_LICENSE
        or ledger.get("upstream_clarification_received") is not False
    ):
        errors.append("ledger_license")

    try:
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        verify_manifest(KIT / "MANIFEST.sha256", errors)
    except (OSError, ValueError) as error:
        errors.append(f"manifest_exception:{error}")

    validate_state(final, errors)
    if final:
        validate_final_evidence(errors)

    commands = [
        (
            "job_state_machine",
            ["node", "--test", "test/job-state-machine.test.js"],
            PROJECT / "app",
            ("fail 0",),
            180,
        ),
        (
            "runtime_spool",
            ["node", "--test", "test/runtime-spool.test.js"],
            PROJECT / "app",
            ("fail 0",),
            420,
        ),
        (
            "root_contract",
            ["node", "--test", "tests/runtime-spool.test.js"],
            PROJECT,
            ("fail 0",),
            180,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
        ("app_test", ["npm", "test"], PROJECT / "app", ("fail 0",), 600),
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            REPO,
            ("PRESTAGE0_VALIDATION=PASS",),
            300,
        ),
        (
            "dag",
            [
                sys.executable,
                str(KIT / "tests/validate_task_dag.py"),
                str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml"),
            ],
            REPO,
            ("DAG_VALIDATION=PASS tasks=30 stages=6",),
            120,
        ),
        (
            "traceability",
            [
                sys.executable,
                str(KIT / "tests/validate_traceability.py"),
                str(PACK),
            ],
            REPO,
            ("TRACEABILITY_VALIDATION=PASS requirements=53",),
            120,
        ),
        (
            "no_wait",
            [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)],
            REPO,
            ("NO_WAIT_VALIDATION=PASS",),
            120,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            REPO,
            ("TASKPACK_VALIDATION=PASS",),
            180,
        ),
    ]
    for name, args, cwd, required, timeout in commands:
        run_command(
            name,
            args,
            errors,
            cwd=cwd,
            required=required,
            timeout=timeout,
        )
    run_command(
        "shell_syntax",
        [
            "bash",
            "-n",
            str(KIT / "scripts/install-cloud-process-family.sh"),
            str(KIT / "scripts/install-runtime-spool.sh"),
            str(KIT / "scripts/accept-runtime-spool.sh"),
        ],
        errors,
        timeout=120,
    )

    reports.extend(
        [
            f"mode={'final' if final else 'prepare'}",
            f"base_commit={BASE_COMMIT}",
            f"changed_paths={len(changed_paths())}",
            f"implementation_paths={len(IMPLEMENTATION_PATHS)}",
            f"evidence_required={len(FINAL_EVIDENCE)}",
            f"license_expression={STRICT_LICENSE}",
            "upstream_clarification_received=false",
            "real_credentials=not_used",
            "cb210_started=false",
            "pg_2_executed=false",
            "remote_publication=none",
        ]
    )
    return errors, reports


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--final", action="store_true")
    args = parser.parse_args()
    try:
        errors, reports = validate(final=args.final)
    except Exception as error:  # fail closed at the outermost boundary
        print(f"CB200_VALIDATION=FAIL exception={type(error).__name__}:{error}")
        return 2
    if errors:
        print("CB200_VALIDATION=FAIL")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print("CB200_VALIDATION=PASS")
    for report in reports:
        print(f"- {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
