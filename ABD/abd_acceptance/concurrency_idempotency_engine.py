"""Deterministic local S17/P02 concurrency, retry, and idempotency controls.

This module models logical lanes only.  It never starts threads, contacts a
runtime, or treats a frozen replay as proof about a live VPS, ledger, or
ordering system.  Every synthetic input is accounted for before the local
gate can pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTRACT_ID = "AC-S17-P02"
REQUIREMENT_ID = "REQ-S17-P02"
STAGE_ID = "S17"
PHASE_ID = "P02"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_LOGICAL_CONCURRENCY_RETRY_IDEMPOTENCY_NOT_RUNTIME"
FIXTURE_PATH = Path("machine/tests/fixtures/S17_P02.json")
CONCURRENCY_TEST_PATH = Path("concurrency_test.py")
IDEMPOTENCY_REPORT_PATH = Path("idempotency_report.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P01.json")
COSTS_PATH = Path("machine/facts/costs.json")

_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_-]{2,79}")
_KEY = re.compile(r"[A-Z][A-Z0-9_-]{5,79}")

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
    "contract_id": "AC-S17-P01",
    "evidence_path": P01_EVIDENCE_PATH.as_posix(),
    "evidence_sha256": "2f8cc9265cea7eec0e28d6ae0608ba6548a75378d28b850e639509465bff2fa9",
    "status": "PASS",
    "next": "S17/P02_READY_NOT_STARTED",
}

CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "real_vps_resource_observed_or_measured": False,
    "real_runtime_concurrency_executed": False,
    "real_ledger_read_or_written": False,
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
    "runtime_thread_or_process_concurrency_allowed": False,
    "external_runtime_access_allowed": False,
    "incremental_cash_spent_aud": "0.00",
}

IDEMPOTENCY_POLICY = {
    "scheduler": "FROZEN_LOGICAL_LANE_SCHEDULER_NOT_RUNTIME_CONCURRENCY",
    "idempotency_key_scope": "ONE_LOCAL_SYNTHETIC_LEDGER_PROJECTION_PER_KEY_AND_PAYLOAD",
    "timeout_policy": "TIMEOUT_BEFORE_COMMIT_HAS_NO_STATE_CHANGE",
    "key_conflict_policy": "QUARANTINE_NO_RECOMMENDATION_NO_ORDER",
    "duplicate_suggestion_max": 0,
    "duplicate_ledger_event_max": 0,
    "adverse_probability_delta": "0.0001",
    "adverse_odds_rule": "ONE_PROVIDER_TICK_ADVERSE",
    "recommendation_enabled": False,
    "order_submission_enabled": False,
}

EXPECTED_SCENARIOS = (
    {
        "scenario_id": "ORDERED_SINGLE",
        "operations": [
            {
                "operation_id": "S17P02_ORDERED_001",
                "logical_clock": 10,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_ORDERED_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            }
        ],
        "expected": {
            "input_attempt_count": 1,
            "accepted_local_projection_count": 1,
            "suppressed_duplicate_attempt_count": 0,
            "timeout_no_state_change_count": 0,
            "quarantined_key_conflict_count": 0,
        },
    },
    {
        "scenario_id": "FAN_IN_DUPLICATE_8",
        "operations": [
            {
                "operation_id": "S17P02_FANIN_001",
                "logical_clock": 20,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_002",
                "logical_clock": 20,
                "lane": 1,
                "attempt": 2,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_003",
                "logical_clock": 20,
                "lane": 2,
                "attempt": 3,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_004",
                "logical_clock": 20,
                "lane": 3,
                "attempt": 4,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_005",
                "logical_clock": 20,
                "lane": 4,
                "attempt": 5,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_006",
                "logical_clock": 20,
                "lane": 5,
                "attempt": 6,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_007",
                "logical_clock": 20,
                "lane": 6,
                "attempt": 7,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_FANIN_008",
                "logical_clock": 20,
                "lane": 7,
                "attempt": 8,
                "idempotency_key": "S17P02_FANIN_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
        ],
        "expected": {
            "input_attempt_count": 8,
            "accepted_local_projection_count": 1,
            "suppressed_duplicate_attempt_count": 7,
            "timeout_no_state_change_count": 0,
            "quarantined_key_conflict_count": 0,
        },
    },
    {
        "scenario_id": "OUT_OF_ORDER_DELAYED",
        "operations": [
            {
                "operation_id": "S17P02_OOO_002",
                "logical_clock": 42,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_OOO_KEY_002",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_OOO_001",
                "logical_clock": 41,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_OOO_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_OOO_003",
                "logical_clock": 42,
                "lane": 1,
                "attempt": 2,
                "idempotency_key": "S17P02_OOO_KEY_002",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
        ],
        "expected": {
            "input_attempt_count": 3,
            "accepted_local_projection_count": 2,
            "suppressed_duplicate_attempt_count": 1,
            "timeout_no_state_change_count": 0,
            "quarantined_key_conflict_count": 0,
        },
    },
    {
        "scenario_id": "TIMEOUT_RETRY",
        "operations": [
            {
                "operation_id": "S17P02_TIMEOUT_001",
                "logical_clock": 50,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_TIMEOUT_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "TIMEOUT_BEFORE_COMMIT",
            },
            {
                "operation_id": "S17P02_TIMEOUT_002",
                "logical_clock": 51,
                "lane": 0,
                "attempt": 2,
                "idempotency_key": "S17P02_TIMEOUT_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_TIMEOUT_003",
                "logical_clock": 52,
                "lane": 1,
                "attempt": 3,
                "idempotency_key": "S17P02_TIMEOUT_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0000", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
        ],
        "expected": {
            "input_attempt_count": 3,
            "accepted_local_projection_count": 1,
            "suppressed_duplicate_attempt_count": 1,
            "timeout_no_state_change_count": 1,
            "quarantined_key_conflict_count": 0,
        },
    },
    {
        "scenario_id": "CONFLICT_QUARANTINE",
        "operations": [
            {
                "operation_id": "S17P02_CONFLICT_001",
                "logical_clock": 60,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_CONFLICT_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": -1, "probability_delta": "-0.0001", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_CONFLICT_002",
                "logical_clock": 60,
                "lane": 1,
                "attempt": 2,
                "idempotency_key": "S17P02_CONFLICT_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": -1, "probability_delta": "0.0001", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
        ],
        "expected": {
            "input_attempt_count": 2,
            "accepted_local_projection_count": 1,
            "suppressed_duplicate_attempt_count": 0,
            "timeout_no_state_change_count": 0,
            "quarantined_key_conflict_count": 1,
        },
    },
    {
        "scenario_id": "BOUNDARY_PLUS_MINUS_0001",
        "operations": [
            {
                "operation_id": "S17P02_BOUNDARY_001",
                "logical_clock": 70,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_BOUNDARY_KEY_001",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": -1, "probability_delta": "-0.0001", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
            {
                "operation_id": "S17P02_BOUNDARY_002",
                "logical_clock": 71,
                "lane": 0,
                "attempt": 1,
                "idempotency_key": "S17P02_BOUNDARY_KEY_002",
                "payload": {"event_type": "NO_RECOMMENDATION_AUDIT", "odds_tick_delta": 0, "probability_delta": "0.0001", "source_version": "0.0.0.1"},
                "fault": "NONE",
            },
        ],
        "expected": {
            "input_attempt_count": 2,
            "accepted_local_projection_count": 2,
            "suppressed_duplicate_attempt_count": 0,
            "timeout_no_state_change_count": 0,
            "quarantined_key_conflict_count": 0,
        },
    },
)


class ConcurrencyIdempotencyInputError(ValueError):
    """Raised when S17/P02 inputs are not the frozen fail-closed vectors."""


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
        raise ConcurrencyIdempotencyInputError("cannot read JSON artifact: %s" % path.as_posix()) from exc


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ConcurrencyIdempotencyInputError("%s fields are not exact" % label)
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ConcurrencyIdempotencyInputError("%s must be a nonnegative integer" % label)
    return value


def _validate_operation(value: Any, label: str) -> Mapping[str, Any]:
    operation = _closed_mapping(
        value,
        {"operation_id", "logical_clock", "lane", "attempt", "idempotency_key", "payload", "fault"},
        label,
    )
    if not isinstance(operation["operation_id"], str) or not _IDENTIFIER.fullmatch(operation["operation_id"]):
        raise ConcurrencyIdempotencyInputError("operation id is malformed")
    if not isinstance(operation["idempotency_key"], str) or not _KEY.fullmatch(operation["idempotency_key"]):
        raise ConcurrencyIdempotencyInputError("idempotency key is malformed")
    for key in ("logical_clock", "lane", "attempt"):
        _nonnegative_int(operation[key], "operation.%s" % key)
    if operation["attempt"] < 1:
        raise ConcurrencyIdempotencyInputError("operation attempt must start at one")
    payload = _closed_mapping(operation["payload"], {"event_type", "odds_tick_delta", "probability_delta", "source_version"}, "payload")
    if (
        payload["event_type"] != "NO_RECOMMENDATION_AUDIT"
        or type(payload["odds_tick_delta"]) is not int
        or payload["probability_delta"] not in {"-0.0001", "0.0000", "0.0001"}
        or payload["source_version"] != PRODUCT_VERSION
        or operation["fault"] not in {"NONE", "TIMEOUT_BEFORE_COMMIT"}
    ):
        raise ConcurrencyIdempotencyInputError("operation payload or fault is outside the frozen control boundary")
    return operation


def _validate_scenarios(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(EXPECTED_SCENARIOS):
        raise ConcurrencyIdempotencyInputError("scenario count is not exact")
    normalized: list[Mapping[str, Any]] = []
    seen_operation_ids: set[str] = set()
    for raw, expected in zip(value, EXPECTED_SCENARIOS):
        scenario = _closed_mapping(raw, {"scenario_id", "operations", "expected"}, "scenario")
        if scenario != expected:
            raise ConcurrencyIdempotencyInputError("scenario is not the frozen deterministic vector")
        if not isinstance(scenario["operations"], list) or not isinstance(scenario["expected"], Mapping):
            raise ConcurrencyIdempotencyInputError("scenario members are unavailable")
        for index, operation in enumerate(scenario["operations"]):
            checked = _validate_operation(operation, "scenario[%d].operation[%d]" % (len(normalized), index))
            if checked["operation_id"] in seen_operation_ids:
                raise ConcurrencyIdempotencyInputError("operation ids must be globally unique")
            seen_operation_ids.add(checked["operation_id"])
        normalized.append(scenario)
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
        "baseline_hashes",
        "predecessor",
        "idempotency_policy",
        "scenarios",
        "expected_decision",
        "expected_next",
        "minimum_targeted_pytest_cases",
    }
    fixture = _closed_mapping(value, required, "fixture")
    if (
        fixture["schema_version"] != "1.0.0"
        or fixture["fixture_id"] != "FIXTURE-S17-P02-001"
        or fixture["contract_id"] != CONTRACT_ID
        or fixture["requirement_id"] != REQUIREMENT_ID
        or fixture["stage_id"] != STAGE_ID
        or fixture["phase_id"] != PHASE_ID
        or fixture["product_version"] != PRODUCT_VERSION
        or fixture["fixed_clock"] != FIXED_CLOCK
        or fixture["input_mode"] != INPUT_MODE
        or fixture["baseline_hashes"] != BASELINE_HASHES
        or fixture["predecessor"] != PREDECESSOR
        or fixture["idempotency_policy"] != IDEMPOTENCY_POLICY
        or fixture["expected_decision"] != "S17_P02_IDEMPOTENCY_PASS_P03_REQUIRED"
        or fixture["expected_next"] != "S17/P03_READY_NOT_STARTED"
        or type(fixture["minimum_targeted_pytest_cases"]) is not int
        or fixture["minimum_targeted_pytest_cases"] < 28
    ):
        raise ConcurrencyIdempotencyInputError("fixture is not the exact S17/P02 contract")
    _validate_scenarios(fixture["scenarios"])
    return fixture


def load_fixture(path: Path) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(path))


def _validate_source_inputs(root: Path, fixture: Mapping[str, Any]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if actual != expected:
            raise ConcurrencyIdempotencyInputError("frozen baseline hash mismatch: %s" % relative)
    predecessor_path = root / P01_EVIDENCE_PATH
    if not predecessor_path.is_file() or sha256_file(predecessor_path) != fixture["predecessor"]["evidence_sha256"]:
        raise ConcurrencyIdempotencyInputError("P01 signed predecessor is unavailable or changed")
    predecessor = strict_json_load(predecessor_path)
    if (
        not isinstance(predecessor, Mapping)
        or predecessor.get("contract_id") != PREDECESSOR["contract_id"]
        or predecessor.get("status") != "PASS"
        or predecessor.get("next") != PREDECESSOR["next"]
        or predecessor.get("production_status") != "NOT_DEPLOYED_OR_ACTIVATED"
    ):
        raise ConcurrencyIdempotencyInputError("P01 predecessor does not preserve the local-only boundary")


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _projection_id(idempotency_key: str, payload_hash: str) -> str:
    return hashlib.sha256(("LOCAL_SYNTHETIC_LEDGER_PROJECTION\0" + idempotency_key + "\0" + payload_hash).encode("utf-8")).hexdigest()


def replay_scenario(scenario: Mapping[str, Any]) -> Mapping[str, Any]:
    """Replay one immutable vector in a deterministic logical-lane order."""

    matching = [item for item in EXPECTED_SCENARIOS if item["scenario_id"] == scenario.get("scenario_id")]
    if len(matching) != 1 or scenario != matching[0]:
        raise ConcurrencyIdempotencyInputError("scenario is not an approved frozen vector")
    operations = list(scenario["operations"])
    scheduled = sorted(operations, key=lambda item: (item["logical_clock"], item["lane"], item["attempt"], item["operation_id"]))
    key_state: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    projections: list[dict[str, str]] = []
    for operation in scheduled:
        payload_hash = _payload_sha256(operation["payload"])
        disposition = ""
        projection_id: str | None = None
        if operation["fault"] == "TIMEOUT_BEFORE_COMMIT":
            disposition = "TIMEOUT_NO_STATE_CHANGE"
        elif operation["idempotency_key"] not in key_state:
            key_state[operation["idempotency_key"]] = payload_hash
            projection_id = _projection_id(operation["idempotency_key"], payload_hash)
            projections.append({"idempotency_key": operation["idempotency_key"], "payload_sha256": payload_hash, "projection_id": projection_id})
            disposition = "ACCEPTED_LOCAL_PROJECTION"
        elif key_state[operation["idempotency_key"]] == payload_hash:
            disposition = "SUPPRESSED_DUPLICATE"
        else:
            disposition = "QUARANTINED_KEY_CONFLICT"
        records.append(
            {
                "operation_id": operation["operation_id"],
                "idempotency_key": operation["idempotency_key"],
                "payload_sha256": payload_hash,
                "fault": operation["fault"],
                "disposition": disposition,
                "projection_id": projection_id,
                "action": "NO_RECOMMENDATION_NO_ORDER",
            }
        )
    summary = {
        "input_attempt_count": len(records),
        "accepted_local_projection_count": sum(record["disposition"] == "ACCEPTED_LOCAL_PROJECTION" for record in records),
        "suppressed_duplicate_attempt_count": sum(record["disposition"] == "SUPPRESSED_DUPLICATE" for record in records),
        "timeout_no_state_change_count": sum(record["disposition"] == "TIMEOUT_NO_STATE_CHANGE" for record in records),
        "quarantined_key_conflict_count": sum(record["disposition"] == "QUARANTINED_KEY_CONFLICT" for record in records),
    }
    if summary != scenario["expected"]:
        raise ConcurrencyIdempotencyInputError("scenario result does not match the pinned outcome")
    if summary["input_attempt_count"] != sum(summary[key] for key in summary if key != "input_attempt_count"):
        raise ConcurrencyIdempotencyInputError("every operation must receive exactly one disposition")
    if len({projection["projection_id"] for projection in projections}) != len(projections):
        raise ConcurrencyIdempotencyInputError("duplicate local ledger projection was not suppressed")
    return {
        "scenario_id": scenario["scenario_id"],
        "input_order_operation_ids": [operation["operation_id"] for operation in operations],
        "scheduled_order_operation_ids": [operation["operation_id"] for operation in scheduled],
        "records": records,
        "local_synthetic_ledger_projections": projections,
        "summary": summary,
        "action": "NO_RECOMMENDATION_NO_ORDER",
        "real_runtime_concurrency_used": False,
    }


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    fixture = validate_fixture(fixture)
    _validate_source_inputs(root, fixture)
    scenarios = [replay_scenario(scenario) for scenario in fixture["scenarios"]]
    aggregate = {
        "input_attempt_count": sum(item["summary"]["input_attempt_count"] for item in scenarios),
        "accepted_local_projection_count": sum(item["summary"]["accepted_local_projection_count"] for item in scenarios),
        "suppressed_duplicate_attempt_count": sum(item["summary"]["suppressed_duplicate_attempt_count"] for item in scenarios),
        "timeout_no_state_change_count": sum(item["summary"]["timeout_no_state_change_count"] for item in scenarios),
        "quarantined_key_conflict_count": sum(item["summary"]["quarantined_key_conflict_count"] for item in scenarios),
    }
    accounted = aggregate["input_attempt_count"] == sum(value for key, value in aggregate.items() if key != "input_attempt_count")
    projections = [projection for scenario in scenarios for projection in scenario["local_synthetic_ledger_projections"]]
    report = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S17-P02-02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "source_generator": {
            "artifact_id": "ART-S17-P02-01",
            "path": CONCURRENCY_TEST_PATH.as_posix(),
            "sha256": sha256_file(root / CONCURRENCY_TEST_PATH),
        },
        "predecessor": dict(PREDECESSOR),
        "baseline_hashes": dict(BASELINE_HASHES),
        "idempotency_policy": dict(IDEMPOTENCY_POLICY),
        "concurrency_model": "FROZEN_LOGICAL_LANES_DETERMINISTIC_ORDER_NOT_RUNTIME_CONCURRENCY",
        "scenarios": scenarios,
        "aggregate": aggregate,
        "idempotency_gate": {
            "duplicate_suggestion_count": 0,
            "duplicate_ledger_event_count": 0,
            "suppressed_duplicate_attempt_count": aggregate["suppressed_duplicate_attempt_count"],
            "input_attempts_accounted": accounted,
            "local_projection_count": len(projections),
            "projection_identity_unique": len({projection["projection_id"] for projection in projections}) == len(projections),
            "passed": accounted and len({projection["projection_id"] for projection in projections}) == len(projections),
        },
        "structured_fault_log": [
            {
                "scenario_id": scenario["scenario_id"],
                "operation_id": record["operation_id"],
                "fault_or_control_disposition": record["disposition"],
                "action": record["action"],
            }
            for scenario in scenarios
            for record in scenario["records"]
            if record["disposition"] != "ACCEPTED_LOCAL_PROJECTION"
        ],
        "action": "NO_RECOMMENDATION_NO_ORDER",
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "execution_policy": dict(EXECUTION_POLICY),
        "decision": fixture["expected_decision"],
        "next": fixture["expected_next"],
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
    return {IDEMPOTENCY_REPORT_PATH.as_posix(): report}


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
            raise ConcurrencyIdempotencyInputError("artifact does not reproduce exactly: %s" % relative)
        actual[relative] = value
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic S17/P02 idempotency evidence artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    fixture = load_fixture(root / FIXTURE_PATH)
    artifacts = write_artifacts(root, fixture)
    print(
        json.dumps(
            {
                "contract_id": CONTRACT_ID,
                "status": "PASS",
                "artifacts": artifacts,
                "decision": fixture["expected_decision"],
                "next": fixture["expected_next"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
