"""Targeted, deterministic tests for the local S19 whole-stage review."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage19_review import (
    CONTRACT_PATH,
    EVIDENCE_PATH,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FINDINGS_PATH,
    FIXTURE_PATH,
    ORACLE_PATH,
    PHASE_SPECS,
    RESOLVED_FINDINGS,
    Stage19ReviewError,
    build_evidence,
    evaluate_stage_snapshot,
    perform_rollback_drill,
    validate_candidate_preflight,
    write_stage_review_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


@lru_cache(maxsize=1)
def _preflight():
    return validate_candidate_preflight(ROOT)


def _check(identifier: str):
    return next(row for row in _preflight()["checks"] if row["id"] == identifier)


def test_candidate_preflight_passes_without_stage_review_reports() -> None:
    result = _preflight()
    assert result["status"] == "PASS"
    assert result["stage_status"] == "S19_WHOLE_STAGE_REVIEW_PASS"
    assert result["next"] == "S19/GITHUB_STAGE_UPLOAD_READY"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


@pytest.mark.parametrize("phase", list(PHASE_SPECS))
def test_each_signed_phase_receipt_is_current_and_hash_pinned(phase: str) -> None:
    spec = PHASE_SPECS[phase]
    check = _check("S19REVIEW-%s-CURRENT-PHASE-ORACLE" % phase)
    assert check["passed"] is True
    assert sha256_file(ROOT / spec["evidence_path"]) == spec["evidence_sha256"]
    assert sha256_file(ROOT / spec["rollback_path"]) == spec["rollback_sha256"]


def test_frozen_baseline_hashes_remain_exact() -> None:
    rows = [row for row in _preflight()["checks"] if row["id"].startswith("S19REVIEW-BASELINE-")]
    assert len(rows) == 10
    assert all(row["passed"] is True for row in rows)


def test_contract_scope_and_execution_policy_are_exact() -> None:
    assert _check("S19REVIEW-CONTRACT-IDENTITY")["passed"] is True
    assert _check("S19REVIEW-SCOPE-EXACT")["passed"] is True
    assert _check("S19REVIEW-PHASE-RECORDS-EXACT")["passed"] is True
    assert _check("S19REVIEW-NO-FULL-REGRESSION-POLICY")["passed"] is True
    assert strict_json_load(ROOT / CONTRACT_PATH)["execution_policy"] == EXECUTION_POLICY


def test_taskpack_trace_is_closed_for_all_s19_phases() -> None:
    for phase in PHASE_SPECS:
        assert _check("S19REVIEW-%s-TASKPACK-TRACE-EXACT" % phase)["passed"] is True


def test_findings_are_resolved_and_limitations_remain_explicit() -> None:
    findings = strict_json_load(ROOT / FINDINGS_PATH)
    assert _check("S19REVIEW-FINDINGS-AND-LIMITATIONS-EXACT")["passed"] is True
    assert findings["findings"] == RESOLVED_FINDINGS
    assert findings["summary"] == {"total": 3, "open": 0, "resolved": 3, "blocked": 0}


def test_alpha_beta_ga_and_final_delivery_boundaries_are_preserved() -> None:
    for identifier in (
        "S19REVIEW-SOFTWARE-ALPHA-LOCAL-NO-FUNDS-OR-ORDER-GATE",
        "S19REVIEW-MODEL-BETA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-GATE",
        "S19REVIEW-ACTUAL-GA-AND-RETURN-TRUTH-BOUNDARY-GATE",
        "S19REVIEW-FINAL-DELIVERY-NONSECRET-LOCAL-NONPRODUCTION-GATE",
        "S19REVIEW-FINAL-DELIVERY-RELEASE-CHAIN-GATE",
    ):
        assert _check(identifier)["passed"] is True


def test_external_boundary_is_local_no_action_only() -> None:
    result = _preflight()
    assert _check("S19REVIEW-NO-NETWORK-RUNTIME-ACCOUNT-DATABASE-ORDER-DEPLOY-OR-SOAK-BOUNDARY")["passed"] is True
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["snapshot"]["external_action_boundary_preserved"] is True


def test_oracle_is_static_no_network_process_wait_or_order() -> None:
    assert (ROOT / ORACLE_PATH).is_file()
    assert _check("S19REVIEW-ORACLE-STATIC-NO-NETWORK-PROCESS-WAIT-OR-ORDER")["passed"] is True


def test_cli_wiring_is_exact() -> None:
    assert _check("S19REVIEW-CLI-WRITER-AND-VERIFIER-EXACT")["passed"] is True


def test_rollback_drill_keeps_runtime_and_release_blocked() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["recommendation_generated"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert rollback["incremental_cash_spent_aud"] == "0.00"


def test_positive_snapshot_is_no_action_only() -> None:
    case = FIXTURE["cases"][0]
    result = evaluate_stage_snapshot(case["snapshot"])
    assert result["status"] == "S19_STAGE_REVIEW_VERIFIED_NO_ACTION"
    assert result["reason_codes"] == []
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["production_deployed_or_activated"] is False
    assert result["real_time_soak_waited"] is False


@pytest.mark.parametrize("case", FIXTURE["cases"][1:], ids=[case["case_id"] for case in FIXTURE["cases"][1:]])
def test_negative_snapshot_cases_fail_closed(case) -> None:
    result = evaluate_stage_snapshot(case["snapshot"])
    assert result["status"] == case["expected"]["status"]
    assert result["reason_codes"] == case["expected"]["reason_codes"]
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False


def test_malformed_snapshot_fails_closed() -> None:
    with pytest.raises(Stage19ReviewError):
        evaluate_stage_snapshot({"findings_open": 0})


def test_candidate_evidence_build_is_pass_and_remains_nonproduction() -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False)
    assert evidence["status"] == "PASS"
    assert evidence["stage_status"] == "S19_WHOLE_STAGE_REVIEW_PASS"
    assert evidence["release_status"] == "S19_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
    assert evidence["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert evidence["deterministic_replay"] == {"single_pass_fixture_cases": 10, "phase_test_suites_rerun": False, "real_time_wait_performed": False}
    assert rollback["status"] == "PASS"


def test_noncanonical_evidence_directory_is_refused_without_writing() -> None:
    assert not (ROOT / EVIDENCE_PATH).exists()
    with pytest.raises(Stage19ReviewError):
        write_stage_review_evidence(ROOT, ROOT / "machine")
    assert not (ROOT / EVIDENCE_PATH).exists()
