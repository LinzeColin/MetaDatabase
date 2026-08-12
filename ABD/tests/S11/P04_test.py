from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.risk_engine import (
    RiskEngineAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from risk_engine import (
    RiskEngineError,
    artifact_sha256,
    build_correlation_graph,
    build_report,
    evaluate_vector,
    report_sha256,
    validate_correlation_graph,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S11_P04.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
GRAPH = json.loads((ROOT / "correlation_graph.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "risk_vectors.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _vector(vector_id: str) -> dict:
    return next(row for row in VECTORS["vectors"] if row["vector_id"] == vector_id)


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S11-P04"
    assert result["next"] == "S11/STAGE_REVIEW_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 26
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_frozen_graph_vectors_and_report_are_exact_replays() -> None:
    rebuilt = build_correlation_graph(PARAMETERS)
    report = build_report(GRAPH, VECTORS, PARAMETERS)
    assert rebuilt == GRAPH
    assert artifact_sha256(rebuilt) == FIXTURE["expected_correlation_graph_sha256"]
    assert report["report_sha256"] == FIXTURE["expected_report_sha256"]
    assert VECTORS["expected_report_sha256"] == report["report_sha256"]
    assert report_sha256(report) == report["report_sha256"]


@pytest.mark.parametrize(
    ("vector_id", "baseline_action", "final_action", "stake_cents", "reason_code"),
    [
        ("K01-GA-P03-ROUTE-STABLE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", 600, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE"),
        ("K02-BETA-SINGLE-TICKET-CAP", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", 450, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE"),
        ("K03-ALPHA-COEFFICIENT-ZERO", "NO_RECOMMENDATION", "NO_RECOMMENDATION", 0, "STAGE_COEFFICIENT_ZERO"),
        ("K04-EVENT-CAP-REMAINING-CAPACITY", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", 100, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE"),
        ("K05-CLUSTER-CAP-REMAINING-CAPACITY", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", 100, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE"),
        ("K06-OPEN-CAP-REMAINING-CAPACITY", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", 100, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE"),
        ("K07-BELOW-PROVIDER-MINIMUM-NO-UPROUND", "NO_RECOMMENDATION", "NO_RECOMMENDATION", 0, "STAKE_BELOW_PROVIDER_MINIMUM"),
        ("K08-DAILY-LOSS-SOFT-STOP", "NO_RECOMMENDATION", "NO_RECOMMENDATION", 0, "DAILY_LOSS_SOFT_STOP"),
        ("K09-STRATEGY-SLICE-DRAWDOWN-KILL", "NO_RECOMMENDATION", "NO_RECOMMENDATION", 0, "STRATEGY_SLICE_DRAWDOWN_KILL"),
        ("K10-LEDGER-DIFFERENCE-HARD-STOP", "NO_RECOMMENDATION", "NO_RECOMMENDATION", 0, "LEDGER_DIFFERENCE_HARD_STOP"),
        ("K11-RISK-THRESHOLD-POINT-0001-FLIP", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "NO_RECOMMENDATION", 0, "ADVERSE_RISK_STABILITY_FLIP"),
        ("K12-TARGET-SHORTFALL-DIAGNOSTIC-ONLY", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE", 600, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE"),
    ],
)
def test_fixed_vectors_cover_stage_caps_exposure_controls_and_hard_stops(
    vector_id: str,
    baseline_action: str,
    final_action: str,
    stake_cents: int,
    reason_code: str,
) -> None:
    result = evaluate_vector(_vector(vector_id), GRAPH, PARAMETERS)
    assert result["baseline"]["action"] == baseline_action
    assert result["action"] == final_action
    assert result["stake_cents"] == stake_cents
    assert result["reason_code"] == reason_code
    assert result["all_expected_matches"] is True


def test_every_generated_allocation_and_adverse_scenario_respects_all_risk_caps() -> None:
    report = build_report(GRAPH, VECTORS, PARAMETERS)
    for result in report["results"]:
        for scenario in [result["baseline"], *result["scenarios"].values()]:
            assert all(scenario["risk_invariants"].values()), (result["vector_id"], scenario)


@pytest.mark.parametrize("exposure_cents", [0, 1, 95, 100, 1396, 1497, 1500, 1501, 4500])
def test_property_synthetic_exposure_ranges_never_create_a_cap_breach(exposure_cents: int) -> None:
    vector = deepcopy(_vector("K01-GA-P03-ROUTE-STABLE"))
    vector["existing_event_exposure_cents"] = exposure_cents
    vector["existing_cluster_exposure_cents"] = exposure_cents
    vector["existing_open_exposure_cents"] = exposure_cents * 3
    result = evaluate_vector(vector, GRAPH, PARAMETERS)
    for scenario in [result["baseline"], *result["scenarios"].values()]:
        assert all(scenario["risk_invariants"].values())
        assert scenario["stake_cents"] <= scenario["capacity_cents"]["single_ticket"]
        assert scenario["stake_cents"] <= scenario["capacity_cents"]["event"]
        assert scenario["stake_cents"] <= scenario["capacity_cents"]["cluster"]
        assert scenario["stake_cents"] <= scenario["capacity_cents"]["open"]


def test_one_in_ten_thousand_risk_threshold_tightening_flips_to_no_recommendation() -> None:
    result = evaluate_vector(_vector("K11-RISK-THRESHOLD-POINT-0001-FLIP"), GRAPH, PARAMETERS)
    assert result["baseline"]["stake_cents"] == 100
    assert result["scenarios"]["risk_threshold_tightened"]["action"] == "NO_RECOMMENDATION"
    assert result["scenarios"]["all_adverse"]["action"] == "NO_RECOMMENDATION"
    assert result["adverse_flip_dimensions"] == ["risk_threshold_tightened", "all_adverse"]
    assert result["action"] == "NO_RECOMMENDATION"


def test_target_shortfall_is_diagnostic_only_and_never_increases_or_relaxes_stake() -> None:
    base = evaluate_vector(_vector("K01-GA-P03-ROUTE-STABLE"), GRAPH, PARAMETERS)
    shortfall = evaluate_vector(_vector("K12-TARGET-SHORTFALL-DIAGNOSTIC-ONLY"), GRAPH, PARAMETERS)
    assert shortfall["action"] == base["action"]
    assert shortfall["stake_cents"] == base["stake_cents"]
    assert "TARGET_SHORTFALL_DIAGNOSTIC_ONLY_NO_GATE_RELAXATION" in shortfall["baseline"]["diagnostics"]


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("daily_loss_fraction", "0.03", "DAILY_LOSS_SOFT_STOP"),
        ("seven_day_drawdown_fraction", "0.075", "SEVEN_DAY_DRAWDOWN_DIAGNOSTIC"),
        ("strategy_slice_drawdown_fraction", "0.1", "STRATEGY_SLICE_DRAWDOWN_KILL"),
        ("absolute_drawdown_fraction", "0.7", "ABSOLUTE_DISASTER_LINE_HARD_STOP"),
        ("ledger_difference_cents", 1, "LEDGER_DIFFERENCE_HARD_STOP"),
    ],
)
def test_loss_drawdown_and_ledger_boundaries_stop_new_candidate(field: str, value: str | int, reason_code: str) -> None:
    vector = deepcopy(_vector("K01-GA-P03-ROUTE-STABLE"))
    vector[field] = value
    result = evaluate_vector(vector, GRAPH, PARAMETERS)
    assert result["baseline"]["action"] == "NO_RECOMMENDATION"
    assert result["baseline"]["stake_cents"] == 0
    assert result["baseline"]["reason_code"] == reason_code


def test_under_minimum_stake_is_zero_and_never_rounded_up() -> None:
    result = evaluate_vector(_vector("K07-BELOW-PROVIDER-MINIMUM-NO-UPROUND"), GRAPH, PARAMETERS)
    assert result["baseline"]["stake_cents"] == 0
    assert result["baseline"]["reason_code"] == "STAKE_BELOW_PROVIDER_MINIMUM"


def test_deterministic_replay_hash_is_identical_without_waiting() -> None:
    hashes = {build_report(deepcopy(GRAPH), deepcopy(VECTORS), deepcopy(PARAMETERS))["report_sha256"] for _ in range(3)}
    assert hashes == {FIXTURE["expected_report_sha256"]}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda graph, registry: graph["clusters"].pop(),
        lambda graph, registry: registry.update({"correlation_graph_sha256": "f" * 64}),
        lambda graph, registry: registry["vectors"][0].update({"conservative_probability": 0}),
        lambda graph, registry: registry["vectors"][0].update({"upstream_route_action": "RECOMMEND_REAL_ORDER"}),
        lambda graph, registry: registry["vectors"].__setitem__(1, deepcopy(registry["vectors"][0])),
    ],
)
def test_malformed_or_drifted_graph_and_vectors_fail_closed(mutate) -> None:
    graph = deepcopy(GRAPH)
    registry = deepcopy(VECTORS)
    mutate(graph, registry)
    with pytest.raises(RiskEngineError):
        validate_correlation_graph(graph, PARAMETERS)
        validate_registry(registry, graph, PARAMETERS)


def test_core_source_has_no_network_process_soak_float_or_order_capability() -> None:
    source = (ROOT / "risk_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"})
    assert "sleep(" not in source
    assert "submit_order" not in source
    assert "confirm_order" not in source
    assert "retry_order" not in source
    assert "float(" not in source


def test_candidate_fails_closed_when_frozen_graph_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "correlation_graph.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    graph["risk_controls"]["daily_loss_soft_stop"] = "0.04"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P04-FROZEN-RISK-REPLAY" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_expected_report_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S11_P04.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_report_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P04-FROZEN-GRAPH-VECTORS-AND-REPORT-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p03_predecessor_is_changed(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S11-P03.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["status"] = "FAIL"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P04-PREDECESSOR-P03-SIGNED-AND-REPLAYABLE" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:constrained_kelly_and_correlated_portfolio"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S11-P04": write_risk_engine_phase_evidence' in source
    assert '"AC-S11-P04": verify_risk_engine_phase_evidence' in source
    with pytest.raises((RiskEngineAcceptanceError, FileNotFoundError)):
        from abd_acceptance.risk_engine import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
