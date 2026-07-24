from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from moomooau_archive.capacity import CapacityAssessment, CapacityState
from moomooau_archive.kill_switch import KillId
from moomooau_archive.patch_lifecycle import (
    OperationsAction,
    OperationsReadinessSnapshot,
    PatchChangeSet,
    PatchImpact,
    PatchLifecycleDecision,
    PatchLifecycleError,
    PatchLifecycleRunContract,
    PatchLifecycleRunner,
)
from moomooau_archive.release_control import GateStatus, ObservationProvenance
from moomooau_archive.stage7_ops import PatchCandidate, PatchLifecycleGate, PatchSurface

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
CANDIDATE_COMMIT = "a" * 40
LAST_VERIFIED_COMMIT = "b" * 40
CONTAINER_DIGEST = "sha256:" + "c" * 64
RUNTIME_CHANGES = PatchChangeSet(("LinzeDatabase/MooMooAU/src/moomooau_archive/m3.py",))


def _green_capacity() -> CapacityAssessment:
    return CapacityAssessment(
        CapacityState.GREEN,
        True,
        True,
        ("CAPACITY_WITHIN_BUDGET",),
    )


def _operations(**overrides: object) -> OperationsReadinessSnapshot:
    values: dict[str, object] = {
        "capacity": _green_capacity(),
        "active_kill_id": None,
        "public_evidence_fresh": True,
        "full_reconciliation_clean": True,
        "protected_recovery_ready": True,
        "benefit_over_cost": True,
        "live_timeline_assets": 1,
        "private_evidence_findings": 0,
    }
    values.update(overrides)
    return OperationsReadinessSnapshot(**values)  # type: ignore[arg-type]


def _candidate(
    changes: PatchChangeSet = RUNTIME_CHANGES,
    **overrides: object,
) -> PatchCandidate:
    values: dict[str, object] = {
        "surfaces": changes.surfaces,
        "rollback_commit": LAST_VERIFIED_COMMIT,
        "candidate_commit_verified": True,
        "rollback_commit_verified": True,
        "immutable_pin_verified": True,
        "hash_lock_verified": True,
        "sbom_verified": True,
        "reproducible_build_verified": True,
        "build_provenance_verified": True,
        "full_test_suite_passed": True,
        "dependency_audit_verified": True,
        "high_or_critical_findings": 0,
        "secret_scan_findings": 0,
        "scope_scan_findings": 0,
        "frozen_baseline_verified": True,
        "synthetic_recovery_passed": True,
        "protected_canary_required": changes.protected_canary_required,
        "protected_canary_passed": changes.protected_canary_required,
    }
    values.update(overrides)
    return PatchCandidate(**values)  # type: ignore[arg-type]


def _contract(
    *,
    provenance: ObservationProvenance = ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
    predecessor_ready: bool | None = None,
    candidate: PatchCandidate | None = None,
    changes: PatchChangeSet = RUNTIME_CHANGES,
    operations: OperationsReadinessSnapshot | None = None,
    last_verified_commit: str = LAST_VERIFIED_COMMIT,
) -> PatchLifecycleRunContract:
    snapshot = operations or _operations()
    predecessor = (
        snapshot.protected_recovery_ready if predecessor_ready is None else predecessor_ready
    )
    return PatchLifecycleRunContract(
        run_id="patch-" + "1" * 32,
        candidate_commit=CANDIDATE_COMMIT,
        last_verified_commit=last_verified_commit,
        candidate_container_digest=CONTAINER_DIGEST,
        provenance=provenance,
        predecessor_ready=predecessor,
        candidate=candidate or _candidate(changes),
        changes=changes,
        operations=snapshot,
    )


def test_t0708_protected_policy_ready_is_not_an_execution_or_health_claim() -> None:
    result = PatchLifecycleRunner().evaluate(_contract())

    assert result.status is GateStatus.READY
    assert result.decision is PatchLifecycleDecision.READY_FOR_OWNER_APPROVED_PROMOTION
    assert result.reason_codes == ()
    assert result.required_actions == (OperationsAction.OWNER_APPROVAL_REQUIRED,)

    public = result.to_public_dict()
    assert public["candidate_commit"] == CANDIDATE_COMMIT
    assert public["rollback_commit"] == LAST_VERIFIED_COMMIT
    assert public["protected_canary_required"] is True
    assert public["patch_applied"] is False
    assert public["production_health_claimed"] is False
    assert public["stage7_completion_claimed"] is False
    assert all(
        public[key] == 0
        for key in (
            "public_repository_writes",
            "private_repository_calls",
            "gmail_calls",
            "secret_reads",
            "workflow_dispatches",
            "deployments",
            "rollback_executions",
            "feature_flag_mutations",
            "m3_mutations",
        )
    )
    rendered = json.dumps(public, sort_keys=True) + repr(result) + repr(result.contract.changes)
    assert RUNTIME_CHANGES.paths[0] not in rendered


def test_t0708_local_policy_cannot_claim_predecessor_canary_or_protected_run() -> None:
    operations = _operations(protected_recovery_ready=False)
    candidate = _candidate(protected_canary_passed=False)
    contract = _contract(
        provenance=ObservationProvenance.LOCAL_SYNTHETIC,
        predecessor_ready=False,
        candidate=candidate,
        operations=operations,
    )
    result = PatchLifecycleRunner().evaluate(contract)

    assert result.status is GateStatus.BLOCKED
    assert result.decision is PatchLifecycleDecision.FREEZE_KEEP_LAST_VERIFIED
    assert set(result.reason_codes) >= {
        "PROTECTED_PATCH_LIFECYCLE_NOT_RUN",
        "T0707_PROTECTED_PREDECESSOR_NOT_READY",
        "PROTECTED_RECOVERY_NOT_READY",
        "PROTECTED_PATCH_CANARY_NOT_PASSED",
    }
    assert set(result.required_actions) >= {
        OperationsAction.FREEZE_PATCH,
        OperationsAction.KEEP_LAST_VERIFIED_COMMIT,
        OperationsAction.HOLD_M3_AND_NEW_WRITES,
    }

    with pytest.raises(PatchLifecycleError, match="frozen boundary"):
        _contract(
            provenance=ObservationProvenance.LOCAL_SYNTHETIC,
            predecessor_ready=True,
        )

    with pytest.raises(PatchLifecycleError, match="frozen boundary"):
        PatchLifecycleRunContract(
            run_id="patch-" + "1" * 32,
            candidate_commit=CANDIDATE_COMMIT,
            last_verified_commit=LAST_VERIFIED_COMMIT,
            candidate_container_digest=CONTAINER_DIGEST,
            provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
            predecessor_ready=True,
            candidate=_candidate(),
            changes=RUNTIME_CHANGES,
            operations=_operations(),
            deployment_allowed=True,
        )


@pytest.mark.parametrize(
    ("override", "reason"),
    (
        ({"candidate_commit_verified": False}, "CANDIDATE_COMMIT_NOT_VERIFIED"),
        ({"rollback_commit_verified": False}, "ROLLBACK_COMMIT_NOT_VERIFIED"),
        ({"immutable_pin_verified": False}, "IMMUTABLE_PIN_NOT_VERIFIED"),
        ({"hash_lock_verified": False}, "HASH_LOCK_NOT_VERIFIED"),
        ({"sbom_verified": False}, "SBOM_NOT_VERIFIED"),
        ({"reproducible_build_verified": False}, "REPRODUCIBLE_BUILD_NOT_VERIFIED"),
        ({"build_provenance_verified": False}, "BUILD_PROVENANCE_NOT_VERIFIED"),
        ({"full_test_suite_passed": False}, "FULL_TEST_SUITE_NOT_PASSED"),
        ({"dependency_audit_verified": False}, "DEPENDENCY_AUDIT_NOT_VERIFIED"),
        ({"high_or_critical_findings": 1}, "HIGH_OR_CRITICAL_FINDING_OPEN"),
        ({"secret_scan_findings": 1}, "SECRET_SCAN_FINDING_OPEN"),
        ({"scope_scan_findings": 1}, "NON_GOAL_SCOPE_FINDING_OPEN"),
        ({"frozen_baseline_verified": False}, "FROZEN_BASELINE_NOT_VERIFIED"),
        ({"synthetic_recovery_passed": False}, "SYNTHETIC_RECOVERY_NOT_PASSED"),
        ({"protected_canary_passed": False}, "PROTECTED_PATCH_CANARY_NOT_PASSED"),
    ),
)
def test_t0708_every_patch_assurance_gate_fails_closed(
    override: dict[str, object],
    reason: str,
) -> None:
    candidate = _candidate(**override)
    report = PatchLifecycleGate().evaluate(candidate)
    assert report.status is GateStatus.BLOCKED
    assert reason in report.reason_codes


@pytest.mark.parametrize(
    ("operations", "reason", "action"),
    (
        (
            _operations(
                capacity=CapacityAssessment(
                    CapacityState.UNKNOWN,
                    False,
                    False,
                    ("OWNER_LFS_BUDGET_NOT_PROVISIONED",),
                )
            ),
            "CAPACITY_UNKNOWN",
            OperationsAction.STOP_BACKFILL,
        ),
        (
            _operations(
                capacity=CapacityAssessment(
                    CapacityState.RED,
                    False,
                    False,
                    ("RED_CAPACITY_SAFETY_THRESHOLD",),
                )
            ),
            "CAPACITY_RED",
            OperationsAction.STOP_BACKFILL,
        ),
        (
            _operations(
                capacity=CapacityAssessment(
                    CapacityState.GREEN,
                    False,
                    False,
                    ("OWNER_WRITE_AUTHORIZATION_REVOKED",),
                )
            ),
            "CAPACITY_WRITE_NOT_AUTHORIZED",
            OperationsAction.HOLD_M3_AND_NEW_WRITES,
        ),
        (
            _operations(active_kill_id=KillId.KILL_009),
            "ACTIVE_KILL_CRITERION",
            OperationsAction.HOLD_ACTIVE_KILL,
        ),
        (
            _operations(public_evidence_fresh=False),
            "PUBLIC_EVIDENCE_STALE",
            OperationsAction.REBUILD_PUBLIC_EVIDENCE,
        ),
        (
            _operations(full_reconciliation_clean=False),
            "FULL_RECONCILIATION_NOT_CLEAN",
            OperationsAction.HOLD_M3,
        ),
        (
            _operations(protected_recovery_ready=False),
            "PROTECTED_RECOVERY_NOT_READY",
            OperationsAction.HOLD_M3_AND_NEW_WRITES,
        ),
        (
            _operations(benefit_over_cost=False),
            "BENEFIT_OVER_COST_NOT_PROVEN",
            OperationsAction.PAUSE_PROCESSED_TIMELINE,
        ),
        (
            _operations(live_timeline_assets=0),
            "LIVE_TIMELINE_ASSET_COUNT_NOT_ONE",
            OperationsAction.REPAIR_SINGLE_TIMELINE,
        ),
        (
            _operations(private_evidence_findings=1),
            "PRIVATE_VALUE_IN_PUBLIC_EVIDENCE",
            OperationsAction.DISABLE_PUBLIC_EVIDENCE,
        ),
    ),
)
def test_t0708_operations_stop_and_remediation_policy_is_deterministic(
    operations: OperationsReadinessSnapshot,
    reason: str,
    action: OperationsAction,
) -> None:
    candidate = _candidate(
        protected_canary_passed=operations.protected_recovery_ready,
    )
    result = PatchLifecycleRunner().evaluate(
        _contract(
            predecessor_ready=operations.protected_recovery_ready,
            candidate=candidate,
            operations=operations,
        )
    )
    assert result.status is GateStatus.BLOCKED
    assert reason in result.reason_codes
    assert action in result.required_actions
    assert OperationsAction.KEEP_LAST_VERIFIED_COMMIT in result.required_actions


def test_t0708_yellow_capacity_limits_derived_data_without_faking_a_red_stop() -> None:
    operations = _operations(
        capacity=CapacityAssessment(
            CapacityState.YELLOW,
            True,
            False,
            ("YELLOW_CAPACITY_SAFETY_THRESHOLD",),
        )
    )
    result = PatchLifecycleRunner().evaluate(_contract(operations=operations))
    assert result.status is GateStatus.READY
    assert result.reason_codes == ()
    assert result.required_actions == (
        OperationsAction.LIMIT_DERIVED_DATA,
        OperationsAction.OWNER_APPROVAL_REQUIRED,
    )


def test_t0708_paths_surfaces_impacts_and_exact_rollback_are_fail_closed() -> None:
    changes = PatchChangeSet(
        (
            ".github/workflows/moomooau-stage7-ci.yml",
            "LinzeDatabase/MooMooAU/requirements/stage6.lock",
        )
    )
    assert changes.surfaces == (
        PatchSurface.GITHUB_ACTION,
        PatchSurface.PYTHON_DEPENDENCY,
    )
    assert changes.impacts == (PatchImpact.SUPPLY_CHAIN,)
    assert changes.protected_canary_required

    with pytest.raises(PatchLifecycleError, match="canonical"):
        PatchChangeSet(("../private-object",))
    with pytest.raises(PatchLifecycleError, match="canonical"):
        PatchChangeSet((RUNTIME_CHANGES.paths[0], RUNTIME_CHANGES.paths[0]))
    with pytest.raises(PatchLifecycleError, match="frozen boundary"):
        _contract(last_verified_commit="d" * 40)
    assurance_only = PatchChangeSet(("LinzeDatabase/MooMooAU/tests/tasks/test_t0708.py",))
    with pytest.raises(PatchLifecycleError, match="frozen boundary"):
        _contract(changes=assurance_only, candidate=_candidate(RUNTIME_CHANGES))

    outside = PatchChangeSet(("PFI/private-runtime.py",))
    outside_result = PatchLifecycleRunner().evaluate(
        _contract(candidate=_candidate(outside), changes=outside)
    )
    assert "PATCH_PATH_OUTSIDE_MOOMOOAU_SCOPE" in outside_result.reason_codes
    assert OperationsAction.REMOVE_SCOPE_DRIFT in outside_result.required_actions


def test_t0708_no_secret_workflow_is_read_only_policy_preflight() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/moomooau-patch-lifecycle.yml").read_text(
        encoding="utf-8"
    )
    assert "zero-production-secret policy preflight" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "validate_stage7.py" in workflow
    assert "--preflight" in workflow
    assert "requirements/stage6.lock" in workflow
    assert "--require-hashes" in workflow
    assert "--no-deps --disable-pip" in workflow
    assert "stage7-patch-sbom.cdx.json" in workflow
    assert "patch_lifecycle.py" in workflow
    assert re.findall(
        r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}",
        workflow,
    ) == ["MOOMOOAU_GOVERNANCE_DEPLOY_KEY"]
    assert "ssh-key: ${{ secrets.MOOMOOAU_GOVERNANCE_DEPLOY_KEY }}" in workflow
    assert "Reject fork pull requests before protected dependency checkout" in workflow
    assert all(
        token not in workflow.casefold()
        for token in (
            "contents: write",
            "schedule:",
            "pull_request_target",
            "actions/cache",
            "upload-artifact",
            "download-artifact",
            "self-hosted",
            "git push",
        )
    )


def test_t0708_stage7_aggregate_closes_t0702_and_authorizes_only_t0703() -> None:
    aggregate = json.loads(
        (PROJECT_ROOT / "evidence/stage7/latest.json").read_text(encoding="utf-8")
    )
    assert aggregate["status"] == "AUTHORIZED_T0703_REPAIR_CANDIDATE_PENDING_PROTECTED_EXECUTION"
    assert (
        aggregate["scoped_preflight"]
        == "PASS_CONTROL_BETA_M3_BLUE_GREEN_TIMELINE_GA_CODEX_AUTO_RECOVERY_AND_PATCH_POLICY"
    )
    assert aggregate["observation"]["recovery_drill_local_mechanism"] == "PASS"
    assert aggregate["observation"]["patch_lifecycle_local_policy"] == "PASS"
    assert aggregate["observation"]["protected_patch_lifecycle"] == "NOT_RUN"
    assert aggregate["implementation_completion_status"] == "LOCAL_MECHANISMS_READY"
    assert aggregate["observation"]["alpha_remote_preflight"] == "PASS"
    assert (
        aggregate["observation"]["beta_real_raw_only"]
        == "PASS_RAW_RECOVERY_100_PERCENT_ZERO_SOURCE_MUTATION"
    )
    assert (
        aggregate["observation"]["beta_public_safe_failure_diagnostics"]
        == "CLOSED_PASS_AFTER_TYPED_METADATA_QUARANTINE"
    )
    assert aggregate["protected_oracles_executed"] == 3
    assert aggregate["protected_oracles_passed"] == 2
    assert aggregate["protected_oracles_failed"] == 1
    assert aggregate["protected_workflow_runs"] == 15
    assert aggregate["production_workflow_runs"] == 0
    assert aggregate["final_acceptances_passed"] == 0
    assert aggregate["delivery_status"] == "CONTROLLED_T0703_DELIVERY_AUTHORIZED_NOT_FINAL"
    assert (
        aggregate["observation"]["m3_deterministic_evidence_run"]
        == "FOUR_FAILED_ZERO_EFFECT_ATTEMPTS_RECOVERY_AUTHORIZED"
    )
    assert (
        "PROTECTED_M3_SAFE_DEFERRED_AGGREGATE_RECOVERY_CANDIDATE_NOT_RUN"
        in aggregate["blocking_conditions"]
    )
