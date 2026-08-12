#!/usr/bin/env python3
"""Attest current redacted prerequisite receipts through the private data client only."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

from current_production_core_activation_prerequisite_static_evidence_classification_diagnostic import (
    PREREQUISITES,
    Prerequisite,
    _valid_redacted_receipt,
)


PASS_STATUS = "PASS_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION"
PRIVATE_AREA = "Private-MetaDatabase"
PRIVATE_DOMAIN = "ABD"
MAX_PRIVATE_RECEIPT_BYTES = 16384
MAX_PRIVATE_DATABASE_READ_REQUESTS = 6
MANIFEST_RECORD_FIELDS = frozenset({"sha256", "original_name", "size_bytes", "domain", "batch", "object_path", "ingested_at"})
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
MANIFEST_STATES = {"OBSERVED_IN_MEMORY", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}
PREREQUISITE_STATES = {
    "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
    "PRIVATE_MANIFEST_REJECTED_REDACTED",
    "CANDIDATE_NOT_OBSERVED_REDACTED",
    "CANDIDATE_AMBIGUOUS_REDACTED",
    "CANDIDATE_REJECTED_REDACTED",
    "REDACTED_RECEIPT_UNAVAILABLE_REDACTED",
    "REDACTED_RECEIPT_REJECTED_REDACTED",
    "NOT_READY_EVIDENCE_OBSERVED_REDACTED",
    "READY_EVIDENCE_OBSERVED_REDACTED",
}
FILENAME_STEMS = {
    "CONTROLLED_ENTRY": "abd-current-production-protected-provider-auth-route-resolver-receipt",
    "MANAGEMENT_PLANE": "abd-current-production-ovh-management-plane-diagnostic-receipt",
    "SSH_TRANSPORT": "abd-current-production-ssh-transport-failure-classification-diagnostic-receipt",
    "FROZEN_CONFIG_SEMANTIC_CHECK": "abd-current-production-core-config-semantic-preflight-receipt",
    "CORE_EXECUTION_CONTRACT": "abd-current-production-core-execution-preflight-receipt",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError(ValueError):
    """Raised when private receipt continuity input violates the strict boundary."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError) as exc:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "private redacted prerequisite receipt continuity attestation contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "private redacted prerequisite receipt continuity facts")


def _receipt_filename(spec: Prerequisite, observed_on: str) -> str:
    return "%s-%s.json" % (FILENAME_STEMS[spec.identifier], observed_on.replace("-", ""))


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-PRIVATE-REDACTED-PREREQUISITE-RECEIPT-CONTINUITY-ATTESTATION-001":
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION_READ_ONLY":
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("attestation must remain read-only")
    expected = {
        "private_area": PRIVATE_AREA,
        "private_domain": PRIVATE_DOMAIN,
        "prerequisite_ids": [spec.identifier for spec in PREREQUISITES],
        "current_receipt_filename_stems": [FILENAME_STEMS[spec.identifier] for spec in PREREQUISITES],
        "maximum_private_receipt_bytes": MAX_PRIVATE_RECEIPT_BYTES,
        "maximum_private_database_read_requests": MAX_PRIVATE_DATABASE_READ_REQUESTS,
        "provider_api_requests": 0,
        "product_github_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("attestation expectations are not exact")
    boundary = {
        "private_database_client_read_only": True,
        "single_private_manifest_metadata_stream_read_in_memory_only": True,
        "at_most_one_current_candidate_per_prerequisite_receipt_type": True,
        "selected_private_redacted_receipt_status_fields_read_in_memory_only": True,
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
        "product_github_api_request_sent": False,
        "provider_api_request_sent": False,
        "ssh_connection_attempted": False,
        "browser_login_submitted": False,
        "workflow_dispatched_or_pushed": False,
        "provider_resource_network_cloudflare_host_or_service_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ONLY_NOT_ACTUAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PRIVATE_DATA_PROVIDER_WORKFLOW_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "private_manifest_state",
        "private_manifest_metadata_read_in_memory_only",
        "selected_private_redacted_receipt_content_read_in_memory_only",
        "private_database_read_requests",
        "prerequisite_states",
        "core_activation_prerequisites_ready",
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "product_github_api_requests",
        "provider_api_requests",
        "ssh_connections_attempted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION":
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES or facts.get("private_manifest_state") not in MANIFEST_STATES:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("facts state is invalid")
    for field in (
        "private_manifest_metadata_read_in_memory_only",
        "selected_private_redacted_receipt_content_read_in_memory_only",
        "core_activation_prerequisites_ready",
    ):
        if type(facts.get(field)) is not bool:
            raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("facts boolean state is invalid")
    if type(facts.get("private_database_read_requests")) is not int or not 0 <= facts["private_database_read_requests"] <= MAX_PRIVATE_DATABASE_READ_REQUESTS:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("private database request count is invalid")
    states = _object(facts.get("prerequisite_states"), "prerequisite states")
    if set(states) != {spec.identifier for spec in PREREQUISITES} or any(state not in PREREQUISITE_STATES for state in states.values()):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("prerequisite state set is invalid")
    for field in (
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("redaction boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("outbound operation count is invalid")
    ready = all(states[spec.identifier] == "READY_EVIDENCE_OBSERVED_REDACTED" for spec in PREREQUISITES)
    if facts["core_activation_prerequisites_ready"] is not ready:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("core activation readiness is inconsistent")
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        if facts["private_manifest_state"] != "NOT_ATTEMPTED" or facts["private_database_read_requests"] != 0 or facts["private_manifest_metadata_read_in_memory_only"] or facts["selected_private_redacted_receipt_content_read_in_memory_only"]:
            raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("unavailable root facts are inconsistent")
    elif facts["private_manifest_state"] == "OBSERVED_IN_MEMORY":
        if not facts["private_manifest_metadata_read_in_memory_only"] or facts["private_database_read_requests"] < 1:
            raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("observed manifest facts are inconsistent")
    elif facts["private_manifest_metadata_read_in_memory_only"]:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("unavailable manifest facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_ATTESTATION",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "private_manifest_state": "NOT_ATTEMPTED",
        "private_manifest_metadata_read_in_memory_only": False,
        "selected_private_redacted_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 0,
        "prerequisite_states": {spec.identifier: "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED" for spec in PREREQUISITES},
        "core_activation_prerequisites_ready": False,
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }


def _safe_regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and (info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)) == 0


def load_private_client(client_path: Path) -> ModuleType:
    if not _safe_regular_file(client_path):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("private client is unavailable")
    module_spec = importlib.util.spec_from_file_location("abd_private_db_client", client_path)
    if module_spec is None or module_spec.loader is None:
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("private client loader is unavailable")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if getattr(module, "AREAS", None) is None or PRIVATE_AREA not in module.AREAS or not callable(getattr(module, "_gh", None)):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("private client interface is invalid")
    return module


def _private_read(client: ModuleType, relative_path: str) -> bytes:
    raw = client._gh(
        [
            "repos/%s/contents/%s/%s?ref=%s" % (client.REPO, PRIVATE_AREA, relative_path, client.BRANCH),
            "-H",
            "Accept: application/vnd.github.raw",
        ],
        retries=1,
    )
    if not isinstance(raw, bytes):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("private read response is invalid")
    return raw


def _manifest_candidate(record: object, expected_name: str) -> str | None:
    if not isinstance(record, dict) or set(record) != MANIFEST_RECORD_FIELDS:
        return None
    sha = record.get("sha256")
    if not isinstance(sha, str) or SHA256_PATTERN.fullmatch(sha) is None:
        return None
    if record.get("domain") != PRIVATE_DOMAIN or record.get("original_name") != expected_name or type(record.get("size_bytes")) is not int or not 0 < record["size_bytes"] <= MAX_PRIVATE_RECEIPT_BYTES:
        return None
    object_path = record.get("object_path")
    if not isinstance(object_path, str) or object_path != "objects/%s/%s_%s" % (sha[:2], sha, expected_name):
        return None
    try:
        date.fromisoformat(str(record.get("ingested_at")))
    except ValueError:
        return None
    return object_path


def _candidates_from_manifest(raw: bytes, observed_on: str) -> tuple[dict[str, list[str]], bool]:
    candidates = {spec.identifier: [] for spec in PREREQUISITES}
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return candidates, False
    expected_names = {spec.identifier: _receipt_filename(spec, observed_on) for spec in PREREQUISITES}
    for line in lines:
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return candidates, False
        if not isinstance(record, dict) or set(record) != MANIFEST_RECORD_FIELDS:
            return candidates, False
        if record.get("domain") != PRIVATE_DOMAIN:
            continue
        for spec in PREREQUISITES:
            if record.get("original_name") == expected_names[spec.identifier]:
                object_path = _manifest_candidate(record, expected_names[spec.identifier])
                if object_path is None:
                    return candidates, False
                candidates[spec.identifier].append(object_path)
    return candidates, True


def _receipt_state(raw: bytes, spec: Prerequisite, observed_on: str) -> str:
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "REDACTED_RECEIPT_REJECTED_REDACTED"
    if not _valid_redacted_receipt(receipt, spec) or receipt.get("observed_on") != observed_on:
        return "REDACTED_RECEIPT_REJECTED_REDACTED"
    return "READY_EVIDENCE_OBSERVED_REDACTED" if receipt[spec.ready_field] else "NOT_READY_EVIDENCE_OBSERVED_REDACTED"


def discover_private_continuity(repo_root: Path, client: ModuleType, observed_on: str | None = None) -> dict[str, Any]:
    """Read one private manifest and at most one current redacted receipt per gate."""

    target_date = observed_on or datetime.now(timezone.utc).date().isoformat()
    facts = _base_facts(target_date)
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    facts["private_database_read_requests"] = 1
    try:
        manifest_raw = _private_read(client, "manifest.jsonl")
    except (CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError, RuntimeError, OSError, ValueError):
        facts["private_manifest_state"] = "UNAVAILABLE_REDACTED"
        return facts
    candidates, valid_manifest = _candidates_from_manifest(manifest_raw, target_date)
    if not valid_manifest:
        facts["private_manifest_state"] = "REJECTED_REDACTED"
        facts["prerequisite_states"] = {spec.identifier: "PRIVATE_MANIFEST_REJECTED_REDACTED" for spec in PREREQUISITES}
        return facts
    facts["private_manifest_state"] = "OBSERVED_IN_MEMORY"
    facts["private_manifest_metadata_read_in_memory_only"] = True
    states: dict[str, str] = {}
    for spec in PREREQUISITES:
        matches = candidates[spec.identifier]
        if not matches:
            states[spec.identifier] = "CANDIDATE_NOT_OBSERVED_REDACTED"
            continue
        if len(matches) != 1:
            states[spec.identifier] = "CANDIDATE_AMBIGUOUS_REDACTED"
            continue
        facts["private_database_read_requests"] += 1
        try:
            raw = _private_read(client, matches[0])
        except (CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError, RuntimeError, OSError, ValueError):
            states[spec.identifier] = "REDACTED_RECEIPT_UNAVAILABLE_REDACTED"
            continue
        facts["selected_private_redacted_receipt_content_read_in_memory_only"] = True
        states[spec.identifier] = _receipt_state(raw, spec, target_date)
    facts["prerequisite_states"] = states
    facts["core_activation_prerequisites_ready"] = all(state == "READY_EVIDENCE_OBSERVED_REDACTED" for state in states.values())
    return facts


def evaluate_attestation(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    states = _object(facts["prerequisite_states"], "prerequisite states")
    checks = [
        {"id": "PRIVATE_REDACTED_MANIFEST_OBSERVED", "passed": facts["private_manifest_state"] == "OBSERVED_IN_MEMORY"},
        *[{"id": "%s_CURRENT_READY_EVIDENCE_OBSERVED" % spec.identifier, "passed": states[spec.identifier] == "READY_EVIDENCE_OBSERVED_REDACTED"} for spec in PREREQUISITES],
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    ready = bool(facts["core_activation_prerequisites_ready"])
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_CONTINUITY_COMPLETE_SEPARATE_CORE_ACTION_AUTHORIZATION_REQUIRED" if ready else "CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_CONTINUITY_INCOMPLETE_NO_CORE_ACTION_AUTHORIZED",
        "core_activation_prerequisites_ready": ready,
        "prerequisite_states": dict(states),
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_attestation(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["core_activation_prerequisites_ready"], bool):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("attestation authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError("attestation checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "core_activation_prerequisites_ready": result["core_activation_prerequisites_ready"],
        "prerequisite_states": result["prerequisite_states"],
        "product_outbound_operations_not_attempted": result["product_outbound_operations_not_attempted"],
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
        "decision": "CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "core_activation_prerequisites_ready": False,
        "prerequisite_states": {spec.identifier: "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED" for spec in PREREQUISITES},
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_PRIVATE_REDACTED_PREREQUISITE_RECEIPT_CONTINUITY_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "private_data_provider_workflow_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--private-client", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        client = load_private_client(args.private_client)
        receipt = build_receipt(load_contract(args.contract), discover_private_continuity(args.repo_root, client))
    except (CurrentProductionPrivateRedactedPrerequisiteReceiptContinuityAttestationError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
