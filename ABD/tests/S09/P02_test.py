from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.tennis_combat_models import (
    TennisCombatAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
)
from combat_model import CombatModelInputError, build_combat_market_anchored_prediction, load_feature_availability_registry as load_combat_registry
from generic_residual import PROBABILITY_SUM_TOLERANCE, canonical_json_bytes, load_market_family_registry
from tennis_model import TennisModelInputError, build_tennis_market_anchored_prediction, load_feature_availability_registry as load_tennis_registry


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S09_P02.json").read_text(encoding="utf-8"))
FEATURE_REGISTRY = load_tennis_registry(ROOT / "feature_availability.json")
MARKET_REGISTRY = load_market_family_registry(ROOT / "market_family_registry.json")
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _case(identifier: str) -> dict:
    matches = [row for row in FIXTURE["cases"] if row["case_id"] == identifier]
    assert len(matches) == 1
    return deepcopy(matches[0])


def _run(row: dict) -> dict:
    if row["model"] == "tennis":
        return build_tennis_market_anchored_prediction(row["input"], FEATURE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    if row["model"] == "combat":
        return build_combat_market_anchored_prediction(row["input"], FEATURE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    raise AssertionError("unexpected fixture model")


def _sum(outcomes: list[dict]) -> Decimal:
    return sum((Decimal(outcome["fused_probability"]) for outcome in outcomes), Decimal("0"))


def test_candidate_preflight_passes_without_generated_phase_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == FIXTURE["contract_id"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= 25
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_report_is_an_exact_deterministic_replay_of_the_frozen_fixture() -> None:
    from abd_acceptance.tennis_combat_models import build_report

    report = build_report(FIXTURE, FEATURE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    assert hashlib.sha256(canonical_json_bytes(report)).hexdigest() == FIXTURE["expected_report_sha256"]
    assert report["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert report["summary"]["all_time_safe_results_remain_market_anchored"] is True
    assert report["summary"]["all_fallback_results_zero_residual"] is True


@pytest.mark.parametrize(
    "identifier",
    [
        "TENNIS_POSITIVE",
        "TENNIS_BOUNDARY_AT_DECISION",
        "TENNIS_UNCONFIRMED",
        "COMBAT_POSITIVE",
        "COMBAT_FUTURE_REQUIRED_FEATURE",
    ],
)
def test_each_frozen_case_matches_its_time_and_market_contract(identifier: str) -> None:
    row = _case(identifier)
    result = _run(row)
    expected = row["expected"]
    prediction = result["market_anchored_prediction"]
    assert result["temporal_safe"] is expected["temporal_safe"]
    assert prediction["residual_weight"] == expected["residual_weight"]
    assert prediction["market_prior_weight"] == expected["market_prior_weight"]
    assert prediction["decision"] == expected["decision"]
    assert _sum(prediction["outcomes"]) == Decimal("1")
    assert Decimal(prediction["market_prior_weight"]) >= Decimal("0.50")


@pytest.mark.parametrize(
    "identifier,container,feature_id",
    [
        ("TENNIS_POSITIVE", "players", "surface_dynamic_rating"),
        ("COMBAT_POSITIVE", "fighters", "dynamic_rating"),
    ],
)
def test_future_observation_is_excluded_from_asof_selection(identifier: str, container: str, feature_id: str) -> None:
    row = _case(identifier)
    baseline = _run(row)
    modified = deepcopy(row)
    competitor = modified["input"]["competitors"][0]
    modified["input"][container][competitor][feature_id].append(
        {"known_at": "2026-08-15T10:00:00.0001+10:00", "value": "3000"}
    )
    assert _run(modified) == baseline


def test_exact_decision_time_is_allowed_and_plus_point_zero_zero_zero_one_falls_back() -> None:
    boundary = _run(_case("TENNIS_BOUNDARY_AT_DECISION"))
    future = _run(_case("COMBAT_FUTURE_REQUIRED_FEATURE"))
    assert boundary["temporal_safe"] is True
    assert boundary["market_anchored_prediction"]["residual_weight"] == "0.35"
    assert future["temporal_safe"] is False
    assert future["market_anchored_prediction"]["residual_weight"] == "0"


@pytest.mark.parametrize("identifier", ["TENNIS_UNCONFIRMED", "COMBAT_FUTURE_REQUIRED_FEATURE"])
def test_unavailable_or_unconfirmed_feature_keeps_the_market_untouched(identifier: str) -> None:
    row = _case(identifier)
    result = _run(row)
    prediction = result["market_anchored_prediction"]
    assert result["temporal_safe"] is False
    assert prediction["residual_weight"] == "0"
    assert prediction["market_prior_weight"] == "1"
    actual = {item["outcome_id"]: item["fused_probability"] for item in prediction["outcomes"]}
    assert actual == row["input"]["market_probabilities"]


@pytest.mark.parametrize(
    "identifier,error",
    [("TENNIS_POSITIVE", TennisModelInputError), ("COMBAT_POSITIVE", CombatModelInputError)],
)
def test_event_must_be_strictly_after_the_frozen_decision_time(identifier: str, error: type[ValueError]) -> None:
    row = _case(identifier)
    row["input"]["event_at"] = row["input"]["decision_at"]
    with pytest.raises(error):
        _run(row)


@pytest.mark.parametrize(
    "identifier,error",
    [("TENNIS_POSITIVE", TennisModelInputError), ("COMBAT_POSITIVE", CombatModelInputError)],
)
def test_float_probabilities_are_rejected(identifier: str, error: type[ValueError]) -> None:
    row = _case(identifier)
    outcome_id = row["input"]["competitors"][0]
    row["input"]["market_probabilities"][outcome_id] = 0.55
    with pytest.raises(error):
        _run(row)


@pytest.mark.parametrize(
    "identifier,container,feature_id,error",
    [
        ("TENNIS_POSITIVE", "players", "serve_points_won", TennisModelInputError),
        ("COMBAT_POSITIVE", "fighters", "strike_defense_index", CombatModelInputError),
    ],
)
def test_ambiguous_same_timestamp_feature_history_fails_closed(
    identifier: str, container: str, feature_id: str, error: type[ValueError]
) -> None:
    row = _case(identifier)
    competitor = row["input"]["competitors"][0]
    history = row["input"][container][competitor][feature_id]
    history.append(deepcopy(history[0]))
    with pytest.raises(error):
        _run(row)


@pytest.mark.parametrize(
    "identifier,error",
    [("TENNIS_POSITIVE", TennisModelInputError), ("COMBAT_POSITIVE", CombatModelInputError)],
)
def test_timezone_is_required_for_the_decision_clock(identifier: str, error: type[ValueError]) -> None:
    row = _case(identifier)
    row["input"]["decision_at"] = "2026-08-15T10:00:00"
    with pytest.raises(error):
        _run(row)


@pytest.mark.parametrize("identifier", ["TENNIS_POSITIVE", "COMBAT_POSITIVE"])
def test_one_hundred_replays_have_one_hash_without_waiting(identifier: str) -> None:
    row = _case(identifier)
    hashes = {hashlib.sha256(canonical_json_bytes(_run(row))).hexdigest() for _ in range(FIXTURE["replay_count"])}
    assert len(hashes) == 1


def test_ten_thousand_deterministic_adverse_perturbations_do_not_require_real_time_soak() -> None:
    tennis_base = _case("TENNIS_POSITIVE")
    tennis_result = _run(tennis_base)
    cache: dict[str, dict] = {}
    for iteration in range(FIXTURE["adverse_replay_count"]):
        mode = ("future", "unconfirmed", "unavailable")[iteration % 3]
        if mode not in cache:
            if mode == "future":
                row = deepcopy(tennis_base)
                row["input"]["players"]["PLAYER_A"]["surface_dynamic_rating"].append(
                    {"known_at": "2026-08-15T10:00:00.0001+10:00", "value": "3000"}
                )
            elif mode == "unconfirmed":
                row = deepcopy(tennis_base)
                row["input"]["players"]["PLAYER_A"]["participation_status"] = [
                    {"known_at": "2026-08-15T09:00:00+10:00", "value": "PROBABLE"}
                ]
            else:
                row = _case("COMBAT_FUTURE_REQUIRED_FEATURE")
            cache[mode] = _run(row)
        result = cache[mode]
        if mode == "future":
            assert result == tennis_result
        else:
            prediction = result["market_anchored_prediction"]
            assert result["temporal_safe"] is False
            assert prediction["residual_weight"] == "0"
            assert _sum(prediction["outcomes"]) == Decimal("1")
    assert set(cache) == {"future", "unconfirmed", "unavailable"}


def test_feature_registry_policy_drift_is_rejected_by_both_models() -> None:
    drifted = deepcopy(FEATURE_REGISTRY)
    drifted["policy"]["missing_required_feature_action"] = "MODEL_ONLY"
    with pytest.raises(TennisModelInputError):
        build_tennis_market_anchored_prediction(
            _case("TENNIS_POSITIVE")["input"], drifted, MARKET_REGISTRY, PARAMETERS
        )
    with pytest.raises(CombatModelInputError):
        build_combat_market_anchored_prediction(
            _case("COMBAT_POSITIVE")["input"], drifted, MARKET_REGISTRY, PARAMETERS
        )


def test_core_sources_have_no_network_process_soak_float_or_order_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    for relative in ("tennis_model.py", "combat_model.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not imports.intersection(prohibited)
        assert "sleep(" not in source
        assert "float(" not in source
        assert "submit_order" not in source
        assert '"order_submission_enabled": False' in source


def test_rollback_drill_is_hash_only_and_changes_no_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flags"] == ["model:tennis_surface_serve_return", "model:combat_rating_style_readiness"]
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert all(item["status"] == "PASS" for item in rollback["artifacts"].values())


def test_candidate_fails_closed_when_feature_registry_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "feature_availability.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["policy"]["future_information_tolerance"] = 1
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P02-MODELS-AND-FIXTURE" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p01_signed_predecessor_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / "machine/evidence/EVD-S09-P01.json").write_text("{}\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P02-P01-PREDECESSOR-PASS" in result["summary"]["failed_check_ids"]


def test_phase_receipt_is_absent_before_delivery_and_cannot_be_claimed(tmp_path: Path) -> None:
    with pytest.raises((TennisCombatAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(tmp_path)


def test_cli_is_wired_to_the_exact_contract_and_preserves_no_order_boundary() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S09-P02": write_tennis_combat_models_phase_evidence' in source
    assert '"AC-S09-P02": verify_tennis_combat_models_phase_evidence' in source
    assert load_combat_registry(ROOT / "feature_availability.json") == FEATURE_REGISTRY


def test_fixture_and_report_keep_financial_and_runtime_claims_unverified() -> None:
    boundary = FIXTURE["claim_boundary"]
    assert boundary["network_accessed"] is False
    assert boundary["actual_market_or_odds_observed"] is False
    assert boundary["recommendation_generated"] is False
    assert boundary["order_submission_enabled"] is False
    assert boundary["real_time_soak_required"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert PROBABILITY_SUM_TOLERANCE == Decimal("0.000000000001")
