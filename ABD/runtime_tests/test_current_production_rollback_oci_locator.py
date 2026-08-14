from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_rollback_oci_locator import (
    PASS_STATUS,
    CurrentProductionRollbackOciLocatorError,
    build_receipt,
    evaluate_catalog,
    validate_catalog,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "current_production_rollback_oci_locator_contract.json"
VALIDATOR_PATH = RUNTIME / "current_production_rollback_oci_locator.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _catalog() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_PRIVATE_ROLLBACK_OCI_CATALOG_METADATA",
        "observed_on": "2026-08-12",
        "private_catalog": {
            "manifest_read": True,
            "manifest_size_bytes": 100332,
            "abd_json_receipt_count": 39,
            "receipt_read_failures": 0,
            "oci_archive_objects_downloaded": False,
        },
        "old_rollback_image": {
            "exact_identity_match_count": 0,
            "archive_catalog_status": "NOT_LOCATED_IN_PRIVATE_ABD_METADATA",
        },
        "current_candidate_archive": {
            "catalog_record_present": True,
            "archive_object_content_read": False,
            "catalog_record_name": "abd-shadow-oci-candidate-a79c1109c85b-20260810.tar",
            "catalog_record_size_bytes": 18043392,
        },
        "code_search": {
            "attempted": True,
            "complete": False,
            "exact_identity_match_count": 0,
        },
    }


def test_contract_preserves_catalog_only_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["private_catalog_metadata_read"] is True
    assert boundary["private_archive_object_downloaded"] is False
    assert boundary["host_runtime_or_configuration_changed"] is False
    assert boundary["image_loaded_or_retagged"] is False
    assert boundary["real_time_soak_waited"] is False


def test_exact_catalog_passes_but_never_authorizes_recovery_execution() -> None:
    result = evaluate_catalog(_contract(), _catalog())

    assert result["status"] == PASS_STATUS
    assert result["locator_valid"] is True
    assert result["execution_authorized"] is False
    assert result["failure_codes"] == []
    assert result["unresolved_prerequisites"] == [
        "OLD_ROLLBACK_OCI_ARCHIVE_CONTENT_AND_PROVENANCE_NOT_PROVED",
        "SEPARATE_CURRENT_CANDIDATE_RECOVERY_ARCHIVE_CONTENT_ATTESTATION_CONTRACT",
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["private_catalog"].update({"receipt_read_failures": 1}),
        lambda value: value["old_rollback_image"].update({"exact_identity_match_count": 1}),
        lambda value: value["current_candidate_archive"].update({"archive_object_content_read": True}),
    ],
)
def test_catalog_divergence_is_rejected_before_any_recovery_execution(mutate) -> None:
    catalog = _catalog()
    mutate(catalog)

    with pytest.raises(CurrentProductionRollbackOciLocatorError):
        validate_catalog(catalog)


def test_contract_cannot_authorize_an_archive_download() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["private_archive_object_downloaded"] = True

    with pytest.raises(CurrentProductionRollbackOciLocatorError, match="source boundary"):
        validate_contract(contract)


def test_receipt_is_redacted_and_reports_unproved_old_rollback() -> None:
    contract = _contract()
    receipt = build_receipt(contract, _catalog())
    serialized = json.dumps(receipt, sort_keys=True)
    expected = contract["expected"]
    assert isinstance(expected, dict)

    assert receipt["status"] == PASS_STATUS
    assert receipt["execution_authorized"] is False
    assert receipt["observed"]["old_rollback_archive_proved"] is False
    assert receipt["observed"]["current_candidate_archive_metadata_located"] is True
    assert str(expected["old_rollback_image_id"]) not in serialized
    assert str(expected["current_candidate_archive_name"]) not in serialized


def test_source_has_no_network_or_host_mutation_capability() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "import subprocess",
        "import requests",
        "import urllib",
        "time.sleep(",
        "docker load",
        "docker tag",
        "systemctl start",
        "systemctl enable",
        "cloudflared tunnel",
    ):
        assert forbidden not in source
