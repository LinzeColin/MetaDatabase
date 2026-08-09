"""Independent fail-closed acceptance oracle for ABD S13/P04.

The oracle replays only the frozen six-path journey catalog.  It does not
connect to a platform, account, mailbox, market, or deployment target; it
cannot submit or confirm an order and it cannot claim a real financial return.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ET

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .post_advice_settlement import verify_existing_phase_evidence as verify_post_advice_settlement_phase_evidence


CONTRACT_ID = "AC-S13-P04"
REQUIREMENT_ID = "REQ-S13-P04"
STAGE_ID = "S13"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"

JOURNEY_PATH = Path("journey_tests.json")
RECOVERY_PATH = Path("recovery_actions.json")
ORACLE_PATH = Path("abd_acceptance/journey_paths.py")
TEST_PATH = Path("tests/S13/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S13_P04.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S13-P03.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S13/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S13/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "journey:s13-p04-six-complete-paths"
JOURNEY_TYPES = ("WALKING_SKELETON", "GOLDEN", "BLACK", "ABUSE", "DEGRADED", "RECOVERY")
CLAIM_BOUNDARY = {
    "actual_market_or_odds_observed": False,
    "actual_order_execution_claimed": False,
    "external_network_accessed": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_account_accessed": False,
    "real_time_soak_waited": False,
    "system_order_confirmation_enabled": False,
}
_FACT_PATHS = (
    Path("machine/facts/canonical_facts.json"),
    Path("machine/facts/parameters.json"),
    Path("machine/facts/requirements.json"),
    Path("machine/facts/acceptance_contracts.json"),
    Path("machine/facts/task_graph.json"),
    Path("machine/facts/traceability_matrix.json"),
    Path("machine/facts/roadmap.json"),
)
_JOURNEY_FIELDS = {
    "journey_id",
    "journey_type",
    "input",
    "state_transitions",
    "output",
    "evidence_refs",
    "user_action_zh",
    "recovery_action_id",
    "synthetic_test_only",
}
_INPUT_FIELDS = {
    "input_id",
    "synthetic_test_only",
    "advice_state",
    "visible_odds",
    "minimum_odds",
    "identity_status",
    "risk_status",
    "component_status",
    "untrusted_content_detected",
}
_TRANSITION_FIELDS = {"from", "to"}
_OUTPUT_FIELDS = {"terminal_status", "automatic_order_submitted", "actual_return_claimed", "external_state_changed"}
_ACTION_FIELDS = {
    "action_id",
    "journey_id",
    "trigger_status",
    "steps",
    "terminal_status",
    "evidence_preserved",
    "external_state_changed",
    "production_state_changed",
    "actual_return_claimed",
    "order_submission_enabled",
    "synthetic_test_only",
}


class JourneyPathsAcceptanceError(ValueError):
    """Raised when a six-path journey delivery cannot be replayed safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, relative.as_posix())
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise JourneyPathsAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise JourneyPathsAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise JourneyPathsAcceptanceError("blank evidence-index row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise JourneyPathsAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(value)
    return rows


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _identifier(value: Any, prefix: str, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(prefix + r"[A-Z0-9-]{3,96}", value) is None:
        raise JourneyPathsAcceptanceError("%s is not a closed identifier" % field)
    return value


def _decimal_odds(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"[1-9]\d*\.\d{6}", value) is None:
        raise JourneyPathsAcceptanceError("%s must be six-place decimal text" % field)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise JourneyPathsAcceptanceError("%s is not decimal" % field) from exc
    if parsed <= Decimal("1.000000"):
        raise JourneyPathsAcceptanceError("%s must exceed one" % field)
    return parsed


def _chinese_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or re.search(r"[\u3400-\u9fff]", value) is None:
        raise JourneyPathsAcceptanceError("%s must be non-empty Chinese text" % field)
    return value


def _validate_input(value: Any, journey_type: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _INPUT_FIELDS or _contains_float(value):
        raise JourneyPathsAcceptanceError("journey input fields are not closed")
    if value.get("synthetic_test_only") is not True:
        raise JourneyPathsAcceptanceError("journey input must be frozen synthetic")
    advice_state = value.get("advice_state")
    identity_status = value.get("identity_status")
    risk_status = value.get("risk_status")
    component_status = value.get("component_status")
    untrusted = value.get("untrusted_content_detected")
    if journey_type in {"WALKING_SKELETON", "GOLDEN"}:
        expected = ("VALID", "MATCHED", "PASS", "HEALTHY", False)
    elif journey_type == "BLACK":
        expected = ("REVOKED", "MATCHED", "PASS", "HEALTHY", False)
    elif journey_type == "ABUSE":
        expected = ("UNTRUSTED", "UNTRUSTED", "FAIL", "QUARANTINE", True)
    elif journey_type == "DEGRADED":
        expected = ("VALID", "MATCHED", "PASS", "DEGRADED", False)
    elif journey_type == "RECOVERY":
        expected = ("EXPIRED", "MATCHED", "PASS", "RECOVERY_READY", False)
    else:
        raise JourneyPathsAcceptanceError("journey type is unknown")
    if (advice_state, identity_status, risk_status, component_status, untrusted) != expected:
        raise JourneyPathsAcceptanceError("journey input state is inconsistent with its type")
    visible = value.get("visible_odds")
    minimum = value.get("minimum_odds")
    if (visible is None) != (minimum is None):
        raise JourneyPathsAcceptanceError("visible and minimum odds must be present together")
    if visible is not None:
        visible_decimal = _decimal_odds(visible, "visible_odds")
        minimum_decimal = _decimal_odds(minimum, "minimum_odds")
        if journey_type in {"WALKING_SKELETON", "GOLDEN"} and visible_decimal != minimum_decimal:
            raise JourneyPathsAcceptanceError("green journey must hold the exact minimum odds")
        if journey_type == "BLACK" and visible_decimal != minimum_decimal - Decimal("0.000100"):
            raise JourneyPathsAcceptanceError("black journey must use the adverse 0.0001 odds boundary")
    elif journey_type in {"WALKING_SKELETON", "GOLDEN", "BLACK"}:
        raise JourneyPathsAcceptanceError("quote journey must include frozen visible and minimum odds")
    return deepcopy(dict(value))


def _validate_transitions(value: Any, journey_id: str) -> list[Dict[str, str]]:
    if not isinstance(value, list) or len(value) < 2:
        raise JourneyPathsAcceptanceError("%s needs at least two transitions" % journey_id)
    normalized: list[Dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != _TRANSITION_FIELDS:
            raise JourneyPathsAcceptanceError("%s transition fields are not closed" % journey_id)
        previous = item.get("from")
        current = item.get("to")
        if not isinstance(previous, str) or not isinstance(current, str) or not previous or not current or previous == current:
            raise JourneyPathsAcceptanceError("%s transition %d is invalid" % (journey_id, index))
        if index and normalized[-1]["to"] != previous:
            raise JourneyPathsAcceptanceError("%s transitions are not contiguous" % journey_id)
        normalized.append({"from": previous, "to": current})
    return normalized


def _validate_journey(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _JOURNEY_FIELDS or _contains_float(value):
        raise JourneyPathsAcceptanceError("journey fields are not closed")
    journey_type = value.get("journey_type")
    if journey_type not in JOURNEY_TYPES:
        raise JourneyPathsAcceptanceError("journey type is not closed")
    journey_id = _identifier(value.get("journey_id"), "S13-P04-", "journey_id")
    if journey_id != "S13-P04-" + journey_type.replace("_", "-"):
        raise JourneyPathsAcceptanceError("journey id must match its type")
    output = value.get("output")
    if not isinstance(output, Mapping) or set(output) != _OUTPUT_FIELDS:
        raise JourneyPathsAcceptanceError("journey output fields are not closed")
    terminal = output.get("terminal_status")
    if not isinstance(terminal, str) or not terminal:
        raise JourneyPathsAcceptanceError("journey terminal status is invalid")
    if output.get("automatic_order_submitted") is not False or output.get("actual_return_claimed") is not False or output.get("external_state_changed") is not False:
        raise JourneyPathsAcceptanceError("journey output exceeds the local-only claim boundary")
    evidence_refs = value.get("evidence_refs")
    if not isinstance(evidence_refs, list) or len(evidence_refs) != 4 or len(evidence_refs) != len(set(evidence_refs)):
        raise JourneyPathsAcceptanceError("journey evidence references are not closed")
    required_evidence = {"EVD-S13-P01", "EVD-S13-P02", "EVD-S13-P03"}
    if not required_evidence.issubset(set(evidence_refs)) or not any(item == "JOURNEY-" + journey_id for item in evidence_refs):
        raise JourneyPathsAcceptanceError("journey evidence references do not bind all S13 predecessors")
    recovery_action_id = _identifier(value.get("recovery_action_id"), "RECOVER-S13-P04-", "recovery_action_id")
    if recovery_action_id != "RECOVER-" + journey_id:
        raise JourneyPathsAcceptanceError("journey recovery action does not bind its id")
    if value.get("synthetic_test_only") is not True:
        raise JourneyPathsAcceptanceError("journey must be synthetic test only")
    return {
        "journey_id": journey_id,
        "journey_type": journey_type,
        "input": _validate_input(value.get("input"), journey_type),
        "state_transitions": _validate_transitions(value.get("state_transitions"), journey_id),
        "output": {"terminal_status": terminal, "automatic_order_submitted": False, "actual_return_claimed": False, "external_state_changed": False},
        "evidence_refs": list(evidence_refs),
        "user_action_zh": _chinese_text(value.get("user_action_zh"), "user_action_zh"),
        "recovery_action_id": recovery_action_id,
        "synthetic_test_only": True,
    }


def validate_journey_catalog(value: Any) -> Dict[str, Any]:
    expected = {"schema_version", "journey_catalog_id", "product_version", "fixed_clock", "input_mode", "claim_boundary", "journeys"}
    if not isinstance(value, Mapping) or set(value) != expected or _contains_float(value):
        raise JourneyPathsAcceptanceError("journey catalog fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("journey_catalog_id") != "S13-P04-SIX-COMPLETE-JOURNEYS"
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("input_mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        or value.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise JourneyPathsAcceptanceError("journey catalog header is not frozen")
    journeys = value.get("journeys")
    if not isinstance(journeys, list) or len(journeys) != len(JOURNEY_TYPES):
        raise JourneyPathsAcceptanceError("journey catalog must contain exactly six paths")
    normalized = [_validate_journey(item) for item in journeys]
    types = [item["journey_type"] for item in normalized]
    ids = [item["journey_id"] for item in normalized]
    if types != list(JOURNEY_TYPES) or len(ids) != len(set(ids)):
        raise JourneyPathsAcceptanceError("journey order or identity is not exact")
    return {
        "schema_version": "1.0.0",
        "journey_catalog_id": "S13-P04-SIX-COMPLETE-JOURNEYS",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "journeys": normalized,
    }


def validate_recovery_catalog(value: Any, journeys: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    expected = {"schema_version", "recovery_catalog_id", "product_version", "fixed_clock", "claim_boundary", "actions"}
    if not isinstance(value, Mapping) or set(value) != expected or _contains_float(value):
        raise JourneyPathsAcceptanceError("recovery catalog fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("recovery_catalog_id") != "S13-P04-RECOVERY-ACTIONS"
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise JourneyPathsAcceptanceError("recovery catalog header is not frozen")
    actions = value.get("actions")
    if not isinstance(actions, list) or len(actions) != len(JOURNEY_TYPES):
        raise JourneyPathsAcceptanceError("recovery catalog must contain six actions")
    journey_map = {item["journey_id"]: item for item in journeys}
    normalized: list[Dict[str, Any]] = []
    seen_actions: set[str] = set()
    for item in actions:
        if not isinstance(item, Mapping) or set(item) != _ACTION_FIELDS:
            raise JourneyPathsAcceptanceError("recovery action fields are not closed")
        action_id = _identifier(item.get("action_id"), "RECOVER-S13-P04-", "action_id")
        journey_id = item.get("journey_id")
        journey = journey_map.get(journey_id)
        if journey is None or action_id in seen_actions or action_id != journey["recovery_action_id"]:
            raise JourneyPathsAcceptanceError("recovery action does not bind one journey")
        seen_actions.add(action_id)
        steps = item.get("steps")
        if not isinstance(steps, list) or len(steps) < 3 or not all(isinstance(step, str) and re.fullmatch(r"[A-Z0-9_]{3,128}", step) for step in steps):
            raise JourneyPathsAcceptanceError("recovery action steps are invalid")
        terminal = item.get("terminal_status")
        if not isinstance(terminal, str) or not terminal:
            raise JourneyPathsAcceptanceError("recovery terminal is invalid")
        safe = (
            item.get("trigger_status") == journey["output"]["terminal_status"]
            and item.get("evidence_preserved") is True
            and item.get("external_state_changed") is False
            and item.get("production_state_changed") is False
            and item.get("actual_return_claimed") is False
            and item.get("order_submission_enabled") is False
            and item.get("synthetic_test_only") is True
        )
        if not safe:
            raise JourneyPathsAcceptanceError("recovery action exceeds local-only boundary")
        normalized.append({
            "action_id": action_id,
            "journey_id": journey_id,
            "trigger_status": item["trigger_status"],
            "steps": list(steps),
            "terminal_status": terminal,
            "evidence_preserved": True,
            "external_state_changed": False,
            "production_state_changed": False,
            "actual_return_claimed": False,
            "order_submission_enabled": False,
            "synthetic_test_only": True,
        })
    if [item["action_id"] for item in normalized] != [item["recovery_action_id"] for item in journeys]:
        raise JourneyPathsAcceptanceError("recovery action order is not exact")
    return {
        "schema_version": "1.0.0",
        "recovery_catalog_id": "S13-P04-RECOVERY-ACTIONS",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "actions": normalized,
    }


def replay_journeys(journey_catalog: Any, recovery_catalog: Any) -> Dict[str, Any]:
    """Replay the exact six path catalog and return only local synthetic outcomes."""

    journeys = validate_journey_catalog(journey_catalog)
    recovery = validate_recovery_catalog(recovery_catalog, journeys["journeys"])
    actions = {item["journey_id"]: item for item in recovery["actions"]}
    outcomes = [
        {
            "journey_id": journey["journey_id"],
            "journey_type": journey["journey_type"],
            "input_id": journey["input"]["input_id"],
            "transition_count": len(journey["state_transitions"]),
            "terminal_status": journey["output"]["terminal_status"],
            "evidence_refs": list(journey["evidence_refs"]),
            "user_action_zh": journey["user_action_zh"],
            "recovery_action_id": journey["recovery_action_id"],
            "recovery_terminal_status": actions[journey["journey_id"]]["terminal_status"],
            "automatic_order_submitted": False,
            "actual_return_claimed": False,
            "external_state_changed": False,
            "synthetic_test_only": True,
        }
        for journey in journeys["journeys"]
    ]
    payload = {"outcomes": outcomes, "claim_boundary": dict(CLAIM_BOUNDARY)}
    return {**payload, "replay_sha256": _canonical_sha256(payload)}


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S13P04-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S13P04-CONTRACTS-PARSE")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S13P04-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S13P04-TRACEABILITY-PARSE")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [item for item in graph["tasks"] if item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        scope_ok = (
            requirement.get("scope") == ["journey_tests.json", "recovery_actions.json"]
            and requirement.get("target") == "每类路径有输入、状态、输出、证据和恢复。"
            and requirement.get("value") == "实现Walking Skeleton、Golden、Black、Abuse、Degraded、Recovery路径。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
        )
        _add(checks, "S13P04-TASKPACK-SCOPE-EXACT", scope_ok, {"scope": requirement.get("scope"), "target": requirement.get("target")})
        trace_ok = (
            [item.get("id") for item in tasks] == ["T-S13-P04-01", "T-S13-P04-02", "T-S13-P04-03"]
            and tasks[0].get("depends_on") == ["T-S13-P03-03"]
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == ["TEST-S13-P04", "TEST-S13-P04-BOUNDARY", "TEST-S13-P04-REPLAY"]
            and trace.get("evidence_id") == "EVD-S13-P04"
            and trace.get("artifact_ids") == ["ART-S13-P04-01", "ART-S13-P04-02"]
        )
        _add(checks, "S13P04-TASKPACK-TRACE-CLOSED", trace_ok, {"tasks": [item.get("id") for item in tasks], "trace": trace})
    except Exception as exc:
        _add(checks, "S13P04-TASKPACK-TRACE-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        predecessor = verify_post_advice_settlement_phase_evidence(root)
        receipt = strict_json_load(root / PREDECESSOR_PATH)
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        index = _row(rows, "INDEX-AC-S13-P03")
        expected = fixture.get("predecessor") if isinstance(fixture, Mapping) else None
        actual_hash = sha256_file(root / PREDECESSOR_PATH)
        hashes[PREDECESSOR_PATH.as_posix()] = actual_hash
        passed = (
            isinstance(expected, Mapping)
            and predecessor.get("status") == "PASS"
            and predecessor.get("contract_id") == expected.get("contract_id") == "AC-S13-P03"
            and predecessor.get("next") == expected.get("next") == "S13/P04_READY_NOT_STARTED"
            and predecessor.get("evidence_sha256") == expected.get("evidence_sha256") == actual_hash
            and receipt.get("status") == "PASS"
            and receipt.get("next") == "S13/P04_READY_NOT_STARTED"
            and index.get("status") == "PASS"
            and index.get("artifact_sha256") == actual_hash
        )
        _add(checks, "S13P04-P03-PREDECESSOR-SIGNED-AND-INDEXED", passed, {"predecessor": predecessor, "index": index})
    except Exception as exc:
        _add(checks, "S13P04-P03-PREDECESSOR-SIGNED-AND-INDEXED", False, "%s: %s" % (type(exc).__name__, exc))


def _check_catalogs(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S13P04-FIXTURE-PARSE")
    journeys_source = _safe_load(root, JOURNEY_PATH, checks, "S13P04-JOURNEY-CATALOG-PARSE")
    recovery_source = _safe_load(root, RECOVERY_PATH, checks, "S13P04-RECOVERY-CATALOG-PARSE")
    if not isinstance(fixture, Mapping) or not isinstance(journeys_source, Mapping) or not isinstance(recovery_source, Mapping):
        return fixture if isinstance(fixture, Mapping) else None
    try:
        expected_fields = {
            "schema_version",
            "fixture_id",
            "fixed_clock",
            "parameters_sha256",
            "predecessor",
            "claim_boundary",
            "expected_journey_types",
            "expected_transition_counts",
            "expected_terminal_statuses",
            "expected_recovery_action_ids",
            "expected_replay_sha256",
            "expected_preflight_minimum",
            "expected_next",
        }
        fixture_ok = (
            set(fixture) == expected_fields
            and fixture.get("schema_version") == "1.0.0"
            and fixture.get("fixture_id") == "FIX-S13-P04-SIX-COMPLETE-JOURNEYS"
            and fixture.get("fixed_clock") == FIXED_CLOCK
            and fixture.get("claim_boundary") == CLAIM_BOUNDARY
            and fixture.get("expected_journey_types") == list(JOURNEY_TYPES)
            and fixture.get("expected_next") == "S13/STAGE_REVIEW_READY_NOT_STARTED"
            and isinstance(fixture.get("expected_preflight_minimum"), int)
            and not _contains_float(fixture)
        )
        _add(checks, "S13P04-FIXTURE-CONTRACT-EXACT", fixture_ok, {"fixture_id": fixture.get("fixture_id"), "fields": sorted(fixture)})
        parameter_hash = sha256_file(root / "machine/facts/parameters.json")
        _add(checks, "S13P04-PARAMETERS-HASH-EXACT", fixture.get("parameters_sha256") == parameter_hash, {"fixture": fixture.get("parameters_sha256"), "actual": parameter_hash})
        journeys = validate_journey_catalog(journeys_source)
        recovery = validate_recovery_catalog(recovery_source, journeys["journeys"])
        replay = replay_journeys(journeys, recovery)
        outcome_by_id = {item["journey_id"]: item for item in replay["outcomes"]}
        catalog_ok = (
            [item["journey_type"] for item in journeys["journeys"]] == fixture.get("expected_journey_types")
            and {item["journey_id"]: len(item["state_transitions"]) for item in journeys["journeys"]} == fixture.get("expected_transition_counts")
            and {item["journey_id"]: item["output"]["terminal_status"] for item in journeys["journeys"]} == fixture.get("expected_terminal_statuses")
            and [item["action_id"] for item in recovery["actions"]] == fixture.get("expected_recovery_action_ids")
            and all(item["journey_id"] in outcome_by_id for item in journeys["journeys"])
        )
        _add(checks, "S13P04-SIX-PATHS-INPUT-STATE-OUTPUT-EVIDENCE-RECOVERY-EXACT", catalog_ok, replay["outcomes"])
        _add(checks, "S13P04-DETERMINISTIC-REPLAY-EXACT", replay["replay_sha256"] == fixture.get("expected_replay_sha256"), replay["replay_sha256"])
        black = next(item for item in journeys["journeys"] if item["journey_type"] == "BLACK")
        golden = next(item for item in journeys["journeys"] if item["journey_type"] == "GOLDEN")
        black_visible = Decimal(str(black["input"]["visible_odds"]))
        black_minimum = Decimal(str(black["input"]["minimum_odds"]))
        golden_visible = Decimal(str(golden["input"]["visible_odds"]))
        golden_minimum = Decimal(str(golden["input"]["minimum_odds"]))
        boundary_ok = (
            black_visible == black_minimum - Decimal("0.000100")
            and golden_visible == golden_minimum
            and outcome_by_id[black["journey_id"]]["terminal_status"] == "RED_REVOKE_DO_NOT_ORDER"
            and all(item["actual_return_claimed"] is False and item["automatic_order_submitted"] is False and item["external_state_changed"] is False for item in replay["outcomes"])
        )
        _add(checks, "S13P04-POINT-0001-ADVERSE-ODDS-REVOKES-WITHOUT-ACTUAL-CLAIM", boundary_ok, {"black": outcome_by_id[black["journey_id"]], "golden": outcome_by_id[golden["journey_id"]]})
        recovery_ok = all(
            item["evidence_preserved"] is True
            and item["external_state_changed"] is False
            and item["production_state_changed"] is False
            and item["actual_return_claimed"] is False
            and item["order_submission_enabled"] is False
            for item in recovery["actions"]
        )
        _add(checks, "S13P04-ALL-RECOVERIES-PRESERVE-EVIDENCE-AND-LOCAL-ONLY", recovery_ok, recovery["actions"])
        for relative in (JOURNEY_PATH, RECOVERY_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
        return fixture
    except Exception as exc:
        _add(checks, "S13P04-SIX-PATH-RUNNER", False, "%s: %s" % (type(exc).__name__, exc))
        return fixture


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtp" + "lib", "asyncio", "time", "random", "os"}
    prohibited_literals = {"sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "web" + "hook", "smtp" + "lib"}
    failures: list[Any] = []
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        bad_imports = sorted(imports.intersection(prohibited_imports))
        bad_literals = sorted(item for item in prohibited_literals if item in source)
        if bad_imports or bad_literals:
            failures.append({"path": ORACLE_PATH.as_posix(), "imports": bad_imports, "literals": bad_literals})
    except Exception as exc:
        failures.append({"path": ORACLE_PATH.as_posix(), "error": "%s: %s" % (type(exc).__name__, exc)})
    for relative in (JOURNEY_PATH, RECOVERY_PATH):
        try:
            source = (root / relative).read_text(encoding="utf-8")
            bad_literals = sorted(item for item in prohibited_literals if item in source)
            if bad_literals:
                failures.append({"path": relative.as_posix(), "literals": bad_literals})
        except Exception as exc:
            failures.append({"path": relative.as_posix(), "error": "%s: %s" % (type(exc).__name__, exc)})
    _add(checks, "S13P04-STATIC-NO-NETWORK-SOAK-OR-ORDER", not failures, failures or "static boundary intact")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        scan = scan_dependency_budget(root)
        passed = scan.get("status") == "PASS" and scan.get("summary", {}).get("paid_or_unknown_dependencies") == 0
        _add(checks, "S13P04-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", passed, scan.get("summary"))
    except Exception as exc:
        _add(checks, "S13P04-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    }


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        cases = list(ET.parse(root / JUNIT_PATH).getroot().iter("testcase"))
        minimum = fixture.get("expected_preflight_minimum") if isinstance(fixture, Mapping) else None
        passed = (
            isinstance(minimum, int)
            and summary["tests"] >= minimum
            and not summary["failures"]
            and not summary["errors"]
            and not summary["skipped"]
            and all(case.attrib.get("time") == "0.000" for case in cases)
        )
        _add(checks, "S13P04-TARGETED-JUNIT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S13P04-TARGETED-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S13P04-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S13P04-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S13P04-TASKPACK-REPORT-PARSE")
    _add(checks, "S13P04-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "SIX_COMPLETE_SYNTHETIC_JOURNEYS_AND_LOCAL_RECOVERY_READY_STAGE_REVIEW_REQUIRED" if passed else "S13/P04_BLOCKED",
        "next": "S13/STAGE_REVIEW_READY_NOT_STARTED" if passed else "S13/P04_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "external_effect_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack_trace(root, checks)
    fixture = _check_catalogs(root, checks, hashes)
    _check_predecessor(root, fixture, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in (JOURNEY_PATH, RECOVERY_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S13_P04_JOURNEY_CATALOG_RESTORE_SIGNED_S13_P03_KEEP_ALL_EVIDENCE",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "actual_return_claimed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, JOURNEY_PATH, RECOVERY_PATH, TEST_PATH, FIXTURE_PATH, *_FACT_PATHS, PREDECESSOR_PATH]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S13/P04_test.py --junitxml=machine/evidence/S13/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S13/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S13/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S13-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"journey_count": 6, "adverse_scenario_count": 1, "real_time_wait_performed": False},
        "external_effect_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S13_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED",
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    if len(raw_lines) != len(rows):
        raise JourneyPathsAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-AC-S13-P04",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S13/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = sum(row.get("id") == replacement["id"] for row in rows)
    if matches != 1:
        raise JourneyPathsAcceptanceError("S13/P04 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise JourneyPathsAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise JourneyPathsAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/STAGE_REVIEW_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise JourneyPathsAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "SIX_COMPLETE_SYNTHETIC_JOURNEYS_AND_LOCAL_RECOVERY_READY_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S13/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("actual_return_claimed") is False
    )
    if not valid:
        raise JourneyPathsAcceptanceError("existing S13/P04 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/STAGE_REVIEW_READY_NOT_STARTED",
    }
