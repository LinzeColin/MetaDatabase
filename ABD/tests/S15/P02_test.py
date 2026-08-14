from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.source_contract_integration import (
    CONTRACT_TESTS_PATH,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FIXTURES_MANIFEST_PATH,
    INTEGRATION_TESTS_PATH,
    NEGATIVE_MUTATION_IDS,
    ORACLE_PATH,
    SOURCE_CONTRACT_IDS,
    SOURCE_SPECS,
    SourceContractIntegrationError,
    TEST_PATH,
    evaluate_integration_case,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_source_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / FIXTURES_MANIFEST_PATH).read_text(encoding="utf-8"))
INTEGRATION_TESTS = json.loads((ROOT / INTEGRATION_TESTS_PATH).read_text(encoding="utf-8"))


def _bundle() -> dict[str, dict[str, object]]:
    return {
        str(spec["id"]): json.loads((ROOT / spec["fixture_path"]).read_text(encoding="utf-8"))
        for spec in SOURCE_SPECS
    }


def test_candidate_preflight_replays_only_the_declared_local_source_contract_surface() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["execution_policy"] == EXECUTION_POLICY
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["network_outage_claim_boundary"] == {
        "simulated_network_unavailable_tested": True,
        "real_network_outage_exercised": False,
        "external_network_accessed": False,
    }


def test_catalogs_name_exact_task_outputs_and_closed_synthetic_source_contracts() -> None:
    contract_tests = json.loads((ROOT / CONTRACT_TESTS_PATH).read_text(encoding="utf-8"))
    assert contract_tests["artifact_id"] == "ART-S15-P02-01"
    assert INTEGRATION_TESTS["artifact_id"] == "ART-S15-P02-02"
    assert MANIFEST["artifact_id"] == "ART-S15-P02-03"
    assert [row["id"] for row in contract_tests["source_contracts"]] == list(SOURCE_CONTRACT_IDS)
    assert FIXTURE["expected_source_contract_ids"] == list(SOURCE_CONTRACT_IDS)
    assert contract_tests["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert INTEGRATION_TESTS["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert MANIFEST["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


@pytest.mark.parametrize("case", INTEGRATION_TESTS["cases"], ids=lambda case: case["case_id"])
def test_frozen_source_contract_integration_cases_replay_exactly(case: dict[str, object]) -> None:
    result = evaluate_integration_case(MANIFEST, _bundle(), case)
    projection = result["decision_projection"]
    assert projection["status"] == case["expected"]["status"]
    assert projection["reason_codes"] == case["expected"]["reason_codes"]
    assert result["network_probe_performed"] is False
    assert result["real_network_outage_exercised"] is False
    assert projection["external_network_accessed"] is False
    assert projection["gmail_account_or_api_accessed"] is False
    assert projection["tab_or_provider_runtime_accessed"] is False
    assert projection["recommendation_generated"] is False
    assert projection["order_submission_enabled"] is False
    assert projection["actual_return_claimed"] is False
    assert projection["external_state_changed"] is False
    assert projection["real_time_soak_waited"] is False
    assert projection["incremental_cash_spent_aud"] == "0.00"


def test_simulated_network_unavailable_projection_is_identical_to_baseline_without_a_network_probe() -> None:
    outputs = {
        case["case_id"]: evaluate_integration_case(MANIFEST, _bundle(), case)
        for case in INTEGRATION_TESTS["cases"]
    }
    equivalence = FIXTURE["expected_outage_equivalence"]
    baseline = outputs[equivalence["baseline_case_id"]]
    unavailable = outputs[equivalence["outage_case_id"]]
    assert baseline["decision_projection"] == unavailable["decision_projection"]
    assert baseline["decision_projection_sha256"] == unavailable["decision_projection_sha256"]
    assert baseline["network_probe_performed"] is False
    assert unavailable["network_probe_performed"] is False
    assert unavailable["real_network_outage_exercised"] is False


@pytest.mark.parametrize("mutation_id", NEGATIVE_MUTATION_IDS)
def test_source_fixture_negative_mutations_fail_closed(mutation_id: str) -> None:
    if mutation_id == "MUT-S15-P02-UNKNOWN-FIELD":
        source_id = "SRC-S15-P02-PAGE"
        document = deepcopy(_bundle()[source_id])
        document["unexpected"] = "rejected"
    elif mutation_id == "MUT-S15-P02-FLOAT-ODDS":
        source_id = "SRC-S15-P02-ODDS"
        document = deepcopy(_bundle()[source_id])
        document["payload"]["quoted_odds"] = 1.8
    elif mutation_id == "MUT-S15-P02-NONCANONICAL-ODDS":
        source_id = "SRC-S15-P02-ODDS"
        document = deepcopy(_bundle()[source_id])
        document["payload"]["quoted_odds"] = "1.8"
    elif mutation_id == "MUT-S15-P02-NONSYNTHETIC-RESULT":
        source_id = "SRC-S15-P02-RESULT"
        document = deepcopy(_bundle()[source_id])
        document["synthetic_test_only"] = False
    else:
        raise AssertionError(mutation_id)
    with pytest.raises(SourceContractIntegrationError):
        validate_source_fixture(source_id, document)


def test_identical_frozen_input_replay_is_deterministic_and_never_an_order() -> None:
    case = INTEGRATION_TESTS["cases"][0]
    assert evaluate_integration_case(MANIFEST, _bundle(), case) == evaluate_integration_case(MANIFEST, _bundle(), deepcopy(case))


def test_rollback_drill_is_local_only_and_keeps_signed_s15_p01_predecessor() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["actual_return_claimed"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_execution_boundary_never_converts_local_contract_tests_into_live_or_return_claims() -> None:
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }
    assert EXTERNAL_EFFECT_BOUNDARY["external_network_accessed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["gmail_account_or_api_accessed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["tab_or_provider_runtime_accessed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["order_submitted_confirmed_or_retried"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False


def test_fixture_manifest_explicitly_excludes_real_network_outage_and_external_source_access() -> None:
    assert INTEGRATION_TESTS["outage_equivalence"] == {
        "baseline_case_id": "S15-P02-BASELINE-LOCAL",
        "outage_case_id": "S15-P02-SIMULATED-NETWORK-UNAVAILABLE",
        "real_network_outage_exercised": False,
        "deterministic_projection_must_match": True,
    }
    for document in _bundle().values():
        assert document["synthetic_test_only"] is True
        assert document["external_source_accessed"] is False


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
