from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.traceability_proxy import (
    BOUNDARY_SPEC,
    CRITICAL_PHASE_IDS,
    EVIDENCE_PATH,
    EXECUTION_POLICY,
    EXPECTED_ARTIFACTS,
    EXPECTED_TASK_IDS,
    EXPECTED_TEST_IDS,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    GATE_IDS,
    NEGATIVE_MUTATION_IDS,
    ORACLE_PATH,
    SOFTWARE_GATE_PATH,
    TEST_PATH,
    TraceabilityGateError,
    evaluate_traceability_graph,
    perform_rollback_drill,
    validate_boundary_documents,
    validate_candidate_preflight,
    validate_fixture,
    validate_signed_p03_receipt,
    validate_software_gate,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))
GATE = json.loads((ROOT / SOFTWARE_GATE_PATH).read_text(encoding="utf-8"))
REQUIREMENTS = json.loads((ROOT / "machine/facts/requirements.json").read_text(encoding="utf-8"))
CONTRACTS = json.loads((ROOT / "machine/facts/acceptance_contracts.json").read_text(encoding="utf-8"))
GRAPH = json.loads((ROOT / "machine/facts/task_graph.json").read_text(encoding="utf-8"))
TRACEABILITY = json.loads((ROOT / "machine/facts/traceability_matrix.json").read_text(encoding="utf-8"))
EVIDENCE_INDEX = [json.loads(line) for line in (ROOT / "machine/evidence/evidence_index.jsonl").read_text(encoding="utf-8").splitlines() if line]
P03_E2E_TESTS = json.loads((ROOT / "e2e_tests.json").read_text(encoding="utf-8"))
P03_E2E_EVIDENCE = json.loads((ROOT / "e2e_evidence.json").read_text(encoding="utf-8"))


def test_candidate_preflight_replays_the_declared_s15_traceability_gate_only() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["execution_policy"] == EXECUTION_POLICY
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_gate_and_fixture_name_exact_p04_outputs_and_critical_scope() -> None:
    assert GATE["artifact_id"] == "ART-S15-P04-02"
    assert GATE["critical_chain"][-1]["contract_id"] == "AC-S15-P04"
    assert FIXTURE["expected_critical_phase_ids"] == list(CRITICAL_PHASE_IDS)
    assert FIXTURE["expected_gate_ids"] == list(GATE_IDS)
    assert FIXTURE["expected_negative_mutation_ids"] == list(NEGATIVE_MUTATION_IDS)
    assert EXPECTED_ARTIFACTS == {
        "ART-S15-P04-01": Path("traceability_validator.py"),
        "ART-S15-P04-02": Path("software_gate.json"),
    }


@pytest.mark.parametrize("phase_id", CRITICAL_PHASE_IDS)
def test_each_critical_phase_has_a_complete_non_orphan_chain(phase_id: str) -> None:
    result = evaluate_traceability_graph(REQUIREMENTS, CONTRACTS, GRAPH, TRACEABILITY, EVIDENCE_INDEX, GATE)
    assert result["status"] == "PASS", result
    check = next(item for item in result["checks"] if item["id"] == "S15P04-CHAIN-%s-COMPLETE" % phase_id)
    assert check["passed"] is True
    assert result["summary"]["orphan_count"] == 0
    assert result["summary"]["cycle_count"] == 0
    assert result["summary"]["unpassed_critical_acceptance_count"] == 0


def test_p04_task_and_test_links_are_exactly_the_frozen_contract_links() -> None:
    trace = next(row for row in TRACEABILITY if row["requirement_id"] == "REQ-S15-P04")
    assert trace["task_ids"] == list(EXPECTED_TASK_IDS)
    assert trace["test_ids"] == list(EXPECTED_TEST_IDS)
    assert trace["artifact_ids"] == list(EXPECTED_ARTIFACTS)
    assert trace["evidence_id"] == "EVD-S15-P04"
    assert (ROOT / ORACLE_PATH).is_file()
    assert (ROOT / SOFTWARE_GATE_PATH).is_file()
    assert (ROOT / TEST_PATH).is_file()


def test_one_in_ten_thousand_favourable_and_adverse_paths_remain_opposite_and_local() -> None:
    outcome = validate_boundary_documents(GATE, P03_E2E_TESTS, P03_E2E_EVIDENCE)
    assert outcome == {
        "delta": "0.0001",
        "favourable_case_id": BOUNDARY_SPEC["favourable_case_id"],
        "adverse_case_id": BOUNDARY_SPEC["adverse_case_id"],
        "adverse_must_fail_closed": True,
    }


def test_identical_frozen_inputs_replay_deterministically() -> None:
    first = evaluate_traceability_graph(REQUIREMENTS, CONTRACTS, GRAPH, TRACEABILITY, EVIDENCE_INDEX, GATE)
    second = evaluate_traceability_graph(deepcopy(REQUIREMENTS), deepcopy(CONTRACTS), deepcopy(GRAPH), deepcopy(TRACEABILITY), deepcopy(EVIDENCE_INDEX), deepcopy(GATE))
    assert first == second


@pytest.mark.parametrize("mutation_id", NEGATIVE_MUTATION_IDS)
def test_traceability_negative_mutations_fail_closed(mutation_id: str) -> None:
    if mutation_id == "MUT-S15-P04-UNKNOWN-GATE-FIELD":
        gate = deepcopy(GATE)
        gate["unexpected"] = "rejected"
        with pytest.raises(TraceabilityGateError):
            validate_software_gate(gate)
    elif mutation_id == "MUT-S15-P04-ORPHAN-S15-TASK":
        graph = deepcopy(GRAPH)
        graph["tasks"].append(
            {
                "id": "T-S15-P04-ORPHAN",
                "stage_id": "S15",
                "phase_id": "P04",
                "depends_on": [],
                "requirement_ids": ["REQ-S15-P04"],
                "acceptance_criteria_ids": ["AC-S15-P04"],
            }
        )
        result = evaluate_traceability_graph(REQUIREMENTS, CONTRACTS, graph, TRACEABILITY, EVIDENCE_INDEX, GATE)
        assert result["status"] == "FAIL"
        assert result["summary"]["orphan_count"] > 0
    elif mutation_id == "MUT-S15-P04-CYCLIC-TASK-GRAPH":
        graph = deepcopy(GRAPH)
        task = next(row for row in graph["tasks"] if row["id"] == "T-S15-P04-01")
        task["depends_on"] = [*task["depends_on"], "T-S15-P04-03"]
        result = evaluate_traceability_graph(REQUIREMENTS, CONTRACTS, graph, TRACEABILITY, EVIDENCE_INDEX, GATE)
        assert result["status"] == "FAIL"
        assert result["summary"]["cycle_count"] > 0
    elif mutation_id == "MUT-S15-P04-UNPASSED-CRITICAL-PREDECESSOR":
        index = deepcopy(EVIDENCE_INDEX)
        row = next(item for item in index if item["id"] == "INDEX-AC-S15-P03")
        row["status"] = "PLANNED"
        result = evaluate_traceability_graph(REQUIREMENTS, CONTRACTS, GRAPH, TRACEABILITY, index, GATE)
        assert result["status"] == "FAIL"
        assert result["summary"]["unpassed_critical_acceptance_count"] == 1
    elif mutation_id == "MUT-S15-P04-BOUNDARY-CASE-MISMATCH":
        e2e_tests = deepcopy(P03_E2E_TESTS)
        row = next(item for item in e2e_tests["scenarios"] if item["case_id"] == BOUNDARY_SPEC["adverse_case_id"])
        row["expected"]["status"] = BOUNDARY_SPEC["favourable_status"]
        with pytest.raises(TraceabilityGateError):
            validate_boundary_documents(GATE, e2e_tests, P03_E2E_EVIDENCE)
    else:
        raise AssertionError(mutation_id)


def test_fixture_is_closed_and_has_the_required_targeted_test_floor() -> None:
    assert validate_fixture(FIXTURE) == FIXTURE
    assert FIXTURE["minimum_targeted_pytest_cases"] == 18


def test_rollback_drill_keeps_signed_p03_and_changes_no_external_or_database_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["database_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["actual_return_claimed"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_execution_policy_cannot_be_interpreted_as_live_host_or_edge_access() -> None:
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
    assert EXTERNAL_EFFECT_BOUNDARY["database_connection_opened"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False


def test_oracle_has_no_network_process_wait_or_order_capability() -> None:
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


def test_signed_p03_receipt_is_pinned_and_remains_local_evidence_only() -> None:
    receipt = validate_signed_p03_receipt(ROOT)
    assert receipt["contract_id"] == "AC-S15-P03"
    assert receipt["status"] == "PASS"
    assert receipt["next"] == "S15/P04_READY_NOT_STARTED"
    assert receipt["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert receipt["external_effect_boundary"]["production_deployed_or_activated"] is False
