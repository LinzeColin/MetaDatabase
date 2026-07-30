from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.capacity_governance import verify_existing_phase_evidence as verify_s04_p04
from abd_acceptance.coverage_observability import verify_existing_phase_evidence as verify_s05_p04
from abd_acceptance.evidence_continuity import verify_existing_phase_evidence as verify_s07_p04
from abd_acceptance.legacy_receipt_compatibility import COMPATIBILITY_ID, MANIFEST_PATH, PINNED_MANIFEST_SHA256, approved_successor_sha256
from abd_acceptance.usability_accessibility import verify_existing_phase_evidence as verify_s03_p04
from abd_acceptance.stage8_review import (
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FINDINGS_PATH,
    FIXTURE_PATH,
    JUNIT_PATH,
    LEGACY_COMPATIBILITY_HELPER_PATH,
    ORACLE_PATH,
    PHASE_NEXT,
    PHASE_VERIFIERS,
    PINNED_BASELINE_HASHES,
    PINNED_REVIEW_ARTIFACT_HASHES,
    REPOSITORY_CI_CONTRACT,
    REPOSITORY_FAST_WORKFLOW_PATH,
    REVIEW_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SIGNED_STATE_JUNIT_PATH,
    TEST_PATH,
    _check_contract_and_findings,
    _check_manifest,
    _check_pins,
    _check_repository_ci_contract,
    _check_reports,
    _current_code_hash,
    _junit_is_normalized,
    _junit_summary,
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
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"))
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


@pytest.fixture(scope="module")
def candidate_result() -> dict:
    return validate_candidate_preflight(ROOT)


@pytest.fixture(scope="module")
def stage_result() -> dict:
    return evaluate_contract(ROOT)


def test_candidate_preflight_passes_without_generated_stage_reports(candidate_result: dict) -> None:
    assert candidate_result["status"] == "PASS", candidate_result
    assert candidate_result["decision"] == "S08_STAGE_REVIEW_CANDIDATE_VALID"
    assert candidate_result["next"] == FIXTURE["expected_next"]


def test_whole_stage_review_passes_without_generated_stage_reports(stage_result: dict) -> None:
    assert stage_result["status"] == "PASS", stage_result
    assert stage_result["decision"] == "S08_WHOLE_STAGE_REVIEW_PASS"
    assert stage_result["stage_status"] == "S08_WHOLE_STAGE_REVIEW_PASS"
    assert stage_result["summary"]["checks"] >= 40
    assert stage_result["summary"]["failed"] == 0
    assert stage_result["release_status"] == FIXTURE["expected_release_status"]
    assert stage_result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert stage_result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert stage_result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_review_identity_scope_and_terminal_state_are_exact() -> None:
    assert CONTRACT_ID == "STAGE-REVIEW-S08"
    assert REVIEW_ID == "ABD-S08-WHOLE-STAGE-REVIEW"
    assert CONTRACT["stage_id"] == "S08"
    assert CONTRACT["review_scope"]["phase_ids"] == ["P01", "P02", "P03", "P04"]
    assert CONTRACT["release_status_on_pass"] == FIXTURE["expected_release_status"]
    assert CONTRACT["next_on_pass"] == FIXTURE["expected_next"]
    assert CONTRACT["repository_ci_contract"] == FIXTURE["repository_ci_contract"] == REPOSITORY_CI_CONTRACT


@pytest.mark.parametrize("relative", sorted(PINNED_REVIEW_ARTIFACT_HASHES))
def test_review_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_REVIEW_ARTIFACT_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_phase_records_bind_exact_evidence_rollback_outputs_and_next_state() -> None:
    assert [record["phase_id"] for record in CONTRACT["phase_records"]] == FIXTURE["expected_phase_ids"]
    for record in CONTRACT["phase_records"]:
        phase = record["phase_id"]
        assert sha256_file(ROOT / record["evidence_path"]) == FIXTURE["expected_phase_evidence_sha256"][phase]
        assert sha256_file(ROOT / record["rollback_path"]) == FIXTURE["expected_phase_rollback_sha256"][phase]
        assert record["expected_next"] == PHASE_NEXT[phase]
        assert len(record["implementation_commit"]) == 40
        assert len(record["pre_review_evidence_sha256"]) == 64


@pytest.mark.parametrize("phase", ["P01", "P02", "P03", "P04"])
def test_each_phase_signed_receipt_and_current_oracle_remain_verifiable(stage_result: dict, phase: str) -> None:
    row = next(item for item in stage_result["checks"] if item["id"] == "S08REVIEW-%s-CURRENT-PHASE-ORACLE" % phase)
    assert row["passed"] is True, row


def test_signed_phase_evidence_is_portable_and_shared_runtime_is_explicit(stage_result: dict) -> None:
    for identifier in ("S08REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS", "S08REVIEW-SHARED-RUNTIME-CONTRACT-EXACT"):
        row = next(item for item in stage_result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row
    for phase in FIXTURE["expected_phase_ids"]:
        evidence = strict_json_load(ROOT / ("machine/evidence/EVD-S08-%s.json" % phase))
        serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        assert "/" + "Users/" not in serialized
        assert "file" + "://" not in serialized


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
        {"probability_sum_within_tolerance": True, "replicated_sources_do_not_change_consensus": True, "single_long_odds_blocked": True, "fresh_confirmed_line_only": True, "stale_or_desynchronized_blocks": True, "signed_receipts_current": True, "portable_evidence": True, "findings_open": -1},
        {"probability_sum_within_tolerance": 1, "replicated_sources_do_not_change_consensus": True, "single_long_odds_blocked": True, "fresh_confirmed_line_only": True, "stale_or_desynchronized_blocks": True, "signed_receipts_current": True, "portable_evidence": True, "findings_open": 0},
        {"probability_sum_within_tolerance": True, "replicated_sources_do_not_change_consensus": True, "single_long_odds_blocked": True, "fresh_confirmed_line_only": True, "stale_or_desynchronized_blocks": True, "signed_receipts_current": True, "portable_evidence": True, "findings_open": False},
    ],
)
def test_malformed_snapshot_fails_closed(snapshot: dict) -> None:
    with pytest.raises(ValueError):
        evaluate_stage_snapshot(snapshot)


def test_deterministic_replay_and_adverse_stability_are_cpu_only(stage_result: dict) -> None:
    for identifier in ("S08REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", "S08REVIEW-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ACTION"):
        row = next(item for item in stage_result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row


def test_review_source_has_no_network_process_or_sleep_capability(stage_result: dict) -> None:
    row = next(item for item in stage_result["checks"] if item["id"] == "S08REVIEW-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY")
    assert row["passed"] is True, row


def test_findings_preserve_provenance_and_upload_is_still_pending(stage_result: dict) -> None:
    assert FINDINGS["summary"] == FIXTURE["expected_findings_summary"]
    finding = next(row for row in FINDINGS["findings"] if row["id"] == "S08-REVIEW-001")
    compatibility_finding = next(row for row in FINDINGS["findings"] if row["id"] == "S08-REVIEW-002")
    ci_finding = next(row for row in FINDINGS["findings"] if row["id"] == "S08-REVIEW-003")
    assert finding["status"] == "RESOLVED_IN_STAGE_REVIEW"
    assert finding["old_to_new_receipt_sha256"] == {
        phase: {"old": FIXTURE["pre_review_receipt_sha256"][phase], "new": FIXTURE["expected_phase_evidence_sha256"][phase]}
        for phase in FIXTURE["expected_phase_ids"]
    }
    assert compatibility_finding["status"] == "RESOLVED_IN_STAGE_REVIEW"
    assert compatibility_finding["affected_contract_ids"] == FIXTURE["legacy_receipt_compatibility"]["contract_ids"]
    assert ci_finding["status"] == "RESOLVED_IN_STAGE_REVIEW"
    assert ci_finding["affected_paths"] == [REPOSITORY_FAST_WORKFLOW_PATH.as_posix()]
    assert ci_finding["fast_gate_timeout_minutes"] == 15
    assert ci_finding["full_regression_or_real_time_soak_allowed"] is False
    assert ci_finding["real_time_soak_waited"] is False
    assert stage_result["next"] == "S08/GITHUB_STAGE_UPLOAD_READY"
    assert stage_result["external_effect_boundary"]["github_upload_performed_by_local_review"] is False


def test_legacy_receipt_successor_compatibility_is_hash_pinned_and_replays() -> None:
    expected = FIXTURE["legacy_receipt_compatibility"]
    document = strict_json_load(ROOT / MANIFEST_PATH)
    assert MANIFEST_PATH.as_posix() == expected["manifest_path"]
    assert sha256_file(ROOT / MANIFEST_PATH) == expected["manifest_sha256"] == PINNED_MANIFEST_SHA256
    assert sha256_file(ROOT / LEGACY_COMPATIBILITY_HELPER_PATH) == expected["helper_sha256"]
    assert document["compatibility_id"] == COMPATIBILITY_ID
    assert document["stage_id"] == "S08"
    assert document["approved_successor_hashes"]
    for path, digest in document["approved_successor_hashes"].items():
        assert approved_successor_sha256(ROOT, path) == digest
    replay = {
        "AC-S03-P04": verify_s03_p04(ROOT),
        "AC-S04-P04": verify_s04_p04(ROOT),
        "AC-S05-P04": verify_s05_p04(ROOT),
        "AC-S07-P04": verify_s07_p04(ROOT),
    }
    assert list(replay) == expected["contract_ids"]
    assert all(result["status"] == "PASS" for result in replay.values()), replay


def test_rollback_drill_is_hash_only_and_does_not_change_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["real_time_soak_waited"] is False


def test_build_evidence_binds_current_candidate_without_external_claim(stage_result: dict) -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False)
    assert evidence["status"] == "PASS", evidence["summary"] if "summary" in evidence else evidence["validation"]["summary"]
    assert evidence["validation"] == stage_result
    assert evidence["next"] == FIXTURE["expected_next"]
    assert evidence["decision_sha256"]
    assert rollback["status"] == "PASS"


def test_candidate_code_hash_is_bound_to_oracle_source() -> None:
    evidence, _ = build_evidence(ROOT, require_test_reports=False)
    assert evidence["hashes"]["code"] == _current_code_hash(ROOT)
    assert ORACLE_PATH.as_posix() in evidence["hashes"]["inputs"]


def test_contract_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    contract = strict_json_load(clone / CONTRACT_PATH)
    contract["next_on_pass"] = "S08/UNSAFE_AUTO_ADVANCE"
    _write_json(clone / CONTRACT_PATH, contract)
    checks: list[dict] = []
    _check_pins(clone, checks, {})
    assert next(row for row in checks if row["id"] == "S08REVIEW-PIN-MACHINE-FACTS-STAGE8_REVIEW_CONTRACT-JSON")["passed"] is False


@pytest.mark.parametrize("mutation", ["workflow_hash", "unscoped_pytest", "full_reference", "sleep_reference"])
def test_repository_ci_contract_tamper_fails_closed_in_a_clone(tmp_path: Path, mutation: str) -> None:
    clone = _clone_project(tmp_path)
    fast_path = clone.parent / REPOSITORY_FAST_WORKFLOW_PATH
    if mutation == "workflow_hash":
        fast_path.write_text(fast_path.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
    elif mutation == "unscoped_pytest":
        fast_path.write_text(fast_path.read_text(encoding="utf-8").replace("python -m pytest -q", "python -m pytest -q tests/S00/stage_review_test.py"), encoding="utf-8")
    elif mutation == "full_reference":
        fast_path.write_text(fast_path.read_text(encoding="utf-8") + "\n# abd-full-regression.yml\n", encoding="utf-8")
    else:
        fast_path.write_text(fast_path.read_text(encoding="utf-8") + "\n# sleep 1\n", encoding="utf-8")
    checks: list[dict] = []
    _check_repository_ci_contract(clone, strict_json_load(clone / CONTRACT_PATH), checks)
    assert next(row for row in checks if row["id"] == "S08REVIEW-REPOSITORY-CI-HASHES")["passed"] is False
    if mutation != "workflow_hash":
        assert next(row for row in checks if row["id"] == "S08REVIEW-REPOSITORY-CI-FAST-TARGETED-GATE")["passed"] is False


def test_open_finding_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    findings = strict_json_load(clone / FINDINGS_PATH)
    findings["summary"]["open"] = 1
    findings["summary"]["resolved"] = 0
    _write_json(clone / FINDINGS_PATH, findings)
    checks: list[dict] = []
    _check_contract_and_findings(strict_json_load(clone / CONTRACT_PATH), strict_json_load(clone / FINDINGS_PATH), strict_json_load(clone / FIXTURE_PATH), checks)
    assert next(row for row in checks if row["id"] == "S08REVIEW-ALL-FINDINGS-RESOLVED")["passed"] is False


def test_phase_verifier_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import abd_acceptance.stage8_review as review

    for phase in ["P01", "P02", "P03"]:
        monkeypatch.setitem(review.PHASE_VERIFIERS, phase, lambda root, phase=phase: {"status": "PASS", "next": PHASE_NEXT[phase]})
    monkeypatch.setitem(review.PHASE_VERIFIERS, "P04", lambda root: {"status": "FAIL", "next": "S08/P04_REMEDIATION_REQUIRED"})
    _failed(evaluate_contract(ROOT), "S08REVIEW-P04-CURRENT-PHASE-ORACLE")


def test_manifest_tamper_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    manifest_path = clone / "machine/evidence/artifact_manifest.json"
    manifest = strict_json_load(manifest_path)
    manifest["files"][0]["sha256"] = "0" * 64
    _write_json(manifest_path, manifest)
    checks: list[dict] = []
    _check_manifest(clone, checks, require_test_reports=False)
    assert next(row for row in checks if row["id"] == "S08REVIEW-ARTIFACT-MANIFEST-COVERAGE")["passed"] is False


def test_report_required_mode_fails_closed_when_target_report_is_missing(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / JUNIT_PATH).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(clone, FIXTURE, checks, require_test_reports=True)
    assert next(row for row in checks if row["id"] == "S08REVIEW-TARGETED-PYTEST-REPORT")["passed"] is False


def test_existing_evidence_is_not_claimed_before_it_is_written(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / EVIDENCE_PATH).unlink(missing_ok=True)
    (clone / ROLLBACK_EVIDENCE_PATH).unlink(missing_ok=True)
    result = verify_existing_stage_review_evidence(clone)
    assert result["status"] == "FAIL"
    assert result["next"] == "S08/STAGE_REVIEW_REMEDIATION_REQUIRED"


def test_junit_helpers_do_not_treat_unfinalized_reports_as_green_evidence() -> None:
    for relative in (JUNIT_PATH, SIGNED_STATE_JUNIT_PATH):
        path = ROOT / relative
        if path.is_file():
            summary = _junit_summary(path)
            if summary["failures"] == 0 and summary["errors"] == 0:
                assert _junit_is_normalized(path) is True
            else:
                assert _junit_is_normalized(path) is False
        else:
            assert not path.exists()
