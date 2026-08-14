from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.threat_model import (
    ABUSE_CASES_PATH,
    BOUNDARY_IDS,
    CONTRACT_ID,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    ORACLE_PATH,
    THREAT_IDS,
    THREAT_MODEL_PATH,
    TRUST_BOUNDARIES_PATH,
    ThreatModelAcceptanceError,
    evaluate_threat_snapshot,
    perform_rollback_drill,
    validate_abuse_cases,
    validate_candidate_preflight,
    validate_threat_model,
    validate_trust_boundaries,
    verify_existing_phase_evidence,
    write_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
THREAT_MODEL = json.loads((ROOT / THREAT_MODEL_PATH).read_text(encoding="utf-8"))
TRUST_BOUNDARIES = json.loads((ROOT / TRUST_BOUNDARIES_PATH).read_text(encoding="utf-8"))
ABUSE_CASES = json.loads((ROOT / ABUSE_CASES_PATH).read_text(encoding="utf-8"))
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == CONTRACT_ID
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_frozen_catalogs_bind_the_exact_task_pack_identifiers() -> None:
    model = validate_threat_model(THREAT_MODEL)
    boundaries = validate_trust_boundaries(TRUST_BOUNDARIES, model["threats"])
    cases = validate_abuse_cases(ABUSE_CASES, model["threats"], boundaries["boundaries"])
    assert [row["threat_id"] for row in model["threats"]] == list(THREAT_IDS)
    assert [row["boundary_id"] for row in boundaries["boundaries"]] == list(BOUNDARY_IDS)
    assert [row["case_id"] for row in cases["cases"]] == FIXTURE["expected_case_ids"]


@pytest.mark.parametrize("threat_id", THREAT_IDS)
def test_each_high_threat_has_four_distinct_control_groups(threat_id: str) -> None:
    model = validate_threat_model(THREAT_MODEL)
    threat = next(row for row in model["threats"] if row["threat_id"] == threat_id)
    grouped = [threat[group + "_control_ids"] for group in ("prevention", "detection", "response", "recovery")]
    assert all(len(group) >= 1 for group in grouped)
    controls = [item for group in grouped for item in group]
    assert len(controls) == len(set(controls))
    assert threat["risk_level"] == "HIGH"
    assert threat["local_contract_only"] is True


@pytest.mark.parametrize("index", range(7))
def test_boundary_and_abuse_case_bind_each_threat_control(index: int) -> None:
    model = validate_threat_model(THREAT_MODEL)
    boundaries = validate_trust_boundaries(TRUST_BOUNDARIES, model["threats"])
    cases = validate_abuse_cases(ABUSE_CASES, model["threats"], boundaries["boundaries"])
    threat = model["threats"][index]
    boundary = boundaries["boundaries"][index]
    case = cases["cases"][index]
    assert boundary["threat_id"] == threat["threat_id"] == case["threat_id"]
    assert case["boundary_id"] == boundary["boundary_id"]
    for group in ("prevention", "detection", "response", "recovery"):
        assert case[group + "_control_id"] in threat[group + "_control_ids"]
        assert case[group + "_control_id"] in boundary["control_ids"]


@pytest.mark.parametrize("row", FIXTURE["snapshot_cases"], ids=lambda row: row["case_id"])
def test_frozen_single_pass_snapshots_replay_exactly(row: dict[str, object]) -> None:
    result = evaluate_threat_snapshot(row["snapshot"])
    assert result["status"] == row["expected"]["status"]
    assert result["reason_codes"] == row["expected"]["reason_codes"]
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"coverage_score": 1.0}),
        lambda value: value.update({"findings_open": True}),
        lambda value: value.update({"unknown": False}),
    ],
)
def test_malformed_security_snapshots_fail_closed(mutate) -> None:
    snapshot = deepcopy(FIXTURE["snapshot_cases"][0]["snapshot"])
    mutate(snapshot)
    with pytest.raises(ThreatModelAcceptanceError):
        evaluate_threat_snapshot(snapshot)


def test_catalog_tampering_fails_closed() -> None:
    model = deepcopy(THREAT_MODEL)
    model["threats"][0]["prevention_control_ids"] = []
    with pytest.raises(ThreatModelAcceptanceError):
        validate_threat_model(model)


def test_boundary_tampering_fails_closed() -> None:
    model = validate_threat_model(THREAT_MODEL)
    boundaries = deepcopy(TRUST_BOUNDARIES)
    boundaries["boundaries"][0]["control_ids"] = boundaries["boundaries"][0]["control_ids"][:-1]
    with pytest.raises(ThreatModelAcceptanceError):
        validate_trust_boundaries(boundaries, model["threats"])


def test_abuse_outcome_tampering_fails_closed() -> None:
    model = validate_threat_model(THREAT_MODEL)
    boundaries = validate_trust_boundaries(TRUST_BOUNDARIES, model["threats"])
    cases = deepcopy(ABUSE_CASES)
    cases["cases"][0]["expected_outcome"] = "ALLOW_EXTERNAL_ACTION"
    with pytest.raises(ThreatModelAcceptanceError):
        validate_abuse_cases(cases, model["threats"], boundaries["boundaries"])


def test_external_effect_and_execution_boundaries_are_exactly_local_only() -> None:
    assert THREAT_MODEL["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }


def test_oracle_has_no_network_process_soak_or_order_capability() -> None:
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


def test_rollback_drill_is_local_and_preserves_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["recommendation_generated"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert rollback["incremental_cash_spent_aud"] == "0.00"


def test_writer_rejects_a_noncanonical_evidence_directory_before_mutation() -> None:
    with pytest.raises(ThreatModelAcceptanceError):
        write_phase_evidence(ROOT, ROOT / "machine/not-evidence")


def test_acceptance_cli_is_wired_and_unsigned_evidence_cannot_verify() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S14-P01": write_threat_model_phase_evidence' in source
    assert '"AC-S14-P01": verify_threat_model_phase_evidence' in source
    with pytest.raises(ThreatModelAcceptanceError):
        verify_existing_phase_evidence(ROOT / "missing")
