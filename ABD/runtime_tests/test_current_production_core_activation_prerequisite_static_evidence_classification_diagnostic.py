from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_core_activation_prerequisite_static_evidence_classification_diagnostic as diagnostic
from current_production_core_activation_prerequisite_static_evidence_classification_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    PREREQUISITES,
    CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError,
    build_receipt,
    discover_static_evidence,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_core_activation_prerequisite_static_evidence_classification_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_core_activation_prerequisite_static_evidence_classification_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_core_activation_prerequisite_static_evidence_classification_diagnostic.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _states(value: str) -> dict[str, str]:
    return {spec.identifier: value for spec in PREREQUISITES}


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "contract_set_observed": True,
        "prerequisite_states": _states("LOCAL_REDACTED_RECEIPT_NOT_OBSERVED_REDACTED"),
        "core_activation_prerequisites_ready": False,
        "private_object_content_read": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
        "static_source_path_or_raw_content_emitted_or_persisted": False,
        "github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _write_json(path: Path, payload: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(mode)


def _write_contract_surface(root: Path) -> None:
    for spec in PREREQUISITES:
        _write_json(root / spec.contract_relative_path, {
            "schema_version": "1.0.0",
            "contract_id": "redacted",
            "product_version": "0.0.0.1",
            "status": "READ_ONLY",
            "expected": {},
            "source_boundary": {},
            "claim_boundary": "static only",
            "rollback": {},
        })


def _write_receipt(root: Path, spec: diagnostic.Prerequisite, ready: bool = True, extra: dict[str, object] | None = None) -> None:
    payload: dict[str, object] = {field: "REDACTED" for field in spec.receipt_fields}
    payload.update({
        "schema_version": "1.0.0",
        "receipt_type": spec.receipt_type,
        "status": spec.pass_status,
        "decision": "REDACTED_STATIC_EVIDENCE_ONLY",
        "observed_on": "2026-08-12",
        "checks": [],
        "failure_codes": [],
        "source_boundary": {},
        "claim_boundary": "static only",
        spec.ready_field: ready,
        spec.authorization_field: False,
    })
    if extra:
        payload.update(extra)
    _write_json(root / spec.receipt_relative_path, payload)


def test_contract_preserves_five_gate_static_only_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["prerequisite_ids"] == [spec.identifier for spec in PREREQUISITES]
    assert expected["github_api_requests"] == 0
    assert expected["provider_api_requests"] == 0
    assert boundary["fixed_contract_key_sets_read_in_memory_only"] is True
    assert boundary["private_object_content_read"] is False
    assert boundary["credential_config_or_runtime_secret_read_or_persisted"] is False


def test_all_valid_redacted_receipts_classify_ready_but_never_authorize_core(tmp_path: Path) -> None:
    _write_contract_surface(tmp_path)
    for spec in PREREQUISITES:
        _write_receipt(tmp_path, spec)

    facts = discover_static_evidence(tmp_path, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["contract_set_observed"] is True
    assert set(facts["prerequisite_states"].values()) == {"READY_EVIDENCE_OBSERVED_REDACTED"}
    assert result["status"] == PASS_STATUS
    assert result["core_activation_prerequisites_ready"] is True
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_actual_worktree_marks_only_local_receipts_as_not_observed() -> None:
    facts = discover_static_evidence(ROOT.parent, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["repository_root_state"] == "AVAILABLE_READ_ONLY"
    assert facts["contract_set_observed"] is True
    assert set(facts["prerequisite_states"].values()) == {"LOCAL_REDACTED_RECEIPT_NOT_OBSERVED_REDACTED"}
    assert result["status"] == PASS_STATUS
    assert result["core_activation_prerequisites_ready"] is False
    assert result["core_start_authorized"] is False


def test_valid_unready_receipt_is_classified_without_claiming_a_runtime_failure(tmp_path: Path) -> None:
    _write_contract_surface(tmp_path)
    for spec in PREREQUISITES:
        _write_receipt(tmp_path, spec, ready=spec.identifier != "SSH_TRANSPORT")

    facts = discover_static_evidence(tmp_path, observed_on="2026-08-12")

    assert facts["prerequisite_states"]["SSH_TRANSPORT"] == "NOT_READY_EVIDENCE_OBSERVED_REDACTED"
    assert facts["core_activation_prerequisites_ready"] is False


def test_unknown_receipt_field_is_rejected_and_not_emitted(tmp_path: Path) -> None:
    _write_contract_surface(tmp_path)
    for spec in PREREQUISITES:
        _write_receipt(tmp_path, spec)
    _write_receipt(tmp_path, PREREQUISITES[0], extra={"must_not_be_retained": "secret-looking-content"})

    facts = discover_static_evidence(tmp_path, observed_on="2026-08-12")
    receipt = build_receipt(_contract(), facts)
    serialized = json.dumps(receipt, sort_keys=True)

    assert facts["prerequisite_states"]["CONTROLLED_ENTRY"] == "REDACTED_RECEIPT_REJECTED_REDACTED"
    assert "secret-looking-content" not in serialized
    assert "must_not_be_retained" not in serialized


def test_unsafe_receipt_fails_closed(tmp_path: Path) -> None:
    _write_contract_surface(tmp_path)
    for spec in PREREQUISITES:
        _write_receipt(tmp_path, spec)
    unsafe = tmp_path / PREREQUISITES[0].receipt_relative_path
    unsafe.chmod(0o666)
    assert unsafe.stat().st_mode & stat.S_IWOTH

    facts = discover_static_evidence(tmp_path, observed_on="2026-08-12")

    assert facts["prerequisite_states"]["CONTROLLED_ENTRY"] == "REDACTED_RECEIPT_REJECTED_REDACTED"
    assert facts["core_activation_prerequisites_ready"] is False


def test_missing_contract_fails_closed_before_receipt_lookup(tmp_path: Path) -> None:
    _write_contract_surface(tmp_path)
    for spec in PREREQUISITES:
        _write_receipt(tmp_path, spec)
    (tmp_path / PREREQUISITES[0].contract_relative_path).unlink()

    facts = discover_static_evidence(tmp_path, observed_on="2026-08-12")

    assert facts["contract_set_observed"] is False
    assert facts["prerequisite_states"]["CONTROLLED_ENTRY"] == "CONTRACT_NOT_OBSERVED_REDACTED"
    assert facts["core_activation_prerequisites_ready"] is False


def test_unavailable_root_fails_closed() -> None:
    facts = discover_static_evidence(Path("/definitely-not-present"), observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["repository_root_state"] == "UNAVAILABLE_REDACTED"
    assert result["core_activation_prerequisites_ready"] is False
    assert result["core_start_authorized"] is False


def test_facts_reject_outbound_counts_and_inconsistent_readiness() -> None:
    with pytest.raises(CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(github_api_requests=1))

    with pytest.raises(CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError, match="core activation readiness"):
        validate_facts(_facts(
            prerequisite_states=_states("READY_EVIDENCE_OBSERVED_REDACTED"),
            core_activation_prerequisites_ready=False,
        ))


def test_contract_cannot_relax_static_only_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["ssh_connections_attempted"] = 1

    with pytest.raises(CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_network_or_command_execution_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--repo-root" in runner
    assert "current_production_core_activation_prerequisite_static_evidence_classification_diagnostic.py" in runner
    for forbidden in (
        "socket.",
        "urllib.request",
        "import requests",
        "requests.",
        "urlopen",
        "subprocess",
        "ssh ",
        "curl ",
        "wget ",
        "gh ",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
    ):
        assert forbidden not in runner
        assert forbidden not in module


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC"
