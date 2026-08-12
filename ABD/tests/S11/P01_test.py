from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.friction import (
    FrictionAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from friction import (
    FrictionInputError,
    artifact_sha256,
    build_artifacts,
    build_backtest,
    build_model,
    canonical_json_bytes,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S11_P01.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S11-P01"
    assert result["next"] == "S11/P02_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 28
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_model_and_backtest_are_exact_frozen_replays() -> None:
    model, backtest = build_artifacts(FIXTURE, PARAMETERS)
    assert artifact_sha256(model) == FIXTURE["expected_model_sha256"]
    assert artifact_sha256(backtest) == FIXTURE["expected_backtest_sha256"]
    assert json.loads((ROOT / "friction_model.json").read_text(encoding="utf-8")) == model
    assert json.loads((ROOT / "friction_backtest.json").read_text(encoding="utf-8")) == backtest
    assert model["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert backtest["next"] == "S11/P02_READY_NOT_STARTED"


def test_effective_friction_is_maximum_of_default_and_rolling_p95() -> None:
    model = build_model(FIXTURE, PARAMETERS)
    expected = {
        "MORE_THAN_2H": ("0.01", "0.011", "0.011"),
        "15M_TO_2H": ("0.015", "0.013", "0.015"),
        "0_TO_15M": ("0.02", "0.021", "0.021"),
        "LIVE": ("0.03", "0.034", "0.034"),
    }
    for row in model["time_bands"]:
        default, observed_p95, effective = expected[row["time_band"]]
        assert (row["default_friction"], row["rolling_observed_p95"], row["effective_friction"]) == (default, observed_p95, effective)
        assert Decimal(row["effective_friction"]) == max(Decimal(default), Decimal(observed_p95))


def test_observed_p95_includes_every_friction_component() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["time_bands"][0]["observations"][-1]["rejection"] = "0.011"
    model = build_model(mutated, PARAMETERS)
    more_than_2h = model["time_bands"][0]
    assert more_than_2h["rolling_observed_p95"] == "0.021"
    assert more_than_2h["effective_friction"] == "0.021"


def test_net_expectation_adverse_boundaries_reduce_every_candidate() -> None:
    backtest = build_backtest(FIXTURE, PARAMETERS)
    assert len(backtest["candidate_results"]) == 4
    for row in backtest["candidate_results"]:
        assert Decimal(row["adverse_friction"]) == Decimal(row["effective_friction"]) + Decimal("0.0001")
        assert Decimal(row["adverse_odds"]) == Decimal(row["odds"]) - Decimal("0.000001")
        assert Decimal(row["adverse_net_expected"]) < Decimal(row["net_expected"])
        assert row["action"] == "NO_ORDER_RESEARCH_ONLY"


def test_positive_research_net_expectation_does_not_enable_a_recommendation_or_order() -> None:
    backtest = build_backtest(FIXTURE, PARAMETERS)
    assert backtest["summary"]["positive_net_expected_count"] == 3
    assert backtest["summary"]["recommendations_enabled"] is False
    assert backtest["summary"]["order_actions_enabled"] is False
    assert {row["action"] for row in backtest["candidate_results"]} == {"NO_ORDER_RESEARCH_ONLY"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture.update({"rolling_window_size": 4}),
        lambda fixture: fixture["time_bands"].pop(),
        lambda fixture: fixture["time_bands"][0]["observations"][0].update({"observation_index": 2}),
        lambda fixture: fixture["time_bands"][0]["observations"][0].update({"operational": "1"}),
        lambda fixture: fixture["claim_boundary"].update({"network_accessed": True}),
    ],
)
def test_malformed_or_unsafe_fixture_fails_closed(mutate) -> None:
    mutated = deepcopy(FIXTURE)
    mutate(mutated)
    with pytest.raises(FrictionInputError):
        validate_fixture(mutated, PARAMETERS)


def test_unknown_time_band_and_non_decimal_input_fail_closed() -> None:
    unknown_band = deepcopy(FIXTURE)
    unknown_band["candidates"][0]["time_band"] = "UNKNOWN"
    with pytest.raises(FrictionInputError):
        validate_fixture(unknown_band, PARAMETERS)
    non_decimal = deepcopy(FIXTURE)
    non_decimal["candidates"][0]["odds"] = 1.8
    with pytest.raises(FrictionInputError):
        validate_fixture(non_decimal, PARAMETERS)


def test_deterministic_replay_hash_is_identical_without_waiting() -> None:
    hashes = {
        hashlib.sha256(canonical_json_bytes(build_artifacts(FIXTURE, PARAMETERS)[1])).hexdigest()
        for _ in range(3)
    }
    assert hashes == {FIXTURE["expected_backtest_sha256"]}


def test_core_source_has_no_network_process_soak_or_order_capability() -> None:
    source = (ROOT / "friction.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection(prohibited)
    assert "sleep(" not in source
    assert "submit_order" not in source
    assert "retry_order" not in source
    assert "float(" not in source


def test_candidate_fails_closed_when_frozen_model_artifact_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "friction_model.json"
    model = json.loads(path.read_text(encoding="utf-8"))
    model["next"] = "S11/P99_READY"
    path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P01-FROZEN-MODEL-AND-BACKTEST-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_expected_replay_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S11_P01.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_backtest_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P01-FROZEN-MODEL-AND-BACKTEST-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_friction_rule_is_weakened(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/facts/parameters.json"
    parameters = json.loads(path.read_text(encoding="utf-8"))
    parameters["friction"]["effective_rule"] = "MIN(DEFAULT, ROLLING_OBSERVED_P95)"
    path.write_text(json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P01-BASELINE-PARAMETERS" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:friction_executable_net_expectation"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S11-P01": write_friction_phase_evidence' in source
    assert '"AC-S11-P01": verify_friction_phase_evidence' in source
    with pytest.raises((FrictionAcceptanceError, FileNotFoundError)):
        from abd_acceptance.friction import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
