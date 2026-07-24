#!/usr/bin/env python3
"""Read-only validator for the v1.0.15 protected T0703 PASS package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_package_manifest import (
    BASELINE_PREDECESSOR_MANIFEST_PATH,
    BASELINE_PREDECESSOR_MANIFEST_SHA256,
    CONTROL_PREDECESSOR_MANIFEST_PATH,
    CONTROL_PREDECESSOR_MANIFEST_SHA256,
    FOUNDATION_PREDECESSOR_MANIFEST_PATH,
    FOUNDATION_PREDECESSOR_MANIFEST_SHA256,
    INHERITED_CONTRACT_HASHES,
    LEGACY_MANIFEST_PATH,
    LEGACY_MANIFEST_SHA256,
    MANIFEST_PATH,
    PACKAGE_ID,
    PACKAGE_VERSION,
    PREDECESSOR_MANIFEST_PATH,
    PREDECESSOR_MANIFEST_SHA256,
    build_manifest,
)
from jsonschema import Draft202012Validator, FormatChecker
from validate_delivery_status import validate as validate_delivery_status

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_PATH = Path("taskpack/SOURCE_PROVENANCE.v1.0.15.json")
CURRENT_MAINLINE_BASE_COMMIT = (
    "caeae1879ffeb7f5f804dfe79a515b20ffc5ffe7"  # pragma: allowlist secret
)
ACCEPTANCE_REMEDIATION_BASE_COMMIT = (
    "83fec6161d5cd80c62f3553d6332c0113ef5a514"  # pragma: allowlist secret
)
CANDIDATE_SNAPSHOT = {
    "repository": "LinzeColin/MetaDatabase",
    "mainline_base_commit": CURRENT_MAINLINE_BASE_COMMIT,
    "acceptance_remediation_base_commit": ACCEPTANCE_REMEDIATION_BASE_COMMIT,
    "shallow_checkout_fallback": "EXACT_PIN_ONLY",
}
PROTECTED_BETA_ATTEMPT_LEDGER_PATH = Path("machine/stages/S7/reviews/t0702/attempt-ledger.json")
PROTECTED_M3_ATTEMPT_LEDGER_PATH = Path("machine/stages/S7/reviews/t0703/attempt-ledger.json")
PROTECTED_M3_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0703/execution-receipt.json")
PROTECTED_M3_RECEIPT_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-m3-execution-receipt-v1.schema.json"
)
AUTHORIZATION_BASIS = (
    "The exact T0702 protected PASS, immutable six-attempt failed T0703 lineage, PR 110 and its "
    "exact-main 83fec616 protected attempt-1 PASS, plus independent zero-effect verification "
    "close T0703 and consume every M3 dispatch authority without entering T0704"
)
AUTHORIZED_SCOPE = (
    "One T0703 receipt-closure package: bind the exact protected PASS and independent unchanged "
    "Gmail/private-repository observations, preserve the six failed heads as immutable history, "
    "set M3 authority and every data-plane budget to zero, and allow only one controlled evidence "
    "delivery. T0704, Timeline, production, final Acceptance and final publication remain "
    "unauthorized"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_provenance(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Return the exact RMD-06 and protected T0703 PASS provenance authority."""

    root = root.resolve()
    attempt_ledger = _load(root / PROTECTED_BETA_ATTEMPT_LEDGER_PATH)
    attempt_summary = attempt_ledger.get("summary", {})
    m3_ledger = _load(root / PROTECTED_M3_ATTEMPT_LEDGER_PATH)
    m3_attempts = m3_ledger.get("attempts", [])
    m3_policy = m3_ledger.get("completion_policy", {})
    m3_receipt = _load(root / PROTECTED_M3_RECEIPT_PATH)
    m3_receipt_schema = _load(root / PROTECTED_M3_RECEIPT_SCHEMA_PATH)
    if (
        len(attempt_ledger.get("rejected_dispatches", [])) != 1
        or len(attempt_ledger.get("attempts", [])) != 11
        or attempt_summary.get("controlled_main_deliveries") != 8
        or attempt_summary.get("protected_beta_dispatches") != 12
        or attempt_summary.get("context_rejected_dispatches") != 1
        or attempt_summary.get("protected_workflow_runs") != 11
        or attempt_summary.get("workflow_reruns") != 0
        or attempt_summary.get("latest_outcome") != "PASS"
        or attempt_summary.get("last_failure_phase") != "METADATA_VERIFICATION"
        or attempt_summary.get("last_installation_token_failure_class") != "UNCLASSIFIED"
        or attempt_summary.get("t0702_complete") is not True
        or attempt_summary.get("m3_predecessor_satisfied") is not True
        or attempt_summary.get("m3_allowed") is not False
        or attempt_summary.get("m3_authority_status") != "WITHHELD_BY_CURRENT_OWNER_SCOPE"
    ):
        raise ValueError("protected Beta attempt ledger is not the exact observed state")
    if (
        len(m3_attempts) != 6
        or [item.get("sequence") for item in m3_attempts] != [1, 2, 3, 4, 5, 6]
        or [item.get("workflow", {}).get("run_id") for item in m3_attempts]
        != [
            30060804854,
            30063841144,
            30066295809,
            30068892160,
            30072484529,
            30077550182,
        ]
        or [item.get("workflow", {}).get("workflow_head_sha") for item in m3_attempts]
        != [
            "f747ddcd2e5eab589802a0c545293cd6f275ca71",  # pragma: allowlist secret
            "9b15c4d5208429125c9ce2680cac4fbb408f65e0",  # pragma: allowlist secret
            "bc0bfb3bc60a5ad769b286bb7b4bcdfc1ac195e6",  # pragma: allowlist secret
            "b922219fa80fd0f55e8dd0d100a87ced2a77b2b8",  # pragma: allowlist secret
            "c860f3880b48b03c3f71ac79e61e278125fb1811",  # pragma: allowlist secret
            "9ca3b47eaaa75ef2f6e6650b41960d11545ed04e",  # pragma: allowlist secret
        ]
        or any(item.get("workflow", {}).get("reruns") != 0 for item in m3_attempts)
        or any(
            item.get("jobs", {}).get("m3_budget_one", {}).get("status") != "FAILED"
            for item in m3_attempts
        )
        or any(
            item.get("jobs", {}).get("identity_plaintext_cleanup", {}).get("status") != "PASS"
            for item in m3_attempts
        )
        or any(
            item.get("effects", {}).get("private_repository_new_commits") != 0
            or item.get("effects", {}).get("private_repository_head_changed") is not False
            or item.get("effects", {}).get("processed_writes") != "ZERO_OBSERVED"
            or item.get("effects", {}).get("processed_current_before_dispatch") != "ZERO"
            or item.get("effects", {}).get("processed_current_after_dispatch") != "ZERO"
            or item.get("effects", {}).get("gmail_trash_messages_after_dispatch") != 0
            or item.get("effects", {}).get("source_mutation_attribution") != "ZERO_OBSERVED"
            for item in m3_attempts[:4]
        )
        or m3_attempts[4].get("public_failure", {}).get("aggregate_failure_class")
        != "MUTATION_FAILED"
        or m3_attempts[4].get("effects", {}).get("private_repository_new_commits")
        != "NONZERO_NOT_EXACTLY_COUNTED"
        or m3_attempts[4].get("effects", {}).get("private_repository_head_changed") is not True
        or m3_attempts[4].get("effects", {}).get("processed_writes") != "ONE_RECOVERED"
        or m3_attempts[4].get("effects", {}).get("processed_current_before_dispatch") != "ZERO"
        or m3_attempts[4].get("effects", {}).get("processed_current_after_dispatch") != "ONE"
        or m3_attempts[4].get("effects", {}).get("gmail_trash_messages_after_dispatch") != 1
        or m3_attempts[4].get("effects", {}).get("source_mutation_attribution")
        != "UNCONFIRMED_EXACT_SOURCE"
        or m3_attempts[5].get("public_failure", {}).get("reason_code")
        != "PROTECTED_M3_PROCESSED_PLAN_FAILED"
        or m3_attempts[5].get("public_failure", {}).get("failure_phase") != "PROCESSED_PLAN"
        or m3_attempts[5].get("effects", {}).get("private_repository_new_commits") != 0
        or m3_attempts[5].get("effects", {}).get("private_repository_head_changed") is not False
        or m3_attempts[5].get("effects", {}).get("raw_ciphertext_creations") != "ZERO_OBSERVED"
        or m3_attempts[5].get("effects", {}).get("processed_writes") != "ZERO_OBSERVED"
        or m3_attempts[5].get("effects", {}).get("processed_current_before_dispatch") != "ONE"
        or m3_attempts[5].get("effects", {}).get("processed_current_after_dispatch") != "ONE"
        or m3_attempts[5].get("effects", {}).get("gmail_trash_messages_after_dispatch") != 0
        or m3_attempts[5].get("effects", {}).get("source_mutation_attribution") != "ZERO_OBSERVED"
        or any(item.get("effects", {}).get("source_mutations") != 0 for item in m3_attempts)
        or m3_policy.get("same_head_rerun_allowed") is not False
        or m3_policy.get("failed_head_redispatch_allowed") is not False
        or m3_policy.get("repaired_exact_main_candidate_dispatch_allowed") is not True
        or m3_policy.get("zero_mutation_reconciliation_dispatch_allowed") is not True
        or m3_policy.get("next_candidate_dispatch_limit") != 1
    ):
        raise ValueError("protected M3 attempt ledger is not the exact reconciliation lineage")
    receipt_errors = list(
        Draft202012Validator(
            m3_receipt_schema,
            format_checker=FormatChecker(),
        ).iter_errors(m3_receipt)
    )
    receipt_control = m3_receipt.get("control", {})
    receipt_public = m3_receipt.get("public_result", {})
    receipt_verification = m3_receipt.get("independent_post_run_verification", {})
    receipt_scope = m3_receipt.get("scope_decision", {})
    receipt_claims = m3_receipt.get("claims", {})
    if (
        receipt_errors
        or m3_receipt.get("task_id") != "T0703"
        or m3_receipt.get("observed_at_utc") != "2026-07-24T09:20:08Z"
        or receipt_control.get("pull_request_number") != 110
        or receipt_control.get("merge_commit_sha") != "83fec6161d5cd80c62f3553d6332c0113ef5a514"
        or receipt_control.get("workflow_run_id") != 30081901453
        or receipt_control.get("workflow_head_sha") != receipt_control.get("merge_commit_sha")
        or receipt_control.get("workflow_attempt") != 1
        or receipt_control.get("reruns") != 0
        or receipt_control.get("prior_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_M3_ATTEMPT_LEDGER_PATH)
        or any(job.get("status") != "PASS" for job in m3_receipt.get("jobs", {}).values())
        or receipt_public.get("status")
        != "PROTECTED_M3_ZERO_MUTATION_RECONCILIATION_COMPLETED_NOT_FINAL"
        or receipt_public.get("remote_recovery_one_hundred_percent") is not True
        or receipt_public.get("prior_unknown_mutation_reconciled") is not True
        or receipt_public.get("current_run_source_mutation_budget") != 0
        or receipt_public.get("collateral_mutations") != 0
        or receipt_public.get("timeline_publish_attempts") != 0
        or receipt_public.get("exact_mailbox_counts_disclosed") is not False
        or receipt_verification.get("private_repository_head_unchanged") is not True
        or receipt_verification.get("private_repository_tree_unchanged") is not True
        or receipt_verification.get("private_repository_path_counts_unchanged") is not True
        or receipt_verification.get("gmail_trash_aggregate_delta") != 0
        or receipt_verification.get("source_mutations") != 0
        or receipt_verification.get("exact_private_locator_disclosed") is not False
        or receipt_scope.get("t0703_complete") is not True
        or receipt_scope.get("t0704_authorized") is not False
        or receipt_scope.get("further_m3_dispatch_allowed") is not False
        or receipt_claims.get("s7ac_003_passed") is not True
        or receipt_claims.get("stage7_complete") is not False
        or receipt_claims.get("final_acceptance") is not False
    ):
        raise ValueError("protected M3 PASS receipt is not exact or scope-stopped")
    return {
        "schema_version": "moomooau.source-provenance.v15",
        "authorization": {
            "basis": AUTHORIZATION_BASIS,
            "authorized_on": "2026-07-24",
            "authorized_scope": AUTHORIZED_SCOPE,
        },
        "predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-24-V1.0.14",
            "version": "1.0.14",
            "manifest": PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "control_predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.4",
            "version": "1.0.4",
            "manifest": CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": CONTROL_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "foundation_predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.3",
            "version": "1.0.3",
            "manifest": FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": FOUNDATION_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "baseline_predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-22-V1.0.2",
            "version": "1.0.2",
            "manifest": BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix(),
            "manifest_sha256": BASELINE_PREDECESSOR_MANIFEST_SHA256,
            "status": "IMMUTABLE_CONTROL_PREDECESSOR",
        },
        "historical_baseline": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-20-V1.0.1",
            "version": "1.0.1",
            "manifest": LEGACY_MANIFEST_PATH.as_posix(),
            "manifest_sha256": LEGACY_MANIFEST_SHA256,
            "status": "IMMUTABLE_HISTORICAL_BASELINE",
        },
        "inherited_contract_hashes": INHERITED_CONTRACT_HASHES,
        "effective_package": {
            "package_id": PACKAGE_ID,
            "version": PACKAGE_VERSION,
            "manifest": MANIFEST_PATH.as_posix(),
            "roadmap": "taskpack/ROADMAP.v1.0.15.md",
            "status_authority": "machine/status/latest.json",
            "workflow_validator": "machine/tools/validate_workflow_matrix.py",
            "publication_status": "CONTROLLED_T0703_COMPLETED_NOT_FINAL",
        },
        "candidate_snapshot": CANDIDATE_SNAPSHOT,
        "semantic_delta": {
            "governance_visibility_changed": False,
            "dependency_credential_kind": "GITHUB_READ_ONLY_DEPLOY_KEY",
            "dependency_credential_repository_scope": "LinzeColin/Governance",
            "credential_material_in_package": False,
            "production_secret_reads_authorized": 0,
            "project_runtime_secret_reads_authorized": 8,
            "fork_pull_request_policy": ("FAIL_CLOSED_BEFORE_PROTECTED_DEPENDENCY_CHECKOUT"),
            "pull_request_target_allowed": False,
            "product_contract_changed": False,
            "task_graph_changed": False,
            "final_acceptance_thresholds_changed": False,
            "stage7_fixed_calendar_wait_removed": True,
            "protected_oracles_executed": 3,
            "protected_oracles_passed": 3,
            "protected_oracles_failed": 0,
            "production_workflow_runs": 0,
            "protected_workflow_runs": (
                attempt_summary["protected_workflow_runs"] + len(m3_attempts) + 1
            ),
            "remote_workflow_runs": (
                attempt_summary["protected_workflow_runs"] + len(m3_attempts) + 1
            ),
            "controlled_main_deliveries": (
                attempt_summary["controlled_main_deliveries"] + len(m3_attempts) + 1
            ),
            "protected_beta_dispatches": attempt_summary["protected_beta_dispatches"],
            "context_rejected_dispatches": attempt_summary["context_rejected_dispatches"],
            "protected_beta_reruns": attempt_summary["workflow_reruns"],
            "private_raw_commits": "NONZERO_WITHIN_CONFIGURED_BUDGET",
            "private_raw_remote_recovery": "ONE_HUNDRED_PERCENT",
            "private_namespace_blob_state": "NONZERO_AGE_CIPHERTEXT_ONLY",
            "gmail_trash_aggregate_delta": 1,
            "gmail_exact_source_mutation_attribution": (
                "RECONCILED_TO_SOLE_VERIFIED_ALREADY_TRASHED_SOURCE"
            ),
            "m3_runs": 1,
            "processed_writes": "ONE_RECOVERED",
            "timeline_writes": 0,
            "protected_beta_outcome": "PASS_RAW_RECOVERY_100_PERCENT_ZERO_SOURCE_MUTATION",
            "protected_beta_last_failure_phase": "METADATA_VERIFICATION",
            "protected_beta_last_installation_failure_class": "UNCLASSIFIED",
            "protected_beta_exact_root_cause_claimed": False,
            "exact_mailbox_counts_disclosed": False,
            "protected_m3_entrypoint_implemented": True,
            "protected_m3_workflow_enabled_default": True,
            "protected_m3_contract_authorized": False,
            "protected_m3_environment_reused": "moomooau-beta",
            "protected_m3_empty_processing_registries_force_safe_deferred": True,
            "protected_m3_dispatches": 7,
            "protected_m3_reruns": 0,
            "protected_m3_failed_attempts": 6,
            "protected_m3_zero_effect_failures": 5,
            "protected_m3_successful_receipts": 1,
            "protected_m3_current_run_source_mutations": 0,
            "protected_m3_current_run_private_repository_writes": 0,
            "protected_m3_independent_zero_effect_verified": True,
            "protected_m3_last_failure_phase": "PROCESSED_PLAN",
            "protected_m3_last_installation_failure_class": "UNCLASSIFIED",
            "protected_m3_last_aggregate_failure_class": "UNCLASSIFIED",
            "protected_m3_processed_current_before_last_attempt": "ONE",
            "protected_m3_processed_current_after_last_attempt": "ONE",
            "protected_m3_metadata_quarantine_parity_repaired": True,
            "protected_m3_closed_failure_diagnostics": True,
            "protected_m3_installation_failure_class_diagnostics": True,
            "protected_m3_optional_scope_echo_probe": True,
            "protected_m3_server_date_ttl_validation": True,
            "protected_m3_empty_registry_quarantine_safe_deferred_repaired": True,
            "protected_m3_aggregate_failure_class_diagnostics": True,
            "protected_m3_zero_write_reconciliation_implemented": True,
            "protected_m3_historical_label_replay_repaired": True,
            "github_openapi_commit": (
                "5c88ff6bc3c36a12ccd69b8e0fee479b7202188a"  # pragma: allowlist secret
            ),
            "owner_confirmed_github_app_installed_and_repository_linked": True,
            "protected_m3_workflow_sha256": _sha256(
                root.parents[1] / ".github/workflows/moomooau-m3.yml"
            ),
            "m3_authority_status": "CONSUMED_AFTER_PROTECTED_PASS_SCOPE_STOP",
            "protected_beta_attempt_ledger_sha256": _sha256(
                root / PROTECTED_BETA_ATTEMPT_LEDGER_PATH
            ),
            "protected_m3_attempt_ledger_sha256": _sha256(root / PROTECTED_M3_ATTEMPT_LEDGER_PATH),
            "protected_m3_execution_receipt_sha256": _sha256(root / PROTECTED_M3_RECEIPT_PATH),
            "protected_m3_execution_receipt_schema_sha256": _sha256(
                root / PROTECTED_M3_RECEIPT_SCHEMA_PATH
            ),
            "remote_publications": 0,
        },
    }


def _validate_provenance(root: Path, failures: list[str]) -> None:
    try:
        provenance = _load(root / PROVENANCE_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        failures.append("v1.0.15 provenance is missing or invalid")
        return
    if not isinstance(provenance, dict):
        failures.append("v1.0.15 provenance must be an object")
        return
    if provenance != build_provenance(root):
        failures.append("v1.0.15 provenance differs from the exact deterministic authority")
    authorization = provenance.get("authorization", {})
    effective = provenance.get("effective_package", {})
    predecessor = provenance.get("predecessor", {})
    control_predecessor = provenance.get("control_predecessor", {})
    foundation_predecessor = provenance.get("foundation_predecessor", {})
    baseline_predecessor = provenance.get("baseline_predecessor", {})
    historical = provenance.get("historical_baseline", {})
    candidate_snapshot = provenance.get("candidate_snapshot", {})
    semantic_delta = provenance.get("semantic_delta", {})
    if not isinstance(authorization, dict):
        authorization = {}
    if not isinstance(effective, dict):
        effective = {}
    if not isinstance(predecessor, dict):
        predecessor = {}
    if not isinstance(control_predecessor, dict):
        control_predecessor = {}
    if not isinstance(foundation_predecessor, dict):
        foundation_predecessor = {}
    if not isinstance(baseline_predecessor, dict):
        baseline_predecessor = {}
    if not isinstance(historical, dict):
        historical = {}
    if not isinstance(candidate_snapshot, dict):
        candidate_snapshot = {}
    if not isinstance(semantic_delta, dict):
        semantic_delta = {}
    if (
        provenance.get("schema_version") != "moomooau.source-provenance.v15"
        or authorization.get("basis") != AUTHORIZATION_BASIS
        or authorization.get("authorized_scope") != AUTHORIZED_SCOPE
        or effective.get("package_id") != PACKAGE_ID
        or effective.get("version") != PACKAGE_VERSION
        or effective.get("manifest") != MANIFEST_PATH.as_posix()
        or effective.get("roadmap") != "taskpack/ROADMAP.v1.0.15.md"
        or effective.get("status_authority") != "machine/status/latest.json"
        or effective.get("workflow_validator") != "machine/tools/validate_workflow_matrix.py"
        or effective.get("publication_status") != "CONTROLLED_T0703_COMPLETED_NOT_FINAL"
    ):
        failures.append("v1.0.15 provenance identity or authorization mismatch")
    if (
        predecessor.get("manifest") != PREDECESSOR_MANIFEST_PATH.as_posix()
        or predecessor.get("manifest_sha256") != PREDECESSOR_MANIFEST_SHA256
        or predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.14 predecessor provenance mismatch")
    if (
        control_predecessor.get("manifest") != CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix()
        or control_predecessor.get("manifest_sha256") != CONTROL_PREDECESSOR_MANIFEST_SHA256
        or control_predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.4 control predecessor provenance mismatch")
    if (
        foundation_predecessor.get("manifest") != FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix()
        or foundation_predecessor.get("manifest_sha256") != FOUNDATION_PREDECESSOR_MANIFEST_SHA256
        or foundation_predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.3 foundation predecessor provenance mismatch")
    if (
        baseline_predecessor.get("manifest") != BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix()
        or baseline_predecessor.get("manifest_sha256") != BASELINE_PREDECESSOR_MANIFEST_SHA256
        or baseline_predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.2 baseline predecessor provenance mismatch")
    if (
        historical.get("manifest") != LEGACY_MANIFEST_PATH.as_posix()
        or historical.get("manifest_sha256") != LEGACY_MANIFEST_SHA256
        or historical.get("status") != "IMMUTABLE_HISTORICAL_BASELINE"
    ):
        failures.append("v1.0.1 historical provenance mismatch")
    if provenance.get("inherited_contract_hashes") != INHERITED_CONTRACT_HASHES:
        failures.append("inherited contract provenance mismatch")
    if candidate_snapshot != CANDIDATE_SNAPSHOT:
        failures.append("RMD-06 clean candidate snapshot provenance mismatch")
    expected_semantic_delta = build_provenance(root)["semantic_delta"]
    if semantic_delta != expected_semantic_delta:
        failures.append("v1.0.15 semantic delta is incomplete or overstated")


def validate(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / MANIFEST_PATH
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {"status": "FAIL", "verified_files": 0, "failures": ["manifest missing or unsafe"]}
    try:
        manifest = _load(manifest_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "verified_files": 0,
            "failures": [f"manifest is not valid readable JSON: {type(exc).__name__}"],
        }
    if not isinstance(manifest, dict):
        return {
            "status": "FAIL",
            "verified_files": 0,
            "failures": ["manifest root must be an object"],
        }

    failures: list[str] = []
    seen: set[str] = set()
    entries = manifest.get("files", [])
    if not isinstance(entries, list):
        entries = []
        failures.append("manifest files must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append("manifest entry must be an object")
            continue
        relative = entry.get("path", "")
        if not isinstance(relative, str) or not relative:
            failures.append("manifest path is invalid")
            continue
        if relative in seen:
            failures.append("duplicate manifest path")
            continue
        seen.add(relative)
        candidate = root / relative
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError:
            failures.append("manifest path escapes project root")
            continue
        if not path.is_file() or candidate.is_symlink():
            failures.append(f"missing or unsafe file: {relative}")
            continue
        if path.stat().st_size != entry.get("bytes") or _sha256(path) != entry.get("sha256"):
            failures.append(f"byte mismatch: {relative}")

    if manifest.get("package_id") != PACKAGE_ID or manifest.get("version") != PACKAGE_VERSION:
        failures.append("manifest package identity mismatch")
    if manifest.get("file_count_excluding_manifest") != len(entries):
        failures.append("manifest count mismatch")
    if MANIFEST_PATH.as_posix() in seen:
        failures.append("manifest must not hash itself")
    legacy_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("path") == LEGACY_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if legacy_entry is None or legacy_entry.get("sha256") != LEGACY_MANIFEST_SHA256:
        failures.append("legacy v1.0.1 manifest artifact is not preserved")
    predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("path") == PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if predecessor_entry is None or predecessor_entry.get("sha256") != PREDECESSOR_MANIFEST_SHA256:
        failures.append("predecessor v1.0.14 manifest artifact is not preserved")
    control_predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("path") == CONTROL_PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if (
        control_predecessor_entry is None
        or control_predecessor_entry.get("sha256") != CONTROL_PREDECESSOR_MANIFEST_SHA256
    ):
        failures.append("control predecessor v1.0.4 manifest artifact is not preserved")
    foundation_predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("path") == FOUNDATION_PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if (
        foundation_predecessor_entry is None
        or foundation_predecessor_entry.get("sha256") != FOUNDATION_PREDECESSOR_MANIFEST_SHA256
    ):
        failures.append("foundation predecessor v1.0.3 manifest artifact is not preserved")
    baseline_predecessor_entry = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("path") == BASELINE_PREDECESSOR_MANIFEST_PATH.as_posix()
        ),
        None,
    )
    if (
        baseline_predecessor_entry is None
        or baseline_predecessor_entry.get("sha256") != BASELINE_PREDECESSOR_MANIFEST_SHA256
    ):
        failures.append("baseline predecessor v1.0.2 manifest artifact is not preserved")
    for relative, expected in INHERITED_CONTRACT_HASHES.items():
        entry = next(
            (item for item in entries if isinstance(item, dict) and item.get("path") == relative),
            None,
        )
        if entry is None or entry.get("sha256") != expected:
            failures.append(f"inherited contract is not preserved: {relative}")

    try:
        expected = build_manifest(root)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        failures.append(f"canonical manifest selection failed: {type(exc).__name__}")
    else:
        if manifest != expected:
            failures.append("manifest differs from the canonical v1.0.15 package selection")

    _validate_provenance(root, failures)
    status_result = validate_delivery_status(root)
    if status_result["status"] != "PASS":
        failures.append("sole delivery status authority failed validation")
    return {
        "status": "PASS" if not failures else "FAIL",
        "package_id": manifest.get("package_id"),
        "version": manifest.get("version"),
        "verified_files": len(seen),
        "legacy_manifest_sha256": LEGACY_MANIFEST_SHA256,
        "status_authority": manifest.get("status_authority"),
        "production_ready": status_result.get("production_readiness") == "PASS",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = validate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
