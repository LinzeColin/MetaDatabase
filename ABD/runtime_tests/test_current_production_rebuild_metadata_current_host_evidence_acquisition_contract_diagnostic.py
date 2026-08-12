from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic as diagnostic
from current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic import (
    FAIL_STATUS,
    FUTURE_RECEIPT_SCHEMA_FIELDS,
    HOST_METADATA_INPUT_SURFACE,
    PASS_STATUS,
    REJECTION_STATES,
    CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError,
    build_receipt,
    discover_current_host_evidence_acquisition_contract,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic.py"
ADMISSION_CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic_contract.json"
CORE_PREFLIGHT_CONTRACT_PATH = RUNTIME / "current_production_core_execution_preflight_contract.json"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _admission_contract() -> dict[str, object]:
    return json.loads(ADMISSION_CONTRACT_PATH.read_text(encoding="utf-8"))


def _core_preflight_contract() -> dict[str, object]:
    return json.loads(CORE_PREFLIGHT_CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_ACQUISITION_CONTRACT_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "admission_contract_state": "OBSERVED_STATIC",
        "core_preflight_contract_state": "OBSERVED_STATIC",
        "current_host_evidence_acquisition_state": "CURRENT_HOST_METADATA_REQUIRED_REDACTED",
        "future_current_host_metadata_input_surface": list(HOST_METADATA_INPUT_SURFACE),
        "future_rejection_states": list(REJECTION_STATES),
        "future_receipt_schema_fields": list(FUTURE_RECEIPT_SCHEMA_FIELDS),
        "current_host_metadata_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _static_rejected_facts(**overrides: object) -> dict[str, object]:
    values = _facts(
        admission_contract_state="REJECTED_REDACTED",
        current_host_evidence_acquisition_state="STATIC_INPUT_REJECTED_REDACTED",
    )
    values.update(overrides)
    return values


def _root(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_contract_declares_current_host_schema_without_reading_host() -> None:
    contract = _contract()

    validate_contract(contract)

    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["future_current_host_metadata_input_surface"] == list(HOST_METADATA_INPUT_SURFACE)
    assert expected["future_receipt_schema_fields"] == list(FUTURE_RECEIPT_SCHEMA_FIELDS)
    assert expected["evidence_freshness_policy"]["historical_or_static_evidence_accepted"] is False
    assert boundary["current_host_metadata_read"] is False
    assert boundary["ssh_connection_attempted"] is False
    assert boundary["repair_deployment_or_core_start_attempted"] is False


def test_valid_static_inputs_require_future_current_host_metadata(tmp_path: Path) -> None:
    admission = tmp_path / "admission.json"
    preflight = tmp_path / "preflight.json"
    _write_json(admission, _admission_contract())
    _write_json(preflight, _core_preflight_contract())

    facts = discover_current_host_evidence_acquisition_contract(_root(tmp_path), admission, preflight, "2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)
    serialized = json.dumps(build_receipt(_contract(), facts), sort_keys=True)

    assert facts["current_host_evidence_acquisition_state"] == "CURRENT_HOST_METADATA_REQUIRED_REDACTED"
    assert result["status"] == PASS_STATUS
    assert result["repair_execution_authorized"] is False
    assert result["core_start_authorized"] is False
    assert "config_file_kind" not in serialized
    assert "current_rebuild_file_kind" not in serialized


def test_missing_static_input_is_distinguished_and_remains_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    preflight = tmp_path / "preflight.json"
    _write_json(preflight, _core_preflight_contract())

    facts = discover_current_host_evidence_acquisition_contract(_root(tmp_path), missing, preflight, "2026-08-12")

    assert facts["admission_contract_state"] == "UNAVAILABLE_REDACTED"
    assert facts["core_preflight_contract_state"] == "OBSERVED_STATIC"
    assert facts["current_host_evidence_acquisition_state"] == "STATIC_INPUT_REJECTED_REDACTED"
    assert evaluate_diagnostic(_contract(), facts)["status"] == PASS_STATUS


def test_rejected_admission_and_core_preflight_contracts_are_distinguished(tmp_path: Path) -> None:
    bad_admission = tmp_path / "bad-admission.json"
    bad_preflight = tmp_path / "bad-preflight.json"
    _write_json(bad_admission, {"unexpected": True})
    _write_json(bad_preflight, {"unexpected": True})

    facts = discover_current_host_evidence_acquisition_contract(_root(tmp_path), bad_admission, bad_preflight, "2026-08-12")

    assert facts["admission_contract_state"] == "REJECTED_REDACTED"
    assert facts["core_preflight_contract_state"] == "REJECTED_REDACTED"
    assert facts["current_host_evidence_acquisition_state"] == "STATIC_INPUT_REJECTED_REDACTED"


def test_unsafe_repository_root_does_not_attempt_static_contract_reads(tmp_path: Path) -> None:
    root_file = tmp_path / "not-a-root"
    root_file.write_text("not a directory", encoding="utf-8")
    admission = tmp_path / "admission.json"
    preflight = tmp_path / "preflight.json"
    _write_json(admission, _admission_contract())
    _write_json(preflight, _core_preflight_contract())

    facts = discover_current_host_evidence_acquisition_contract(root_file, admission, preflight, "2026-08-12")

    assert facts["repository_root_state"] == "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
    assert facts["admission_contract_state"] == "NOT_ATTEMPTED"
    assert facts["core_preflight_contract_state"] == "NOT_ATTEMPTED"


def test_facts_reject_read_authorization_and_outbound_relaxation() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError, match="acquisition boundary"):
        validate_facts(_facts(current_host_metadata_read=True))

    with pytest.raises(CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError, match="acquisition boundary"):
        validate_facts(_facts(repair_execution_authorized=True))

    with pytest.raises(CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(ssh_connections_attempted=1))


def test_facts_reject_weakened_future_schema_or_rejection_states() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError, match="future evidence declaration"):
        validate_facts(_facts(future_rejection_states=list(REJECTION_STATES[:-1])))

    with pytest.raises(CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError, match="future evidence declaration"):
        validate_facts(_facts(future_receipt_schema_fields=list(FUTURE_RECEIPT_SCHEMA_FIELDS[:-1])))


def test_static_rejection_does_not_become_host_or_repair_authorization() -> None:
    facts = _static_rejected_facts()

    result = evaluate_diagnostic(_contract(), facts)
    receipt = build_receipt(_contract(), facts)

    assert result["status"] == PASS_STATUS
    assert "STATIC_INPUT_REJECTED" in result["decision"]
    assert result["repair_execution_authorized"] is False
    assert receipt["core_start_authorized"] is False
    assert "STATIC_ACQUISITION_INPUT_ACCEPTED" in receipt["failure_codes"]


def test_contract_rejects_boundary_weakening() -> None:
    contract = _contract()
    contract["source_boundary"]["current_host_metadata_read"] = True

    with pytest.raises(CurrentProductionRebuildMetadataCurrentHostEvidenceAcquisitionContractDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_is_fixed_to_the_two_nonsecret_contracts() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")

    assert "current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic.py" in runner
    assert "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic_contract.json" in runner
    assert "current_production_core_execution_preflight_contract.json" in runner
    assert "--observed-on" in runner
    assert "private_db_client.py" not in runner


def test_module_has_no_network_or_process_capability() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    for prohibited in (
        "import subprocess",
        "import socket",
        "import urllib",
        "import requests",
        "import http",
        "os.system(",
        "subprocess.",
        "socket.",
        "private_db_client",
    ):
        assert prohibited not in source


def test_failure_status_is_reserved_for_invalid_diagnostic_inputs() -> None:
    assert PASS_STATUS != FAIL_STATUS
    assert diagnostic._failure_receipt(ValueError("invalid"), "not-a-date")["status"] == FAIL_STATUS
