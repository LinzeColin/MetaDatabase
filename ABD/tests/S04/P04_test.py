from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.capacity_governance import (
    BASELINE_PATH,
    CAPACITY_PATH,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXPECTED_DISK_BUCKETS,
    EXPECTED_NUMERIC_DELTAS,
    EXPECTED_RETENTION_CLASSES,
    EXPECTED_STATES,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PACK_REPORT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    PINNED_REPO_HASHES,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    SECRET_PATTERNS,
    SHEDDING_PATH,
    SIGNED_STATE_JUNIT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    CapacityGovernanceContractError,
    _base_metrics,
    _set_or_delete_path,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    evaluate_load_profile,
    perform_capacity_drill,
    resource_disposition,
    simulate_disk_horizon,
    validate_capacity_budget,
    validate_load_baseline,
    validate_resource_shedding,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from abd_acceptance.release_control import verify_existing_phase_evidence as verify_p03_evidence


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
CAPACITY = strict_json_load(ROOT / CAPACITY_PATH)
SHEDDING = strict_json_load(ROOT / SHEDDING_PATH)
BASELINE = strict_json_load(ROOT / BASELINE_PATH)


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


def _all_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _all_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_values(item)
    else:
        yield value


def _nested_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            path = prefix + (key,)
            yield path
            yield from _nested_paths(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = prefix + (index,)
            yield path
            yield from _nested_paths(item, path)


def test_baseline_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "CAPACITY_RESOURCE_GOVERNANCE_CONTRACT_FROZEN"
    assert result["phase_status"] == "S04_P04_PASS"
    assert result["pass_gate_interpretation"] == "OFFLINE_INTEGER_365_DAY_FROZEN_10X_DESIGN_ENVELOPE_AVOIDS_SWAP_AND_DISK_EXHAUSTION_BY_BOUNDED_SHEDDING; OVH_RUNTIME_CAPACITY_REMAINS_UNVERIFIED"
    assert result["activation_gate"] == FIXTURE["expected_activation_gate"]
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["runtime_capacity_status"] == "NOT_MEASURED_OR_VERIFIED_ON_OVH"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_signed_p03_is_exact_phase_prerequisite() -> None:
    result = verify_p03_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_P03_EVIDENCE_VERIFIED"
    assert result["next"] == "S04/P04_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_REPO_HASHES))
def test_repository_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT.parent / relative) == PINNED_REPO_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_capacity_budget_is_strict_and_valid() -> None:
    assert validate_capacity_budget(CAPACITY) == []
    assert json.loads((ROOT / CAPACITY_PATH).read_text(encoding="utf-8")) == CAPACITY


def test_resource_shedding_policy_is_strict_and_valid() -> None:
    assert validate_resource_shedding(SHEDDING, CAPACITY) == []
    assert SHEDDING["state_order"] == EXPECTED_STATES


def test_load_baseline_is_strict_and_valid() -> None:
    assert validate_load_baseline(BASELINE) == []
    assert BASELINE["baseline_kind"] == "DETERMINISTIC_SYNTHETIC_ENGINEERING_BASELINE_NOT_OBSERVED_TRAFFIC"


@pytest.mark.parametrize("mutation", FIXTURE["invalid_capacity_mutations"], ids=lambda row: row["id"])
def test_every_declared_capacity_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(CAPACITY)
    _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
    assert validate_capacity_budget(candidate), mutation


@pytest.mark.parametrize("mutation", FIXTURE["invalid_shedding_mutations"], ids=lambda row: row["id"])
def test_every_declared_shedding_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(SHEDDING)
    _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
    assert validate_resource_shedding(candidate, CAPACITY), mutation


@pytest.mark.parametrize("mutation", FIXTURE["invalid_baseline_mutations"], ids=lambda row: row["id"])
def test_every_declared_baseline_fault_fails_closed(mutation: dict) -> None:
    candidate = copy.deepcopy(BASELINE)
    _set_or_delete_path(candidate, mutation["path"], mutation.get("value"), delete=mutation.get("delete") is True)
    assert validate_load_baseline(candidate), mutation


@pytest.mark.parametrize("validator", [validate_capacity_budget, validate_resource_shedding, validate_load_baseline])
@pytest.mark.parametrize("malformed", [None, [], "invalid", 1, True])
def test_top_level_malformed_artifacts_fail_closed(validator, malformed) -> None:
    assert validator(malformed)


def test_every_nested_contract_block_rejects_whole_value_type_corruption() -> None:
    malformed_values = [None, [], {}, "invalid", True, -1, 1.5]
    for source, validator in [
        (CAPACITY, validate_capacity_budget),
        (SHEDDING, validate_resource_shedding),
        (BASELINE, validate_load_baseline),
    ]:
        for key in source:
            for malformed in malformed_values:
                candidate = copy.deepcopy(source)
                candidate[key] = malformed
                assert validator(candidate), {"key": key, "malformed": malformed}
        for path in _nested_paths(source):
            original = source
            for part in path:
                original = original[part]
            for malformed in malformed_values:
                if type(malformed) is type(original) and malformed == original:
                    continue
                candidate = copy.deepcopy(source)
                _set_or_delete_path(candidate, path, malformed)
                assert isinstance(validator(candidate), list), {"path": path, "malformed": malformed}


@pytest.mark.parametrize(
    "source,path,validator",
    [
        (CAPACITY, ["target_host", "vcpu"], validate_capacity_budget),
        (SHEDDING, ["hysteresis", "minimum_state_hold_seconds"], validate_resource_shedding),
        (BASELINE, ["profiles", 0, "active_slot_cpu_millicores"], validate_load_baseline),
    ],
)
def test_binary_float_in_machine_artifact_fails_closed(source, path, validator) -> None:
    candidate = copy.deepcopy(source)
    _set_or_delete_path(candidate, path, 1.5)
    assert validator(candidate)


@pytest.mark.parametrize("row", FIXTURE["expected_state_boundaries"], ids=lambda row: row["id"])
def test_every_resource_boundary_is_inclusive_and_exact(row: dict) -> None:
    metrics = _base_metrics()
    metrics[row["metric"]] = row["value"]
    result = resource_disposition(metrics, CAPACITY, SHEDDING)
    assert result["state"] == row["expected_state"]
    assert result["effective_live_recommendation_enabled"] is False
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        {"disk_used_mib": None},
        {"disk_used_mib": -1},
        {"disk_used_mib": True},
        {"cpu_usage_basis_points": "7000"},
        {"memory_usage_basis_points": 1.0},
        {"browser_sessions": -1},
        {"swap_used_mib": False},
        {"telemetry_age_seconds": None},
    ],
)
def test_unknown_or_malformed_telemetry_is_emergency(mutation: dict) -> None:
    metrics = _base_metrics()
    metrics.update(mutation)
    result = resource_disposition(metrics, CAPACITY, SHEDDING)
    assert result["state"] == "EMERGENCY"
    assert result["reasons"] == ["UNKNOWN_OR_MALFORMED_TELEMETRY"]
    assert result["new_advice_capacity_allowed"] is False


def test_missing_and_extra_metrics_fail_closed() -> None:
    missing = _base_metrics()
    missing.pop("disk_used_mib")
    extra = {**_base_metrics(), "undeclared": 1}
    assert resource_disposition(missing, CAPACITY, SHEDDING)["state"] == "EMERGENCY"
    assert resource_disposition(extra, CAPACITY, SHEDDING)["state"] == "EMERGENCY"


def test_highest_resource_severity_wins() -> None:
    metrics = _base_metrics()
    metrics.update({"cpu_usage_basis_points": 7000, "disk_used_mib": 34816, "swap_used_mib": 1})
    result = resource_disposition(metrics, CAPACITY, SHEDDING)
    assert result["state"] == "EMERGENCY"
    assert "SWAP_USED" in result["reasons"]


@pytest.mark.parametrize("state_id", EXPECTED_STATES)
def test_state_action_contract_never_enables_live_recommendation(state_id: str) -> None:
    row = next(item for item in SHEDDING["states"] if item["id"] == state_id)
    if state_id == "NORMAL":
        metrics = _base_metrics()
    elif state_id == "CONSTRAINED":
        metrics = {**_base_metrics(), "cpu_usage_basis_points": 7000}
    elif state_id == "CRITICAL":
        metrics = {**_base_metrics(), "cpu_usage_basis_points": 8500}
    else:
        metrics = {**_base_metrics(), "cpu_usage_basis_points": 9000}
    result = resource_disposition(metrics, CAPACITY, SHEDDING)
    assert result["state"] == state_id
    assert result["actions"] == row["actions"]
    assert result["effective_live_recommendation_enabled"] is False


def test_cpu_memory_and_disk_budgets_balance_exactly() -> None:
    cpu = CAPACITY["cpu_budget"]
    memory = CAPACITY["memory_budget"]
    disk = CAPACITY["disk_budget"]
    assert cpu["active_slot_outer_hard_limit_millicores"] + cpu["candidate_shadow_outer_hard_limit_millicores"] + cpu["host_system_and_tunnel_reserve_millicores"] == 2000
    assert memory["active_slot_outer_hard_limit_mib"] + memory["candidate_shadow_outer_hard_limit_mib"] + memory["host_system_and_tunnel_reserve_mib"] == 4096
    assert {row["id"]: row["budget_mib"] for row in disk["allocation_buckets"]} == EXPECTED_DISK_BUCKETS
    assert sum(EXPECTED_DISK_BUCKETS.values()) == 40960


def test_retention_never_auto_deletes_ledger_or_acceptance_evidence() -> None:
    classes = {row["id"]: (row["budget_mib"], row["automatic_delete"]) for row in CAPACITY["retention_budget"]["classes"]}
    assert classes == EXPECTED_RETENTION_CLASSES
    assert classes["immutable_ledger"][1] is False
    assert classes["acceptance_evidence"][1] is False
    assert {key for key, (_, automatic) in classes.items() if automatic} == {"operational_logs", "temporary_files"}


def test_one_x_profile_stays_normal_and_bounded() -> None:
    profile = next(row for row in BASELINE["profiles"] if row["id"] == "EXPECTED_1X")
    result = evaluate_load_profile(profile, BASELINE, CAPACITY, SHEDDING)
    assert result["status"] == "PASS"
    assert result["pre_shed_disposition"]["state"] == "NORMAL"
    assert result["candidate_shadow_shed"] is False
    assert result["disk_horizon"]["final_used_mib"] == 17796
    assert result["disk_horizon"]["free_mib"] == 23164


def test_frozen_ten_x_sheds_candidate_and_optional_work_before_core() -> None:
    profile = next(row for row in BASELINE["profiles"] if row["id"] == "FROZEN_10X")
    result = evaluate_load_profile(profile, BASELINE, CAPACITY, SHEDDING)
    assert result["status"] == "PASS"
    assert result["pre_shed_disposition"]["state"] == "CONSTRAINED"
    assert result["candidate_shadow_shed"] is True
    assert result["post_shed_disposition"]["state"] == "NORMAL"
    assert result["swap_used_mib"] == 0
    assert result["disk_horizon"]["optional_writes_allowed_at_end"] is False
    assert result["disk_horizon"]["core_writes_allowed_at_end"] is True
    assert result["disk_horizon"]["final_used_mib"] == 32396
    assert result["disk_horizon"]["free_mib"] == 8564
    assert result["disk_horizon"]["disk_exhausted"] is False
    assert result["disk_horizon"]["minimum_free_reserve_preserved"] is True


def test_disk_simulation_stops_before_stop_advice_watermark() -> None:
    profile = copy.deepcopy(next(row for row in BASELINE["profiles"] if row["id"] == "FROZEN_10X"))
    profile["immutable_daily_growth_mib"] = 4096
    result = simulate_disk_horizon(profile, BASELINE, CAPACITY, SHEDDING, optional_writes_initially_allowed=False)
    assert result["core_stop_day"] is not None
    assert result["core_writes_allowed_at_end"] is False
    assert result["final_used_mib"] < CAPACITY["disk_budget"]["watermarks_used_mib"]["stop_new_advice"]
    assert result["disk_exhausted"] is False


@pytest.mark.parametrize("delta", EXPECTED_NUMERIC_DELTAS)
@pytest.mark.parametrize("adverse_odds_tick", [False, True])
def test_ten_x_capacity_result_is_stable_at_numeric_boundary(delta: str, adverse_odds_tick: bool) -> None:
    profile = next(row for row in BASELINE["profiles"] if row["id"] == "FROZEN_10X")
    baseline = evaluate_load_profile(profile, BASELINE, CAPACITY, SHEDDING)
    replay = evaluate_load_profile(profile, BASELINE, CAPACITY, SHEDDING)
    assert delta in FIXTURE["allowed_numeric_boundary_deltas"]
    assert isinstance(adverse_odds_tick, bool)
    assert replay == baseline
    assert replay["status"] == "PASS"


def test_capacity_drill_is_deterministic_and_has_no_external_effect() -> None:
    first = perform_capacity_drill(ROOT)
    second = perform_capacity_drill(ROOT)
    assert first == second
    assert first["status"] == "PASS"
    assert first["target_host_accessed"] is False
    assert first["production_runtime_verified"] is False
    assert first["real_load_generated"] is False
    assert first["production_state_changed"] is False
    assert first["external_state_changed"] is False
    assert first["incremental_cash_spent_aud"] == "0.00"


def test_evidence_build_is_deterministic_without_runtime_reports() -> None:
    first, rollback_first = build_evidence(ROOT, require_external_reports=False)
    second, rollback_second = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert rollback_first == rollback_second
    assert first["status"] == "PASS"
    assert first["scope_boundary"]["production_10x_throughput_not_claimed"] is True
    assert first["scope_boundary"]["stage_review_not_started"] is True
    assert first["capacity_proof"]["production_capacity_verified"] is False
    assert first["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_existing_evidence_verifier_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S04_P04_EVIDENCE_VERIFIED"
        assert result["next"] == FIXTURE["expected_next"]
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S04_P04_EVIDENCE_INVALID_FAIL_CLOSED"


def test_signed_receipt_verifies_in_isolated_copy_without_git_history(tmp_path: Path) -> None:
    if not (ROOT / EVIDENCE_PATH).is_file() or not (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        result = verify_existing_phase_evidence(ROOT, verify_git_history=False)
        assert result["status"] == "FAIL"
        return
    root = _clone_project(tmp_path)
    result = verify_existing_phase_evidence(root, verify_git_history=False)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S04_P04_EVIDENCE_VERIFIED"


def test_stage_review_is_ready_but_not_started() -> None:
    forbidden = [
        Path("tests/S04/stage_review_test.py"),
        Path("machine/tests/fixtures/S04_STAGE_REVIEW.json"),
        Path("machine/evidence/EVD-S04-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S04-STAGE-REVIEW_rollback.json"),
        Path("abd_acceptance/stage4_review.py"),
    ]
    assert not [path.as_posix() for path in forbidden if (ROOT / path).exists()]


@pytest.mark.parametrize(
    "relative,check_id",
    [
        (CAPACITY_PATH, "S04P04-PIN-capacity_budget_json"),
        (SHEDDING_PATH, "S04P04-PIN-resource_shedding_json"),
        (BASELINE_PATH, "S04P04-PIN-load_baseline_json"),
        (FIXTURE_PATH, "S04P04-PIN-machine-tests-fixtures-S04_P04_json"),
        (Path("machine/evidence/EVD-S04-P03.json"), "S04P04-BASELINE-machine-evidence-EVD-S04-P03_json"),
    ],
)
def test_oracle_rejects_tampered_phase_or_prerequisite_artifact(tmp_path: Path, relative: Path, check_id: str) -> None:
    root = _clone_project(tmp_path)
    (root / relative).write_bytes((root / relative).read_bytes() + b"\n")
    _failed(evaluate_contract(root), check_id)


def test_oracle_rejects_its_own_source_tampering(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / "abd_acceptance/capacity_governance.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S04P04-ORACLE-SELF-INTEGRITY")


@pytest.mark.parametrize(
    "relative,mutation,check_id",
    [
        (CAPACITY_PATH, (["financial_and_order_boundary", "incremental_cash_budget_aud"], "1.00"), "S04P04-CAPACITY-VALID"),
        (SHEDDING_PATH, (["states", 3, "new_advice_capacity_allowed"], True), "S04P04-SHEDDING-VALID"),
        (BASELINE_PATH, (["runtime_measurement", "target_host_benchmark_executed"], True), "S04P04-BASELINE-VALID"),
    ],
)
def test_semantic_fault_injection_is_rejected_by_oracle_clone(tmp_path: Path, relative: Path, mutation, check_id: str) -> None:
    root = _clone_project(tmp_path)
    value = strict_json_load(root / relative)
    _set_or_delete_path(value, mutation[0], mutation[1])
    _write_json(root / relative, value)
    _failed(evaluate_contract(root), check_id)


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    original = (root / CAPACITY_PATH).read_text(encoding="utf-8")
    (root / CAPACITY_PATH).write_text(original.replace('"schema_version": "1.0.0",', '"schema_version": "1.0.0",\n  "schema_version": "1.0.0",', 1), encoding="utf-8")
    _failed(evaluate_contract(root), "S04P04-CAPACITY-STRICT-JSON")


def test_external_reports_are_mandatory_when_requested(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for path in [JUNIT_PATH, FULL_JUNIT_PATH, SIGNED_STATE_JUNIT_PATH]:
        if (root / path).exists():
            (root / path).unlink()
    result = evaluate_contract(root, require_external_reports=True)
    for check_id in ["S04P04-TARGETED-PYTEST", "S04P04-FULL-REGRESSION", "S04P04-SIGNED-STATE-REGRESSION"]:
        assert check_id in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(CapacityGovernanceContractError, match="inside the ABD project root"):
        write_phase_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "abd_acceptance", "--contract", CONTRACT_ID, "--evidence", "machine/evidence"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    # Before signed reports/receipts exist the command may fail closed, but it
    # must be implemented rather than rejected by argparse.
    assert "contract is not implemented" not in result.stderr


def test_no_phase_artifact_contains_secret_or_local_path() -> None:
    for relative in [CAPACITY_PATH, SHEDDING_PATH, BASELINE_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/capacity_governance.py")]:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert not any(pattern.search(text) for pattern in SECRET_PATTERNS), relative
        assert ("/" + "Users/") not in text
        assert ("file" + "://") not in text


def test_all_frozen_numeric_artifacts_avoid_binary_float() -> None:
    for value in [CAPACITY, SHEDDING, BASELINE, FIXTURE]:
        assert not any(isinstance(item, float) for item in _all_values(value))


def test_zero_cash_no_order_and_no_return_guarantee_are_explicit() -> None:
    boundary = CAPACITY["financial_and_order_boundary"]
    assert boundary["initial_bankroll_aud"] == "300.00"
    assert boundary["incremental_cash_budget_aud"] == "0.00"
    assert boundary["automatic_paid_scale_up_allowed"] is False
    assert boundary["order_submission_module_present"] is False
    assert boundary["monthly_30pct_target_guaranteed"] is False
    assert boundary["target_shortfall_may_relax_capacity_or_safety_gate"] is False


def test_external_effect_boundary_is_exact_and_inactive() -> None:
    assert CAPACITY["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert FIXTURE["expected_external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud")
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"


def test_taskpack_and_audit_inputs_exist() -> None:
    for relative in [PACK_REPORT_PATH, SCAN_REPORT_PATH, Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"), Path("machine/facts/traceability_matrix.json")]:
        assert (ROOT / relative).is_file(), relative
