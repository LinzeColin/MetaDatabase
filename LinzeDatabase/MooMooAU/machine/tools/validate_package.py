#!/usr/bin/env python3
"""Read-only validator for the v1.0.23 protected T0705 GA phase-diagnostic package."""

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
PROVENANCE_PATH = Path("taskpack/SOURCE_PROVENANCE.v1.0.23.json")
CURRENT_MAINLINE_BASE_COMMIT = (
    "4c207ad539754166fae6642ff4e6850438d3e2fc"  # pragma: allowlist secret
)
ACCEPTANCE_REMEDIATION_BASE_COMMIT = (
    "4c207ad539754166fae6642ff4e6850438d3e2fc"  # pragma: allowlist secret
)
T0704_PASS_MAIN_COMMIT = "65cef09935475ab578d28a61817cc92700d6da04"  # pragma: allowlist secret
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
PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0704/attempt-ledger.json"
)
PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-blue-green-attempt-ledger-v1.schema.json"
)
PROTECTED_BLUE_GREEN_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0704/execution-receipt.json")
PROTECTED_BLUE_GREEN_RECEIPT_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-blue-green-execution-receipt-v1.schema.json"
)
PROTECTED_GA_ATTEMPT_LEDGER_PATH = Path("machine/stages/S7/reviews/t0705/attempt-ledger.json")
PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/repair-attempt-ledger.json"
)
PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-repair-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/label-replay-attempt-ledger.json"
)
PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-label-replay-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/post-processed-attempt-ledger.json"
)
PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-post-processed-attempt-ledger-v1.schema.json"
)
T0705_RUN_CONTRACT_PATH = Path("machine/stages/S7/contracts/run_contract.json")
AUTHORIZATION_BASIS = (
    "The exact protected T0702, T0703 and T0704 PASS receipts, all four immutable T0705 "
    "failed-attempt ledgers, owner no-time-gate direction and one-task successor Run Contract "
    "freeze all four failed heads and authorize exactly one new T0705 exact-main closed-enum "
    "phase-diagnostic schedule-mode "
    "rehearsal without authorizing T0706 or final publication"
)
AUTHORIZED_SCOPE = (
    "One T0705 closed-enum phase-diagnostic candidate: never rerun or redispatch failed heads "
    "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f, "
    "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0 or "
    "cc7c8af9a40122a61ee2549fb365df813cbd4f16 or "
    "4c207ad539754166fae6642ff4e6850438d3e2fc. Record only the last entered closed operation "
    "phase without receiving or inspecting an exception or protected value, while preserving "
    "persisted first-import timestamp and label-state replay plus pre-Raw metadata "
    "quarantine, prior pending refs, fail-closed second verification, ACTIVE processing and "
    "paired-empty SAFE_DEFERRED. Bind all protected predecessor receipts and all four failed "
    "ledgers, reuse the existing "
    "eight-name moomooau-beta Environment and installed GitHub App, refresh live "
    "private-repository capacity before Gmail exchange, then allow one new attempt-1 "
    "workflow_dispatch SCHEDULE_REHEARSAL with rerun zero. Verified-only Raw and Processed remote "
    "recovery precede "
    "exact-message Trash budget one; Timeline and checkpoint recovery are mandatory. Enable only "
    "the committed 04:30 Australia/Sydney schedule after PASS and stop before T0706"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_provenance(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Return the exact RMD-06 and protected T0705 phase-diagnostic authority."""

    root = root.resolve()
    attempt_ledger = _load(root / PROTECTED_BETA_ATTEMPT_LEDGER_PATH)
    attempt_summary = attempt_ledger.get("summary", {})
    m3_ledger = _load(root / PROTECTED_M3_ATTEMPT_LEDGER_PATH)
    m3_attempts = m3_ledger.get("attempts", [])
    m3_policy = m3_ledger.get("completion_policy", {})
    m3_receipt = _load(root / PROTECTED_M3_RECEIPT_PATH)
    m3_receipt_schema = _load(root / PROTECTED_M3_RECEIPT_SCHEMA_PATH)
    blue_green_ledger = _load(root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_PATH)
    blue_green_schema = _load(root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA_PATH)
    blue_green_receipt = _load(root / PROTECTED_BLUE_GREEN_RECEIPT_PATH)
    blue_green_receipt_schema = _load(root / PROTECTED_BLUE_GREEN_RECEIPT_SCHEMA_PATH)
    ga_ledger = _load(root / PROTECTED_GA_ATTEMPT_LEDGER_PATH)
    ga_ledger_schema = _load(root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH)
    ga_repair_ledger = _load(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_PATH)
    ga_repair_ledger_schema = _load(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA_PATH)
    ga_label_replay_ledger = _load(root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_PATH)
    ga_label_replay_ledger_schema = _load(
        root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_post_processed_ledger = _load(root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_PATH)
    ga_post_processed_ledger_schema = _load(
        root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    t0705_contract = _load(root / T0705_RUN_CONTRACT_PATH)
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
        or receipt_control.get("merge_commit_sha")
        != "83fec6161d5cd80c62f3553d6332c0113ef5a514"  # pragma: allowlist secret
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
    blue_green_errors = list(
        Draft202012Validator(
            blue_green_schema,
            format_checker=FormatChecker(),
        ).iter_errors(blue_green_ledger)
    )
    blue_green_attempts = blue_green_ledger.get("attempts", [])
    blue_green_attempt = (
        blue_green_attempts[0]
        if isinstance(blue_green_attempts, list) and len(blue_green_attempts) == 1
        else {}
    )
    blue_green_delivery = blue_green_attempt.get("delivery", {})
    blue_green_workflow = blue_green_attempt.get("workflow", {})
    blue_green_jobs = blue_green_attempt.get("jobs", {})
    blue_green_effects = blue_green_attempt.get("effects", {})
    blue_green_diagnosis = blue_green_attempt.get("diagnosis", {})
    blue_green_policy = blue_green_ledger.get("completion_policy", {})
    blue_green_claims = blue_green_ledger.get("claims", {})
    if (
        blue_green_errors
        or blue_green_ledger.get("task_id") != "T0704"
        or blue_green_delivery.get("pull_request_number") != 112
        or blue_green_delivery.get("merge_commit_sha")
        != "b3ff184bd9a7f0e66a7fde6cd6656f11dd982177"  # pragma: allowlist secret
        or blue_green_workflow.get("run_id") != 30175241669
        or blue_green_workflow.get("workflow_head_sha")
        != "b3ff184bd9a7f0e66a7fde6cd6656f11dd982177"  # pragma: allowlist secret
        or blue_green_workflow.get("run_attempt") != 1
        or blue_green_workflow.get("reruns") != 0
        or blue_green_jobs.get("authority_gate", {}).get("status") != "PASS"
        or blue_green_jobs.get("blue_green_shadow_and_timeline", {}).get("status") != "FAILED"
        or blue_green_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or blue_green_effects.get("private_repository_new_commits") != 5
        or blue_green_effects.get("raw_ciphertext_creations") != 0
        or blue_green_effects.get("candidate_processed_shadow_objects") != 2
        or blue_green_effects.get("timeline_snapshot_objects") != 2
        or blue_green_effects.get("encrypted_timeline_state_objects") != 1
        or blue_green_effects.get("processed_current_path_and_blob_identity") is not True
        or blue_green_effects.get("live_timeline_assets_after_dispatch") != 0
        or blue_green_effects.get("scheduled_runs") != 0
        or blue_green_effects.get("ga_runs") != 0
        or blue_green_diagnosis.get("high_confidence_defect")
        != "GITHUB_RELEASE_ASSET_302_RECOVERY_NOT_SUPPORTED"
        or blue_green_policy.get("same_head_rerun_allowed") is not False
        or blue_green_policy.get("failed_head_redispatch_allowed") is not False
        or blue_green_policy.get("new_reviewed_repair_candidate_allowed") is not True
        or blue_green_policy.get("next_candidate_dispatch_limit") != 1
        or blue_green_policy.get("t0704_complete") is not False
        or blue_green_policy.get("t0705_authorized") is not False
        or any(value is not False for value in blue_green_claims.values())
    ):
        raise ValueError("protected T0704 failed attempt ledger is not exact or frozen")
    blue_green_receipt_errors = list(
        Draft202012Validator(
            blue_green_receipt_schema,
            format_checker=FormatChecker(),
        ).iter_errors(blue_green_receipt)
    )
    blue_green_receipt_control = blue_green_receipt.get("control", {})
    blue_green_receipt_jobs = blue_green_receipt.get("jobs", {})
    blue_green_receipt_public = blue_green_receipt.get("public_result", {})
    blue_green_receipt_verification = blue_green_receipt.get(
        "independent_post_run_verification", {}
    )
    blue_green_receipt_scope = blue_green_receipt.get("scope_decision", {})
    blue_green_receipt_claims = blue_green_receipt.get("claims", {})
    if (
        blue_green_receipt_errors
        or blue_green_receipt.get("task_id") != "T0704"
        or blue_green_receipt.get("observed_at_utc") != "2026-07-25T22:52:22Z"
        or blue_green_receipt_control.get("pull_request_number") != 113
        or blue_green_receipt_control.get("merge_commit_sha") != T0704_PASS_MAIN_COMMIT
        or blue_green_receipt_control.get("workflow_run_id") != 30178201201
        or blue_green_receipt_control.get("workflow_head_sha")
        != blue_green_receipt_control.get("merge_commit_sha")
        or blue_green_receipt_control.get("workflow_attempt") != 1
        or blue_green_receipt_control.get("dispatches_for_head") != 1
        or blue_green_receipt_control.get("reruns") != 0
        or blue_green_receipt_control.get("prior_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_PATH)
        or blue_green_receipt_control.get("prior_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA_PATH)
        or blue_green_receipt_control.get("m3_receipt_sha256")
        != _sha256(root / PROTECTED_M3_RECEIPT_PATH)
        or any(job.get("status") != "PASS" for job in blue_green_receipt_jobs.values())
        or blue_green_receipt_public.get("status") != "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL"
        or blue_green_receipt_public.get("blue_green_gate_status") != "PASS"
        or blue_green_receipt_public.get("processed_recoveries") != 1
        or blue_green_receipt_public.get("parser_comparisons") != 1
        or blue_green_receipt_public.get("current_pointer_mutations") != 0
        or blue_green_receipt_public.get("timeline_snapshot_recoveries") != 1
        or blue_green_receipt_public.get("timeline_publish_attempts") != 1
        or blue_green_receipt_public.get("minimum_live_timeline_assets") != 1
        or blue_green_receipt_public.get("maximum_live_timeline_assets") != 1
        or blue_green_receipt_public.get("full_reconcile_difference") != 0
        or blue_green_receipt_public.get("gmail_mutations") != 0
        or blue_green_receipt_public.get("unresolved_comparison_differences") != 0
        or blue_green_receipt_public.get("remote_timeline_recovery_one_hundred_percent") is not True
        or blue_green_receipt_public.get("exact_mailbox_counts_disclosed") is not False
        or blue_green_receipt_verification.get("private_repository_tree_complete") is not True
        or blue_green_receipt_verification.get("private_repository_tree_truncated") is not False
        or blue_green_receipt_verification.get("moomooau_namespace_new_commits") != 1
        or blue_green_receipt_verification.get("other_namespace_activity_excluded") is not True
        or blue_green_receipt_verification.get("changed_files_in_repair_commit") != 1
        or blue_green_receipt_verification.get("encrypted_timeline_state_writes") != 1
        or blue_green_receipt_verification.get("raw_tree_unchanged") is not True
        or blue_green_receipt_verification.get("processed_tree_unchanged") is not True
        or blue_green_receipt_verification.get("candidate_processed_shadow_writes") != 0
        or blue_green_receipt_verification.get("timeline_snapshot_writes") != 0
        or blue_green_receipt_verification.get("processed_current_path_and_blob_identity")
        is not True
        or blue_green_receipt_verification.get("live_timeline_assets") != 1
        or blue_green_receipt_verification.get("live_asset_age_envelope") is not True
        or blue_green_receipt_verification.get("live_asset_download_recovered") is not True
        or blue_green_receipt_verification.get("independent_asset_decryption_claimed") is not False
        or blue_green_receipt_verification.get("source_mutations") != 0
        or blue_green_receipt_verification.get("exact_private_locator_disclosed") is not False
        or blue_green_receipt_scope.get("t0704_complete") is not True
        or blue_green_receipt_scope.get("t0705_authorized") is not False
        or blue_green_receipt_scope.get("further_blue_green_dispatch_allowed") is not False
        or blue_green_receipt_claims.get("s7ac_004_passed") is not True
        or blue_green_receipt_claims.get("t0705_complete") is not False
        or blue_green_receipt_claims.get("stage7_complete") is not False
        or blue_green_receipt_claims.get("final_acceptance") is not False
    ):
        raise ValueError("protected T0704 PASS receipt is not exact or scope-stopped")
    ga_ledger_errors = list(
        Draft202012Validator(
            ga_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_ledger)
    )
    ga_attempts = ga_ledger.get("attempts", [])
    ga_attempt = ga_attempts[0] if isinstance(ga_attempts, list) and len(ga_attempts) == 1 else {}
    ga_delivery = ga_attempt.get("delivery", {})
    ga_workflow = ga_attempt.get("workflow", {})
    ga_jobs = ga_attempt.get("jobs", {})
    ga_failure = ga_attempt.get("public_failure", {})
    ga_effects = ga_attempt.get("effects", {})
    ga_diagnosis = ga_attempt.get("diagnosis", {})
    ga_policy = ga_ledger.get("completion_policy", {})
    ga_claims = ga_ledger.get("claims", {})
    if (
        ga_ledger_errors
        or ga_ledger.get("task_id") != "T0705"
        or ga_delivery.get("pull_request_number") != 115
        or ga_delivery.get("merge_commit_sha")
        != "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f"  # pragma: allowlist secret
        or ga_delivery.get("terminal_checks") != 39
        or ga_delivery.get("successful_checks") != 22
        or ga_delivery.get("failed_checks") != 11
        or ga_delivery.get("skipped_checks") != 5
        or ga_delivery.get("neutral_checks") != 1
        or ga_workflow.get("run_id") != 30182491342
        or ga_workflow.get("workflow_id") != 318812500
        or ga_workflow.get("event") != "workflow_dispatch"
        or ga_workflow.get("workflow_head_sha")
        != "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f"  # pragma: allowlist secret
        or ga_workflow.get("run_attempt") != 1
        or ga_workflow.get("reruns") != 0
        or ga_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_failure.get("reason_code") != "PROTECTED_GA_FAILED"
        or ga_failure.get("exact_root_cause_claimed") is not False
        or ga_failure.get("protected_values_disclosed") is not False
        or ga_failure.get("platform_schedule_event_claimed") is not False
        or ga_failure.get("production_health_claimed") is not False
        or ga_failure.get("final_acceptance_claimed") is not False
        or ga_effects.get("private_repository_new_commits") != 0
        or ga_effects.get("raw_path_changes") != 0
        or ga_effects.get("processed_path_changes") != 0
        or ga_effects.get("state_path_changes") != 0
        or ga_effects.get("other_path_changes") != 0
        or ga_effects.get("gmail_checkpoint_exists_after_dispatch") is not False
        or ga_effects.get("timeline_state_exists_after_dispatch") is not True
        or ga_effects.get("live_timeline_assets_before_dispatch") != 1
        or ga_effects.get("live_timeline_assets_after_dispatch") != 1
        or ga_effects.get("canonical_live_timeline_assets_after_dispatch") != 1
        or ga_effects.get("gmail_mutation_api_reachable") is not False
        or ga_effects.get("platform_schedule_events") != 0
        or ga_effects.get("identity_plaintext_cleanup") != "PASS"
        or ga_effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
        or ga_effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
        or ga_diagnosis.get("observable_failure_boundary")
        != "BEFORE_GMAIL_CREDENTIAL_EXCHANGE_OR_DATA_PLANE_WRITE"
        or ga_diagnosis.get("exact_runtime_exception") != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
        or ga_diagnosis.get("high_confidence_defect")
        != "GA_REJECTED_PAIRED_SAFE_DEFERRED_REGISTRIES"
        or ga_policy.get("same_head_rerun_allowed") is not False
        or ga_policy.get("failed_head_redispatch_allowed") is not False
        or ga_policy.get("new_reviewed_repair_candidate_allowed") is not True
        or ga_policy.get("next_candidate_dispatch_limit") != 1
        or ga_policy.get("t0705_complete") is not False
        or ga_policy.get("t0706_authorized") is not False
        or ga_policy.get("final_publication_authorized") is not False
        or any(value is not False for value in ga_claims.values())
    ):
        raise ValueError("protected T0705 failed attempt ledger is not exact or frozen")
    ga_repair_errors = list(
        Draft202012Validator(
            ga_repair_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_repair_ledger)
    )
    ga_repair_attempts = ga_repair_ledger.get("attempts", [])
    ga_repair_attempt = (
        ga_repair_attempts[0]
        if isinstance(ga_repair_attempts, list) and len(ga_repair_attempts) == 1
        else {}
    )
    ga_repair_predecessor = ga_repair_ledger.get("predecessor_control", {})
    ga_repair_delivery = ga_repair_attempt.get("delivery", {})
    ga_repair_workflow = ga_repair_attempt.get("workflow", {})
    ga_repair_jobs = ga_repair_attempt.get("jobs", {})
    ga_repair_effects = ga_repair_attempt.get("effects", {})
    ga_repair_diagnosis = ga_repair_attempt.get("diagnosis", {})
    ga_repair_policy = ga_repair_ledger.get("completion_policy", {})
    ga_repair_claims = ga_repair_ledger.get("claims", {})
    if (
        ga_repair_errors
        or ga_repair_predecessor.get("prior_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_PATH)
        or ga_repair_predecessor.get("prior_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH)
        or ga_repair_attempt.get("sequence") != 2
        or ga_repair_delivery.get("pull_request_number") != 116
        or ga_repair_delivery.get("merge_commit_sha")
        != "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0"  # pragma: allowlist secret
        or ga_repair_delivery.get("merge_commit_sha") != ga_repair_workflow.get("workflow_head_sha")
        or ga_repair_delivery.get("terminal_checks") != 23
        or ga_repair_delivery.get("successful_checks") != 23
        or any(
            ga_repair_delivery.get(key) != 0
            for key in ("failed_checks", "skipped_checks", "neutral_checks")
        )
        or ga_repair_workflow.get("run_id") != 30184702520
        or ga_repair_workflow.get("workflow_id") != 318812500
        or ga_repair_workflow.get("event") != "workflow_dispatch"
        or ga_repair_workflow.get("run_attempt") != 1
        or ga_repair_workflow.get("reruns") != 0
        or ga_repair_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_repair_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_repair_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_repair_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_repair_effects.get("private_repository_new_commits_since_dispatch") != 0
        or any(
            ga_repair_effects.get(key) != 0
            for key in (
                "raw_path_changes",
                "processed_path_changes",
                "state_path_changes",
                "other_path_changes",
                "platform_schedule_events",
            )
        )
        or ga_repair_effects.get("gmail_checkpoint_exists_after_dispatch") is not False
        or ga_repair_effects.get("timeline_state_exists_after_dispatch") is not True
        or ga_repair_effects.get("live_timeline_assets_after_dispatch") != 1
        or ga_repair_effects.get("gmail_mutation_api_reached") is not False
        or ga_repair_effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
        or ga_repair_effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
        or ga_repair_diagnosis.get("exact_runtime_exception") != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
        or ga_repair_diagnosis.get("high_confidence_defect")
        != "GA_DID_NOT_QUARANTINE_MESSAGE_METADATA_UNVERIFIABLE"
        or ga_repair_policy.get("same_head_rerun_allowed") is not False
        or ga_repair_policy.get("failed_head_redispatch_allowed") is not False
        or ga_repair_policy.get("new_reviewed_metadata_quarantine_repair_candidate_allowed")
        is not True
        or ga_repair_policy.get("next_candidate_dispatch_limit") != 1
        or ga_repair_policy.get("historical_ga_rehearsal_dispatches_consumed") != 2
        or ga_repair_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_repair_policy.get("t0705_complete") is not False
        or ga_repair_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_repair_claims.values())
    ):
        raise ValueError("protected T0705 repair attempt ledger is not exact or frozen")
    ga_label_replay_errors = list(
        Draft202012Validator(
            ga_label_replay_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_label_replay_ledger)
    )
    ga_label_replay_attempts = ga_label_replay_ledger.get("attempts", [])
    ga_label_replay_attempt = (
        ga_label_replay_attempts[0]
        if isinstance(ga_label_replay_attempts, list) and len(ga_label_replay_attempts) == 1
        else {}
    )
    ga_label_replay_predecessor = ga_label_replay_ledger.get("predecessor_control", {})
    ga_label_replay_delivery = ga_label_replay_attempt.get("delivery", {})
    ga_label_replay_workflow = ga_label_replay_attempt.get("workflow", {})
    ga_label_replay_jobs = ga_label_replay_attempt.get("jobs", {})
    ga_label_replay_effects = ga_label_replay_attempt.get("effects", {})
    ga_label_replay_diagnosis = ga_label_replay_attempt.get("diagnosis", {})
    ga_label_replay_policy = ga_label_replay_ledger.get("completion_policy", {})
    ga_label_replay_claims = ga_label_replay_ledger.get("claims", {})
    if (
        ga_label_replay_errors
        or ga_label_replay_predecessor.get("prior_run_contract_sha256")
        != "db60c9347010467684f618be12386829782f8b1d64335bd5120727ece8252407"  # pragma: allowlist secret  # noqa: E501
        or ga_label_replay_predecessor.get("first_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_PATH)
        or ga_label_replay_predecessor.get("first_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH)
        or ga_label_replay_predecessor.get("second_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_PATH)
        or ga_label_replay_predecessor.get("second_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA_PATH)
        or ga_label_replay_attempt.get("sequence") != 3
        or ga_label_replay_delivery.get("pull_request_number") != 117
        or ga_label_replay_delivery.get("merge_commit_sha")
        != "cc7c8af9a40122a61ee2549fb365df813cbd4f16"  # pragma: allowlist secret
        or ga_label_replay_delivery.get("merge_commit_sha")
        != ga_label_replay_workflow.get("workflow_head_sha")
        or ga_label_replay_delivery.get("terminal_checks") != 40
        or ga_label_replay_delivery.get("successful_checks") != 35
        or ga_label_replay_delivery.get("failed_checks") != 0
        or ga_label_replay_delivery.get("skipped_checks") != 5
        or ga_label_replay_delivery.get("neutral_checks") != 0
        or ga_label_replay_workflow.get("run_id") != 30187132406
        or ga_label_replay_workflow.get("workflow_id") != 318812500
        or ga_label_replay_workflow.get("event") != "workflow_dispatch"
        or ga_label_replay_workflow.get("run_attempt") != 1
        or ga_label_replay_workflow.get("reruns") != 0
        or ga_label_replay_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_label_replay_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_label_replay_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_label_replay_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_label_replay_effects.get("private_repository_new_commits_since_dispatch") != 0
        or ga_label_replay_effects.get("private_repository_path_aggregate_change")
        != "UNCHANGED_BECAUSE_ZERO_NEW_COMMITS"
        or ga_label_replay_effects.get("gmail_checkpoint_exists_after_dispatch") is not False
        or ga_label_replay_effects.get("timeline_state_exists_after_dispatch") is not True
        or ga_label_replay_effects.get("active_moomoo_candidate_outside_trash_after_dispatch")
        is not True
        or ga_label_replay_effects.get("gmail_mutation_api_reached")
        != "NOT_CLAIMED_WITHOUT_PROTECTED_TRACE"
        or ga_label_replay_effects.get("timeline_release_asset_independent_remeasurement")
        != "NOT_PERFORMED"
        or ga_label_replay_effects.get("platform_schedule_events") != 0
        or ga_label_replay_effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
        or ga_label_replay_effects.get("production_enablement_variable_after_dispatch") != "ABSENT"
        or ga_label_replay_diagnosis.get("exact_runtime_exception")
        != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
        or ga_label_replay_diagnosis.get("high_confidence_defect")
        != "GA_DID_NOT_REPLAY_PERSISTED_FIRST_IMPORT_LABEL_STATE"
        or ga_label_replay_policy.get("same_head_rerun_allowed") is not False
        or ga_label_replay_policy.get("failed_head_redispatch_allowed") is not False
        or ga_label_replay_policy.get("new_reviewed_label_replay_repair_candidate_allowed")
        is not True
        or ga_label_replay_policy.get("next_candidate_dispatch_limit") != 1
        or ga_label_replay_policy.get("historical_ga_rehearsal_dispatches_consumed") != 3
        or ga_label_replay_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_label_replay_policy.get("t0705_complete") is not False
        or ga_label_replay_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_label_replay_claims.values())
    ):
        raise ValueError("protected T0705 label-replay attempt ledger is not exact or frozen")

    ga_post_processed_errors = list(
        Draft202012Validator(
            ga_post_processed_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_post_processed_ledger)
    )
    ga_post_processed_attempts = ga_post_processed_ledger.get("attempts", [])
    ga_post_processed_attempt = (
        ga_post_processed_attempts[0]
        if isinstance(ga_post_processed_attempts, list) and len(ga_post_processed_attempts) == 1
        else {}
    )
    ga_post_processed_predecessor = ga_post_processed_ledger.get("predecessor_control", {})
    ga_post_processed_delivery = ga_post_processed_attempt.get("delivery", {})
    ga_post_processed_workflow = ga_post_processed_attempt.get("workflow", {})
    ga_post_processed_jobs = ga_post_processed_attempt.get("jobs", {})
    ga_post_processed_public_failure = ga_post_processed_attempt.get("public_failure", {})
    ga_post_processed_effects = ga_post_processed_attempt.get("effects", {})
    ga_post_processed_diagnosis = ga_post_processed_attempt.get("diagnosis", {})
    ga_post_processed_policy = ga_post_processed_ledger.get("completion_policy", {})
    ga_post_processed_claims = ga_post_processed_ledger.get("claims", {})
    if (
        ga_post_processed_errors
        or ga_post_processed_predecessor.get("prior_run_contract_sha256")
        != "6892f0812f4e050b4e16cef44e47e3387060c950339f0df654f2a2b214d3daf6"  # pragma: allowlist secret  # noqa: E501
        or ga_post_processed_predecessor.get("first_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_PATH)
        or ga_post_processed_predecessor.get("first_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH)
        or ga_post_processed_predecessor.get("second_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_PATH)
        or ga_post_processed_predecessor.get("second_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA_PATH)
        or ga_post_processed_predecessor.get("third_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_PATH)
        or ga_post_processed_predecessor.get("third_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_PATH)
        or ga_post_processed_attempt.get("sequence") != 4
        or ga_post_processed_delivery.get("pull_request_number") != 118
        or ga_post_processed_delivery.get("pull_request_head_sha")
        != "5693dbf09c472046530f4ff3bb23ed425deccf34"  # pragma: allowlist secret
        or ga_post_processed_delivery.get("merge_commit_parent_sha")
        != "cc7c8af9a40122a61ee2549fb365df813cbd4f16"  # pragma: allowlist secret
        or ga_post_processed_delivery.get("merge_commit_sha") != CURRENT_MAINLINE_BASE_COMMIT
        or ga_post_processed_delivery.get("merge_commit_sha")
        != ga_post_processed_workflow.get("workflow_head_sha")
        or ga_post_processed_delivery.get("terminal_checks") != 23
        or ga_post_processed_delivery.get("successful_checks") != 23
        or any(
            ga_post_processed_delivery.get(key) != 0
            for key in ("failed_checks", "skipped_checks", "neutral_checks")
        )
        or ga_post_processed_workflow.get("run_id") != 30189278592
        or ga_post_processed_workflow.get("workflow_id") != 318812500
        or ga_post_processed_workflow.get("event") != "workflow_dispatch"
        or ga_post_processed_workflow.get("run_attempt") != 1
        or ga_post_processed_workflow.get("reruns") != 0
        or ga_post_processed_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_post_processed_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_post_processed_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_post_processed_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_post_processed_public_failure.get("reason_code") != "PROTECTED_GA_FAILED"
        or ga_post_processed_public_failure.get("exact_root_cause_claimed") is not False
        or ga_post_processed_effects.get("private_repository_new_commits_during_attempt") != 6
        or ga_post_processed_effects.get("private_repository_added_encrypted_paths") != 6
        or ga_post_processed_effects.get("private_repository_modified_paths") != 0
        or ga_post_processed_effects.get("private_repository_removed_paths") != 0
        or ga_post_processed_effects.get("raw_content_paths_added") != 2
        or ga_post_processed_effects.get("raw_manifest_paths_added") != 1
        or ga_post_processed_effects.get("processed_content_paths_added") != 1
        or ga_post_processed_effects.get("processed_manifest_paths_added") != 1
        or ga_post_processed_effects.get("processed_current_pointer_paths_added") != 1
        or ga_post_processed_effects.get("timeline_snapshot_or_manifest_paths_changed") != 0
        or ga_post_processed_effects.get("timeline_state_paths_changed") != 0
        or ga_post_processed_effects.get("gmail_checkpoint_paths_changed") != 0
        or ga_post_processed_effects.get("added_paths_with_age_magic") != 6
        or ga_post_processed_effects.get("added_paths_without_age_magic") != 0
        or ga_post_processed_effects.get("gmail_checkpoint_exists_after_dispatch") is not False
        or ga_post_processed_effects.get("timeline_state_exists_after_dispatch") is not True
        or ga_post_processed_effects.get("live_timeline_assets_after_dispatch") != 1
        or ga_post_processed_effects.get("active_moomoo_candidate_outside_trash_after_dispatch")
        is not True
        or ga_post_processed_effects.get("gmail_mutation_api_reached")
        != "NOT_CLAIMED_WITHOUT_PROTECTED_TRACE"
        or ga_post_processed_effects.get("gmail_mutation_independent_remeasurement")
        != "NOT_CLAIMED_WITHOUT_EXACT_PRE_DISPATCH_BASELINE"
        or ga_post_processed_effects.get("platform_schedule_events") != 0
        or ga_post_processed_effects.get("identity_plaintext_cleanup") != "PASS"
        or ga_post_processed_effects.get("one_shot_authority_variable_after_dispatch") != "ABSENT"
        or ga_post_processed_effects.get("production_enablement_variable_after_dispatch")
        != "ABSENT"
        or ga_post_processed_diagnosis.get("observable_failure_boundary")
        != (
            "AFTER_SIX_ENCRYPTED_RAW_PROCESSED_CURRENT_ADDITIONS_"
            "BEFORE_TIMELINE_SNAPSHOT_OR_CHECKPOINT"
        )
        or ga_post_processed_diagnosis.get("exact_runtime_exception")
        != "NOT_DISCLOSED_BY_PROTECTED_OUTPUT"
        or ga_post_processed_diagnosis.get("exact_root_cause_claimed") is not False
        or ga_post_processed_diagnosis.get("safe_next_diagnostic")
        != "CLOSED_ENUM_LAST_ENTERED_GA_PHASE_ONLY"
        or ga_post_processed_policy.get("same_head_rerun_allowed") is not False
        or ga_post_processed_policy.get("failed_head_redispatch_allowed") is not False
        or ga_post_processed_policy.get("new_reviewed_phase_diagnostic_candidate_allowed")
        is not True
        or ga_post_processed_policy.get("next_candidate_dispatch_limit") != 1
        or ga_post_processed_policy.get("historical_ga_rehearsal_dispatches_consumed") != 4
        or ga_post_processed_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_post_processed_policy.get("t0705_complete") is not False
        or ga_post_processed_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_post_processed_claims.values())
    ):
        raise ValueError("protected T0705 post-Processed attempt ledger is not exact or frozen")

    t0705_authorization = t0705_contract.get("authorization", {})
    t0705_budget = t0705_contract.get("authorized_effect_budget", {})
    if (
        t0705_contract.get("schema_version") != "moomooau.run-contract.v1"
        or t0705_contract.get("stage_id") != "S7"
        or t0705_contract.get("task_id") != "T0705"
        or t0705_contract.get("baseline_commit") != CURRENT_MAINLINE_BASE_COMMIT
        or t0705_contract.get("baseline_manifest_sha256") != PREDECESSOR_MANIFEST_SHA256
        or t0705_authorization.get("purpose")
        != "T0705_PROTECTED_GA_PHASE_DIAGNOSTIC_RECOVERY_AND_ENABLEMENT_ONLY"
        or t0705_authorization.get("original_run_contract_sha256")
        != "1c94dfdce8b5809718e2772d422bb6db773f8b9899ad9e719b0ffda11d0053b9"  # pragma: allowlist secret  # noqa: E501
        or t0705_authorization.get("prior_run_contract_sha256")
        != "6892f0812f4e050b4e16cef44e47e3387060c950339f0df654f2a2b214d3daf6"  # pragma: allowlist secret  # noqa: E501
        or t0705_authorization.get("failed_attempt_ledgers_required") != 4
        or t0705_authorization.get("first_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("first_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("second_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("second_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("third_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("third_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("fourth_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("fourth_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("failed_workflow_head_shas")
        != [
            "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f",  # pragma: allowlist secret
            "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0",  # pragma: allowlist secret
            "cc7c8af9a40122a61ee2549fb365df813cbd4f16",  # pragma: allowlist secret
            CURRENT_MAINLINE_BASE_COMMIT,
        ]
        or t0705_authorization.get("failed_head_rerun_allowed") is not False
        or t0705_authorization.get("failed_head_redispatch_allowed") is not False
        or t0705_authorization.get("t0704_receipt_sha256")
        != _sha256(root / PROTECTED_BLUE_GREEN_RECEIPT_PATH)
        or t0705_authorization.get("t0705_authorized") is not True
        or t0705_authorization.get("t0706_authorized") is not False
        or t0705_authorization.get("controlled_main_delivery_total_limit") != 6
        or t0705_authorization.get("controlled_main_deliveries_consumed") != 4
        or t0705_authorization.get("controlled_main_deliveries_remaining") != 2
        or t0705_authorization.get("ga_rehearsal_dispatches_consumed") != 4
        or t0705_authorization.get("ga_metadata_quarantine_repair_dispatches_consumed") != 1
        or t0705_authorization.get("ga_label_replay_repair_dispatches_consumed") != 1
        or t0705_authorization.get("ga_phase_diagnostic_dispatch_limit") != 1
        or t0705_authorization.get("ga_phase_diagnostic_rerun_limit") != 0
        or t0705_authorization.get("manual_environment_reviewers_required") is not False
        or t0705_authorization.get("fixed_calendar_wait_days") != 0
        or t0705_authorization.get("final_publication_authorized") is not False
        or t0705_budget.get("controlled_main_deliveries_total_maximum") != 6
        or t0705_budget.get("controlled_main_deliveries_remaining_maximum") != 2
        or t0705_budget.get("protected_environment_secret_names_maximum") != 8
        or t0705_budget.get("protected_ga_rehearsal_dispatches_total_maximum") != 5
        or t0705_budget.get("protected_ga_rehearsal_dispatches_consumed") != 4
        or t0705_budget.get("protected_ga_metadata_quarantine_repair_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_label_replay_repair_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_phase_diagnostic_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_rehearsal_reruns_maximum") != 0
        or t0705_budget.get("failed_head_reruns_maximum") != 0
        or t0705_budget.get("failed_head_redispatches_maximum") != 0
        or t0705_budget.get("protected_ga_phase_diagnostic_pipeline_runs_maximum") != 1
        or t0705_budget.get("platform_schedule_events_during_rehearsal_maximum") != 0
        or t0705_budget.get("gmail_exact_message_trash_mutations_maximum") != 1
        or t0705_budget.get("maximum_live_timeline_assets") != 1
        or t0705_budget.get("production_schedule_enablement_mutations_maximum") != 1
        or t0705_budget.get("t0706_runs_maximum") != 0
    ):
        raise ValueError("T0705 Run Contract is not the exact bounded candidate authority")
    return {
        "schema_version": "moomooau.source-provenance.v23",
        "authorization": {
            "basis": AUTHORIZATION_BASIS,
            "authorized_on": "2026-07-26",
            "authorized_scope": AUTHORIZED_SCOPE,
        },
        "predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-26-V1.0.22",
            "version": "1.0.22",
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
            "roadmap": "taskpack/ROADMAP.v1.0.23.md",
            "status_authority": "machine/status/latest.json",
            "workflow_validator": "machine/tools/validate_workflow_matrix.py",
            "publication_status": "CONTROLLED_T0705_PHASE_DIAGNOSTIC_CANDIDATE_NOT_FINAL",
        },
        "candidate_snapshot": CANDIDATE_SNAPSHOT,
        "semantic_delta": {
            "governance_visibility_changed": False,
            "dependency_credential_kind": "GITHUB_READ_ONLY_DEPLOY_KEY",
            "dependency_credential_repository_scope": "LinzeColin/Governance",
            "credential_material_in_package": False,
            "production_secret_reads_authorized": 8,
            "project_runtime_secret_reads_authorized": 8,
            "fork_pull_request_policy": ("FAIL_CLOSED_BEFORE_PROTECTED_DEPENDENCY_CHECKOUT"),
            "pull_request_target_allowed": False,
            "product_contract_changed": False,
            "task_graph_changed": False,
            "final_acceptance_thresholds_changed": False,
            "stage7_fixed_calendar_wait_removed": True,
            "protected_oracles_executed": 5,
            "protected_oracles_passed": 4,
            "protected_oracles_failed": 1,
            "production_workflow_runs": 4,
            "protected_workflow_runs": (
                attempt_summary["protected_workflow_runs"] + len(m3_attempts) + 7
            ),
            "remote_workflow_runs": (
                attempt_summary["protected_workflow_runs"] + len(m3_attempts) + 7
            ),
            "controlled_main_deliveries": (
                attempt_summary["controlled_main_deliveries"] + len(m3_attempts) + 7
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
            "timeline_writes": 4,
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
            "protected_blue_green_entrypoint_implemented": True,
            "protected_blue_green_workflow_enabled_default": True,
            "protected_blue_green_workflow_sha256": _sha256(
                root.parents[1] / ".github/workflows/moomooau-blue-green.yml"
            ),
            "protected_blue_green_contract_authorized": False,
            "protected_blue_green_repair_contract_authorized": False,
            "protected_blue_green_environment_reused": "moomooau-beta",
            "protected_blue_green_secret_values_exact": 8,
            "protected_blue_green_dispatches": 2,
            "protected_blue_green_reruns": 0,
            "protected_blue_green_failed_attempts": 1,
            "protected_blue_green_successful_receipts": 1,
            "protected_blue_green_fixed_calendar_wait_days": 0,
            "protected_blue_green_gmail_mutations": 0,
            "protected_blue_green_current_pointer_mutations": 0,
            "protected_blue_green_candidate_shadow_commits": 2,
            "protected_blue_green_timeline_snapshot_commits": 2,
            "protected_blue_green_timeline_state_commits": 2,
            "protected_blue_green_timeline_writes": 4,
            "protected_blue_green_live_timeline_assets": 1,
            "protected_blue_green_processed_current_unchanged": True,
            "protected_blue_green_release_asset_redirect_defect_proven": True,
            "protected_blue_green_release_asset_redirect_repair_verified": True,
            "protected_blue_green_failed_head_frozen": True,
            "protected_blue_green_successful_head_frozen": True,
            "protected_blue_green_raw_tree_unchanged_after_repair": True,
            "protected_blue_green_processed_tree_unchanged_after_repair": True,
            "protected_blue_green_duplicate_candidate_commits": 0,
            "protected_blue_green_duplicate_timeline_snapshot_commits": 0,
            "protected_blue_green_current_run_source_mutations": 0,
            "protected_blue_green_independent_namespace_verification": True,
            "protected_blue_green_other_namespace_activity_excluded": True,
            "protected_blue_green_attempt_ledger_sha256": _sha256(
                root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_PATH
            ),
            "protected_blue_green_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_BLUE_GREEN_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_blue_green_execution_receipt_sha256": _sha256(
                root / PROTECTED_BLUE_GREEN_RECEIPT_PATH
            ),
            "protected_blue_green_execution_receipt_schema_sha256": _sha256(
                root / PROTECTED_BLUE_GREEN_RECEIPT_SCHEMA_PATH
            ),
            "protected_ga_entrypoint_implemented": True,
            "t0705_run_contract_sha256": _sha256(root / T0705_RUN_CONTRACT_PATH),
            "protected_ga_workflow_sha256": _sha256(
                root.parents[1] / ".github/workflows/moomooau-production.yml"
            ),
            "protected_ga_contract_authorized": True,
            "protected_ga_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_repair_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_repair_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_REPAIR_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_label_replay_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_label_replay_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_LABEL_REPLAY_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_post_processed_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_post_processed_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_POST_PROCESSED_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_environment_reused": "moomooau-beta",
            "protected_ga_secret_names_exact": 8,
            "protected_ga_rehearsal_dispatches": 4,
            "protected_ga_rehearsal_reruns": 0,
            "protected_ga_pipeline_runs": 0,
            "protected_ga_failed_attempts": 4,
            "protected_ga_metadata_quarantine_repair_dispatches_consumed": 1,
            "protected_ga_label_replay_repair_dispatches_consumed": 1,
            "protected_ga_phase_diagnostic_dispatches_authorized": 1,
            "protected_ga_closed_phase_diagnostics": True,
            "protected_ga_fourth_attempt_age_encrypted_added_paths": 6,
            "protected_ga_fourth_attempt_timeline_or_checkpoint_path_changes": 0,
            "protected_ga_fourth_attempt_exact_root_cause_claimed": False,
            "protected_ga_failed_head_frozen": True,
            "protected_ga_safe_deferred_compatibility_repaired_locally": True,
            "protected_ga_metadata_quarantine_repaired_locally": True,
            "protected_ga_persisted_first_import_label_state_replayed_locally": True,
            "protected_ga_second_verification_remains_fail_closed": True,
            "protected_ga_schedule_mode": "SCHEDULE_REHEARSAL",
            "protected_ga_platform_schedule_events": 0,
            "protected_ga_target_time": "04:30",
            "protected_ga_timezone": "Australia/Sydney",
            "protected_ga_live_capacity_refresh_before_gmail": True,
            "production_schedule_enabled": False,
            "t0705_authorized": True,
            "t0706_authorized": False,
            "remote_publications": 0,
        },
    }


def _validate_provenance(root: Path, failures: list[str]) -> None:
    provenance_version = PROVENANCE_PATH.name.removeprefix("SOURCE_PROVENANCE.v").removesuffix(
        ".json"
    )
    if provenance_version == PROVENANCE_PATH.name:
        provenance_version = PACKAGE_VERSION
    try:
        provenance = _load(root / PROVENANCE_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        failures.append(f"v{provenance_version} provenance is missing or invalid")
        return
    if not isinstance(provenance, dict):
        failures.append(f"v{provenance_version} provenance must be an object")
        return
    if provenance != build_provenance(root):
        failures.append(
            f"v{provenance_version} provenance differs from the exact deterministic authority"
        )
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
        provenance.get("schema_version") != "moomooau.source-provenance.v23"
        or authorization.get("basis") != AUTHORIZATION_BASIS
        or authorization.get("authorized_scope") != AUTHORIZED_SCOPE
        or effective.get("package_id") != PACKAGE_ID
        or effective.get("version") != PACKAGE_VERSION
        or effective.get("manifest") != MANIFEST_PATH.as_posix()
        or effective.get("roadmap") != "taskpack/ROADMAP.v1.0.23.md"
        or effective.get("status_authority") != "machine/status/latest.json"
        or effective.get("workflow_validator") != "machine/tools/validate_workflow_matrix.py"
        or effective.get("publication_status")
        != "CONTROLLED_T0705_PHASE_DIAGNOSTIC_CANDIDATE_NOT_FINAL"
    ):
        failures.append(f"v{provenance_version} provenance identity or authorization mismatch")
    if (
        predecessor.get("manifest") != PREDECESSOR_MANIFEST_PATH.as_posix()
        or predecessor.get("manifest_sha256") != PREDECESSOR_MANIFEST_SHA256
        or predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.22 predecessor provenance mismatch")
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
        failures.append(f"v{provenance_version} semantic delta is incomplete or overstated")


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
        failures.append("predecessor v1.0.21 manifest artifact is not preserved")
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
            failures.append("manifest differs from the canonical v1.0.23 package selection")

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
    parser.add_argument(
        "--write-provenance",
        action="store_true",
        help="write the deterministic versioned source-provenance artifact before validation",
    )
    args = parser.parse_args()
    if args.write_provenance:
        root = args.root.resolve()
        path = root / PROVENANCE_PATH
        path.write_text(
            json.dumps(build_provenance(root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "written": PROVENANCE_PATH.as_posix(),
                    "sha256": _sha256(path),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    result = validate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
