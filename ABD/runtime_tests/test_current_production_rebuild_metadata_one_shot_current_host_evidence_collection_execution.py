from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution as execution
import current_production_ssh_local_route_policy_diagnostic as local_route
from current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError,
    build_receipt,
    discover_current_host_evidence_collection_execution,
    evaluate_execution,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution.sh"
MODULE_PATH = RUNTIME / "current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution.py"
COLLECTION_RUN_CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_current_host_evidence_collection_run_contract_diagnostic_contract.json"
ACQUISITION_CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic_contract.json"
ADMISSION_CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic_contract.json"
CORE_PREFLIGHT_CONTRACT_PATH = RUNTIME / "current_production_core_execution_preflight_contract.json"
LOCAL_ROUTE_POLICY_CONTRACT_PATH = RUNTIME / "current_production_ssh_local_route_policy_diagnostic_contract.json"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _contract() -> dict[str, object]:
    return _json(CONTRACT_PATH)


def _local_route_receipt(observed_on: str = "2026-08-12", *, ready: bool = True) -> dict[str, object]:
    facts: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC",
        "observed_on": observed_on,
        "ssh_config_state": "RESOLVED",
        "route_shape": "DIRECT",
        "default_route_state": "AVAILABLE",
        "target_route_state": "AVAILABLE",
        "socket_precheck_state": "AVAILABLE",
        "local_route_policy_ready": ready,
        "ssh_config_value_emitted_or_persisted": False,
        "route_output_emitted_or_persisted": False,
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    if not ready:
        facts["target_route_state"] = "UNAVAILABLE"
    return local_route.build_receipt(_json(LOCAL_ROUTE_POLICY_CONTRACT_PATH), facts)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _static_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    collection = tmp_path / "collection.json"
    acquisition = tmp_path / "acquisition.json"
    admission = tmp_path / "admission.json"
    preflight = tmp_path / "preflight.json"
    route = tmp_path / "route.json"
    _write_json(collection, _json(COLLECTION_RUN_CONTRACT_PATH))
    _write_json(acquisition, _json(ACQUISITION_CONTRACT_PATH))
    _write_json(admission, _json(ADMISSION_CONTRACT_PATH))
    _write_json(preflight, _json(CORE_PREFLIGHT_CONTRACT_PATH))
    _write_json(route, _json(LOCAL_ROUTE_POLICY_CONTRACT_PATH))
    return collection, acquisition, admission, preflight, route


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _discover_with_route_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipt: object) -> dict[str, object]:
    collection, acquisition, admission, preflight, route = _static_paths(tmp_path)
    ssh_config = tmp_path / "ssh-config"
    ssh_config.write_text("Host ovh-prod\n", encoding="utf-8")
    monkeypatch.setattr(execution, "_build_current_local_route_receipt", lambda *_: receipt)
    return discover_current_host_evidence_collection_execution(
        _root(tmp_path),
        collection,
        acquisition,
        admission,
        preflight,
        route,
        ssh_config,
        "2026-08-12",
    )


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "collection_run_contract_state": "OBSERVED_STATIC",
        "acquisition_contract_state": "OBSERVED_STATIC",
        "admission_contract_state": "OBSERVED_STATIC",
        "core_preflight_contract_state": "OBSERVED_STATIC",
        "local_route_policy_contract_state": "OBSERVED_STATIC",
        "transport_route_receipt_state": "OBSERVED_CURRENT_LOCAL_POLICY_ONLY_REDACTED",
        "transport_eligibility_state": "LOCAL_ROUTE_POLICY_ONLY_TRANSPORT_NOT_PROVEN_REDACTED",
        "current_host_metadata_collection_state": "CURRENT_HOST_METADATA_REQUIRED_REDACTED",
        "current_host_metadata_collection_attempts": 0,
        "current_host_metadata_read": False,
        "privileged_metadata_read": False,
        "runtime_prerequisites_read": False,
        "core_unit_read": False,
        "connector_unit_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "socket_connections_attempted": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_requires_independent_transport_proof_and_preserves_zero_connection_boundary() -> None:
    contract = _contract()

    validate_contract(contract)

    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_current_host_metadata_collection_attempts"] == 1
    assert expected["same_utc_date_required"] is True
    assert expected["local_route_policy_only_is_transport_proof"] is False
    assert boundary["socket_connection_attempted"] is False
    assert boundary["ssh_connection_attempted"] is False
    assert boundary["current_host_metadata_read"] is False


def test_current_local_policy_is_not_promoted_to_transport_proof_or_metadata_collection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    facts = _discover_with_route_receipt(tmp_path, monkeypatch, _local_route_receipt())
    result = evaluate_execution(_contract(), facts)
    serialized = json.dumps(build_receipt(_contract(), facts), sort_keys=True)

    assert facts["transport_route_receipt_state"] == "OBSERVED_CURRENT_LOCAL_POLICY_ONLY_REDACTED"
    assert facts["transport_eligibility_state"] == "LOCAL_ROUTE_POLICY_ONLY_TRANSPORT_NOT_PROVEN_REDACTED"
    assert facts["current_host_metadata_collection_state"] == "CURRENT_HOST_METADATA_REQUIRED_REDACTED"
    assert facts["current_host_metadata_collection_attempts"] == 0
    assert result["status"] == PASS_STATUS
    assert result["current_host_metadata_read"] is False
    assert "route_shape" not in serialized
    assert "config_file_kind" not in serialized


def test_stale_local_route_evidence_is_distinguished_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    facts = _discover_with_route_receipt(tmp_path, monkeypatch, _local_route_receipt("2026-08-11"))

    assert facts["transport_route_receipt_state"] == "STALE_REDACTED"
    assert facts["transport_eligibility_state"] == "TRANSPORT_ROUTE_EVIDENCE_STALE_REDACTED"
    assert facts["current_host_metadata_collection_state"] == "CURRENT_HOST_METADATA_STALE_REDACTED"
    assert facts["current_host_metadata_collection_attempts"] == 0


def test_malformed_route_receipt_is_schema_rejected_without_metadata_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    facts = _discover_with_route_receipt(tmp_path, monkeypatch, {"unexpected": True})

    assert facts["transport_route_receipt_state"] == "SCHEMA_REJECTED_REDACTED"
    assert facts["transport_eligibility_state"] == "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    assert facts["current_host_metadata_collection_state"] == "CURRENT_HOST_METADATA_SCHEMA_REJECTED_REDACTED"
    assert facts["current_host_metadata_read"] is False


def test_route_diagnostic_unavailability_remains_metadata_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = local_route._failure_receipt(ValueError("input"))
    facts = _discover_with_route_receipt(tmp_path, monkeypatch, receipt)

    assert facts["transport_route_receipt_state"] == "UNAVAILABLE_REDACTED"
    assert facts["transport_eligibility_state"] == "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED"
    assert facts["current_host_metadata_collection_state"] == "CURRENT_HOST_METADATA_REQUIRED_REDACTED"


def test_invalid_static_contract_prevents_route_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    collection, acquisition, admission, preflight, route = _static_paths(tmp_path)
    _write_json(collection, {"unexpected": True})
    ssh_config = tmp_path / "ssh-config"
    ssh_config.write_text("Host ovh-prod\n", encoding="utf-8")
    called = False

    def should_not_run(*_: object) -> dict[str, object]:
        nonlocal called
        called = True
        return _local_route_receipt()

    monkeypatch.setattr(execution, "_build_current_local_route_receipt", should_not_run)
    facts = discover_current_host_evidence_collection_execution(
        _root(tmp_path), collection, acquisition, admission, preflight, route, ssh_config, "2026-08-12"
    )

    assert facts["collection_run_contract_state"] == "REJECTED_REDACTED"
    assert facts["transport_route_receipt_state"] == "NOT_ATTEMPTED"
    assert facts["current_host_metadata_collection_state"] == "STATIC_INPUT_REJECTED_REDACTED"
    assert called is False


def test_facts_reject_metadata_collection_or_outbound_relaxation() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError, match="collection attempt boundary"):
        validate_facts(_facts(current_host_metadata_collection_attempts=1))

    with pytest.raises(CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError, match="collection boundary"):
        validate_facts(_facts(current_host_metadata_read=True))

    with pytest.raises(CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError, match="outbound operation count"):
        validate_facts(_facts(ssh_connections_attempted=1))


def test_facts_reject_promoting_local_route_policy_to_transport_proof() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError, match="route receipt facts"):
        validate_facts(_facts(transport_eligibility_state="TRANSPORT_ROUTE_NOT_PROVEN_REDACTED"))


def test_contract_rejects_boundary_relaxation() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["socket_connection_attempted"] = True

    with pytest.raises(CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError, match="boundary"):
        validate_contract(contract)


def test_runner_is_fixed_to_existing_contracts_and_local_ssh_config_only() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")

    assert "current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution.py" in runner
    assert "current_production_rebuild_metadata_current_host_evidence_collection_run_contract_diagnostic_contract.json" in runner
    assert "current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic_contract.json" in runner
    assert "current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic_contract.json" in runner
    assert "current_production_core_execution_preflight_contract.json" in runner
    assert "current_production_ssh_local_route_policy_diagnostic_contract.json" in runner
    assert "--ssh-config" in runner
    assert "private_db_client.py" not in runner


def test_module_reuses_only_the_existing_local_route_diagnostic_and_has_no_direct_network_capability() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "current_production_ssh_local_route_policy_diagnostic" in source
    for prohibited in (
        "import socket",
        "import urllib",
        "import requests",
        "import http",
        "os.system(",
        "subprocess.",
        "private_db_client",
    ):
        assert prohibited not in source


def test_failure_status_is_reserved_for_invalid_execution_inputs() -> None:
    assert PASS_STATUS != FAIL_STATUS
    assert execution._failure_receipt(ValueError("invalid"), "not-a-date")["status"] == FAIL_STATUS
