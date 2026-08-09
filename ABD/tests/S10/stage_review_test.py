from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage10_review import (
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FINDINGS_PATH,
    FIXTURE_PATH,
    JUNIT_PATH,
    ORACLE_PATH,
    PHASE_NEXT,
    PHASE_OUTPUTS,
    PHASE_TARGETS,
    PHASE_VERIFIERS,
    REVIEW_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    Stage10ReviewError,
    _check_reports,
    _parse_sums,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    evaluate_stage_snapshot,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_stage_review_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = strict_json_load(ROOT / CONTRACT_PATH)
FINDINGS = strict_json_load(ROOT / FINDINGS_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_test_reports: bool = False) -> dict:
    return _evaluate_contract(root, require_test_reports)


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(".git", ".pytest_cache", ".venv", "__pycache__", "*.pyc"))
    return destination


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


@pytest.fixture(scope="module")
def stage_result() -> dict:
    return validate_candidate_preflight(ROOT)


def test_candidate_preflight_is_offline_and_passes_without_stage_reports(stage_result: dict) -> None:
    assert stage_result["status"] == "PASS", stage_result
    assert stage_result["stage_status"] == "S10_WHOLE_STAGE_REVIEW_PASS"
    assert stage_result["decision"] == "S10_WHOLE_STAGE_REVIEW_PASS"
    assert stage_result["next"] == FIXTURE["expected_next"]
    assert stage_result["release_status"] == FIXTURE["expected_release_status"]
    assert stage_result["summary"]["checks"] >= 78
    assert stage_result["summary"]["failed"] == 0


def test_review_identity_scope_and_no_full_regression_policy_are_exact() -> None:
    assert CONTRACT_ID == "STAGE-REVIEW-S10"
    assert REVIEW_ID == "ABD-S10-WHOLE-STAGE-REVIEW"
    assert CONTRACT["stage_id"] == "S10"
    assert CONTRACT["review_scope"]["phase_ids"] == FIXTURE["expected_phase_ids"]
    assert CONTRACT["review_scope"]["requirement_ids"] == ["REQ-S10-P01", "REQ-S10-P02", "REQ-S10-P03", "REQ-S10-P04"]
    assert CONTRACT["review_scope"]["acceptance_contract_ids"] == ["AC-S10-P01", "AC-S10-P02", "AC-S10-P03", "AC-S10-P04"]
    assert CONTRACT["execution_policy"] == {
        "offline_deterministic_only": True,
        "phase_test_rerun_allowed": False,
        "full_regression_or_real_time_soak_allowed": False,
        "github_upload_performed_by_local_review": False,
        "production_deployed_or_activated": False,
        "incremental_cash_spent_aud": "0.00",
    }


@pytest.mark.parametrize("relative", sorted(CONTRACT["baseline_hashes"]))
def test_baseline_artifact_hash_matches_stage_review_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == CONTRACT["baseline_hashes"][relative]


@pytest.mark.parametrize("phase", FIXTURE["expected_phase_ids"])
def test_phase_records_bind_exact_evidence_rollback_outputs_and_next_state(phase: str) -> None:
    record = next(row for row in CONTRACT["phase_records"] if row["phase_id"] == phase)
    assert record["target"] == PHASE_TARGETS[phase]
    assert record["outputs"] == PHASE_OUTPUTS[phase]
    assert sha256_file(ROOT / record["evidence_path"]) == FIXTURE["expected_phase_evidence_sha256"][phase]
    assert sha256_file(ROOT / record["rollback_path"]) == FIXTURE["expected_phase_rollback_sha256"][phase]
    assert record["expected_next"] == PHASE_NEXT[phase]


@pytest.mark.parametrize("phase", FIXTURE["expected_phase_ids"])
def test_each_signed_phase_receipt_and_current_oracle_remain_verifiable(stage_result: dict, phase: str) -> None:
    row = next(item for item in stage_result["checks"] if item["id"] == "S10REVIEW-%s-CURRENT-PHASE-ORACLE" % phase)
    assert row["passed"] is True, row


@pytest.mark.parametrize("row", FIXTURE["cases"], ids=lambda row: row["case_id"])
def test_frozen_stage_cases_are_fail_closed_and_actionless(row: dict) -> None:
    result = evaluate_stage_snapshot(row["snapshot"])
    assert result["status"] == row["expected"]["status"]
    assert result["reason_codes"] == row["expected"]["reason_codes"]
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        {"phase_receipts_current": 1, "taskpack_trace_closed": True, "temporal_calibration_gates_preserved": True, "conservative_probability_gates_preserved": True, "decimal_determinism_gates_preserved": True, "adverse_perturbation_gate_preserved": True, "external_action_boundary_preserved": True, "portable_evidence": True, "findings_open": 0},
        {"phase_receipts_current": True, "taskpack_trace_closed": True, "temporal_calibration_gates_preserved": True, "conservative_probability_gates_preserved": True, "decimal_determinism_gates_preserved": True, "adverse_perturbation_gate_preserved": True, "external_action_boundary_preserved": True, "portable_evidence": True, "findings_open": -1},
        {"phase_receipts_current": True, "taskpack_trace_closed": True, "temporal_calibration_gates_preserved": True, "conservative_probability_gates_preserved": True, "decimal_determinism_gates_preserved": True, "adverse_perturbation_gate_preserved": True, "external_action_boundary_preserved": True, "portable_evidence": True, "findings_open": False},
    ],
)
def test_malformed_snapshot_fails_closed(snapshot: dict) -> None:
    with pytest.raises(ValueError):
        evaluate_stage_snapshot(snapshot)


def test_stage_controls_preserve_calibration_bootstrap_decimal_and_adverse_gates(stage_result: dict) -> None:
    for identifier in (
        "S10REVIEW-TEMPORAL-CALIBRATION-AND-TIME-ORDER-PRESERVED",
        "S10REVIEW-CONSERVATIVE-BOOTSTRAP-AND-MONOTONICITY-PRESERVED",
        "S10REVIEW-DECIMAL-FIXED-POINT-AND-DUAL-IMPLEMENTATION-PRESERVED",
        "S10REVIEW-ONE-IN-TEN-THOUSAND-ADVERSE-GATE-PRESERVED",
    ):
        row = next(item for item in stage_result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row


def test_cpu_only_deterministic_replay_and_adverse_stability_hold(stage_result: dict) -> None:
    for identifier in ("S10REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", "S10REVIEW-ADVERSE-REPLAY-NO-ACTION"):
        row = next(item for item in stage_result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row
    assert FIXTURE["replay_count"] == 100
    assert FIXTURE["adverse_replay_count"] == 10000


def test_stage_review_source_has_no_network_process_sleep_float_or_order_capability(stage_result: dict) -> None:
    row = next(item for item in stage_result["checks"] if item["id"] == "S10REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY")
    assert row["passed"] is True, row
    assert stage_result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    assert "float(" not in source
    assert "submit_order" not in source
    assert "retry_order" not in source


def test_checksum_parser_accepts_only_the_canonical_checksum_format() -> None:
    parsed = _parse_sums(ROOT / "machine/evidence/SHA256SUMS")
    assert parsed["machine/evidence/artifact_manifest.json"] == sha256_file(ROOT / "machine/evidence/artifact_manifest.json")


def test_findings_preserve_process_gap_provenance_and_upload_is_pending() -> None:
    assert FINDINGS["summary"] == FIXTURE["expected_findings_summary"]
    finding = next(row for row in FINDINGS["findings"] if row["id"] == "S10-REVIEW-001")
    assert finding["status"] == "RESOLVED_IN_STAGE_REVIEW"
    assert "任务包未预置整体复审合同" in finding["title"]
    assert "GitHub 上传" in finding["residual_risk"]
    assert CONTRACT["next_on_pass"] == "S10/GITHUB_STAGE_UPLOAD_READY"


def test_rollback_drill_is_hash_only_and_does_not_change_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["real_time_soak_waited"] is False


def test_build_evidence_binds_current_candidate_without_external_claim(stage_result: dict) -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False)
    assert evidence["status"] == "PASS", evidence["validation"]["summary"]
    assert evidence["validation"] == stage_result
    assert evidence["next"] == FIXTURE["expected_next"]
    assert evidence["hashes"]["code"] == sha256_file(ROOT / ORACLE_PATH)
    assert evidence["decision_sha256"]
    assert rollback["status"] == "PASS"


def test_contract_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    contract = strict_json_load(clone / CONTRACT_PATH)
    contract["next_on_pass"] = "S10/UNSAFE_AUTO_ADVANCE"
    _write_json(clone / CONTRACT_PATH, contract)
    _failed(evaluate_contract(clone), "S10REVIEW-CONTRACT-IDENTITY")


def test_phase_verifier_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import abd_acceptance.stage10_review as review

    for phase in ["P01", "P02", "P03"]:
        monkeypatch.setitem(review.PHASE_VERIFIERS, phase, lambda root, phase=phase: {"status": "PASS", "evidence_sha256": FIXTURE["expected_phase_evidence_sha256"][phase]})
    monkeypatch.setitem(review.PHASE_VERIFIERS, "P04", lambda root: {"status": "FAIL"})
    _failed(evaluate_contract(ROOT), "S10REVIEW-P04-CURRENT-PHASE-ORACLE")


def test_report_required_mode_fails_closed_when_target_report_is_missing(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / JUNIT_PATH).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(clone, FIXTURE, checks, require_test_reports=True)
    row = next(item for item in checks if item["id"] == "S10REVIEW-TARGETED-PYTEST-REPORT")
    assert row["passed"] is False, row


def test_existing_evidence_is_not_claimed_when_required_artifacts_are_absent(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / EVIDENCE_PATH).unlink(missing_ok=True)
    (clone / ROLLBACK_EVIDENCE_PATH).unlink(missing_ok=True)
    with pytest.raises(Stage10ReviewError):
        verify_existing_stage_review_evidence(clone)
