from __future__ import annotations

from typing import Any

from .canonical import canonical_json_bytes, sha256_hex
from .engine import DEFAULT_LIMITS, RUNTIME_VERSION, STABLE_ID, validate_bundle
from .errors import EFSError

CAPACITY_CONTRACT_SCHEMA = "efs.capacity_contract.v1"
WORKLOAD_ASSESSMENT_SCHEMA = "efs.workload_assessment.v1"


def build_capacity_contract(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic hard limits and shape; never invent latency claims."""
    validate_bundle(bundle)
    limits = dict(bundle["runtime_limits"])
    feature_count = len(bundle["feature_contracts"])
    expert_count = len(bundle["experts"])
    bucket_count = len(bundle["timing_head"]["buckets"])
    expert_weight_count = sum(len(expert["weights"]) for expert in bundle["experts"].values())
    aggregator_weight_count = sum(len(item["aggregator"]["weights"]) for item in bundle["admissible_expert_sets"])
    single_evaluation_operation_units = feature_count + expert_weight_count + aggregator_weight_count + bucket_count
    contract: dict[str, Any] = {
        "schema": CAPACITY_CONTRACT_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "bundle_sha256": bundle["payload_sha256"],
        "configured_hard_limits": limits,
        "observed_bundle_shape": {
            "feature_count": feature_count,
            "expert_count": expert_count,
            "admissible_expert_set_count": len(bundle["admissible_expert_sets"]),
            "timing_bucket_count": bucket_count,
            "expert_weight_count": expert_weight_count,
            "aggregator_weight_count": aggregator_weight_count,
        },
        "deterministic_operation_budget": {
            "single_evaluation_units": single_evaluation_operation_units,
            "configured_max_batch_units": single_evaluation_operation_units * limits["max_batch"],
            "interpretation": "STRUCTURAL_COMPLEXITY_ONLY_NOT_CPU_TIME",
        },
        "claim_boundary": {
            "latency_slo_proven": False,
            "throughput_slo_proven": False,
            "concurrency_safety_proven": False,
            "production_7x24_proven": False,
            "requires_host_environment_benchmark": True,
        },
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    contract["contract_sha256"] = sha256_hex(contract)
    return contract


def assess_workload(
    contract: dict[str, Any],
    *,
    batch_size: int,
    request_bytes_each: int,
    concurrent_callers: int,
) -> dict[str, Any]:
    """Fail closed against hard limits; concurrency remains host-owned and unproven."""
    if not isinstance(contract, dict):
        raise EFSError("CONTRACT_INVALID", "capacity contract must be an object")
    if contract.get("schema") != CAPACITY_CONTRACT_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported capacity contract schema")
    claimed = contract.get("contract_sha256")
    payload = dict(contract)
    payload.pop("contract_sha256", None)
    if not isinstance(claimed, str) or claimed != sha256_hex(payload):
        raise EFSError("HASH_MISMATCH", "capacity contract hash mismatch")
    for name, value in {
        "batch_size": batch_size,
        "request_bytes_each": request_bytes_each,
        "concurrent_callers": concurrent_callers,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise EFSError("CONTRACT_INVALID", f"{name} must be a positive integer")

    limits = contract.get("configured_hard_limits")
    if not isinstance(limits, dict):
        raise EFSError("CONTRACT_INVALID", "capacity contract hard limits must be an object")
    max_batch = limits.get("max_batch")
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or max_batch < 1:
        raise EFSError("CONTRACT_INVALID", "capacity contract max_batch must be a positive integer")
    budget = contract.get("deterministic_operation_budget")
    if not isinstance(budget, dict):
        raise EFSError("CONTRACT_INVALID", "capacity contract operation budget must be an object")
    single_units = budget.get("single_evaluation_units")
    if isinstance(single_units, bool) or not isinstance(single_units, int) or single_units < 1:
        raise EFSError("CONTRACT_INVALID", "capacity contract single_evaluation_units must be a positive integer")
    checks = {
        "batch_within_limit": batch_size <= max_batch,
        "request_bytes_within_limit": request_bytes_each <= DEFAULT_LIMITS["request_bytes"],
        "single_caller_profile": concurrent_callers == 1,
    }
    reasons = []
    if not checks["batch_within_limit"]:
        reasons.append("BATCH_LIMIT_EXCEEDED")
    if not checks["request_bytes_within_limit"]:
        reasons.append("REQUEST_BYTE_LIMIT_EXCEEDED")
    if not checks["single_caller_profile"]:
        reasons.append("CONCURRENCY_NOT_PROVEN_REQUIRES_HOST_ISOLATION")
    assessment: dict[str, Any] = {
        "schema": WORKLOAD_ASSESSMENT_SCHEMA,
        "capacity_contract_sha256": claimed,
        "status": "PASS" if not reasons else "REJECT",
        "checks": checks,
        "blocking_reasons": reasons,
        "requested": {
            "batch_size": batch_size,
            "request_bytes_each": request_bytes_each,
            "concurrent_callers": concurrent_callers,
        },
        "estimated_operation_units": single_units * batch_size,
        "automatic_scale_out_permitted": False,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "network_requests_total": 0,
    }
    assessment["assessment_sha256"] = sha256_hex(assessment)
    return assessment
