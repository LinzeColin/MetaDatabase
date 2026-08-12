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

from current_candidate_recovery_oci_attestation import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentCandidateRecoveryOciAttestationError,
    build_receipt,
    evaluate_candidate,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "current_candidate_recovery_oci_attestation_contract.json"
VALIDATOR_PATH = RUNTIME / "current_candidate_recovery_oci_attestation.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _candidate() -> dict[str, object]:
    return {
        "oci_archive_sha256": "2cbfde404f1d21b3241da4f31eb67f44708798c959e62c2213265647c2db332d",
        "oci_archive_bytes": 18043392,
        "candidate_manifest_digest": "sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "candidate_image_id": "sha256:e9a3d81370ec722178393f1d153fc8c1540987ec44740aa435603977b1688702",
        "candidate_architecture": "amd64",
        "candidate_os": "linux",
        "candidate_layer_count": 3,
    }


def test_contract_preserves_temporary_archive_only_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["private_archive_object_downloaded"] is True
    assert boundary["archive_content_read"] is True
    assert boundary["archive_loaded_or_retagged"] is False
    assert boundary["host_runtime_or_configuration_changed"] is False
    assert boundary["real_time_soak_waited"] is False


def test_exact_candidate_identity_passes_without_authorizing_execution() -> None:
    result = evaluate_candidate(_contract(), _candidate())

    assert result["status"] == PASS_STATUS
    assert result["attestation_valid"] is True
    assert result["execution_authorized"] is False
    assert result["failure_codes"] == []


@pytest.mark.parametrize(
    ("key", "value", "failure_code"),
    [
        ("oci_archive_sha256", "0" * 64, "ARCHIVE_CONTENT_IDENTITY_EXACT"),
        ("oci_archive_bytes", 18043391, "ARCHIVE_BYTE_COUNT_EXACT"),
        ("candidate_manifest_digest", "sha256:" + "0" * 64, "OCI_MANIFEST_IDENTITY_EXACT"),
        ("candidate_image_id", "sha256:" + "0" * 64, "OCI_CONFIG_IDENTITY_EXACT"),
    ],
)
def test_identity_divergence_fails_closed(key: str, value: object, failure_code: str) -> None:
    candidate = _candidate()
    candidate[key] = value

    result = evaluate_candidate(_contract(), candidate)

    assert result["status"] == FAIL_STATUS
    assert result["attestation_valid"] is False
    assert failure_code in result["failure_codes"]


def test_contract_cannot_authorize_archive_load() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["archive_loaded_or_retagged"] = True

    with pytest.raises(CurrentCandidateRecoveryOciAttestationError, match="source boundary"):
        validate_contract(contract)


def test_receipt_is_redacted_and_keeps_old_rollback_unproved() -> None:
    contract = _contract()
    receipt = build_receipt(contract, evaluate_candidate(contract, _candidate()), "2026-08-12")
    serialized = json.dumps(receipt, sort_keys=True)
    expected = contract["expected"]
    assert isinstance(expected, dict)

    assert receipt["status"] == PASS_STATUS
    assert receipt["execution_authorized"] is False
    assert receipt["observed"]["current_candidate_archive_content_attested"] is True
    assert receipt["observed"]["old_rollback_archive_proved"] is False
    assert str(expected["archive_sha256"]) not in serialized
    assert str(expected["manifest_digest"]) not in serialized
    assert str(expected["config_digest"]) not in serialized


def test_source_has_no_network_or_runtime_mutation_capability() -> None:
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
