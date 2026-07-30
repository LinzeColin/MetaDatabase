from __future__ import annotations

from typing import Any

from .canonical import sha256_hex
from .engine import DEFAULT_LIMITS, RUNTIME_VERSION, STABLE_ID, _normalize_json_mapping, _parse_time, validate_bundle
from .errors import EFSError
from .lifecycle import compare_candidate_to_lkg, health_snapshot

RECOVERY_PLAN_SCHEMA = "efs.host_recovery_plan.v1"


def _zero_counters() -> dict[str, int]:
    return {
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }


def build_recovery_plan(
    *,
    as_of: str,
    lkg: dict[str, Any] | str | bytes,
    candidate: dict[str, Any] | str | bytes | None = None,
    failure_code: str,
) -> dict[str, Any]:
    """Return a deterministic host-owned recovery plan without executing it."""
    _parse_time(as_of, "recovery.as_of")
    if not isinstance(failure_code, str) or not failure_code or len(failure_code) > 128:
        raise EFSError("CONTRACT_INVALID", "recovery.failure_code must be a bounded non-empty string")

    lkg_health = health_snapshot(lkg, as_of=as_of)
    plan: dict[str, Any] = {
        "schema": RECOVERY_PLAN_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "as_of": as_of,
        "failure_code": failure_code,
        "automatic_execution_permitted": False,
        "state_mutation_performed": False,
        "transport_owner": "HOST",
        "persistence_owner": "HOST",
        "lkg_health_snapshot_sha256": lkg_health["snapshot_sha256"],
        "lkg_state": lkg_health["bundle_state"],
        "candidate_present": candidate is not None,
        "actions": [],
        "blocking_reasons": [],
        **_zero_counters(),
    }

    if lkg_health["status"] != "HEALTHY":
        plan["decision"] = "HOST_RESTORE_REQUIRED"
        plan["blocking_reasons"].append("LKG_NOT_HEALTHY")
        plan["actions"] = [
            "BLOCK_FORECAST_PUBLICATION",
            "RESTORE_LAST_VERIFIED_LKG_FROM_HOST_AUTHORITY",
            "RUN_HEALTH_CHECK_WITH_EXPLICIT_AS_OF",
        ]
    elif candidate is None:
        plan["decision"] = "KEEP_LKG"
        plan["actions"] = ["KEEP_LKG", "RECORD_COMPACT_FAILURE_FACT"]
    else:
        compatibility = compare_candidate_to_lkg(candidate, lkg)
        plan["compatibility_report_sha256"] = compatibility["report_sha256"]
        try:
            candidate_map = _normalize_json_mapping(candidate, "candidate", DEFAULT_LIMITS["bundle_bytes"])
            validate_bundle(candidate_map)
            plan["candidate_bundle_sha256"] = candidate_map["payload_sha256"]
        except EFSError:
            plan["candidate_bundle_sha256"] = None
        if compatibility["compatible_for_in_place_refresh"]:
            plan["decision"] = "QUARANTINE_CANDIDATE_KEEP_LKG"
            plan["actions"] = [
                "KEEP_LKG",
                "QUARANTINE_CANDIDATE",
                "REQUIRE_SEPARATE_FROZEN_EVIDENCE_REVIEW",
            ]
        else:
            plan["decision"] = "REJECT_CANDIDATE_KEEP_LKG"
            plan["blocking_reasons"].extend(compatibility["blocking_reasons"])
            plan["actions"] = ["KEEP_LKG", "REJECT_CANDIDATE", "RECORD_COMPACT_FAILURE_FACT"]

    plan["blocking_reasons"] = sorted(set(plan["blocking_reasons"]))
    plan["plan_sha256"] = sha256_hex(plan)
    return plan
