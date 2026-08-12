from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic as diagnostic
from current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    REPAIR_SOURCE_CONSTANTS,
    REPAIR_SOURCE_FUNCTIONS,
    CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError,
    build_receipt,
    discover_static_provenance,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic.py"
REPAIR_CONTRACT_PATH = RUNTIME / "current_production_blue_release_repair_contract.json"
REPAIR_SOURCE_PATH = RUNTIME / "current_production_blue_release_repair.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _repair_contract() -> dict[str, object]:
    return json.loads(REPAIR_CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "repair_contract_state": "OBSERVED_STATIC",
        "repair_source_state": "OBSERVED_STATIC",
        "rebuild_metadata_source_repair_provenance_state": "SOURCE_PROVENANCE_DECLARED_REDACTED",
        "source_provenance_declared": True,
        "repair_source_executed": False,
        "rebuild_script_content_read": False,
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


def _write_repair_source(path: Path, include_functions: bool = True) -> None:
    declarations = "\n".join(
        [
            'RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR"',
            'INFRA_SOURCE_PATHS = ["infra/config.schema.json", "infra/rebuild.sh"]',
        ]
    )
    functions = "\n".join("def %s():\n    return None" % name for name in sorted(REPAIR_SOURCE_FUNCTIONS)) if include_functions else ""
    path.write_text("%s\n%s\n" % (declarations, functions), encoding="utf-8")


def _root(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def test_contract_preserves_static_source_only_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["rebuild_metadata_subdomain"] == diagnostic.REBUILD_METADATA_SUBDOMAIN
    assert expected["repair_source_constant_names"] == sorted(REPAIR_SOURCE_CONSTANTS)
    assert boundary["repair_source_executed"] is False
    assert boundary["rebuild_script_content_read"] is False


def test_static_contract_and_source_declare_provenance_without_execution(tmp_path: Path) -> None:
    repair_contract = tmp_path / "repair-contract.json"
    repair_source = tmp_path / "repair-source.py"
    repair_contract.write_text(json.dumps(_repair_contract()), encoding="utf-8")
    _write_repair_source(repair_source)

    facts = discover_static_provenance(_root(tmp_path), repair_contract, repair_source, "2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)
    serialized = json.dumps(build_receipt(_contract(), facts), sort_keys=True)

    assert facts["rebuild_metadata_source_repair_provenance_state"] == "SOURCE_PROVENANCE_DECLARED_REDACTED"
    assert facts["source_provenance_declared"] is True
    assert result["status"] == PASS_STATUS
    assert result["core_start_authorized"] is False
    assert "infra/rebuild.sh" not in serialized
    assert "INFRA_SOURCE_PATHS" not in serialized


def test_source_without_required_declaration_is_not_promoted(tmp_path: Path) -> None:
    repair_contract = tmp_path / "repair-contract.json"
    repair_source = tmp_path / "repair-source.py"
    repair_contract.write_text(json.dumps(_repair_contract()), encoding="utf-8")
    _write_repair_source(repair_source, include_functions=False)

    facts = discover_static_provenance(_root(tmp_path), repair_contract, repair_source, "2026-08-12")

    assert facts["repair_contract_state"] == "OBSERVED_STATIC"
    assert facts["repair_source_state"] == "OBSERVED_STATIC"
    assert facts["rebuild_metadata_source_repair_provenance_state"] == "SOURCE_PROVENANCE_NOT_DECLARED_REDACTED"
    assert facts["source_provenance_declared"] is False


def test_rejected_contract_and_source_are_distinguished(tmp_path: Path) -> None:
    rejected_contract = tmp_path / "rejected-contract.json"
    repair_source = tmp_path / "repair-source.py"
    rejected_contract.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
    _write_repair_source(repair_source)

    rejected = discover_static_provenance(_root(tmp_path, "contract-root"), rejected_contract, repair_source, "2026-08-12")
    assert rejected["rebuild_metadata_source_repair_provenance_state"] == "REPAIR_CONTRACT_REJECTED_REDACTED"

    repair_contract = tmp_path / "repair-contract.json"
    bad_source = tmp_path / "bad-source.py"
    repair_contract.write_text(json.dumps(_repair_contract()), encoding="utf-8")
    bad_source.write_text("def broken(:\n", encoding="utf-8")
    source_rejected = discover_static_provenance(_root(tmp_path, "source-root"), repair_contract, bad_source, "2026-08-12")
    assert source_rejected["rebuild_metadata_source_repair_provenance_state"] == "REPAIR_SOURCE_REJECTED_REDACTED"


def test_unavailable_inputs_fail_closed(tmp_path: Path) -> None:
    missing_contract = tmp_path / "missing-contract.json"
    missing_source = tmp_path / "missing-source.py"
    facts = discover_static_provenance(_root(tmp_path), missing_contract, missing_source, "2026-08-12")
    assert facts["rebuild_metadata_source_repair_provenance_state"] == "REPAIR_CONTRACT_UNAVAILABLE_REDACTED"

    repair_contract = tmp_path / "repair-contract.json"
    repair_contract.write_text(json.dumps(_repair_contract()), encoding="utf-8")
    source_missing = discover_static_provenance(_root(tmp_path, "source-missing"), repair_contract, missing_source, "2026-08-12")
    assert source_missing["rebuild_metadata_source_repair_provenance_state"] == "REPAIR_SOURCE_UNAVAILABLE_REDACTED"


def test_facts_reject_external_operations_and_boundary_relaxation() -> None:
    with pytest.raises(CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(provider_api_requests=1))

    with pytest.raises(CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError, match="static boundary"):
        validate_facts(_facts(repair_source_executed=True))


def test_contract_cannot_relax_source_execution_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["repair_source_executed"] = True

    with pytest.raises(CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_and_module_have_no_repair_execution_or_network_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--repo-root" in runner
    assert "--observed-on" in runner
    assert "current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic.py" in runner
    for forbidden in (
        "subprocess",
        "socket.",
        "urllib.request",
        "import requests",
        "requests.",
        "urlopen",
        "ssh ",
        "curl ",
        "wget ",
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

    with pytest.raises(CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC"
