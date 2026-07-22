from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.market_ontology import verify_existing_phase_evidence as verify_p01_evidence
from abd_acceptance.source_capabilities import (
    AFFECTED_JUNIT_PATH,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXPECTED_ARTIFACTS,
    EXPECTED_MODES,
    EXPECTED_NUMERIC_DELTAS,
    EXPECTED_PROVIDERS,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    PROVIDER_CONTRACTS_PATH,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SOURCE_CAPABILITIES_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SourceCapabilityContractError,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_capability_request,
    validate_candidate_preflight,
    validate_signed_receipt_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
PROVIDER_CONTRACTS = strict_json_load(ROOT / PROVIDER_CONTRACTS_PATH)
SOURCE_CAPABILITIES = strict_json_load(ROOT / SOURCE_CAPABILITIES_PATH)
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


def _mutate(request: dict, mutation: dict) -> dict:
    result = copy.deepcopy(request)
    key = mutation["path"][0]
    if mutation.get("delete") is True:
        result.pop(key, None)
    else:
        result[key] = mutation.get("value")
    return result


def _failed(result: dict, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "SOURCE_CAPABILITY_CONTRACTS_FROZEN_FAIL_CLOSED"
    assert result["phase_status"] == "S05_P02_PASS"
    assert result["production_collection_status"] == "ALL_15_PROVIDER_MODE_CAPABILITIES_DISABLED_PENDING_SOURCE_SPECIFIC_RUNTIME_PROOF"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S05/P03_READY_NOT_STARTED"
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_signed_p01_is_exact_phase_prerequisite() -> None:
    result = verify_p01_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S05_P01_EVIDENCE_VERIFIED"
    assert result["next"] == "S05/P02_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_artifact_identity_and_parent_binding_are_exact() -> None:
    assert PROVIDER_CONTRACTS["artifact_id"] == "ART-S05-P02-01"
    assert SOURCE_CAPABILITIES["artifact_id"] == "ART-S05-P02-02"
    assert PROVIDER_CONTRACTS["acceptance_contract_id"] == SOURCE_CAPABILITIES["acceptance_contract_id"] == CONTRACT_ID
    assert SOURCE_CAPABILITIES["provider_contracts_sha256"] == sha256_file(ROOT / PROVIDER_CONTRACTS_PATH)
    assert FIXTURE["expected_artifacts"] == EXPECTED_ARTIFACTS


def test_authority_hashes_are_pinned_to_signed_inputs() -> None:
    authority = PROVIDER_CONTRACTS["authority"]
    actual = {row["path"]: row["sha256"] for row in authority.values()}
    assert len(actual) == 6
    assert all(PINNED_BASELINE_HASHES[path] == digest for path, digest in actual.items())


@pytest.mark.parametrize("mode", EXPECTED_MODES)
def test_each_mode_is_unique_versioned_and_fail_closed(mode: str) -> None:
    rows = [row for row in PROVIDER_CONTRACTS["mode_contracts"] if row["mode"] == mode]
    assert len(rows) == 1
    row = rows[0]
    assert row["required_gate_ids"]
    assert len(row["required_gate_ids"]) == len(set(row["required_gate_ids"]))
    assert row["minimum_fields"]
    assert row["frequency_budget"]
    assert row["failure_action"]


@pytest.mark.parametrize("provider_id", EXPECTED_PROVIDERS)
def test_each_provider_contract_starts_with_zero_collection_budget(provider_id: str) -> None:
    rows = [row for row in PROVIDER_CONTRACTS["provider_contracts"] if row["provider_id"] == provider_id]
    assert len(rows) == 1
    row = rows[0]
    assert row["production_collection_enabled"] is False
    assert row["rate_budget"]["enabled_requests_per_period"] == 0
    assert "ORDER_SUBMISSION_CONFIRMATION_OR_RETRY" in row["prohibited_access_methods"]
    assert row["stop_conditions"]


def test_tab_contract_preserves_official_source_boundaries() -> None:
    tab = PROVIDER_CONTRACTS["provider_contracts"][0]
    assert tab["provider_id"] == "TAB"
    assert "SCREEN_SCRAPING" in tab["prohibited_access_methods"]
    assert "THIRD_PARTY_CREDENTIAL_ACCESS" in tab["prohibited_access_methods"]
    assert tab["realtime_truth"] == "NOT_FROM_EMAIL_OR_ACTIVITY_STATEMENT"
    assert "PF-TAB-004" in tab["source_fact_ids"]
    assert "PF-TAB-005" in tab["source_fact_ids"]


def test_sportsbet_contract_does_not_infer_automation_permission() -> None:
    sportsbet = PROVIDER_CONTRACTS["provider_contracts"][1]
    assert sportsbet["provider_id"] == "SPORTSBET"
    assert "UNPROVEN_SCRAPING_AUTOMATION_OR_API" in sportsbet["prohibited_access_methods"]
    assert sportsbet["allowed_access_methods"] == ["OWNER_VISIBLE_MANUAL_OBSERVATION_AFTER_IDENTITY_MATCH"]
    assert "PF-SPORTSBET-003" in sportsbet["source_fact_ids"]


def test_unbound_provider_has_no_implicitly_allowed_method() -> None:
    other = PROVIDER_CONTRACTS["provider_contracts"][2]
    assert other["provider_id"] == "OTHER_OBSERVABLE_PROVIDER"
    assert other["allowed_access_methods"] == []
    assert other["official_source_ids"] == []
    assert other["applicable_licensed_entity"] == "UNBOUND_UNKNOWN"


def test_gmail_cloudflare_and_ovh_are_not_market_source_enablement() -> None:
    assert [row["system_id"] for row in PROVIDER_CONTRACTS["adjacent_systems_out_of_scope"]] == ["GMAIL", "CLOUDFLARE", "OVH"]


def test_capability_matrix_is_exact_cartesian_product() -> None:
    rows = SOURCE_CAPABILITIES["capabilities"]
    pairs = [(row["provider_id"], row["mode"]) for row in rows]
    assert len(rows) == 15
    assert len(set(pairs)) == 15
    assert set(pairs) == {(provider, mode) for provider in EXPECTED_PROVIDERS for mode in EXPECTED_MODES}


@pytest.mark.parametrize("capability", SOURCE_CAPABILITIES["capabilities"], ids=lambda row: row["capability_id"])
def test_every_real_capability_is_disabled_and_unverified(capability: dict) -> None:
    assert capability["production_collection_enabled"] is False
    assert capability["runtime_verified"] is False
    assert capability["max_requests_per_period"] == 0
    assert capability["passed_gate_ids"] == []
    assert capability["reason_codes"]
    assert capability["failure_action"]


@pytest.mark.parametrize("capability", SOURCE_CAPABILITIES["capabilities"], ids=lambda row: row["capability_id"])
def test_every_real_capability_request_denies_collection(capability: dict) -> None:
    request = {
        "provider_id": capability["provider_id"],
        "mode": capability["mode"],
        "provider_contract_version": capability["provider_contract_version"],
        "source_version_sha256": "c" * 64,
        "evaluation_date": "2026-07-23",
        "incremental_cash_aud": "0.00",
        "passed_gate_ids": capability["required_gate_ids"],
        "requested_action": "COLLECT_READ_ONLY",
        "execution_environment": "PRODUCTION",
    }
    result = resolve_capability_request(capability, request)
    assert result["decision"] == "DENY_COLLECTION"
    assert result["reason_code"] == "CAPABILITY_DISABLED"
    assert result["external_action_performed"] is False
    assert result["advice_enabled"] is False
    assert result["order_enabled"] is False


def test_frozen_synthetic_contract_is_only_positive_path() -> None:
    result = resolve_capability_request(
        FIXTURE["frozen_test_only_positive_contract"],
        FIXTURE["frozen_test_only_positive_request"],
    )
    assert result == {
        "decision": "ALLOW_FROZEN_TEST_READ_ONLY",
        "reason_code": "SOURCE_CONTRACT_PASS_TEST_ONLY",
        "detail": {"provider_id": "FROZEN_SYNTHETIC_PROVIDER", "mode": "FILE_OR_STATIC_DATA"},
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


@pytest.mark.parametrize("mutation", FIXTURE["negative_mutations"], ids=lambda row: row["id"])
def test_every_declared_contract_fault_fails_closed(mutation: dict) -> None:
    request = _mutate(FIXTURE["frozen_test_only_positive_request"], mutation)
    result = resolve_capability_request(FIXTURE["frozen_test_only_positive_contract"], request)
    assert result["decision"] == "DENY_COLLECTION"
    assert result["reason_code"] == mutation["expected_reason"]
    assert result["external_action_performed"] is False


@pytest.mark.parametrize("delta", EXPECTED_NUMERIC_DELTAS)
def test_ten_thousandth_and_adverse_tick_do_not_relax_source_contract(delta: str) -> None:
    request = copy.deepcopy(FIXTURE["frozen_test_only_positive_request"])
    baseline = resolve_capability_request(FIXTURE["frozen_test_only_positive_contract"], request)
    request["numeric_probe"] = delta
    request["adverse_odds_tick"] = True
    perturbed = resolve_capability_request(FIXTURE["frozen_test_only_positive_contract"], request)
    assert perturbed == baseline
    assert request["adverse_odds_tick"] is True


def test_replay_is_byte_deterministic() -> None:
    first = resolve_capability_request(copy.deepcopy(FIXTURE["frozen_test_only_positive_contract"]), copy.deepcopy(FIXTURE["frozen_test_only_positive_request"]))
    second = resolve_capability_request(copy.deepcopy(FIXTURE["frozen_test_only_positive_contract"]), copy.deepcopy(FIXTURE["frozen_test_only_positive_request"]))
    assert first == second
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_duplicate_capability_record_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / SOURCE_CAPABILITIES_PATH)
    artifact["capabilities"].append(copy.deepcopy(artifact["capabilities"][0]))
    _write_json(root / SOURCE_CAPABILITIES_PATH, artifact)
    _failed(evaluate_contract(root), "S05P02-CAPABILITY-MATRIX-COMPLETE")


def test_missing_capability_record_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / SOURCE_CAPABILITIES_PATH)
    artifact["capabilities"].pop()
    _write_json(root / SOURCE_CAPABILITIES_PATH, artifact)
    _failed(evaluate_contract(root), "S05P02-CAPABILITY-MATRIX-COMPLETE")


def test_enabling_one_real_capability_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / SOURCE_CAPABILITIES_PATH)
    artifact["capabilities"][0]["production_collection_enabled"] = True
    _write_json(root / SOURCE_CAPABILITIES_PATH, artifact)
    _failed(evaluate_contract(root), "S05P02-CAPABILITY-DISABLED-TAB")


def test_provider_rate_budget_above_zero_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / PROVIDER_CONTRACTS_PATH)
    artifact["provider_contracts"][0]["rate_budget"]["enabled_requests_per_period"] = 1
    _write_json(root / PROVIDER_CONTRACTS_PATH, artifact)
    _failed(evaluate_contract(root), "S05P02-PROVIDER-CONTRACT-TAB")


def test_order_boundary_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / PROVIDER_CONTRACTS_PATH)
    artifact["hard_boundaries"]["real_order_submission_confirmation_or_retry_present"] = True
    _write_json(root / PROVIDER_CONTRACTS_PATH, artifact)
    _failed(evaluate_contract(root), "S05P02-A300-A0-NO-ORDER-NO-GUARANTEE")


def test_claim_boundary_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / SOURCE_CAPABILITIES_PATH)
    artifact["claim_boundary"]["any_real_market_observed"] = True
    _write_json(root / SOURCE_CAPABILITIES_PATH, artifact)
    _failed(evaluate_contract(root), "S05P02-CAPABILITY-CLAIM-BOUNDARY")


def test_p03_remains_planned_and_unstarted() -> None:
    result = evaluate_contract(ROOT)
    check = next(row for row in result["checks"] if row["id"] == "S05P02-P03-NOT-STARTED")
    assert check["passed"] is True, check
    assert check["detail"]["present"] == []
    assert check["detail"]["index"][0]["status"] == "PLANNED"


def test_partial_p03_candidate_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / "scheduler.py").write_text("# partial and invalid\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S05P02-P03-NOT-STARTED")


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["contract_matrix_proof"]["capability_record_count"] == 15
    assert first["contract_matrix_proof"]["production_collection_enabled_count"] == 0
    assert all(row["matched"] is True for row in first["structured_failure_log"])
    assert first["next"] == "S05/P03_READY_NOT_STARTED"


def test_rollback_drill_restores_every_phase_artifact() -> None:
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
    _failed(result, "S05P02-TARGETED-PYTEST")
    assert "S05P02-AFFECTED-REGRESSION" in result["summary"]["failed_check_ids"]
    assert "S05P02-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(SourceCapabilityContractError, match="inside the ABD project root"):
        write_phase_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "abd_acceptance", "--contract", CONTRACT_ID, "--evidence", "machine/evidence"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert "contract is not implemented" not in result.stderr


def test_readme_and_cli_wiring_reference_p02_contract() -> None:
    main = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    init = (ROOT / "abd_acceptance/__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '"AC-S05-P02": write_source_capability_phase_evidence' in main
    assert "validate_source_capability_candidate" in init
    assert "verify_source_capability_evidence" in init
    assert "当前 `S05/P02`" in readme


def test_signed_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = validate_signed_receipt_preflight(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        verified = verify_existing_phase_evidence(ROOT)
        assert verified["status"] == "PASS", verified
        assert verified["decision"] == "S05_P02_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S05_P02_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED"


def test_candidate_preflight_does_not_recursively_verify_p01() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert not any(row["id"] == "S05P02-P01-SIGNED-PREREQUISITE" for row in result["checks"])


def test_artifacts_contain_no_secret_or_machine_specific_path() -> None:
    paths = [PROVIDER_CONTRACTS_PATH, SOURCE_CAPABILITIES_PATH, FIXTURE_PATH, Path("abd_acceptance/source_capabilities.py"), Path("tests/S05/P02_test.py")]
    rendered = "\n".join((ROOT / path).read_text(encoding="utf-8", errors="replace") for path in paths)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert ("-----BEGIN " + "PRIVATE KEY-----") not in rendered
    assert ("ghp" + "_") not in rendered


def test_external_effect_boundary_matches_fixture_and_has_no_runtime_claim() -> None:
    assert EXTERNAL_EFFECT_BOUNDARY == FIXTURE["expected_external_effect_boundary"]
    assert set(value for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud") == {False}
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
    assert set(PROVIDER_CONTRACTS["claim_boundary"].values()) == {False}
    assert set(SOURCE_CAPABILITIES["claim_boundary"].values()) == {False}


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

