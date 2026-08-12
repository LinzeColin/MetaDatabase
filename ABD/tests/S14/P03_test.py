from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.component_governance import (
    ComponentGovernanceError,
    EXTERNAL_EFFECT_BOUNDARY,
    PRODUCTION_COMPONENT_FIELDS,
    build_evidence,
    evaluate_component_snapshot,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_component_governance,
    validate_component_fixture,
    validate_patch_sla,
    validate_sbom,
)
from abd_acceptance.security_analysis import verify_existing_phase_evidence as verify_security_analysis_phase_evidence


ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _fixture() -> dict:
    return _load("machine/tests/fixtures/S14_P03.json")


def _sbom() -> dict:
    return _load("sbom.json")


def test_frozen_taskpack_contract_is_exact() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["contract_id"] == "AC-S14-P03"
    assert result["requirement_id"] == "REQ-S14-P03"
    assert result["status"] == "PASS"
    assert result["decision"] == "COMPONENT_METADATA_COMPLETE_LOCAL_ONLY_P04_PROVENANCE_REQUIRED"
    assert result["next"] == "S14/P04_READY_NOT_STARTED"


def test_candidate_preflight_passes() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["summary"]["failed"] == 0
    assert result["analysis"]["production_component_count"] == 1
    assert result["analysis"]["development_component_count"] == 12


def test_sbom_validates() -> None:
    summary = validate_sbom(_sbom(), ROOT)
    assert summary == {
        "production_component_count": 1,
        "development_component_count": 12,
        "unadmitted_runtime_prerequisite_count": 3,
        "runtime_direct_dependency_count": 0,
    }


def test_component_governance_validates() -> None:
    governance = validate_component_governance(_load("component_governance.json"))
    assert governance["admission_rules"]["missing_source"] == "BLOCK_RELEASE"
    assert governance["admission_rules"]["missing_license"] == "BLOCK_RELEASE"


def test_patch_sla_validates() -> None:
    patch_sla = validate_patch_sla(_load("patch_sla.json"))
    assert [item["maximum_elapsed_hours"] for item in patch_sla["severity_slas"]] == ["24", "168", "720"]


def test_p02_predecessor_is_current() -> None:
    predecessor = verify_security_analysis_phase_evidence(ROOT)
    assert predecessor["status"] == "PASS"
    assert predecessor["next"] == "S14/P03_READY_NOT_STARTED"


def test_production_component_has_complete_metadata() -> None:
    component = _sbom()["production_components"][0]
    assert set(component) == set(PRODUCTION_COMPONENT_FIELDS)
    for field in ("source", "version", "version_pin", "license", "governance_owner"):
        assert component[field]
    assert component["version"] == component["version_pin"]


def test_development_components_are_not_production() -> None:
    components = _sbom()["development_components"]
    assert len(components) == 12
    assert all(component["production_component"] is False for component in components)
    assert all(component["release_admission"] == "DEVELOPMENT_ONLY_NOT_IN_PRODUCTION_COMPONENT_SCOPE" for component in components)


def test_unadmitted_runtime_prerequisites_are_blocked() -> None:
    prerequisites = _sbom()["declared_unadmitted_runtime_prerequisites"]
    assert len(prerequisites) == 3
    assert all(item["release_admission"] == "BLOCKED" for item in prerequisites)
    assert all(item["scope"] == "PLANNED_RUNTIME_PREREQUISITE_NOT_PRODUCTION_COMPONENT" for item in prerequisites)


def test_execution_boundary_remains_local() -> None:
    sbom = _sbom()
    assert sbom["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert sbom["not_production_evidence"] is True


@pytest.mark.parametrize("case", _fixture()["snapshot_cases"], ids=lambda case: case["case_id"])
def test_frozen_snapshot_cases(case: dict) -> None:
    actual = evaluate_component_snapshot(case["snapshot"])
    assert actual["status"] == case["expected"]["status"]
    assert actual["reason_codes"] == case["expected"]["reason_codes"]
    assert actual["recommendation_generated"] is False
    assert actual["order_submission_enabled"] is False


def test_missing_source_is_rejected() -> None:
    candidate = deepcopy(_sbom())
    del candidate["production_components"][0]["source"]
    with pytest.raises(ComponentGovernanceError):
        validate_sbom(candidate, ROOT)


def test_missing_version_is_rejected() -> None:
    candidate = deepcopy(_sbom())
    del candidate["production_components"][0]["version"]
    with pytest.raises(ComponentGovernanceError):
        validate_sbom(candidate, ROOT)


def test_missing_license_is_rejected() -> None:
    candidate = deepcopy(_sbom())
    del candidate["production_components"][0]["license"]
    with pytest.raises(ComponentGovernanceError):
        validate_sbom(candidate, ROOT)


def test_missing_governance_owner_is_rejected() -> None:
    candidate = deepcopy(_sbom())
    del candidate["production_components"][0]["governance_owner"]
    with pytest.raises(ComponentGovernanceError):
        validate_sbom(candidate, ROOT)


def test_version_pin_mismatch_is_rejected() -> None:
    candidate = deepcopy(_sbom())
    candidate["production_components"][0]["version_pin"] = "0.0.0.2"
    with pytest.raises(ComponentGovernanceError):
        validate_sbom(candidate, ROOT)


def test_unadmitted_runtime_component_cannot_be_admitted() -> None:
    candidate = deepcopy(_sbom())
    candidate["declared_unadmitted_runtime_prerequisites"][0]["release_admission"] = "ADMITTED"
    with pytest.raises(ComponentGovernanceError):
        validate_sbom(candidate, ROOT)


def test_point_0001_coverage_boundary_is_rejected() -> None:
    snapshot = deepcopy(_fixture()["snapshot_cases"][0]["snapshot"])
    snapshot["coverage_score"] = "0.9999"
    result = evaluate_component_snapshot(snapshot)
    assert result["reason_codes"] == ["COMPONENT_METADATA_COVERAGE_NOT_EXACT"]


def test_unfavorable_foreign_odds_input_is_rejected() -> None:
    snapshot = deepcopy(_fixture()["snapshot_cases"][0]["snapshot"])
    snapshot["foreign_odds_input_present"] = True
    result = evaluate_component_snapshot(snapshot)
    assert result["reason_codes"] == ["FOREIGN_ODDS_INPUT_REJECTED"]


def test_malformed_snapshot_is_rejected() -> None:
    snapshot = deepcopy(_fixture()["snapshot_cases"][0]["snapshot"])
    snapshot["coverage_score"] = 1
    with pytest.raises(ComponentGovernanceError):
        evaluate_component_snapshot(snapshot)


def test_snapshot_replay_is_deterministic() -> None:
    snapshot = _fixture()["snapshot_cases"][0]["snapshot"]
    first = evaluate_component_snapshot(snapshot)
    second = evaluate_component_snapshot(snapshot)
    assert first == second
    assert first["output_sha256"] == second["output_sha256"]


def test_evidence_build_is_deterministic_before_reports() -> None:
    first_evidence, first_rollback = build_evidence(ROOT, require_test_reports=False)
    second_evidence, second_rollback = build_evidence(ROOT, require_test_reports=False)
    assert first_evidence == second_evidence
    assert first_rollback == second_rollback
    assert first_evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_rollback_drill_is_local_and_preserves_no_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False
