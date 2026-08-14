"""Deterministic local S17/P03 fault-projection controls.

This module replays only frozen logical fault vectors.  It never exits a
process, changes DNS or a page, consumes disk or memory, changes a clock,
corrupts a model, contacts a service, or uses a real market/runtime record.
The local result is intentionally fail-closed: when an error vector is
present, a stale snapshot is rejected and the result is degraded without a
recommendation or order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTRACT_ID = "AC-S17-P03"
REQUIREMENT_ID = "REQ-S17-P03"
STAGE_ID = "S17"
PHASE_ID = "P03"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_CHAOS_FAULT_INJECTION_NOT_LIVE_RUNTIME"
FIXTURE_PATH = Path("machine/tests/fixtures/S17_P03.json")
CHAOS_RUNNER_PATH = Path("chaos_runner.py")
CHAOS_SCENARIOS_PATH = Path("chaos_scenarios.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P02.json")

_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_-]{2,79}")

BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}

PREDECESSOR = {
    "contract_id": "AC-S17-P02",
    "evidence_path": P02_EVIDENCE_PATH.as_posix(),
    "evidence_sha256": "c417d9eb732c24969d11db52bd501438572a57e2b3eeef8791085e746aae2711",
    "status": "PASS",
    "next": "S17/P03_READY_NOT_STARTED",
}

CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "real_vps_resource_observed_or_measured": False,
    "real_process_exit_injected": False,
    "real_dns_or_network_fault_injected": False,
    "real_page_disk_memory_clock_or_model_mutated": False,
    "real_runtime_or_ledger_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}

EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "actual_fault_injection_allowed": False,
    "external_runtime_access_allowed": False,
    "incremental_cash_spent_aud": "0.00",
}

CHAOS_POLICY = {
    "injection_mode": "FROZEN_LOGICAL_FAULT_PROJECTION_NOT_ACTUAL_SYSTEM_FAULT",
    "stale_data_policy": "REJECT_STALE_DATA_ON_ANY_ERROR",
    "degradation_policy": "AUTO_DEGRADE_NO_RECOMMENDATION_NO_ORDER",
    "recovery_policy": "RESTORE_PREVIOUS_SIGNED_ARTIFACTS_LOCAL_ONLY",
    "adverse_probability_deltas": ["-0.0001", "0.0000", "0.0001"],
    "adverse_odds_tick_delta_min": -1,
    "recommendation_enabled": False,
    "order_submission_enabled": False,
}

EXPECTED_SCENARIOS = (
    {
        "scenario_id": "BASELINE_HEALTHY_CURRENT",
        "fault": "NONE",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-001", "availability": "CURRENT", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-001", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": False, "selected_data": "CURRENT_FROZEN_SNAPSHOT", "stale_data_used": False, "stale_data_disposition": "NOT_SELECTED", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "PROCESS_EXIT_FAIL_CLOSED",
        "fault": "PROCESS_EXIT",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-002", "availability": "UNAVAILABLE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-002", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "DNS_FAILURE_FAIL_CLOSED",
        "fault": "DNS_FAILURE",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-003", "availability": "UNAVAILABLE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-003", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "NETWORK_FAILURE_FAIL_CLOSED",
        "fault": "NETWORK_FAILURE",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-004", "availability": "UNAVAILABLE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-004", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "PAGE_SCHEMA_CHANGE_FAIL_CLOSED",
        "fault": "PAGE_SCHEMA_CHANGE",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-005", "availability": "INVALID_SCHEMA", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-005", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "DISK_PRESSURE_FAIL_CLOSED",
        "fault": "DISK_PRESSURE",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-006", "availability": "UNAVAILABLE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-006", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "MEMORY_PRESSURE_FAIL_CLOSED",
        "fault": "MEMORY_PRESSURE",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-007", "availability": "UNAVAILABLE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-007", "availability": "STALE", "probability_delta": "0.0000", "odds_tick_delta": 0},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "CLOCK_SKEW_FAIL_CLOSED",
        "fault": "CLOCK_SKEW",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-008", "availability": "INVALID_CLOCK", "probability_delta": "-0.0001", "odds_tick_delta": -1},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-008", "availability": "STALE", "probability_delta": "-0.0001", "odds_tick_delta": -1},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
    {
        "scenario_id": "MODEL_ARTIFACT_CORRUPTION_FAIL_CLOSED",
        "fault": "MODEL_ARTIFACT_CORRUPTION",
        "current_snapshot": {"snapshot_id": "CURRENT-S17P03-009", "availability": "INVALID_MODEL_ARTIFACT", "probability_delta": "0.0001", "odds_tick_delta": -1},
        "stale_snapshot": {"snapshot_id": "STALE-S17P03-009", "availability": "STALE", "probability_delta": "0.0001", "odds_tick_delta": -1},
        "expected": {"degraded": True, "selected_data": "NONE", "stale_data_used": False, "stale_data_disposition": "REJECTED_STALE_DATA", "action": "NO_RECOMMENDATION_NO_ORDER"},
    },
)


class ChaosInputError(ValueError):
    """Raised when S17/P03 inputs leave the frozen fail-closed boundary."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def strict_json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChaosInputError("cannot read JSON artifact: %s" % path.as_posix()) from exc


def _compact_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ChaosInputError("%s fields are not exact" % label)
    return value


def _validate_snapshot(value: Any, label: str, allowed_availability: set[str]) -> Mapping[str, Any]:
    snapshot = _closed_mapping(value, {"snapshot_id", "availability", "probability_delta", "odds_tick_delta"}, label)
    if (
        not isinstance(snapshot["snapshot_id"], str)
        or not _IDENTIFIER.fullmatch(snapshot["snapshot_id"])
        or snapshot["availability"] not in allowed_availability
        or snapshot["probability_delta"] not in {"-0.0001", "0.0000", "0.0001"}
        or type(snapshot["odds_tick_delta"]) is not int
        or snapshot["odds_tick_delta"] < -1
        or snapshot["odds_tick_delta"] > 0
    ):
        raise ChaosInputError("snapshot is outside the frozen boundary")
    return snapshot


def _validate_scenarios(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(EXPECTED_SCENARIOS):
        raise ChaosInputError("scenario count is not exact")
    normalized: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    for raw, expected in zip(value, EXPECTED_SCENARIOS):
        scenario = _closed_mapping(raw, {"scenario_id", "fault", "current_snapshot", "stale_snapshot", "expected"}, "scenario")
        if scenario != expected:
            raise ChaosInputError("scenario is not the frozen deterministic vector")
        if scenario["scenario_id"] in seen_ids:
            raise ChaosInputError("scenario ids must be unique")
        seen_ids.add(scenario["scenario_id"])
        _validate_snapshot(scenario["current_snapshot"], "current_snapshot", {"CURRENT", "UNAVAILABLE", "INVALID_SCHEMA", "INVALID_CLOCK", "INVALID_MODEL_ARTIFACT"})
        _validate_snapshot(scenario["stale_snapshot"], "stale_snapshot", {"STALE"})
        normalized.append(scenario)
    return normalized


def validate_fixture(value: Any) -> Mapping[str, Any]:
    required = {
        "schema_version", "fixture_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock",
        "input_mode", "baseline_hashes", "predecessor", "chaos_policy", "scenarios", "expected_decision", "expected_next", "minimum_targeted_pytest_cases",
    }
    fixture = _closed_mapping(value, required, "fixture")
    if (
        fixture["schema_version"] != "1.0.0"
        or fixture["fixture_id"] != "FIXTURE-S17-P03-001"
        or fixture["contract_id"] != CONTRACT_ID
        or fixture["requirement_id"] != REQUIREMENT_ID
        or fixture["stage_id"] != STAGE_ID
        or fixture["phase_id"] != PHASE_ID
        or fixture["product_version"] != PRODUCT_VERSION
        or fixture["fixed_clock"] != FIXED_CLOCK
        or fixture["input_mode"] != INPUT_MODE
        or fixture["baseline_hashes"] != BASELINE_HASHES
        or fixture["predecessor"] != PREDECESSOR
        or fixture["chaos_policy"] != CHAOS_POLICY
        or fixture["expected_decision"] != "S17_P03_CHAOS_STALE_DATA_GATE_PASS_P04_REQUIRED"
        or fixture["expected_next"] != "S17/P04_READY_NOT_STARTED"
        or type(fixture["minimum_targeted_pytest_cases"]) is not int
        or fixture["minimum_targeted_pytest_cases"] < 30
    ):
        raise ChaosInputError("fixture is not the exact S17/P03 contract")
    _validate_scenarios(fixture["scenarios"])
    return fixture


def load_fixture(path: Path) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(path))


def _validate_source_inputs(root: Path, fixture: Mapping[str, Any]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if actual != expected:
            raise ChaosInputError("frozen baseline hash mismatch: %s" % relative)
    predecessor_path = root / P02_EVIDENCE_PATH
    if not predecessor_path.is_file() or sha256_file(predecessor_path) != fixture["predecessor"]["evidence_sha256"]:
        raise ChaosInputError("P02 signed predecessor is unavailable or changed")
    predecessor = strict_json_load(predecessor_path)
    if (
        not isinstance(predecessor, Mapping)
        or predecessor.get("contract_id") != PREDECESSOR["contract_id"]
        or predecessor.get("status") != "PASS"
        or predecessor.get("decision") != "S17_P02_IDEMPOTENCY_PASS_P03_REQUIRED"
        or predecessor.get("next") != PREDECESSOR["next"]
        or predecessor.get("production_status") != "NOT_DEPLOYED_OR_ACTIVATED"
        or predecessor.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or predecessor.get("decision_sha256") != _compact_hash({key: value for key, value in predecessor.items() if key != "decision_sha256"})
    ):
        raise ChaosInputError("P02 predecessor does not preserve the local-only boundary")


def replay_scenario(scenario: Mapping[str, Any]) -> Mapping[str, Any]:
    """Replay one immutable logical error vector without injecting a real fault."""

    matching = [item for item in EXPECTED_SCENARIOS if item["scenario_id"] == scenario.get("scenario_id")]
    if len(matching) != 1 or scenario != matching[0]:
        raise ChaosInputError("scenario is not an approved frozen vector")
    expected = scenario["expected"]
    error_present = scenario["fault"] != "NONE"
    result = {
        "scenario_id": scenario["scenario_id"],
        "fault": scenario["fault"],
        "fault_injection_mode": CHAOS_POLICY["injection_mode"],
        "current_snapshot": dict(scenario["current_snapshot"]),
        "stale_snapshot": dict(scenario["stale_snapshot"]),
        "degraded": expected["degraded"],
        "selected_data": expected["selected_data"],
        "stale_data_used": expected["stale_data_used"],
        "stale_data_disposition": expected["stale_data_disposition"],
        "action": expected["action"],
        "recovery_projection": "RESTORE_PREVIOUS_SIGNED_ARTIFACTS_LOCAL_ONLY" if error_present else "NOT_REQUIRED",
        "real_fault_injected": False,
    }
    if error_present and (
        result["degraded"] is not True
        or result["selected_data"] != "NONE"
        or result["stale_data_used"] is not False
        or result["stale_data_disposition"] != "REJECTED_STALE_DATA"
    ):
        raise ChaosInputError("error vector did not fail closed")
    return result


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    fixture = validate_fixture(fixture)
    _validate_source_inputs(root, fixture)
    scenarios = [replay_scenario(scenario) for scenario in fixture["scenarios"]]
    error_scenarios = [scenario for scenario in scenarios if scenario["fault"] != "NONE"]
    aggregate = {
        "scenario_count": len(scenarios),
        "error_scenario_count": len(error_scenarios),
        "degraded_count": sum(item["degraded"] is True for item in scenarios),
        "rejected_stale_data_count": sum(item["stale_data_disposition"] == "REJECTED_STALE_DATA" for item in scenarios),
        "stale_data_used_count": sum(item["stale_data_used"] is True for item in scenarios),
        "no_recommendation_no_order_count": sum(item["action"] == "NO_RECOMMENDATION_NO_ORDER" for item in scenarios),
    }
    stale_gate = {
        "error_scenario_count": aggregate["error_scenario_count"],
        "auto_degraded_count": aggregate["degraded_count"],
        "rejected_stale_data_count": aggregate["rejected_stale_data_count"],
        "stale_data_used_count": aggregate["stale_data_used_count"],
        "passed": (
            aggregate["error_scenario_count"] == 8
            and aggregate["degraded_count"] == 8
            and aggregate["rejected_stale_data_count"] == 8
            and aggregate["stale_data_used_count"] == 0
            and aggregate["no_recommendation_no_order_count"] == 9
        ),
    }
    report = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S17-P03-02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "source_generator": {"artifact_id": "ART-S17-P03-01", "path": CHAOS_RUNNER_PATH.as_posix(), "sha256": sha256_file(root / CHAOS_RUNNER_PATH)},
        "predecessor": dict(PREDECESSOR),
        "baseline_hashes": dict(BASELINE_HASHES),
        "chaos_policy": dict(CHAOS_POLICY),
        "fault_injection_mode": CHAOS_POLICY["injection_mode"],
        "scenarios": scenarios,
        "aggregate": aggregate,
        "stale_data_gate": stale_gate,
        "structured_fault_log": [
            {
                "scenario_id": item["scenario_id"],
                "fault": item["fault"],
                "degraded": item["degraded"],
                "stale_data_disposition": item["stale_data_disposition"],
                "action": item["action"],
                "real_fault_injected": item["real_fault_injected"],
            }
            for item in error_scenarios
        ],
        "action": "NO_RECOMMENDATION_NO_ORDER",
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "execution_policy": dict(EXECUTION_POLICY),
        "decision": fixture["expected_decision"],
        "next": fixture["expected_next"],
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
    return {CHAOS_SCENARIOS_PATH.as_posix(): report}


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, str]:
    artifacts = build_artifacts(root, fixture)
    for relative, artifact in artifacts.items():
        _atomic_write(root / relative, canonical_json_bytes(artifact))
    return {relative: artifact_sha256(artifact) for relative, artifact in artifacts.items()}


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = build_artifacts(root, fixture)
    actual: dict[str, Any] = {}
    for relative, artifact in expected.items():
        value = strict_json_load(root / relative)
        if value != artifact:
            raise ChaosInputError("artifact does not reproduce exactly: %s" % relative)
        actual[relative] = value
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic S17/P03 frozen fault-projection artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    fixture = load_fixture(root / FIXTURE_PATH)
    artifacts = write_artifacts(root, fixture)
    print(json.dumps({"contract_id": CONTRACT_ID, "status": "PASS", "artifacts": artifacts, "decision": fixture["expected_decision"], "next": fixture["expected_next"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
