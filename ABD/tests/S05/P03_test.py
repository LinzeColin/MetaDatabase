from __future__ import annotations

import copy
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.source_capabilities import verify_existing_phase_evidence as verify_p02_evidence
from abd_acceptance.source_scheduler import (
    AFFECTED_JUNIT_PATH,
    CADENCE_TESTS_PATH,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXPECTED_ARTIFACTS,
    EXPECTED_NUMERIC_DELTAS,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    RATE_BUDGET_PATH,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SCHEDULER_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    SourceSchedulerContractError,
    SchedulerContractError,
    ADVICE_USABLE_SECONDS,
    CADENCE_ORDER,
    DISTANCE_RECALCULATION_SECONDS,
    MAX_DISPATCH_DEVIATION_MICROSECONDS,
    QUOTE_USABLE_SECONDS,
    REFRESH_SECONDS,
    _structural_self_hash,
    build_evidence,
    calculate_backoff_seconds,
    classify_cadence,
    dispatch_timing,
    evaluate_contract as _evaluate_contract,
    evaluate_freshness,
    next_due_at,
    parse_timestamp,
    plan_refresh,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_signed_receipt_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
CADENCE = strict_json_load(ROOT / CADENCE_TESTS_PATH)
RATE_BUDGET = strict_json_load(ROOT / RATE_BUDGET_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
SOURCE_CAPABILITIES = strict_json_load(ROOT / "source_capabilities.json")


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(root, require_external_reports, _verify_git_history=Path(root).resolve() == ROOT.resolve())


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"))
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


def _iso_minus(seconds: int, microseconds: int = 0) -> str:
    now = datetime.fromisoformat(FIXTURE["fixed_clock"])
    return (now - timedelta(seconds=seconds, microseconds=microseconds)).isoformat()


def test_baseline_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["minimum_oracle_checks"]
    assert result["decision"] == "ADAPTIVE_REFRESH_SCHEDULE_FROZEN_FAIL_CLOSED"
    assert result["phase_status"] == "S05_P03_PASS"
    assert result["production_collection_status"] == "ALL_15_REAL_PROVIDER_MODE_BUDGETS_REMAIN_ZERO_AND_DISABLED"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S05/P04_READY_NOT_STARTED"
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_signed_p02_is_exact_phase_prerequisite() -> None:
    result = verify_p02_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S05_P02_EVIDENCE_VERIFIED"
    assert result["next"] == "S05/P03_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    actual = sha256_file(ROOT / relative)
    assert actual == PINNED_PHASE_HASHES[relative] or actual == SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_artifact_identity_and_taskpack_binding_are_exact() -> None:
    assert CADENCE["artifact_id"] == "ART-S05-P03-02"
    assert RATE_BUDGET["artifact_id"] == "ART-S05-P03-03"
    assert CADENCE["acceptance_contract_id"] == RATE_BUDGET["acceptance_contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_artifacts"] == EXPECTED_ARTIFACTS
    assert sha256_file(ROOT / SCHEDULER_PATH) == CADENCE["authority"]["scheduler"]["sha256"]


def test_scheduler_artifact_is_offline_stdlib_only() -> None:
    text = (ROOT / SCHEDULER_PATH).read_text(encoding="utf-8")
    for token in ["import requests", "import httpx", "import urllib", "import socket", "import subprocess", "from selenium", "from playwright"]:
        assert token not in text
    assert "never performs network I/O" in text
    assert "order" in text


def test_parse_timestamp_requires_an_explicit_offset() -> None:
    assert parse_timestamp(FIXTURE["fixed_clock"]).utcoffset() is not None
    with pytest.raises(SchedulerContractError):
        parse_timestamp("2026-07-23T18:00:00")
    with pytest.raises(SchedulerContractError):
        parse_timestamp(True)


@pytest.mark.parametrize("row", CADENCE["cadence_bands"], ids=lambda row: row["band"])
def test_each_cadence_band_matches_machine_parameters(row: dict) -> None:
    band = row["band"]
    assert row["refresh_seconds"] == REFRESH_SECONDS[band]
    assert row["quote_usable_seconds"] == QUOTE_USABLE_SECONDS[band]
    assert row["advice_usable_seconds"] == ADVICE_USABLE_SECONDS[band]
    assert row["advice_usable_seconds"] < row["quote_usable_seconds"]


def test_cadence_order_and_recalculation_clock_are_exact() -> None:
    assert [row["band"] for row in CADENCE["cadence_bands"]] == list(CADENCE_ORDER)
    assert DISTANCE_RECALCULATION_SECONDS == 60
    assert MAX_DISPATCH_DEVIATION_MICROSECONDS == 2_000_000


@pytest.mark.parametrize("vector", CADENCE["cadence_vectors"], ids=lambda row: row["id"])
def test_declared_cadence_vector(vector: dict) -> None:
    result = classify_cadence(vector["time_to_start_seconds"], status=vector["status"], source_live_supported=vector["source_live_supported"])
    if "expected_band" in vector:
        assert result["decision"] == "CADENCE_CLASSIFIED"
        assert result["band"] == vector["expected_band"]
        assert result["refresh_seconds"] == vector["expected_refresh_seconds"]
    else:
        assert result["decision"] == vector["expected_action"]
        assert result["reason_code"] == vector["expected_reason"]
    assert result["external_action_performed"] is False
    assert result["advice_enabled"] is False
    assert result["order_enabled"] is False


@pytest.mark.parametrize("vector", strict_json_load(ROOT / "machine/tests/fixtures/schedule_boundary_vectors.json")["vectors"])
def test_original_taskpack_schedule_boundary_vector(vector: dict) -> None:
    result = classify_cadence(vector.get("time_to_start_seconds", 0), status=vector.get("status", "PREMATCH"), source_live_supported=vector.get("source_supported", False))
    if "expected_refresh_seconds" in vector:
        assert result["refresh_seconds"] == vector["expected_refresh_seconds"]
    else:
        assert result["decision"] == "NO_DISPATCH_NO_ADVICE"
        assert result["reason_code"] == "LIVE_REFRESH_UNSUPPORTED"


@pytest.mark.parametrize("seconds,expected", [(86401, "more_than_24h"), (86400, "2h_to_24h"), (7201, "2h_to_24h"), (7200, "15m_to_2h"), (901, "15m_to_2h"), (900, "0_to_15m"), (1, "0_to_15m")])
def test_adverse_time_boundary_classification(seconds: int, expected: str) -> None:
    assert classify_cadence(seconds)["band"] == expected


@pytest.mark.parametrize("value", [0, -1, True, "900", None])
def test_invalid_or_started_prematch_time_fails_closed(value) -> None:
    result = classify_cadence(value)
    assert result["decision"] == "NO_DISPATCH_NO_ADVICE"
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("vector", CADENCE["dispatch_vectors"], ids=lambda row: row["id"])
def test_dispatch_deviation_gate(vector: dict) -> None:
    result = dispatch_timing(vector["scheduled_at"], vector["actual_dispatch_at"])
    assert (result["decision"] == "DISPATCH_TIMING_PASS") is vector["expected_pass"]
    assert result["deviation_microseconds"] == vector["expected_deviation_microseconds"]
    assert result["external_action_performed"] is False


@pytest.mark.parametrize("value", ["bad", "2026-07-23T18:00:00", None, True])
def test_invalid_dispatch_timestamp_fails_closed(value) -> None:
    result = dispatch_timing(FIXTURE["fixed_clock"], value)
    assert result["decision"] == "NO_DISPATCH_NO_ADVICE"
    assert result["reason_code"] == "INVALID_DISPATCH_TIMESTAMP"


@pytest.mark.parametrize("vector", CADENCE["freshness_vectors"], ids=lambda row: row["id"])
def test_declared_freshness_vector(vector: dict) -> None:
    inputs = {key: value for key, value in vector.items() if key in {"now", "band", "source_timestamp", "observed_timestamp", "content_sha256", "source_clock_trusted", "advice_created_at"}}
    result = evaluate_freshness(**inputs)
    assert result["quote_usable"] is vector["expected_quote_usable"]
    assert result["advice_input_eligible"] is vector["expected_advice_input_eligible"]
    assert result["recommendation_generated"] is False
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("band", CADENCE_ORDER)
def test_exact_advice_age_is_eligible_but_one_microsecond_older_is_blocked(band: str) -> None:
    limit = ADVICE_USABLE_SECONDS[band]
    common = {"now": FIXTURE["fixed_clock"], "band": band, "observed_timestamp": _iso_minus(1), "content_sha256": "a" * 64, "source_clock_trusted": True}
    exact = evaluate_freshness(source_timestamp=_iso_minus(limit), **common)
    stale = evaluate_freshness(source_timestamp=_iso_minus(limit, 1), **common)
    assert exact["advice_input_eligible"] is True
    assert stale["quote_usable"] is True
    assert stale["advice_input_eligible"] is False
    assert stale["decision"] == "NO_ADVICE"


@pytest.mark.parametrize("band", CADENCE_ORDER)
def test_exact_quote_age_is_usable_but_one_microsecond_older_is_blocked(band: str) -> None:
    limit = QUOTE_USABLE_SECONDS[band]
    common = {"now": FIXTURE["fixed_clock"], "band": band, "observed_timestamp": _iso_minus(1), "content_sha256": "b" * 64, "source_clock_trusted": True}
    exact = evaluate_freshness(source_timestamp=_iso_minus(limit), **common)
    stale = evaluate_freshness(source_timestamp=_iso_minus(limit, 1), **common)
    assert exact["quote_usable"] is True
    assert exact["advice_input_eligible"] is False
    assert stale["quote_usable"] is False
    assert stale["advice_input_eligible"] is False
    assert stale["reason_code"] == "STALE_QUOTE_BLOCKED"


def test_older_of_source_and_observation_timestamps_controls_freshness() -> None:
    result = evaluate_freshness(now=FIXTURE["fixed_clock"], band="0_to_15m", source_timestamp=_iso_minus(1), observed_timestamp=_iso_minus(16), content_sha256="c" * 64, source_clock_trusted=True)
    assert result["effective_quote_age_microseconds"] == 16_000_000
    assert result["quote_usable"] is True
    assert result["advice_input_eligible"] is False


@pytest.mark.parametrize("vector", FIXTURE["freshness_fault_vectors"], ids=lambda row: row["id"])
def test_freshness_fault_fails_closed(vector: dict) -> None:
    request = copy.deepcopy(FIXTURE["freshness_base"])
    request[vector["mutation"]] = vector["value"]
    result = evaluate_freshness(**request)
    assert result["decision"] in {"NO_ADVICE", "NO_DISPATCH_NO_ADVICE"}
    assert result["reason_code"] == vector["expected_reason"]
    assert result["advice_enabled"] is False
    assert result["order_enabled"] is False


def test_advice_age_itself_is_also_bounded() -> None:
    request = copy.deepcopy(FIXTURE["freshness_base"])
    request["advice_created_at"] = _iso_minus(46)
    result = evaluate_freshness(**request)
    assert result["quote_usable"] is True
    assert result["advice_input_eligible"] is False
    assert result["decision"] == "NO_ADVICE"


def test_real_budget_matrix_exactly_covers_signed_p02_capabilities() -> None:
    actual = RATE_BUDGET["capability_budgets"]
    expected = SOURCE_CAPABILITIES["capabilities"]
    assert len(actual) == len(expected) == 15
    assert {row["capability_id"] for row in actual} == {row["capability_id"] for row in expected}
    assert len({row["capability_id"] for row in actual}) == 15


@pytest.mark.parametrize("budget", RATE_BUDGET["capability_budgets"], ids=lambda row: row["capability_id"])
def test_every_real_capability_budget_remains_zero_and_disabled(budget: dict) -> None:
    assert budget["production_collection_enabled"] is False
    assert budget["max_dispatches_per_window"] == 0
    assert budget["window_seconds"] == 0
    assert budget["reason"] == "P02_CAPABILITY_DISABLED"


@pytest.mark.parametrize("budget", RATE_BUDGET["capability_budgets"], ids=lambda row: row["capability_id"])
def test_even_forged_allow_decision_cannot_plan_a_real_capability(budget: dict) -> None:
    request = copy.deepcopy(FIXTURE["frozen_test_only_positive_request"])
    request.update({"capability_id": budget["capability_id"], "capability_decision": "ALLOW_VERIFIED_READ_ONLY", "execution_environment": "PRODUCTION"})
    result = plan_refresh(request, RATE_BUDGET)
    assert result["decision"] == "NO_DISPATCH_NO_ADVICE"
    assert result["reason_code"] == "CAPABILITY_BUDGET_DISABLED"
    assert result["external_action_performed"] is False


def test_frozen_synthetic_budget_is_only_positive_planning_path() -> None:
    result = plan_refresh(FIXTURE["frozen_test_only_positive_request"], RATE_BUDGET)
    for key, value in FIXTURE["expected_positive_result"].items():
        assert result[key] == value
    assert result["collection_performed"] is False
    assert result["advice_enabled"] is False
    assert result["order_enabled"] is False
    assert result["external_action_performed"] is False


@pytest.mark.parametrize("mutation", FIXTURE["negative_schedule_mutations"], ids=lambda row: row["id"])
def test_declared_schedule_fault_fails_closed(mutation: dict) -> None:
    result = plan_refresh(_mutate(FIXTURE["frozen_test_only_positive_request"], mutation), RATE_BUDGET)
    assert result["decision"] == "NO_DISPATCH_NO_ADVICE"
    assert result["reason_code"] == mutation["expected_reason"]
    assert result["external_action_performed"] is False
    assert result["advice_enabled"] is False


@pytest.mark.parametrize("vector", FIXTURE["backoff_vectors"])
def test_backoff_vector_is_deterministic_and_capped(vector: dict) -> None:
    assert calculate_backoff_seconds(vector["failure_count"], RATE_BUDGET["backoff_policy"]) == vector["expected_seconds"]


@pytest.mark.parametrize("failure_count", [-1, True, "1", None])
def test_invalid_backoff_count_is_rejected(failure_count) -> None:
    with pytest.raises(SchedulerContractError):
        calculate_backoff_seconds(failure_count, RATE_BUDGET["backoff_policy"])


def test_failed_dispatch_uses_later_of_cadence_and_backoff() -> None:
    result = next_due_at(FIXTURE["fixed_clock"], 20, actual_dispatch_at="2026-07-23T18:00:02+10:00", failure_count=2, backoff_policy=RATE_BUDGET["backoff_policy"])
    assert result["decision"] == "NEXT_DUE_PLANNED"
    assert result["backoff_seconds"] == 60
    assert result["cadence_due_at"] == "2026-07-23T18:00:20+10:00"
    assert result["next_due_at"] == "2026-07-23T18:01:02+10:00"


@pytest.mark.parametrize("delta", EXPECTED_NUMERIC_DELTAS)
def test_ten_thousandth_and_adverse_odds_tick_do_not_relax_time_or_source_gates(delta: str) -> None:
    baseline = plan_refresh(copy.deepcopy(FIXTURE["frozen_test_only_positive_request"]), RATE_BUDGET)
    request = copy.deepcopy(FIXTURE["frozen_test_only_positive_request"])
    request["numeric_probe"] = delta
    request["adverse_odds_tick"] = True
    assert plan_refresh(request, RATE_BUDGET) == baseline


def test_schedule_replay_is_byte_deterministic() -> None:
    first = plan_refresh(copy.deepcopy(FIXTURE["frozen_test_only_positive_request"]), copy.deepcopy(RATE_BUDGET))
    second = plan_refresh(copy.deepcopy(FIXTURE["frozen_test_only_positive_request"]), copy.deepcopy(RATE_BUDGET))
    assert first == second
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_enabling_one_real_budget_fails_candidate(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / RATE_BUDGET_PATH)
    artifact["capability_budgets"][0].update({"production_collection_enabled": True, "max_dispatches_per_window": 1, "window_seconds": 60})
    _write_json(root / RATE_BUDGET_PATH, artifact)
    _failed(evaluate_contract(root), "S05P03-ALL-REAL-BUDGETS-ZERO")


def test_removing_one_real_budget_fails_candidate(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / RATE_BUDGET_PATH)
    artifact["capability_budgets"].pop()
    _write_json(root / RATE_BUDGET_PATH, artifact)
    _failed(evaluate_contract(root), "S05P03-REAL-BUDGET-MATRIX-COMPLETE")


def test_relaxing_advice_freshness_fails_candidate(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    artifact = strict_json_load(root / CADENCE_TESTS_PATH)
    artifact["cadence_bands"][2]["advice_usable_seconds"] = 90
    _write_json(root / CADENCE_TESTS_PATH, artifact)
    _failed(evaluate_contract(root), "S05P03-CADENCE-BAND-15M_TO_2H")


def test_scheduler_source_mutation_fails_hash_pin(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / SCHEDULER_PATH).write_text((root / SCHEDULER_PATH).read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S05P03-PHASE-PIN-scheduler_py")


def test_p04_progression_is_not_partial_or_unverified() -> None:
    result = evaluate_contract(ROOT)
    check = next(row for row in result["checks"] if row["id"] == "S05P03-P04-PROGRESSION")
    assert check["passed"] is True, check
    assert check["detail"]["mode"] in {"S05_P04_NOT_STARTED", "VERIFIED_S05_P04_CANDIDATE", "VERIFIED_S05_P04_SIGNED"}


def test_partial_p04_candidate_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    (root / "silent_gap_oracle.py").unlink()
    _failed(evaluate_contract(root), "S05P03-P04-PROGRESSION")


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["schedule_proof"]["real_capability_budget_count"] == 15
    assert first["schedule_proof"]["real_enabled_budget_count"] == 0
    assert all(row["matched"] is True for row in first["structured_failure_log"])
    assert first["next"] == "S05/P04_READY_NOT_STARTED"


def test_rollback_drill_restores_every_changed_artifact() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["artifacts"]) == len(ROLLBACK_ARTIFACTS)
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["external_state_changed"] is False
    assert result["real_provider_dispatch_performed"] is False


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, AFFECTED_JUNIT_PATH, FULL_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S05P03-TARGETED-PYTEST")
    assert "S05P03-AFFECTED-REGRESSION" in result["summary"]["failed_check_ids"]
    assert "S05P03-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(SourceSchedulerContractError, match="inside the ABD project root"):
        write_phase_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "abd_acceptance", "--contract", CONTRACT_ID, "--evidence", "machine/evidence"], cwd=root, check=False, capture_output=True, text=True)
    assert "contract is not implemented" not in result.stderr


def test_readme_init_and_cli_reference_p03_contract() -> None:
    main = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    init = (ROOT / "abd_acceptance/__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '"AC-S05-P03": write_source_scheduler_phase_evidence' in main
    assert "validate_source_scheduler_candidate" in init
    assert "verify_source_scheduler_evidence" in init
    assert "当前 `S05/P03`" in readme


def test_signed_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = validate_signed_receipt_preflight(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        verified = verify_existing_phase_evidence(ROOT)
        assert verified["status"] == "PASS", verified
        assert verified["decision"] == "S05_P03_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S05_P03_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED"


def test_candidate_preflight_does_not_recursively_verify_p02() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert not any(row["id"] == "S05P03-P02-SIGNED-PREREQUISITE" for row in result["checks"])


def test_artifacts_contain_no_secret_or_machine_specific_path() -> None:
    paths = [SCHEDULER_PATH, CADENCE_TESTS_PATH, RATE_BUDGET_PATH, FIXTURE_PATH, Path("abd_acceptance/source_scheduler.py"), Path("tests/S05/P03_test.py")]
    rendered = "\n".join((ROOT / path).read_text(encoding="utf-8", errors="replace") for path in paths)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert ("-----BEGIN " + "PRIVATE KEY-----") not in rendered
    assert ("ghp" + "_") not in rendered


def test_external_effect_boundary_matches_fixture_and_has_no_runtime_claim() -> None:
    assert EXTERNAL_EFFECT_BOUNDARY == FIXTURE["expected_external_effect_boundary"]
    assert set(value for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud") == {False}
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
    assert CADENCE["claim_boundary"]["fixed_clock_contract_implemented"] is True
    assert RATE_BUDGET["claim_boundary"]["real_provider_budget_enabled"] is False


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
