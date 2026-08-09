"""Targeted frozen tests for the S16/P03 red-team and cross-model gate."""

from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path

import pytest

from abd_acceptance.model_redteam import (
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from abd_acceptance.model_redteam_engine import (
    ATTACK_CATEGORIES,
    CLAIM_BOUNDARY,
    CROSS_MODEL_REVIEW_PATH,
    MODEL_REDTEAM_PATH,
    ModelRedteamInputError,
    build_artifacts,
    canonical_json_bytes,
    load_fixture,
    strict_json_load,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
RAW_FIXTURE = strict_json_load(ROOT / "machine/tests/fixtures/S16_P03.json")
STATE = load_fixture(ROOT)
ARTIFACTS = build_artifacts(ROOT, RAW_FIXTURE)
REDTEAM = ARTIFACTS[MODEL_REDTEAM_PATH.as_posix()]
REVIEW = ARTIFACTS[CROSS_MODEL_REVIEW_PATH.as_posix()]


def _mutated_case(index: int, payload: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    raw = copy.deepcopy(RAW_FIXTURE)
    raw["attack_cases"][index]["attack_input"] = payload
    artifacts = build_artifacts(ROOT, raw)
    return artifacts[MODEL_REDTEAM_PATH.as_posix()]["attack_results"][index], artifacts[CROSS_MODEL_REVIEW_PATH.as_posix()]


def test_fixture_identity_and_scope_are_frozen() -> None:
    fixture = STATE["fixture"]
    assert fixture["contract_id"] == "AC-S16-P03"
    assert fixture["requirement_id"] == "REQ-S16-P03"
    assert fixture["expected_next"] == "S16/P04_READY_NOT_STARTED"
    assert fixture["claim_boundary"] == CLAIM_BOUNDARY


@pytest.mark.parametrize("index,category", list(enumerate(ATTACK_CATEGORIES)))
def test_each_frozen_attack_is_blocked(index: int, category: str) -> None:
    result = REDTEAM["attack_results"][index]
    assert result["category"] == category
    assert result["expected_outcome"] == result["observed_outcome"] == "BLOCKED"
    assert result["attack_blocked"] is True
    assert result["safe_action"] == "NO_RECOMMENDATION_NO_ORDER"


@pytest.mark.parametrize("index,category", list(enumerate(ATTACK_CATEGORIES)))
def test_each_frozen_attack_uses_a_nonempty_reason(index: int, category: str) -> None:
    result = REDTEAM["attack_results"][index]
    assert result["category"] == category
    assert result["reason_code"] == RAW_FIXTURE["attack_cases"][index]["expected_reason"]


@pytest.mark.parametrize(
    "index,payload",
    [
        (0, {"feature_available_at": "2025-11-30T23:59:58+10:00", "decision_at": "2025-11-30T23:59:58+10:00"}),
        (1, {"observed_odds": "2.3500", "median_odds": "2.0000", "mad": "0.1000"}),
        (2, {"expected_identity": "S16P03-EVENT-ALPHA", "observed_identity": "S16P03-EVENT-ALPHA", "identity_confidence": "0.9950"}),
        (3, {"expected_source_sha256": "d99bd2049eaaeae6264bba71570010b0bc615e08270062e99a56edd4b26b732f", "observed_source_sha256": "d99bd2049eaaeae6264bba71570010b0bc615e08270062e99a56edd4b26b732f"}),
        (4, {"proposed_cluster_exposure": "0.0500"}),
        (5, {"claimed_monthly_return": "0.30", "requested_gate_relaxation": False}),
    ],
)
def test_attack_boundary_that_no_longer_detects_causes_a_blocking_phase_result(index: int, payload: dict[str, object]) -> None:
    result, review = _mutated_case(index, payload)
    assert result["observed_outcome"] == "BYPASSED"
    assert result["attack_blocked"] is False
    assert review["review_consensus"]["all_required_attacks_blocked"] is False
    assert review["review_consensus"]["decision"] == "S16_P03_BLOCKING_DEFECT_DETECTED"


def test_all_six_attack_categories_are_present_once() -> None:
    assert REDTEAM["required_attack_categories"] == list(ATTACK_CATEGORIES)
    assert [row["category"] for row in REDTEAM["attack_results"]] == list(ATTACK_CATEGORIES)
    assert REDTEAM["summary"] == {
        "attack_count": 6,
        "blocked_count": 6,
        "bypass_count": 0,
        "all_attack_paths_blocked": True,
        "any_bypass_is_blocking_defect": True,
    }


def test_cross_model_review_keeps_champion_and_candidate_unactivated() -> None:
    assert REVIEW["reviewed_models"] == [
        {
            "model_id": "MARKET_CONSENSUS_CHAMPION",
            "role": "CHAMPION",
            "p01_active_weight": "1.00",
            "p02_evaluation_candidate": False,
            "review_verdict": "BLOCK_PROMOTION_PENDING_S16_P04",
        },
        {
            "model_id": "GENERIC_RESIDUAL_CHALLENGER",
            "role": "CHALLENGER",
            "p01_active_weight": "0.00",
            "p02_evaluation_candidate": True,
            "review_verdict": "BLOCK_PROMOTION_PENDING_S16_P04",
        },
    ]
    assert REVIEW["review_consensus"]["model_promotion_allowed"] is False
    assert REVIEW["review_consensus"]["activation_status"] == "NOT_ACTIVATED_PENDING_S16_P04"


def test_cross_model_review_binds_the_redteam_artifact_hash() -> None:
    assert REVIEW["redteam_artifact_sha256"] == hashlib.sha256(canonical_json_bytes(REDTEAM)).hexdigest()


def test_replay_is_byte_stable_for_identical_inputs() -> None:
    first = build_artifacts(ROOT, copy.deepcopy(RAW_FIXTURE))
    second = build_artifacts(ROOT, copy.deepcopy(RAW_FIXTURE))
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("contract_id", "AC-S16-P04"),
        lambda value: value["p02_evidence"].__setitem__("evidence_sha256", "f" * 64),
        lambda value: value.__setitem__("claim_boundary", {**value["claim_boundary"], "model_promotion_allowed": True}),
        lambda value: value["attack_cases"].reverse(),
    ],
)
def test_fixture_identity_and_predecessor_mutations_fail_closed(mutation: object) -> None:
    raw = copy.deepcopy(RAW_FIXTURE)
    mutation(raw)
    with pytest.raises(ModelRedteamInputError):
        validate_fixture(ROOT, raw)


@pytest.mark.parametrize("artifact_path,artifact_id", [(MODEL_REDTEAM_PATH, "ART-S16-P03-01"), (CROSS_MODEL_REVIEW_PATH, "ART-S16-P03-02")])
def test_artifact_identities_are_exact(artifact_path: Path, artifact_id: str) -> None:
    assert ARTIFACTS[artifact_path.as_posix()]["artifact_id"] == artifact_id


@pytest.mark.parametrize("field", ["external_network_accessed", "real_market_or_odds_observed", "order_submission_enabled", "production_deployed_or_activated"])
def test_claim_boundary_prohibits_external_effects(field: str) -> None:
    assert REDTEAM["claim_boundary"][field] is False
    assert REVIEW["claim_boundary"][field] is False
    assert EXTERNAL_EFFECT_BOUNDARY[field] is False


def test_oracle_static_boundary_has_no_network_or_process_imports() -> None:
    imports: set[str] = set()
    for relative in ("model_redteam.py", "abd_acceptance/model_redteam_engine.py", "abd_acceptance/model_redteam.py"):
        for node in ast.walk(ast.parse((ROOT / relative).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"})


def test_candidate_preflight_passes_before_report_signing() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["decision"] == RAW_FIXTURE["expected_decision"]
    assert result["next"] == RAW_FIXTURE["expected_next"]


def test_contract_evaluation_remains_phase_scoped_before_report_signing() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["summary"]["failed"] == 0
    assert result["execution_policy"]["phase_test_only"] is True
    assert result["execution_policy"]["full_regression_or_real_time_soak_allowed"] is False


def test_rollback_is_local_and_preserves_no_promotion() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["model_weight_changed"] is False
    assert rollback["model_promotion_allowed"] is False


def test_generator_wrapper_is_a_local_engine_entrypoint() -> None:
    source = (ROOT / "model_redteam.py").read_text(encoding="utf-8")
    assert "abd_acceptance.model_redteam_engine" in source
    assert "main" in source
