from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.model_challenge import (
    CORE_PATH,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXTURE_PATH,
    ORACLE_PATH,
    ModelChallengeAcceptanceError,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from abd_acceptance.model_challenge_engine import (
    BASELINE_REPORT_PATH,
    CHALLENGER_CATALOG,
    CHALLENGER_REPORT_PATH,
    CLAIM_BOUNDARY,
    MODEL_REGISTRY_PATH,
    ModelChallengeInputError,
    artifact_sha256,
    build_artifacts,
    load_fixture,
    strict_json_load,
    validate_artifacts,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))
REGISTRY = strict_json_load(ROOT / MODEL_REGISTRY_PATH)
BASELINE = strict_json_load(ROOT / BASELINE_REPORT_PATH)
CHALLENGER = strict_json_load(ROOT / CHALLENGER_REPORT_PATH)


def test_candidate_preflight_replays_the_exact_local_champion_challenger_contract() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["execution_policy"] == EXECUTION_POLICY
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_artifacts_replay_byte_for_value_from_the_frozen_fixture() -> None:
    fixture = load_fixture(ROOT / FIXTURE_PATH)
    expected = build_artifacts(ROOT, fixture)
    assert validate_artifacts(ROOT, fixture) == expected
    assert expected[MODEL_REGISTRY_PATH.as_posix()] == REGISTRY
    assert expected[BASELINE_REPORT_PATH.as_posix()] == BASELINE
    assert expected[CHALLENGER_REPORT_PATH.as_posix()] == CHALLENGER


def test_market_consensus_is_the_only_active_champion_before_s16_p02() -> None:
    champion = REGISTRY["champion"]
    assert champion["model_id"] == "MARKET_CONSENSUS_CHAMPION"
    assert champion["active_weight"] == "1.00"
    assert REGISTRY["selection_policy"] == {
        "comparison_mode": "FROZEN_TIME_WINDOW_PRE_EVALUATION",
        "significant_increment_required": True,
        "weight_when_increment_not_significant": "0.00",
        "market_prior_weight_min": "0.50",
        "candidate_residual_weight_cap": "0.35",
        "activation_requires_contract": "AC-S16-P02",
        "safe_action_before_s16_p02": "KEEP_CHAMPION_MARKET_ONLY",
    }


@pytest.mark.parametrize("model_id", [row["model_id"] for row in CHALLENGER_CATALOG])
def test_every_challenger_without_significant_increment_has_exact_zero_weight(model_id: str) -> None:
    row = next(item for item in REGISTRY["challengers"] if item["model_id"] == model_id)
    report_row = next(item for item in CHALLENGER["challengers"] if item["model_id"] == model_id)
    assert row["significant_increment"] is False
    assert row["active_weight"] == "0.00"
    assert row["activation_status"] == "KEEP_CHAMPION_MARKET_ONLY_PENDING_S16_P02"
    assert report_row["significant_increment"] is False
    assert report_row["assigned_weight"] == "0.00"


@pytest.mark.parametrize("window", FIXTURE["frozen_windows"], ids=lambda row: row["window_id"])
def test_every_time_window_is_explicitly_frozen_synthetic_and_nonempirical(window: dict[str, object]) -> None:
    baseline_window = next(item for item in BASELINE["frozen_windows"] if item["window_id"] == window["window_id"])
    assert baseline_window == window
    assert baseline_window["classification"] == "FROZEN_SYNTHETIC_PRE_EVALUATION_NOT_EMPIRICAL"
    assert baseline_window["observed_outcome_count"] == 0


@pytest.mark.parametrize(
    ("artifact", "artifact_id"),
    [
        (REGISTRY, "ART-S16-P01-01"),
        (BASELINE, "ART-S16-P01-02"),
        (CHALLENGER, "ART-S16-P01-03"),
    ],
)
def test_artifacts_have_exact_task_pack_artifact_identity(artifact: dict[str, object], artifact_id: str) -> None:
    assert artifact["artifact_id"] == artifact_id
    assert artifact["contract_id"] == "AC-S16-P01"
    assert artifact["stage_id"] == "S16"
    assert artifact["phase_id"] == "P01"


def test_artifact_hash_links_are_closed_and_deterministic() -> None:
    assert BASELINE["registry_sha256"] == artifact_sha256(REGISTRY)
    assert CHALLENGER["registry_sha256"] == artifact_sha256(REGISTRY)
    assert CHALLENGER["baseline_report_sha256"] == artifact_sha256(BASELINE)
    assert build_artifacts(ROOT, load_fixture(ROOT / FIXTURE_PATH)) == build_artifacts(ROOT, load_fixture(ROOT / FIXTURE_PATH))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda fixture: fixture["challenger_assessments"][0]["windows"][0].update({"assigned_weight": "0.0001"}),
        lambda fixture: fixture["challenger_assessments"][0]["windows"][0].update({"significant_increment": True}),
        lambda fixture: fixture["frozen_windows"][0].update({"classification": "LIVE_EMPIRICAL_WINDOW"}),
        lambda fixture: fixture["frozen_windows"][0].update({"observed_outcome_count": 1}),
        lambda fixture: fixture["challenger_assessments"][0]["aggregate"].update({"assigned_weight": "0.01"}),
        lambda fixture: fixture["predecessors"].pop("AC-S11-P04"),
    ],
    ids=[
        "NONZERO_WINDOW_WEIGHT",
        "UNVERIFIED_SIGNIFICANT_INCREMENT",
        "LIVE_WINDOW",
        "EMPIRICAL_OUTCOME_CLAIM",
        "NONZERO_AGGREGATE_WEIGHT",
        "MISSING_SIGNED_PREDECESSOR",
    ],
)
def test_invalid_increment_or_window_mutations_fail_closed(mutation) -> None:
    candidate = deepcopy(FIXTURE)
    mutation(candidate)
    with pytest.raises(ModelChallengeInputError):
        validate_fixture(candidate)


def test_parameter_hash_drift_fails_before_any_artifact_is_rebuilt() -> None:
    candidate = deepcopy(FIXTURE)
    candidate["parameters_sha256"] = "0" * 64
    with pytest.raises(ModelChallengeInputError):
        build_artifacts(ROOT, validate_fixture(candidate))


@pytest.mark.parametrize("contract_id", sorted(FIXTURE["predecessors"]))
def test_signed_stage_predecessor_metadata_is_preserved_in_the_registry(contract_id: str) -> None:
    expected = FIXTURE["predecessors"][contract_id]
    row = next(item for item in REGISTRY["signed_predecessors"] if item["contract_id"] == contract_id)
    assert row["evidence_path"] == expected["evidence_path"]
    assert row["evidence_sha256"] == expected["evidence_sha256"]
    assert row["status"] == "PASS"
    assert row["next"] == expected["next"]


def test_reports_do_not_convert_a_synthetic_comparison_into_empirical_or_production_claims() -> None:
    for artifact in (REGISTRY, BASELINE, CHALLENGER):
        assert artifact["claim_boundary"] == CLAIM_BOUNDARY
        assert artifact["claim_boundary"]["empirical_model_increment_verified"] is False
        assert artifact["claim_boundary"]["recommendation_generated_or_enabled"] is False
        assert artifact["claim_boundary"]["order_submission_enabled"] is False
        assert artifact["claim_boundary"]["production_deployed_or_activated"] is False
        assert artifact["claim_boundary"]["real_time_soak_waited"] is False
    assert CHALLENGER["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert CHALLENGER["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_rollback_is_local_only_and_keeps_the_market_champion_surface() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["feature_flag_id"] == FEATURE_FLAG_ID
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_execution_policy_blocks_full_regression_soak_and_external_runtime() -> None:
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "phase_test_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "predecessor_verification_mode": "PINNED_SIGNED_RECEIPTS_AND_LOCAL_SOURCE_HASHES",
        "incremental_cash_spent_aud": "0.00",
    }


def test_core_and_oracle_have_no_network_process_sleep_or_order_capability() -> None:
    imports: set[str] = set()
    source = ""
    for path in (CORE_PATH, ORACLE_PATH):
        content = (ROOT / path).read_text(encoding="utf-8")
        source += content
        for node in ast.walk(ast.parse(content)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"})
    assert "sleep(" not in source
    assert "submit_order" not in source
    assert "retry_order" not in source
    assert "http://" not in source
    assert "https://" not in source


def test_candidate_preflight_error_type_is_reserved_for_failed_signed_surface() -> None:
    assert issubclass(ModelChallengeAcceptanceError, ValueError)
