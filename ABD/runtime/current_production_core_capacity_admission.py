#!/usr/bin/env python3
"""Evaluate redacted current-production ABD core capacity facts without starting it."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from host_capacity_gate import (
    EXPECTED_SWAP_ENTRIES,
    MIN_MEMORY_KIB,
    MIN_PHYSICAL_DISK_BYTES,
    MIN_VCPU,
    HostCapacityGateError,
    evaluate_host_facts,
)


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION"


class CurrentProductionCoreCapacityAdmissionError(ValueError):
    """Raised when a current-production core capacity admission input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreCapacityAdmissionError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreCapacityAdmissionError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "core capacity admission contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreCapacityAdmissionError) as exc:
        raise CurrentProductionCoreCapacityAdmissionError("core capacity admission contract is unreadable") from exc


def load_facts(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "redacted host capacity facts")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreCapacityAdmissionError) as exc:
        raise CurrentProductionCoreCapacityAdmissionError("redacted host capacity facts are unreadable") from exc


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
        raise CurrentProductionCoreCapacityAdmissionError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreCapacityAdmissionError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-CAPACITY-ADMISSION-001":
        raise CurrentProductionCoreCapacityAdmissionError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreCapacityAdmissionError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION_READ_ONLY":
        raise CurrentProductionCoreCapacityAdmissionError("capacity admission must remain read-only")
    if _object(contract.get("expected"), "capacity admission expected") != {
        "source_guard_contract_id": "ABD-POST-FREEZE-HOST-BUNDLE",
        "source_guard_script": "runtime/host_capacity_gate.py",
        "minimum_vcpu": MIN_VCPU,
        "minimum_memory_kib": MIN_MEMORY_KIB,
        "minimum_physical_disk_bytes": MIN_PHYSICAL_DISK_BYTES,
        "required_swap_entries": EXPECTED_SWAP_ENTRIES,
    }:
        raise CurrentProductionCoreCapacityAdmissionError("capacity admission thresholds are not exact")
    expected_boundary = {
        "live_host_capacity_metadata_read": True,
        "remote_script_written": False,
        "host_runtime_or_configuration_changed": False,
        "image_loaded_or_retagged": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "runtime_secret_or_tunnel_credential_read": False,
        "external_network_scope": "AUTHORIZED_SSH_HOST_METADATA_ONLY",
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != expected_boundary:
        raise CurrentProductionCoreCapacityAdmissionError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION_ONLY_NOT_CORE_START_SERVICE_DEPLOYMENT_OR_PUBLIC_RELEASE":
        raise CurrentProductionCoreCapacityAdmissionError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreCapacityAdmissionError("rollback boundary is not exact")


def evaluate_admission(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    try:
        gate = evaluate_host_facts(facts)
    except HostCapacityGateError as exc:
        raise CurrentProductionCoreCapacityAdmissionError("host capacity facts are invalid") from exc
    passed = gate["status"] == "PASS" and gate["activation_allowed"] is True
    return {
        "status": PASS_STATUS if passed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION_PASS_SEPARATE_EXECUTION_CONTRACT_REQUIRED"
        if passed
        else "CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION_FAIL_CLOSED",
        "capacity_admitted": passed,
        "core_start_authorized": False,
        "checks": gate["checks"],
        "failure_codes": gate["failure_codes"],
    }


def build_receipt(contract: Mapping[str, Any], result: Mapping[str, Any], observed_on: str) -> dict[str, Any]:
    validate_contract(contract)
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError as exc:
        raise CurrentProductionCoreCapacityAdmissionError("observed date is invalid") from exc
    required = {"status", "decision", "capacity_admitted", "core_start_authorized", "checks", "failure_codes"}
    if set(result) != required:
        raise CurrentProductionCoreCapacityAdmissionError("admission result field set is not exact")
    if result["status"] not in {PASS_STATUS, FAIL_STATUS}:
        raise CurrentProductionCoreCapacityAdmissionError("admission result status is invalid")
    if not isinstance(result["capacity_admitted"], bool) or result["core_start_authorized"] is not False:
        raise CurrentProductionCoreCapacityAdmissionError("admission result authorization is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) for check in checks):
        raise CurrentProductionCoreCapacityAdmissionError("admission checks are invalid")
    redacted_checks = [
        {"id": check.get("id"), "passed": check.get("passed")}
        for check in checks
        if set(check) in ({"id", "passed", "actual", "minimum"}, {"id", "passed", "actual", "expected"})
    ]
    if len(redacted_checks) != 4:
        raise CurrentProductionCoreCapacityAdmissionError("admission checks are not exact")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": observed_date,
        "capacity_admitted": result["capacity_admitted"],
        "core_start_authorized": False,
        "checks": redacted_checks,
        "failure_codes": list(result["failure_codes"]),
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
        "decision": "CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION_INPUT_FAILED_CLOSED",
        "observed_on": observed_date,
        "capacity_admitted": False,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CORE_CAPACITY_ADMISSION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        result = evaluate_admission(contract, load_facts(args.facts))
        receipt = build_receipt(contract, result, args.observed_on)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreCapacityAdmissionError, HostCapacityGateError, ValueError) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
