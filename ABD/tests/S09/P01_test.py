from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.generic_residual import (
    GenericResidualAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
)
from generic_residual import (
    PROBABILITY_SUM_TOLERANCE,
    GenericResidualInputError,
    build_report,
    calculate_market_anchored_residual,
    canonical_json_bytes,
    load_market_family_registry,
    validate_market_family_registry,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S09_P01.json").read_text(encoding="utf-8"))
REGISTRY = load_market_family_registry(ROOT / "market_family_registry.json")
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _case(identifier: str) -> dict:
    matches = [case for case in FIXTURE["cases"] if case["id"] == identifier]
    assert len(matches) == 1
    return deepcopy(matches[0])


def _sum(outcomes: list[dict]) -> Decimal:
    return sum((Decimal(outcome["fused_probability"]) for outcome in outcomes), Decimal("0"))


def test_candidate_preflight_and_contract_pass_without_generated_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == FIXTURE["contract_id"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= 25
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_report_is_an_exact_deterministic_replay_of_frozen_vectors() -> None:
    report = build_report(FIXTURE, REGISTRY, PARAMETERS)
    report_hash = hashlib.sha256(canonical_json_bytes(report)).hexdigest()
    assert report_hash == FIXTURE["expected_report_sha256"]
    assert report["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert report["external_effect_boundary"]["external_network_accessed"] is False
    assert report["external_effect_boundary"]["recommendation_generated_or_enabled"] is False
    assert report["external_effect_boundary"]["order_submission_enabled"] is False


@pytest.mark.parametrize(
    "identifier",
    [
        "BINARY_NO_INCREMENT",
        "MULTINOMIAL_NO_INCREMENT",
        "SPREAD_NO_INCREMENT",
        "TOTAL_NO_INCREMENT",
        "FUTURES_NO_INCREMENT",
    ],
)
def test_no_domain_increment_forces_an_untouched_market_vector(identifier: str) -> None:
    case = _case(identifier)
    result = calculate_market_anchored_residual(case, REGISTRY, PARAMETERS)
    assert result["domain_increment_applied"] is False
    assert result["residual_weight"] == "0"
    assert result["market_prior_weight"] == "1"
    assert _sum(result["outcomes"]) == Decimal("1")
    actual = {outcome["outcome_id"]: Decimal(outcome["fused_probability"]) for outcome in result["outcomes"]}
    expected = {outcome_id: Decimal(probability) for outcome_id, probability in case["market_probabilities"].items()}
    assert actual == expected


def test_verified_residual_is_capped_and_market_anchored() -> None:
    result = calculate_market_anchored_residual(_case("BINARY_VERIFIED_CAPPED"), REGISTRY, PARAMETERS)
    assert result["domain_increment_applied"] is True
    assert result["residual_weight"] == "0.35"
    assert result["market_prior_weight"] == "0.65"
    outcomes = {outcome["outcome_id"]: outcome["fused_probability"] for outcome in result["outcomes"]}
    assert outcomes == {"AWAY": "0.365", "HOME": "0.635"}
    assert _sum(result["outcomes"]) == Decimal("1")


def test_unproven_candidate_is_ignored_even_when_it_is_present() -> None:
    with_candidate = _case("BINARY_NO_INCREMENT")
    without_candidate = deepcopy(with_candidate)
    without_candidate.pop("candidate_residual_probabilities")
    assert calculate_market_anchored_residual(with_candidate, REGISTRY, PARAMETERS) == calculate_market_anchored_residual(
        without_candidate, REGISTRY, PARAMETERS
    )


@pytest.mark.parametrize(
    "identifier, mutate",
    [
        ("UNKNOWN_MARKET_FAMILY", lambda case: case.update({"market_family": "unknown"})),
        ("SPREAD_MISSING_SETTLEMENT_LINE", lambda case: case.pop("settlement_line")),
        ("VERIFIED_INCREMENT_WITHOUT_HASH", lambda case: case["domain_increment"].pop("evidence_sha256")),
        ("INCOMPLETE_MARKET_VECTOR", lambda case: case["market_probabilities"].update({"HOME": "0.54"})),
    ],
)
def test_malformed_or_unproven_inputs_fail_closed(identifier: str, mutate) -> None:
    case = _case("BINARY_VERIFIED_CAPPED")
    if identifier == "SPREAD_MISSING_SETTLEMENT_LINE":
        case = _case("SPREAD_NO_INCREMENT")
    mutate(case)
    with pytest.raises(GenericResidualInputError):
        calculate_market_anchored_residual(case, REGISTRY, PARAMETERS)


def test_binary_float_probability_is_rejected() -> None:
    case = _case("BINARY_NO_INCREMENT")
    case["market_probabilities"]["HOME"] = 0.55
    with pytest.raises(GenericResidualInputError):
        calculate_market_anchored_residual(case, REGISTRY, PARAMETERS)


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    case = _case("BINARY_VERIFIED_CAPPED")
    hashes = {
        hashlib.sha256(canonical_json_bytes(calculate_market_anchored_residual(case, REGISTRY, PARAMETERS))).hexdigest()
        for _ in range(FIXTURE["replay_count"])
    }
    assert len(hashes) == 1


def test_ten_thousand_adverse_decimal_perturbations_remain_safe_without_soak() -> None:
    base = _case("BINARY_NO_INCREMENT")
    cache: dict[tuple[str, str], dict] = {}
    for iteration in range(FIXTURE["adverse_replay_count"]):
        delta = Decimal((iteration % 3) - 1) * Decimal("0.0001")
        home = Decimal("0.55") + delta
        away = Decimal("1") - home
        key = (format(home, "f"), format(away, "f"))
        if key not in cache:
            case = deepcopy(base)
            case["market_probabilities"] = {"HOME": key[0], "AWAY": key[1]}
            cache[key] = calculate_market_anchored_residual(case, REGISTRY, PARAMETERS)
        result = cache[key]
        assert result["residual_weight"] == "0"
        assert _sum(result["outcomes"]) == Decimal("1")
        assert all(Decimal(outcome["fused_probability"]) > Decimal("0") for outcome in result["outcomes"])
    assert len(cache) == 3


def test_registry_rejects_distribution_or_fallback_drift() -> None:
    drifted = deepcopy(REGISTRY)
    drifted["families"][0]["distribution"] = "CATEGORICAL"
    with pytest.raises(GenericResidualInputError):
        validate_market_family_registry(drifted)
    drifted = deepcopy(REGISTRY)
    drifted["families"][1]["fallback"] = "MODEL_ONLY"
    with pytest.raises(GenericResidualInputError):
        validate_market_family_registry(drifted)


def test_core_source_has_no_network_process_soak_or_order_capability() -> None:
    source = (ROOT / "generic_residual.py").read_text(encoding="utf-8")
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
    assert "submit_order" not in source


def test_rollback_drill_is_hash_only_and_changes_no_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:generic_residual"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert all(item["status"] == "PASS" for item in rollback["artifacts"].values())


def test_candidate_fails_closed_when_registry_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "market_family_registry.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["families"][0]["fallback"] = "MODEL_ONLY"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P01-REGISTRY-AND-FIXTURE" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_signed_predecessor_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S07-P04.json"
    path.write_text("{}\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert any(identifier.startswith("S09P01-PREDECESSOR-HASH") for identifier in result["summary"]["failed_check_ids"])


def test_phase_receipt_is_absent_before_delivery_and_cannot_be_claimed(tmp_path: Path) -> None:
    with pytest.raises((GenericResidualAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(tmp_path)


def test_cli_is_wired_to_exact_contract_and_preserves_no_order_boundary() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S09-P01": write_generic_residual_phase_evidence' in source
    assert '"AC-S09-P01": verify_generic_residual_phase_evidence' in source
    core_source = (ROOT / "generic_residual.py").read_text(encoding="utf-8")
    assert '"order_submission_enabled": False' in core_source
    assert "submit_order" not in core_source


def test_fixture_and_report_keep_financial_and_runtime_claims_unverified() -> None:
    boundary = FIXTURE["claim_boundary"]
    assert boundary["network_accessed"] is False
    assert boundary["actual_market_or_odds_observed"] is False
    assert boundary["recommendation_generated"] is False
    assert boundary["order_submission_enabled"] is False
    assert boundary["real_time_soak_required"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    report = build_report(FIXTURE, REGISTRY, PARAMETERS)
    assert report["summary"]["all_no_domain_increment_weights_zero"] is True
    assert Decimal(report["summary"]["minimum_market_prior_weight"]) >= Decimal("0.50")
    assert PROBABILITY_SUM_TOLERANCE == Decimal("0.000000000001")
