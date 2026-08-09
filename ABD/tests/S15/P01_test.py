from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.software_correctness import (
    COVERAGE_SCOPE,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    NEGATIVE_MUTATION_IDS,
    ORACLE_PATH,
    PROPERTY_SPECS,
    REQUIRED_BRANCH_IDS,
    SCHEMA_TESTS_PATH,
    SoftwareCorrectnessAcceptanceError,
    TEST_PATH,
    UNIT_TESTS_PATH,
    calculate_branch_coverage,
    evaluate_property_suite,
    evaluate_quality_snapshot,
    perform_rollback_drill,
    validate_candidate_preflight,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))


def _results_by_case() -> dict[str, dict[str, object]]:
    return {row["case_id"]: evaluate_quality_snapshot(row["snapshot"]) for row in FIXTURE["snapshot_cases"]}


def test_candidate_preflight_replays_only_the_declared_correctness_surface() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["coverage_claim_boundary"] == COVERAGE_SCOPE
    assert result["execution_policy"] == EXECUTION_POLICY
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_catalogs_name_the_exact_task_outputs_without_a_repository_wide_claim() -> None:
    unit = json.loads((ROOT / UNIT_TESTS_PATH).read_text(encoding="utf-8"))
    properties = json.loads((ROOT / "property_tests.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / SCHEMA_TESTS_PATH).read_text(encoding="utf-8"))
    assert unit["artifact_id"] == "ART-S15-P01-01"
    assert properties["artifact_id"] == "ART-S15-P01-02"
    assert schema["artifact_id"] == "ART-S15-P01-03"
    assert unit["coverage_scope"] == COVERAGE_SCOPE
    assert unit["coverage_scope"]["repository_wide_coverage_claimed"] is False
    assert properties["properties"] == list(PROPERTY_SPECS)
    assert schema["negative_mutation_ids"] == list(NEGATIVE_MUTATION_IDS)


@pytest.mark.parametrize("row", FIXTURE["snapshot_cases"], ids=lambda row: row["case_id"])
def test_frozen_unit_and_boundary_cases_replay_exactly(row: dict[str, object]) -> None:
    actual = evaluate_quality_snapshot(row["snapshot"])
    assert actual == row["expected"]
    assert actual["recommendation_generated"] is False
    assert actual["order_submission_enabled"] is False
    assert actual["external_state_changed"] is False
    assert actual["real_time_soak_waited"] is False
    assert actual["incremental_cash_spent_aud"] == "0.00"


@pytest.mark.parametrize("spec", PROPERTY_SPECS, ids=lambda spec: spec["id"])
def test_frozen_funds_and_threshold_properties_all_pass(spec: dict[str, object]) -> None:
    properties = {item["id"]: item for item in evaluate_property_suite(_results_by_case())}
    assert properties[spec["id"]]["passed"] is True


@pytest.mark.parametrize("mutation_id", NEGATIVE_MUTATION_IDS)
def test_schema_negative_mutations_fail_closed(mutation_id: str) -> None:
    snapshot = deepcopy(FIXTURE["snapshot_cases"][0]["snapshot"])
    if mutation_id == "MUT-S15-P01-UNKNOWN-FIELD":
        snapshot["unexpected"] = "rejected"
    elif mutation_id == "MUT-S15-P01-FLOAT-NUMERIC":
        snapshot["score"] = 0.95
    elif mutation_id == "MUT-S15-P01-NONCANONICAL-DECIMAL":
        snapshot["score"] = "0.95"
    elif mutation_id == "MUT-S15-P01-NONSYNTHETIC-INPUT":
        snapshot["synthetic_test_only"] = False
    else:
        raise AssertionError(mutation_id)
    with pytest.raises(SoftwareCorrectnessAcceptanceError):
        evaluate_quality_snapshot(snapshot)


def test_declared_branch_inventory_is_fully_exercised_by_the_frozen_cases() -> None:
    coverage = calculate_branch_coverage(list(_results_by_case().values()))
    assert coverage["covered_branch_ids"] == list(REQUIRED_BRANCH_IDS)
    assert coverage["missing_branch_ids"] == []
    assert coverage["branch_coverage"] == FIXTURE["expected_branch_coverage"] == "1.0000"
    assert coverage["passes"] is True


def test_identical_input_replay_is_deterministic_and_never_an_order() -> None:
    snapshot = FIXTURE["snapshot_cases"][0]["snapshot"]
    assert evaluate_quality_snapshot(snapshot) == evaluate_quality_snapshot(deepcopy(snapshot))


def test_rollback_drill_is_local_only_and_keeps_predecessors() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_execution_boundary_never_converts_local_tests_into_a_return_or_production_claim() -> None:
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }
    assert EXTERNAL_EFFECT_BOUNDARY["recommendation_generated_or_enabled"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["order_submitted_confirmed_or_retried"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False


def test_oracle_has_no_network_process_sleep_or_order_capability() -> None:
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
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
    assert (ROOT / TEST_PATH).is_file()
