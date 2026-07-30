from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.score_football_models import (
    ScoreFootballAcceptanceError,
    build_report,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
)
from football_model import FootballModelInputError, build_football_market_anchored_prediction, load_distribution_registry
from generic_residual import PROBABILITY_SUM_TOLERANCE, canonical_json_bytes, load_market_family_registry
from score_models import (
    ScoreModelInputError,
    build_score_projection,
    dixon_coles_scoreline_distribution,
    negative_binomial_distribution,
    poisson_distribution,
    skellam_distribution,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S09_P03.json").read_text(encoding="utf-8"))
REGISTRY = load_distribution_registry(ROOT / "distribution_tests.json")
MARKET_REGISTRY = load_market_family_registry(ROOT / "market_family_registry.json")
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _football_case(identifier: str) -> dict:
    matches = [row for row in FIXTURE["football_cases"] if row["case_id"] == identifier]
    assert len(matches) == 1
    return deepcopy(matches[0])


def _football(row: dict) -> dict:
    return build_football_market_anchored_prediction(row["input"], REGISTRY, MARKET_REGISTRY, PARAMETERS)


def _sum_outcomes(outcomes: list[dict]) -> Decimal:
    return sum((Decimal(row["fused_probability"]) for row in outcomes), Decimal("0"))


def _report() -> dict:
    return build_report(FIXTURE, REGISTRY, MARKET_REGISTRY, PARAMETERS)


def test_candidate_preflight_passes_without_generated_phase_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == FIXTURE["contract_id"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= 29
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_report_is_an_exact_deterministic_replay_of_the_frozen_fixture() -> None:
    report = _report()
    assert hashlib.sha256(canonical_json_bytes(report)).hexdigest() == FIXTURE["expected_report_sha256"]
    assert report["summary"] == {
        "distribution_vector_count": 5,
        "football_case_count": 5,
        "time_safe_increment_case_count": 2,
        "market_only_fallback_case_count": 3,
        "all_safe_results_remain_market_anchored": True,
        "all_fallback_results_zero_residual": True,
    }


@pytest.mark.parametrize(
    "vector_id",
    ["POISSON_REFERENCE", "DIXON_COLES_REFERENCE", "SKELLAM_REFERENCE", "NEGATIVE_BINOMIAL_REFERENCE"],
)
def test_each_frozen_distribution_preserves_mass_and_bounded_tail(vector_id: str) -> None:
    rows = {row["vector_id"]: row for row in _report()["distributions"]}
    row = rows[vector_id]
    finite_mass = Decimal(row["finite_mass"])
    tail = Decimal(row["tail_probability"])
    assert abs((finite_mass + tail) - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
    assert tail <= Decimal("0.000000000001")
    assert all(Decimal(value) > Decimal("0") for value in row["anchors"].values())


def test_dixon_coles_adjusts_only_low_score_cells_and_keeps_nonnegative_mass() -> None:
    independent = dixon_coles_scoreline_distribution("1.4", "1.0", "0", 18)
    adjusted = dixon_coles_scoreline_distribution("1.4", "1.0", "-0.04", 18)
    lookup = lambda rows, home, away: next(
        Decimal(row["probability"]) for row in rows if row["home_goals"] == home and row["away_goals"] == away
    )
    assert lookup(independent["scorelines"], 0, 0) != lookup(adjusted["scorelines"], 0, 0)
    assert lookup(independent["scorelines"], 2, 2) == lookup(adjusted["scorelines"], 2, 2)
    assert all(Decimal(row["probability"]) >= Decimal("0") for row in adjusted["scorelines"])


def test_skellam_is_symmetric_when_home_and_away_rates_match() -> None:
    distribution = skellam_distribution("1.2", "1.2", 18)
    values = {row["goal_difference"]: Decimal(row["probability"]) for row in distribution["probabilities"]}
    assert values[-1] == values[1]
    assert values[-2] == values[2]
    assert Decimal(distribution["tail_probability"]) <= Decimal("0.000000000001")


def test_negative_binomial_tail_is_explicit_and_mass_is_complete() -> None:
    distribution = negative_binomial_distribution("2.4", "8", 40)
    assert abs(Decimal(distribution["finite_mass"]) + Decimal(distribution["tail_probability"]) - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
    assert Decimal(distribution["tail_probability"]) <= Decimal("0.000000000001")
    assert Decimal(distribution["probabilities"][0]["probability"]) > Decimal("0")


@pytest.mark.parametrize("mapping_id", ["ONE_X_TWO", "TOTALS_2_5", "BOTH_TEAMS_TO_SCORE"])
def test_score_projection_maps_each_required_market_only_after_tail_gate(mapping_id: str) -> None:
    projection = build_score_projection("1.4", "1.0", "-0.04", "8", REGISTRY)
    mapping = projection["market_mappings"][mapping_id]
    assert projection["mapping_status"] == "COMPLETE_WITHIN_TAIL_TOLERANCE"
    assert mapping["status"] == "COMPLETE_WITHIN_TAIL_TOLERANCE"
    assert sum((Decimal(value) for value in mapping["outcomes"].values()), Decimal("0")) == Decimal("1")
    assert Decimal(mapping["tail_probability"]) <= Decimal("0.000000000001")


@pytest.mark.parametrize(
    "identifier",
    [
        "FOOTBALL_POSITIVE",
        "FOOTBALL_BOUNDARY_AT_DECISION",
        "FOOTBALL_FUTURE_REQUIRED_FEATURE",
        "FOOTBALL_UNCONFIRMED",
        "FOOTBALL_TAIL_FALLBACK",
    ],
)
def test_each_frozen_football_case_matches_its_market_and_temporal_contract(identifier: str) -> None:
    row = _football_case(identifier)
    result = _football(row)
    expected = row["expected"]
    prediction = result["market_anchored_prediction"]
    assert result["temporal_safe"] is expected["temporal_safe"]
    assert prediction["residual_weight"] == expected["residual_weight"]
    assert prediction["market_prior_weight"] == expected["market_prior_weight"]
    assert prediction["decision"] == expected["decision"]
    assert _sum_outcomes(prediction["outcomes"]) == Decimal("1")
    assert Decimal(prediction["market_prior_weight"]) >= Decimal("0.50")


def test_future_observation_is_excluded_from_football_asof_selection() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    baseline = _football(row)
    modified = deepcopy(row)
    modified["input"]["features"]["league_home_goal_rate"].append(
        {"known_at": "2026-08-16T10:00:00.0001+10:00", "value": "3"}
    )
    assert _football(modified) == baseline


def test_exact_decision_time_is_allowed_while_plus_point_zero_zero_zero_one_and_high_tail_fall_back() -> None:
    boundary = _football(_football_case("FOOTBALL_BOUNDARY_AT_DECISION"))
    future = _football(_football_case("FOOTBALL_FUTURE_REQUIRED_FEATURE"))
    tail = _football(_football_case("FOOTBALL_TAIL_FALLBACK"))
    assert boundary["market_anchored_prediction"]["residual_weight"] == "0.35"
    assert future["market_anchored_prediction"]["residual_weight"] == "0"
    assert tail["temporal_safe"] is True
    assert tail["market_anchored_prediction"]["residual_weight"] == "0"
    assert tail["score_projection"]["mapping_status"] == "MARKET_ONLY_TAIL_ABOVE_TOLERANCE"


def test_float_market_probability_is_rejected() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    row["input"]["market_probabilities"]["HOME"] = 0.48
    with pytest.raises(FootballModelInputError):
        _football(row)


def test_event_must_be_strictly_after_decision_time() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    row["input"]["event_at"] = row["input"]["decision_at"]
    with pytest.raises(FootballModelInputError):
        _football(row)


def test_ambiguous_same_timestamp_feature_history_fails_closed() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    history = row["input"]["features"]["league_home_goal_rate"]
    history.append(deepcopy(history[0]))
    with pytest.raises(FootballModelInputError):
        _football(row)


def test_timezone_is_required_for_decision_clock() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    row["input"]["decision_at"] = "2026-08-16T10:00:00"
    with pytest.raises(FootballModelInputError):
        _football(row)


def test_distribution_registry_policy_and_football_contract_drift_are_rejected() -> None:
    drifted = deepcopy(REGISTRY)
    drifted["policy"]["tail_tolerance"] = "1"
    with pytest.raises(ScoreModelInputError):
        build_score_projection("1.4", "1.0", "-0.04", "8", drifted)
    with pytest.raises(FootballModelInputError):
        build_football_market_anchored_prediction(_football_case("FOOTBALL_POSITIVE")["input"], drifted, MARKET_REGISTRY, PARAMETERS)


def test_hierarchical_rate_outside_frozen_bounds_fails_closed() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    row["input"]["features"]["league_home_goal_rate"] = [
        {"known_at": "2026-08-15T12:00:00+10:00", "value": "3.0001"}
    ]
    with pytest.raises(FootballModelInputError):
        _football(row)


def test_one_hundred_replays_have_one_hash_without_waiting() -> None:
    row = _football_case("FOOTBALL_POSITIVE")
    hashes = {hashlib.sha256(canonical_json_bytes(_football(row))).hexdigest() for _ in range(FIXTURE["replay_count"])}
    assert len(hashes) == 1


def test_ten_thousand_deterministic_adverse_perturbations_do_not_require_real_time_soak() -> None:
    base = _football_case("FOOTBALL_POSITIVE")
    baseline = _football(base)
    cache: dict[str, dict] = {}
    for iteration in range(FIXTURE["adverse_replay_count"]):
        mode = ("future", "market_tick", "tail")[iteration % 3]
        if mode not in cache:
            if mode == "future":
                row = deepcopy(base)
                row["input"]["features"]["home_attack_effect"].append(
                    {"known_at": "2026-08-16T10:00:00.0001+10:00", "value": "1"}
                )
            elif mode == "market_tick":
                row = deepcopy(base)
                row["input"]["market_probabilities"] = {"HOME": "0.4799", "DRAW": "0.27", "AWAY": "0.2501"}
            else:
                row = _football_case("FOOTBALL_TAIL_FALLBACK")
            cache[mode] = _football(row)
        result = cache[mode]
        prediction = result["market_anchored_prediction"]
        if mode == "future":
            assert result == baseline
        elif mode == "tail":
            assert prediction["residual_weight"] == "0"
        else:
            assert prediction["residual_weight"] == "0.35"
            assert _sum_outcomes(prediction["outcomes"]) == Decimal("1")
        assert Decimal(prediction["market_prior_weight"]) >= Decimal("0.50")
    assert set(cache) == {"future", "market_tick", "tail"}


def test_core_sources_have_no_network_process_soak_float_or_order_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    for relative in ("score_models.py", "football_model.py"):
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
    assert rollback["feature_flags"] == ["model:football_hierarchical_score"]
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert all(item["status"] == "PASS" for item in rollback["artifacts"].values())


def test_candidate_fails_closed_when_distribution_registry_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "distribution_tests.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["policy"]["tail_tolerance"] = "1"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P03-MODELS-AND-FIXTURE" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p02_signed_predecessor_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / "machine/evidence/EVD-S09-P02.json").write_text("{}\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P03-P02-PREDECESSOR-PASS" in result["summary"]["failed_check_ids"]


def test_phase_receipt_is_absent_before_delivery_and_cannot_be_claimed(tmp_path: Path) -> None:
    with pytest.raises((ScoreFootballAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(tmp_path)


def test_cli_is_wired_to_exact_contract_and_distribution_registry() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S09-P03": write_score_football_models_phase_evidence' in source
    assert '"AC-S09-P03": verify_score_football_models_phase_evidence' in source
    assert load_distribution_registry(ROOT / "distribution_tests.json") == REGISTRY


def test_fixture_and_report_keep_financial_and_runtime_claims_unverified() -> None:
    boundary = FIXTURE["claim_boundary"]
    assert boundary["network_accessed"] is False
    assert boundary["actual_market_or_odds_observed"] is False
    assert boundary["recommendation_generated"] is False
    assert boundary["order_submission_enabled"] is False
    assert boundary["real_time_soak_required"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert PROBABILITY_SUM_TOLERANCE == Decimal("0.000000000001")


def test_zero_rate_poisson_is_exact_at_zero_and_nonnegative() -> None:
    distribution = poisson_distribution("0", 18)
    assert distribution["probabilities"][0]["probability"] == "1"
    assert all(row["probability"] == "0" for row in distribution["probabilities"][1:])
