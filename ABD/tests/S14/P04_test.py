from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.artifact_provenance import (
    ArtifactProvenanceError,
    EXTERNAL_EFFECT_BOUNDARY,
    build_evidence,
    compute_local_attestation,
    evaluate_provenance_snapshot,
    perform_rollback_drill,
    validate_artifact_signing,
    validate_candidate_preflight,
    validate_provenance,
    validate_provenance_fixture,
    validate_security_rollback,
)
from abd_acceptance.component_governance import verify_existing_phase_evidence as verify_component_governance_phase_evidence


ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _fixture() -> dict:
    return _load("machine/tests/fixtures/S14_P04.json")


def _provenance() -> dict:
    return _load("provenance.json")


def _pass_snapshot() -> dict:
    return deepcopy(_fixture()["snapshot_cases"][0]["snapshot"])


def test_frozen_taskpack_contract_is_exact() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["contract_id"] == "AC-S14-P04"
    assert result["requirement_id"] == "REQ-S14-P04"
    assert result["status"] == "PASS"
    assert result["decision"] == "LOCAL_PRE_RELEASE_PROVENANCE_COMPLETE_STAGE_REVIEW_REQUIRED"
    assert result["next"] == "S14/STAGE_REVIEW_READY_NOT_STARTED"


def test_candidate_preflight_passes() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["summary"]["failed"] == 0
    assert result["analysis"]["source_input_count"] == 16


def test_p03_predecessor_is_current() -> None:
    result = verify_component_governance_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S14/P04_READY_NOT_STARTED"


def test_provenance_validates() -> None:
    summary = validate_provenance(_provenance(), ROOT)
    assert summary["source_input_count"] == 16
    assert summary["dependency_lock_count"] == 3
    assert summary["attestation_is_keyed_signature"] is False


def test_signing_policy_validates() -> None:
    summary = validate_artifact_signing((ROOT / "artifact_signing.md").read_text(encoding="utf-8"))
    assert summary["actual_release_signature_created"] is False


def test_rollback_policy_validates() -> None:
    summary = validate_security_rollback((ROOT / "security_rollback.md").read_text(encoding="utf-8"))
    assert summary["external_mutation_performed"] is False


def test_fixture_validates() -> None:
    assert validate_provenance_fixture(_fixture())["snapshot_case_count"] == 13


def test_source_inputs_are_current() -> None:
    provenance = _provenance()
    assert provenance["source_inputs"]["abd_acceptance/artifact_provenance.py"]
    assert provenance["source_inputs"]["tests/S14/P04_test.py"]


def test_dependency_trace_retains_zero_runtime_dependencies() -> None:
    provenance = _provenance()
    assert provenance["dependency_provenance"]["runtime_direct_dependencies"] == []
    assert provenance["dependency_provenance"]["runtime_status"] == "NO_DECLARED_RUNTIME_DIRECT_DEPENDENCIES"


def test_build_environment_is_local_only() -> None:
    environment = _provenance()["build_environment"]
    assert environment["command"] == "uv run --frozen --python 3.12"
    assert environment["production_host_or_image_verified"] is False


def test_local_attestation_recomputes_exactly() -> None:
    provenance = _provenance()
    assert provenance["local_attestation"]["value"] == compute_local_attestation(provenance)


def test_companion_documents_are_hash_bound() -> None:
    hashes = _provenance()["artifact_hashes"]
    assert set(hashes) == {"artifact_signing.md", "security_rollback.md"}
    assert all(len(value) == 64 for value in hashes.values())


def test_release_boundary_blocks_real_release() -> None:
    boundary = _provenance()["release_boundary"]
    assert boundary["actual_release_signed"] is False
    assert boundary["deployment_or_activation_performed"] is False
    assert boundary["approval_evidence_present"] is False


def test_external_boundary_is_unchanged() -> None:
    assert _provenance()["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


@pytest.mark.parametrize("case", _fixture()["snapshot_cases"], ids=lambda case: case["case_id"])
def test_frozen_snapshot_cases(case: dict) -> None:
    actual = evaluate_provenance_snapshot(case["snapshot"])
    assert actual["status"] == case["expected"]["status"]
    assert actual["reason_codes"] == case["expected"]["reason_codes"]
    assert actual["release_enabled"] is False
    assert actual["order_submission_enabled"] is False


def test_source_hash_mismatch_is_rejected() -> None:
    candidate = deepcopy(_provenance())
    candidate["source_inputs"]["VERSION"] = "0" * 64
    with pytest.raises(ArtifactProvenanceError):
        validate_provenance(candidate, ROOT)


def test_dependency_hash_mismatch_is_rejected() -> None:
    candidate = deepcopy(_provenance())
    candidate["dependency_provenance"]["locked_files"]["uv.lock"] = "0" * 64
    with pytest.raises(ArtifactProvenanceError):
        validate_provenance(candidate, ROOT)


def test_build_environment_mismatch_is_rejected() -> None:
    candidate = deepcopy(_provenance())
    candidate["build_environment"]["production_host_or_image_verified"] = True
    with pytest.raises(ArtifactProvenanceError):
        validate_provenance(candidate, ROOT)


def test_attestation_mismatch_is_rejected() -> None:
    candidate = deepcopy(_provenance())
    candidate["local_attestation"]["value"] = "0" * 64
    with pytest.raises(ArtifactProvenanceError):
        validate_provenance(candidate, ROOT)


def test_real_release_claim_is_rejected() -> None:
    candidate = deepcopy(_provenance())
    candidate["release_boundary"]["actual_release_signed"] = True
    with pytest.raises(ArtifactProvenanceError):
        validate_provenance(candidate, ROOT)


def test_source_base_revision_is_predecessor_not_release_claim() -> None:
    source_base = _provenance()["source_base"]
    assert source_base["revision_role"] == "S14_P03_SIGNED_PREDECESSOR_BASE_NOT_A_P04_RELEASE_COMMIT"
    assert source_base["current_p04_commit_status"] == "NOT_CREATED_AT_LOCAL_ATTESTATION_TIME"


def test_missing_signing_boundary_is_rejected() -> None:
    with pytest.raises(ArtifactProvenanceError):
        validate_artifact_signing("# ABD Artifact Signing Boundary\n")


def test_missing_rollback_boundary_is_rejected() -> None:
    with pytest.raises(ArtifactProvenanceError):
        validate_security_rollback("# ABD Security Rollback Boundary\n")


def test_point_0001_coverage_low_is_rejected() -> None:
    snapshot = _pass_snapshot()
    snapshot["coverage_score"] = "0.9999"
    assert evaluate_provenance_snapshot(snapshot)["reason_codes"] == ["PROVENANCE_COVERAGE_NOT_EXACT"]


def test_point_0001_coverage_high_is_rejected() -> None:
    snapshot = _pass_snapshot()
    snapshot["coverage_score"] = "1.0001"
    assert evaluate_provenance_snapshot(snapshot)["reason_codes"] == ["PROVENANCE_COVERAGE_NOT_EXACT"]


def test_unfavorable_foreign_odds_input_is_rejected() -> None:
    snapshot = _pass_snapshot()
    snapshot["foreign_odds_input_present"] = True
    assert evaluate_provenance_snapshot(snapshot)["reason_codes"] == ["FOREIGN_ODDS_INPUT_REJECTED"]


def test_malformed_snapshot_is_rejected() -> None:
    snapshot = _pass_snapshot()
    snapshot["coverage_score"] = 1
    with pytest.raises(ArtifactProvenanceError):
        evaluate_provenance_snapshot(snapshot)


def test_snapshot_replay_is_deterministic() -> None:
    first = evaluate_provenance_snapshot(_pass_snapshot())
    second = evaluate_provenance_snapshot(_pass_snapshot())
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
