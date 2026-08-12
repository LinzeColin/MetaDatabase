#!/usr/bin/env python3
"""Validate the non-mutating remediation contract for the current ABD host."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CONTROL_PLANE_REMEDIATION_CONTRACT"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CONTROL_PLANE_REMEDIATION_CONTRACT"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CONTROL_PLANE_REMEDIATION_CONTRACT"


class CurrentProductionRemediationError(ValueError):
    """Raised when a remediation contract or redacted baseline is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionRemediationError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionRemediationError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _image_id(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise CurrentProductionRemediationError("%s must be an image id" % name)
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise CurrentProductionRemediationError("%s must be lowercase" % name)
    return value


def _path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\n" in value or "\x00" in value:
        raise CurrentProductionRemediationError("%s must be an absolute path" % name)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "remediation contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRemediationError) as exc:
        raise CurrentProductionRemediationError("remediation contract is unreadable") from exc


def load_baseline(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "redacted baseline")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRemediationError) as exc:
        raise CurrentProductionRemediationError("redacted baseline is unreadable") from exc


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "contract_id",
        "product_version",
        "status",
        "diagnostic_input",
        "remediation_targets",
        "source_boundary",
        "claim_boundary",
        "rollback",
    }
    if set(contract) != required:
        raise CurrentProductionRemediationError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionRemediationError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CONTROL-PLANE-REMEDIATION-001":
        raise CurrentProductionRemediationError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionRemediationError("product version is not exact")
    if contract.get("status") != "CONTRACT_ONLY_NO_HOST_MUTATION":
        raise CurrentProductionRemediationError("contract must remain non-mutating")
    if _object(contract.get("diagnostic_input"), "diagnostic input") != {
        "contract_id": "ABD-POST-FREEZE-SHADOW-POST-PROMOTION-REVIEW-001",
        "failure_codes": [
            "PRIOR_IMAGE_RETAINED_UNTAGGED",
            "CORE_SERVICE_INACTIVE",
            "CORE_CONNECTOR_INACTIVE",
            "CONNECTOR_CONFIG_REGULAR_FILE",
            "CONNECTOR_HAS_NO_HOSTNAME",
        ],
    }:
        raise CurrentProductionRemediationError("diagnostic input is not exact")

    targets = _object(contract.get("remediation_targets"), "remediation targets")
    if set(targets) != {"rollback_asset", "core_units", "connector_config"}:
        raise CurrentProductionRemediationError("remediation target set is not exact")
    rollback_asset = _object(targets.get("rollback_asset"), "rollback asset")
    expected_rollback_asset = {
        "prior_image_id": "sha256:6d51e3e01c2fb7a02460ac9c9eeaf20b8f41f144c4dc795eaae5335b15737ec8",
        "current_host_state": "ABSENT",
        "private_source_state": "UNKNOWN_PRIVATE_CATALOG_NOT_READABLE",
        "required_before_any_image_load": "PRIVATE_RECOVERABLE_OCI_ARCHIVE_VERIFIED",
        "image_load_authorized_by_this_contract": False,
        "current_candidate_shadow_must_remain_unchanged": True,
    }
    if dict(rollback_asset) != expected_rollback_asset:
        raise CurrentProductionRemediationError("rollback asset target is not exact")
    _image_id(rollback_asset["prior_image_id"], "prior image id")

    core_units = _object(targets.get("core_units"), "core units")
    if dict(core_units) != {
        "service_names": ["abd.service", "abd-cloudflared.service"],
        "current_safe_state": "NOT_FOUND_AND_INACTIVE",
        "unit_creation_authorized_by_this_contract": False,
        "unit_start_authorized_by_this_contract": False,
        "core_activation_requires": "SEPARATE_CORE_CAPACITY_AND_EXECUTION_CONTRACT",
    }:
        raise CurrentProductionRemediationError("core unit target is not exact")

    connector = _object(targets.get("connector_config"), "connector configuration")
    expected_connector = {
        "path": "/etc/cloudflared/config.yml",
        "current_safe_state": "MISSING",
        "hostname_state": "UNKNOWN_UNTIL_REGULAR_FILE_REVIEWED",
        "required_pre_activation": {
            "regular_non_symlink_file": True,
            "hostname_entries_allowed": False,
            "only_terminal_ingress": "http_status:404",
            "metrics_bind": "127.0.0.1:49312",
        },
        "config_write_authorized_by_this_contract": False,
        "connector_start_authorized_by_this_contract": False,
        "cloudflare_change_authorized_by_this_contract": False,
    }
    if dict(connector) != expected_connector:
        raise CurrentProductionRemediationError("connector target is not exact")
    _path(connector["path"], "connector path")

    expected_boundary = {
        "host_runtime_or_configuration_changed": False,
        "image_loaded_or_retagged": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "runtime_secret_or_tunnel_credential_read": False,
        "external_network_accessed": False,
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != expected_boundary:
        raise CurrentProductionRemediationError("source boundary is not exact")
    if contract.get("claim_boundary") != "REDACTED_CURRENT_PRODUCTION_REMEDIATION_CONTRACT_ONLY_NOT_HOST_REMEDIATION_CORE_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionRemediationError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRemediationError("rollback boundary is not exact")


def validate_baseline(baseline: Mapping[str, Any]) -> None:
    required = {"schema_version", "observation_type", "observed_on", "prior_image", "core_units", "connector_config"}
    if set(baseline) != required:
        raise CurrentProductionRemediationError("baseline field set is not exact")
    if baseline.get("schema_version") != "1.0.0":
        raise CurrentProductionRemediationError("baseline schema is not supported")
    if baseline.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CONTROL_PLANE_METADATA":
        raise CurrentProductionRemediationError("baseline observation type is not exact")
    try:
        date.fromisoformat(str(baseline.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionRemediationError("baseline observation date is invalid") from exc
    if _object(baseline.get("prior_image"), "baseline prior image") != {
        "host_inventory": "ABSENT",
        "private_source_catalog": "UNKNOWN_PRIVATE_CATALOG_NOT_READABLE",
    }:
        raise CurrentProductionRemediationError("baseline prior image state is not exact")
    units = _object(baseline.get("core_units"), "baseline core units")
    expected_unit = {"load_state": "not-found", "active_state": "inactive", "unit_file_state": ""}
    if dict(units) != {"abd.service": expected_unit, "abd-cloudflared.service": expected_unit}:
        raise CurrentProductionRemediationError("baseline core unit states are not exact")
    if _object(baseline.get("connector_config"), "baseline connector config") != {
        "kind": "missing",
        "hostname_configured": "UNKNOWN",
    }:
        raise CurrentProductionRemediationError("baseline connector state is not exact")


def evaluate_baseline(contract: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_baseline(baseline)
    targets = _object(contract["remediation_targets"], "remediation targets")
    rollback_asset = _object(targets["rollback_asset"], "rollback asset")
    core_units = _object(targets["core_units"], "core units")
    connector = _object(targets["connector_config"], "connector configuration")
    prior_image = _object(baseline["prior_image"], "baseline prior image")
    observed_units = _object(baseline["core_units"], "baseline core units")
    observed_connector = _object(baseline["connector_config"], "baseline connector config")
    checks = [
        {"id": "PRIOR_IMAGE_ABSENT_RECORDED", "passed": prior_image["host_inventory"] == rollback_asset["current_host_state"]},
        {"id": "PRIVATE_ROLLBACK_SOURCE_REMAINS_UNVERIFIED", "passed": prior_image["private_source_catalog"] == rollback_asset["private_source_state"]},
        {
            "id": "CORE_UNITS_REMAIN_NOT_FOUND_AND_INACTIVE",
            "passed": all(
                unit == {"load_state": "not-found", "active_state": "inactive", "unit_file_state": ""}
                for unit in observed_units.values()
            )
            and list(observed_units) == list(core_units["service_names"]),
        },
        {"id": "CONNECTOR_CONFIG_REMAINS_MISSING", "passed": observed_connector["kind"] == connector["current_safe_state"].lower()},
        {"id": "CONNECTOR_HOSTNAME_REMAINS_UNKNOWN", "passed": observed_connector["hostname_configured"] == "UNKNOWN"},
    ]
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if not failures else FAIL_STATUS,
        "decision": "FUTURE_HOST_MUTATION_REQUIRES_SEPARATE_EXECUTION_CONTRACT" if not failures else "REMEDIATION_BASELINE_DIVERGED_REQUIRES_NEW_READ_ONLY_INVENTORY",
        "contract_valid": not failures,
        "execution_authorized": False,
        "checks": checks,
        "failure_codes": failures,
        "unresolved_prerequisites": [
            "PRIVATE_RECOVERABLE_OCI_ARCHIVE_VERIFIED",
            "SEPARATE_CORE_CAPACITY_AND_EXECUTION_CONTRACT",
            "SEPARATE_CONNECTOR_NONSECRET_CONFIG_AND_SECRET_BINDING_CONTRACT",
        ]
        if not failures
        else [],
    }


def build_receipt(contract: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_baseline(contract, baseline)
    observed_units = _object(baseline["core_units"], "baseline core units")
    connector = _object(baseline["connector_config"], "baseline connector config")
    prior_image = _object(baseline["prior_image"], "baseline prior image")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": baseline["observed_on"],
        "contract_valid": result["contract_valid"],
        "execution_authorized": result["execution_authorized"],
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "unresolved_prerequisites": result["unresolved_prerequisites"],
        "observed": {
            "prior_image_present": prior_image["host_inventory"] != "ABSENT",
            "private_rollback_source_verified": prior_image["private_source_catalog"] == "VERIFIED",
            "core_units_state": "NOT_FOUND_AND_INACTIVE"
            if all(unit["load_state"] == "not-found" and unit["active_state"] == "inactive" for unit in observed_units.values())
            else "DIVERGED",
            "connector_config_state": str(connector["kind"]).upper(),
            "connector_hostname_state": connector["hostname_configured"],
        },
        "source_boundary": dict(_object(contract["source_boundary"], "source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "REMEDIATION_CONTRACT_INPUT_FAILED_CLOSED",
        "contract_valid": False,
        "execution_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_REMEDIATION_CONTRACT_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_baseline(args.baseline))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRemediationError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
