"""Targeted deterministic tests for ABD S09/P04 only.

The ten-thousand adverse checks are CPU-only fixture replays.  They deliberately
perform no real-time soak or external operation.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.multi_sport_fallback import (
    MultiSportFallbackAcceptanceError,
    build_report,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
)
from baseball_model import BaseballModelInputError, build_baseball_market_anchored_prediction
from basketball_model import BasketballModelInputError, build_basketball_market_anchored_prediction
from generic_residual import PROBABILITY_SUM_TOLERANCE, canonical_json_bytes, load_market_family_registry
from racing_model import (
    RacingModelInputError,
    build_niche_market_only_prediction,
    build_racing_market_anchored_prediction,
    load_niche_fallback_registry,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S09_P04.json").read_text(encoding="utf-8"))
NICHE_REGISTRY = load_niche_fallback_registry(ROOT / "niche_fallback.json")
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
    if row["model"] == "racing":
        return build_racing_market_anchored_prediction(row["input"], NICHE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    if row["model"] == "basketball":
        return build_basketball_market_anchored_prediction(row["input"], NICHE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    if row["model"] == "baseball":
        return build_baseball_market_anchored_prediction(row["input"], NICHE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    if row["model"] == "niche":
        return build_niche_market_only_prediction(row["input"], NICHE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    raise AssertionError("unexpected fixture model")


def _sum(outcomes: list[dict]) -> Decimal:
    return sum((Decimal(outcome["fused_probability"]) for outcome in outcomes), Decimal("0"))


def test_candidate_preflight_passes_without_generated_phase_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == FIXTURE["contract_id"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= 30
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_report_is_an_exact_deterministic_replay_of_the_frozen_fixture() -> None:
    report = build_report(FIXTURE, NICHE_REGISTRY, MARKET_REGISTRY, PARAMETERS)
    assert hashlib.sha256(canonical_json_bytes(report)).hexdigest() == FIXTURE["expected_report_sha256"]
    assert report["summary"] == {
        "case_count": 7,
        "time_safe_increment_case_count": 4,
        "market_only_fallback_case_count": 3,
        "all_time_safe_results_remain_market_anchored": True,
        "all_unproven_or_unavailable_results_zero_residual": True,
        "niche_market_only_case_count": 1,
    }


@pytest.mark.parametrize(
    "identifier",
    [
        "RACING_POSITIVE",
        "RACING_FUTURE_REQUIRED_FEATURE",
        "BASKETBALL_POSITIVE",
        "BASKETBALL_UNCONFIRMED",
        "BASEBALL_POSITIVE",
        "BASEBALL_BOUNDARY_AT_DECISION",
        "NICHE_MARKET_ONLY",
    ],
)
def test_each_frozen_case_matches_its_market_and_fallback_contract(identifier: str) -> None:
    row = _case(identifier)
    result = _run(row)
    expected = row["expected"]
    prediction = result["market_anchored_prediction"]
    assert result.get("temporal_safe", False) is expected["temporal_safe"]
    assert prediction["residual_weight"] == expected["residual_weight"]
    assert prediction["market_prior_weight"] == expected["market_prior_weight"]
    assert prediction["decision"] == expected["decision"]
    assert _sum(prediction["outcomes"]) == Decimal("1")
    assert Decimal(prediction["market_prior_weight"]) >= Decimal("0.50")
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False


def test_racing_plackett_luce_and_harville_probabilities_preserve_complete_mass() -> None:
    result = _run(_case("RACING_POSITIVE"))
    win = result["plackett_luce_win_probabilities"]
    exacta = result["harville_exacta_probabilities"]
    assert sum((Decimal(value) for value in win.values()), Decimal("0")) == Decimal("1")
    assert abs(sum((Decimal(row["probability"]) for row in exacta), Decimal("0")) - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
    assert {(row["first"], row["second"]) for row in exacta} == {
        ("RUNNER_A", "RUNNER_B"),
        ("RUNNER_A", "RUNNER_C"),
        ("RUNNER_B", "RUNNER_A"),
        ("RUNNER_B", "RUNNER_C"),
        ("RUNNER_C", "RUNNER_A"),
        ("RUNNER_C", "RUNNER_B"),
    }


def test_future_observation_is_excluded_from_racing_asof_selection() -> None:
    row = _case("RACING_POSITIVE")
    baseline = _run(row)
    modified = deepcopy(row)
    modified["input"]["features"]["runner_strengths"].append(
        {"known_at": "2026-08-17T10:00:00.0001+10:00", "value": {"RUNNER_A": "100", "RUNNER_B": "1", "RUNNER_C": "1"}}
    )
    assert _run(modified) == baseline


def test_exact_decision_time_is_allowed_while_plus_point_zero_zero_zero_one_and_unconfirmed_fall_back() -> None:
    boundary = _run(_case("BASEBALL_BOUNDARY_AT_DECISION"))
    future = _run(_case("RACING_FUTURE_REQUIRED_FEATURE"))
    unconfirmed = _run(_case("BASKETBALL_UNCONFIRMED"))
    assert boundary["temporal_safe"] is True
    assert boundary["market_anchored_prediction"]["residual_weight"] == "0.35"
    assert future["temporal_safe"] is False
    assert future["market_anchored_prediction"]["residual_weight"] == "0"
    assert unconfirmed["temporal_safe"] is False
    assert unconfirmed["market_anchored_prediction"]["residual_weight"] == "0"


@pytest.mark.parametrize("identifier", ["RACING_FUTURE_REQUIRED_FEATURE", "BASKETBALL_UNCONFIRMED", "NICHE_MARKET_ONLY"])
def test_unproven_or_unavailable_input_keeps_the_market_untouched(identifier: str) -> None:
    row = _case(identifier)
    result = _run(row)
    prediction = result["market_anchored_prediction"]
    assert prediction["residual_weight"] == "0"
    assert prediction["market_prior_weight"] == "1"
    assert {item["outcome_id"]: item["fused_probability"] for item in prediction["outcomes"]} == row["input"]["market_probabilities"]
    if row["model"] == "niche":
        assert result["action"] == "MARKET_ONLY_OR_NO_ADVICE"


@pytest.mark.parametrize(
    "identifier,error",
    [
        ("RACING_POSITIVE", RacingModelInputError),
        ("BASKETBALL_POSITIVE", BasketballModelInputError),
        ("BASEBALL_POSITIVE", BaseballModelInputError),
    ],
)
def test_event_must_be_strictly_after_the_frozen_decision_time(identifier: str, error: type[ValueError]) -> None:
    row = _case(identifier)
    row["input"]["event_at"] = row["input"]["decision_at"]
    with pytest.raises(error):
        _run(row)


@pytest.mark.parametrize(
    "identifier,error",
    [
        ("RACING_POSITIVE", RacingModelInputError),
        ("BASKETBALL_POSITIVE", BasketballModelInputError),
        ("BASEBALL_POSITIVE", BaseballModelInputError),
    ],
)
def test_float_market_probabilities_are_rejected(identifier: str, error: type[ValueError]) -> None:
    row = _case(identifier)
    outcome = row["input"]["competitors"][0]
    row["input"]["market_probabilities"][outcome] = 0.5
    with pytest.raises(error):
        _run(row)


def test_ambiguous_same_timestamp_feature_history_fails_closed() -> None:
    row = _case("BASEBALL_POSITIVE")
    history = row["input"]["features"]["home_offense_index"]
    history.append(deepcopy(history[0]))
    with pytest.raises(BaseballModelInputError):
        _run(row)


@pytest.mark.parametrize(
    "identifier,error",
    [
        ("RACING_POSITIVE", RacingModelInputError),
        ("BASKETBALL_POSITIVE", BasketballModelInputError),
        ("BASEBALL_POSITIVE", BaseballModelInputError),
    ],
)
def test_timezone_is_required_for_the_decision_clock(identifier: str, error: type[ValueError]) -> None:
    row = _case(identifier)
    row["input"]["decision_at"] = "2026-08-19T10:00:00"
    with pytest.raises(error):
        _run(row)


def test_niche_policy_drift_is_rejected_by_all_scoped_models() -> None:
    drifted = deepcopy(NICHE_REGISTRY)
    drifted["policy"]["unproven_domain_model_action"] = "MODEL_ONLY"
    with pytest.raises(RacingModelInputError):
        build_racing_market_anchored_prediction(_case("RACING_POSITIVE")["input"], drifted, MARKET_REGISTRY, PARAMETERS)
    with pytest.raises(BasketballModelInputError):
        build_basketball_market_anchored_prediction(_case("BASKETBALL_POSITIVE")["input"], drifted, MARKET_REGISTRY, PARAMETERS)
    with pytest.raises(BaseballModelInputError):
        build_baseball_market_anchored_prediction(_case("BASEBALL_POSITIVE")["input"], drifted, MARKET_REGISTRY, PARAMETERS)


def test_core_sources_have_no_network_process_soak_float_or_order_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    for relative in ("racing_model.py", "basketball_model.py", "baseball_model.py"):
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


@pytest.mark.parametrize("identifier", ["RACING_POSITIVE", "BASKETBALL_POSITIVE", "BASEBALL_POSITIVE", "NICHE_MARKET_ONLY"])
def test_one_hundred_replays_have_one_hash_without_waiting(identifier: str) -> None:
    row = _case(identifier)
    hashes = {hashlib.sha256(canonical_json_bytes(_run(row))).hexdigest() for _ in range(FIXTURE["replay_count"])}
    assert len(hashes) == 1


def test_ten_thousand_deterministic_adverse_perturbations_do_not_require_real_time_soak() -> None:
    base = _case("BASKETBALL_POSITIVE")
    baseline = _run(base)
    cache: dict[str, dict] = {}
    for iteration in range(FIXTURE["adverse_replay_count"]):
        mode = ("future", "unconfirmed", "market_tick", "niche")[iteration % 4]
        if mode not in cache:
            if mode == "future":
                row = deepcopy(base)
                row["input"]["features"]["home_pace"].append({"known_at": "2026-08-18T10:00:00.0001+10:00", "value": "130"})
            elif mode == "unconfirmed":
                row = deepcopy(base)
                row["input"]["features"]["participation_status"] = [{"known_at": "2026-08-18T09:00:00+10:00", "value": "PROBABLE"}]
            elif mode == "market_tick":
                row = deepcopy(base)
                row["input"]["market_probabilities"] = {"HOME": "0.5399", "AWAY": "0.4601"}
            else:
                row = _case("NICHE_MARKET_ONLY")
            cache[mode] = _run(row)
        result = cache[mode]
        prediction = result["market_anchored_prediction"]
        if mode == "future":
            assert result == baseline
        elif mode in {"unconfirmed", "niche"}:
            assert prediction["residual_weight"] == "0"
        else:
            assert prediction["residual_weight"] == "0.35"
            assert _sum(prediction["outcomes"]) == Decimal("1")
    assert set(cache) == {"future", "unconfirmed", "market_tick", "niche"}


def test_rollback_drill_is_hash_only_and_changes_no_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flags"] == [
        "model:racing_plackett_luce_harville",
        "model:basketball_pace_efficiency",
        "model:baseball_pitcher_bullpen",
        "policy:niche_market_only",
    ]
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert all(item["status"] == "PASS" for item in rollback["artifacts"].values())


def test_candidate_fails_closed_when_niche_policy_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "niche_fallback.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["niche_market_only"]["default_action"] = "MODEL_ONLY"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P04-MODELS-AND-FIXTURE" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p03_signed_predecessor_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    (clone / "machine/evidence/EVD-S09-P03.json").write_text("{}\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S09P04-P03-PREDECESSOR-PASS" in result["summary"]["failed_check_ids"]


def test_phase_receipt_is_absent_before_delivery_and_cannot_be_claimed(tmp_path: Path) -> None:
    with pytest.raises((MultiSportFallbackAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(tmp_path)


def test_cli_is_wired_to_the_exact_contract_and_preserves_no_order_boundary() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S09-P04": write_multi_sport_fallback_phase_evidence' in source
    assert '"AC-S09-P04": verify_multi_sport_fallback_phase_evidence' in source


def test_fixture_and_report_keep_financial_and_runtime_claims_unverified() -> None:
    boundary = FIXTURE["claim_boundary"]
    assert boundary["network_accessed"] is False
    assert boundary["actual_market_or_odds_observed"] is False
    assert boundary["recommendation_generated"] is False
    assert boundary["order_submission_enabled"] is False
    assert boundary["real_time_soak_required"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert PROBABILITY_SUM_TOLERANCE == Decimal("0.000000000001")
