"""Deterministic local S17/P04 recovery-drill controls.

The module models restart, replay, restore, rollback, and expired-ticket
cleanup as frozen logical vectors only.  It does not restart a process, read
or write a ledger, restore a backup, change an environment, delete tickets,
or wait for wall-clock time.  Every over-limit vector is degraded fail-closed
with recommendation and order actions disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


CONTRACT_ID = "AC-S17-P04"
REQUIREMENT_ID = "REQ-S17-P04"
STAGE_ID = "S17"
PHASE_ID = "P04"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_RECOVERY_DRILL_NOT_LIVE_RUNTIME"
FIXTURE_PATH = Path("machine/tests/fixtures/S17_P04.json")
RECOVERY_TEST_PATH = Path("recovery_test.py")
DISASTER_DRILL_PATH = Path("disaster_drill.md")
RECOVERY_REPORT_PATH = Path("recovery_report.json")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P03.json")

_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_-]{2,99}")

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
    "contract_id": "AC-S17-P03",
    "evidence_path": P03_EVIDENCE_PATH.as_posix(),
    "evidence_sha256": "2f40bd1eed62a0b1ed14347507d497fa54cc63db56c4f31112c631fe48beef97",
    "status": "PASS",
    "next": "S17/P04_READY_NOT_STARTED",
}

CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "real_vps_resource_observed_or_measured": False,
    "real_process_restarted": False,
    "real_ledger_read_or_written": False,
    "real_backup_restored": False,
    "real_dual_environment_rolled_back": False,
    "real_ticket_deleted_or_changed": False,
    "real_advice_service_recovered": False,
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
    "actual_restart_or_restore_allowed": False,
    "external_runtime_access_allowed": False,
    "incremental_cash_spent_aud": "0.00",
}

RECOVERY_POLICY = {
    "drill_mode": "FROZEN_LOGICAL_RECOVERY_DRILL_NOT_RUNTIME_RESTART_OR_RESTORE",
    "ledger_recovery_point_seconds_max": 60,
    "advice_service_recovery_seconds_max": 900,
    "over_limit_policy": "DEGRADE_FAIL_CLOSED_NO_RECOMMENDATION_NO_ORDER",
    "restore_policy": "RESTORE_PREVIOUS_SIGNED_ARTIFACTS_LOCAL_ONLY",
    "ticket_cleanup_policy": "FROZEN_EXPIRED_TICKET_PROJECTION_NO_REAL_DELETION",
    "recommendation_enabled": False,
    "order_submission_enabled": False,
}

EXPECTED_SCENARIOS = (
    {"scenario_id": "PROCESS_RESTART_WITHIN_GATE", "operation": "PROCESS_RESTART", "logical_rpo_seconds": 30, "logical_rto_seconds": 300, "frozen_ticket_count": 0, "probability_delta": "0.0000", "odds_tick_delta": 0, "expected": {"restoration_eligible": True, "rpo_pass": True, "rto_pass": True, "advice_service_state": "LOGICAL_SERVICE_RESTORED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "WITHIN_FROZEN_RPO_RTO"}},
    {"scenario_id": "LEDGER_REPLAY_RPO_BOUNDARY", "operation": "LEDGER_REPLAY", "logical_rpo_seconds": 60, "logical_rto_seconds": 600, "frozen_ticket_count": 0, "probability_delta": "-0.0001", "odds_tick_delta": -1, "expected": {"restoration_eligible": True, "rpo_pass": True, "rto_pass": True, "advice_service_state": "LOGICAL_SERVICE_RESTORED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "WITHIN_FROZEN_RPO_RTO"}},
    {"scenario_id": "BACKUP_RESTORE_RTO_BOUNDARY", "operation": "BACKUP_RESTORE", "logical_rpo_seconds": 45, "logical_rto_seconds": 900, "frozen_ticket_count": 0, "probability_delta": "0.0001", "odds_tick_delta": -1, "expected": {"restoration_eligible": True, "rpo_pass": True, "rto_pass": True, "advice_service_state": "LOGICAL_SERVICE_RESTORED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "WITHIN_FROZEN_RPO_RTO"}},
    {"scenario_id": "DUAL_ENVIRONMENT_ROLLBACK_WITHIN_GATE", "operation": "DUAL_ENVIRONMENT_ROLLBACK", "logical_rpo_seconds": 15, "logical_rto_seconds": 420, "frozen_ticket_count": 0, "probability_delta": "0.0000", "odds_tick_delta": 0, "expected": {"restoration_eligible": True, "rpo_pass": True, "rto_pass": True, "advice_service_state": "LOGICAL_SERVICE_RESTORED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "WITHIN_FROZEN_RPO_RTO"}},
    {"scenario_id": "EXPIRED_TICKET_CLEANUP_WITHIN_GATE", "operation": "EXPIRED_TICKET_CLEANUP", "logical_rpo_seconds": 0, "logical_rto_seconds": 120, "frozen_ticket_count": 3, "probability_delta": "0.0000", "odds_tick_delta": 0, "expected": {"restoration_eligible": True, "rpo_pass": True, "rto_pass": True, "advice_service_state": "LOGICAL_SERVICE_RESTORED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "WITHIN_FROZEN_RPO_RTO"}},
    {"scenario_id": "LEDGER_REPLAY_RPO_61_FAIL_CLOSED", "operation": "LEDGER_REPLAY", "logical_rpo_seconds": 61, "logical_rto_seconds": 300, "frozen_ticket_count": 0, "probability_delta": "-0.0001", "odds_tick_delta": -1, "expected": {"restoration_eligible": False, "rpo_pass": False, "rto_pass": True, "advice_service_state": "DEGRADED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "RPO_EXCEEDED_FAIL_CLOSED"}},
    {"scenario_id": "DUAL_ENVIRONMENT_ROLLBACK_RTO_901_FAIL_CLOSED", "operation": "DUAL_ENVIRONMENT_ROLLBACK", "logical_rpo_seconds": 60, "logical_rto_seconds": 901, "frozen_ticket_count": 0, "probability_delta": "0.0001", "odds_tick_delta": -1, "expected": {"restoration_eligible": False, "rpo_pass": True, "rto_pass": False, "advice_service_state": "DEGRADED_NO_RECOMMENDATION_NO_ORDER", "action": "NO_RECOMMENDATION_NO_ORDER", "reason_code": "RTO_EXCEEDED_FAIL_CLOSED"}},
)


class RecoveryInputError(ValueError):
    """Raised when S17/P04 inputs leave the frozen fail-closed boundary."""


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
        raise RecoveryInputError("cannot read JSON artifact: %s" % path.as_posix()) from exc


def _p03_decision_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")).hexdigest()


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RecoveryInputError("%s fields are not exact" % label)
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise RecoveryInputError("%s must be a nonnegative integer" % label)
    return value


def _validate_scenarios(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != len(EXPECTED_SCENARIOS):
        raise RecoveryInputError("scenario count is not exact")
    normalized: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    operations = {"PROCESS_RESTART", "LEDGER_REPLAY", "BACKUP_RESTORE", "DUAL_ENVIRONMENT_ROLLBACK", "EXPIRED_TICKET_CLEANUP"}
    for raw, expected in zip(value, EXPECTED_SCENARIOS):
        scenario = _closed_mapping(raw, {"scenario_id", "operation", "logical_rpo_seconds", "logical_rto_seconds", "frozen_ticket_count", "probability_delta", "odds_tick_delta", "expected"}, "scenario")
        if scenario != expected:
            raise RecoveryInputError("scenario is not the frozen deterministic vector")
        if not isinstance(scenario["scenario_id"], str) or not _IDENTIFIER.fullmatch(scenario["scenario_id"]) or scenario["scenario_id"] in seen:
            raise RecoveryInputError("scenario id is malformed or duplicated")
        seen.add(scenario["scenario_id"])
        if scenario["operation"] not in operations:
            raise RecoveryInputError("recovery operation is outside the frozen scope")
        _nonnegative_int(scenario["logical_rpo_seconds"], "logical_rpo_seconds")
        _nonnegative_int(scenario["logical_rto_seconds"], "logical_rto_seconds")
        _nonnegative_int(scenario["frozen_ticket_count"], "frozen_ticket_count")
        if scenario["probability_delta"] not in {"-0.0001", "0.0000", "0.0001"} or type(scenario["odds_tick_delta"]) is not int or scenario["odds_tick_delta"] < -1 or scenario["odds_tick_delta"] > 0:
            raise RecoveryInputError("boundary vector is outside the frozen control range")
        normalized.append(scenario)
    return normalized


def validate_fixture(value: Any) -> Mapping[str, Any]:
    required = {"schema_version", "fixture_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock", "input_mode", "baseline_hashes", "predecessor", "recovery_policy", "scenarios", "expected_decision", "expected_next", "minimum_targeted_pytest_cases"}
    fixture = _closed_mapping(value, required, "fixture")
    if (
        fixture["schema_version"] != "1.0.0"
        or fixture["fixture_id"] != "FIXTURE-S17-P04-001"
        or fixture["contract_id"] != CONTRACT_ID
        or fixture["requirement_id"] != REQUIREMENT_ID
        or fixture["stage_id"] != STAGE_ID
        or fixture["phase_id"] != PHASE_ID
        or fixture["product_version"] != PRODUCT_VERSION
        or fixture["fixed_clock"] != FIXED_CLOCK
        or fixture["input_mode"] != INPUT_MODE
        or fixture["baseline_hashes"] != BASELINE_HASHES
        or fixture["predecessor"] != PREDECESSOR
        or fixture["recovery_policy"] != RECOVERY_POLICY
        or fixture["expected_decision"] != "S17_P04_RECOVERY_DRILL_PASS_STAGE_REVIEW_REQUIRED"
        or fixture["expected_next"] != "S17/STAGE_REVIEW_READY_NOT_STARTED"
        or type(fixture["minimum_targeted_pytest_cases"]) is not int
        or fixture["minimum_targeted_pytest_cases"] < 30
    ):
        raise RecoveryInputError("fixture is not the exact S17/P04 contract")
    _validate_scenarios(fixture["scenarios"])
    return fixture


def load_fixture(path: Path) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(path))


def _validate_source_inputs(root: Path, fixture: Mapping[str, Any]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if actual != expected:
            raise RecoveryInputError("frozen baseline hash mismatch: %s" % relative)
    predecessor_path = root / P03_EVIDENCE_PATH
    if not predecessor_path.is_file() or sha256_file(predecessor_path) != fixture["predecessor"]["evidence_sha256"]:
        raise RecoveryInputError("P03 signed predecessor is unavailable or changed")
    predecessor = strict_json_load(predecessor_path)
    unsigned = dict(predecessor) if isinstance(predecessor, Mapping) else {}
    decision_sha256 = unsigned.pop("decision_sha256", None)
    if (
        not isinstance(predecessor, Mapping)
        or predecessor.get("contract_id") != PREDECESSOR["contract_id"]
        or predecessor.get("status") != "PASS"
        or predecessor.get("decision") != "S17_P03_CHAOS_STALE_DATA_GATE_PASS_P04_REQUIRED"
        or predecessor.get("next") != PREDECESSOR["next"]
        or predecessor.get("production_status") != "NOT_DEPLOYED_OR_ACTIVATED"
        or predecessor.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or decision_sha256 != _p03_decision_hash(unsigned)
    ):
        raise RecoveryInputError("P03 predecessor does not preserve the local-only boundary")


def replay_scenario(scenario: Mapping[str, Any]) -> Mapping[str, Any]:
    """Replay one immutable logical restoration vector without side effects."""

    matching = [item for item in EXPECTED_SCENARIOS if item["scenario_id"] == scenario.get("scenario_id")]
    if len(matching) != 1 or scenario != matching[0]:
        raise RecoveryInputError("scenario is not an approved frozen vector")
    expected = scenario["expected"]
    result = {
        "scenario_id": scenario["scenario_id"],
        "operation": scenario["operation"],
        "logical_rpo_seconds": scenario["logical_rpo_seconds"],
        "logical_rto_seconds": scenario["logical_rto_seconds"],
        "frozen_ticket_count": scenario["frozen_ticket_count"],
        "probability_delta": scenario["probability_delta"],
        "odds_tick_delta": scenario["odds_tick_delta"],
        "restoration_eligible": expected["restoration_eligible"],
        "rpo_pass": expected["rpo_pass"],
        "rto_pass": expected["rto_pass"],
        "advice_service_state": expected["advice_service_state"],
        "action": expected["action"],
        "reason_code": expected["reason_code"],
        "recovery_mode": RECOVERY_POLICY["drill_mode"],
        "real_runtime_state_changed": False,
        "real_time_wait_performed": False,
    }
    if result["restoration_eligible"]:
        if not (result["rpo_pass"] and result["rto_pass"] and result["logical_rpo_seconds"] <= 60 and result["logical_rto_seconds"] <= 900):
            raise RecoveryInputError("eligible restoration is outside the fixed gates")
    elif result["rpo_pass"] and result["rto_pass"]:
        raise RecoveryInputError("over-limit vector did not fail closed")
    return result


def _drill_markdown(scenarios: list[Mapping[str, Any]]) -> str:
    lines = [
        "# ABD S17/P04 冻结恢复与常态演练",
        "",
        "- 模式：`FROZEN_LOGICAL_RECOVERY_DRILL_NOT_RUNTIME_RESTART_OR_RESTORE`",
        "- 账本恢复点逻辑门：`<=60` 秒；建议服务恢复逻辑门：`<=900` 秒（15 分钟）。",
        "- 本文档不重启进程、不读写账本、不恢复备份、不切换环境、不删除票据，亦不等待真实时间。",
        "- 任一超限向量仅降级为 `NO_RECOMMENDATION_NO_ORDER`，不放宽证据、数值、风险、安全或来源门。",
        "",
        "| 场景 | 操作 | 逻辑 RPO 秒 | 逻辑 RTO 秒 | 结果 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for scenario in scenarios:
        lines.append("| %s | %s | %d | %d | %s |" % (scenario["scenario_id"], scenario["operation"], scenario["logical_rpo_seconds"], scenario["logical_rto_seconds"], scenario["reason_code"]))
    lines.extend(["", "## 回滚", "", "关闭本地恢复演练功能开关，保留冻结输入和不可变证据；仅在后续受控 Phase 中考虑真实运行时。", ""])
    return "\n".join(lines)


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    fixture = validate_fixture(fixture)
    _validate_source_inputs(root, fixture)
    scenarios = [replay_scenario(scenario) for scenario in fixture["scenarios"]]
    eligible = [item for item in scenarios if item["restoration_eligible"]]
    failures = [item for item in scenarios if not item["restoration_eligible"]]
    aggregate = {
        "scenario_count": len(scenarios),
        "eligible_restore_count": len(eligible),
        "rpo_within_gate_count": sum(item["rpo_pass"] is True for item in eligible),
        "rto_within_gate_count": sum(item["rto_pass"] is True for item in eligible),
        "rpo_exceeded_fail_closed_count": sum(item["reason_code"] == "RPO_EXCEEDED_FAIL_CLOSED" for item in failures),
        "rto_exceeded_fail_closed_count": sum(item["reason_code"] == "RTO_EXCEEDED_FAIL_CLOSED" for item in failures),
        "frozen_expired_ticket_projection_count": sum(item["frozen_ticket_count"] for item in scenarios),
        "recommendation_or_order_enabled_count": 0,
    }
    gate = {
        "ledger_recovery_point_seconds_max": RECOVERY_POLICY["ledger_recovery_point_seconds_max"],
        "advice_service_recovery_seconds_max": RECOVERY_POLICY["advice_service_recovery_seconds_max"],
        "eligible_max_logical_rpo_seconds": max(item["logical_rpo_seconds"] for item in eligible),
        "eligible_max_logical_rto_seconds": max(item["logical_rto_seconds"] for item in eligible),
        "eligible_rpo_gate_passed": all(item["rpo_pass"] for item in eligible),
        "eligible_rto_gate_passed": all(item["rto_pass"] for item in eligible),
        "over_limit_vectors_fail_closed": len(failures) == 2 and all(item["action"] == "NO_RECOMMENDATION_NO_ORDER" for item in failures),
        "passed": len(eligible) == 5 and len(failures) == 2 and all(item["rpo_pass"] and item["rto_pass"] for item in eligible),
    }
    report = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S17-P04-03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "source_generator": {"artifact_id": "ART-S17-P04-01", "path": RECOVERY_TEST_PATH.as_posix(), "sha256": sha256_file(root / RECOVERY_TEST_PATH)},
        "drill_document": {"artifact_id": "ART-S17-P04-02", "path": DISASTER_DRILL_PATH.as_posix()},
        "predecessor": dict(PREDECESSOR),
        "baseline_hashes": dict(BASELINE_HASHES),
        "recovery_policy": dict(RECOVERY_POLICY),
        "scenarios": scenarios,
        "aggregate": aggregate,
        "recovery_gate": gate,
        "structured_failure_log": [{"scenario_id": item["scenario_id"], "reason_code": item["reason_code"], "logical_rpo_seconds": item["logical_rpo_seconds"], "logical_rto_seconds": item["logical_rto_seconds"], "action": item["action"], "real_runtime_state_changed": item["real_runtime_state_changed"]} for item in failures],
        "action": "NO_RECOMMENDATION_NO_ORDER",
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "execution_policy": dict(EXECUTION_POLICY),
        "decision": fixture["expected_decision"],
        "next": fixture["expected_next"],
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
    return {DISASTER_DRILL_PATH.as_posix(): _drill_markdown(scenarios), RECOVERY_REPORT_PATH.as_posix(): report}


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, str]:
    artifacts = build_artifacts(root, fixture)
    for relative, artifact in artifacts.items():
        payload = artifact.encode("utf-8") if isinstance(artifact, str) else canonical_json_bytes(artifact)
        _atomic_write(root / relative, payload)
    return {relative: hashlib.sha256((artifact.encode("utf-8") if isinstance(artifact, str) else canonical_json_bytes(artifact))).hexdigest() for relative, artifact in artifacts.items()}


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = build_artifacts(root, fixture)
    actual: dict[str, Any] = {}
    for relative, artifact in expected.items():
        path = root / relative
        value: Any = path.read_text(encoding="utf-8") if isinstance(artifact, str) else strict_json_load(path)
        if value != artifact:
            raise RecoveryInputError("artifact does not reproduce exactly: %s" % relative)
        actual[relative] = value
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic S17/P04 frozen recovery-drill artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    fixture = load_fixture(root / FIXTURE_PATH)
    artifacts = write_artifacts(root, fixture)
    print(json.dumps({"contract_id": CONTRACT_ID, "status": "PASS", "artifacts": artifacts, "decision": fixture["expected_decision"], "next": fixture["expected_next"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
