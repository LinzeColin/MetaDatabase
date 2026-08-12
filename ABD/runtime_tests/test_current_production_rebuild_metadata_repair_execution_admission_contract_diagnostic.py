from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic as diagnostic
from current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    REQUIRED_INDEPENDENT_EVIDENCE_IDS,
    CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError,
    build_receipt,
    discover_execution_admission,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic.py"
PROVENANCE_CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic_contract.json"
CORE_PREFLIGHT_CONTRACT_PATH = RUNTIME / "current_production_core_execution_preflight_contract.json"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _provenance_contract() -> dict[str, object]:
    return json.loads(PROVENANCE_CONTRACT_PATH.read_text(encoding="utf-8"))


def _core_preflight_contract() -> dict[str, object]:
    return json.loads(CORE_PREFLIGHT_CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "provenance_contract_state": "OBSERVED_STATIC",
        "core_preflight_contract_state": "OBSERVED_STATIC",
        "repair_execution_admission_state": "HOST_EVIDENCE_REQUIRED_REDACTED",
        "independent_evidence_requirement_state": "ALL_INDEPENDENT_EVIDENCE_REQUIRED_REDACTED",
        "independent_evidence_required": list(REQUIRED_INDEPENDENT_EVIDENCE_IDS),
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "current_host_metadata_read": False,
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
        provenance_contract_state="REJECTED_REDACTED",
        repair_execution_admission_state="STATIC_INPUT_REJECTED_REDACTED",
        independent_evidence_requirement_state="STATIC_INPUT_REJECTED_REDACTED",
        independent_evidence_required=[],
    )
    values.update(overrides)
    return values


def _root(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_contract_preserves_static_only_admission_boundary() -> None:
    contract = _contract()

    validate_contract(contract)

    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["independent_evidence_ids"] == list(REQUIRED_INDEPENDENT_EVIDENCE_IDS)
    assert boundary["current_host_metadata_read"] is False
    assert boundary["repair_deployment_or_core_start_attempted"] is False
    assert boundary["real_time_soak_waited"] is False


def test_two_static_contracts_require_all_independent_current_evidence(tmp_path: Path) -> None:
    provenance = tmp_path / "provenance.json"
    preflight = tmp_path / "preflight.json"
    _write_json(provenance, _provenance_contract())
    _write_json(preflight, _core_preflight_contract())

    facts = discover_execution_admission(_root(tmp_path), provenance, preflight, "2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)
    serialized = json.dumps(build_receipt(_contract(), facts), sort_keys=True)

    assert facts["repair_execution_admission_state"] == "HOST_EVIDENCE_REQUIRED_REDACTED"
    assert facts["independent_evidence_requirement_state"] == "ALL_INDEPENDENT_EVIDENCE_REQUIRED_REDACTED"
    assert facts["independent_evidence_required"] == list(REQUIRED_INDEPENDENT_EVIDENCE_IDS)
    assert result["status"] == PASS_STATUS
    assert result["repair_execution_authorized"] is False
    assert result["core_start_authorized"] is False
    assert "current_rebuild_file_kind" not in serialized
    assert "repair_contract_id" not in serialized


def test_unavailable_static_inputs_are_distinguished_and_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    preflight = tmp_path / "preflight.json"
    _write_json(preflight, _core_preflight_contract())

    facts = discover_execution_admission(_root(tmp_path), missing, preflight, "2026-08-12")

    assert facts["provenance_contract_state"] == "UNAVAILABLE_REDACTED"
    assert facts["core_preflight_contract_state"] == "OBSERVED_STATIC"
    assert facts["repair_execution_admission_state"] == "STATIC_INPUT_REJECTED_REDACTED"
    assert facts["independent_evidence_required"] == []
    assert evaluate_diagnostic(_contract(), facts)["status"] == PASS_STATUS


def test_rejected_provenance_and_core_preflight_contracts_are_distinguished(tmp_path: Path) -> None:
    bad_provenance = tmp_path / "bad-provenance.json"
    bad_preflight = tmp_path / "bad-preflight.json"
    _write_json(bad_provenance, {"unexpected": True})
    _write_json(bad_preflight, {"unexpected": True})

    facts = discover_execution_admission(_root(tmp_path), bad_provenance, bad_preflight, "2026-08-12")

    assert facts["provenance_contract_state"] == "REJECTED_REDACTED"
    assert facts["core_preflight_contract_state"] == "REJECTED_REDACTED"
    assert facts["repair_execution_admission_state"] == "STATIC_INPUT_REJECTED_REDACTED"


def test_unsafe_or_unavailable_repository_root_does_not_attempt_contracts(tmp_path: Path) -> None:
    root_file = tmp_path / "not-a-root"
    root_file.write_text("not a directory", encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    preflight = tmp_path / "preflight.json"
    _write_json(provenance, _provenance_contract())
    _write_json(preflight, _core_preflight_contract())

    facts = discover_execution_admission(root_file, provenance, preflight, "2026-08-12")

    assert facts["repository_root_state"] == "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
    assert facts["provenance_contract_state"] == "NOT_ATTEMPTED"
    assert facts["core_preflight_contract_state"] == "NOT_ATTEMPTED"


def test_facts_reject_authorization_or_outbound_operation_relaxation() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, match="admission boundary"):
        validate_facts(_facts(repair_execution_authorized=True))

    with pytest.raises(CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(provider_api_requests=1))

    with pytest.raises(CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, match="admission boundary"):
        validate_facts(_facts(current_host_metadata_read=True))


def test_facts_reject_incomplete_independent_evidence_declaration() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, match="independent evidence requirement"):
        validate_facts(_facts(independent_evidence_required=list(REQUIRED_INDEPENDENT_EVIDENCE_IDS[:-1])))

    with pytest.raises(CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, match="static input rejection"):
        validate_facts(_static_rejected_facts(independent_evidence_required=["CURRENT_HOST_METADATA_CURRENT"]))


def test_static_rejection_is_reported_without_authorization() -> None:
    facts = _static_rejected_facts()

    result = evaluate_diagnostic(_contract(), facts)
    receipt = build_receipt(_contract(), facts)

    assert result["status"] == PASS_STATUS
    assert "STATIC_INPUT_REJECTED" in result["decision"]
    assert result["repair_execution_authorized"] is False
    assert receipt["core_start_authorized"] is False
    assert "STATIC_ADMISSION_INPUT_ACCEPTED" in receipt["failure_codes"]


def test_contract_rejects_any_boundary_weakening() -> None:
    contract = _contract()
    contract["source_boundary"]["repair_deployment_or_core_start_attempted"] = True

    with pytest.raises(CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_is_fixed_to_the_two_nonsecret_contracts() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")

    assert "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic.py" in runner
    assert "current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic_contract.json" in runner
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


def test_failure_status_is_reserved_for_unreadable_or_invalid_diagnostic_inputs() -> None:
    assert PASS_STATUS != FAIL_STATUS
    assert diagnostic._failure_receipt(ValueError("invalid"), "not-a-date")["status"] == FAIL_STATUS
