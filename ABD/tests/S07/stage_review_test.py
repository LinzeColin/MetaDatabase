from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage7_review import (
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FINDINGS_PATH,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    ORACLE_PATH,
    PHASE_NEXT,
    PHASE_VERIFIERS,
    PINNED_BASELINE_HASHES,
    PINNED_REVIEW_ARTIFACT_HASHES,
    REVIEW_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SIGNED_STATE_JUNIT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    _check_manifest,
    _check_pins,
    _check_reports,
    _current_code_hash,
    _junit_is_normalized,
    _junit_summary,
    _structural_self_hash,
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


def evaluate_contract(root: Path, require_test_reports: bool = False):
    return _evaluate_contract(root, require_test_reports, _verify_git_history=Path(root).resolve() == ROOT.resolve())


@pytest.fixture(scope="module")
def candidate_result() -> dict:
    return validate_candidate_preflight(ROOT)


@pytest.fixture(scope="module")
def stage_result() -> dict:
    return evaluate_contract(ROOT)


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"))
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_candidate_preflight_passes_without_generated_stage_reports(candidate_result: dict) -> None:
    result = candidate_result
    assert result["status"] == "PASS", result
    assert result["decision"] == "S07_STAGE_REVIEW_CANDIDATE_VALID"
    assert result["next"] == FIXTURE["expected_next"]


def test_whole_stage_review_passes_without_generated_stage_reports(stage_result: dict) -> None:
    result = stage_result
    assert result["status"] == "PASS", result
    assert result["decision"] == "S07_WHOLE_STAGE_REVIEW_PASS"
    assert result["stage_status"] == "S07_WHOLE_STAGE_REVIEW_PASS"
    assert result["summary"]["checks"] >= 35
    assert result["summary"]["failed"] == 0
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_review_identity_scope_and_terminal_state_are_exact() -> None:
    assert CONTRACT_ID == "STAGE-REVIEW-S07"
    assert REVIEW_ID == "ABD-S07-WHOLE-STAGE-REVIEW"
    assert CONTRACT["stage_id"] == "S07"
    assert CONTRACT["review_scope"]["phase_ids"] == ["P01", "P02", "P03", "P04"]
    assert CONTRACT["release_status_on_pass"] == FIXTURE["expected_release_status"]
    assert CONTRACT["next_on_pass"] == FIXTURE["expected_next"]


@pytest.mark.parametrize("relative", sorted(PINNED_REVIEW_ARTIFACT_HASHES))
def test_review_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_REVIEW_ARTIFACT_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_phase_records_bind_exact_evidence_rollback_outputs_and_next_state() -> None:
    assert [record["phase_id"] for record in CONTRACT["phase_records"]] == FIXTURE["expected_phase_ids"]
    for record in CONTRACT["phase_records"]:
        phase = record["phase_id"]
        assert sha256_file(ROOT / record["evidence_path"]) == FIXTURE["expected_phase_evidence_sha256"][phase]
        assert sha256_file(ROOT / record["rollback_path"]) == FIXTURE["expected_phase_rollback_sha256"][phase]
        assert record["expected_next"] == PHASE_NEXT[phase]
        assert len(record["implementation_commit"]) == 40
        assert len(record["implementation_code_sha256"]) == 64


@pytest.mark.parametrize("phase", ["P01", "P02", "P03", "P04"])
def test_each_phase_signed_receipt_and_current_oracle_remain_verifiable(stage_result: dict, phase: str) -> None:
    row = next(item for item in stage_result["checks"] if item["id"] == "S07REVIEW-%s-CURRENT-PHASE-ORACLE" % phase)
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


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        {"identity_confidence": "0.995", "future_information_tolerance": 0, "actual_funds_changed_without_execution": False, "phase_receipts_signed": True, "orphans": {}},
        {"identity_confidence": "0.9950", "future_information_tolerance": False, "actual_funds_changed_without_execution": False, "phase_receipts_signed": True, "orphans": {}},
        {"identity_confidence": "0.9950", "future_information_tolerance": 0, "actual_funds_changed_without_execution": "false", "phase_receipts_signed": True, "orphans": {}},
        {"identity_confidence": "0.9950", "future_information_tolerance": 0, "actual_funds_changed_without_execution": False, "phase_receipts_signed": True, "orphans": {"bad": "not-a-list"}},
    ],
)
def test_malformed_snapshot_fails_closed(snapshot: dict) -> None:
    with pytest.raises(ValueError):
        evaluate_stage_snapshot(snapshot)


def test_deterministic_replay_and_adverse_stability_are_cpu_only(stage_result: dict) -> None:
    result = stage_result
    for identifier in ["S07REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", "S07REVIEW-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ACTION"]:
        row = next(item for item in result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row


def test_review_source_has_no_network_process_or_sleep_capability(stage_result: dict) -> None:
    result = stage_result
    row = next(item for item in result["checks"] if item["id"] == "S07REVIEW-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY")
    assert row["passed"] is True, row


def test_signed_phase_evidence_has_no_local_path_material(stage_result: dict) -> None:
    row = next(item for item in stage_result["checks"] if item["id"] == "S07REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS")
    assert row["passed"] is True, row


def test_findings_are_resolved_and_upload_is_still_pending(stage_result: dict) -> None:
    assert FINDINGS["summary"]["open"] == 0
    assert all(row["status"] == "RESOLVED_IN_REVIEW_CANDIDATE" for row in FINDINGS["findings"])
    result = stage_result
    assert result["next"] == "S07/GITHUB_STAGE_UPLOAD_READY"
    assert result["external_effect_boundary"]["github_upload_performed_by_local_review"] is False


def test_rollback_drill_is_hash_only_and_does_not_change_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["real_time_soak_waited"] is False


def test_build_evidence_binds_current_candidate_without_external_report_claim(monkeypatch: pytest.MonkeyPatch, stage_result: dict) -> None:
    import abd_acceptance.stage7_review as review

    monkeypatch.setattr(review, "evaluate_contract", lambda *args, **kwargs: stage_result)
    evidence, rollback = build_evidence(ROOT, require_test_reports=False)
    assert evidence["status"] == "PASS", evidence
    assert evidence["hashes"]["code"] == _current_code_hash(ROOT)
    assert evidence["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert rollback["status"] == "PASS"


def test_existing_evidence_is_absent_before_write_or_valid_after_write() -> None:
    if (ROOT / EVIDENCE_PATH).is_file():
        result = verify_existing_stage_review_evidence(ROOT)
        assert result["status"] == "PASS", result
    else:
        assert not (ROOT / ROLLBACK_EVIDENCE_PATH).exists()


def test_junit_helpers_accept_existing_reports_only_when_normalized() -> None:
    for relative in (JUNIT_PATH, SIGNED_STATE_JUNIT_PATH, FULL_JUNIT_PATH):
        path = ROOT / relative
        if path.is_file():
            assert _junit_summary(path)["failures"] == 0
            assert _junit_is_normalized(path) is True
        else:
            assert not path.exists()


def test_module_cli_is_scoped_without_global_dispatcher_change() -> None:
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    dispatcher = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert "def main(" in source
    assert "--verify-existing" in source
    assert "stage7_review" not in dispatcher


def test_contract_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    contract = strict_json_load(clone / CONTRACT_PATH)
    contract["next_on_pass"] = "S07/UNSAFE_AUTO_ADVANCE"
    _write_json(clone / CONTRACT_PATH, contract)
    checks: list[dict] = []
    _check_pins(clone, checks, {})
    assert next(row for row in checks if row["id"] == "S07REVIEW-PIN-MACHINE-FACTS-STAGE7_REVIEW_CONTRACT-JSON")["passed"] is False


def test_open_finding_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    findings = strict_json_load(clone / FINDINGS_PATH)
    findings["summary"]["open"] = 1
    _write_json(clone / FINDINGS_PATH, findings)
    checks: list[dict] = []
    _check_pins(clone, checks, {})
    assert next(row for row in checks if row["id"] == "S07REVIEW-PIN-MACHINE-EVIDENCE-S07-STAGE_REVIEW-FINDINGS-JSON")["passed"] is False


def test_phase_verifier_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    for phase in ["P01", "P02", "P03"]:
        monkeypatch.setitem(PHASE_VERIFIERS, phase, lambda root, verify_git_history=True, phase=phase: {"status": "PASS", "next": PHASE_NEXT[phase]})
    monkeypatch.setitem(PHASE_VERIFIERS, "P04", lambda root, verify_git_history=True: {"status": "FAIL", "next": "S07/P04_REMEDIATION_REQUIRED"})
    _failed(evaluate_contract(ROOT), "S07REVIEW-P04-CURRENT-PHASE-ORACLE")


def test_manifest_tamper_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    manifest_path = clone / "machine/evidence/artifact_manifest.json"
    manifest = strict_json_load(manifest_path)
    manifest["files"][0]["sha256"] = "0" * 64
    _write_json(manifest_path, manifest)
    checks: list[dict] = []
    _check_manifest(clone, checks, require_test_reports=False)
    assert next(row for row in checks if row["id"] == "S07REVIEW-ARTIFACT-MANIFEST-COVERAGE")["passed"] is False


def test_report_required_mode_fails_closed_when_target_report_is_missing(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / JUNIT_PATH).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(clone, FIXTURE, checks, require_test_reports=True)
    assert next(row for row in checks if row["id"] == "S07REVIEW-TARGETED-PYTEST-REPORT")["passed"] is False
