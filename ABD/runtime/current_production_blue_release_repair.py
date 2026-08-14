#!/usr/bin/env python3
"""Evaluate redacted facts for an append-only current-blue release repair."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR"
INFRA_SOURCE_PATHS = [
    "infra/config.schema.json",
    "infra/rebuild.sh",
]
BOOTSTRAP_INITIALIZER_SOURCE = "runtime/current_production_blue_release_acceptance_init.py"
ACCEPTANCE_MODULE_PATHS = [
    "abd_acceptance/infrastructure_iac.py",
    "abd_acceptance/canonical_facts.py",
    "abd_acceptance/legacy_receipt_compatibility.py",
    "abd_acceptance/stage3_delivery.py",
]
ACCEPTANCE_PACKAGE_PYTHON_FILE_COUNT = 5
ACCEPTANCE_PACKAGE_NONPYTHON_FILE_COUNT = 0
SOURCE_BUNDLE_PROFILE = {
    "infra_paths": INFRA_SOURCE_PATHS,
    "bootstrap_initializer_source": BOOTSTRAP_INITIALIZER_SOURCE,
    "acceptance_module_paths": ACCEPTANCE_MODULE_PATHS,
    "acceptance_package_python_file_count": ACCEPTANCE_PACKAGE_PYTHON_FILE_COUNT,
    "acceptance_package_nonpython_file_count": ACCEPTANCE_PACKAGE_NONPYTHON_FILE_COUNT,
}


class CurrentProductionBlueReleaseRepairError(ValueError):
    """Raised when release-repair contract inputs are malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionBlueReleaseRepairError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionBlueReleaseRepairError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _date(value: object, name: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise CurrentProductionBlueReleaseRepairError("%s is invalid" % name) from exc


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionBlueReleaseRepairError) as exc:
        raise CurrentProductionBlueReleaseRepairError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "blue release repair contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "blue release repair facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionBlueReleaseRepairError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionBlueReleaseRepairError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-BLUE-RELEASE-REPAIR-001":
        raise CurrentProductionBlueReleaseRepairError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionBlueReleaseRepairError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_NO_CORE_ACTIVATION":
        raise CurrentProductionBlueReleaseRepairError("repair status is not exact")
    expected = {
        "current_target": "BLUE_SHADOW_RELEASE",
        "shadow_blue_project_present": True,
        "core_unit": {"load_state": "not-found", "active_state": "inactive"},
        "existing_files": {"compose_file_kind": "regular"},
        "missing_before_repair": {
            "config_schema_file_kind": "missing",
            "rebuild_file_kind": "missing",
            "abd_acceptance_directory_kind": "missing",
        },
        "host_python_major_minor": "3.12",
        "host_python_jsonschema_import": "present",
        "source_bundle_profile": SOURCE_BUNDLE_PROFILE,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionBlueReleaseRepairError("repair expectations are not exact")
    boundary = {
        "local_nonsecret_source_bundle_read": True,
        "live_host_nonsecret_metadata_read": True,
        "config_contents_read": False,
        "runtime_env_contents_read": False,
        "runtime_secret_contents_read": False,
        "release_compose_contents_changed": False,
        "release_nonsecret_files_added": True,
        "current_symlink_changed": False,
        "shadow_container_changed": False,
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
        raise CurrentProductionBlueReleaseRepairError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_BLUE_RELEASE_NONSECRET_REPAIR_ONLY_NOT_CONFIG_VALIDATION_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionBlueReleaseRepairError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "failure_cleanup": "REMOVE_ONLY_EXACT_FILES_CREATED_BY_THIS_RUN",
        "successful_repair_rollback": "SEPARATE_CONTRACT_REQUIRED",
        "current_symlink_preserved": True,
        "shadow_runtime_preserved": True,
    }:
        raise CurrentProductionBlueReleaseRepairError("rollback boundary is not exact")


def source_bundle_paths(contract: Mapping[str, Any]) -> list[str]:
    validate_contract(contract)
    return list(INFRA_SOURCE_PATHS)


def _validate_unit(value: object, name: str) -> None:
    unit = _object(value, name)
    if set(unit) != {"load_state", "active_state"} or any(not isinstance(item, str) for item in unit.values()):
        raise CurrentProductionBlueReleaseRepairError("%s is invalid" % name)


def validate_preflight_facts(facts: Mapping[str, Any]) -> None:
    required = {"schema_version", "observation_type", "observed_on", "current_target", "shadow_blue_project_present", "core_unit", "existing_files", "missing_before_repair", "host_python_major_minor", "host_python_jsonschema_import"}
    if set(facts) != required:
        raise CurrentProductionBlueReleaseRepairError("preflight field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_PREFLIGHT":
        raise CurrentProductionBlueReleaseRepairError("preflight identity is not exact")
    _date(facts.get("observed_on"), "preflight observation date")
    if facts.get("current_target") not in {"BLUE_SHADOW_RELEASE", "OTHER_MANAGED_RELEASE", "UNKNOWN"}:
        raise CurrentProductionBlueReleaseRepairError("preflight current target is invalid")
    if not isinstance(facts.get("shadow_blue_project_present"), bool):
        raise CurrentProductionBlueReleaseRepairError("preflight shadow state is invalid")
    _validate_unit(facts.get("core_unit"), "preflight core unit")
    existing = _object(facts.get("existing_files"), "existing files")
    missing = _object(facts.get("missing_before_repair"), "missing before repair")
    if set(existing) != {"compose_file_kind"} or any(not isinstance(item, str) for item in existing.values()):
        raise CurrentProductionBlueReleaseRepairError("preflight existing files are invalid")
    if set(missing) != {"config_schema_file_kind", "rebuild_file_kind", "abd_acceptance_directory_kind"} or any(not isinstance(item, str) for item in missing.values()):
        raise CurrentProductionBlueReleaseRepairError("preflight missing files are invalid")
    if facts.get("host_python_major_minor") not in {"3.12", "unknown"}:
        raise CurrentProductionBlueReleaseRepairError("preflight Python version is invalid")
    if facts.get("host_python_jsonschema_import") not in {"present", "missing", "unknown"}:
        raise CurrentProductionBlueReleaseRepairError("preflight Python dependency state is invalid")


def validate_completion_facts(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> None:
    required = {"schema_version", "observation_type", "observed_on", "current_target", "shadow_blue_project_present", "core_unit", "compose_file_kind", "installed_infra_file_kinds", "installed_acceptance_package", "python_import"}
    if set(facts) != required:
        raise CurrentProductionBlueReleaseRepairError("completion field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_COMPLETION":
        raise CurrentProductionBlueReleaseRepairError("completion identity is not exact")
    _date(facts.get("observed_on"), "completion observation date")
    if facts.get("current_target") not in {"BLUE_SHADOW_RELEASE", "OTHER_MANAGED_RELEASE", "UNKNOWN"}:
        raise CurrentProductionBlueReleaseRepairError("completion current target is invalid")
    if not isinstance(facts.get("shadow_blue_project_present"), bool):
        raise CurrentProductionBlueReleaseRepairError("completion shadow state is invalid")
    _validate_unit(facts.get("core_unit"), "completion core unit")
    if facts.get("compose_file_kind") not in {"regular", "missing", "other", "unknown_access"}:
        raise CurrentProductionBlueReleaseRepairError("completion compose state is invalid")
    installed = _object(facts.get("installed_infra_file_kinds"), "installed infra file kinds")
    if set(installed) != set(source_bundle_paths(contract)) or any(value not in {"regular", "missing", "other", "unknown_access"} for value in installed.values()):
        raise CurrentProductionBlueReleaseRepairError("completion infra bundle state is invalid")
    package = _object(facts.get("installed_acceptance_package"), "installed acceptance package")
    if set(package) != {"python_file_count", "nonpython_file_count", "all_python_regular"} or not isinstance(package.get("python_file_count"), int) or not isinstance(package.get("nonpython_file_count"), int) or not isinstance(package.get("all_python_regular"), bool):
        raise CurrentProductionBlueReleaseRepairError("completion acceptance package state is invalid")
    if facts.get("python_import") not in {"PASS", "FAIL", "UNKNOWN"}:
        raise CurrentProductionBlueReleaseRepairError("completion Python import state is invalid")


def evaluate_preflight(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_preflight_facts(facts)
    expected = _object(contract["expected"], "expected")
    checks = [
        {"id": "CURRENT_TARGET_IS_BLUE_SHADOW_RELEASE", "passed": facts["current_target"] == expected["current_target"]},
        {"id": "BLUE_SHADOW_PROJECT_PRESENT", "passed": facts["shadow_blue_project_present"] is expected["shadow_blue_project_present"]},
        {"id": "CORE_UNIT_NOT_FOUND_AND_INACTIVE", "passed": _object(facts["core_unit"], "core unit") == _object(expected["core_unit"], "expected core unit")},
        {"id": "CURRENT_COMPOSE_FILE_REGULAR", "passed": _object(facts["existing_files"], "existing files") == _object(expected["existing_files"], "expected existing files")},
        {"id": "REPAIR_TARGET_FILES_ALL_MISSING", "passed": _object(facts["missing_before_repair"], "missing before repair") == _object(expected["missing_before_repair"], "expected missing before repair")},
        {"id": "HOST_PYTHON_312", "passed": facts["host_python_major_minor"] == expected["host_python_major_minor"]},
        {"id": "HOST_JSONSCHEMA_IMPORT_PRESENT", "passed": facts["host_python_jsonschema_import"] == expected["host_python_jsonschema_import"]},
    ]
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    return {"status": PASS_STATUS if not failures else FAIL_STATUS, "repair_authorized": not failures, "core_start_authorized": False, "checks": checks, "failure_codes": failures}


def evaluate_repair(contract: Mapping[str, Any], preflight: Mapping[str, Any], completion: Mapping[str, Any]) -> dict[str, Any]:
    preflight_result = evaluate_preflight(contract, preflight)
    validate_completion_facts(contract, completion)
    expected = _object(contract["expected"], "expected")
    installed = _object(completion["installed_infra_file_kinds"], "installed infra file kinds")
    package = _object(completion["installed_acceptance_package"], "installed acceptance package")
    profile = _object(expected["source_bundle_profile"], "source bundle profile")
    completion_checks = [
        {"id": "CURRENT_TARGET_REMAINS_BLUE_SHADOW_RELEASE", "passed": completion["current_target"] == expected["current_target"]},
        {"id": "BLUE_SHADOW_PROJECT_REMAINS_PRESENT", "passed": completion["shadow_blue_project_present"] is expected["shadow_blue_project_present"]},
        {"id": "CORE_UNIT_REMAINS_NOT_FOUND_AND_INACTIVE", "passed": _object(completion["core_unit"], "completion core unit") == _object(expected["core_unit"], "expected core unit")},
        {"id": "COMPOSE_FILE_REMAINS_REGULAR", "passed": completion["compose_file_kind"] == "regular"},
        {"id": "SOURCE_BUNDLE_FILES_ALL_REGULAR", "passed": all(kind == "regular" for kind in installed.values())},
        {"id": "FULL_ACCEPTANCE_PACKAGE_PRESENT", "passed": package == {"python_file_count": profile["acceptance_package_python_file_count"], "nonpython_file_count": profile["acceptance_package_nonpython_file_count"], "all_python_regular": True}},
        {"id": "STAGED_MODULE_IMPORT_PASS", "passed": completion["python_import"] == "PASS"},
    ]
    checks = [*preflight_result["checks"], *completion_checks]
    failures = [str(check["id"]) for check in checks if not check["passed"]]
    repaired = preflight_result["repair_authorized"] is True and not failures
    return {
        "status": PASS_STATUS if repaired else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_BLUE_RELEASE_REPAIRED_SEPARATE_CONFIG_CHECK_AND_UNIT_EXECUTION_CONTRACT_REQUIRED" if repaired else "CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_FAILED_CLOSED",
        "release_repaired": repaired,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failures,
    }


def build_receipt(contract: Mapping[str, Any], preflight: Mapping[str, Any], completion: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_repair(contract, preflight, completion)
    checks = result["checks"]
    if not isinstance(result["release_repaired"], bool) or result["core_start_authorized"] is not False:
        raise CurrentProductionBlueReleaseRepairError("repair authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionBlueReleaseRepairError("repair checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": completion["observed_on"],
        "release_repaired": result["release_repaired"],
        "core_start_authorized": False,
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
        "decision": "CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_INPUT_FAILED_CLOSED",
        "release_repaired": False,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--completion", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.preflight), load_facts(args.completion))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionBlueReleaseRepairError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
