#!/usr/bin/env python3
"""Attest one running ABD shadow image identity without changing runtime state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from http.client import HTTPConnection
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SHADOW_LABEL_KEY = "com.linze.abd.runtime-role"
CORE_LABEL_KEY = "com.linze.abd.phase"
PRODUCT_VERSION_LABEL_KEY = "com.linze.abd.product-version"
ORDER_SUBMISSION_LABEL_KEY = "com.linze.abd.order-submission"
PROBE_HOST = "127.0.0.1"
PROBE_PORT = 8081
PASS_STATUS = "PASS_SHADOW_IMAGE_IDENTITY_ATTESTATION"
FAIL_STATUS = "FAIL_SHADOW_IMAGE_IDENTITY_ATTESTATION"
UNAVAILABLE_STATUS = "FAIL_SHADOW_IMAGE_IDENTITY_ATTESTATION_INPUT_UNAVAILABLE"


class ShadowImageIdentityAttestationError(ValueError):
    """Raised when a one-shot shadow image identity attestation is malformed."""


CommandRunner = Callable[[Sequence[str]], str]
JsonProbe = Callable[[str, int, str], Mapping[str, Any]]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ShadowImageIdentityAttestationError("%s must be an object" % name)
    return value


def _nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShadowImageIdentityAttestationError("%s must be a non-negative integer" % name)
    return value


def _optional_nonnegative_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, name)


def _sha256_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ShadowImageIdentityAttestationError("%s must be a sha256 image identifier" % name)
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise ShadowImageIdentityAttestationError("%s must be a lowercase sha256 image identifier" % name)
    return value


def _image_reference(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("local/abd-runtime@sha256:"):
        raise ShadowImageIdentityAttestationError("%s must be the local ABD digest reference" % name)
    digest = value.rsplit("@", 1)[-1]
    _sha256_digest(digest, name)
    return value


def _line_values(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _read_memory_pair(value: str) -> tuple[int, int]:
    pieces = value.strip().split("/")
    if len(pieces) != 2:
        raise ShadowImageIdentityAttestationError("container memory pair is malformed")
    try:
        return _nonnegative_int(int(pieces[0]), "memory_limit_bytes"), _nonnegative_int(
            int(pieces[1]), "memory_swap_limit_bytes"
        )
    except ValueError as exc:
        raise ShadowImageIdentityAttestationError("container memory pair is malformed") from exc


def _run_command(arguments: Sequence[str]) -> str:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _probe_loopback_json(host: str = PROBE_HOST, port: int = PROBE_PORT, path: str = "/status") -> Mapping[str, Any]:
    if path not in {"/status", "/evidence"}:
        raise ShadowImageIdentityAttestationError("attestation path is not accepted")
    connection = HTTPConnection(host, port, timeout=2)
    try:
        connection.request("GET", path, headers={"Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise ShadowImageIdentityAttestationError("shadow attestation endpoint did not return HTTP 200")
        payload = json.loads(response.read())
    finally:
        connection.close()
    return _object(payload, "shadow attestation payload")


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowImageIdentityAttestationError("attestation contract is unreadable") from exc
    return _object(value, "attestation contract")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "contract_id",
        "product_version",
        "status",
        "observation_scope",
        "expected",
        "runtime_boundary",
        "source_claim",
        "rollback",
    }
    if set(contract) != required:
        raise ShadowImageIdentityAttestationError("attestation contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise ShadowImageIdentityAttestationError("unsupported attestation schema version")
    if contract.get("contract_id") != "ABD-POST-FREEZE-SHADOW-IMAGE-IDENTITY-005":
        raise ShadowImageIdentityAttestationError("unexpected attestation contract identifier")
    if contract.get("product_version") != "0.0.0.1":
        raise ShadowImageIdentityAttestationError("unexpected attestation product version")
    if contract.get("status") != "ONE_SHOT_HOST_LOOPBACK_IMAGE_IDENTITY_ATTESTATION_ONLY":
        raise ShadowImageIdentityAttestationError("attestation must remain one-shot and host-loopback-only")
    if contract.get("observation_scope") != "HOST_LOCAL_DOCKER_METADATA_AND_FIXED_LOOPBACK_HTTP_STATUS_AND_EVIDENCE_ONLY":
        raise ShadowImageIdentityAttestationError("attestation observation scope is not exact")
    if contract.get("source_claim") != "RUNNING_IMAGE_IDENTITY_ONLY_NOT_SOURCE_COMMIT_OR_OCI_ARCHIVE_PROVENANCE":
        raise ShadowImageIdentityAttestationError("attestation source claim is not exact")

    expected = _object(contract.get("expected"), "attestation expected")
    expected_keys = {
        "shadow_label",
        "core_label",
        "shadow_container_count",
        "core_container_count",
        "image_reference",
        "image_id",
        "labels",
        "memory_limit_bytes",
        "memory_swap_limit_bytes",
        "port_mapping",
        "status_payload",
        "observation_evidence_payload",
    }
    if set(expected) != expected_keys:
        raise ShadowImageIdentityAttestationError("attestation expected field set is not exact")
    if expected.get("shadow_label") != SHADOW_LABEL_KEY + "=candidate-shadow":
        raise ShadowImageIdentityAttestationError("shadow label is not exact")
    if expected.get("core_label") != CORE_LABEL_KEY + "=S04-P01":
        raise ShadowImageIdentityAttestationError("core label is not exact")
    if expected.get("shadow_container_count") != 1 or expected.get("core_container_count") != 0:
        raise ShadowImageIdentityAttestationError("attestation container counts are not exact")
    image_reference = _image_reference(expected.get("image_reference"), "expected image_reference")
    image_id = _sha256_digest(expected.get("image_id"), "expected image_id")
    if image_reference.rsplit("@", 1)[-1] != image_id:
        raise ShadowImageIdentityAttestationError("image reference and image identifier disagree")
    if expected.get("labels") != {
        "product_version": "0.0.0.1",
        "runtime_role": "candidate-shadow",
        "order_submission": "disabled",
    }:
        raise ShadowImageIdentityAttestationError("attestation image labels are not exact")
    if expected.get("memory_limit_bytes") != 512 * 1024 * 1024:
        raise ShadowImageIdentityAttestationError("attestation memory limit is not exact")
    if expected.get("memory_swap_limit_bytes") != 512 * 1024 * 1024:
        raise ShadowImageIdentityAttestationError("attestation memory swap limit is not exact")
    if expected.get("port_mapping") != "127.0.0.1:8081":
        raise ShadowImageIdentityAttestationError("attestation port mapping is not exact")
    if expected.get("status_payload") != {
        "service": "ABD",
        "version": "0.0.0.1",
        "mode": "SHADOW_READ_ONLY",
        "decision": "NO_RECOMMENDATION_NO_ORDER",
        "ready": True,
        "recommendation_enabled": False,
        "order_submission_enabled": False,
        "market_or_account_connected": False,
        "gmail_or_tab_connected": False,
    }:
        raise ShadowImageIdentityAttestationError("attestation status payload is not exact")
    if expected.get("observation_evidence_payload") != {
        "service": "ABD",
        "version": "0.0.0.1",
        "mode": "SHADOW_READ_ONLY",
        "surface": "STATIC_OBSERVATION_EVIDENCE_ONLY",
        "static_calibration": {
            "scope": "E0_2025_26_HISTORICAL_SINGLE_SEASON",
            "fixture_count": 380,
            "outcome_rows": 1140,
            "evidence_status": "STATIC_SINGLE_SEASON_DESCRIPTION_NOT_ELIGIBLE_FOR_MODEL_UPDATE",
            "model_update_eligible": False,
        },
        "capability_boundary": {
            "market_or_account_connected": False,
            "gmail_or_tab_connected": False,
            "recommendation_enabled": False,
            "order_submission_enabled": False,
            "public_business_inbound_enabled": False,
        },
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }:
        raise ShadowImageIdentityAttestationError("attestation observation evidence payload is not exact")

    expected_boundary = {
        "runtime_config_or_secret_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "continuous_monitoring_created": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("runtime_boundary"), "runtime_boundary") != expected_boundary:
        raise ShadowImageIdentityAttestationError("attestation runtime boundary is not exact")
    expected_rollback = {
        "action": "REMOVE_ATTESTER_ONLY_KEEP_SHADOW_RUNTIME_UNCHANGED",
        "runtime_or_image_rollback_performed": False,
        "prior_private_evidence_deleted_automatically": False,
    }
    if _object(contract.get("rollback"), "rollback") != expected_rollback:
        raise ShadowImageIdentityAttestationError("attestation rollback is not exact")


def collect_shadow_image_identity_facts(
    contract: Mapping[str, Any], *, run: CommandRunner = _run_command, probe: JsonProbe = _probe_loopback_json
) -> dict[str, Any]:
    """Read only Docker metadata plus fixed host-loopback status and evidence endpoints."""

    validate_contract(contract)
    expected = _object(contract["expected"], "attestation expected")
    shadow_ids = _line_values(run(("docker", "ps", "-q", "--filter", "label=" + str(expected["shadow_label"]))))
    core_ids = _line_values(run(("docker", "ps", "-q", "--filter", "label=" + str(expected["core_label"]))))
    facts: dict[str, Any] = {
        "shadow_container_count": len(shadow_ids),
        "core_container_count": len(core_ids),
        "shadow_running": None,
        "image_id": None,
        "repo_digests": None,
        "labels": None,
        "memory_limit_bytes": None,
        "memory_swap_limit_bytes": None,
        "port_mapping": None,
        "status_payload": None,
        "observation_evidence_payload": None,
    }
    if len(shadow_ids) != 1:
        return facts

    container = shadow_ids[0]
    facts["shadow_running"] = run(("docker", "inspect", "--format", "{{.State.Running}}", container)).strip() == "true"
    image_id = run(("docker", "inspect", "--format", "{{.Image}}", container)).strip()
    facts["image_id"] = image_id
    try:
        repo_digests = json.loads(run(("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id)))
    except json.JSONDecodeError as exc:
        raise ShadowImageIdentityAttestationError("Docker image repo digests are malformed") from exc
    if not isinstance(repo_digests, list) or not all(isinstance(value, str) for value in repo_digests):
        raise ShadowImageIdentityAttestationError("Docker image repo digests are malformed")
    facts["repo_digests"] = repo_digests
    facts["labels"] = {
        "product_version": run(("docker", "inspect", "--format", "{{index .Config.Labels \"com.linze.abd.product-version\"}}", container)).strip(),
        "runtime_role": run(("docker", "inspect", "--format", "{{index .Config.Labels \"com.linze.abd.runtime-role\"}}", container)).strip(),
        "order_submission": run(("docker", "inspect", "--format", "{{index .Config.Labels \"com.linze.abd.order-submission\"}}", container)).strip(),
    }
    memory_limit, memory_swap_limit = _read_memory_pair(
        run(("docker", "inspect", "--format", "{{.HostConfig.Memory}}/{{.HostConfig.MemorySwap}}", container))
    )
    facts["memory_limit_bytes"] = memory_limit
    facts["memory_swap_limit_bytes"] = memory_swap_limit
    facts["port_mapping"] = run(("docker", "port", container, "8080/tcp")).strip()
    facts["status_payload"] = dict(probe(PROBE_HOST, PROBE_PORT, "/status"))
    facts["observation_evidence_payload"] = dict(probe(PROBE_HOST, PROBE_PORT, "/evidence"))
    return facts


def evaluate_shadow_image_identity_facts(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed when any running shadow image identity or boundary diverges."""

    validate_contract(contract)
    required = {
        "shadow_container_count",
        "core_container_count",
        "shadow_running",
        "image_id",
        "repo_digests",
        "labels",
        "memory_limit_bytes",
        "memory_swap_limit_bytes",
        "port_mapping",
        "status_payload",
        "observation_evidence_payload",
    }
    if set(facts) != required:
        raise ShadowImageIdentityAttestationError("attestation facts have an unexpected shape")
    expected = _object(contract["expected"], "attestation expected")
    shadow_count = _nonnegative_int(facts["shadow_container_count"], "shadow_container_count")
    core_count = _nonnegative_int(facts["core_container_count"], "core_container_count")
    shadow_running = facts["shadow_running"]
    if shadow_running is not None and not isinstance(shadow_running, bool):
        raise ShadowImageIdentityAttestationError("shadow_running must be boolean or null")
    image_id = facts["image_id"]
    if image_id is not None and not isinstance(image_id, str):
        raise ShadowImageIdentityAttestationError("image_id must be a string or null")
    repo_digests = facts["repo_digests"]
    if repo_digests is not None and (
        not isinstance(repo_digests, list) or not all(isinstance(value, str) for value in repo_digests)
    ):
        raise ShadowImageIdentityAttestationError("repo_digests must be a string list or null")
    labels = facts["labels"]
    if labels is not None and (
        not isinstance(labels, Mapping) or set(labels) != {"product_version", "runtime_role", "order_submission"}
        or not all(isinstance(value, str) for value in labels.values())
    ):
        raise ShadowImageIdentityAttestationError("labels have an unexpected shape")
    memory_limit = _optional_nonnegative_int(facts["memory_limit_bytes"], "memory_limit_bytes")
    memory_swap_limit = _optional_nonnegative_int(facts["memory_swap_limit_bytes"], "memory_swap_limit_bytes")
    port_mapping = facts["port_mapping"]
    if port_mapping is not None and not isinstance(port_mapping, str):
        raise ShadowImageIdentityAttestationError("port_mapping must be a string or null")
    status_payload = facts["status_payload"]
    if status_payload is not None and not isinstance(status_payload, Mapping):
        raise ShadowImageIdentityAttestationError("status_payload must be an object or null")
    observation_evidence_payload = facts["observation_evidence_payload"]
    if observation_evidence_payload is not None and not isinstance(observation_evidence_payload, Mapping):
        raise ShadowImageIdentityAttestationError("observation_evidence_payload must be an object or null")

    checks = [
        {"id": "EXACTLY_ONE_SHADOW_CONTAINER", "passed": shadow_count == expected["shadow_container_count"]},
        {"id": "CORE_RUNTIME_ABSENT", "passed": core_count == expected["core_container_count"]},
        {"id": "SHADOW_CONTAINER_RUNNING", "passed": shadow_running is True},
        {"id": "SHADOW_IMAGE_ID_EXACT", "passed": image_id == expected["image_id"]},
        {"id": "SHADOW_IMAGE_REFERENCE_EXACT", "passed": repo_digests == [expected["image_reference"]]},
        {"id": "SHADOW_IMAGE_LABELS_EXACT", "passed": labels == expected["labels"]},
        {"id": "SHADOW_MEMORY_LIMIT_EXACT", "passed": memory_limit == expected["memory_limit_bytes"]},
        {"id": "SHADOW_NO_ADDITIONAL_SWAP", "passed": memory_swap_limit == expected["memory_swap_limit_bytes"] == memory_limit},
        {"id": "LOOPBACK_PORT_MAPPING_EXACT", "passed": port_mapping == expected["port_mapping"]},
        {"id": "SAFE_STATUS_PAYLOAD_EXACT", "passed": dict(status_payload) == expected["status_payload"] if status_payload is not None else False},
        {
            "id": "STATIC_OBSERVATION_EVIDENCE_PAYLOAD_EXACT",
            "passed": dict(observation_evidence_payload) == expected["observation_evidence_payload"]
            if observation_evidence_payload is not None
            else False,
        },
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    passed = not failure_codes
    return {
        "schema_version": "1.0.0",
        "status": PASS_STATUS if passed else FAIL_STATUS,
        "decision": "SHADOW_IMAGE_IDENTITY_BOUNDARY_PASS" if passed else "SHADOW_IMAGE_IDENTITY_BOUNDARY_FAIL_CLOSED",
        "attestation_valid": passed,
        "checks": checks,
        "failure_codes": failure_codes,
        "observed": {
            "shadow_container_count": shadow_count,
            "core_container_count": core_count,
            "shadow_running": shadow_running,
            "image_identity_exact": image_id == expected["image_id"] and repo_digests == [expected["image_reference"]],
            "image_labels_exact": labels == expected["labels"],
            "memory_limit_exact": memory_limit == expected["memory_limit_bytes"],
            "no_additional_container_swap": memory_swap_limit == expected["memory_swap_limit_bytes"] == memory_limit,
            "host_loopback_port_exact": port_mapping == expected["port_mapping"],
            "status_payload_exact": dict(status_payload) == expected["status_payload"] if status_payload is not None else False,
            "observation_evidence_payload_exact": dict(observation_evidence_payload) == expected["observation_evidence_payload"]
            if observation_evidence_payload is not None
            else False,
        },
        "runtime_config_or_secret_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "continuous_monitoring_created": False,
        "real_time_soak_waited": False,
    }


def build_receipt(
    contract: Mapping[str, Any],
    facts: Mapping[str, Any],
    contract_sha256: str,
    validator_sha256: str,
    observed_on: str,
) -> dict[str, Any]:
    validate_contract(contract)
    _sha256_digest("sha256:" + contract_sha256, "contract_sha256")
    _sha256_digest("sha256:" + validator_sha256, "validator_sha256")
    try:
        observed_date = date.fromisoformat(observed_on)
    except ValueError as exc:
        raise ShadowImageIdentityAttestationError("observation date is invalid") from exc
    result = evaluate_shadow_image_identity_facts(contract, facts)
    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_POST_FREEZE_SHADOW_IMAGE_IDENTITY_ATTESTATION",
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": observed_date.isoformat(),
        "contract_sha256": contract_sha256,
        "validator_sha256": validator_sha256,
        "source_claim": contract["source_claim"],
        "attestation_valid": result["attestation_valid"],
        "checks": result["checks"],
        "failure_codes": result["failure_codes"],
        "observed": result["observed"],
        "runtime_boundary": dict(_object(contract["runtime_boundary"], "runtime_boundary")),
    }


def _unavailable_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        observed_date = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        observed_date = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_POST_FREEZE_SHADOW_IMAGE_IDENTITY_ATTESTATION",
        "status": UNAVAILABLE_STATUS,
        "decision": "SHADOW_IMAGE_IDENTITY_INPUT_UNAVAILABLE_FAIL_CLOSED",
        "observed_on": observed_date,
        "attestation_valid": False,
        "checks": [],
        "failure_codes": ["SHADOW_IMAGE_IDENTITY_INPUT_UNAVAILABLE"],
        "error_type": type(error).__name__,
        "runtime_config_or_secret_read": False,
        "external_network_accessed": False,
        "runtime_state_changed": False,
        "continuous_monitoring_created": False,
        "real_time_soak_waited": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        contract_bytes = args.contract.read_bytes()
        contract = load_contract(args.contract)
        facts = collect_shadow_image_identity_facts(contract)
        receipt = build_receipt(
            contract,
            facts,
            _sha256(contract_bytes),
            _sha256(Path(__file__).read_bytes()),
            args.observed_on,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, subprocess.SubprocessError, ShadowImageIdentityAttestationError, ValueError) as exc:
        receipt = _unavailable_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
