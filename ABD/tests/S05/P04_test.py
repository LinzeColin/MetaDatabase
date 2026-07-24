from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.coverage_observability import (
    AFFECTED_JUNIT_PATH,
    CONTRACT_ID,
    DASHBOARD_PATH,
    EVIDENCE_PATH,
    EXPECTED_ARTIFACTS,
    EXPECTED_MODES,
    EXPECTED_NUMERIC_DELTAS,
    EXPECTED_PROVIDERS,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    ORACLE_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    CoverageObservabilityContractError,
    SilentGapOracleError,
    _apply_dashboard_mutation,
    _oracle_for_dashboard,
    _structural_self_hash,
    audit_coverage,
    build_coverage_record,
    build_evidence,
    classify_source_capability,
    evaluate_contract as _evaluate_contract,
    evaluate_gap_threshold,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_signed_receipt_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from abd_acceptance.source_scheduler import verify_existing_phase_evidence as verify_p03_evidence


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = strict_json_load(ROOT / DASHBOARD_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
PROVIDER_CONTRACTS = strict_json_load(ROOT / "provider_contracts.json")
SOURCE_CAPABILITIES = strict_json_load(ROOT / "source_capabilities.json")
RATE_BUDGET = strict_json_load(ROOT / "rate_budget.json")


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(root, require_external_reports, _verify_git_history=Path(root).resolve() == ROOT.resolve())


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


def _capability_budget_pairs():
    budgets = {row["capability_id"]: row for row in RATE_BUDGET["capability_budgets"]}
    return [(row, budgets[row["capability_id"]]) for row in SOURCE_CAPABILITIES["capabilities"]]


def test_baseline_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "COVERAGE_GAPS_EXPLICIT_ZERO_SILENT"
    assert result["phase_status"] == "S05_P04_PASS"
    assert result["production_coverage_status"] == "ZERO_OF_15_REAL_PROVIDER_MODE_UNITS_COVERED_ALL_15_EXPLICIT_GAPS"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S05/STAGE_REVIEW_READY_NOT_STARTED"
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_signed_p03_is_exact_phase_prerequisite() -> None:
    result = verify_p03_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S05_P03_EVIDENCE_VERIFIED"
    assert result["next"] == "S05/P04_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) in {
        PINNED_PHASE_HASHES[relative],
        SUCCESSOR_UNIT_PROFILE_HASHES.get(relative),
    }


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_adapter_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_artifact_identity_and_taskpack_binding_are_exact() -> None:
    assert DASHBOARD["artifact_id"] == "ART-S05-P04-01"
    assert DASHBOARD["acceptance_contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_artifacts"] == EXPECTED_ARTIFACTS
    assert sha256_file(ROOT / ORACLE_PATH) == DASHBOARD["authority"]["silent_gap_oracle"]["sha256"]


def test_silent_gap_oracle_is_offline_stdlib_only() -> None:
    text = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    for token in ["import requests", "import httpx", "import urllib", "import socket", "import subprocess", "from selenium", "from playwright"]:
        assert token not in text
    assert "external_action_performed" in text
    assert "advice_allowed" in text


def test_standalone_oracle_command_passes_without_side_effects() -> None:
    result = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / ORACLE_PATH), str(ROOT / DASHBOARD_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert report["silent_gap_count"] == 0
    assert report["covered_count"] == 0
    assert report["external_action_performed"] is False


def test_dashboard_scope_does_not_claim_real_coverage() -> None:
    scope = DASHBOARD["scope"]
    assert scope["declared_discovery_scope"] == "ALL_OBSERVABLE_MARKETS"
    assert scope["coverage_dimension"] == "SIGNED_PROVIDER_BY_ACCESS_MODE_CONTRACT_MATRIX"
    assert scope["actual_market_universe_enumerated_or_verified"] is False
    assert scope["runtime_provider_coverage_verified"] is False
    assert scope["production_covered_count"] == 0


def test_expected_universe_is_exact_provider_mode_cross_product() -> None:
    expected = [
        (provider, mode)
        for provider in EXPECTED_PROVIDERS
        for mode in EXPECTED_MODES
    ]
    actual = [(row["provider_id"], row["mode"]) for row in DASHBOARD["expected_coverage_units"]]
    assert actual == expected
    assert len(actual) == len(set(actual)) == 15


@pytest.mark.parametrize("capability,budget", _capability_budget_pairs(), ids=lambda pair: pair[0]["capability_id"] if isinstance(pair, tuple) else None)
def test_every_dashboard_record_is_derived_from_signed_capability_and_budget(capability: dict, budget: dict) -> None:
    expected = build_coverage_record(capability, budget, observed_at=FIXTURE["fixed_clock"])
    actual = next(row for row in DASHBOARD["coverage_records"] if row["coverage_unit_id"] == capability["capability_id"])
    assert actual == expected
    assert actual["production_collection_enabled"] is False
    assert actual["runtime_verified"] is False
    assert actual["rate_budget_enabled"] is False
    assert actual["advice_eligible"] is False


@pytest.mark.parametrize("capability,budget", _capability_budget_pairs(), ids=lambda pair: pair[0]["capability_id"] if isinstance(pair, tuple) else None)
def test_classification_is_deterministic_and_never_silently_drops(capability: dict, budget: dict) -> None:
    first = classify_source_capability(copy.deepcopy(capability), copy.deepcopy(budget))
    second = classify_source_capability(copy.deepcopy(capability), copy.deepcopy(budget))
    assert first == second
    assert first["coverage_status"] in DASHBOARD["status_contract"]["allowed_statuses"]
    assert first["reason_code"]
    assert first["recovery_action_id"]


@pytest.mark.parametrize("status,count", FIXTURE["expected_status_counts"].items())
def test_status_counts_are_exact_and_honest(status: str, count: int) -> None:
    actual = sum(row["coverage_status"] == status for row in DASHBOARD["coverage_records"])
    assert actual == count
    assert DASHBOARD["summary"]["status_counts"][status] == count


@pytest.mark.parametrize("record", DASHBOARD["coverage_records"], ids=lambda row: row["coverage_unit_id"])
def test_every_explicit_gap_has_reason_recovery_owner_and_source_lineage(record: dict) -> None:
    assert record["coverage_status"] != "COVERED"
    assert record["reason_code"]
    assert record["recovery_action_id"]
    assert record["action_owner"] in {"SOURCE_GOVERNANCE", "OWNER"}
    assert record["source_state"]
    assert record["source_reason_codes"]
    assert record["source_failure_action"]


@pytest.mark.parametrize("action", DASHBOARD["recovery_actions"], ids=lambda row: row["action_id"])
def test_recovery_action_is_owned_nonempty_and_does_not_mutate_external_state(action: dict) -> None:
    assert action["owner"]
    assert action["action_zh"]
    assert action["changes_external_state"] is False


def test_positive_oracle_result_matches_frozen_fixture() -> None:
    result = _oracle_for_dashboard(DASHBOARD)
    for key, value in FIXTURE["expected_positive_result"].items():
        assert result[key] == value
    assert result["status_counts"] == FIXTURE["expected_status_counts"]


@pytest.mark.parametrize("mutation", FIXTURE["negative_dashboard_mutations"], ids=lambda row: row["id"])
def test_declared_dashboard_fault_fails_closed(mutation: dict) -> None:
    changed = _apply_dashboard_mutation(DASHBOARD, mutation)
    result = _oracle_for_dashboard(changed)
    reasons = [row["reason_code"] for row in result["findings"]]
    assert result["status"] == "FAIL"
    assert result["decision"] == "BLOCK_COVERAGE_AND_ADVICE"
    assert mutation["expected_reason"] in reasons
    assert result["silent_gap_count"] == mutation["expected_silent_gap_count"]
    assert result["advice_allowed"] is False
    assert result["external_action_performed"] is False


@pytest.mark.parametrize("vector", FIXTURE["gap_threshold_vectors"], ids=lambda row: row["value"])
def test_exact_zero_gap_boundary(vector: dict) -> None:
    result = evaluate_gap_threshold(vector["value"])
    assert result["status"] == vector["expected_status"]
    assert result["reason_code"] == vector["expected_reason"]


@pytest.mark.parametrize("value", [True, False, 0, 0.0, None, [], {}, "NaN", "Infinity", "-Infinity", "bad"])
def test_malformed_or_nonfinite_gap_boundary_fails_closed(value) -> None:
    result = evaluate_gap_threshold(value)
    assert result["status"] == "FAIL"
    assert result["decision"] == "BLOCK_COVERAGE_AND_ADVICE"


def test_generic_numeric_deltas_are_exact_and_odds_tick_is_not_applicable() -> None:
    assert [row["value"] for row in FIXTURE["gap_threshold_vectors"]] == EXPECTED_NUMERIC_DELTAS
    assert FIXTURE["adverse_odds_tick"]["applies"] is False
    assert "no odds" in FIXTURE["adverse_odds_tick"]["reason"]


def test_missing_entire_record_collection_is_a_silent_gap_failure() -> None:
    result = audit_coverage(DASHBOARD["expected_coverage_units"], None, DASHBOARD["recovery_actions"], fixed_clock=FIXTURE["fixed_clock"])
    assert result["status"] == "FAIL"
    assert result["silent_gap_count"] >= 1
    assert result["advice_allowed"] is False


def test_missing_expected_universe_fails_closed() -> None:
    result = audit_coverage(None, DASHBOARD["coverage_records"], DASHBOARD["recovery_actions"], fixed_clock=FIXTURE["fixed_clock"])
    assert result["status"] == "FAIL"
    assert result["silent_gap_count"] >= 1


def test_malformed_recovery_catalog_fails_closed() -> None:
    result = audit_coverage(DASHBOARD["expected_coverage_units"], DASHBOARD["coverage_records"], None, fixed_clock=FIXTURE["fixed_clock"])
    assert result["status"] == "FAIL"
    assert any(row["reason_code"] == "RECOVERY_CATALOG_MALFORMED" for row in result["findings"])


def test_duplicate_expected_unit_is_detected_as_silent_gap() -> None:
    expected = copy.deepcopy(DASHBOARD["expected_coverage_units"])
    expected.append(copy.deepcopy(expected[0]))
    result = audit_coverage(expected, DASHBOARD["coverage_records"], DASHBOARD["recovery_actions"], fixed_clock=FIXTURE["fixed_clock"])
    assert result["status"] == "FAIL"
    assert any(row["reason_code"] == "DUPLICATE_EXPECTED_UNIT" for row in result["findings"])


def test_capability_budget_identity_mismatch_raises() -> None:
    capability, budget = _capability_budget_pairs()[0]
    changed = copy.deepcopy(budget)
    changed["capability_id"] = "CAP-SPORTSBET-PUBLIC_BROWSER"
    with pytest.raises(SilentGapOracleError, match="identity"):
        classify_source_capability(capability, changed)


def test_unknown_capability_state_maps_to_explicit_unknown() -> None:
    capability, budget = _capability_budget_pairs()[0]
    changed = copy.deepcopy(capability)
    changed["state"] = "NEW_UNRECOGNIZED_STATE"
    result = classify_source_capability(changed, budget)
    assert result["coverage_status"] == "UNKNOWN"
    assert result["reason_code"] == "SOURCE_IDENTITY_OR_PERMISSION_UNKNOWN"


def test_a_forged_covered_record_without_runtime_gates_fails_closed() -> None:
    changed = copy.deepcopy(DASHBOARD)
    record = changed["coverage_records"][0]
    record.update(
        {
            "coverage_status": "COVERED",
            "reason_code": "ALL_SOURCE_RUNTIME_AND_FRESHNESS_GATES_VERIFIED",
            "recovery_action_id": "MONITOR_FRESHNESS_AND_REVALIDATE",
        }
    )
    result = _oracle_for_dashboard(changed)
    assert any(row["reason_code"] == "COVERED_WITHOUT_ALL_RUNTIME_GATES" for row in result["findings"])
    assert result["advice_allowed"] is False


def test_oracle_replay_is_byte_deterministic() -> None:
    first = _oracle_for_dashboard(copy.deepcopy(DASHBOARD))
    second = _oracle_for_dashboard(copy.deepcopy(DASHBOARD))
    assert first == second
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)
    assert first["input_sha256"] == FIXTURE["expected_positive_result"]["input_sha256"]
    assert first["decision_sha256"] == FIXTURE["expected_positive_result"]["decision_sha256"]


def test_removing_dashboard_record_fails_candidate(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / DASHBOARD_PATH)
    artifact["coverage_records"].pop()
    _write_json(root / DASHBOARD_PATH, artifact)
    _failed(evaluate_contract(root), "S05P04-RECORD-DERIVATION")


def test_enabling_real_rate_budget_fails_candidate(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / "rate_budget.json")
    artifact["capability_budgets"][0].update({"production_collection_enabled": True, "max_dispatches_per_window": 1, "window_seconds": 60})
    _write_json(root / "rate_budget.json", artifact)
    _failed(evaluate_contract(root), "S05P04-BASELINE-PIN-rate_budget_json")


def test_oracle_source_mutation_fails_hash_pin(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / ORACLE_PATH).write_text((root / ORACLE_PATH).read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S05P04-PHASE-PIN-silent_gap_oracle_py")


def test_stage_review_progression_accepts_only_complete_verified_successor() -> None:
    result = evaluate_contract(ROOT)
    check = next(
        row
        for row in result["checks"]
        if row["id"] == "S05P04-STAGE-REVIEW-PROGRESSION"
    )
    assert check["passed"] is True, check
    assert check["detail"]["mode"] in {
        "S05_STAGE_REVIEW_NOT_STARTED",
        "VERIFIED_S05_STAGE_REVIEW_CANDIDATE",
        "VERIFIED_S05_STAGE_REVIEW_SIGNED",
    }


def test_partial_stage_review_candidate_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / "machine/facts/stage5_review_contract.json").write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S05P04-STAGE-REVIEW-PROGRESSION")


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["coverage_proof"]["silent_gap_count"] == 0
    assert first["coverage_proof"]["explicit_gap_count"] == 15
    assert first["coverage_proof"]["covered_count"] == 0
    assert all(row["matched"] is True for row in first["structured_failure_log"])
    assert first["next"] == "S05/STAGE_REVIEW_READY_NOT_STARTED"


def test_rollback_drill_restores_every_changed_artifact() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["artifacts"]) == len(ROLLBACK_ARTIFACTS)
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["external_state_changed"] is False
    assert result["provider_account_api_or_page_accessed"] is False


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, AFFECTED_JUNIT_PATH, FULL_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S05P04-TARGETED-JUNIT")
    assert "S05P04-AFFECTED-JUNIT" in result["summary"]["failed_check_ids"]
    assert "S05P04-FULL-JUNIT" in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(CoverageObservabilityContractError, match="inside the ABD project root"):
        write_phase_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "abd_acceptance", "--contract", CONTRACT_ID, "--evidence", "machine/evidence"], cwd=root, check=False, capture_output=True, text=True)
    assert "contract is not implemented" not in result.stderr


def test_readme_init_and_cli_reference_p04_contract() -> None:
    main = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    init = (ROOT / "abd_acceptance/__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '"AC-S05-P04": write_coverage_observability_phase_evidence' in main
    assert "validate_coverage_observability_candidate" in init
    assert "verify_coverage_observability_evidence" in init
    assert "当前 `S05/P04`" in readme


def test_signed_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = validate_signed_receipt_preflight(ROOT)
    if result["status"] == "PASS":
        verified = verify_existing_phase_evidence(ROOT)
        assert verified["status"] == "PASS", verified
        assert verified["decision"] == "S05_P04_EVIDENCE_VERIFIED"
        with tempfile.TemporaryDirectory() as directory:
            portable_root = _clone_project(Path(directory))
            portable = verify_existing_phase_evidence(portable_root, verify_git_history=False)
            assert portable["status"] == "PASS", portable
            assert portable["decision"] == "S05_P04_EVIDENCE_VERIFIED"
    else:
        assert result["decision"] == "S05_P04_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED"
        assert result["summary"]["failed"] > 0


def test_candidate_preflight_does_not_recursively_verify_p03() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert not any(row["id"] == "S05P04-P03-SIGNED-PREREQUISITE" for row in result["checks"])


def test_artifacts_contain_no_secret_or_machine_specific_path() -> None:
    paths = [DASHBOARD_PATH, ORACLE_PATH, FIXTURE_PATH, Path("abd_acceptance/coverage_observability.py"), Path("tests/S05/P04_test.py")]
    rendered = "\n".join((ROOT / path).read_text(encoding="utf-8", errors="replace") for path in paths)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert ("-----BEGIN " + "PRIVATE KEY-----") not in rendered
    assert ("ghp" + "_") not in rendered


def test_external_effect_boundary_matches_fixture_and_has_no_runtime_claim() -> None:
    assert EXTERNAL_EFFECT_BOUNDARY == FIXTURE["expected_external_effect_boundary"]
    assert set(value for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud") == {False}
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
    assert DASHBOARD["claim_boundary"]["production_coverage_verified"] is False
    assert DASHBOARD["claim_boundary"]["zero_silent_gaps_applies_only_to_pinned_provider_mode_contract_universe"] is True


def test_canonical_financial_order_and_target_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert parameters["target_30pct"]["guaranteed"] is False
    assert parameters["target_30pct"]["shortfall_behavior"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert set(costs["incremental_cash_budget"].values()) == {"0.00"}
