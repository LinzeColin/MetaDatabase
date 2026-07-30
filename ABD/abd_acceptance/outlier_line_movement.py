"""Independent fail-closed acceptance oracle for ABD S08/P04.

Only frozen synthetic quote fixtures are accepted. This oracle never opens a
network connection, accesses an account, emits a recommendation, submits an
order, deploys infrastructure, or performs elapsed-time waiting.
"""

from __future__ import annotations

import ast
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from outlier_detector import (
    MAD_MULTIPLIER,
    OutlierDetectorError,
    build_report,
    canonical_json_bytes,
    evaluate_market_integrity,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S08-P04"
REQUIREMENT_ID = "REQ-S08-P04"
STAGE_ID = "S08"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

CORE_PATH = Path("outlier_detector.py")
LINE_PATH = Path("line_movement.py")
ARTIFACT_PATH = Path("outlier_fixtures.json")
ORACLE_PATH = Path("abd_acceptance/outlier_line_movement.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
BUDGET_PATH = Path("abd_acceptance/budget.py")
TEST_PATH = Path("tests/S08/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S08_P04.json")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P03.json")
P03_VECTORS_PATH = Path("consensus_vectors.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S08/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S08/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, BUDGET_PATH)

_PREDECESSOR = {
    "sha256": "b5e92c155f25f7b505f4129a4599af7425c117eda7a6828cbcbd7443a7ff367b",
    "contract_id": "AC-S08-P03",
    "status": "PASS",
    "next": "S08/P04_READY_NOT_STARTED",
}
_P03_VECTORS_SHA256 = "0fc10d3949080111b246120261c028e486b43a5e84b99a59cc32cbd0de186efb"
_IMMUTABLE_BASELINE_HASHES = {
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
_ROLLBACK_ARTIFACTS = (CORE_PATH, LINE_PATH, ARTIFACT_PATH, ORACLE_PATH, CLI_PATH, BUDGET_PATH, TEST_PATH, FIXTURE_PATH)
_MICROSECONDS_PER_SECOND = 1_000_000
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
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


class OutlierLineMovementAcceptanceError(ValueError):
    """Raised when the P04 acceptance receipt is not reproducible."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _portable(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise OutlierLineMovementAcceptanceError("path is outside the ABD root") from exc


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        portable = _portable(root, path)
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, portable)
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise OutlierLineMovementAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise OutlierLineMovementAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise OutlierLineMovementAcceptanceError("expected exactly one id=%s" % identifier)
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise OutlierLineMovementAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _decimal(value: Any, *, label: str, lower_bound: Decimal | None = None) -> Decimal:
    if not isinstance(value, str):
        raise OutlierLineMovementAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OutlierLineMovementAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or (lower_bound is not None and parsed <= lower_bound):
        raise OutlierLineMovementAcceptanceError("%s is outside accepted bounds" % label)
    return parsed


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise OutlierLineMovementAcceptanceError("%s must be an ISO-8601 timestamp" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OutlierLineMovementAcceptanceError("%s is not ISO-8601" % label) from exc
    if parsed.tzinfo is None:
        raise OutlierLineMovementAcceptanceError("%s must include a timezone" % label)
    return parsed


def _elapsed_microseconds(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    return ((delta.days * 86_400 + delta.seconds) * _MICROSECONDS_PER_SECOND) + delta.microseconds


def _lower_median(values: List[Decimal]) -> Decimal:
    if not values:
        raise OutlierLineMovementAcceptanceError("median requires values")
    return sorted(values)[(len(values) - 1) // 2]


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _IMMUTABLE_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S08P04-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S08P04-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S08P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S08P04-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S08P04-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S08P04-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise OutlierLineMovementAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        expected_outputs = {"outlier_detector.py", "line_movement.py", "outlier_fixtures.json"}
        passed = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "单一异常长赔率不能制造建议。"
            and set(requirement.get("scope", [])) == expected_outputs
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S08-P04 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S08-P04-01", "T-S08-P04-02", "T-S08-P04-03"]
            and expected_outputs.issubset(task_outputs)
        )
        _add(checks, "S08P04-TASKPACK-EXACT", passed, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S08P04-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, root / P03_EVIDENCE_PATH, checks, "S08P04-P03-EVIDENCE-STRICT-JSON")
    vectors = _safe_load(root, root / P03_VECTORS_PATH, checks, "S08P04-P03-VECTORS-STRICT-JSON")
    try:
        evidence_hash = sha256_file(root / P03_EVIDENCE_PATH)
        vectors_hash = sha256_file(root / P03_VECTORS_PATH)
        hashes[P03_EVIDENCE_PATH.as_posix()] = evidence_hash
        hashes[P03_VECTORS_PATH.as_posix()] = vectors_hash
        evidence_ok = isinstance(evidence, Mapping) and evidence_hash == _PREDECESSOR["sha256"] and all(
            evidence.get(key) == value for key, value in _PREDECESSOR.items() if key != "sha256"
        )
        vectors_ok = isinstance(vectors, Mapping) and vectors_hash == _P03_VECTORS_SHA256 and vectors.get("contract_id") == "AC-S08-P03" and vectors.get("phase_id") == "P03"
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-AC-S08-P03")
        index_ok = index.get("status") == "PASS" and index.get("artifact_sha256") == evidence_hash
        _add(checks, "S08P04-P03-RECEIPT-IMMUTABLE", evidence_ok, {"expected": _PREDECESSOR["sha256"], "actual": evidence_hash})
        _add(checks, "S08P04-P03-VECTORS-IMMUTABLE", vectors_ok, {"expected": _P03_VECTORS_SHA256, "actual": vectors_hash})
        _add(checks, "S08P04-P03-EVIDENCE-INDEX", index_ok, index)
    except Exception as exc:
        _add(checks, "S08P04-P03-PREDECESSOR-CHECK", False, "%s: %s" % (type(exc).__name__, exc))


def _check_parameter_alignment(root: Path, checks: List[Dict[str, Any]]) -> None:
    parameters = _safe_load(root, root / "machine/facts/parameters.json", checks, "S08P04-PARAMETERS-STRICT-JSON")
    if not isinstance(parameters, Mapping):
        return
    numeric = parameters.get("numeric_determinism")
    freshness = parameters.get("coverage_and_freshness")
    passed = (
        isinstance(numeric, Mapping)
        and isinstance(freshness, Mapping)
        and numeric.get("authoritative_decimal_precision_digits") == 50
        and numeric.get("binary_float_for_authoritative_decision") is False
        and numeric.get("boundary_perturbation_time_adverse_seconds") == 2
        and numeric.get("odds_storage_scale") == "1e-6"
        and freshness.get("outlier_mad_multiplier") == "3.5"
        and freshness.get("quote_usable_seconds", {}).get("15m_to_2h") == 90
    )
    _add(checks, "S08P04-PARAMETER-ALIGNMENT", passed, {"numeric_determinism": numeric, "coverage_and_freshness": freshness})


def _reference_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Independent reference calculation; it intentionally does not call P04 core."""

    if not isinstance(case, Mapping):
        raise OutlierLineMovementAcceptanceError("case must be an object")
    quotes = case.get("quotes")
    events = case.get("line_observations")
    if not isinstance(quotes, list) or len(quotes) < 3 or not isinstance(events, list) or len(events) < 3:
        raise OutlierLineMovementAcceptanceError("reference inputs incomplete")
    mad_multiplier = _decimal(case.get("mad_multiplier"), label="mad_multiplier", lower_bound=Decimal("0"))
    as_of = _timestamp(case.get("as_of"), label="as_of")
    quote_usable_seconds = case.get("quote_usable_seconds")
    max_time_skew_seconds = case.get("max_time_skew_seconds")
    min_confirmations = case.get("minimum_confirming_sources")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (quote_usable_seconds, max_time_skew_seconds, min_confirmations)):
        raise OutlierLineMovementAcceptanceError("reference integer configuration invalid")
    quote_by_source: Dict[str, Decimal] = {}
    for index, raw in enumerate(quotes):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("source_id"), str):
            raise OutlierLineMovementAcceptanceError("quote source invalid")
        source_id = raw["source_id"]
        if source_id in quote_by_source:
            raise OutlierLineMovementAcceptanceError("duplicate quote source")
        odds = _decimal(raw.get("odds"), label="quotes[%d].odds" % index, lower_bound=Decimal("1"))
        quote_by_source[source_id] = odds
    median = _lower_median(list(quote_by_source.values()))
    mad = _lower_median([abs(odds - median) for odds in quote_by_source.values()])
    threshold = mad * mad_multiplier
    outlier_ids = sorted(source_id for source_id, odds in quote_by_source.items() if abs(odds - median) > threshold)
    long_outlier_ids = sorted(source_id for source_id in outlier_ids if quote_by_source[source_id] > median)

    event_by_source: Dict[str, Mapping[str, Any]] = {}
    current_times: List[datetime] = []
    stale_ids: List[str] = []
    up_count = 0
    down_count = 0
    for index, raw in enumerate(events):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("source_id"), str):
            raise OutlierLineMovementAcceptanceError("line source invalid")
        source_id = raw["source_id"]
        if source_id in event_by_source:
            raise OutlierLineMovementAcceptanceError("duplicate line source")
        previous = _decimal(raw.get("previous_odds"), label="events[%d].previous_odds" % index, lower_bound=Decimal("1"))
        current = _decimal(raw.get("current_odds"), label="events[%d].current_odds" % index, lower_bound=Decimal("1"))
        previous_at = _timestamp(raw.get("previous_observed_at"), label="events[%d].previous_observed_at" % index)
        current_at = _timestamp(raw.get("current_observed_at"), label="events[%d].current_observed_at" % index)
        if current_at < previous_at or current_at > as_of:
            raise OutlierLineMovementAcceptanceError("line timestamp invalid")
        if source_id not in quote_by_source or quote_by_source[source_id] != current:
            raise OutlierLineMovementAcceptanceError("quote and line source/odds mismatch")
        age = _elapsed_microseconds(as_of, current_at)
        if age > quote_usable_seconds * _MICROSECONDS_PER_SECOND:
            stale_ids.append(source_id)
        if current > previous:
            up_count += 1
        elif current < previous:
            down_count += 1
        event_by_source[source_id] = raw
        current_times.append(current_at)
    if set(event_by_source) != set(quote_by_source):
        raise OutlierLineMovementAcceptanceError("quote and line source sets mismatch")
    skew = _elapsed_microseconds(max(current_times), min(current_times))
    if stale_ids:
        line_status = "BLOCK_STALE_QUOTES"
    elif skew > max_time_skew_seconds * _MICROSECONDS_PER_SECOND:
        line_status = "BLOCK_TIME_DESYNCHRONIZED"
    elif not up_count and not down_count:
        line_status = "NO_LINE_MOVEMENT"
    elif up_count >= min_confirmations and not down_count:
        line_status = "CONFIRMED_UP"
    elif down_count >= min_confirmations and not up_count:
        line_status = "CONFIRMED_DOWN"
    else:
        line_status = "BLOCK_UNCONFIRMED_LINE_MOVEMENT"
    reasons: List[str] = []
    if long_outlier_ids:
        reasons.append("LONG_ODDS_OUTLIER")
    elif outlier_ids:
        reasons.append("NON_LONG_ODDS_OUTLIER")
    if line_status == "BLOCK_STALE_QUOTES":
        reasons.append("STALE_QUOTE")
    elif line_status == "BLOCK_TIME_DESYNCHRONIZED":
        reasons.append("TIME_DESYNCHRONIZED")
    elif line_status == "BLOCK_UNCONFIRMED_LINE_MOVEMENT":
        reasons.append("UNCONFIRMED_LINE_MOVEMENT")
    return {
        "median_odds": _decimal_text(median),
        "median_absolute_deviation": _decimal_text(mad),
        "outlier_threshold": _decimal_text(threshold),
        "outlier_source_ids": outlier_ids,
        "long_outlier_source_ids": long_outlier_ids,
        "line_status": line_status,
        "gate": "ALLOW_DOWNSTREAM_MARKET_PRIOR" if not reasons else "BLOCK_NO_RECOMMENDATION",
        "downstream_market_prior_allowed": not reasons,
        "block_reasons": reasons,
    }


def _check_artifact(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S08P04-FIXTURE-STRICT-JSON")
    artifact = _safe_load(root, root / ARTIFACT_PATH, checks, "S08P04-ARTIFACT-STRICT-JSON")
    if not isinstance(fixture, Mapping) or not isinstance(artifact, Mapping):
        return
    try:
        expected_artifact = build_report(fixture)
        _add(checks, "S08P04-ARTIFACT-REPLAY-EXACT", artifact == expected_artifact, "recomputed from frozen P04 fixture")
        required_fixture = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S08-P04-OUTLIER-LINE-MOVEMENT",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "expected_next": "S08/STAGE_REVIEW_READY_NOT_STARTED",
            "fixed_clock": FIXED_CLOCK,
            "replay_count": 100,
            "adverse_replay_count": 10000,
            "fixed_seed": 8004,
            "expected_oracle_check_minimum": 34,
            "predecessor_evidence_sha256": _PREDECESSOR["sha256"],
            "predecessor_consensus_vectors_sha256": _P03_VECTORS_SHA256,
            "mad_multiplier": "3.5",
            "quote_usable_seconds": 90,
            "max_time_skew_seconds": 2,
            "minimum_confirming_sources": 2,
            "boundary_perturbation_odds": "0.0001",
        }
        _add(checks, "S08P04-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in required_fixture.items()), sorted(required_fixture))
        claim = fixture.get("claim_boundary")
        safe_claim = isinstance(claim, Mapping) and all(
            claim.get(key) is value
            for key, value in {
                "network_accessed": False,
                "actual_market_or_odds_observed": False,
                "recommendation_generated": False,
                "order_submission_enabled": False,
                "real_time_soak_required": False,
            }.items()
        ) and claim.get("incremental_cash_spent_aud") == "0.00"
        _add(checks, "S08P04-FIXTURE-NO-EXTERNAL-CLAIM", safe_claim, claim)
        report_boundary = artifact.get("external_effect_boundary")
        _add(checks, "S08P04-ARTIFACT-BOUNDARY", report_boundary == {
            "external_network_accessed": False,
            "real_market_or_odds_observed": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        }, report_boundary)
        fixture_cases = fixture.get("cases")
        artifact_cases = {item.get("id"): item for item in artifact.get("cases", []) if isinstance(item, Mapping)}
        if not isinstance(fixture_cases, list) or len(fixture_cases) != 6:
            raise OutlierLineMovementAcceptanceError("exactly six frozen P04 cases are required")
        for fixture_case in fixture_cases:
            if not isinstance(fixture_case, Mapping) or not isinstance(fixture_case.get("id"), str):
                raise OutlierLineMovementAcceptanceError("fixture P04 case invalid")
            identifier = fixture_case["id"]
            expected = fixture_case.get("expected")
            actual = artifact_cases.get(identifier)
            if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
                _add(checks, "S08P04-CASE-%s" % identifier, False, "expected or artifact case missing")
                continue
            detection = actual.get("outlier_detection") if isinstance(actual.get("outlier_detection"), Mapping) else {}
            movement = actual.get("line_movement") if isinstance(actual.get("line_movement"), Mapping) else {}
            expected_ok = (
                actual.get("gate") == expected.get("gate")
                and detection.get("outlier_source_ids") == expected.get("outlier_source_ids")
                and detection.get("long_outlier_source_ids") == expected.get("long_outlier_source_ids")
                and movement.get("status") == expected.get("line_status")
                and actual.get("downstream_market_prior_allowed") == expected.get("downstream_market_prior_allowed")
                and actual.get("recommendation_generated") is False
                and actual.get("recommendation_permitted") is False
            )
            _add(checks, "S08P04-CASE-%s" % identifier, expected_ok, {"expected": expected, "actual_gate": actual.get("gate"), "actual_outliers": detection.get("outlier_source_ids"), "actual_line_status": movement.get("status")})
            reference = _reference_case(fixture_case)
            reference_ok = (
                detection.get("median_odds") == reference["median_odds"]
                and detection.get("median_absolute_deviation") == reference["median_absolute_deviation"]
                and detection.get("outlier_threshold") == reference["outlier_threshold"]
                and detection.get("outlier_source_ids") == reference["outlier_source_ids"]
                and detection.get("long_outlier_source_ids") == reference["long_outlier_source_ids"]
                and movement.get("status") == reference["line_status"]
                and actual.get("gate") == reference["gate"]
                and actual.get("downstream_market_prior_allowed") == reference["downstream_market_prior_allowed"]
                and actual.get("block_reasons") == reference["block_reasons"]
            )
            _add(checks, "S08P04-INDEPENDENT-REFERENCE-%s" % identifier, reference_ok, reference)
        invalid_cases = fixture.get("invalid_cases")
        invalid_ok = isinstance(invalid_cases, list) and len(invalid_cases) == 5
        if isinstance(invalid_cases, list):
            for invalid_case in invalid_cases:
                try:
                    evaluate_market_integrity(invalid_case)
                except OutlierDetectorError:
                    continue
                invalid_ok = False
        _add(checks, "S08P04-INVALID-INPUT-FAILS-CLOSED", invalid_ok, "odds, source identity, timestamps, source-set and MAD negatives")
        for relative in (CORE_PATH, LINE_PATH, ARTIFACT_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (OutlierDetectorError, OutlierLineMovementAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S08P04-ARTIFACT-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    for path in (CORE_PATH, LINE_PATH):
        try:
            source = (root / path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as exc:
            _add(checks, "S08P04-%s-PARSE" % path.stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        imports = set()
        forbidden_calls: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen"}:
                forbidden_calls.append(node.func.attr)
        safe = not (imports & prohibited_imports) and not forbidden_calls
        _add(checks, "S08P04-%s-NO-NETWORK-PROCESS-OR-SOAK" % path.stem.upper(), safe, {"imports": sorted(imports), "calls": sorted(forbidden_calls)})
        float_literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]
        _add(checks, "S08P04-%s-DECIMAL-ONLY" % path.stem.upper(), "float(" not in source and not float_literals, "authoritative odds calculations are Decimal-only")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S08P04-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        _add(checks, "S08P04-TARGETED-PYTEST-REPORT", junit["tests"] >= 25 and not junit["failures"] and not junit["errors"] and not junit["skipped"], junit)
    except Exception as exc:
        _add(checks, "S08P04-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S08P04-SCAN-REPORT", "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S08P04-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S08P04-PACK-REPORT-STRICT-JSON")
    _add(checks, "S08P04-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "OUTLIER_AND_LINE_MOVEMENT_GATES_READY_STAGE_REVIEW_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S08/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S08/P04_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    _check_parameter_alignment(root, checks)
    _check_artifact(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in _ROLLBACK_ARTIFACTS
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S08_P04_OUTLIER_AND_LINE_DERIVATION_KEEP_P03_CONSENSUS_EVIDENCE",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        CORE_PATH, LINE_PATH, ARTIFACT_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH,
        Path("market_consensus.py"), Path("abd_acceptance/market_consensus.py"),
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"), Path("machine/facts/roadmap.json"), P03_EVIDENCE_PATH, P03_VECTORS_PATH,
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "downstream dispatcher or budget-scanner evolution must not invalidate phase-owned evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({
        "contract_id": evidence.get("contract_id"),
        "decision": evidence.get("decision"),
        "next": evidence.get("next"),
        "validation": evidence.get("validation"),
    }))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-P04",
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
        "shared_runtime_contract": _shared_runtime_contract(),
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S08/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S08/P04_test.py --junitxml=machine/evidence/S08/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S08/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S08-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S08_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    updated = {
        "id": "INDEX-AC-S08-P04",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S08/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise OutlierLineMovementAcceptanceError("planned S08/P04 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise OutlierLineMovementAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise OutlierLineMovementAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S08/STAGE_REVIEW_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise OutlierLineMovementAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-AC-S08-P04")
    current_hash = sha256_file(root / EVIDENCE_PATH)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "OUTLIER_AND_LINE_MOVEMENT_GATES_READY_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S08/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == current_hash
    )
    if not valid:
        raise OutlierLineMovementAcceptanceError("existing S08/P04 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": current_hash, "next": "S08/STAGE_REVIEW_READY_NOT_STARTED"}
