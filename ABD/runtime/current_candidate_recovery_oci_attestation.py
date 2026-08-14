#!/usr/bin/env python3
"""Attest one temporary ABD current-candidate OCI archive without loading it."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from shadow_runtime_provenance import (
    ShadowRuntimeProvenanceError,
    load_contract as load_semantic_contract,
    validate_contract as validate_semantic_contract,
    validate_oci_archive,
)


PASS_STATUS = "PASS_CURRENT_CANDIDATE_RECOVERY_OCI_ARCHIVE_ATTESTATION"
FAIL_STATUS = "FAIL_CURRENT_CANDIDATE_RECOVERY_OCI_ARCHIVE_ATTESTATION"
RECEIPT_TYPE = "ABD_CURRENT_CANDIDATE_RECOVERY_OCI_ARCHIVE_ATTESTATION"


class CurrentCandidateRecoveryOciAttestationError(ValueError):
    """Raised when current-candidate archive attestation inputs are malformed."""


SemanticValidator = Callable[[Mapping[str, Any], Path], Mapping[str, Any]]


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentCandidateRecoveryOciAttestationError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentCandidateRecoveryOciAttestationError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise CurrentCandidateRecoveryOciAttestationError("%s must be a sha256 digest" % name)
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise CurrentCandidateRecoveryOciAttestationError("%s must be lowercase" % name)
    return value


def _sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise CurrentCandidateRecoveryOciAttestationError("%s must be a sha256" % name)
    if any(character not in "0123456789abcdef" for character in value):
        raise CurrentCandidateRecoveryOciAttestationError("%s must be lowercase" % name)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "current candidate archive attestation contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentCandidateRecoveryOciAttestationError) as exc:
        raise CurrentCandidateRecoveryOciAttestationError("current candidate archive attestation contract is unreadable") from exc


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "contract_id",
        "product_version",
        "status",
        "expected",
        "source_boundary",
        "claim_boundary",
        "rollback",
    }
    if set(contract) != required:
        raise CurrentCandidateRecoveryOciAttestationError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentCandidateRecoveryOciAttestationError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-CANDIDATE-RECOVERY-OCI-ATTESTATION-001":
        raise CurrentCandidateRecoveryOciAttestationError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentCandidateRecoveryOciAttestationError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_PRIVATE_OCI_ARCHIVE_CONTENT_ATTESTATION_ONLY":
        raise CurrentCandidateRecoveryOciAttestationError("attestation must remain archive-only")
    expected = _object(contract.get("expected"), "attestation expected")
    expected_values = {
        "private_object_path": "objects/2c/2cbfde404f1d21b3241da4f31eb67f44708798c959e62c2213265647c2db332d_abd-shadow-oci-candidate-a79c1109c85b-20260810.tar",
        "archive_sha256": "2cbfde404f1d21b3241da4f31eb67f44708798c959e62c2213265647c2db332d",
        "archive_bytes": 18043392,
        "manifest_digest": "sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "config_digest": "sha256:e9a3d81370ec722178393f1d153fc8c1540987ec44740aa435603977b1688702",
        "semantic_contract_id": "ABD-POST-FREEZE-SHADOW-SOURCE-TO-OCI-001",
    }
    if dict(expected) != expected_values:
        raise CurrentCandidateRecoveryOciAttestationError("attestation expected state is not exact")
    _sha256(expected["archive_sha256"], "archive sha256")
    _digest(expected["manifest_digest"], "manifest digest")
    _digest(expected["config_digest"], "config digest")
    expected_boundary = {
        "private_archive_object_downloaded": True,
        "temporary_local_archive_only": True,
        "archive_content_read": True,
        "archive_loaded_or_retagged": False,
        "host_runtime_or_configuration_changed": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "runtime_secret_or_tunnel_credential_read": False,
        "external_network_scope": "PRIVATE_DATABASE_OBJECT_GET_ONLY",
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != expected_boundary:
        raise CurrentCandidateRecoveryOciAttestationError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_CANDIDATE_RECOVERY_ARCHIVE_CONTENT_ONLY_NOT_OLD_ROLLBACK_ASSET_HOST_RECOVERY_OR_AUTOMATIC_ROLLBACK":
        raise CurrentCandidateRecoveryOciAttestationError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "DELETE_ONLY_THIS_RUN_TEMPORARY_ARCHIVE_AFTER_ATTESTATION",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentCandidateRecoveryOciAttestationError("rollback boundary is not exact")


def _semantic_contract(path: Path, expected_id: str) -> Mapping[str, Any]:
    try:
        semantic_contract = load_semantic_contract(path)
        validate_semantic_contract(semantic_contract)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowRuntimeProvenanceError) as exc:
        raise CurrentCandidateRecoveryOciAttestationError("semantic OCI contract is unreadable") from exc
    if semantic_contract.get("contract_id") != expected_id:
        raise CurrentCandidateRecoveryOciAttestationError("semantic OCI contract identity is not exact")
    return semantic_contract


def evaluate_candidate(contract: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    required = {
        "oci_archive_sha256",
        "oci_archive_bytes",
        "candidate_manifest_digest",
        "candidate_image_id",
        "candidate_architecture",
        "candidate_os",
        "candidate_layer_count",
    }
    if set(candidate) != required:
        raise CurrentCandidateRecoveryOciAttestationError("candidate fact set is not exact")
    expected = _object(contract["expected"], "attestation expected")
    checks = [
        {"id": "ARCHIVE_CONTENT_IDENTITY_EXACT", "passed": candidate["oci_archive_sha256"] == expected["archive_sha256"]},
        {"id": "ARCHIVE_BYTE_COUNT_EXACT", "passed": candidate["oci_archive_bytes"] == expected["archive_bytes"]},
        {"id": "OCI_MANIFEST_IDENTITY_EXACT", "passed": candidate["candidate_manifest_digest"] == expected["manifest_digest"]},
        {"id": "OCI_CONFIG_IDENTITY_EXACT", "passed": candidate["candidate_image_id"] == expected["config_digest"]},
        {"id": "OCI_PLATFORM_EXACT", "passed": candidate["candidate_architecture"] == "amd64" and candidate["candidate_os"] == "linux"},
        {
            "id": "OCI_LAYER_SET_NONEMPTY",
            "passed": isinstance(candidate["candidate_layer_count"], int)
            and not isinstance(candidate["candidate_layer_count"], bool)
            and candidate["candidate_layer_count"] > 0,
        },
    ]
    if not isinstance(candidate["oci_archive_bytes"], int) or isinstance(candidate["oci_archive_bytes"], bool):
        raise CurrentCandidateRecoveryOciAttestationError("candidate archive bytes must be an integer")
    _sha256(candidate["oci_archive_sha256"], "candidate archive sha256")
    _digest(candidate["candidate_manifest_digest"], "candidate manifest digest")
    _digest(candidate["candidate_image_id"], "candidate image id")
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if not failures else FAIL_STATUS,
        "decision": "CURRENT_CANDIDATE_RECOVERY_ARCHIVE_CONTENT_ATTESTED_NOT_LOADED_OR_STARTED"
        if not failures
        else "CURRENT_CANDIDATE_RECOVERY_ARCHIVE_CONTENT_DIVERGED_FAIL_CLOSED",
        "attestation_valid": not failures,
        "execution_authorized": False,
        "checks": checks,
        "failure_codes": failures,
    }


def attest_archive(
    contract: Mapping[str, Any],
    archive: Path,
    semantic_contract_path: Path,
    *,
    validate_archive: SemanticValidator = validate_oci_archive,
) -> dict[str, Any]:
    validate_contract(contract)
    if not archive.is_file() or archive.is_symlink():
        raise CurrentCandidateRecoveryOciAttestationError("temporary OCI archive must be a regular file")
    expected = _object(contract["expected"], "attestation expected")
    semantic_contract = _semantic_contract(semantic_contract_path, str(expected["semantic_contract_id"]))
    try:
        candidate = validate_archive(semantic_contract, archive)
    except ShadowRuntimeProvenanceError as exc:
        raise CurrentCandidateRecoveryOciAttestationError("temporary OCI archive semantic validation failed") from exc
    return evaluate_candidate(contract, candidate)


def build_receipt(contract: Mapping[str, Any], result: Mapping[str, Any], observed_on: str) -> dict[str, Any]:
    validate_contract(contract)
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise CurrentCandidateRecoveryOciAttestationError("observed date is invalid") from exc
    required = {"status", "decision", "attestation_valid", "execution_authorized", "checks", "failure_codes"}
    if set(result) != required:
        raise CurrentCandidateRecoveryOciAttestationError("attestation result field set is not exact")
    if result["status"] not in {PASS_STATUS, FAIL_STATUS} or not isinstance(result["attestation_valid"], bool):
        raise CurrentCandidateRecoveryOciAttestationError("attestation result is invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": observed_date,
        "attestation_valid": result["attestation_valid"],
        "execution_authorized": False,
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "observed": {
            "current_candidate_archive_content_attested": result["attestation_valid"],
            "archive_loaded_or_retagged": False,
            "host_runtime_or_configuration_changed": False,
            "old_rollback_archive_proved": False,
        },
        "source_boundary": dict(_object(contract["source_boundary"], "source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        observed_date = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_CANDIDATE_RECOVERY_ARCHIVE_ATTESTATION_INPUT_FAILED_CLOSED",
        "observed_on": observed_date,
        "attestation_valid": False,
        "execution_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_CANDIDATE_RECOVERY_ARCHIVE_ATTESTATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "archive_loaded_or_retagged": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--semantic-contract", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        result = attest_archive(contract, args.archive, args.semantic_contract)
        receipt = build_receipt(contract, result, args.observed_on)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentCandidateRecoveryOciAttestationError, ShadowRuntimeProvenanceError, ValueError) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
