from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.platform_router import (
    PlatformRouterAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from platform_router import (
    PlatformRouterError,
    artifact_sha256,
    build_provider_score,
    build_report,
    evaluate_vector,
    route_once,
    validate_provider,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S11_P03.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
SCORE = json.loads((ROOT / "provider_score.json").read_text(encoding="utf-8"))
ROUTING = json.loads((ROOT / "routing_fixtures.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _vector(vector_id: str) -> dict:
    return next(row for row in ROUTING["vectors"] if row["vector_id"] == vector_id)


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S11-P03"
    assert result["next"] == "S11/P04_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 25
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_score_policy_and_routing_fixtures_are_exact_frozen_replays() -> None:
    rebuilt = build_provider_score(PARAMETERS)
    report = build_report(SCORE, ROUTING, PARAMETERS)
    assert rebuilt == SCORE
    assert artifact_sha256(rebuilt) == FIXTURE["expected_provider_score_sha256"]
    assert artifact_sha256(ROUTING) == FIXTURE["expected_routing_fixtures_sha256"]
    assert report["report_sha256"] == FIXTURE["expected_report_sha256"]
    assert ROUTING["expected_report_sha256"] == report["report_sha256"]


@pytest.mark.parametrize(
    ("vector_id", "baseline_action", "final_action", "reason_code"),
    [
        ("R01-UNIQUE-STABLE-SYNTHETIC-PLATFORM", "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES", "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES", "ALL_PLATFORM_GATES_AND_UNIQUE_ROUTE_STABLE"),
        ("R02-TOP-SCORE-TIE-FAILS-CLOSED", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "TOP_PLATFORM_SCORE_TIED"),
        ("R03-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP", "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES", "NO_RECOMMENDATION", "ADVERSE_PLATFORM_ROUTING_STABILITY_FLIP"),
        ("R04-MINIMUM-ODDS-BOUNDARY-ADVERSE-FLIP", "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES", "NO_RECOMMENDATION", "ADVERSE_PLATFORM_ROUTING_STABILITY_FLIP"),
        ("R05-SOURCE-CONTRACT-FAILS-CLOSED", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "NO_PLATFORM_PASSES_ALL_HARD_GATES"),
        ("R06-SETTLEMENT-RULES-FAIL-CLOSED", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "NO_PLATFORM_PASSES_ALL_HARD_GATES"),
        ("R07-ACTION-CHANNEL-FAILS-CLOSED", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "NO_PLATFORM_PASSES_ALL_HARD_GATES"),
        ("R08-MINIMUM-STAKE-EXCEEDS-ROUTING-STAKE", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "NO_PLATFORM_PASSES_ALL_HARD_GATES"),
        ("R09-UPSTREAM-P02-CANDIDATE-REQUIRED", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "NO_PLATFORM_PASSES_ALL_HARD_GATES"),
        ("R10-NONPOSITIVE-EXECUTABLE-SCORE", "NO_RECOMMENDATION", "NO_RECOMMENDATION", "NO_PLATFORM_PASSES_ALL_HARD_GATES"),
        ("R11-RETURN-POINT-0001-ADVERSE-FLIP", "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES", "NO_RECOMMENDATION", "ADVERSE_PLATFORM_ROUTING_STABILITY_FLIP"),
        ("R12-LIVE-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP", "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES", "NO_RECOMMENDATION", "ADVERSE_PLATFORM_ROUTING_STABILITY_FLIP"),
    ],
)
def test_frozen_unique_route_boundary_and_negative_vectors(
    vector_id: str, baseline_action: str, final_action: str, reason_code: str
) -> None:
    result = evaluate_vector(_vector(vector_id), SCORE, PARAMETERS)
    assert result["baseline"]["action"] == baseline_action
    assert result["action"] == final_action
    assert result["reason_code"] == reason_code
    assert result["all_expected_matches"] is True


def test_only_one_stable_synthetic_provider_is_routed_and_it_is_not_a_recommendation() -> None:
    report = build_report(SCORE, ROUTING, PARAMETERS)
    stable = report["results"][0]
    assert stable["baseline"]["selected_provider_id"] == "SYNTHETIC_PROVIDER_ALPHA"
    assert stable["action"] == "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES"
    assert report["summary"]["routed_candidate_pending_constrained_kelly_and_risk_count"] == 1
    assert report["summary"]["no_recommendation_count"] == 11
    assert report["external_effect_boundary"]["recommendation_generated_or_enabled"] is False
    assert report["external_effect_boundary"]["order_submission_enabled"] is False


@pytest.mark.parametrize(
    ("vector_id", "reason_code"),
    [
        ("R05-SOURCE-CONTRACT-FAILS-CLOSED", "SOURCE_CONTRACT_NOT_PASSED"),
        ("R06-SETTLEMENT-RULES-FAIL-CLOSED", "SETTLEMENT_RULES_UNCLEAR"),
        ("R07-ACTION-CHANNEL-FAILS-CLOSED", "ACTION_CHANNEL_UNAVAILABLE"),
        ("R08-MINIMUM-STAKE-EXCEEDS-ROUTING-STAKE", "MINIMUM_STAKE_EXCEEDS_ROUTING_STAKE"),
        ("R09-UPSTREAM-P02-CANDIDATE-REQUIRED", "UPSTREAM_P02_CANDIDATE_GATE_NOT_PASSED"),
        ("R10-NONPOSITIVE-EXECUTABLE-SCORE", "NON_POSITIVE_EXECUTABLE_PLATFORM_SCORE"),
    ],
)
def test_every_platform_hard_gate_fails_closed_with_a_specific_provider_reason(vector_id: str, reason_code: str) -> None:
    routed = route_once(_vector(vector_id)["providers"], SCORE, PARAMETERS)
    assert routed["action"] == "NO_RECOMMENDATION"
    assert routed["providers"][0]["reason_code"] == reason_code


@pytest.mark.parametrize(
    ("vector_id", "expected_flips"),
    [
        ("R03-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP", ["stale_time_plus", "all_adverse"]),
        ("R04-MINIMUM-ODDS-BOUNDARY-ADVERSE-FLIP", ["odds_adverse", "all_adverse"]),
        ("R11-RETURN-POINT-0001-ADVERSE-FLIP", ["return_minus", "stale_penalty_plus", "settlement_penalty_plus", "minimum_stake_penalty_plus", "action_friction_plus", "all_adverse"]),
        ("R12-LIVE-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP", ["stale_time_plus", "all_adverse"]),
    ],
)
def test_one_in_ten_thousand_time_penalty_and_odds_adversity_forces_no_recommendation(
    vector_id: str, expected_flips: list[str]
) -> None:
    result = evaluate_vector(_vector(vector_id), SCORE, PARAMETERS)
    assert result["adverse_flip_dimensions"] == expected_flips
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["reason_code"] == "ADVERSE_PLATFORM_ROUTING_STABILITY_FLIP"


def test_all_five_frozen_time_bands_are_bound_to_quote_usable_limits() -> None:
    report = build_report(SCORE, ROUTING, PARAMETERS)
    limits = {
        provider["quote_usable_limit_seconds"]
        for result in report["results"]
        for provider in result["baseline"]["providers"]
    }
    assert limits == {2100, 420, 90, 30, 12}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda registry: registry.update({"provider_score_sha256": "f" * 64}),
        lambda registry: registry["vectors"].pop(),
        lambda registry: registry["vectors"][0]["providers"][0].update({"provider_id": "REAL_PROVIDER"}),
        lambda registry: registry["vectors"][0]["providers"][0].update({"observed_odds": 2.0}),
    ],
)
def test_malformed_ambiguous_or_non_fixed_point_routing_inputs_fail_closed(mutate) -> None:
    registry = deepcopy(ROUTING)
    mutate(registry)
    with pytest.raises(PlatformRouterError):
        validate_registry(registry, SCORE, PARAMETERS)


def test_fixed_point_provider_rejects_unaligned_stake_and_unknown_p02_binding() -> None:
    provider = deepcopy(_vector("R01-UNIQUE-STABLE-SYNTHETIC-PLATFORM")["providers"][0])
    provider["routing_stake_cents"] = 301
    routed = route_once([provider], SCORE, PARAMETERS)
    assert routed["providers"][0]["reason_code"] == "ROUTING_STAKE_NOT_ALIGNED_TO_INCREMENT"
    provider = deepcopy(_vector("R01-UNIQUE-STABLE-SYNTHETIC-PLATFORM")["providers"][0])
    provider["p02_vector_id"] = "UNKNOWN"
    with pytest.raises(PlatformRouterError):
        validate_provider(provider)


def test_deterministic_replay_hash_is_identical_without_waiting() -> None:
    hashes = {build_report(SCORE, ROUTING, PARAMETERS)["report_sha256"] for _ in range(3)}
    assert hashes == {FIXTURE["expected_report_sha256"]}


def test_core_source_has_no_network_process_soak_float_or_order_capability() -> None:
    source = (ROOT / "platform_router.py").read_text(encoding="utf-8")
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


def test_candidate_fails_closed_when_score_policy_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "provider_score.json"
    score = json.loads(path.read_text(encoding="utf-8"))
    score["hard_gates"]["unique_highest_score_required"] = False
    path.write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P03-SCORE-FIXTURES-AND-REPORT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_fixture_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S11_P03.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_report_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P03-FROZEN-SCORE-FIXTURES-AND-REPORT-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p02_receipt_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S11-P02.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["next"] = "S11/P99_READY"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P03-PREDECESSOR-P02-SIGNED-AND-REPLAYABLE" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:dynamic_platform_routing"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S11-P03": write_platform_router_phase_evidence' in source
    assert '"AC-S11-P03": verify_platform_router_phase_evidence' in source
    with pytest.raises((PlatformRouterAcceptanceError, FileNotFoundError)):
        from abd_acceptance.platform_router import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
