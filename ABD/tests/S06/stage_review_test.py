from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage6_review import (
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    ORACLE_PATH,
    PHASE_DECISIONS,
    PHASE_NEXT,
    PHASE_VERIFIERS,
    PINNED_REVIEW_ARTIFACT_HASHES,
    REVIEW_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SIGNED_STATE_JUNIT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    _current_code_hash,
    _historical_code_hash,
    _integrated_flow,
    _junit_is_normalized,
    _junit_summary,
    _negative_flow,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_stage_review_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = strict_json_load(ROOT / CONTRACT_PATH)
FINDINGS = strict_json_load(ROOT / FINDINGS_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_candidate_preflight_passes_without_external_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S06_STAGE_REVIEW_CANDIDATE_VALID"
    assert result["next"] == FIXTURE["expected_next"]


def test_whole_stage_review_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S06_WHOLE_STAGE_REVIEW_PASS"
    assert result["stage_status"] == "S06_WHOLE_STAGE_REVIEW_PASS"
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [item["id"] for item in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_review_identity_scope_and_terminal_state_are_exact() -> None:
    assert CONTRACT_ID == "STAGE-REVIEW-S06"
    assert REVIEW_ID == "ABD-S06-WHOLE-STAGE-REVIEW"
    assert CONTRACT["stage_id"] == "S06"
    assert CONTRACT["review_scope"]["phase_ids"] == ["P01", "P02", "P03", "P04"]
    assert CONTRACT["release_status_on_pass"] == "NOT_READY_S07_TO_S19_AND_GMAIL_RUNTIME_ACTIVATION_REQUIRED"
    assert CONTRACT["next_on_pass"] == "S06/GITHUB_STAGE_UPLOAD_READY"


@pytest.mark.parametrize("relative", sorted(PINNED_REVIEW_ARTIFACT_HASHES))
def test_review_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_REVIEW_ARTIFACT_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_phase_records_bind_exact_evidence_rollback_outputs_and_next_state() -> None:
    records = CONTRACT["phase_records"]
    assert [record["phase_id"] for record in records] == FIXTURE["expected_phase_ids"]
    for record in records:
        phase = record["phase_id"]
        assert sha256_file(ROOT / record["evidence_path"]) == FIXTURE["expected_phase_evidence_sha256"][phase]
        assert sha256_file(ROOT / record["rollback_path"]) == FIXTURE["expected_phase_rollback_sha256"][phase]
        assert record["required_outputs"]
        assert record["expected_next"] == PHASE_NEXT[phase]
        assert len(record["implementation_commit"]) == 40
        assert len(record["implementation_code_sha256"]) == 64


@pytest.mark.parametrize("phase", ["P01", "P02", "P03", "P04"])
def test_each_phase_signed_receipt_and_current_oracle_remain_verifiable(phase: str) -> None:
    result = PHASE_VERIFIERS[phase](ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["next"] == PHASE_NEXT[phase]
    evidence = strict_json_load(ROOT / ("machine/evidence/EVD-S06-%s.json" % phase))
    assert evidence["decision"] == PHASE_DECISIONS[phase]


def test_s04_delivery_receipt_remains_a_valid_s06_prerequisite() -> None:
    result = evaluate_contract(ROOT)
    row = next(item for item in result["checks"] if item["id"] == "S06REVIEW-S04-DELIVERY-PREREQUISITE")
    assert row["passed"] is True, row


@pytest.mark.parametrize("record", CONTRACT["phase_records"], ids=lambda row: row["phase_id"])
def test_historical_implementation_code_digest_is_exact(record: dict) -> None:
    assert _historical_code_hash(ROOT, record["implementation_commit"], verify_git_history=True) == record["implementation_code_sha256"]


def test_positive_flow_preserves_parses_and_only_prepares_a_request() -> None:
    flow = _integrated_flow(ROOT, FIXTURE)
    assert flow["preservation"]["status"] == "PRESERVED_READBACK_VERIFIED"
    assert [row["status"] for row in flow["security"]] == ["PARSED_SAFE", "PARSED_SAFE"]
    assert flow["decision"]["status"] == "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"
    assert flow["decision"]["gmail_mutation_performed"] is False
    assert flow["dispatch"]["status"] == "TRASH_REQUEST_READY_NO_MUTATION"
    assert flow["restore"]["status"] == "RESTORE_REQUEST_READY_NO_MUTATION"
    assert flow["audit"]["status"] == "AUDIT_PASS"


@pytest.mark.parametrize("label", ["unknown_sender", "failed_authentication", "failed_malware_attestation", "tampered_archive"])
def test_cross_phase_negative_input_always_keeps(label: str) -> None:
    result = _negative_flow(ROOT, FIXTURE)[label]
    assert result["status"] == "KEEP_AND_QUARANTINE"
    assert result["trash_eligible"] is False
    assert result["gmail_mutation_performed"] is False
    assert result["permanent_delete_performed"] is False


def test_stage_review_replays_without_real_time_wait() -> None:
    result = evaluate_contract(ROOT)
    for identifier in [
        "S06REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT",
        "S06REVIEW-ONE-IN-TEN-THOUSAND-UNKNOWN-KEEPS",
        "S06REVIEW-0600-DATA-ONLY-NO-SCHEDULER",
        "S06REVIEW-NO-REAL-TIME-SOAK-BOUNDARY",
    ]:
        row = next(item for item in result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row


def test_no_permanent_delete_and_scope_method_boundary_are_enforced() -> None:
    result = evaluate_contract(ROOT)
    for identifier in [
        "S06REVIEW-NO-SLEEP-OR-PERMANENT-DELETE-CALL",
        "S06REVIEW-GMAIL-SCOPE-AND-METHODS-EXACT",
        "S06REVIEW-NO-NETWORK-OR-PROCESS-IMPORT",
    ]:
        row = next(item for item in result["checks"] if item["id"] == identifier)
        assert row["passed"] is True, row


def test_findings_are_all_resolved_without_a_runtime_claim() -> None:
    assert FINDINGS["summary"]["open"] == 0
    assert all(item["status"] == "RESOLVED_IN_REVIEW_CANDIDATE" for item in FINDINGS["findings"])
    result = evaluate_contract(ROOT)
    assert result["external_effect_boundary"]["gmail_account_or_api_accessed"] is False
    assert result["external_effect_boundary"]["ovh_or_cloudflare_runtime_accessed"] is False
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"


def test_review_artifacts_do_not_contain_secret_or_local_path_material() -> None:
    result = evaluate_contract(ROOT)
    row = next(item for item in result["checks"] if item["id"] == "S06REVIEW-NO-SECRET-OR-LOCAL-PATH")
    assert row["passed"] is True, row


def test_rollback_drill_is_read_only_and_covers_the_declared_artifacts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"]
    assert set(result["artifacts"]) == {item.as_posix() for item in ROLLBACK_ARTIFACTS}
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["real_time_soak_waited"] is False


def test_build_evidence_is_deterministic_before_external_report_binding() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first
    assert first["hashes"]["code"] == _current_code_hash(ROOT)
    assert first["external_effect_boundary"]["gmail_mutation_performed"] is False


def test_existing_evidence_is_absent_before_write_or_valid_after_write() -> None:
    result = verify_existing_stage_review_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
    else:
        assert result["status"] == "FAIL", result


def test_junit_helpers_reject_missing_reports_before_they_are_generated() -> None:
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH, SIGNED_STATE_JUNIT_PATH):
        path = ROOT / relative
        if path.is_file():
            assert _junit_summary(path)["failures"] == 0
            assert _junit_is_normalized(path) is True
        else:
            assert not path.exists()


def test_cli_writer_is_registered() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert "from .stage6_review import write_stage6_review_evidence" in source
    assert '"STAGE-REVIEW-S06": write_stage6_review_evidence' in source


def test_contract_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    contract = strict_json_load(clone / CONTRACT_PATH)
    contract["next_on_pass"] = "S06/UNSAFE_AUTO_ADVANCE"
    _write_json(clone / CONTRACT_PATH, contract)
    _failed(evaluate_contract(clone), "S06REVIEW-PIN-MACHINE-FACTS-STAGE6_REVIEW_CONTRACT-JSON")


def test_findings_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    findings = strict_json_load(clone / FINDINGS_PATH)
    findings["summary"]["open"] = 1
    _write_json(clone / FINDINGS_PATH, findings)
    _failed(evaluate_contract(clone), "S06REVIEW-PIN-MACHINE-EVIDENCE-S06-STAGE_REVIEW-FINDINGS-JSON")


def test_baseline_hash_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/facts/costs.json"
    path.write_text(path.read_text(encoding="utf-8").replace("0.00", "0.01", 1), encoding="utf-8")
    _failed(evaluate_contract(clone), "S06REVIEW-BASELINE-CRITICAL-HASHES")


def test_phase_evidence_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S06-P04.json"
    evidence = strict_json_load(path)
    evidence["next"] = "S06/UNSAFE"
    _write_json(path, evidence)
    _failed(evaluate_contract(clone), "S06REVIEW-P04-RECEIPT-HASHES")


def test_p04_fixture_mutation_fails_closed_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / FIXTURE["p04_fixture_path"]
    p04 = strict_json_load(path)
    p04["sender_state"] = "UNKNOWN"
    _write_json(path, p04)
    _failed(evaluate_contract(clone), "S06REVIEW-FROZEN-MESSAGE-CROSS-PHASE-REQUEST-ONLY")


def test_oracle_source_mutation_fails_structural_integrity_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / ORACLE_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n# test mutation\n", encoding="utf-8")
    _failed(evaluate_contract(clone), "S06REVIEW-ORACLE-STRUCTURAL-HASH")


def test_review_test_mutation_fails_pin_in_a_clone(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / TEST_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\n# test mutation\n", encoding="utf-8")
    _failed(evaluate_contract(clone), "S06REVIEW-PIN-TESTS-S06-STAGE_REVIEW_TEST-PY")


def test_evidence_paths_are_reserved_for_stage_review_only() -> None:
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S06-STAGE-REVIEW.json"
    assert ROLLBACK_EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S06-STAGE-REVIEW_rollback.json"
