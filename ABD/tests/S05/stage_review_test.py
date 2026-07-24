from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.coverage_observability import (
    evaluate_contract as evaluate_p04,
    verify_existing_phase_evidence as verify_p04,
)
from abd_acceptance.market_ontology import verify_existing_phase_evidence as verify_p01
from abd_acceptance.source_capabilities import verify_existing_phase_evidence as verify_p02
from abd_acceptance.source_scheduler import verify_existing_phase_evidence as verify_p03
from abd_acceptance.stage5_review import (
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    FINDINGS_PATH,
    FIXED_CLOCK,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PACK_REPORT_PATH,
    PHASE_DECISIONS,
    PHASE_NEXT,
    PINNED_REVIEW_ARTIFACT_HASHES,
    REVIEW_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    SIGNED_STATE_JUNIT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    Stage5ReviewContractError,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_signed_receipt_preflight,
    verify_existing_stage_review_evidence,
    write_stage5_review_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = strict_json_load(ROOT / CONTRACT_PATH)
FINDINGS = strict_json_load(ROOT / FINDINGS_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
ONTOLOGY = strict_json_load(ROOT / "market_ontology.json")
CAPABILITIES = strict_json_load(ROOT / "source_capabilities.json")
CADENCE = strict_json_load(ROOT / "cadence_tests.json")
RATE_BUDGET = strict_json_load(ROOT / "rate_budget.json")
DASHBOARD = strict_json_load(ROOT / "coverage_dashboard.json")
PHASE_VERIFIERS = {
    "P01": verify_p01,
    "P02": verify_p02,
    "P03": verify_p03,
    "P04": verify_p04,
}


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
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_candidate_preflight_passes_without_phase_recursion() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S05_STAGE_REVIEW_CANDIDATE_VALID"
    assert result["summary"]["failed"] == 0
    assert result["next"] == FIXTURE["expected_next"]


def test_whole_stage_review_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S05_WHOLE_STAGE_REVIEW_PASS"
    assert result["stage_status"] == "S05_WHOLE_STAGE_REVIEW_PASS"
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["production_coverage_status"] == "ZERO_OF_15_REAL_PROVIDER_MODE_UNITS_COVERED_ALL_15_EXPLICIT_GAPS"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_contract_identity_scope_and_terminal_state_are_exact() -> None:
    assert CONTRACT_ID == "STAGE-REVIEW-S05"
    assert REVIEW_ID == "ABD-S05-WHOLE-STAGE-REVIEW"
    assert FIXED_CLOCK == "2026-07-24T12:00:00+10:00"
    assert CONTRACT["review_scope"]["phase_ids"] == ["P01", "P02", "P03", "P04"]
    assert CONTRACT["release_status_on_pass"] == "NOT_READY_S06_TO_S19_AND_REAL_SOURCE_RUNTIME_ACTIVATION_REQUIRED"
    assert CONTRACT["next_on_pass"] == "S05/GITHUB_STAGE_UPLOAD_READY"


@pytest.mark.parametrize("relative", sorted(PINNED_REVIEW_ARTIFACT_HASHES))
def test_review_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_REVIEW_ARTIFACT_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_each_phase_record_binds_immutable_evidence_and_rollback() -> None:
    for record in CONTRACT["phase_records"]:
        phase = record["phase_id"]
        assert sha256_file(ROOT / record["evidence_path"]) == FIXTURE["expected_phase_evidence_sha256"][phase]
        assert sha256_file(ROOT / record["rollback_path"]) == FIXTURE["expected_phase_rollback_sha256"][phase]
        assert record["expected_next"] == PHASE_NEXT[phase]
        assert len(record["implementation_commit"]) == 40
        assert len(record["implementation_code_sha256"]) == 64


@pytest.mark.parametrize("phase", ["P01", "P02", "P03", "P04"])
def test_each_phase_signed_receipt_remains_verifiable(phase: str) -> None:
    result = PHASE_VERIFIERS[phase](ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == PHASE_DECISIONS[phase]
    assert result["next"] == PHASE_NEXT[phase]


def test_capability_ids_are_exact_provider_mode_cartesian_product() -> None:
    expected = [
        "CAP-%s-%s" % (provider, mode)
        for provider in FIXTURE["expected_provider_ids"]
        for mode in FIXTURE["expected_modes"]
    ]
    assert [row["capability_id"] for row in CAPABILITIES["capabilities"]] == expected
    assert [row["capability_id"] for row in RATE_BUDGET["capability_budgets"]] == expected
    assert [row["coverage_unit_id"] for row in DASHBOARD["coverage_records"]] == expected


def test_all_real_capabilities_remain_disabled_zero_budget_and_non_advisable() -> None:
    assert all(
        row["production_collection_enabled"] is False
        and row["runtime_verified"] is False
        and row["max_requests_per_period"] == 0
        for row in CAPABILITIES["capabilities"]
    )
    assert all(
        row["production_collection_enabled"] is False
        and row["max_dispatches_per_window"] == 0
        and row["window_seconds"] == 0
        for row in RATE_BUDGET["capability_budgets"]
    )
    assert all(
        row["production_collection_enabled"] is False
        and row["runtime_verified"] is False
        and row["rate_budget_enabled"] is False
        and row["advice_eligible"] is False
        for row in DASHBOARD["coverage_records"]
    )


def test_coverage_summary_is_zero_silent_and_all_explicit() -> None:
    summary = DASHBOARD["summary"]
    assert summary["expected_unit_count"] == 15
    assert summary["represented_unit_count"] == 15
    assert summary["silent_gap_count"] == 0
    assert summary["explicit_gap_count"] == 15
    assert summary["covered_count"] == 0
    assert summary["status_counts"] == FIXTURE["expected_coverage_status_counts"]
    assert summary["all_explicit_gaps_have_reason"] is True
    assert summary["all_explicit_gaps_have_recovery_action"] is True
    assert summary["all_explicit_gaps_have_action_owner"] is True
    assert summary["advice_enabled"] is False


def test_every_gap_references_a_matching_recovery_owner() -> None:
    actions = {row["action_id"]: row for row in DASHBOARD["recovery_actions"]}
    for row in DASHBOARD["coverage_records"]:
        assert row["reason_code"]
        assert actions[row["recovery_action_id"]]["owner"] == row["action_owner"]


def test_synthetic_budget_is_separate_and_cannot_dispatch_externally() -> None:
    synthetic = RATE_BUDGET["frozen_test_only_budget"]
    real_ids = {row["capability_id"] for row in CAPABILITIES["capabilities"]}
    coverage_ids = {row["coverage_unit_id"] for row in DASHBOARD["coverage_records"]}
    assert synthetic["capability_id"] == FIXTURE["expected_synthetic_capability_id"]
    assert synthetic["test_fixture_only"] is True
    assert synthetic["external_action_permitted"] is False
    assert synthetic["capability_id"] not in real_ids
    assert synthetic["capability_id"] not in coverage_ids


def test_fixed_clock_and_stale_input_gates_remain_exact() -> None:
    gate = CADENCE["fixed_clock_gate"]
    freshness = CADENCE["freshness_gate"]
    assert gate["maximum_dispatch_deviation_seconds"] == 2
    assert gate["at_exact_limit"] == "PASS"
    assert gate["above_exact_limit"] == "NO_DISPATCH_NO_ADVICE"
    assert freshness["future_timestamp_action"] == "NO_ADVICE"
    assert freshness["unknown_or_untrusted_clock_action"] == "NO_ADVICE"
    assert freshness["quote_older_than_advice_limit_action"] == "DO_NOT_ENTER_ADVICE_EVALUATION"


def test_declared_scope_is_not_real_market_coverage_evidence() -> None:
    assert ONTOLOGY["declared_discovery_scope"] == "ALL_OBSERVABLE_MARKETS"
    assert ONTOLOGY["claim_boundary"]["actual_provider_or_market_observed"] is False
    assert ONTOLOGY["claim_boundary"]["all_observable_markets_enumerated_or_verified"] is False
    assert DASHBOARD["scope"]["actual_market_universe_enumerated_or_verified"] is False
    assert DASHBOARD["scope"]["runtime_provider_coverage_verified"] is False
    assert DASHBOARD["scope"]["production_covered_count"] == 0


@pytest.mark.parametrize(
    "key",
    [
        "actual_market_universe_enumerated_or_verified",
        "all_observable_markets_verified",
        "provider_permission_or_runtime_access_verified",
        "production_collection_enabled",
        "runtime_freshness_verified",
        "production_coverage_verified",
        "production_advice_enabled",
        "ovh_7x24_runtime_verified",
        "cloudflare_global_chinese_access_verified",
        "gmail_evidence_archival_verified",
        "financial_target_verified_or_guaranteed",
    ],
)
def test_every_production_claim_boundary_remains_false(key: str) -> None:
    assert CONTRACT["claim_boundary"][key] is False


@pytest.mark.parametrize(
    ("key", "value"),
    sorted(CONTRACT["external_effect_boundary"].items()),
)
def test_external_effect_boundary_is_exact(key: str, value) -> None:
    if key == "incremental_cash_spent_aud":
        assert value == "0.00"
    elif key == "owner_final_order_only":
        assert value is True
    else:
        assert value is False


def test_capability_activation_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    changed = strict_json_load(root / "source_capabilities.json")
    changed["capabilities"][0]["production_collection_enabled"] = True
    _write_json(root / "source_capabilities.json", changed)
    _failed(validate_candidate_preflight(root), "S05REVIEW-CAPABILITY-MATRIX")


def test_rate_budget_activation_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    changed = strict_json_load(root / "rate_budget.json")
    changed["capability_budgets"][0]["max_dispatches_per_window"] = 1
    _write_json(root / "rate_budget.json", changed)
    _failed(validate_candidate_preflight(root), "S05REVIEW-RATE-BUDGET-MATRIX")


def test_coverage_unit_removal_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    changed = strict_json_load(root / "coverage_dashboard.json")
    changed["coverage_records"].pop()
    _write_json(root / "coverage_dashboard.json", changed)
    _failed(validate_candidate_preflight(root), "S05REVIEW-COVERAGE-MATRIX")


def test_synthetic_external_action_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    changed = strict_json_load(root / "rate_budget.json")
    changed["frozen_test_only_budget"]["external_action_permitted"] = True
    _write_json(root / "rate_budget.json", changed)
    _failed(validate_candidate_preflight(root), "S05REVIEW-SYNTHETIC-REAL-SOURCE-SEPARATION")


def test_claim_overstatement_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    changed = strict_json_load(root / CONTRACT_PATH)
    changed["claim_boundary"]["all_observable_markets_verified"] = True
    _write_json(root / CONTRACT_PATH, changed)
    _failed(validate_candidate_preflight(root), "S05REVIEW-REAL-MARKET-OVERCLAIM-BOUNDARY")


def test_open_finding_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    changed = strict_json_load(root / FINDINGS_PATH)
    changed["findings"][0]["status"] = "OPEN"
    changed["summary"]["resolved_in_review_candidate"] = 5
    changed["summary"]["open"] = 1
    _write_json(root / FINDINGS_PATH, changed)
    _failed(validate_candidate_preflight(root), "S05REVIEW-ALL-FINDINGS-RESOLVED")


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    text = (root / CONTRACT_PATH).read_text(encoding="utf-8")
    text = text.replace('"schema_version": "1.0.0",', '"schema_version": "1.0.0",\n  "schema_version": "1.0.0",', 1)
    (root / CONTRACT_PATH).write_text(text, encoding="utf-8")
    _failed(validate_candidate_preflight(root), "S05REVIEW-PREFLIGHT-CONTRACT-STRICT-JSON")


def test_p04_progression_accepts_complete_review_candidate() -> None:
    result = evaluate_p04(ROOT, require_external_reports=False, _verify_git_history=True)
    assert result["status"] == "PASS", result
    check = next(row for row in result["checks"] if row["id"] == "S05P04-STAGE-REVIEW-PROGRESSION")
    assert check["passed"] is True
    assert check["detail"]["mode"] in {
        "VERIFIED_S05_STAGE_REVIEW_CANDIDATE",
        "VERIFIED_S05_STAGE_REVIEW_SIGNED",
    }


def test_partial_stage_review_candidate_fails_p04_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / FIXTURE_PATH).unlink()
    result = evaluate_p04(root, require_external_reports=False, _verify_git_history=False)
    _failed(result, "S05P04-STAGE-REVIEW-PROGRESSION")


def test_every_finding_has_a_unique_executed_verification_gate() -> None:
    result = validate_candidate_preflight(ROOT)
    check_ids = {row["id"] for row in result["checks"]}
    gates = [row["verification_gate"] for row in FINDINGS["findings"]]
    assert len(gates) == len(set(gates))
    assert set(gates) <= check_ids


@pytest.mark.parametrize("relative", ROLLBACK_ARTIFACTS)
def test_every_rollback_artifact_is_regular_and_present(relative: Path) -> None:
    assert (ROOT / relative).is_file(), relative


def test_rollback_drill_restores_every_signed_stage_artifact() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"]
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["provider_account_api_or_page_accessed"] is False
    assert result["real_market_data_collected"] is False
    assert result["recommendation_or_order_generated"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_rollback_drill_is_deterministic() -> None:
    assert perform_rollback_drill(ROOT) == perform_rollback_drill(ROOT)


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS"
    assert first["phase_completion"]["phase_count"] == 4
    assert first["phase_completion"]["task_count"] == 12
    assert first["phase_completion"]["pinned_provider_mode_unit_count"] == 15
    assert first["phase_completion"]["explicit_gap_count"] == 15
    assert first["phase_completion"]["silent_gap_count"] == 0
    assert first["phase_completion"]["production_covered_count"] == 0
    assert first["phase_completion"]["real_market_universe_enumerated_or_verified"] is False
    assert first["next"] == FIXTURE["expected_next"]


def test_signed_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = validate_signed_receipt_preflight(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S05_STAGE_REVIEW_SIGNED_PREFLIGHT_VALID"
        verified = verify_existing_stage_review_evidence(ROOT)
        assert verified["status"] == "PASS", verified
        assert verified["decision"] == "S05_STAGE_REVIEW_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S05_STAGE_REVIEW_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED"


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH, SIGNED_STATE_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    for check_id in [
        "S05REVIEW-TARGETED-JUNIT",
        "S05REVIEW-FULL-JUNIT",
        "S05REVIEW-SIGNED-STATE-JUNIT",
    ]:
        assert check_id in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(Stage5ReviewContractError, match="inside the ABD project root"):
        write_stage5_review_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "abd_acceptance",
            "--contract",
            CONTRACT_ID,
            "--evidence",
            "machine/evidence",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert "contract is not implemented" not in result.stderr


def test_taskpack_reports_and_source_receipts_are_exact() -> None:
    assert PACK_REPORT_PATH == Path("machine/evidence/validation_report.json")
    assert SCAN_REPORT_PATH == Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
    sources = CONTRACT["supplied_source_receipts"]
    assert sources[0]["sha256"] == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
    assert sources[1]["sha256"] == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
    assert sources[1]["original_file_count"] == 53


def test_canonical_financial_order_and_no_guarantee_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["product"]["monthly_target_return"] == "0.30"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert parameters["target_30pct"]["guaranteed"] is False
    assert parameters["target_30pct"]["shortfall_behavior"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert set(costs["incremental_cash_budget"].values()) == {"0.00"}


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_boundary_deltas"])
def test_numeric_stability_boundary_remains_exact(delta: str) -> None:
    assert delta in {"-0.0001", "0", "0.0001"}


def test_review_artifacts_contain_no_secret_or_machine_specific_path() -> None:
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        Path("abd_acceptance/stage5_review.py"),
        Path("abd_acceptance/coverage_observability.py"),
    ]
    rendered = "\n".join(
        (ROOT / path).read_text(encoding="utf-8", errors="replace")
        for path in paths
    )
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert ("-----BEGIN " + "PRIVATE KEY-----") not in rendered


def test_cli_and_package_exports_reference_stage_review_contract() -> None:
    main = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    init = (ROOT / "abd_acceptance/__init__.py").read_text(encoding="utf-8")
    assert '"STAGE-REVIEW-S05": write_stage5_review_evidence' in main
    assert "write_stage5_review_evidence" in init
    assert "validate_stage5_review_candidate" in init
    assert "validate_stage5_review_signed_receipt" in init
    assert "verify_stage5_review_evidence" in init
