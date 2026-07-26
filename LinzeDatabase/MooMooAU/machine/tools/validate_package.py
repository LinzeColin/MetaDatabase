#!/usr/bin/env python3
"""Read-only validator for the v1.0.34 protected T0705 Trash-confirmation package."""

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
PROVENANCE_PATH = Path("taskpack/SOURCE_PROVENANCE.v1.0.34.json")
CURRENT_MAINLINE_BASE_COMMIT = (
    "4b7442bb635ea1e7cf5a814c3c56047aa288d594"  # pragma: allowlist secret
)
ACCEPTANCE_REMEDIATION_BASE_COMMIT = (
    "4b7442bb635ea1e7cf5a814c3c56047aa288d594"  # pragma: allowlist secret
)
T0705_CANDIDATE_PREFLIGHT_HEAD = (
    "26949ab5031a21b0c515c282c9ef06ff9417e058"  # pragma: allowlist secret
)
T0705_AUTHORITY_CONTEXT_HEAD = (
    "9c79b92bcdf8b027727963dfe52bd183a170954c"  # pragma: allowlist secret
)
T0705_SCHEDULE_PLANNING_HEAD = (
    "27886f54a30a12ca7992a908e97340d1d8234430"  # pragma: allowlist secret
)
T0705_AUTHENTICATION_CLOCK_HEAD = (
    "c2c057b449fe1cbbd470867c274833242e3f139d"  # pragma: allowlist secret
)
T0705_RAW_RECOVERY_HEAD = "0d0b6afd6a0cde606230a3df7378bdd90586de5d"  # pragma: allowlist secret
T0705_TRASH_CONFIRMATION_HEAD = CURRENT_MAINLINE_BASE_COMMIT
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
PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/processed-plan-attempt-ledger.json"
)
PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-processed-plan-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/first-import-attempt-ledger.json"
)
PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-first-import-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/pointer-fetch-attempt-ledger.json"
)
PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-pointer-fetch-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/pointer-blob-attempt-ledger.json"
)
PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-pointer-blob-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/canonical-blob-attempt-ledger.json"
)
PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-canonical-blob-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/canonical-blob-preflight-attempt-ledger.json"
)
PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-candidate-preflight-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/authority-variable-scope-attempt-ledger.json"
)
PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-authority-context-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/schedule-planning-clock-attempt-ledger.json"
)
PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-schedule-planning-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/authentication-clock-coupling-attempt-ledger.json"
)
PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-authentication-clock-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/raw-recovery-representation-attempt-ledger.json"
)
PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/"
    "protected-ga-raw-recovery-representation-attempt-ledger-v1.schema.json"
)
PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_PATH = Path(
    "machine/stages/S7/reviews/t0705/trash-confirmation-attempt-ledger.json"
)
PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-ga-trash-confirmation-attempt-ledger-v1.schema.json"
)
T0705_RUN_CONTRACT_PATH = Path("machine/stages/S7/contracts/run_contract.json")
AUTHORIZATION_BASIS = (
    "The exact protected T0702, T0703 and T0704 PASS receipts, all thirteen immutable T0705 "
    "protected failed-attempt ledgers and the distinct pre-Secret candidate-validation and "
    "authority-context ledgers, "
    "live read-only raw-media versus Git Blob replay, owner no-time-gate direction and one-task "
    "successor Run Contract freeze every failed head and authorize exactly one repository-scoped "
    "one-shot authority T0705 exact-main Trash-confirmation schedule-mode rehearsal "
    "without authorizing "
    "T0706 or final publication"
)
AUTHORIZED_SCOPE = (
    "One repository-scoped one-shot authority T0705 Trash-confirmation recovery "
    "candidate: never rerun or redispatch any protected failed head or either pre-Secret failed "
    "head "
    "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f, "
    "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0 or "
    "cc7c8af9a40122a61ee2549fb365df813cbd4f16 or "
    "4c207ad539754166fae6642ff4e6850438d3e2fc or "
    "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4 or "
    "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7 or "
    "2133673b335a384657c8668b62a1c13055c212cd or "
    "8b6faaf9059661edc3153352b8787ddbc4f733f3 or "
    "6f82e738611e0d2eeeadd2507f738c9e269c91e0 or "
    "26949ab5031a21b0c515c282c9ef06ff9417e058 or "
    "9c79b92bcdf8b027727963dfe52bd183a170954c or "
    "27886f54a30a12ca7992a908e97340d1d8234430 or "
    "c2c057b449fe1cbbd470867c274833242e3f139d or "
    "0d0b6afd6a0cde606230a3df7378bdd90586de5d or "
    "4b7442bb635ea1e7cf5a814c3c56047aa288d594. Use bounded Contents metadata only to bind exact "
    "path, size and blob SHA, then recover Raw and Processed ciphertext from the exact "
    "metadata-addressed "
    "Git Blobs API base64 body with response SHA, decoded size, age envelope and canonical Git "
    "blob SHA validation; never trust Contents inline or raw-media bodies. The ninth protected "
    "attempt already proved exact installation repository scope before Gmail credential exchange. "
    "Preserve "
    "persisted first-import timestamp and label-state replay plus pre-Raw metadata "
    "quarantine, prior pending refs, fail-closed second verification, ACTIVE processing and "
    "paired-empty SAFE_DEFERRED. Bind all protected predecessor receipts, all thirteen protected "
    "failed ledgers plus the candidate-preflight and authority-context ledgers, "
    "reuse the existing "
    "eight-name moomooau-beta Environment and installed GitHub App, refresh live "
    "private-repository capacity before Gmail exchange, set the exact-head one-shot authority "
    "at repository scope only after merge and delete it after consumption, then allow one new "
    "attempt-1 workflow_dispatch SCHEDULE_REHEARSAL with rerun zero; security, authentication, "
    "OAuth, capacity and evidence timestamps use live UTC while RunPlanner alone receives the "
    "committed 2026-07-26T19:00:00Z historical replay clock after all known data effects. "
    "Verified-only Raw and Processed remote "
    "recovery precede exact-message Trash budget one; request only fields=id,labelIds for label "
    "confirmation, and after an uncertain Trash response perform at most one read and zero "
    "mutation retries. Timeline and checkpoint recovery are mandatory. Enable only "
    "the committed 04:30 Australia/Sydney schedule after PASS and stop before T0706"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_provenance(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Return the exact RMD-06 and protected T0705 Trash-confirmation authority."""

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
    ga_processed_plan_ledger = _load(root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_PATH)
    ga_processed_plan_ledger_schema = _load(
        root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_first_import_ledger = _load(root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_PATH)
    ga_first_import_ledger_schema = _load(
        root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_pointer_fetch_ledger = _load(root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_PATH)
    ga_pointer_fetch_ledger_schema = _load(
        root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_pointer_blob_ledger = _load(root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_PATH)
    ga_pointer_blob_ledger_schema = _load(
        root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_canonical_blob_ledger = _load(root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_PATH)
    ga_canonical_blob_ledger_schema = _load(
        root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_candidate_preflight_ledger = _load(
        root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_PATH
    )
    ga_candidate_preflight_ledger_schema = _load(
        root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_authority_context_ledger = _load(root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_PATH)
    ga_authority_context_ledger_schema = _load(
        root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_schedule_planning_ledger = _load(root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_PATH)
    ga_schedule_planning_ledger_schema = _load(
        root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_authentication_clock_ledger = _load(
        root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_PATH
    )
    ga_authentication_clock_ledger_schema = _load(
        root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_raw_recovery_ledger = _load(root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_PATH)
    ga_raw_recovery_ledger_schema = _load(
        root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_PATH
    )
    ga_trash_confirmation_ledger = _load(root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_PATH)
    ga_trash_confirmation_ledger_schema = _load(
        root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_PATH
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
        or ga_post_processed_delivery.get("merge_commit_sha")
        != "4c207ad539754166fae6642ff4e6850438d3e2fc"  # pragma: allowlist secret
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

    ga_processed_plan_errors = list(
        Draft202012Validator(
            ga_processed_plan_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_processed_plan_ledger)
    )
    ga_processed_plan_attempts = ga_processed_plan_ledger.get("attempts", [])
    ga_processed_plan_attempt = (
        ga_processed_plan_attempts[0]
        if isinstance(ga_processed_plan_attempts, list) and len(ga_processed_plan_attempts) == 1
        else {}
    )
    ga_processed_plan_delivery = ga_processed_plan_attempt.get("delivery", {})
    ga_processed_plan_workflow = ga_processed_plan_attempt.get("workflow", {})
    ga_processed_plan_jobs = ga_processed_plan_attempt.get("jobs", {})
    ga_processed_plan_failure = ga_processed_plan_attempt.get("public_failure", {})
    ga_processed_plan_effects = ga_processed_plan_attempt.get("effects", {})
    ga_processed_plan_diagnosis = ga_processed_plan_attempt.get("diagnosis", {})
    ga_processed_plan_policy = ga_processed_plan_ledger.get("completion_policy", {})
    ga_processed_plan_claims = ga_processed_plan_ledger.get("claims", {})
    if (
        ga_processed_plan_errors
        or _sha256(root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_PATH)
        != "9cebe7c23adf11274c645c5b2d87da7d4b435602b6c8bba2b7b6b24b130546dc"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "1964a88737eaaadbbfc5cc22419730cd59c09d86f187132f21cf2c0b79c157a0"  # pragma: allowlist secret  # noqa: E501
        or ga_processed_plan_attempt.get("sequence") != 5
        or ga_processed_plan_delivery.get("pull_request_number") != 119
        or ga_processed_plan_delivery.get("merge_commit_sha")
        != "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4"  # pragma: allowlist secret
        or ga_processed_plan_delivery.get("merge_commit_sha")
        != ga_processed_plan_workflow.get("workflow_head_sha")
        or ga_processed_plan_workflow.get("run_id") != 30192270846
        or ga_processed_plan_workflow.get("run_attempt") != 1
        or ga_processed_plan_workflow.get("reruns") != 0
        or ga_processed_plan_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_processed_plan_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_processed_plan_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_processed_plan_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_processed_plan_failure.get("reason_code") != "PROTECTED_GA_PROCESSED_PLAN_FAILED"
        or ga_processed_plan_failure.get("failure_phase") != "PROCESSED_PLAN"
        or ga_processed_plan_failure.get("exact_root_cause_claimed") is not False
        or any(
            ga_processed_plan_effects.get(key) != 0
            for key in (
                "private_repository_new_commits_during_attempt",
                "private_repository_added_paths",
                "private_repository_modified_paths",
                "private_repository_removed_paths",
                "raw_ciphertext_creations",
                "processed_immutable_creations",
                "processed_current_pointer_mutations",
                "timeline_snapshot_mutations",
                "timeline_state_mutations",
                "timeline_publish_attempts",
                "gmail_checkpoint_mutations",
                "gmail_source_mutations",
                "platform_schedule_events",
            )
        )
        or ga_processed_plan_effects.get("gmail_mutation_api_reached") is not False
        or ga_processed_plan_diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
        or ga_processed_plan_diagnosis.get("exact_root_cause") != "UNKNOWN"
        or ga_processed_plan_diagnosis.get("safe_next_diagnostic")
        != "CLOSED_ENUM_PROCESSED_PLAN_SUBPHASE_ONLY"
        or ga_processed_plan_policy.get("same_head_rerun_allowed") is not False
        or ga_processed_plan_policy.get("failed_head_redispatch_allowed") is not False
        or ga_processed_plan_policy.get("new_reviewed_processed_plan_subphase_candidate_allowed")
        is not True
        or ga_processed_plan_policy.get("next_candidate_dispatch_limit") != 1
        or ga_processed_plan_policy.get("historical_ga_rehearsal_dispatches_consumed") != 5
        or ga_processed_plan_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_processed_plan_policy.get("t0705_complete") is not False
        or ga_processed_plan_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_processed_plan_claims.values())
    ):
        raise ValueError("protected T0705 Processed-plan attempt ledger is not exact or frozen")

    ga_first_import_errors = list(
        Draft202012Validator(
            ga_first_import_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_first_import_ledger)
    )
    ga_first_import_attempts = ga_first_import_ledger.get("attempts", [])
    ga_first_import_attempt = (
        ga_first_import_attempts[0]
        if isinstance(ga_first_import_attempts, list) and len(ga_first_import_attempts) == 1
        else {}
    )
    ga_first_import_delivery = ga_first_import_attempt.get("delivery", {})
    ga_first_import_workflow = ga_first_import_attempt.get("workflow", {})
    ga_first_import_jobs = ga_first_import_attempt.get("jobs", {})
    ga_first_import_failure = ga_first_import_attempt.get("public_failure", {})
    ga_first_import_effects = ga_first_import_attempt.get("effects", {})
    ga_first_import_diagnosis = ga_first_import_attempt.get("diagnosis", {})
    ga_first_import_policy = ga_first_import_ledger.get("completion_policy", {})
    ga_first_import_claims = ga_first_import_ledger.get("claims", {})
    if (
        ga_first_import_errors
        or _sha256(root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_PATH)
        != "9c5b5bedade30d511d0503f0b623a57ff59bca14bd7cf48409f8a6c459879b31"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "d6deff1bc93e92c78e1b3c15771a679bcc5fd6b2a59da216fbbf08a4244be4b3"  # pragma: allowlist secret  # noqa: E501
        or ga_first_import_attempt.get("sequence") != 6
        or ga_first_import_delivery.get("pull_request_number") != 120
        or ga_first_import_delivery.get("merge_commit_sha")
        != "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7"  # pragma: allowlist secret
        or ga_first_import_delivery.get("merge_commit_sha")
        != ga_first_import_workflow.get("workflow_head_sha")
        or ga_first_import_workflow.get("run_id") != 30194651840
        or ga_first_import_workflow.get("run_attempt") != 1
        or ga_first_import_workflow.get("reruns") != 0
        or ga_first_import_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_first_import_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_first_import_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_first_import_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_first_import_failure.get("reason_code") != "PROTECTED_GA_FIRST_IMPORT_RECOVERY_FAILED"
        or ga_first_import_failure.get("failure_phase") != "FIRST_IMPORT_RECOVERY"
        or ga_first_import_failure.get("exact_root_cause_claimed") is not False
        or any(
            ga_first_import_effects.get(key) != 0
            for key in (
                "private_repository_new_commits_during_attempt",
                "private_repository_added_paths",
                "private_repository_modified_paths",
                "private_repository_removed_paths",
                "raw_ciphertext_creations",
                "processed_immutable_creations",
                "processed_current_pointer_mutations",
                "timeline_snapshot_mutations",
                "timeline_state_mutations",
                "timeline_publish_attempts",
                "gmail_checkpoint_mutations",
                "gmail_source_mutations",
                "platform_schedule_events",
            )
        )
        or ga_first_import_effects.get("gmail_mutation_api_reached") is not False
        or ga_first_import_diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
        or ga_first_import_diagnosis.get("exact_root_cause") != "UNKNOWN"
        or ga_first_import_diagnosis.get("safe_next_diagnostic")
        != "CLOSED_ENUM_FIRST_IMPORT_RECOVERY_SUBPHASE_ONLY"
        or ga_first_import_policy.get("same_head_rerun_allowed") is not False
        or ga_first_import_policy.get("failed_head_redispatch_allowed") is not False
        or ga_first_import_policy.get("new_reviewed_first_import_subphase_candidate_allowed")
        is not True
        or ga_first_import_policy.get("exact_repair_or_pass_closure_candidate_allowed") is not True
        or ga_first_import_policy.get("next_candidate_dispatch_limit") != 2
        or ga_first_import_policy.get("historical_ga_rehearsal_dispatches_consumed") != 6
        or ga_first_import_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_first_import_policy.get("t0705_complete") is not False
        or ga_first_import_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_first_import_claims.values())
    ):
        raise ValueError("protected T0705 first-import attempt ledger is not exact or frozen")

    ga_pointer_fetch_errors = list(
        Draft202012Validator(
            ga_pointer_fetch_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_pointer_fetch_ledger)
    )
    ga_pointer_fetch_attempts = ga_pointer_fetch_ledger.get("attempts", [])
    ga_pointer_fetch_attempt = (
        ga_pointer_fetch_attempts[0]
        if isinstance(ga_pointer_fetch_attempts, list) and len(ga_pointer_fetch_attempts) == 1
        else {}
    )
    ga_pointer_fetch_delivery = ga_pointer_fetch_attempt.get("delivery", {})
    ga_pointer_fetch_workflow = ga_pointer_fetch_attempt.get("workflow", {})
    ga_pointer_fetch_jobs = ga_pointer_fetch_attempt.get("jobs", {})
    ga_pointer_fetch_failure = ga_pointer_fetch_attempt.get("public_failure", {})
    ga_pointer_fetch_effects = ga_pointer_fetch_attempt.get("effects", {})
    ga_pointer_fetch_protocol = ga_pointer_fetch_attempt.get("protocol_evidence", {})
    ga_pointer_fetch_diagnosis = ga_pointer_fetch_attempt.get("diagnosis", {})
    ga_pointer_fetch_policy = ga_pointer_fetch_ledger.get("completion_policy", {})
    ga_pointer_fetch_claims = ga_pointer_fetch_ledger.get("claims", {})
    if (
        ga_pointer_fetch_errors
        or _sha256(root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_PATH)
        != "18d2e1cc29182dea7a94b25d25072d15cbc0ac91b091685faba69bcaa7532066"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "801e1e44299115958bc838cc6c8e04c45f482a5ee50567345f22ad2295db83d2"  # pragma: allowlist secret  # noqa: E501
        or ga_pointer_fetch_attempt.get("sequence") != 7
        or ga_pointer_fetch_delivery.get("pull_request_number") != 122
        or ga_pointer_fetch_delivery.get("merge_commit_sha")
        != "2133673b335a384657c8668b62a1c13055c212cd"  # pragma: allowlist secret
        or ga_pointer_fetch_delivery.get("merge_commit_sha")
        != ga_pointer_fetch_workflow.get("workflow_head_sha")
        or ga_pointer_fetch_workflow.get("run_id") != 30196968135
        or ga_pointer_fetch_workflow.get("run_attempt") != 1
        or ga_pointer_fetch_workflow.get("reruns") != 0
        or ga_pointer_fetch_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_pointer_fetch_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_pointer_fetch_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_pointer_fetch_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_pointer_fetch_failure.get("reason_code")
        != "PROTECTED_GA_FIRST_IMPORT_POINTER_FETCH_FAILED"
        or ga_pointer_fetch_failure.get("failure_phase") != "FIRST_IMPORT_POINTER_FETCH"
        or ga_pointer_fetch_failure.get("exact_root_cause_claimed") is not False
        or any(
            ga_pointer_fetch_effects.get(key) != 0
            for key in (
                "private_repository_new_commits_during_attempt",
                "private_repository_added_paths",
                "private_repository_modified_paths",
                "private_repository_removed_paths",
                "raw_ciphertext_creations",
                "processed_immutable_creations",
                "processed_current_pointer_mutations",
                "timeline_snapshot_mutations",
                "timeline_state_mutations",
                "timeline_publish_attempts",
                "gmail_checkpoint_mutations",
                "gmail_source_mutations",
                "platform_schedule_events",
            )
        )
        or ga_pointer_fetch_effects.get("private_repository_head_changed") is not False
        or ga_pointer_fetch_effects.get("gmail_mutation_api_reached") is not False
        or ga_pointer_fetch_protocol.get("matching_private_repositories") != 1
        or ga_pointer_fetch_protocol.get("current_pointer_objects") != 2
        or ga_pointer_fetch_protocol.get("git_tree_blob_objects_valid") != 2
        or ga_pointer_fetch_protocol.get("git_raw_media_objects_valid") != 2
        or ga_pointer_fetch_protocol.get("contents_inline_representation_mismatches") != 1
        or ga_pointer_fetch_protocol.get("canonical_git_blob_sha_bindings_valid") != 2
        or ga_pointer_fetch_diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
        or ga_pointer_fetch_diagnosis.get("exact_root_cause") != "UNKNOWN"
        or ga_pointer_fetch_diagnosis.get("safe_next_repair")
        != "CONTENTS_METADATA_PLUS_EXACT_RAW_MEDIA_WITH_CANONICAL_GIT_BLOB_SHA_BINDING"
        or ga_pointer_fetch_policy.get("same_head_rerun_allowed") is not False
        or ga_pointer_fetch_policy.get("failed_head_redispatch_allowed") is not False
        or ga_pointer_fetch_policy.get("exact_pointer_blob_recovery_repair_candidate_allowed")
        is not True
        or ga_pointer_fetch_policy.get("next_candidate_dispatch_limit") != 1
        or ga_pointer_fetch_policy.get("historical_ga_rehearsal_dispatches_consumed") != 7
        or ga_pointer_fetch_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_pointer_fetch_policy.get("t0705_complete") is not False
        or ga_pointer_fetch_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_pointer_fetch_claims.values())
    ):
        raise ValueError("protected T0705 pointer-fetch attempt ledger is not exact or frozen")

    ga_pointer_blob_errors = list(
        Draft202012Validator(
            ga_pointer_blob_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_pointer_blob_ledger)
    )
    ga_pointer_blob_attempts = ga_pointer_blob_ledger.get("attempts", [])
    ga_pointer_blob_attempt = (
        ga_pointer_blob_attempts[0]
        if isinstance(ga_pointer_blob_attempts, list) and len(ga_pointer_blob_attempts) == 1
        else {}
    )
    ga_pointer_blob_delivery = ga_pointer_blob_attempt.get("delivery", {})
    ga_pointer_blob_workflow = ga_pointer_blob_attempt.get("workflow", {})
    ga_pointer_blob_jobs = ga_pointer_blob_attempt.get("jobs", {})
    ga_pointer_blob_failure = ga_pointer_blob_attempt.get("public_failure", {})
    ga_pointer_blob_effects = ga_pointer_blob_attempt.get("effects", {})
    ga_pointer_blob_transition = ga_pointer_blob_attempt.get("external_state_transition", {})
    ga_pointer_blob_diagnosis = ga_pointer_blob_attempt.get("diagnosis", {})
    ga_pointer_blob_policy = ga_pointer_blob_ledger.get("completion_policy", {})
    ga_pointer_blob_claims = ga_pointer_blob_ledger.get("claims", {})
    if (
        ga_pointer_blob_errors
        or _sha256(root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_PATH)
        != "092f5a580d905213066a99221f51b9065748dceeb82e48e20b54ed42e82d444f"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "2945fb030f4154da1d18142f5b239a5b824126010d8dbcc9ae92b7a973f089ab"  # pragma: allowlist secret  # noqa: E501
        or ga_pointer_blob_attempt.get("sequence") != 8
        or ga_pointer_blob_delivery.get("pull_request_number") != 123
        or ga_pointer_blob_delivery.get("merge_commit_sha")
        != "8b6faaf9059661edc3153352b8787ddbc4f733f3"  # pragma: allowlist secret
        or ga_pointer_blob_delivery.get("merge_commit_sha")
        != ga_pointer_blob_workflow.get("workflow_head_sha")
        or ga_pointer_blob_workflow.get("run_id") != 30199215335
        or ga_pointer_blob_workflow.get("run_attempt") != 1
        or ga_pointer_blob_workflow.get("reruns") != 0
        or ga_pointer_blob_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_pointer_blob_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_pointer_blob_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_pointer_blob_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_pointer_blob_failure.get("reason_code")
        != "PROTECTED_GA_FIRST_IMPORT_POINTER_FETCH_FAILED"
        or ga_pointer_blob_failure.get("failure_phase") != "FIRST_IMPORT_POINTER_FETCH"
        or ga_pointer_blob_failure.get("exact_root_cause_claimed") is not False
        or any(
            ga_pointer_blob_effects.get(key) != 0
            for key in (
                "private_repository_new_commits_during_attempt",
                "private_repository_added_paths",
                "private_repository_modified_paths",
                "private_repository_removed_paths",
                "raw_ciphertext_creations",
                "processed_immutable_creations",
                "processed_current_pointer_mutations",
                "timeline_snapshot_mutations",
                "timeline_state_mutations",
                "timeline_publish_attempts",
                "gmail_checkpoint_mutations",
                "gmail_source_mutations",
                "platform_schedule_events",
            )
        )
        or ga_pointer_blob_effects.get("matching_private_repositories") != 1
        or ga_pointer_blob_effects.get("private_repository_head_changed") is not False
        or ga_pointer_blob_effects.get("gmail_mutation_api_reached") is not False
        or ga_pointer_blob_transition.get("occurred_after_failed_attempt") is not True
        or ga_pointer_blob_transition.get(
            "owner_confirmed_github_app_linked_to_existing_single_private_data_repository"
        )
        is not True
        or ga_pointer_blob_transition.get("runtime_installation_repository_scope_verification")
        != "PENDING_NEW_EXACT_HEAD_PROTECTED_ORACLE"
        or ga_pointer_blob_transition.get("retroactive_root_cause_attribution") is not False
        or ga_pointer_blob_diagnosis.get("exact_runtime_exception") != "NOT_RECEIVED_OR_INSPECTED"
        or ga_pointer_blob_diagnosis.get("exact_root_cause") != "UNKNOWN"
        or ga_pointer_blob_diagnosis.get("exact_root_cause_claimed") is not False
        or ga_pointer_blob_policy.get("same_head_rerun_allowed") is not False
        or ga_pointer_blob_policy.get("failed_head_redispatch_allowed") is not False
        or ga_pointer_blob_policy.get("exact_app_repository_scope_activation_candidate_allowed")
        is not True
        or ga_pointer_blob_policy.get("next_candidate_dispatch_limit") != 1
        or ga_pointer_blob_policy.get("historical_ga_rehearsal_dispatches_consumed") != 8
        or ga_pointer_blob_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_pointer_blob_policy.get("t0705_complete") is not False
        or ga_pointer_blob_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_pointer_blob_claims.values())
    ):
        raise ValueError("protected T0705 pointer-blob attempt ledger is not exact or frozen")

    ga_canonical_blob_errors = list(
        Draft202012Validator(
            ga_canonical_blob_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_canonical_blob_ledger)
    )
    ga_canonical_blob_attempts = ga_canonical_blob_ledger.get("attempts", [])
    ga_canonical_blob_attempt = (
        ga_canonical_blob_attempts[0]
        if isinstance(ga_canonical_blob_attempts, list) and len(ga_canonical_blob_attempts) == 1
        else {}
    )
    ga_canonical_blob_delivery = ga_canonical_blob_attempt.get("delivery", {})
    ga_canonical_blob_workflow = ga_canonical_blob_attempt.get("workflow", {})
    ga_canonical_blob_jobs = ga_canonical_blob_attempt.get("jobs", {})
    ga_canonical_blob_failure = ga_canonical_blob_attempt.get("public_failure", {})
    ga_canonical_blob_effects = ga_canonical_blob_attempt.get("effects", {})
    ga_canonical_blob_scope = ga_canonical_blob_attempt.get("scope_activation", {})
    ga_canonical_blob_protocol = ga_canonical_blob_attempt.get("live_protocol_ab", {})
    ga_canonical_blob_diagnosis = ga_canonical_blob_attempt.get("diagnosis", {})
    ga_canonical_blob_policy = ga_canonical_blob_ledger.get("completion_policy", {})
    ga_canonical_blob_claims = ga_canonical_blob_ledger.get("claims", {})
    if (
        ga_canonical_blob_errors
        or _sha256(root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_PATH)
        != "264cfa33f6e3662485d4abc2b3b69d70ba31fdba4d76b49102c16d7dfaa7e4bd"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "a5449bf6ca1733b5cd01a0cc7873b708bd95bf4dee37ac79550f364c879fd5a8"  # pragma: allowlist secret  # noqa: E501
        or ga_canonical_blob_attempt.get("sequence") != 9
        or ga_canonical_blob_delivery.get("pull_request_number") != 126
        or ga_canonical_blob_delivery.get("merge_commit_sha")
        != "6f82e738611e0d2eeeadd2507f738c9e269c91e0"  # pragma: allowlist secret
        or ga_canonical_blob_delivery.get("merge_commit_sha")
        != ga_canonical_blob_workflow.get("workflow_head_sha")
        or ga_canonical_blob_workflow.get("run_id") != 30201167052
        or ga_canonical_blob_workflow.get("run_attempt") != 1
        or ga_canonical_blob_workflow.get("reruns") != 0
        or ga_canonical_blob_jobs.get("authority_gate", {}).get("status") != "PASS"
        or ga_canonical_blob_jobs.get("ga_schedule_rehearsal", {}).get("status") != "FAILED"
        or ga_canonical_blob_jobs.get("identity_plaintext_cleanup", {}).get("status") != "PASS"
        or ga_canonical_blob_jobs.get("live_schedule_hold", {}).get("status") != "SKIPPED"
        or ga_canonical_blob_failure.get("reason_code")
        != "PROTECTED_GA_FIRST_IMPORT_POINTER_FETCH_FAILED"
        or ga_canonical_blob_failure.get("failure_phase") != "FIRST_IMPORT_POINTER_FETCH"
        or ga_canonical_blob_failure.get("exact_root_cause_claimed") is not False
        or any(
            ga_canonical_blob_effects.get(key) != 0
            for key in (
                "private_repository_new_commits_during_attempt",
                "raw_ciphertext_creations",
                "processed_immutable_creations",
                "processed_current_pointer_mutations",
                "timeline_snapshot_mutations",
                "timeline_state_mutations",
                "timeline_publish_attempts",
                "gmail_checkpoint_mutations",
                "gmail_source_mutations",
                "platform_schedule_events",
            )
        )
        or ga_canonical_blob_effects.get("matching_private_repositories") != 1
        or ga_canonical_blob_effects.get("private_repository_head_changed") is not False
        or ga_canonical_blob_effects.get("gmail_mutation_api_reached") is not False
        or ga_canonical_blob_scope.get("runtime_exact_installation_repository_scope")
        != "PASS_BEFORE_GMAIL_CREDENTIAL_EXCHANGE"
        or ga_canonical_blob_protocol.get("contents_raw_media_canonical_age_size_sha")
        != "PARTIAL_ONE_FAILED"
        or ga_canonical_blob_protocol.get("git_blob_api_encoding_sha_size_age") != "ALL_PASS"
        or ga_canonical_blob_protocol.get("patched_production_adapter_recovery") != "ALL_PASS"
        or ga_canonical_blob_diagnosis.get("exact_protected_runtime_exception")
        != "NOT_RECEIVED_OR_INSPECTED"
        or ga_canonical_blob_diagnosis.get("reproduced_root_cause")
        != "CONTENTS_RAW_MEDIA_RETURNED_NON_CANONICAL_BODY_FOR_ONE_CURRENT_POINTER"
        or ga_canonical_blob_diagnosis.get("safe_next_action")
        != "NEW_EXACT_HEAD_CANONICAL_GIT_BLOB_RECOVERY_REHEARSAL"
        or ga_canonical_blob_policy.get("same_head_rerun_allowed") is not False
        or ga_canonical_blob_policy.get("failed_head_redispatch_allowed") is not False
        or ga_canonical_blob_policy.get("exact_canonical_git_blob_candidate_allowed") is not True
        or ga_canonical_blob_policy.get("next_candidate_dispatch_limit") != 1
        or ga_canonical_blob_policy.get("historical_ga_rehearsal_dispatches_consumed") != 9
        or ga_canonical_blob_policy.get("historical_ga_rehearsal_reruns") != 0
        or ga_canonical_blob_policy.get("t0705_complete") is not False
        or ga_canonical_blob_policy.get("t0706_authorized") is not False
        or any(value is not False for value in ga_canonical_blob_claims.values())
    ):
        raise ValueError("protected T0705 canonical-blob attempt ledger is not exact or frozen")

    ga_candidate_preflight_errors = list(
        Draft202012Validator(
            ga_candidate_preflight_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_candidate_preflight_ledger)
    )
    preflight_delivery = ga_candidate_preflight_ledger.get("delivery", {})
    preflight_workflow = ga_candidate_preflight_ledger.get("workflow", {})
    preflight_jobs = ga_candidate_preflight_ledger.get("jobs", {})
    preflight_failure = ga_candidate_preflight_ledger.get("failure", {})
    preflight_effects = ga_candidate_preflight_ledger.get("effects", {})
    preflight_policy = ga_candidate_preflight_ledger.get("completion_policy", {})
    preflight_claims = ga_candidate_preflight_ledger.get("claims", {})
    if (
        ga_candidate_preflight_errors
        or _sha256(root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_PATH)
        != "f6e5707059df47549cbb92e58157578c872f53d23e2770b83b03ba50d100173d"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "e6f7c63108ca228475e38c5a3b75223861ef45ba419a11738edfc6505b373514"  # pragma: allowlist secret  # noqa: E501
        or preflight_delivery.get("pull_request_number") != 129
        or preflight_delivery.get("merge_commit_sha") != T0705_CANDIDATE_PREFLIGHT_HEAD
        or preflight_delivery.get("merge_commit_sha") != preflight_workflow.get("workflow_head_sha")
        or preflight_workflow.get("run_id") != 30203291213
        or preflight_workflow.get("run_attempt") != 1
        or preflight_workflow.get("reruns") != 0
        or preflight_jobs.get("authority_context") != "PASS"
        or preflight_jobs.get("candidate_validation") != "FAILED"
        or preflight_jobs.get("protected_environment") != "SKIPPED"
        or preflight_failure.get("reason_code") != "RUFF_FORMAT_CHECK_REJECTED"
        or preflight_failure.get("exact_root_cause_claimed") is not True
        or preflight_effects.get("protected_environment_entered") is not False
        or any(
            preflight_effects.get(key) != 0
            for key in (
                "protected_secret_names_injected",
                "gmail_api_calls",
                "private_repository_calls",
                "gmail_mutations",
                "private_repository_mutations",
                "timeline_mutations",
                "checkpoint_mutations",
                "platform_schedule_events",
            )
        )
        or preflight_policy.get("same_head_rerun_allowed") is not False
        or preflight_policy.get("failed_head_redispatch_allowed") is not False
        or preflight_policy.get("frozen_candidate_preflight_head_shas")
        != [T0705_CANDIDATE_PREFLIGHT_HEAD]
        or preflight_policy.get("next_candidate_scope")
        != "FORMAT_ONLY_PLUS_DERIVED_HASH_STATUS_AND_PACKAGE_BINDINGS"
        or preflight_policy.get("next_candidate_dispatch_limit") != 1
        or preflight_policy.get("protected_ga_rehearsal_dispatches_consumed") != 9
        or preflight_policy.get("protected_ga_rehearsal_reruns") != 0
        or any(value is not False for value in preflight_claims.values())
    ):
        raise ValueError(
            "protected T0705 candidate-preflight attempt ledger is not exact or frozen"
        )

    ga_authority_context_errors = list(
        Draft202012Validator(
            ga_authority_context_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_authority_context_ledger)
    )
    authority_delivery = ga_authority_context_ledger.get("delivery", {})
    authority_workflow = ga_authority_context_ledger.get("workflow", {})
    authority_jobs = ga_authority_context_ledger.get("jobs", {})
    authority_failure = ga_authority_context_ledger.get("failure", {})
    authority_effects = ga_authority_context_ledger.get("effects", {})
    authority_policy = ga_authority_context_ledger.get("completion_policy", {})
    authority_claims = ga_authority_context_ledger.get("claims", {})
    if (
        ga_authority_context_errors
        or _sha256(root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_PATH)
        != "04a1f579c29e384c7db16545f5babf4b5feee63333af53f2fc560ba5728fdbab"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "b927dcae93cb20de48cf2cf53fc50906492683eaf3f51021cca79e1f5b31de24"  # pragma: allowlist secret  # noqa: E501
        or ga_authority_context_ledger.get("scope")
        != "PRE_CHECKOUT_PRE_SECRET_AUTHORITY_CONTEXT_ONLY"
        or authority_delivery.get("pull_request_number") != 130
        or authority_delivery.get("pull_request_head_sha")
        != "ca79b2211ffcda40f13dce068db38aa8143957e4"  # pragma: allowlist secret
        or authority_delivery.get("merge_commit_parent_sha") != T0705_CANDIDATE_PREFLIGHT_HEAD
        or authority_delivery.get("merge_commit_sha") != T0705_AUTHORITY_CONTEXT_HEAD
        or authority_delivery.get("merge_commit_sha") != authority_workflow.get("workflow_head_sha")
        or authority_workflow.get("run_id") != 30204453383
        or authority_workflow.get("run_attempt") != 1
        or authority_workflow.get("reruns") != 0
        or authority_jobs.get("authority_context") != "FAILED"
        or authority_jobs.get("candidate_validation") != "SKIPPED"
        or authority_jobs.get("protected_environment") != "SKIPPED"
        or authority_jobs.get("live_schedule_hold") != "SKIPPED"
        or authority_failure.get("reason_code") != "ONE_SHOT_AUTHORITY_VARIABLE_SCOPE_MISMATCH"
        or authority_failure.get("finding")
        != "AUTHORITY_JOB_CANNOT_READ_ENVIRONMENT_SCOPED_VARIABLE"
        or authority_failure.get("exact_root_cause_claimed") is not True
        or authority_effects.get("checkout_started") is not False
        or authority_effects.get("protected_environment_entered") is not False
        or any(
            authority_effects.get(key) != 0
            for key in (
                "protected_secret_names_injected",
                "gmail_api_calls",
                "private_repository_calls",
                "gmail_mutations",
                "private_repository_mutations",
                "timeline_mutations",
                "checkpoint_mutations",
                "platform_schedule_events",
            )
        )
        or authority_effects.get("environment_scoped_one_shot_authority_after_cleanup") != "ABSENT"
        or authority_effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
        or authority_effects.get("production_enablement_variable_after_failure") != "ABSENT"
        or authority_policy.get("same_head_rerun_allowed") is not False
        or authority_policy.get("failed_head_redispatch_allowed") is not False
        or authority_policy.get("frozen_authority_context_head_shas")
        != [T0705_AUTHORITY_CONTEXT_HEAD]
        or authority_policy.get("next_candidate_scope")
        != "REPOSITORY_SCOPED_ONE_SHOT_AUTHORITY_PLUS_DERIVED_BINDINGS_ONLY"
        or authority_policy.get("next_candidate_dispatch_limit") != 1
        or authority_policy.get("protected_ga_rehearsal_dispatches_consumed") != 9
        or authority_policy.get("protected_ga_rehearsal_reruns") != 0
        or authority_policy.get("protected_environment_entries_for_failed_dispatch") != 0
        or any(value is not False for value in authority_claims.values())
    ):
        raise ValueError("protected T0705 authority-context attempt ledger is not exact or frozen")

    ga_schedule_planning_errors = list(
        Draft202012Validator(
            ga_schedule_planning_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_schedule_planning_ledger)
    )
    schedule_workflow = ga_schedule_planning_ledger.get("workflow", {})
    schedule_jobs = ga_schedule_planning_ledger.get("jobs", {})
    schedule_failure = ga_schedule_planning_ledger.get("failure", {})
    schedule_effects = ga_schedule_planning_ledger.get("effects", {})
    schedule_policy = ga_schedule_planning_ledger.get("completion_policy", {})
    schedule_claims = ga_schedule_planning_ledger.get("claims", {})
    if (
        ga_schedule_planning_errors
        or _sha256(root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_PATH)
        != "c4b746090050897b8548a0ec07ed162e807477ed5f3e9047c8c185fb083e45eb"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "a3587e687e74aad18fa4d2259484cde1759ed7825d84de10af94f37fbe594654"  # pragma: allowlist secret  # noqa: E501
        or ga_schedule_planning_ledger.get("scope")
        != "PROTECTED_ENVIRONMENT_PRE_DATA_PLANE_SCHEDULE_PLANNING_ONLY"
        or schedule_workflow.get("workflow_head_sha") != T0705_SCHEDULE_PLANNING_HEAD
        or schedule_workflow.get("run_id") != 30205924236
        or schedule_workflow.get("run_attempt") != 1
        or schedule_workflow.get("reruns") != 0
        or schedule_jobs.get("authority_context") != "PASS"
        or schedule_jobs.get("candidate_validation") != "PASS"
        or schedule_jobs.get("protected_environment") != "FAILED"
        or schedule_jobs.get("plaintext_cleanup") != "PASS"
        or schedule_failure.get("phase") != "SCHEDULE_PLANNING"
        or schedule_failure.get("reason_code") != "PROTECTED_GA_SCHEDULE_PLANNING_FAILED"
        or schedule_failure.get("finding") != "WALL_CLOCK_BEFORE_0430_REJECTED_SCHEDULE_REHEARSAL"
        or schedule_failure.get("exact_root_cause_claimed") is not True
        or schedule_failure.get("taskpack_fake_clock_policy_was_not_applied") is not True
        or schedule_effects.get("protected_environment_entered") is not True
        or schedule_effects.get("protected_secret_names_injected") != 8
        or schedule_effects.get("schedule_checkpoint_recovery") != "PASS"
        or schedule_effects.get("private_repository_read_calls")
        != "NONZERO_WITHIN_CONFIGURED_BUDGET"
        or any(
            schedule_effects.get(key) != 0
            for key in (
                "gmail_api_calls",
                "verified_full_raw_reads",
                "gmail_mutations",
                "private_repository_mutations",
                "raw_mutations",
                "processed_mutations",
                "timeline_mutations",
                "checkpoint_mutations",
                "platform_schedule_events",
            )
        )
        or schedule_effects.get("tmpfs_plaintext_cleanup") != "PASS"
        or schedule_effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
        or schedule_effects.get("production_enablement_variable_after_failure") != "ABSENT"
        or schedule_policy.get("same_head_rerun_allowed") is not False
        or schedule_policy.get("failed_head_redispatch_allowed") is not False
        or schedule_policy.get("frozen_schedule_planning_head_shas")
        != [T0705_SCHEDULE_PLANNING_HEAD]
        or schedule_policy.get("next_candidate_scope")
        != "DETERMINISTIC_HISTORICAL_REPLAY_CLOCK_ONLY_PLUS_DERIVED_BINDINGS"
        or schedule_policy.get("next_candidate_dispatch_limit") != 1
        or schedule_policy.get("protected_ga_rehearsal_dispatches_consumed") != 10
        or schedule_policy.get("protected_ga_rehearsal_reruns") != 0
        or schedule_policy.get("real_time_wait_allowed") is not False
        or schedule_policy.get("rehearsal_clock_fixture_utc") != "2026-07-26T01:00:00Z"
        or schedule_claims.get("candidate_validation_executed") is not True
        or schedule_claims.get("protected_ga_data_plane_executed") is not False
        or any(
            schedule_claims.get(key) is not False
            for key in (
                "production_health_claimed",
                "t0705_pass_claimed",
                "stage7_complete_claimed",
                "final_acceptance_claimed",
                "final_publication_claimed",
            )
        )
    ):
        raise ValueError("protected T0705 schedule-planning attempt ledger is not exact or frozen")

    ga_authentication_clock_errors = list(
        Draft202012Validator(
            ga_authentication_clock_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_authentication_clock_ledger)
    )
    auth_clock_workflow = ga_authentication_clock_ledger.get("workflow", {})
    auth_clock_jobs = ga_authentication_clock_ledger.get("jobs", {})
    auth_clock_failure = ga_authentication_clock_ledger.get("failure", {})
    auth_clock_effects = ga_authentication_clock_ledger.get("effects", {})
    auth_clock_policy = ga_authentication_clock_ledger.get("completion_policy", {})
    auth_clock_claims = ga_authentication_clock_ledger.get("claims", {})
    if (
        ga_authentication_clock_errors
        or _sha256(root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_PATH)
        != "4881b45d1013bc68a8b2f4549b88bc42eb7d9c7d3e2897d76270bb6c83c1efe9"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "bba6e330cee067128c6c14b4dd7333900e1e175beede90fbc93ce390a897782a"  # pragma: allowlist secret  # noqa: E501
        or ga_authentication_clock_ledger.get("scope")
        != "PROTECTED_ENVIRONMENT_PRE_REPOSITORY_RESOLUTION_GITHUB_APP_AUTHENTICATION_ONLY"
        or auth_clock_workflow.get("workflow_head_sha") != T0705_AUTHENTICATION_CLOCK_HEAD
        or auth_clock_workflow.get("run_id") != 30207628898
        or auth_clock_workflow.get("run_attempt") != 1
        or auth_clock_workflow.get("reruns") != 0
        or auth_clock_jobs.get("authority_context") != "PASS"
        or auth_clock_jobs.get("candidate_validation") != "PASS"
        or auth_clock_jobs.get("protected_environment") != "FAILED"
        or auth_clock_jobs.get("live_schedule_hold") != "SKIPPED"
        or auth_clock_jobs.get("plaintext_cleanup") != "PASS"
        or auth_clock_failure.get("phase") != "GITHUB_APP_TOKEN"
        or auth_clock_failure.get("reason_code") != "PROTECTED_GA_GITHUB_APP_TOKEN_FAILED"
        or auth_clock_failure.get("installation_token_failure_class") != "AUTHENTICATION_REJECTED"
        or auth_clock_failure.get("finding") != "HISTORICAL_REHEARSAL_CLOCK_REUSED_FOR_SECURITY_JWT"
        or auth_clock_failure.get("public_payload_exact_root_cause_claimed") is not False
        or auth_clock_failure.get("ledger_exact_root_cause_claimed") is not True
        or auth_clock_effects.get("protected_environment_entered") is not True
        or auth_clock_effects.get("protected_secret_names_injected") != 8
        or auth_clock_effects.get("github_app_token_exchange") != "AUTHENTICATION_REJECTED"
        or auth_clock_effects.get("repository_resolution_reached") is not False
        or auth_clock_effects.get("gmail_oauth_exchange_reached") is not False
        or any(
            auth_clock_effects.get(key) != 0
            for key in (
                "gmail_api_calls",
                "verified_full_raw_reads",
                "private_repository_calls",
                "gmail_mutations",
                "private_repository_mutations",
                "raw_mutations",
                "processed_mutations",
                "timeline_mutations",
                "checkpoint_mutations",
                "platform_schedule_events",
            )
        )
        or auth_clock_effects.get("tmpfs_plaintext_cleanup") != "PASS"
        or auth_clock_effects.get("repository_scoped_one_shot_authority_after_cleanup") != "ABSENT"
        or auth_clock_effects.get("production_enablement_variable_after_failure") != "ABSENT"
        or auth_clock_policy.get("same_head_rerun_allowed") is not False
        or auth_clock_policy.get("failed_head_redispatch_allowed") is not False
        or auth_clock_policy.get("frozen_authentication_clock_head_shas")
        != [T0705_AUTHENTICATION_CLOCK_HEAD]
        or auth_clock_policy.get("next_candidate_scope")
        != "SECURITY_AND_SCHEDULE_CLOCK_DECOUPLING_ONLY_PLUS_DERIVED_BINDINGS"
        or auth_clock_policy.get("next_candidate_dispatch_limit") != 1
        or auth_clock_policy.get("protected_ga_rehearsal_dispatches_consumed") != 11
        or auth_clock_policy.get("protected_ga_rehearsal_reruns") != 0
        or auth_clock_policy.get("security_clock_mode") != "LIVE_UTC"
        or auth_clock_policy.get("schedule_clock_mode") != "DETERMINISTIC_HISTORICAL_REPLAY_FIXTURE"
        or auth_clock_policy.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T13:00:00Z"
        or auth_clock_policy.get("known_data_effect_upper_bound_utc") != "2026-07-26T05:44:53Z"
        or auth_clock_policy.get("real_time_wait_allowed") is not False
        or auth_clock_claims.get("candidate_validation_executed") is not True
        or auth_clock_claims.get("protected_ga_data_plane_executed") is not False
        or any(
            auth_clock_claims.get(key) is not False
            for key in (
                "production_health_claimed",
                "t0705_pass_claimed",
                "stage7_complete_claimed",
                "final_acceptance_claimed",
                "final_publication_claimed",
            )
        )
    ):
        raise ValueError("protected T0705 authentication-clock attempt ledger is not exact")

    ga_raw_recovery_errors = list(
        Draft202012Validator(
            ga_raw_recovery_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_raw_recovery_ledger)
    )
    raw_recovery_workflow = ga_raw_recovery_ledger.get("workflow", {})
    raw_recovery_jobs = ga_raw_recovery_ledger.get("jobs", {})
    raw_recovery_failure = ga_raw_recovery_ledger.get("failure", {})
    raw_recovery_effects = ga_raw_recovery_ledger.get("effects", {})
    raw_recovery_ab = ga_raw_recovery_ledger.get("read_only_representation_ab", {})
    raw_recovery_policy = ga_raw_recovery_ledger.get("completion_policy", {})
    raw_recovery_claims = ga_raw_recovery_ledger.get("claims", {})
    if (
        ga_raw_recovery_errors
        or _sha256(root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_PATH)
        != "69dfae428aacfa3f20748472027dc89cf8d625c57bcbeb8cdb7f9315b743fd65"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "b0457d69d11d6be3cff0edd5b3a4db4ff7a5a7c8306b88670111f5f3d801ad51"  # pragma: allowlist secret  # noqa: E501
        or ga_raw_recovery_ledger.get("scope")
        != "PROTECTED_ENVIRONMENT_VERIFIED_PIPELINE_RAW_RECOVERY_ONLY"
        or raw_recovery_workflow.get("workflow_head_sha") != T0705_RAW_RECOVERY_HEAD
        or raw_recovery_workflow.get("run_id") != 30209560542
        or raw_recovery_workflow.get("run_attempt") != 1
        or raw_recovery_workflow.get("reruns") != 0
        or raw_recovery_jobs.get("authority_context") != "PASS"
        or raw_recovery_jobs.get("candidate_validation") != "PASS"
        or raw_recovery_jobs.get("protected_environment") != "FAILED"
        or raw_recovery_jobs.get("live_schedule_hold") != "SKIPPED"
        or raw_recovery_jobs.get("plaintext_cleanup") != "PASS"
        or raw_recovery_failure.get("phase") != "RAW_RECOVERY"
        or raw_recovery_failure.get("reason_code") != "PROTECTED_GA_RAW_RECOVERY_FAILED"
        or raw_recovery_failure.get("finding")
        != "CONTENTS_RAW_MEDIA_REPRESENTATION_DIFFERS_FROM_CANONICAL_GIT_BLOB"
        or raw_recovery_failure.get("public_payload_exact_root_cause_claimed") is not False
        or raw_recovery_failure.get("ledger_exact_root_cause_claimed") is not True
        or raw_recovery_effects.get("first_candidate_full_recovery_before_trash") is not True
        or raw_recovery_effects.get("first_candidate_second_verification_before_trash") is not True
        or raw_recovery_effects.get("first_candidate_trash_outcome")
        != "CONFIRMED_OR_ALREADY_TRASHED"
        or raw_recovery_effects.get("gmail_exact_message_trash_api_calls_claimed") is not False
        or raw_recovery_effects.get("second_candidate_raw_commit_reached") is not True
        or raw_recovery_effects.get("second_candidate_raw_recovery_completed") is not False
        or raw_recovery_effects.get("timeline_mutations") != 0
        or raw_recovery_effects.get("checkpoint_mutations") != 0
        or raw_recovery_effects.get("tmpfs_plaintext_cleanup") != "PASS"
        or raw_recovery_ab.get("contents_raw_media", {}).get("declared_size_match") is not False
        or raw_recovery_ab.get("contents_raw_media", {}).get("canonical_git_blob_sha_match")
        is not False
        or raw_recovery_ab.get("metadata_addressed_git_blob", {}).get("response_sha_match")
        is not True
        or raw_recovery_ab.get("metadata_addressed_git_blob", {}).get("decoded_size_match")
        is not True
        or raw_recovery_ab.get("metadata_addressed_git_blob", {}).get("age_envelope_valid")
        is not True
        or raw_recovery_ab.get("metadata_addressed_git_blob", {}).get(
            "canonical_git_blob_sha_match"
        )
        is not True
        or raw_recovery_policy.get("frozen_raw_recovery_head_shas") != [T0705_RAW_RECOVERY_HEAD]
        or raw_recovery_policy.get("protected_ga_rehearsal_dispatches_consumed") != 12
        or raw_recovery_policy.get("protected_ga_candidate_preflight_dispatches_consumed") != 5
        or raw_recovery_policy.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T19:00:00Z"
        or raw_recovery_policy.get("known_data_effect_upper_bound_utc") != "2026-07-26T16:12:21Z"
        or raw_recovery_policy.get("real_time_wait_allowed") is not False
        or raw_recovery_claims.get("protected_ga_data_plane_executed") is not True
        or raw_recovery_claims.get("exact_gmail_mutation_call_count_claimed") is not False
    ):
        raise ValueError("protected T0705 Raw-recovery attempt ledger is not exact")

    ga_trash_confirmation_errors = list(
        Draft202012Validator(
            ga_trash_confirmation_ledger_schema,
            format_checker=FormatChecker(),
        ).iter_errors(ga_trash_confirmation_ledger)
    )
    trash_workflow = ga_trash_confirmation_ledger.get("workflow", {})
    trash_failure = ga_trash_confirmation_ledger.get("failure", {})
    trash_effects = ga_trash_confirmation_ledger.get("effects", {})
    trash_topology = ga_trash_confirmation_ledger.get("remote_commit_topology", {})
    trash_probe = ga_trash_confirmation_ledger.get("read_only_gmail_representation_probe", {})
    trash_policy = ga_trash_confirmation_ledger.get("remediation_contract", {})
    trash_claims = ga_trash_confirmation_ledger.get("claims", {})
    if (
        ga_trash_confirmation_errors
        or _sha256(root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_PATH)
        != "6a05af65bc8f0045bb5c7d4ce511ff643c07fe1b6a1a6c8190962cd4c5ca598b"  # pragma: allowlist secret  # noqa: E501
        or _sha256(root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_PATH)
        != "5cee0e8e3dc695251f487f482457ea91cab5b240eed7be81891b0d23bf4cb4e8"  # pragma: allowlist secret  # noqa: E501
        or ga_trash_confirmation_ledger.get("scope")
        != "PROTECTED_ENVIRONMENT_VERIFIED_PIPELINE_TRASH_CONFIRMATION_ONLY"
        or trash_workflow.get("workflow_head_sha") != T0705_TRASH_CONFIRMATION_HEAD
        or trash_workflow.get("run_id") != 30212089899
        or trash_workflow.get("run_attempt") != 1
        or trash_workflow.get("reruns") != 0
        or trash_failure.get("phase") != "TRASH_MUTATION"
        or trash_failure.get("reason_code") != "PROTECTED_GA_TRASH_MUTATION_FAILED"
        or trash_failure.get("public_payload_exact_root_cause_claimed") is not False
        or trash_failure.get("ledger_exact_root_cause_claimed") is not False
        or trash_effects.get("raw_and_processed_remote_recovery_reached_before_failure") is not True
        or trash_effects.get("timeline_mutations") != 0
        or trash_effects.get("checkpoint_mutations") != 0
        or trash_effects.get("tmpfs_plaintext_cleanup") != "PASS"
        or trash_topology.get("private_repository_locator_disclosed") is not False
        or trash_topology.get("private_object_paths_disclosed") is not False
        or trash_topology.get("timeline_or_checkpoint_commit_present") is not False
        or trash_probe.get("message_bodies_read") is not False
        or trash_probe.get("message_mutations") != 0
        or trash_probe.get("minimal_response_contains_nonempty_snippet") is not True
        or trash_probe.get("exact_partial_response_required") != "id,labelIds"
        or trash_policy.get("minimal_confirmation_fields") != "id,labelIds"
        or trash_policy.get("uncertain_trash_response_label_reads_maximum") != 1
        or trash_policy.get("trash_mutation_retries_inside_attempt_maximum") != 0
        or trash_policy.get("frozen_trash_confirmation_head_shas")
        != [T0705_TRASH_CONFIRMATION_HEAD]
        or trash_policy.get("protected_ga_rehearsal_dispatches_consumed") != 13
        or trash_policy.get("protected_ga_candidate_preflight_dispatches_consumed") != 5
        or trash_policy.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T19:00:00Z"
        or trash_policy.get("known_data_effect_upper_bound_utc") != "2026-07-26T17:20:17Z"
        or trash_policy.get("real_time_wait_allowed") is not False
        or trash_claims.get("protected_ga_data_plane_executed") is not True
        or trash_claims.get("exact_protected_failure_root_cause_claimed") is not False
        or trash_claims.get("exact_gmail_mutation_call_count_claimed") is not False
    ):
        raise ValueError("protected T0705 Trash-confirmation attempt ledger is not exact")

    t0705_authorization = t0705_contract.get("authorization", {})
    t0705_budget = t0705_contract.get("authorized_effect_budget", {})
    if (
        t0705_contract.get("schema_version") != "moomooau.run-contract.v1"
        or t0705_contract.get("stage_id") != "S7"
        or t0705_contract.get("task_id") != "T0705"
        or t0705_contract.get("baseline_commit") != CURRENT_MAINLINE_BASE_COMMIT
        or t0705_contract.get("baseline_manifest_sha256") != PREDECESSOR_MANIFEST_SHA256
        or t0705_authorization.get("purpose")
        != "T0705_PROTECTED_GA_TRASH_CONFIRMATION_RECOVERY_AND_ENABLEMENT_ONLY"
        or t0705_authorization.get("original_run_contract_sha256")
        != "1c94dfdce8b5809718e2772d422bb6db773f8b9899ad9e719b0ffda11d0053b9"  # pragma: allowlist secret  # noqa: E501
        or t0705_authorization.get("prior_run_contract_sha256")
        != "004f648b027ec68390a864988a537e7064de9224bab738b429c1c093b0ca4722"  # pragma: allowlist secret  # noqa: E501
        or t0705_authorization.get("failed_attempt_ledgers_required") != 9
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
        or t0705_authorization.get("fifth_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("fifth_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("sixth_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("sixth_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("seventh_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("seventh_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("eighth_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("eighth_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("ninth_failed_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("ninth_failed_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("candidate_preflight_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("candidate_preflight_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("authority_context_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("authority_context_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("schedule_planning_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("schedule_planning_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("authentication_clock_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("authentication_clock_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("raw_recovery_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("raw_recovery_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("trash_confirmation_attempt_ledger_sha256")
        != _sha256(root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_PATH)
        or t0705_authorization.get("trash_confirmation_attempt_ledger_schema_sha256")
        != _sha256(root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_PATH)
        or t0705_authorization.get("failed_workflow_head_shas")
        != [
            "eb7ad073ecd7e4e6d0d8b5d39126cc95d3d2427f",  # pragma: allowlist secret
            "e38cd60ed0458cc6ebe7723c26190d17db0bc5f0",  # pragma: allowlist secret
            "cc7c8af9a40122a61ee2549fb365df813cbd4f16",  # pragma: allowlist secret
            "4c207ad539754166fae6642ff4e6850438d3e2fc",  # pragma: allowlist secret
            "64d88e910ab4078bf90e9fa4f7ce01ef87cf02b4",  # pragma: allowlist secret
            "d10f5086e90aa06f4e6373cb0e44111e1f2c36c7",  # pragma: allowlist secret
            "2133673b335a384657c8668b62a1c13055c212cd",  # pragma: allowlist secret
            "8b6faaf9059661edc3153352b8787ddbc4f733f3",  # pragma: allowlist secret
            "6f82e738611e0d2eeeadd2507f738c9e269c91e0",  # pragma: allowlist secret
        ]
        or t0705_authorization.get("failed_candidate_preflight_head_shas")
        != [T0705_CANDIDATE_PREFLIGHT_HEAD]
        or t0705_authorization.get("failed_authority_context_head_shas")
        != [T0705_AUTHORITY_CONTEXT_HEAD]
        or t0705_authorization.get("failed_schedule_planning_head_shas")
        != [T0705_SCHEDULE_PLANNING_HEAD]
        or t0705_authorization.get("failed_authentication_clock_head_shas")
        != [T0705_AUTHENTICATION_CLOCK_HEAD]
        or t0705_authorization.get("failed_raw_recovery_head_shas") != [T0705_RAW_RECOVERY_HEAD]
        or t0705_authorization.get("failed_trash_confirmation_head_shas")
        != [T0705_TRASH_CONFIRMATION_HEAD]
        or t0705_authorization.get("failed_head_rerun_allowed") is not False
        or t0705_authorization.get("failed_head_redispatch_allowed") is not False
        or t0705_authorization.get("t0704_receipt_sha256")
        != _sha256(root / PROTECTED_BLUE_GREEN_RECEIPT_PATH)
        or t0705_authorization.get("t0705_authorized") is not True
        or t0705_authorization.get("t0706_authorized") is not False
        or t0705_authorization.get("controlled_main_delivery_total_limit") != 17
        or t0705_authorization.get("controlled_main_deliveries_consumed") != 15
        or t0705_authorization.get("controlled_main_deliveries_remaining") != 2
        or t0705_authorization.get("ga_rehearsal_dispatches_consumed") != 13
        or t0705_authorization.get("ga_candidate_preflight_dispatches_consumed") != 5
        or t0705_authorization.get("ga_authority_context_scope_failures_consumed") != 1
        or t0705_authorization.get("ga_schedule_planning_clock_failures_consumed") != 1
        or t0705_authorization.get("ga_authentication_clock_coupling_failures_consumed") != 1
        or t0705_authorization.get("ga_raw_recovery_representation_failures_consumed") != 1
        or t0705_authorization.get("ga_trash_confirmation_failures_consumed") != 1
        or t0705_authorization.get("ga_metadata_quarantine_repair_dispatches_consumed") != 1
        or t0705_authorization.get("ga_label_replay_repair_dispatches_consumed") != 1
        or t0705_authorization.get("ga_phase_diagnostic_dispatches_consumed") != 1
        or t0705_authorization.get("ga_processed_plan_diagnostic_dispatches_consumed") != 1
        or t0705_authorization.get("ga_first_import_diagnostic_dispatches_consumed") != 1
        or t0705_authorization.get("ga_exact_pointer_blob_repair_dispatches_consumed") != 1
        or t0705_authorization.get("ga_app_repository_scope_activation_dispatches_consumed") != 1
        or t0705_authorization.get("ga_canonical_git_blob_recovery_dispatch_limit") != 1
        or t0705_authorization.get("ga_deterministic_clock_recovery_dispatch_limit") != 1
        or t0705_authorization.get("ga_security_clock_decoupling_recovery_dispatch_limit") != 1
        or t0705_authorization.get("ga_raw_canonical_git_blob_recovery_dispatch_limit") != 1
        or t0705_authorization.get("ga_trash_confirmation_recovery_dispatch_limit") != 1
        or t0705_authorization.get("ga_first_import_diagnostic_rerun_limit") != 0
        or t0705_authorization.get("security_clock_mode") != "LIVE_UTC"
        or t0705_authorization.get("rehearsal_schedule_clock_mode")
        != "DETERMINISTIC_HISTORICAL_REPLAY_FIXTURE"
        or t0705_authorization.get("rehearsal_schedule_clock_fixture_utc") != "2026-07-26T19:00:00Z"
        or t0705_authorization.get("known_data_effect_upper_bound_utc") != "2026-07-26T17:20:17Z"
        or t0705_authorization.get("manual_environment_reviewers_required") is not False
        or t0705_authorization.get("fixed_calendar_wait_days") != 0
        or t0705_authorization.get("final_publication_authorized") is not False
        or t0705_budget.get("controlled_main_deliveries_total_maximum") != 17
        or t0705_budget.get("controlled_main_deliveries_remaining_maximum") != 2
        or t0705_budget.get("protected_environment_secret_names_maximum") != 8
        or t0705_budget.get("protected_ga_rehearsal_dispatches_total_maximum") != 14
        or t0705_budget.get("protected_ga_rehearsal_dispatches_consumed") != 13
        or t0705_budget.get("protected_ga_candidate_preflight_dispatches_total_maximum") != 6
        or t0705_budget.get("protected_ga_candidate_preflight_dispatches_consumed") != 5
        or t0705_budget.get("protected_ga_authority_context_scope_failures_maximum") != 1
        or t0705_budget.get("protected_ga_authority_context_scope_failures_consumed") != 1
        or t0705_budget.get("protected_ga_schedule_planning_clock_failures_maximum") != 1
        or t0705_budget.get("protected_ga_schedule_planning_clock_failures_consumed") != 1
        or t0705_budget.get("protected_ga_authentication_clock_coupling_failures_maximum") != 1
        or t0705_budget.get("protected_ga_authentication_clock_coupling_failures_consumed") != 1
        or t0705_budget.get("protected_ga_raw_recovery_representation_failures_maximum") != 1
        or t0705_budget.get("protected_ga_raw_recovery_representation_failures_consumed") != 1
        or t0705_budget.get("protected_ga_trash_confirmation_failures_maximum") != 1
        or t0705_budget.get("protected_ga_trash_confirmation_failures_consumed") != 1
        or t0705_budget.get("protected_ga_metadata_quarantine_repair_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_label_replay_repair_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_phase_diagnostic_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_processed_plan_diagnostic_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_first_import_diagnostic_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_first_import_diagnostic_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_exact_pointer_blob_repair_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_exact_pointer_blob_repair_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_app_repository_scope_activation_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_app_repository_scope_activation_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_canonical_git_blob_recovery_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_deterministic_clock_recovery_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_deterministic_clock_recovery_dispatches_consumed") != 1
        or t0705_budget.get("protected_ga_security_clock_decoupling_recovery_dispatches_maximum")
        != 1
        or t0705_budget.get("protected_ga_raw_canonical_git_blob_recovery_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_trash_confirmation_recovery_dispatches_maximum") != 1
        or t0705_budget.get("protected_ga_rehearsal_reruns_maximum") != 0
        or t0705_budget.get("failed_head_reruns_maximum") != 0
        or t0705_budget.get("failed_head_redispatches_maximum") != 0
        or t0705_budget.get("protected_ga_first_import_diagnostic_pipeline_runs_maximum") != 1
        or t0705_budget.get("protected_ga_exact_pointer_blob_repair_pipeline_runs_maximum") != 1
        or t0705_budget.get("protected_ga_app_repository_scope_activation_pipeline_runs_maximum")
        != 1
        or t0705_budget.get("protected_ga_canonical_git_blob_recovery_pipeline_runs_maximum") != 1
        or t0705_budget.get("protected_ga_deterministic_clock_recovery_pipeline_runs_maximum") != 1
        or t0705_budget.get("protected_ga_security_clock_decoupling_recovery_pipeline_runs_maximum")
        != 1
        or t0705_budget.get("protected_ga_raw_canonical_git_blob_recovery_pipeline_runs_maximum")
        != 1
        or t0705_budget.get("protected_ga_trash_confirmation_recovery_pipeline_runs_maximum") != 1
        or t0705_budget.get("platform_schedule_events_during_rehearsal_maximum") != 0
        or t0705_budget.get("gmail_exact_message_trash_mutations_maximum") != 1
        or t0705_budget.get("maximum_live_timeline_assets") != 1
        or t0705_budget.get("production_schedule_enablement_mutations_maximum") != 1
        or t0705_budget.get("t0706_runs_maximum") != 0
    ):
        raise ValueError("T0705 Run Contract is not the exact bounded candidate authority")
    return {
        "schema_version": "moomooau.source-provenance.v34",
        "authorization": {
            "basis": AUTHORIZATION_BASIS,
            "authorized_on": "2026-07-26",
            "authorized_scope": AUTHORIZED_SCOPE,
        },
        "predecessor": {
            "package_id": "MMAU-ARCHIVE-TP-2026-07-26-V1.0.33",
            "version": "1.0.33",
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
            "roadmap": "taskpack/ROADMAP.v1.0.34.md",
            "status_authority": "machine/status/latest.json",
            "workflow_validator": "machine/tools/validate_workflow_matrix.py",
            "publication_status": (
                "CONTROLLED_T0705_TRASH_CONFIRMATION_RECOVERY_CANDIDATE_NOT_FINAL"
            ),
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
            "production_workflow_runs": 15,
            "protected_workflow_runs": (
                attempt_summary["protected_workflow_runs"] + len(m3_attempts) + 16
            ),
            "remote_workflow_runs": (
                attempt_summary["protected_workflow_runs"] + len(m3_attempts) + 18
            ),
            "controlled_main_deliveries": (
                attempt_summary["controlled_main_deliveries"] + len(m3_attempts) + 18
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
            "protected_ga_processed_plan_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_processed_plan_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_PROCESSED_PLAN_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_first_import_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_first_import_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_FIRST_IMPORT_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_pointer_fetch_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_pointer_fetch_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_POINTER_FETCH_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_pointer_blob_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_pointer_blob_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_POINTER_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_canonical_blob_failed_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_canonical_blob_failed_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_CANONICAL_BLOB_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_candidate_preflight_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_candidate_preflight_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_CANDIDATE_PREFLIGHT_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_authority_context_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_authority_context_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_AUTHORITY_CONTEXT_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_schedule_planning_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_schedule_planning_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_SCHEDULE_PLANNING_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_authentication_clock_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_authentication_clock_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_AUTHENTICATION_CLOCK_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_raw_recovery_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_raw_recovery_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_RAW_RECOVERY_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_trash_confirmation_attempt_ledger_sha256": _sha256(
                root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_PATH
            ),
            "protected_ga_trash_confirmation_attempt_ledger_schema_sha256": _sha256(
                root / PROTECTED_GA_TRASH_CONFIRMATION_ATTEMPT_LEDGER_SCHEMA_PATH
            ),
            "protected_ga_environment_reused": "moomooau-beta",
            "protected_ga_secret_names_exact": 8,
            "protected_ga_rehearsal_dispatches": 13,
            "protected_ga_rehearsal_reruns": 0,
            "protected_ga_candidate_preflight_dispatches": 5,
            "protected_ga_candidate_preflight_protected_environment_entries": 0,
            "protected_ga_candidate_preflight_secret_injections": 0,
            "protected_ga_candidate_preflight_head_frozen": True,
            "protected_ga_authority_context_failures": 1,
            "protected_ga_authority_context_checkout_entries": 0,
            "protected_ga_authority_context_protected_environment_entries": 0,
            "protected_ga_authority_context_secret_injections": 0,
            "protected_ga_authority_context_head_frozen": True,
            "protected_ga_schedule_planning_failures": 1,
            "protected_ga_schedule_planning_gmail_api_calls": 0,
            "protected_ga_schedule_planning_gmail_mutations": 0,
            "protected_ga_schedule_planning_private_repository_mutations": 0,
            "protected_ga_schedule_planning_tmpfs_cleanup": "PASS",
            "protected_ga_schedule_planning_head_frozen": True,
            "protected_ga_authentication_clock_failures": 1,
            "protected_ga_authentication_clock_private_repository_calls": 0,
            "protected_ga_authentication_clock_gmail_calls": 0,
            "protected_ga_authentication_clock_mutations": 0,
            "protected_ga_authentication_clock_tmpfs_cleanup": "PASS",
            "protected_ga_authentication_clock_head_frozen": True,
            "protected_ga_raw_recovery_representation_failures": 1,
            "protected_ga_raw_recovery_first_candidate_full_recovery": True,
            "protected_ga_raw_recovery_first_candidate_trash_outcome": (
                "CONFIRMED_OR_ALREADY_TRASHED"
            ),
            "protected_ga_raw_recovery_exact_trash_call_count_claimed": False,
            "protected_ga_raw_recovery_second_candidate_failed": True,
            "protected_ga_raw_recovery_timeline_mutations": 0,
            "protected_ga_raw_recovery_checkpoint_mutations": 0,
            "protected_ga_raw_recovery_head_frozen": True,
            "protected_ga_trash_confirmation_failures": 1,
            "protected_ga_trash_confirmation_exact_root_cause_claimed": False,
            "protected_ga_trash_confirmation_timeline_mutations": 0,
            "protected_ga_trash_confirmation_checkpoint_mutations": 0,
            "protected_ga_trash_confirmation_head_frozen": True,
            "protected_ga_label_confirmation_fields": "id,labelIds",
            "protected_ga_uncertain_trash_confirmation_reads_maximum": 1,
            "protected_ga_trash_mutation_retries_maximum": 0,
            "protected_ga_pipeline_runs": 0,
            "protected_ga_partial_pipeline_runs": 2,
            "protected_ga_failed_attempts": 13,
            "protected_ga_metadata_quarantine_repair_dispatches_consumed": 1,
            "protected_ga_label_replay_repair_dispatches_consumed": 1,
            "protected_ga_phase_diagnostic_dispatches_consumed": 1,
            "protected_ga_processed_plan_diagnostic_dispatches_consumed": 1,
            "protected_ga_first_import_diagnostic_dispatches_consumed": 1,
            "protected_ga_exact_pointer_blob_repair_dispatches_consumed": 1,
            "protected_ga_app_repository_scope_activation_dispatches_consumed": 1,
            "protected_ga_canonical_git_blob_recovery_dispatches_consumed": 1,
            "protected_ga_deterministic_clock_recovery_dispatches_consumed": 1,
            "protected_ga_security_clock_decoupling_recovery_dispatches_consumed": 1,
            "protected_ga_raw_canonical_git_blob_recovery_dispatches_authorized": 1,
            "protected_ga_trash_confirmation_recovery_dispatches_authorized": 1,
            "protected_ga_closed_phase_diagnostics": True,
            "protected_ga_closed_processed_plan_subphase_diagnostics": True,
            "protected_ga_closed_first_import_subphase_diagnostics": True,
            "protected_ga_canonical_git_blob_recovery_verified_live_and_local": True,
            "protected_ga_fourth_attempt_age_encrypted_added_paths": 6,
            "protected_ga_fourth_attempt_timeline_or_checkpoint_path_changes": 0,
            "protected_ga_fourth_attempt_exact_root_cause_claimed": False,
            "protected_ga_fifth_attempt_private_repository_commits": 0,
            "protected_ga_fifth_attempt_processed_writes": 0,
            "protected_ga_fifth_attempt_gmail_mutations": 0,
            "protected_ga_fifth_attempt_exact_root_cause": "UNKNOWN",
            "protected_ga_sixth_attempt_private_repository_commits": 0,
            "protected_ga_sixth_attempt_processed_writes": 0,
            "protected_ga_sixth_attempt_gmail_mutations": 0,
            "protected_ga_sixth_attempt_exact_root_cause": "UNKNOWN",
            "protected_ga_seventh_attempt_private_repository_commits": 0,
            "protected_ga_seventh_attempt_processed_writes": 0,
            "protected_ga_seventh_attempt_gmail_mutations": 0,
            "protected_ga_seventh_attempt_contents_inline_mismatches": 1,
            "protected_ga_seventh_attempt_exact_root_cause": "UNKNOWN",
            "protected_ga_eighth_attempt_private_repository_commits": 0,
            "protected_ga_eighth_attempt_processed_writes": 0,
            "protected_ga_eighth_attempt_gmail_mutations": 0,
            "protected_ga_eighth_attempt_exact_root_cause": "UNKNOWN",
            "owner_confirmed_github_app_repository_scope_activated_after_eighth_attempt": True,
            "protected_ga_repository_scope_verified_before_gmail": True,
            "protected_ga_ninth_attempt_private_repository_commits": 0,
            "protected_ga_ninth_attempt_processed_writes": 0,
            "protected_ga_ninth_attempt_gmail_mutations": 0,
            "protected_ga_ninth_attempt_exact_protected_exception": "NOT_RECEIVED_OR_INSPECTED",
            "protected_ga_contents_raw_media_canonical_validation": "PARTIAL_MULTIPLE_FAILED",
            "protected_ga_git_blob_api_canonical_validation": "ALL_PASS",
            "protected_ga_processed_patched_adapter_live_recovery": "ALL_PASS",
            "protected_ga_raw_patched_adapter_local_recovery": "ALL_PASS",
            "protected_ga_failed_head_frozen": True,
            "protected_ga_safe_deferred_compatibility_repaired_locally": True,
            "protected_ga_metadata_quarantine_repaired_locally": True,
            "protected_ga_persisted_first_import_label_state_replayed_locally": True,
            "protected_ga_second_verification_remains_fail_closed": True,
            "protected_ga_schedule_mode": "SCHEDULE_REHEARSAL",
            "protected_ga_security_clock_mode": "LIVE_UTC",
            "protected_ga_schedule_clock_mode": "DETERMINISTIC_HISTORICAL_REPLAY_FIXTURE",
            "protected_ga_schedule_clock_fixture_utc": "2026-07-26T19:00:00Z",
            "protected_ga_known_data_effect_upper_bound_utc": "2026-07-26T17:20:17Z",
            "protected_ga_schedule_clock_reaches_security_credentials": False,
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
        provenance.get("schema_version") != "moomooau.source-provenance.v34"
        or authorization.get("basis") != AUTHORIZATION_BASIS
        or authorization.get("authorized_scope") != AUTHORIZED_SCOPE
        or effective.get("package_id") != PACKAGE_ID
        or effective.get("version") != PACKAGE_VERSION
        or effective.get("manifest") != MANIFEST_PATH.as_posix()
        or effective.get("roadmap") != "taskpack/ROADMAP.v1.0.34.md"
        or effective.get("status_authority") != "machine/status/latest.json"
        or effective.get("workflow_validator") != "machine/tools/validate_workflow_matrix.py"
        or effective.get("publication_status")
        != "CONTROLLED_T0705_TRASH_CONFIRMATION_RECOVERY_CANDIDATE_NOT_FINAL"
    ):
        failures.append(f"v{provenance_version} provenance identity or authorization mismatch")
    if (
        predecessor.get("manifest") != PREDECESSOR_MANIFEST_PATH.as_posix()
        or predecessor.get("manifest_sha256") != PREDECESSOR_MANIFEST_SHA256
        or predecessor.get("status") != "IMMUTABLE_CONTROL_PREDECESSOR"
    ):
        failures.append("v1.0.33 predecessor provenance mismatch")
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
        failures.append("predecessor v1.0.32 manifest artifact is not preserved")
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
            failures.append("manifest differs from the canonical v1.0.34 package selection")

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
