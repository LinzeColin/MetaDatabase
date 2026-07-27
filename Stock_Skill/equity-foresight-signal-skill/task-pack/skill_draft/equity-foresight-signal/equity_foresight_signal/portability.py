from __future__ import annotations

from typing import Any

from .canonical import canonical_json_bytes, sha256_hex, strict_json_loads
from .engine import RUNTIME_VERSION, STABLE_ID, evaluate, self_check, validate_bundle
from .errors import EFSError
from .training import train_direction_pipeline, validate_training_config

GOLDEN_VECTOR_SCHEMA = "efs.portability_golden_vector.v1"
GOLDEN_REPORT_SCHEMA = "efs.portability_golden_report.v1"


def _required_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
    return value


def _required_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise EFSError("CONTRACT_INVALID", f"{field} must be a SHA-256 hex string")
    try:
        int(value, 16)
    except ValueError as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} must be a SHA-256 hex string") from exc
    return value.lower()


def _mapping(value: dict[str, Any] | str | bytes, field: str, max_bytes: int = 5_000_000) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = canonical_json_bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object or JSON payload")
    parsed = strict_json_loads(raw, max_bytes=max_bytes)
    if not isinstance(parsed, dict):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
    return parsed


def build_golden_vector(
    *,
    bundle: dict[str, Any] | str | bytes,
    request: dict[str, Any] | str | bytes,
    pit_dataset: dict[str, Any] | str | bytes,
    training_config: dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    bundle_map = _mapping(bundle, "bundle")
    request_map = _mapping(request, "request")
    dataset_map = _mapping(pit_dataset, "PIT dataset", 20_000_000)
    config_map = _mapping(training_config, "training config")
    validate_bundle(bundle_map)
    validate_training_config(config_map)
    forecast = evaluate(request_map, bundle_map)
    training = train_direction_pipeline(dataset_map, config_map)
    runtime = self_check()
    vector: dict[str, Any] = {
        "schema": GOLDEN_VECTOR_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "input_hashes": {
            "bundle_sha256": bundle_map["payload_sha256"],
            "request_sha256": sha256_hex(request_map),
            "pit_dataset_sha256": dataset_map["payload_sha256"],
            "training_config_sha256": config_map["config_sha256"],
        },
        "expected_hashes": {
            "forecast_result_sha256": forecast["result_sha256"],
            "training_run_sha256": training["run_sha256"],
            "runtime_self_check_sha256": sha256_hex(runtime),
        },
        "claim_boundary": {
            "same_runtime_semantics_required": True,
            "cross_python_matrix_proven": False,
            "cross_cpu_architecture_proven": False,
            "os_network_isolation_proven": False,
        },
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    vector["vector_sha256"] = sha256_hex(vector)
    return vector


def verify_golden_vector(
    vector: dict[str, Any] | str | bytes,
    *,
    bundle: dict[str, Any] | str | bytes,
    request: dict[str, Any] | str | bytes,
    pit_dataset: dict[str, Any] | str | bytes,
    training_config: dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    value = _mapping(vector, "golden vector")
    if value.get("schema") != GOLDEN_VECTOR_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported golden vector schema")
    claimed = value.get("vector_sha256")
    payload = dict(value)
    payload.pop("vector_sha256", None)
    if not isinstance(claimed, str) or claimed != sha256_hex(payload):
        raise EFSError("HASH_MISMATCH", "golden vector hash mismatch")
    if value.get("stable_id") != STABLE_ID or value.get("runtime_version") != RUNTIME_VERSION:
        raise EFSError("CONTRACT_INVALID", "golden vector runtime identity mismatch")

    expected_input_keys = {
        "bundle_sha256", "request_sha256", "pit_dataset_sha256", "training_config_sha256",
    }
    expected_output_keys = {
        "forecast_result_sha256", "training_run_sha256", "runtime_self_check_sha256",
    }
    input_hashes = _required_mapping(value.get("input_hashes"), "golden vector.input_hashes")
    expected_hashes = _required_mapping(value.get("expected_hashes"), "golden vector.expected_hashes")
    claim_boundary = _required_mapping(value.get("claim_boundary"), "golden vector.claim_boundary")
    if set(input_hashes) != expected_input_keys:
        raise EFSError("CONTRACT_INVALID", "golden vector input hash keys mismatch")
    if set(expected_hashes) != expected_output_keys:
        raise EFSError("CONTRACT_INVALID", "golden vector expected hash keys mismatch")
    for key in sorted(expected_input_keys):
        _required_sha(input_hashes.get(key), f"golden vector.input_hashes.{key}")
    for key in sorted(expected_output_keys):
        _required_sha(expected_hashes.get(key), f"golden vector.expected_hashes.{key}")
    required_claims = {
        "same_runtime_semantics_required",
        "cross_python_matrix_proven",
        "cross_cpu_architecture_proven",
        "os_network_isolation_proven",
    }
    if set(claim_boundary) != required_claims or any(not isinstance(claim_boundary[key], bool) for key in required_claims):
        raise EFSError("CONTRACT_INVALID", "golden vector claim boundary mismatch")

    actual = build_golden_vector(
        bundle=bundle,
        request=request,
        pit_dataset=pit_dataset,
        training_config=training_config,
    )
    checks = {
        "bundle_input": actual["input_hashes"]["bundle_sha256"] == input_hashes["bundle_sha256"],
        "request_input": actual["input_hashes"]["request_sha256"] == input_hashes["request_sha256"],
        "pit_dataset_input": actual["input_hashes"]["pit_dataset_sha256"] == input_hashes["pit_dataset_sha256"],
        "training_config_input": actual["input_hashes"]["training_config_sha256"] == input_hashes["training_config_sha256"],
        "forecast_result": actual["expected_hashes"]["forecast_result_sha256"] == expected_hashes["forecast_result_sha256"],
        "training_run": actual["expected_hashes"]["training_run_sha256"] == expected_hashes["training_run_sha256"],
        "runtime_self_check": actual["expected_hashes"]["runtime_self_check_sha256"] == expected_hashes["runtime_self_check_sha256"],
    }
    report: dict[str, Any] = {
        "schema": GOLDEN_REPORT_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "golden_vector_sha256": claimed,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "actual_hashes": actual["expected_hashes"],
        "claim_boundary": claim_boundary,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    report["report_sha256"] = sha256_hex(report)
    return report
