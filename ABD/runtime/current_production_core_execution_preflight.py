#!/usr/bin/env python3
"""Fail closed on redacted prerequisites for a separate ABD core execution contract."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT"


class CurrentProductionCoreExecutionPreflightError(ValueError):
    """Raised when a preflight contract or redacted host facts are malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreExecutionPreflightError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreExecutionPreflightError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "core execution preflight contract")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreExecutionPreflightError) as exc:
        raise CurrentProductionCoreExecutionPreflightError("core execution preflight contract is unreadable") from exc


def load_facts(path: Path) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), "redacted core execution preflight facts")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreExecutionPreflightError) as exc:
        raise CurrentProductionCoreExecutionPreflightError("redacted core execution preflight facts are unreadable") from exc


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
        raise CurrentProductionCoreExecutionPreflightError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreExecutionPreflightError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-PREFLIGHT-001":
        raise CurrentProductionCoreExecutionPreflightError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreExecutionPreflightError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_READ_ONLY":
        raise CurrentProductionCoreExecutionPreflightError("preflight must remain read-only")
    expected = _object(contract.get("expected"), "preflight expected")
    required_runtime_metadata = {
        "config_file_kind": "regular",
        "runtime_env_file_kind": "regular",
        "runtime_secret_file_kind": "regular",
        "current_release_link_kind": "symlink",
        "current_release_target_managed": True,
        "current_compose_file_kind": "regular",
        "current_rebuild_file_kind": "regular",
        "core_capacity_dropin_file_kind": "regular",
    }
    expected_values = {
        "candidate_image_present": True,
        "required_runtime_metadata": required_runtime_metadata,
        "core_unit": {"load_state": "not-found", "active_state": "inactive"},
        "connector_unit": {"load_state": "not-found", "active_state": "inactive"},
    }
    if dict(expected) != expected_values:
        raise CurrentProductionCoreExecutionPreflightError("preflight expectations are not exact")
    expected_boundary = {
        "live_host_nonsecret_metadata_read": True,
        "privileged_metadata_read": True,
        "config_contents_read": False,
        "runtime_env_contents_read": False,
        "runtime_secret_contents_read": False,
        "release_file_contents_read": False,
        "remote_script_written": False,
        "host_runtime_or_configuration_changed": False,
        "image_loaded_or_retagged": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != expected_boundary:
        raise CurrentProductionCoreExecutionPreflightError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_ONLY_NOT_RELEASE_REPAIR_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionCoreExecutionPreflightError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreExecutionPreflightError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "privileged_metadata_read",
        "runtime_prerequisites",
        "core_unit",
        "connector_unit",
    }
    if set(facts) != required:
        raise CurrentProductionCoreExecutionPreflightError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreExecutionPreflightError("facts schema is not supported")
    if facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT":
        raise CurrentProductionCoreExecutionPreflightError("facts observation type is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCoreExecutionPreflightError("facts observation date is invalid") from exc
    if not isinstance(facts.get("privileged_metadata_read"), bool):
        raise CurrentProductionCoreExecutionPreflightError("privileged metadata state is invalid")
    runtime_prerequisites = _object(facts.get("runtime_prerequisites"), "runtime prerequisites")
    expected_runtime_fields = {
        "config_file_kind",
        "runtime_env_file_kind",
        "runtime_secret_file_kind",
        "current_release_link_kind",
        "current_release_target_managed",
        "current_compose_file_kind",
        "current_rebuild_file_kind",
        "core_capacity_dropin_file_kind",
        "candidate_image_present",
    }
    if set(runtime_prerequisites) != expected_runtime_fields:
        raise CurrentProductionCoreExecutionPreflightError("runtime prerequisite field set is not exact")
    allowed_kinds = {"regular", "symlink", "directory", "other", "missing", "unknown_access"}
    for key in (
        "config_file_kind",
        "runtime_env_file_kind",
        "runtime_secret_file_kind",
        "current_release_link_kind",
        "current_compose_file_kind",
        "current_rebuild_file_kind",
        "core_capacity_dropin_file_kind",
    ):
        if runtime_prerequisites.get(key) not in allowed_kinds:
            raise CurrentProductionCoreExecutionPreflightError("runtime prerequisite kind is invalid")
    for key in ("current_release_target_managed", "candidate_image_present"):
        if not isinstance(runtime_prerequisites.get(key), bool):
            raise CurrentProductionCoreExecutionPreflightError("runtime prerequisite boolean is invalid")
    for name in ("core_unit", "connector_unit"):
        if _object(facts.get(name), name) != {"load_state": str(_object(facts.get(name), name).get("load_state")), "active_state": str(_object(facts.get(name), name).get("active_state"))}:
            raise CurrentProductionCoreExecutionPreflightError("unit facts are invalid")


def evaluate_preflight(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    expected = _object(contract["expected"], "preflight expected")
    observed_runtime = _object(facts["runtime_prerequisites"], "runtime prerequisites")
    required_runtime = _object(expected["required_runtime_metadata"], "required runtime metadata")
    checks = [
        {"id": "PRIVILEGED_METADATA_READ", "passed": facts["privileged_metadata_read"] is True},
        {"id": "CONFIG_FILE_REGULAR", "passed": observed_runtime["config_file_kind"] == required_runtime["config_file_kind"]},
        {"id": "RUNTIME_ENV_FILE_REGULAR", "passed": observed_runtime["runtime_env_file_kind"] == required_runtime["runtime_env_file_kind"]},
        {"id": "RUNTIME_SECRET_FILE_PRESENT", "passed": observed_runtime["runtime_secret_file_kind"] == required_runtime["runtime_secret_file_kind"]},
        {"id": "CURRENT_RELEASE_LINK_MANAGED", "passed": observed_runtime["current_release_link_kind"] == required_runtime["current_release_link_kind"] and observed_runtime["current_release_target_managed"] is required_runtime["current_release_target_managed"]},
        {"id": "CURRENT_RELEASE_COMPOSE_FILE_REGULAR", "passed": observed_runtime["current_compose_file_kind"] == required_runtime["current_compose_file_kind"]},
        {"id": "CURRENT_RELEASE_REBUILD_FILE_REGULAR", "passed": observed_runtime["current_rebuild_file_kind"] == required_runtime["current_rebuild_file_kind"]},
        {"id": "CORE_CAPACITY_DROPIN_FILE_REGULAR", "passed": observed_runtime["core_capacity_dropin_file_kind"] == required_runtime["core_capacity_dropin_file_kind"]},
        {"id": "CURRENT_CANDIDATE_IMAGE_PRESENT", "passed": observed_runtime["candidate_image_present"] is expected["candidate_image_present"]},
        {"id": "CORE_UNIT_NOT_FOUND_AND_INACTIVE", "passed": _object(facts["core_unit"], "core unit") == _object(expected["core_unit"], "expected core unit")},
        {"id": "CONNECTOR_UNIT_NOT_FOUND_AND_INACTIVE", "passed": _object(facts["connector_unit"], "connector unit") == _object(expected["connector_unit"], "expected connector unit")},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    passed = not failure_codes
    return {
        "status": PASS_STATUS if passed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_INPUT_READY_SEPARATE_MUTATING_EXECUTION_CONTRACT_REQUIRED"
        if passed
        else "CURRENT_PRODUCTION_CORE_EXECUTION_INPUT_INCOMPLETE_FAIL_CLOSED",
        "input_ready": passed,
        "execution_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_preflight(contract, facts)
    required = {"status", "decision", "input_ready", "execution_authorized", "checks", "failure_codes"}
    if set(result) != required:
        raise CurrentProductionCoreExecutionPreflightError("preflight result field set is not exact")
    if result["status"] not in {PASS_STATUS, FAIL_STATUS}:
        raise CurrentProductionCoreExecutionPreflightError("preflight result status is invalid")
    if not isinstance(result["input_ready"], bool) or result["execution_authorized"] is not False:
        raise CurrentProductionCoreExecutionPreflightError("preflight authorization state is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCoreExecutionPreflightError("preflight checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "input_ready": result["input_ready"],
        "execution_authorized": False,
        "checks": list(checks),
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
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_INPUT_FAILED_CLOSED",
        "observed_on": observed_date,
        "input_ready": False,
        "execution_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.facts))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreExecutionPreflightError, ValueError) as exc:
        receipt = _failure_receipt(exc, "INVALID")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
