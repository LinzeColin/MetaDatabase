from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.e2e_multi_environment import (
    CLAIM_BOUNDARY,
    E2E_EVIDENCE_PATH,
    E2E_TESTS_PATH,
    ENVIRONMENT_IDS,
    ENVIRONMENT_MATRIX_PATH,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    NEGATIVE_MUTATION_IDS,
    ORACLE_PATH,
    TEST_PATH,
    MultiEnvironmentE2EError,
    evaluate_e2e_scenario,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_e2e_evidence,
    validate_e2e_tests,
    validate_environment_matrix,
    validate_local_environment_surfaces,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))
E2E_TESTS = json.loads((ROOT / E2E_TESTS_PATH).read_text(encoding="utf-8"))
MATRIX = json.loads((ROOT / ENVIRONMENT_MATRIX_PATH).read_text(encoding="utf-8"))
E2E_EVIDENCE = json.loads((ROOT / E2E_EVIDENCE_PATH).read_text(encoding="utf-8"))


def test_candidate_preflight_replays_only_the_declared_local_multi_surface_contract() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["execution_policy"] == EXECUTION_POLICY
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["claim_boundary"] == CLAIM_BOUNDARY


def test_catalogs_name_exact_task_outputs_and_only_local_contract_surfaces() -> None:
    assert E2E_TESTS["artifact_id"] == "ART-S15-P03-01"
    assert MATRIX["artifact_id"] == "ART-S15-P03-02"
    assert E2E_EVIDENCE["artifact_id"] == "ART-S15-P03-03"
    assert FIXTURE["expected_environment_ids"] == list(ENVIRONMENT_IDS)
    assert E2E_TESTS["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert MATRIX["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert E2E_EVIDENCE["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


@pytest.mark.parametrize("scenario", E2E_TESTS["scenarios"], ids=lambda scenario: scenario["case_id"])
def test_frozen_golden_black_degraded_and_recovery_cases_replay_exactly(scenario: dict[str, object]) -> None:
    result = evaluate_e2e_scenario(ROOT, MATRIX, scenario)
    projection = result["decision_projection"]
    assert projection["status"] == scenario["expected"]["status"]
    assert projection["reason_codes"] == scenario["expected"]["reason_codes"]
    assert result["network_probe_performed"] is False
    assert result["actual_network_outage_exercised"] is False
    assert projection["external_network_accessed"] is False
    assert projection["ovh_account_or_host_accessed"] is False
    assert projection["cloudflare_account_dns_or_tunnel_accessed"] is False
    assert projection["desktop_or_mobile_browser_exercised"] is False
    assert projection["browser_component_installed_or_run"] is False
    assert projection["tab_or_provider_runtime_accessed"] is False
    assert projection["gmail_account_or_api_accessed"] is False
    assert projection["recommendation_generated"] is False
    assert projection["order_submission_enabled"] is False
    assert projection["external_state_changed"] is False
    assert projection["actual_return_claimed"] is False
    assert projection["real_time_soak_waited"] is False
    assert projection["incremental_cash_spent_aud"] == "0.00"


def test_all_declared_local_surfaces_are_hash_pinned_and_semantically_closed() -> None:
    checks = validate_local_environment_surfaces(ROOT, MATRIX)
    assert list(checks) == list(ENVIRONMENT_IDS)
    assert all(item["passed"] for item in checks.values()), checks


def test_every_required_journey_class_is_present_in_the_frozen_e2e_suite() -> None:
    assert E2E_TESTS["journey_classes"] == FIXTURE["expected_journey_classes"] == ["GOLDEN", "BLACK", "DEGRADED", "RECOVERY"]
    assert {scenario["journey_class"] for scenario in E2E_TESTS["scenarios"]} == set(FIXTURE["expected_journey_classes"])


def test_identical_frozen_input_replay_is_deterministic_without_device_or_network_execution() -> None:
    scenario = E2E_TESTS["scenarios"][0]
    assert evaluate_e2e_scenario(ROOT, MATRIX, scenario) == evaluate_e2e_scenario(ROOT, MATRIX, deepcopy(scenario))


@pytest.mark.parametrize("mutation_id", NEGATIVE_MUTATION_IDS)
def test_e2e_negative_mutations_fail_closed(mutation_id: str) -> None:
    if mutation_id == "MUT-S15-P03-UNKNOWN-E2E-FIELD":
        document = deepcopy(E2E_TESTS)
        document["unexpected"] = "rejected"
        validator = lambda value: validate_e2e_tests(value)
    elif mutation_id == "MUT-S15-P03-UNPINNED-ENVIRONMENT-HASH":
        document = deepcopy(MATRIX)
        document["environments"][0]["artifact_sha256"]["infra/config.schema.json"] = "0" * 64
        validator = lambda value: validate_environment_matrix(ROOT, value)
    elif mutation_id == "MUT-S15-P03-UNDECLARED-P02-REPLAY-CASE":
        document = deepcopy(E2E_TESTS)
        document["scenarios"][0]["source_replay_case_id"] = "S15-P02-UNKNOWN"
        validator = lambda value: validate_e2e_tests(value)
    elif mutation_id == "MUT-S15-P03-UNSTRUCTURED-EVIDENCE-LOG":
        document = deepcopy(E2E_EVIDENCE)
        document["structured_logs"][0]["structured_log_id"] = "UNSTRUCTURED"
        validator = lambda value: validate_e2e_evidence(value)
    else:
        raise AssertionError(mutation_id)
    with pytest.raises(MultiEnvironmentE2EError):
        validator(document)


def test_rollback_drill_is_local_only_and_keeps_signed_s15_p02_predecessor() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["actual_return_claimed"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_execution_boundary_never_converts_static_contract_replay_into_live_runtime_claims() -> None:
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "production_equivalent_config_schema_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }
    assert EXTERNAL_EFFECT_BOUNDARY["ovh_account_or_host_accessed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["cloudflare_account_dns_or_tunnel_accessed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["desktop_or_mobile_browser_exercised"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["browser_component_installed_or_run"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False


def test_evidence_explicitly_excludes_live_host_edge_device_and_network_outage_claims() -> None:
    assert CLAIM_BOUNDARY == {
        "local_multi_surface_contract_replayed": True,
        "actual_ovh_host_exercised": False,
        "actual_cloudflare_edge_exercised": False,
        "actual_desktop_or_mobile_browser_exercised": False,
        "actual_browser_component_installed": False,
        "actual_network_outage_exercised": False,
        "external_network_accessed": False,
    }
    assert E2E_EVIDENCE["claim_boundary"] == CLAIM_BOUNDARY


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
