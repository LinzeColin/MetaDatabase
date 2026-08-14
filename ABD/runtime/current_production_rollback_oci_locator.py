#!/usr/bin/env python3
"""Validate one redacted private-catalog location result for ABD rollback OCI assets."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_ROLLBACK_OCI_CATALOG_LOCATOR"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_ROLLBACK_OCI_CATALOG_LOCATOR"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_ROLLBACK_OCI_CATALOG_LOCATOR"


class CurrentProductionRollbackOciLocatorError(ValueError):
    """Raised when the non-downloading catalog location boundary is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionRollbackOciLocatorError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionRollbackOciLocatorError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _image_id(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise CurrentProductionRollbackOciLocatorError("%s must be an image id" % name)
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise CurrentProductionRollbackOciLocatorError("%s must be lowercase" % name)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "rollback OCI locator contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRollbackOciLocatorError) as exc:
        raise CurrentProductionRollbackOciLocatorError("rollback OCI locator contract is unreadable") from exc


def load_catalog(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "redacted catalog observation")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRollbackOciLocatorError) as exc:
        raise CurrentProductionRollbackOciLocatorError("redacted catalog observation is unreadable") from exc


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
        raise CurrentProductionRollbackOciLocatorError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionRollbackOciLocatorError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-ROLLBACK-OCI-LOCATOR-001":
        raise CurrentProductionRollbackOciLocatorError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionRollbackOciLocatorError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_PRIVATE_CATALOG_METADATA_LOCATOR_ONLY":
        raise CurrentProductionRollbackOciLocatorError("locator must remain metadata-only")
    expected = _object(contract.get("expected"), "locator expected")
    expected_values = {
        "private_catalog": "Private-MetaDatabase/manifest.jsonl",
        "old_rollback_image_id": "sha256:6d51e3e01c2fb7a02460ac9c9eeaf20b8f41f144c4dc795eaae5335b15737ec8",
        "current_candidate_image_id": "sha256:a79c1109c85beb9bc495372daf6f7e8f620e6006244ac7d2b32b8481355257b2",
        "current_candidate_archive_name": "abd-shadow-oci-candidate-a79c1109c85b-20260810.tar",
        "current_candidate_archive_size_bytes": 18043392,
    }
    if dict(expected) != expected_values:
        raise CurrentProductionRollbackOciLocatorError("locator expected state is not exact")
    _image_id(expected["old_rollback_image_id"], "old rollback image id")
    _image_id(expected["current_candidate_image_id"], "current candidate image id")
    expected_boundary = {
        "private_catalog_metadata_read": True,
        "private_archive_object_downloaded": False,
        "host_runtime_or_configuration_changed": False,
        "image_loaded_or_retagged": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "runtime_secret_or_tunnel_credential_read": False,
        "external_network_scope": "GITHUB_PRIVATE_DATABASE_METADATA_ONLY",
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != expected_boundary:
        raise CurrentProductionRollbackOciLocatorError("source boundary is not exact")
    if contract.get("claim_boundary") != "PRIVATE_CATALOG_LOCATION_STATUS_ONLY_NOT_ARCHIVE_CONTENT_ATTESTATION_HOST_RECOVERY_OR_AUTOMATIC_ROLLBACK":
        raise CurrentProductionRollbackOciLocatorError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRollbackOciLocatorError("rollback boundary is not exact")


def validate_catalog(catalog: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "private_catalog",
        "old_rollback_image",
        "current_candidate_archive",
        "code_search",
    }
    if set(catalog) != required:
        raise CurrentProductionRollbackOciLocatorError("catalog field set is not exact")
    if catalog.get("schema_version") != "1.0.0":
        raise CurrentProductionRollbackOciLocatorError("catalog schema is not supported")
    if catalog.get("observation_type") != "ABD_PRIVATE_ROLLBACK_OCI_CATALOG_METADATA":
        raise CurrentProductionRollbackOciLocatorError("catalog observation type is not exact")
    try:
        date.fromisoformat(str(catalog.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionRollbackOciLocatorError("catalog observation date is invalid") from exc
    if _object(catalog.get("private_catalog"), "private catalog") != {
        "manifest_read": True,
        "manifest_size_bytes": 100332,
        "abd_json_receipt_count": 39,
        "receipt_read_failures": 0,
        "oci_archive_objects_downloaded": False,
    }:
        raise CurrentProductionRollbackOciLocatorError("private catalog metadata is not exact")
    if _object(catalog.get("old_rollback_image"), "old rollback image") != {
        "exact_identity_match_count": 0,
        "archive_catalog_status": "NOT_LOCATED_IN_PRIVATE_ABD_METADATA",
    }:
        raise CurrentProductionRollbackOciLocatorError("old rollback archive status is not exact")
    if _object(catalog.get("current_candidate_archive"), "current candidate archive") != {
        "catalog_record_present": True,
        "archive_object_content_read": False,
        "catalog_record_name": "abd-shadow-oci-candidate-a79c1109c85b-20260810.tar",
        "catalog_record_size_bytes": 18043392,
    }:
        raise CurrentProductionRollbackOciLocatorError("current candidate archive status is not exact")
    if _object(catalog.get("code_search"), "code search") != {
        "attempted": True,
        "complete": False,
        "exact_identity_match_count": 0,
    }:
        raise CurrentProductionRollbackOciLocatorError("code search observation is not exact")


def evaluate_catalog(contract: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_catalog(catalog)
    private_catalog = _object(catalog["private_catalog"], "private catalog")
    old_rollback_image = _object(catalog["old_rollback_image"], "old rollback image")
    current_candidate = _object(catalog["current_candidate_archive"], "current candidate archive")
    checks = [
        {"id": "PRIVATE_MANIFEST_CATALOG_READ", "passed": private_catalog["manifest_read"] is True},
        {
            "id": "ALL_LISTED_ABD_JSON_RECEIPTS_READ",
            "passed": private_catalog["abd_json_receipt_count"] == 39 and private_catalog["receipt_read_failures"] == 0,
        },
        {
            "id": "OLD_ROLLBACK_IMAGE_HAS_NO_EXACT_METADATA_MATCH",
            "passed": old_rollback_image["exact_identity_match_count"] == 0,
        },
        {
            "id": "OLD_ROLLBACK_ARCHIVE_REMAINS_NOT_PROVED",
            "passed": old_rollback_image["archive_catalog_status"] == "NOT_LOCATED_IN_PRIVATE_ABD_METADATA",
        },
        {
            "id": "CURRENT_CANDIDATE_ARCHIVE_CATALOG_RECORD_LOCATED",
            "passed": current_candidate["catalog_record_present"] is True,
        },
        {
            "id": "NO_OCI_ARCHIVE_OBJECT_DOWNLOADED",
            "passed": private_catalog["oci_archive_objects_downloaded"] is False
            and current_candidate["archive_object_content_read"] is False,
        },
    ]
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if not failures else FAIL_STATUS,
        "decision": "OLD_ROLLBACK_OCI_ARCHIVE_NOT_PROVED_CURRENT_CANDIDATE_RECOVERY_ARCHIVE_METADATA_LOCATED"
        if not failures
        else "ROLLBACK_OCI_CATALOG_LOCATION_INPUT_FAILED_CLOSED",
        "locator_valid": not failures,
        "execution_authorized": False,
        "checks": checks,
        "failure_codes": failures,
        "unresolved_prerequisites": [
            "OLD_ROLLBACK_OCI_ARCHIVE_CONTENT_AND_PROVENANCE_NOT_PROVED",
            "SEPARATE_CURRENT_CANDIDATE_RECOVERY_ARCHIVE_CONTENT_ATTESTATION_CONTRACT",
        ]
        if not failures
        else [],
    }


def build_receipt(contract: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_catalog(contract, catalog)
    private_catalog = _object(catalog["private_catalog"], "private catalog")
    old_rollback_image = _object(catalog["old_rollback_image"], "old rollback image")
    current_candidate = _object(catalog["current_candidate_archive"], "current candidate archive")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": catalog["observed_on"],
        "locator_valid": result["locator_valid"],
        "execution_authorized": result["execution_authorized"],
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "unresolved_prerequisites": result["unresolved_prerequisites"],
        "observed": {
            "private_manifest_catalog_read": private_catalog["manifest_read"],
            "all_listed_abd_json_receipts_read": private_catalog["receipt_read_failures"] == 0,
            "old_rollback_archive_proved": old_rollback_image["archive_catalog_status"] != "NOT_LOCATED_IN_PRIVATE_ABD_METADATA",
            "current_candidate_archive_metadata_located": current_candidate["catalog_record_present"],
            "oci_archive_object_downloaded": private_catalog["oci_archive_objects_downloaded"],
        },
        "source_boundary": dict(_object(contract["source_boundary"], "source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "ROLLBACK_OCI_CATALOG_LOCATOR_INPUT_FAILED_CLOSED",
        "locator_valid": False,
        "execution_authorized": False,
        "checks": [],
        "failure_codes": ["ROLLBACK_OCI_CATALOG_LOCATOR_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "private_archive_object_downloaded": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_catalog(args.catalog))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRollbackOciLocatorError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
