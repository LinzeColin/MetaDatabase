#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P2.5 / CB-240."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-240"
BASE_COMMIT = "8793e186f4baa2767dc3da0378492ffa17984d4d"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
EXPECTED_ACCEPTANCE = ["AC-030", "AC-031", "AC-032", "AC-033"]

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/migrations/005_cb240_canonical_sync.sql",
    "CyberBoss/app/package.json",
    "CyberBoss/app/scripts/canonical-rebuild.js",
    "CyberBoss/app/scripts/canonical-sync-acceptance.js",
    "CyberBoss/app/scripts/canonical-sync-data.js",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/services/canonical/canonical-sync.js",
    "CyberBoss/app/src/services/db/database-adapter.js",
    "CyberBoss/app/src/services/jobs/job-scheduler.js",
    "CyberBoss/app/test/canonical-sync.test.js",
    "CyberBoss/app/test/job-scheduler.test.js",
    "CyberBoss/app/test/runtime-spool.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P2_5_CB_240.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-canonical-sync.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-canonical-sync-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-canonical-sync.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/private_db_client_safe.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.service",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.timer",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb240.py",
    "CyberBoss/tests/canonical-sync.test.js",
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
    "canonical-sync-report.redacted.json",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "publication-check.json",
    "rollback-plan.json",
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
    "CyberBoss/docs/evidence/CB-200",
    "CyberBoss/docs/evidence/CB-210",
    "CyberBoss/docs/evidence/CB-220",
    "CyberBoss/docs/evidence/CB-230",
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
        "CB-220",
        "CB-230",
    }
    if final:
        passed.add("CB-240")
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
            "run_id": "P2.5",
            "gate_id": None,
            "task_id": "CB-240",
            "scope": "canonical_sync_rebuild",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P2.4",
            "gate_id": None,
            "task_id": "CB-230",
            "scope": "durable_outbox_delivery_truth",
            "status": "passed",
        }
    )
    if state.get("current_run") != expected_current:
        errors.append("current_run")


def validate_canonical_report(
    report: dict[str, Any],
    implementation_commit: str,
    errors: list[str],
) -> None:
    try:
        latency = report["ac_031_batching_latency"]
        conflict = report["ac_032_conflict_retry"]
        privacy = report["ac_033_privacy"]
        boundaries = report["boundaries"]
        if (
            report.get("task_id") != "CB-240"
            or report.get("phase") != "P2.5"
            or report.get("release_commit") != implementation_commit
            or report.get("target_id_sha256") != EXPECTED_TARGET_HASH
            or report.get("claim_level") != "deterministic_fixture"
            or report.get("generated_from_synthetic_state") is not True
            or report.get("result") != "passed"
            or report["executable_suite"]["failures"] != 0
            or report["executable_suite"]["fixed_wait"] is not False
            or report["ac_030_rebuild"]["sqlite_present"] is not False
            or report["ac_030_rebuild"]["canonical_event_count"] != 1000
            or report["ac_030_rebuild"]["terminal_job_count"] != 1000
            or report["ac_030_rebuild"]["r2_fixture_only"] is not True
            or report["ac_030_rebuild"]["real_r2_operation"] is not False
            or latency["terminal_jobs"] != 50
            or latency["latency_p95_seconds"] > 60
            or latency["terminal_events"] != 1000
            or latency["count_threshold_batch_count"] != 20
            or any(size != 50 for size in latency["count_threshold_batch_sizes"])
            or latency["age_threshold_flush_at_seconds"] != 60
            or latency["set_diff"] != 0
            or conflict["concurrent_sync_groups"] != 50
            or conflict["manifest_409_refetch_exercised"] is not True
            or conflict["auth_403_pending_exercised"] is not True
            or conflict["rate_limit_429_exercised"] is not True
            or conflict["retry_hint_ms"] != 120000
            or conflict["partial_success_refetch_exercised"] is not True
            or conflict["outage_duration_seconds"] != 600
            or conflict["real_wait_calls"] != 0
            or conflict["set_diff"] != 0
            or privacy["full_prompt_result_identity_hits"] != 0
            or privacy["encryption_key_hits"] != 0
            or report["integrity_protection"][
                "same_event_id_different_hash_detected"
            ]
            is not True
            or report["integrity_protection"]["last_write_wins"] is not False
            or report["integrity_protection"]["bounded_mutation_allowed"] is not False
            or report["canonical_truth"]["allowed_operations"]
            != ["ingest", "get", "list", "verify"]
            or report["canonical_truth"]["forbidden_operations"]
            != ["clone", "put", "delete"]
            or boundaries["code_data_identity_separated"] is not True
            or boundaries["real_private_database_operation"] is not False
            or boundaries["private_database_activation_status"]
            != "activation_pending"
            or boundaries["real_r2_operation"] is not False
            or boundaries["timeline_projection_only"] is not True
            or boundaries["timeline_web_build_search"] is not False
            or boundaries["cb_300_executed"] is not False
            or boundaries["pg_2_executed"] is not False
            or boundaries["upstream_clarification_received"] is not False
            or boundaries["license_expression"] != STRICT_LICENSE
        ):
            errors.append("evidence_canonical_report")
    except (KeyError, TypeError):
        errors.append("evidence_canonical_report_shape")


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
    implementation_commit = str(implementation.get("implementation_commit"))
    if (
        implementation.get("task_id") != "CB-240"
        or implementation.get("phase") != "P2.5"
        or implementation.get("base_commit") != BASE_COMMIT
        or implementation.get("parent_commit") != BASE_COMMIT
        or not re.fullmatch(r"[0-9a-f]{40}", implementation_commit)
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

    canonical_report = load_json(
        EVIDENCE / "canonical-sync-report.redacted.json"
    )
    validate_canonical_report(canonical_report, implementation_commit, errors)

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    source = artifact.get("source") or {}
    canonical = artifact.get("canonical_sync") or {}
    deployment = artifact.get("deployment") or {}
    if (
        artifact.get("task_id") != "CB-240"
        or artifact.get("phase") != "P2.5"
        or artifact.get("release_commit") != implementation_commit
        or source.get("license_expression") != STRICT_LICENSE
        or source.get("corresponding_source_complete") is not True
        or source.get("original_licenses_preserved") is not True
        or source.get("upstream_clarification_received") is not False
        or artifact.get("runtime_spool", {}).get("schema_version") != 5
        or artifact.get("runtime_spool", {}).get("canonical_sync_integrated")
        is not True
        or canonical.get("area") != "Private-MetaDatabase"
        or canonical.get("domain") != "CyberBoss"
        or canonical.get("access_mode") != "no_clone_client"
        or canonical.get("allowed_operations")
        != ["ingest", "get", "list", "verify"]
        or canonical.get("max_records") != 50
        or canonical.get("max_uncompressed_bytes") != 262144
        or canonical.get("max_age_seconds") != 60
        or canonical.get("deterministic_gzip") is not True
        or canonical.get("content_addressed") is not True
        or canonical.get("manifest_conflict_last_write_wins") is not False
        or canonical.get("same_id_different_hash_quarantine") is not True
        or canonical.get("code_data_identity_separated") is not True
        or canonical.get("rebuild_without_sqlite") is not True
        or canonical.get("timeline_projection_only") is not True
        or canonical.get("real_private_database") is not False
        or canonical.get("private_database_activation_status")
        != "activation_pending"
        or canonical.get("real_r2") is not False
        or canonical.get("cb_300_executed") is not False
        or canonical.get("pg_2_executed") is not False
        or deployment.get("candidate_only") is not True
        or deployment.get("switch_current") is not False
        or deployment.get("enable_service") is not False
        or deployment.get("clone_private_database") is not False
        or deployment.get("remote_publication") != "none"
    ):
        errors.append("evidence_artifact")

    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    install = load_json(EVIDENCE / "install-apply.redacted.json")
    for name, document in (("preflight", preflight), ("install", install)):
        if (
            document.get("task_id") != "CB-240"
            or document.get("phase") != "P2.5"
            or document.get("target_id_sha256") != EXPECTED_TARGET_HASH
            or document.get("current_release_before") != EXPECTED_CURRENT
            or document.get("current_release_after") != EXPECTED_CURRENT
            or document.get("workspace_release_before") != EXPECTED_WORKSPACE
            or document.get("workspace_release_after") != EXPECTED_WORKSPACE
            or document.get("service_enabled") is not False
            or document.get("service_active") is not False
            or document.get("canonical_service_enabled") is not False
            or document.get("canonical_service_active") is not False
            or document.get("canonical_timer_enabled") is not False
            or document.get("canonical_timer_active") is not False
            or document.get("code_process_count") != 0
            or document.get("data_process_count") != 0
            or document.get("listener_count") != 0
            or document.get("incoming_count") != 0
            or document.get("canonical_runtime_db_present") is not False
            or document.get("result") != "passed"
        ):
            errors.append(f"evidence_target_{name}")
    if (
        install.get("release_commit") != implementation_commit
        or install.get("apply_count") != 2
        or install.get("verify_count") != 1
        or install.get("idempotent_second_apply") is not True
        or install.get("candidate_retained") is not True
        or install.get("candidate_release_immutable") is not True
        or install.get("target_acceptance_passed") is not True
        or install.get("target_acceptance_test_count", 0) < 17
        or install.get("target_acceptance_set_diff") != 0
        or install.get("target_acceptance_privacy_hits") != 0
        or install.get("private_database_operations") != 0
        or install.get("r2_operations") != 0
        or install.get("real_business_credential_operations") != 0
        or install.get("service_started") is not False
        or install.get("staging_cleaned") is not True
    ):
        errors.append("evidence_install")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("plaintext_scan_hits") != 0
        or security.get("secret_scan_hits") != 0
        or security.get("raw_target_hits") != 0
        or security.get("canonical_full_prompt_result_identity_hits") != 0
        or security.get("canonical_encryption_key_hits") != 0
        or security.get("target_address_persisted") is not False
        or security.get("real_credentials_used") is not False
        or security.get("private_database_operations") != 0
        or security.get("r2_operations") != 0
        or security.get("result") != "passed"
    ):
        errors.append("evidence_security")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("remote_branch_count") != 0
        or publication.get("remote_ref_count") != 0
        or publication.get("pr_count") != 0
        or publication.get("tag_count") != 0
        or publication.get("release_count") != 0
        or publication.get("push_performed") is not False
        or publication.get("remote_publication") != "none"
        or publication.get("result") != "passed"
    ):
        errors.append("evidence_publication")

    source_record = load_json(EVIDENCE / "source-modification-record.json")
    if (
        source_record.get("base_commit") != BASE_COMMIT
        or source_record.get("implementation_commit") != implementation_commit
        or source_record.get("license_expression") != STRICT_LICENSE
        or source_record.get("original_source_and_licenses_preserved") is not True
        or source_record.get("corresponding_source_complete") is not True
        or source_record.get("conflict_record_preserved") is not True
        or source_record.get("upstream_clarification_received") is not False
        or source_record.get("upstream_sync_enabled") is not False
        or source_record.get("upstream_support_claimed") is not False
        or source_record.get("upstream_endorsement_claimed") is not False
        or source_record.get("vendor_original_paths_changed") != []
        or source_record.get("historical_evidence_paths_changed") != []
        or source_record.get("result") != "passed"
    ):
        errors.append("evidence_source_record")

    rollback = load_json(EVIDENCE / "rollback-plan.json")
    if (
        rollback.get("candidate_retained_for_audit") is not True
        or rollback.get("candidate_retained_inactive") is not True
        or rollback.get("current_release_rollback_required") is not False
        or rollback.get("canonical_database_rollback_required") is not False
        or rollback.get("exact_staging_cleanup_completed") is not True
        or rollback.get("final_transient_cleanup_completed") is not True
        or rollback.get("real_canonical_rollback_required") is not False
        or rollback.get("result") != "passed"
    ):
        errors.append("evidence_rollback")

    report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "CB-240 Validation Report",
        "Task state: `passed`",
        "CB-300: `not_started`",
        "PG-2: `not_started`",
        "canonical events: `1,000`",
        "concurrent sync groups: `50`",
        "set diff: `0`",
        "activation_pending",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
    ):
        if marker not in report:
            errors.append(f"evidence_report:{marker}")

    validation = (EVIDENCE / "validation.txt").read_text(encoding="utf-8")
    for marker in (
        "CB240_VALIDATION_RECORD",
        "LOCAL_APP_TESTS=PASS",
        "TARGET_CANONICAL_ACCEPTANCE=PASS",
        "TARGET_FINAL_QUIESCENCE=PASS",
        "PUBLICATION_CHECK=PASS",
        "CB_300_STARTED=false",
        "PG_2_EXECUTED=false",
        "REAL_PRIVATE_DATABASE_OPERATIONS=0",
        "REAL_R2_OPERATIONS=0",
        "UPSTREAM_CLARIFICATION_RECEIVED=false",
    ):
        if marker not in validation:
            errors.append(f"evidence_validation:{marker}")

    for path in EVIDENCE.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "CB240-PRIVATE" in text:
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
        and not path.startswith("CyberBoss/docs/evidence/CB-240/")
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
        PROJECT / "docs/governance/RUN_CONTRACT_P2_5_CB_240.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P2.5 / CB-240",
        BASE_COMMIT,
        *EXPECTED_ACCEPTANCE,
        "Private-MetaDatabase",
        "ingest|get|list|verify",
        "same event ID/different record hash",
        "CB-300",
        "PG-2",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "不创建新 repo",
        "不 push",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")

    dag = yaml.safe_load(
        (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
    )
    task = next((row for row in dag["tasks"] if row.get("id") == "CB-240"), {})
    if (
        task.get("phase") != "P2.5"
        or task.get("stage") != "S2"
        or task.get("dependencies") != ["CB-120", "CB-200", "CB-230"]
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
        row for row in ledger.get("entries", []) if row.get("task_id") == "CB-240"
    ]
    if (
        len(entries) != 1
        or entries[0].get("base_commit") != BASE_COMMIT
        or entries[0].get("upstream_sync_enabled") is not False
        or entries[0].get("upstream_support_claimed") is not False
        or entries[0].get("upstream_endorsement_claimed") is not False
    ):
        errors.append("modification_ledger")
    if (
        ledger.get("strict_compliance_expression") != STRICT_LICENSE
        or ledger.get("upstream_clarification_received") is not False
        or ledger.get("original_source_and_licenses_preserved") is not True
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

    zero_release = "0" * 40
    for name, args, cwd, required, timeout in (
        (
            "canonical_sync",
            [
                "node",
                "--test",
                "test/canonical-sync.test.js",
                "test/job-scheduler.test.js",
            ],
            PROJECT / "app",
            ("fail 0",),
            300,
        ),
        (
            "root_contract",
            ["node", "--test", "tests/canonical-sync.test.js"],
            PROJECT,
            ("fail 0",),
            360,
        ),
        (
            "identity_scope",
            [sys.executable, str(KIT / "tests/test_identity_scope.py")],
            REPO,
            ("OK",),
            300,
        ),
        (
            "config",
            [
                "node",
                str(KIT / "tests/validate_config.js"),
                "--allow-placeholders",
                str(KIT / "config/cyberboss.env.example"),
                str(KIT / "config/workspaces.json.example"),
            ],
            REPO,
            ("CONFIG_VALIDATION=PASS",),
            300,
        ),
        (
            "install_check",
            [
                "bash",
                str(KIT / "scripts/install-canonical-sync.sh"),
                "--check",
                "--release-id",
                zero_release,
            ],
            REPO,
            ("CANONICAL_SYNC_INSTALL_CHECK=PASS",),
            300,
        ),
        (
            "acceptance_check",
            [
                "bash",
                str(KIT / "scripts/accept-canonical-sync.sh"),
                "--check",
                "--release-id",
                zero_release,
            ],
            REPO,
            ("CANONICAL_SYNC_ACCEPTANCE_CHECK=PASS",),
            300,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
        ("app_test", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            REPO,
            ("PRESTAGE0_VALIDATION=PASS",),
            300,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            REPO,
            ("TASKPACK_VALIDATION=PASS",),
            300,
        ),
    ):
        run_command(
            name,
            args,
            errors,
            cwd=cwd,
            required=required,
            timeout=timeout,
        )

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
        help="Validate the frozen CB-230 state before CB-240 closure.",
    )
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for report in reports:
        print(report)
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB240_VALIDATION=FAIL")
        return 1
    print("CB240_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
