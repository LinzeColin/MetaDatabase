"""Deterministic local S17/P01 full-history and 10x-load control engine.

This engine is deliberately a frozen, count-conserving replay.  It does not
benchmark, connect to, or make a capacity claim about the real OVH VPS-1.
Instead it proves that the declared local capacity envelope preserves every
synthetic input disposition and fails closed before runtime deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTRACT_ID = "AC-S17-P01"
REQUIREMENT_ID = "REQ-S17-P01"
STAGE_ID = "S17"
PHASE_ID = "P01"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_FULL_HISTORY_10X_LOAD_NOT_LIVE_VPS"
FIXTURE_PATH = Path("machine/tests/fixtures/S17_P01.json")
LOAD_TEST_PATH = Path("load_test.py")
LOAD_PROFILE_PATH = Path("load_profile.json")
CAPACITY_EVIDENCE_PATH = Path("capacity_evidence.json")
COSTS_PATH = Path("machine/facts/costs.json")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{2,79}")

PREDECESSOR_LAYOUT = {
    "AC-S15-P04": {
        "evidence_path": "machine/evidence/EVD-S15-P04.json",
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S16-P04": {
        "evidence_path": "machine/evidence/EVD-S16-P04.json",
        "next": "S16/STAGE_REVIEW_READY_NOT_STARTED",
    },
}

RESOURCE_CONTRACT = {
    "resource_id": "RES-OVH-EXISTING-VPS1",
    "resource_name": "OVH Singapore VPS-1",
    "ownership_basis": "OWNER_DECLARED_PREEXISTING_RESOURCE",
    "capability_status": "UNVERIFIED_IN_S00_P03",
    "incremental_cash_cost_aud": "0.00",
    "paid_tier_allowed": False,
    "automatic_overage_allowed": False,
    "on_unavailable_or_limit": "BLOCK_RUNTIME_DEPLOYMENT_KEEP_LOCAL_DEVELOPMENT_AND_EVIDENCE",
}

CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "real_vps_resource_observed_or_measured": False,
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
    "real_vps_load_or_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "incremental_cash_spent_aud": "0.00",
}

EXPECTED_LOAD_DEFINITION = {
    "history_scope": "FROZEN_SYNTHETIC_ALL_HISTORY_INDEX_NOT_REAL_MARKET",
    "baseline_event_count": 1200,
    "ten_x_event_count": 12000,
    "load_multiplier": 10,
    "resource_unit_cap": 10000,
    "safety_reserve_units": 1,
    "queue_cap": 12000,
    "silent_drop_max": 0,
    "adverse_probability_delta": "0.0001",
    "adverse_odds_rule": "ONE_PROVIDER_TICK_ADVERSE",
    "event_identity_digest_algorithm": "SHA-256",
}

EXPECTED_SCENARIOS = (
    {
        "scenario_id": "BASELINE_FULL_HISTORY",
        "load_multiplier": 1,
        "ingress_count": 1200,
        "accepted_count": 1200,
        "quarantined_count": 0,
        "resource_units": 1200,
        "queue_high_water": 1200,
        "action": "NO_RECOMMENDATION_NO_ORDER",
    },
    {
        "scenario_id": "TEN_X_FULL_HISTORY",
        "load_multiplier": 10,
        "ingress_count": 12000,
        "accepted_count": 12000,
        "quarantined_count": 0,
        "resource_units": 7500,
        "queue_high_water": 8500,
        "action": "NO_RECOMMENDATION_NO_ORDER",
    },
    {
        "scenario_id": "TEN_X_BOUNDARY_0_9999",
        "load_multiplier": 10,
        "ingress_count": 12000,
        "accepted_count": 12000,
        "quarantined_count": 0,
        "resource_units": 9999,
        "queue_high_water": 12000,
        "action": "NO_RECOMMENDATION_NO_ORDER",
    },
    {
        "scenario_id": "TEN_X_TRACKED_FAULT",
        "load_multiplier": 10,
        "ingress_count": 12000,
        "accepted_count": 11999,
        "quarantined_count": 1,
        "resource_units": 8000,
        "queue_high_water": 9000,
        "action": "NO_RECOMMENDATION_NO_ORDER",
    },
)


class LoadTestInputError(ValueError):
    """Raised when S17/P01 load-control inputs are not fail-closed."""


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
        raise LoadTestInputError("cannot read JSON artifact: %s" % path.as_posix()) from exc


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise LoadTestInputError("%s fields are not exact" % label)
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise LoadTestInputError("%s must be a stable identifier" % label)
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise LoadTestInputError("%s must be a nonnegative integer" % label)
    return value


def _load_cost_contract(root: Path) -> Mapping[str, Any]:
    costs = strict_json_load(root / COSTS_PATH)
    rows = costs.get("resource_costs") if isinstance(costs, Mapping) else None
    if not isinstance(rows, list):
        raise LoadTestInputError("cost resource rows are unavailable")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get("id") == RESOURCE_CONTRACT["resource_id"]]
    if len(matching) != 1:
        raise LoadTestInputError("VPS-1 cost contract must exist exactly once")
    row = matching[0]
    expected = {
        "name": RESOURCE_CONTRACT["resource_name"],
        "ownership_basis": RESOURCE_CONTRACT["ownership_basis"],
        "capability_status": RESOURCE_CONTRACT["capability_status"],
        "incremental_cash_cost_aud": RESOURCE_CONTRACT["incremental_cash_cost_aud"],
        "paid_tier_allowed": RESOURCE_CONTRACT["paid_tier_allowed"],
        "automatic_overage_allowed": RESOURCE_CONTRACT["automatic_overage_allowed"],
        "on_unavailable_or_limit": RESOURCE_CONTRACT["on_unavailable_or_limit"],
    }
    if any(row.get(key) != item for key, item in expected.items()):
        raise LoadTestInputError("VPS-1 cost contract is not the frozen zero-cash boundary")
    return row


def _validate_predecessors(value: Any) -> Mapping[str, Mapping[str, str]]:
    if not isinstance(value, Mapping) or set(value) != set(PREDECESSOR_LAYOUT):
        raise LoadTestInputError("predecessor layout is not exact")
    normalized: dict[str, Mapping[str, str]] = {}
    for contract_id, layout in PREDECESSOR_LAYOUT.items():
        row = _closed_mapping(value.get(contract_id), {"evidence_path", "evidence_sha256", "status", "next"}, contract_id)
        if (
            row["evidence_path"] != layout["evidence_path"]
            or not isinstance(row["evidence_sha256"], str)
            or not _SHA256.fullmatch(row["evidence_sha256"])
            or row["status"] != "PASS"
            or row["next"] != layout["next"]
        ):
            raise LoadTestInputError("predecessor %s is malformed" % contract_id)
        normalized[contract_id] = row
    return normalized


def _validate_scenarios(value: Any, definition: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(EXPECTED_SCENARIOS):
        raise LoadTestInputError("scenario count is not exact")
    normalized: list[Mapping[str, Any]] = []
    effective_resource_cap = definition["resource_unit_cap"] - definition["safety_reserve_units"]
    for raw, expected in zip(value, EXPECTED_SCENARIOS):
        row = _closed_mapping(raw, set(expected), "scenario")
        if any(row.get(key) != item for key, item in expected.items()):
            raise LoadTestInputError("scenario is not the frozen deterministic vector")
        for key in ("load_multiplier", "ingress_count", "accepted_count", "quarantined_count", "resource_units", "queue_high_water"):
            _nonnegative_int(row[key], "scenario.%s" % key)
        if row["accepted_count"] + row["quarantined_count"] != row["ingress_count"]:
            raise LoadTestInputError("scenario must conserve every input disposition")
        if row["resource_units"] > effective_resource_cap:
            raise LoadTestInputError("scenario exceeds the reserved local VPS-1 envelope")
        if row["queue_high_water"] > definition["queue_cap"]:
            raise LoadTestInputError("scenario queue exceeds the frozen capacity cap")
        if row["action"] != "NO_RECOMMENDATION_NO_ORDER":
            raise LoadTestInputError("load replay must never enable an action")
        normalized.append(row)
    return normalized


def validate_fixture(value: Any) -> Mapping[str, Any]:
    required = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "costs_sha256",
        "predecessors",
        "resource_contract",
        "load_definition",
        "scenarios",
        "minimum_targeted_pytest_cases",
        "expected_decision",
        "expected_next",
        "execution_policy",
        "claim_boundary",
    }
    fixture = _closed_mapping(value, required, "fixture")
    identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S17-P01-FROZEN-LOAD",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "resource_contract": RESOURCE_CONTRACT,
        "load_definition": EXPECTED_LOAD_DEFINITION,
        "minimum_targeted_pytest_cases": 26,
        "expected_decision": "S17_P01_FROZEN_FULL_HISTORY_10X_LOAD_PASS_P02_REQUIRED",
        "expected_next": "S17/P02_READY_NOT_STARTED",
        "execution_policy": EXECUTION_POLICY,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    if any(fixture.get(key) != item for key, item in identity.items()):
        raise LoadTestInputError("fixture identity is not exact")
    if not isinstance(fixture["costs_sha256"], str) or not _SHA256.fullmatch(fixture["costs_sha256"]):
        raise LoadTestInputError("fixture costs hash is invalid")
    _validate_predecessors(fixture["predecessors"])
    _validate_scenarios(fixture["scenarios"], fixture["load_definition"])
    return fixture


def load_fixture(path: Path | str) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(Path(path)))


def _read_predecessors(root: Path, fixture: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for contract_id in PREDECESSOR_LAYOUT:
        expected = fixture["predecessors"][contract_id]
        path = root / expected["evidence_path"]
        receipt = strict_json_load(path)
        actual_hash = sha256_file(path)
        if (
            not isinstance(receipt, Mapping)
            or actual_hash != expected["evidence_sha256"]
            or receipt.get("contract_id") != contract_id
            or receipt.get("status") != "PASS"
            or receipt.get("next") != expected["next"]
        ):
            raise LoadTestInputError("predecessor %s is no longer signed and current" % contract_id)
        rows.append({
            "contract_id": contract_id,
            "evidence_path": expected["evidence_path"],
            "evidence_sha256": actual_hash,
            "status": "PASS",
            "next": expected["next"],
        })
    return rows


def _scenario_result(row: Mapping[str, Any], definition: Mapping[str, Any]) -> dict[str, Any]:
    identity_payload = {
        "scenario_id": row["scenario_id"],
        "ingress_count": row["ingress_count"],
        "accepted_count": row["accepted_count"],
        "quarantined_count": row["quarantined_count"],
        "load_multiplier": row["load_multiplier"],
        "digest_algorithm": definition["event_identity_digest_algorithm"],
    }
    return {
        **dict(row),
        "dropped_count": 0,
        "accounted_count": row["accepted_count"] + row["quarantined_count"],
        "missing_disposition_count": 0,
        "identity_digest": hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest(),
        "replay_status": "PASS_COUNT_CONSERVING_NO_ACTION",
    }


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    root = root.resolve()
    fixture = validate_fixture(fixture)
    _load_cost_contract(root)
    if sha256_file(root / COSTS_PATH) != fixture["costs_sha256"]:
        raise LoadTestInputError("cost facts hash drift blocks the local VPS-1 contract")
    predecessors = _read_predecessors(root, fixture)
    definition = fixture["load_definition"]
    scenarios = [_scenario_result(row, definition) for row in fixture["scenarios"]]
    total_ingress = sum(row["ingress_count"] for row in scenarios)
    total_accounted = sum(row["accounted_count"] for row in scenarios)
    total_dropped = sum(row["dropped_count"] for row in scenarios)
    profile: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S17-P01-02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "source_generator": {
            "artifact_id": "ART-S17-P01-01",
            "path": LOAD_TEST_PATH.as_posix(),
            "sha256": sha256_file(root / LOAD_TEST_PATH),
        },
        "costs_sha256": fixture["costs_sha256"],
        "resource_contract": dict(RESOURCE_CONTRACT),
        "load_definition": dict(definition),
        "scenarios": scenarios,
        "signed_predecessors": predecessors,
        "execution_policy": dict(EXECUTION_POLICY),
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    capacity: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S17-P01-03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "profile_path": LOAD_PROFILE_PATH.as_posix(),
        "profile_sha256": artifact_sha256(profile),
        "resource_gate": {
            "declared_resource_id": RESOURCE_CONTRACT["resource_id"],
            "local_envelope_passed": True,
            "actual_vps_capacity_measured": False,
            "actual_vps_capacity_claimed": False,
            "runtime_deployment_allowed": False,
            "on_resource_unavailable_or_limit": RESOURCE_CONTRACT["on_unavailable_or_limit"],
            "effective_resource_unit_cap": definition["resource_unit_cap"] - definition["safety_reserve_units"],
            "maximum_observed_resource_units": max(row["resource_units"] for row in scenarios),
            "queue_cap": definition["queue_cap"],
            "maximum_observed_queue_high_water": max(row["queue_high_water"] for row in scenarios),
        },
        "no_silent_data_loss": {
            "all_inputs_accounted": total_accounted == total_ingress,
            "silent_drop_count": total_dropped,
            "silent_drop_max": definition["silent_drop_max"],
            "tracked_quarantine_count": sum(row["quarantined_count"] for row in scenarios),
            "missing_disposition_count": sum(row["missing_disposition_count"] for row in scenarios),
            "passed": total_accounted == total_ingress and total_dropped == definition["silent_drop_max"],
        },
        "scenario_results": scenarios,
        "signed_predecessors": predecessors,
        "execution_policy": dict(EXECUTION_POLICY),
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "decision": fixture["expected_decision"],
        "next": fixture["expected_next"],
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    return {
        LOAD_PROFILE_PATH.as_posix(): profile,
        CAPACITY_EVIDENCE_PATH.as_posix(): capacity,
    }


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected = build_artifacts(root, fixture)
    for relative, value in expected.items():
        if strict_json_load(root / relative) != value:
            raise LoadTestInputError("artifact differs from deterministic replay: %s" % relative)
    return expected


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(data)
    temporary.replace(path)


def write_artifacts(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> dict[str, Mapping[str, Any]]:
    root = root.resolve()
    artifacts = build_artifacts(root, load_fixture(root / fixture_path))
    for relative, value in artifacts.items():
        _atomic_write(root / relative, canonical_json_bytes(value))
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate frozen local S17/P01 load artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()
    artifacts = write_artifacts(Path(args.root))
    print(
        json.dumps(
            {
                "contract_id": CONTRACT_ID,
                "status": "PASS",
                "artifacts": {path: artifact_sha256(value) for path, value in artifacts.items()},
                "decision": "S17_P01_FROZEN_FULL_HISTORY_10X_LOAD_PASS_P02_REQUIRED",
                "next": "S17/P02_READY_NOT_STARTED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
