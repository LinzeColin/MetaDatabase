#!/usr/bin/env python3
"""Evaluate one redacted frozen ABD configuration semantic preflight."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT"
ALLOWED_ACTIVATION_GATES = {
    "READY_FOR_EXPLICIT_P03_ACTIVATION",
    "BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED",
}
SAFE_FAILURE_CATEGORIES = {
    "FROZEN_CHECK_FAILED_REDACTED",
    "FROZEN_CHECK_OUTPUT_MALFORMED_REDACTED",
    "FROZEN_CHECK_TIMEOUT_REDACTED",
    "FROZEN_CHECK_PRECONDITION_FAILED_REDACTED",
    "FROZEN_CHECK_TRANSPORT_UNAVAILABLE_REDACTED",
}


class CurrentProductionCoreConfigSemanticPreflightError(ValueError):
    """Raised when a preflight contract or redacted fact payload is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreConfigSemanticPreflightError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreConfigSemanticPreflightError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreConfigSemanticPreflightError) as exc:
        raise CurrentProductionCoreConfigSemanticPreflightError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "core config semantic preflight contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted core config semantic preflight facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionCoreConfigSemanticPreflightError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreConfigSemanticPreflightError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-CONFIG-SEMANTIC-PREFLIGHT-001":
        raise CurrentProductionCoreConfigSemanticPreflightError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreConfigSemanticPreflightError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT_READ_ONLY":
        raise CurrentProductionCoreConfigSemanticPreflightError("preflight must remain read-only")
    expected = {
        "current_target": "BLUE_SHADOW_RELEASE",
        "config_file_kind": "regular",
        "rebuild_file_kind": "regular",
        "allowed_activation_gates": [
            "READY_FOR_EXPLICIT_P03_ACTIVATION",
            "BLOCKED_RUNTIME_PREREQUISITES_NOT_VERIFIED",
        ],
        "success_frozen_check": {
            "invoked": True,
            "status": "PASS",
            "secret_values_read": False,
            "error_category": "NONE",
        },
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionCoreConfigSemanticPreflightError("preflight expectations are not exact")
    boundary = {
        "live_host_nonsecret_metadata_read": True,
        "privileged_frozen_config_check_permitted": True,
        "config_contents_read_only_by_frozen_check": True,
        "config_contents_emitted_or_persisted": False,
        "runtime_env_contents_read": False,
        "runtime_secret_contents_read": False,
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
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionCoreConfigSemanticPreflightError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CONFIG_SEMANTIC_PREFLIGHT_ONLY_NOT_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionCoreConfigSemanticPreflightError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreConfigSemanticPreflightError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {"schema_version", "observation_type", "observed_on", "current_target", "config_file_kind", "rebuild_file_kind", "frozen_check"}
    if set(facts) != required:
        raise CurrentProductionCoreConfigSemanticPreflightError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT":
        raise CurrentProductionCoreConfigSemanticPreflightError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCoreConfigSemanticPreflightError("facts observation date is invalid") from exc
    if facts.get("current_target") not in {"BLUE_SHADOW_RELEASE", "OTHER_MANAGED_RELEASE", "UNKNOWN"}:
        raise CurrentProductionCoreConfigSemanticPreflightError("current target is invalid")
    for field in ("config_file_kind", "rebuild_file_kind"):
        if facts.get(field) not in {"regular", "symlink", "directory", "other", "missing", "unknown_access"}:
            raise CurrentProductionCoreConfigSemanticPreflightError("%s is invalid" % field)
    frozen_check = _object(facts.get("frozen_check"), "frozen check")
    if set(frozen_check) != {"invoked", "status", "activation_gate", "secret_values_read", "error_category"}:
        raise CurrentProductionCoreConfigSemanticPreflightError("frozen check field set is not exact")
    status = frozen_check.get("status")
    if status == "PASS":
        if frozen_check.get("invoked") is not True or frozen_check.get("activation_gate") not in ALLOWED_ACTIVATION_GATES or frozen_check.get("secret_values_read") is not False or frozen_check.get("error_category") != "NONE":
            raise CurrentProductionCoreConfigSemanticPreflightError("successful frozen check is invalid")
        return
    if status == "FAIL":
        allowed_categories = SAFE_FAILURE_CATEGORIES - {"FROZEN_CHECK_PRECONDITION_FAILED_REDACTED", "FROZEN_CHECK_TRANSPORT_UNAVAILABLE_REDACTED"}
        if frozen_check.get("invoked") is not True or frozen_check.get("activation_gate") != "NOT_EMITTED" or frozen_check.get("secret_values_read") != "NOT_EMITTED" or frozen_check.get("error_category") not in allowed_categories:
            raise CurrentProductionCoreConfigSemanticPreflightError("failed frozen check is invalid")
        return
    if status == "NOT_RUN":
        if frozen_check.get("invoked") is not False or frozen_check.get("activation_gate") != "NOT_EMITTED" or frozen_check.get("secret_values_read") != "NOT_EMITTED" or frozen_check.get("error_category") not in {"FROZEN_CHECK_PRECONDITION_FAILED_REDACTED", "FROZEN_CHECK_TRANSPORT_UNAVAILABLE_REDACTED"}:
            raise CurrentProductionCoreConfigSemanticPreflightError("non-run frozen check is invalid")
        return
    raise CurrentProductionCoreConfigSemanticPreflightError("frozen check status is invalid")


def evaluate_preflight(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    expected = _object(contract["expected"], "expected")
    frozen_check = _object(facts["frozen_check"], "frozen check")
    checks = [
        {"id": "CURRENT_TARGET_IS_BLUE_SHADOW_RELEASE", "passed": facts["current_target"] == expected["current_target"]},
        {"id": "CONFIG_FILE_REGULAR", "passed": facts["config_file_kind"] == expected["config_file_kind"]},
        {"id": "CURRENT_RELEASE_REBUILD_FILE_REGULAR", "passed": facts["rebuild_file_kind"] == expected["rebuild_file_kind"]},
        {"id": "FROZEN_CHECK_INVOKED", "passed": frozen_check["invoked"] is True},
        {"id": "FROZEN_CHECK_PASSED", "passed": frozen_check["status"] == expected["success_frozen_check"]["status"]},
        {"id": "FROZEN_CHECK_ACTIVATION_GATE_RECOGNIZED", "passed": frozen_check["activation_gate"] in ALLOWED_ACTIVATION_GATES},
        {"id": "FROZEN_CHECK_CONFIRMS_NO_SECRET_VALUES_READ", "passed": frozen_check["secret_values_read"] is False},
        {"id": "FROZEN_CHECK_OUTPUT_REDACTED", "passed": frozen_check["error_category"] == "NONE" or frozen_check["error_category"] in SAFE_FAILURE_CATEGORIES},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    passed = not failure_codes
    return {
        "status": PASS_STATUS if passed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_CONFIG_SEMANTIC_VALID_SEPARATE_CORE_EXECUTION_CONTRACT_REQUIRED" if passed else "CURRENT_PRODUCTION_CONFIG_SEMANTIC_INPUT_INCOMPLETE_OR_INVALID_FAIL_CLOSED",
        "config_semantic_valid": passed,
        "core_start_authorized": False,
        "activation_gate": frozen_check["activation_gate"] if frozen_check["activation_gate"] in ALLOWED_ACTIVATION_GATES else "UNKNOWN",
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_preflight(contract, facts)
    checks = result["checks"]
    if not isinstance(result["config_semantic_valid"], bool) or result["core_start_authorized"] is not False:
        raise CurrentProductionCoreConfigSemanticPreflightError("preflight authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCoreConfigSemanticPreflightError("preflight checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "config_semantic_valid": result["config_semantic_valid"],
        "core_start_authorized": False,
        "activation_gate": result["activation_gate"],
        "checks": list(checks),
        "failure_codes": list(result["failure_codes"]),
        "source_boundary": dict(_object(contract["source_boundary"], "source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_CONFIG_SEMANTIC_PREFLIGHT_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "config_semantic_valid": False,
        "core_start_authorized": False,
        "activation_gate": "UNKNOWN",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CONFIG_SEMANTIC_PREFLIGHT_INPUT_FAILED"],
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreConfigSemanticPreflightError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
