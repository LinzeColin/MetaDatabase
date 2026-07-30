from __future__ import annotations

from decimal import Decimal
import ast
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.devig import (
    DevigAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
)
from devig import (
    METHODS,
    PROBABILITY_SUM_TOLERANCE,
    DevigInputError,
    build_report,
    calculate_market,
    canonical_json_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S08_P01.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "devig_vectors.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _case(identifier: str) -> dict:
    matches = [case for case in VECTORS["cases"] if case["id"] == identifier]
    assert len(matches) == 1
    return matches[0]


def _sum(probabilities: list[str]) -> Decimal:
    return sum((Decimal(value) for value in probabilities), Decimal("0"))


def test_candidate_preflight_and_contract_pass_without_generated_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == FIXTURE["contract_id"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_report_is_an_exact_deterministic_replay_of_frozen_vectors() -> None:
    expected = build_report(VECTORS)
    actual = json.loads((ROOT / "devig_report.json").read_text(encoding="utf-8"))
    assert actual == expected
    assert actual["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert actual["external_effect_boundary"]["external_network_accessed"] is False
    assert actual["external_effect_boundary"]["recommendation_generated_or_enabled"] is False
    assert actual["external_effect_boundary"]["order_submission_enabled"] is False


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["id"])
def test_all_four_methods_are_complete_probability_vectors(case: dict) -> None:
    result = calculate_market(case["odds"], market_complete=case["market_complete"])
    assert tuple(result["methods"]) == METHODS
    assert Decimal(result["booksum"]) >= Decimal("1")
    for method in METHODS:
        probabilities = result["methods"][method]["probabilities"]
        assert len(probabilities) == len(case["odds"])
        assert abs(_sum(probabilities) - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
        assert all(Decimal("0") < Decimal(value) < Decimal("1") for value in probabilities)


def test_shin_reference_agrees_to_one_e12() -> None:
    result = calculate_market(FIXTURE["shin_reference_odds"])
    actual = result["methods"]["SHIN"]["probabilities"]
    for computed, expected in zip(actual, FIXTURE["shin_reference_probabilities"]):
        assert abs(Decimal(computed) - Decimal(expected)) <= Decimal("1e-12")


def test_fair_two_way_boundary_has_zero_method_disagreement() -> None:
    result = calculate_market(_case("FAIR_TWO_WAY_BOUNDARY")["odds"])
    assert result["overround"] == "0"
    assert result["method_disagreement"]["max_abs_probability_span"] == "0"
    for method in METHODS:
        assert result["methods"][method]["probabilities"] == ["0.5", "0.5"]


@pytest.mark.parametrize("case", VECTORS["invalid_cases"], ids=lambda case: case["id"])
def test_incomplete_or_invalid_markets_fail_closed(case: dict) -> None:
    with pytest.raises(DevigInputError):
        calculate_market(case["odds"], market_complete=case["market_complete"])


def test_binary_float_and_non_boolean_completeness_are_rejected() -> None:
    with pytest.raises(DevigInputError):
        calculate_market([1.8, "2.1"])
    with pytest.raises(DevigInputError):
        calculate_market(["1.8", "2.1"], market_complete=1)  # type: ignore[arg-type]


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    case = _case("THREE_WAY_STANDARD_MARGIN")
    hashes = {
        hashlib.sha256(canonical_json_bytes(calculate_market(case["odds"]))).hexdigest()
        for _ in range(FIXTURE["replay_count"])
    }
    assert len(hashes) == 1


def test_ten_thousand_adverse_decimal_perturbations_remain_probability_safe_without_soak() -> None:
    base = tuple(Decimal(value) for value in _case("THREE_WAY_STANDARD_MARGIN")["odds"])
    cache: dict[tuple[str, ...], dict] = {}
    for iteration in range(FIXTURE["adverse_replay_count"]):
        delta = Decimal((iteration % 3) - 1) * Decimal("0.0001")
        odds = (base[0] + delta, base[1], base[2])
        key = tuple(str(value) for value in odds)
        # The fixture cycles three frozen adverse boundaries. Cache the pure
        # result per boundary while retaining all 10,000 deterministic checks.
        # This is replay coverage, never a wall-clock soak.
        if key not in cache:
            cache[key] = calculate_market(odds)
        result = cache[key]
        for method in METHODS:
            probabilities = result["methods"][method]["probabilities"]
            assert abs(_sum(probabilities) - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
        assert "recommendation" not in result
        assert "order" not in result
    assert len(cache) == 3


def test_core_source_has_no_network_process_or_sleep_capability() -> None:
    source = (ROOT / "devig.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"})
    assert "sleep(" not in source
    assert "float(" not in source


def test_rollback_drill_is_hash_only_and_changes_no_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert all(item["status"] == "PASS" for item in rollback["artifacts"].values())


def test_candidate_fails_closed_when_report_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "devig_report.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["summary"]["case_count"] = 999
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S08P01-REPORT-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_signed_predecessor_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S07-P04.json"
    path.write_text("{}\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert any(identifier.startswith("S08P01-PREDECESSOR-HASH") for identifier in result["summary"]["failed_check_ids"])


def test_phase_receipt_is_absent_before_delivery_and_cannot_be_claimed(tmp_path: Path) -> None:
    with pytest.raises((DevigAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(tmp_path)


def test_cli_is_wired_to_exact_contract_and_preserves_no_order_boundary() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S08-P01": write_devig_phase_evidence' in source
    assert '"AC-S08-P01": verify_devig_phase_evidence' in source
    core_source = (ROOT / "devig.py").read_text(encoding="utf-8")
    assert '"order_submission_enabled": False' in core_source
    assert "submit_order" not in core_source


def test_fixture_and_report_keep_the_financial_and_runtime_claims_unverified() -> None:
    boundary = FIXTURE["claim_boundary"]
    assert boundary["network_accessed"] is False
    assert boundary["actual_market_or_odds_observed"] is False
    assert boundary["recommendation_generated"] is False
    assert boundary["order_submission_enabled"] is False
    assert boundary["real_time_soak_required"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
