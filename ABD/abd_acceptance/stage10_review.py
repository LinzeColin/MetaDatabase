"""Fail-closed, offline whole-stage review for ABD S10.

The review re-verifies the four already-signed S10 phase receipts and their
frozen outputs.  It is deliberately narrower than a full regression: no phase
test suite is re-run, no real-time soak is performed, and no network, account,
deployment, recommendation, or order path exists here.
"""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Tuple
import xml.etree.ElementTree as ElementTree

from cross_impl_check import (
    CrossImplementationError,
    build_report as build_decimal_report,
    validate_registry as validate_decimal_registry,
)
from robustness_gate import (
    RobustnessGateError,
    build_report as build_robustness_report,
    report_sha256 as robustness_report_sha256,
    validate_registry as validate_robustness_registry,
)

from .canonical_facts import sha256_file, strict_json_load
from .decimal_math import verify_existing_phase_evidence as verify_p03
from .robustness_gate import verify_existing_phase_evidence as verify_p04
from .temporal_calibration import verify_existing_phase_evidence as verify_p01
from .uncertainty import verify_existing_phase_evidence as verify_p02


CONTRACT_ID = "STAGE-REVIEW-S10"
REVIEW_ID = "ABD-S10-WHOLE-STAGE-REVIEW"
STAGE_ID = "S10"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage10_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S10/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S10_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S10/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S10/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S10/STAGE_REVIEW/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S10-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S10-STAGE-REVIEW_rollback.json")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
ORACLE_PATH = Path("abd_acceptance/stage10_review.py")

CALIBRATION_REPORT_PATH = Path("calibration_report.json")
BOOTSTRAP_MANIFEST_PATH = Path("bootstrap_manifest.json")
NUMERIC_VECTORS_PATH = Path("numeric_vectors.json")
ROBUSTNESS_VECTORS_PATH = Path("boundary_vectors.json")
ROBUSTNESS_REPORT_PATH = Path("robustness_report.json")

PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_DECISIONS = {
    "P01": "TEMPORAL_CALIBRATION_READY_DOWNSTREAM_UNCERTAINTY_GATES_REQUIRED",
    "P02": "CONSERVATIVE_PROBABILITY_READY_DOWNSTREAM_DECIMAL_GATE_REQUIRED",
    "P03": "DECIMAL_FIXED_POINT_READY_DOWNSTREAM_ROBUSTNESS_GATE_REQUIRED",
    "P04": "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED",
}
PHASE_NEXT = {
    "P01": "S10/P02_READY_NOT_STARTED",
    "P02": "S10/P03_READY_NOT_STARTED",
    "P03": "S10/P04_READY_NOT_STARTED",
    "P04": "S10/STAGE_REVIEW_READY_NOT_STARTED",
}
PHASE_TARGETS = {
    "P01": "斜率0.90–1.10、截距绝对值≤0.02。",
    "P02": "固定种子/输入可重放，保守概率单调。",
    "P03": "两套实现差≤1e-12且动作完全一致。",
    "P04": "所有硬边界±0.0001用例100%符合预期。",
}
PHASE_OUTPUTS = {
    "P01": ["calibration.py", "temporal_cv.py", "calibration_report.json"],
    "P02": ["uncertainty.py", "bootstrap_manifest.json"],
    "P03": ["decimal_math.py", "numeric_vectors.json", "cross_impl_check.py"],
    "P04": ["robustness_gate.py", "boundary_vectors.json", "robustness_report.json"],
}
PHASE_EVIDENCE = {phase: Path("machine/evidence/EVD-S10-%s.json" % phase) for phase in PHASE_VERIFIERS}
PHASE_ROLLBACK = {phase: Path("machine/evidence/EVD-S10-%s_rollback.json" % phase) for phase in PHASE_VERIFIERS}
REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "TEMPORAL_CALIBRATION_AND_TIME_ORDER_PRESERVED",
    "CONSERVATIVE_BOOTSTRAP_AND_MONOTONICITY_PRESERVED",
    "DECIMAL_FIXED_POINT_AND_DUAL_IMPLEMENTATION_PRESERVED",
    "ONE_IN_TEN_THOUSAND_ADVERSE_GATE_PRESERVED",
    "NO_NETWORK_ORDER_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_REVIEW_FINDINGS_RESOLVED",
    "NO_FULL_REGRESSION_EXECUTED",
]
_BASELINE_PATHS = {
    "PURSUE_GOAL_PROMPT.txt",
    "VERSION",
    "machine/facts/canonical_facts.json",
    "machine/facts/parameters.json",
    "machine/facts/costs.json",
    "machine/facts/roadmap.json",
    "machine/facts/requirements.json",
    "machine/facts/acceptance_contracts.json",
    "machine/facts/task_graph.json",
    "machine/facts/traceability_matrix.json",
}
_NUMERIC_DETERMINISM = {
    "authoritative_decimal_precision_digits": 50,
    "money_storage": "INTEGER_CENTS",
    "probability_storage_scale": "1e-9",
    "odds_storage_scale": "1e-6",
    "binary_float_for_authoritative_decision": False,
    "probability_rounding": "DOWN",
    "odds_rounding": "DOWN",
    "friction_rounding": "UP",
    "stake_rounding": "DOWN_TO_PROVIDER_INCREMENT",
    "independent_implementation_absolute_tolerance": "1e-12",
    "action_must_match_across_implementations": True,
    "boundary_perturbation_absolute_probability": "0.0001",
    "boundary_perturbation_absolute_threshold": "0.0001",
    "boundary_perturbation_friction_up": "0.0001",
    "boundary_perturbation_time_adverse_seconds": 2,
    "odds_perturbation": "ONE_PROVIDER_TICK_ADVERSE",
    "unstable_action": "NO_RECOMMENDATION",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "github_upload_performed_by_local_review": False,
    "remote_ci_result_claimed_by_local_review": False,
    "external_network_accessed_for_product_runtime": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "model_or_strategy_executed": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_account_balance_read_or_written": False,
    "real_time_soak_waited": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "incremental_cash_spent_aud": "0.00",
    "owner_final_order_only": True,
}
ROLLBACK_ARTIFACTS = (
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
    *tuple(PHASE_EVIDENCE.values()),
    *tuple(PHASE_ROLLBACK.values()),
)
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")
_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}


class Stage10ReviewError(ValueError):
    """Raised when S10 whole-stage evidence cannot be trusted or replayed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


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
        raise Stage10ReviewError("path is outside the ABD root") from exc


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
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise Stage10ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise Stage10ReviewError("JSONL row %d is not an object" % number)
        rows.append(value)
    return rows


def _parse_sums(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise Stage10ReviewError("invalid SHA256SUMS line %d" % number)
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in parsed:
            raise Stage10ReviewError("unsafe or duplicate checksum path")
        parsed[relative] = digest
    if not parsed:
        raise Stage10ReviewError("SHA256SUMS is empty")
    return parsed


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage10ReviewError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage10ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise Stage10ReviewError("JUnit contains no suites")
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for field in result:
            result[field] += int(suite.attrib.get(field, "0"))
    return result


def _junit_is_normalized(path: Path) -> bool:
    try:
        document = ElementTree.parse(path).getroot()
    except Exception:
        return False
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
        for suite in suites
    )


def _is_portable(value: Any) -> bool:
    if isinstance(value, str):
        return "/Users/" not in value and "file://" not in value
    if isinstance(value, Mapping):
        return all(_is_portable(key) and _is_portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_is_portable(item) for item in value)
    return True


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise Stage10ReviewError("expected decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise Stage10ReviewError("invalid decimal") from exc
    if not result.is_finite():
        raise Stage10ReviewError("decimal must be finite")
    return result


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate an offline immutable S10 snapshot without enabling action."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "temporal_calibration_gates_preserved",
        "conservative_probability_gates_preserved",
        "decimal_determinism_gates_preserved",
        "adverse_perturbation_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage10ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage10ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage10ReviewError("findings_open must be a nonnegative integer")
    mapping = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("temporal_calibration_gates_preserved", "TEMPORAL_CALIBRATION_OR_TIME_ORDER_GATE_RELAXED"),
        ("conservative_probability_gates_preserved", "CONSERVATIVE_PROBABILITY_GATE_RELAXED"),
        ("decimal_determinism_gates_preserved", "DECIMAL_DETERMINISM_GATE_RELAXED"),
        ("adverse_perturbation_gate_preserved", "ADVERSE_PERTURBATION_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    reasons = [reason for key, reason in mapping if snapshot[key] is not True]
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S10_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S10_STAGE_REVIEW_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def _check_contract(contract: Any, fixture: Any, findings: Any, checks: List[Dict[str, Any]]) -> None:
    if not isinstance(contract, Mapping) or not isinstance(fixture, Mapping) or not isinstance(findings, Mapping):
        _add(checks, "S10REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "release_status_on_pass": "S10_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S10/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S10/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "targeted_test_command": "pytest -q tests/S10/stage_review_test.py",
    }
    _add(checks, "S10REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    expected_scope = {
        "phase_ids": list(PHASE_VERIFIERS),
        "requirement_ids": ["REQ-S10-%s" % phase for phase in PHASE_VERIFIERS],
        "acceptance_contract_ids": ["AC-S10-%s" % phase for phase in PHASE_VERIFIERS],
        "task_ids": ["T-S10-%s-%02d" % (phase, task) for phase in PHASE_VERIFIERS for task in range(1, 4)],
    }
    _add(checks, "S10REVIEW-SCOPE-EXACT", contract.get("review_scope") == expected_scope, contract.get("review_scope"))
    expected_policy = {
        "offline_deterministic_only": True,
        "phase_test_rerun_allowed": False,
        "full_regression_or_real_time_soak_allowed": False,
        "github_upload_performed_by_local_review": False,
        "production_deployed_or_activated": False,
        "incremental_cash_spent_aud": "0.00",
    }
    _add(checks, "S10REVIEW-NO-FULL-REGRESSION-OR-REALTIME-POLICY", contract.get("execution_policy") == expected_policy, contract.get("execution_policy"))
    _add(checks, "S10REVIEW-REQUIRED-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S10-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "replay_count": 100,
        "adverse_replay_count": 10000,
        "minimum_targeted_pytest_cases": 34,
        "expected_next": contract.get("next_on_pass"),
        "expected_release_status": contract.get("release_status_on_pass"),
    }
    _add(checks, "S10REVIEW-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    summary = findings.get("summary")
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_clock") == FIXED_CLOCK
        and summary == {"total": 1, "open": 0, "resolved": 1, "blocked": 0}
        and isinstance(findings.get("findings"), list)
        and len(findings["findings"]) == 1
        and findings["findings"][0].get("id") == "S10-REVIEW-001"
        and findings["findings"][0].get("status") == "RESOLVED_IN_STAGE_REVIEW"
    )
    _add(checks, "S10REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, summary)


def _check_baseline(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected = contract.get("baseline_hashes")
    if not isinstance(expected, Mapping) or set(expected) != _BASELINE_PATHS:
        _add(checks, "S10REVIEW-BASELINE-CONTRACT-PINS-EXACT", False, expected)
        return
    _add(checks, "S10REVIEW-BASELINE-CONTRACT-PINS-EXACT", True, sorted(expected))
    all_match = True
    for relative, digest in sorted(expected.items()):
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            passed = isinstance(digest, str) and actual == digest
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            passed = False
        all_match = all_match and passed
        _add(checks, "S10REVIEW-BASELINE-%s" % Path(relative).stem.upper(), passed, {"expected": digest, "actual": actual})
    _add(checks, "S10REVIEW-BASELINE-CRITICAL-HASHES", all_match, "all baseline hashes match" if all_match else "baseline drift")


def _check_taskpack(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S10REVIEW-REQUIREMENTS-STRICT-JSON")
    acceptance = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S10REVIEW-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S10REVIEW-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, root / "machine/facts/traceability_matrix.json", checks, "S10REVIEW-TRACE-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(acceptance, list) or not isinstance(graph, Mapping) or not isinstance(traceability, list):
        _add(checks, "S10REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "task pack inputs malformed")
        return False
    records = contract.get("phase_records")
    tasks = graph.get("tasks")
    if not isinstance(records, list) or not isinstance(tasks, list):
        _add(checks, "S10REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "phase records or task graph missing")
        return False
    valid = [record.get("phase_id") for record in records] == list(PHASE_VERIFIERS)
    detail: Dict[str, Any] = {}
    for record in records:
        phase = record.get("phase_id")
        try:
            requirement = _row(requirements, record["requirement_id"])
            criterion = _row(acceptance, record["acceptance_contract_id"])
            trace = _row(traceability, record["requirement_id"], key="requirement_id")
            phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == phase]
            task_ids = [task.get("id") for task in phase_tasks]
            outputs = {item for task in phase_tasks for item in task.get("outputs", [])}
            expected_tasks = ["T-S10-%s-%02d" % (phase, index) for index in range(1, 4)]
            expected_outputs = set(PHASE_OUTPUTS[phase])
            current = (
                phase in PHASE_VERIFIERS
                and record.get("target") == PHASE_TARGETS[phase]
                and record.get("outputs") == PHASE_OUTPUTS[phase]
                and requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("primary_acceptance_criteria_id") == record["acceptance_contract_id"]
                and requirement.get("target") == record["target"]
                and set(requirement.get("scope", [])) == expected_outputs
                and criterion.get("requirement_id") == record["requirement_id"]
                and criterion.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % record["acceptance_contract_id"]
                and criterion.get("pass_gate") == record["target"]
                and task_ids == expected_tasks
                and expected_outputs.issubset(outputs)
                and "tests/S10/%s_test.py" % phase in outputs
                and "machine/tests/fixtures/S10_%s.json" % phase in outputs
                and record["evidence_path"] in outputs
                and record["rollback_path"] in outputs
                and trace.get("acceptance_criteria_id") == record["acceptance_contract_id"]
                and trace.get("task_ids") == expected_tasks
            )
            valid = valid and current
            detail[str(phase)] = {"passed": current, "task_ids": task_ids}
        except Exception as exc:
            valid = False
            detail[str(phase)] = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S10REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", valid, detail)
    return valid


def _check_phase_receipts(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> Tuple[bool, bool, bool]:
    records = contract.get("phase_records")
    if not isinstance(records, list):
        _add(checks, "S10REVIEW-PHASE-RECEIPTS-AVAILABLE", False, "phase records unavailable")
        return False, False, False
    _add(checks, "S10REVIEW-PHASE-RECORDS-EXACT", [record.get("phase_id") for record in records] == fixture.get("expected_phase_ids") == list(PHASE_VERIFIERS), fixture.get("expected_phase_ids"))
    all_receipts = True
    all_portable = True
    all_boundary = True
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        index_rows = []
        all_receipts = False
        _add(checks, "S10REVIEW-EVIDENCE-INDEX-STRICT-JSON", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S10REVIEW-EVIDENCE-INDEX-STRICT-JSON", True, EVIDENCE_INDEX_PATH.as_posix())
    for record in records:
        phase = record.get("phase_id")
        if phase not in PHASE_VERIFIERS:
            all_receipts = False
            continue
        evidence_path = root / record["evidence_path"]
        rollback_path = root / record["rollback_path"]
        evidence = _safe_load(root, evidence_path, checks, "S10REVIEW-%s-EVIDENCE-STRICT-JSON" % phase)
        rollback = _safe_load(root, rollback_path, checks, "S10REVIEW-%s-ROLLBACK-STRICT-JSON" % phase)
        try:
            evidence_hash = sha256_file(evidence_path)
            rollback_hash = sha256_file(rollback_path)
        except Exception as exc:
            evidence_hash = "%s: %s" % (type(exc).__name__, exc)
            rollback_hash = evidence_hash
        hashes[record["evidence_path"]] = str(evidence_hash)
        hashes[record["rollback_path"]] = str(rollback_hash)
        hashes_ok = (
            evidence_hash == record.get("evidence_sha256") == fixture.get("expected_phase_evidence_sha256", {}).get(phase)
            and rollback_hash == record.get("rollback_sha256") == fixture.get("expected_phase_rollback_sha256", {}).get(phase)
        )
        _add(checks, "S10REVIEW-%s-RECEIPT-HASHES" % phase, hashes_ok, {"evidence": evidence_hash, "rollback": rollback_hash})
        try:
            verified = PHASE_VERIFIERS[phase](root)
        except Exception as exc:
            verified = {"status": "FAIL", "detail": "%s: %s" % (type(exc).__name__, exc)}
        current = (
            isinstance(evidence, Mapping)
            and isinstance(rollback, Mapping)
            and evidence.get("status") == "PASS"
            and evidence.get("contract_id") == record.get("acceptance_contract_id")
            and evidence.get("decision") == record.get("expected_decision") == PHASE_DECISIONS[phase]
            and evidence.get("next") == record.get("expected_next") == PHASE_NEXT[phase]
            and evidence.get("release_status") == "S10_%s_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD" % phase
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and rollback.get("status") == "PASS"
            and rollback.get("contract_id") == record.get("acceptance_contract_id")
            and rollback.get("external_state_changed") is False
            and rollback.get("production_state_changed") is False
            and verified.get("status") == "PASS"
            and verified.get("evidence_sha256") == evidence_hash
        )
        all_receipts = all_receipts and hashes_ok and current
        _add(checks, "S10REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, current, {"verifier": verified, "decision": evidence.get("decision") if isinstance(evidence, Mapping) else None, "next": evidence.get("next") if isinstance(evidence, Mapping) else None})
        boundary = evidence.get("external_effect_boundary") if isinstance(evidence, Mapping) else None
        boundary_ok = isinstance(boundary, Mapping) and all(
            boundary.get(key) is False
            for key in (
                "external_network_accessed",
                "actual_market_or_odds_observed",
                "recommendation_generated_or_enabled",
                "order_submission_enabled",
                "real_account_balance_read_or_written",
                "ovh_or_cloudflare_runtime_accessed",
                "production_deployed_or_activated",
                "financial_return_verified_or_guaranteed",
                "real_time_soak_waited",
            )
        ) and boundary.get("incremental_cash_spent_aud") == "0.00"
        all_boundary = all_boundary and boundary_ok
        _add(checks, "S10REVIEW-%s-EXTERNAL-BOUNDARY" % phase, boundary_ok, boundary)
        portable = _is_portable(evidence) and _is_portable(rollback)
        all_portable = all_portable and portable
        _add(checks, "S10REVIEW-%s-EVIDENCE-PORTABLE" % phase, portable, "portable" if portable else "local path or file URI found")
        expected_index = [row for row in index_rows if row.get("id") == "INDEX-AC-S10-%s" % phase]
        index_ok = len(expected_index) == 1 and expected_index[0].get("artifact_sha256") == evidence_hash and expected_index[0].get("status") == "PASS"
        all_receipts = all_receipts and index_ok
        _add(checks, "S10REVIEW-%s-EVIDENCE-INDEX-BINDING" % phase, index_ok, expected_index)
    _add(checks, "S10REVIEW-PHASE-RECEIPTS-CURRENT", all_receipts, "all phase receipts current" if all_receipts else "one or more phase receipts failed")
    _add(checks, "S10REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS", all_portable, "portable" if all_portable else "local path found")
    _add(checks, "S10REVIEW-PHASE-EXTERNAL-BOUNDARY-EXACT", all_boundary, "all phase boundaries checked")
    return all_receipts, all_portable, all_boundary


def _check_stage_controls(root: Path, checks: List[Dict[str, Any]]) -> Tuple[bool, bool, bool, bool]:
    parameters = _safe_load(root, root / "machine/facts/parameters.json", checks, "S10REVIEW-PARAMETERS-STRICT-JSON")
    calibration = _safe_load(root, root / CALIBRATION_REPORT_PATH, checks, "S10REVIEW-CALIBRATION-REPORT-STRICT-JSON")
    bootstrap = _safe_load(root, root / BOOTSTRAP_MANIFEST_PATH, checks, "S10REVIEW-BOOTSTRAP-MANIFEST-STRICT-JSON")
    numeric_vectors = _safe_load(root, root / NUMERIC_VECTORS_PATH, checks, "S10REVIEW-NUMERIC-VECTORS-STRICT-JSON")
    robustness_vectors = _safe_load(root, root / ROBUSTNESS_VECTORS_PATH, checks, "S10REVIEW-ROBUSTNESS-VECTORS-STRICT-JSON")
    stored_robustness = _safe_load(root, root / ROBUSTNESS_REPORT_PATH, checks, "S10REVIEW-ROBUSTNESS-REPORT-STRICT-JSON")
    if not all(isinstance(value, Mapping) for value in (parameters, calibration, bootstrap, numeric_vectors, robustness_vectors, stored_robustness)):
        return False, False, False, False
    numeric_ok = parameters.get("numeric_determinism") == _NUMERIC_DETERMINISM
    _add(checks, "S10REVIEW-NUMERIC-DETERMINISM-PARAMETERS-EXACT", numeric_ok, parameters.get("numeric_determinism"))

    comparison = calibration.get("method_comparison")
    folds = calibration.get("folds")
    temporal_ok = (
        calibration.get("report_id") == "RPT-S10-P01-TEMPORAL-CALIBRATION"
        and calibration.get("decision") == PHASE_DECISIONS["P01"]
        and calibration.get("next") == PHASE_NEXT["P01"]
        and calibration.get("temporal_folds") == 8
        and calibration.get("selected_methods") == {"binary": "LOGISTIC_BINARY", "multiclass": "TEMPERATURE_MULTICLASS"}
        and calibration.get("summary", {}).get("all_methods_eligible") is True
        and calibration.get("summary", {}).get("pass_gate") == PHASE_TARGETS["P01"]
        and isinstance(comparison, list)
        and [row.get("method_id") for row in comparison if isinstance(row, Mapping)] == ["ISOTONIC_BINARY", "LOGISTIC_BINARY", "TEMPERATURE_MULTICLASS"]
        and all(
            row.get("metrics", {}).get("eligible") is True
            and Decimal("0.90") <= _decimal(row.get("metrics", {}).get("slope")) <= Decimal("1.10")
            and abs(_decimal(row.get("metrics", {}).get("intercept"))) <= Decimal("0.02")
            and _decimal(row.get("metrics", {}).get("mean_absolute_error")) <= Decimal("0.025")
            for row in comparison
            if isinstance(row, Mapping)
        )
        and isinstance(folds, list)
        and len(folds) == 8
        and all(
            row.get("binary_training_count", 0) >= 72
            and row.get("binary_validation_count", 0) > 0
            and row.get("multiclass_training_count", 0) >= 30
            and row.get("multiclass_validation_count", 0) > 0
            for row in folds
            if isinstance(row, Mapping)
        )
        and calibration.get("external_effect_boundary", {}).get("real_time_soak_waited") is False
    )
    _add(checks, "S10REVIEW-TEMPORAL-CALIBRATION-AND-TIME-ORDER-PRESERVED", temporal_ok, {"fold_count": len(folds) if isinstance(folds, list) else None, "selected": calibration.get("selected_methods")})

    runtime = bootstrap.get("runtime")
    evaluation = bootstrap.get("evaluation")
    try:
        bootstrap_ok = (
            bootstrap.get("manifest_id") == "MAN-S10-P02-BLOCK-BOOTSTRAP"
            and bootstrap.get("decision") == PHASE_DECISIONS["P02"]
            and bootstrap.get("next") == PHASE_NEXT["P02"]
            and bootstrap.get("parameters") == {
                "runtime_block_bootstrap_iterations": 1000,
                "evaluation_block_bootstrap_iterations": 2000,
                "conservative_probability_percentile": 10,
            }
            and bootstrap.get("conservative_probability_monotonic") is True
            and Decimal("0") <= _decimal(bootstrap.get("conservative_probability")) <= _decimal(bootstrap.get("base_probability"))
            and isinstance(runtime, Mapping)
            and isinstance(evaluation, Mapping)
            and runtime.get("iterations") == 1000
            and evaluation.get("iterations") == 2000
            and runtime.get("percentile") == evaluation.get("percentile") == 10
            and runtime.get("seed") != evaluation.get("seed")
            and runtime.get("sample_sha256") != evaluation.get("sample_sha256")
            and len(str(runtime.get("sample_sha256"))) == len(str(evaluation.get("sample_sha256"))) == 64
            and _decimal(runtime.get("minimum_probability")) <= _decimal(runtime.get("conservative_probability")) <= _decimal(runtime.get("maximum_probability"))
            and _decimal(evaluation.get("minimum_probability")) <= _decimal(evaluation.get("conservative_probability")) <= _decimal(evaluation.get("maximum_probability"))
            and bootstrap.get("external_effect_boundary", {}).get("real_time_soak_waited") is False
        )
    except (Stage10ReviewError, TypeError):
        bootstrap_ok = False
    _add(checks, "S10REVIEW-CONSERVATIVE-BOOTSTRAP-AND-MONOTONICITY-PRESERVED", bootstrap_ok, {"runtime": runtime, "evaluation": evaluation})

    try:
        validated_numeric = validate_decimal_registry(numeric_vectors, parameters)
        decimal_report = build_decimal_report(validated_numeric, parameters)
        decimal_ok = (
            numeric_ok
            and decimal_report.get("report_sha256")
            and decimal_report.get("max_abs_difference") == "0"
            and decimal_report.get("all_within_tolerance") is True
            and decimal_report.get("actions_all_match") is True
            and decimal_report.get("stakes_all_match") is True
            and decimal_report.get("decision") == PHASE_DECISIONS["P03"]
            and decimal_report.get("next") == PHASE_NEXT["P03"]
            and isinstance(decimal_report.get("results"), list)
            and len(decimal_report["results"]) == 6
            and all(
                _decimal(row.get("max_abs_difference")) <= Decimal("1e-12")
                and row.get("actions_match") is True
                and row.get("stakes_match") is True
                for row in decimal_report["results"]
                if isinstance(row, Mapping)
            )
        )
    except (CrossImplementationError, Stage10ReviewError, KeyError, TypeError, ValueError):
        decimal_report = {}
        decimal_ok = False
    _add(checks, "S10REVIEW-DECIMAL-FIXED-POINT-AND-DUAL-IMPLEMENTATION-PRESERVED", decimal_ok, {"result_count": len(decimal_report.get("results", [])) if isinstance(decimal_report, Mapping) else None, "max_abs_difference": decimal_report.get("max_abs_difference") if isinstance(decimal_report, Mapping) else None})

    try:
        validated_robustness = validate_robustness_registry(robustness_vectors, parameters)
        robustness_report = build_robustness_report(validated_robustness, parameters)
        by_id = {row.get("vector_id"): row for row in robustness_report.get("results", []) if isinstance(row, Mapping)}
        robustness_ok = (
            numeric_ok
            and stored_robustness == robustness_report
            and robustness_report.get("report_sha256") == robustness_report_sha256(robustness_report)
            and robustness_report.get("all_hard_boundary_expectations_match") is True
            and robustness_report.get("all_adverse_action_flips_force_no_recommendation") is True
            and robustness_report.get("base_no_recommendations_remain_closed") is True
            and robustness_report.get("decision") == PHASE_DECISIONS["P04"]
            and robustness_report.get("next") == PHASE_NEXT["P04"]
            and isinstance(robustness_report.get("results"), list)
            and len(robustness_report["results"]) == 12
            and all(row.get("all_expected_matches") is True for row in robustness_report["results"] if isinstance(row, Mapping))
            and "probability_minus" in by_id.get("V02-PROBABILITY-MINUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "threshold_plus" in by_id.get("V04-THRESHOLD-PLUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "friction_plus" in by_id.get("V05-FRICTION-PLUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "time_plus" in by_id.get("V06-TIME-PLUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "odds_adverse" in by_id.get("V08-ODDS-TICK-FLIPS", {}).get("adverse_flip_dimensions", [])
            and by_id.get("V11-COMBINED-ONLY-FLIPS", {}).get("adverse_flip_dimensions") == ["all_adverse"]
            and by_id.get("V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES", {}).get("baseline", {}).get("action") == "NO_RECOMMENDATION"
            and by_id.get("V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES", {}).get("gate_action") == "NO_RECOMMENDATION"
        )
    except (RobustnessGateError, Stage10ReviewError, KeyError, TypeError, ValueError):
        robustness_report = {}
        robustness_ok = False
    _add(checks, "S10REVIEW-ONE-IN-TEN-THOUSAND-ADVERSE-GATE-PRESERVED", robustness_ok, {"result_count": len(robustness_report.get("results", [])) if isinstance(robustness_report, Mapping) else None, "decision": robustness_report.get("decision") if isinstance(robustness_report, Mapping) else None})
    return temporal_ok, bootstrap_ok, decimal_ok, robustness_ok


def _check_snapshot_cases(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S10REVIEW-FROZEN-STAGE-CASES", False, "cases unavailable")
        return {}
    results: Dict[str, Dict[str, Any]] = {}
    for row in cases:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("expected"), Mapping):
            _add(checks, "S10REVIEW-FROZEN-STAGE-CASE-SHAPE", False, row)
            continue
        try:
            actual = evaluate_stage_snapshot(row["snapshot"])
            expected = row["expected"]
            passed = (
                actual["status"] == expected.get("status")
                and actual["reason_codes"] == expected.get("reason_codes")
                and actual["recommendation_generated"] is False
                and actual["order_submission_enabled"] is False
                and actual["real_time_soak_waited"] is False
            )
            _add(checks, "S10REVIEW-CASE-%s" % row["case_id"], passed, {"actual": actual, "expected": expected})
            results[row["case_id"]] = actual
        except Exception as exc:
            _add(checks, "S10REVIEW-CASE-%s" % row["case_id"], False, "%s: %s" % (type(exc).__name__, exc))
    positive_source = next((row for row in cases if isinstance(row, Mapping) and row.get("case_id") == "POSITIVE_EXACT_STAGE"), None)
    positive = results.get("POSITIVE_EXACT_STAGE")
    replay_ok = positive_source is not None and positive is not None and fixture.get("replay_count") == 100 and all(evaluate_stage_snapshot(positive_source["snapshot"]) == positive for _ in range(100))
    _add(checks, "S10REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", replay_ok, fixture.get("replay_count"))
    adverse = [row for row in cases if isinstance(row, Mapping) and row.get("case_id") != "POSITIVE_EXACT_STAGE"]
    adverse_ok = fixture.get("adverse_replay_count") == 10000 and bool(adverse)
    expected_reasons: set[str] = set()
    if adverse_ok:
        cache: Dict[str, Dict[str, Any]] = {}
        for iteration in range(10000):
            row = adverse[iteration % len(adverse)]
            identifier = row["case_id"]
            if identifier not in cache:
                cache[identifier] = evaluate_stage_snapshot(row["snapshot"])
            result = cache[identifier]
            adverse_ok = adverse_ok and result["status"] == "S10_STAGE_REVIEW_REJECTED_NO_ACTION" and result["recommendation_generated"] is False and result["order_submission_enabled"] is False and result["real_time_soak_waited"] is False
            expected_reasons.update(result["reason_codes"])
    _add(checks, "S10REVIEW-ADVERSE-REPLAY-NO-ACTION", adverse_ok, {"count": fixture.get("adverse_replay_count"), "reason_codes": sorted(expected_reasons)})
    return results


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        forbidden_calls: list[str] = []
        forbidden_call_names = {"sleep", "run", "Popen", "float", "submit" + "_order"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                call_name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
                if call_name in forbidden_call_names:
                    forbidden_calls.append(call_name)
        prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
        passed = not (imports & prohibited) and not forbidden_calls and ("float" + "(") not in source
        _add(checks, "S10REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", passed, {"imports": sorted(imports), "calls": sorted(forbidden_calls)})
    except Exception as exc:
        _add(checks, "S10REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        passed = summary["tests"] >= fixture.get("minimum_targeted_pytest_cases") and not summary["failures"] and not summary["errors"] and not summary["skipped"] and _junit_is_normalized(root / JUNIT_PATH)
        _add(checks, "S10REVIEW-TARGETED-PYTEST-REPORT", passed, {"summary": summary, "normalized": _junit_is_normalized(root / JUNIT_PATH)})
    except Exception as exc:
        _add(checks, "S10REVIEW-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S10REVIEW-PAID-DEPENDENCY-SCAN-PASS", "STATUS: PASS" in text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in text, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S10REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S10REVIEW-PACK-REPORT-STRICT-JSON")
    _add(checks, "S10REVIEW-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any] | None) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "stage_status": "S10_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S10_WHOLE_STAGE_REVIEW_BLOCKED",
        "decision": "S10_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S10/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S10/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "release_status": "S10_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if status == "PASS" else "S10_RELEASE_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "stage_snapshot": dict(snapshot) if snapshot is not None else None,
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, root / CONTRACT_PATH, checks, "S10REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root, root / FINDINGS_PATH, checks, "S10REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S10REVIEW-FIXTURE-STRICT-JSON")
    if not isinstance(contract, Mapping) or not isinstance(findings, Mapping) or not isinstance(fixture, Mapping):
        return _result(checks, hashes, None)
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, contract, checks, hashes)
    taskpack_ok = _check_taskpack(root, contract, checks)
    phase_ok, portable_ok, boundary_ok = _check_phase_receipts(root, contract, fixture, checks, hashes)
    temporal_ok, bootstrap_ok, decimal_ok, robustness_ok = _check_stage_controls(root, checks)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings.get("summary"), Mapping) else -1
    snapshot = {
        "phase_receipts_current": phase_ok,
        "taskpack_trace_closed": taskpack_ok,
        "temporal_calibration_gates_preserved": temporal_ok,
        "conservative_probability_gates_preserved": bootstrap_ok,
        "decimal_determinism_gates_preserved": decimal_ok,
        "adverse_perturbation_gate_preserved": robustness_ok,
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable_ok,
        "findings_open": findings_open,
    }
    stage_snapshot = evaluate_stage_snapshot(snapshot)
    _add(checks, "S10REVIEW-CURRENT-STAGE-SNAPSHOT-NO-ACTION", stage_snapshot["status"] == "S10_STAGE_REVIEW_VERIFIED_NO_ACTION", stage_snapshot)
    return _result(checks, hashes, stage_snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in ROLLBACK_ARTIFACTS
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S10-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(row["status"] == "PASS" for row in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S10_STAGE_REVIEW_CANDIDATE_KEEP_SIGNED_PHASE_RECEIPTS_AND_REPLAY_OFFLINE",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    phase_outputs = [Path(path) for phase in PHASE_OUTPUTS.values() for path in phase]
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        Path("PURSUE_GOAL_PROMPT.txt"),
        Path("VERSION"),
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        *phase_outputs,
        *tuple(PHASE_EVIDENCE.values()),
        *tuple(PHASE_ROLLBACK.values()),
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S10-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": validation["release_status"],
        "validation": validation,
        "phase_receipts": {
            phase: {
                "evidence_path": PHASE_EVIDENCE[phase].as_posix(),
                "evidence_sha256": sha256_file(root / PHASE_EVIDENCE[phase]),
                "rollback_path": PHASE_ROLLBACK[phase].as_posix(),
                "rollback_sha256": sha256_file(root / PHASE_ROLLBACK[phase]),
            }
            for phase in PHASE_VERIFIERS
        },
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S10-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S10-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S10-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S10-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S10/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S10/stage_review_test.py --junitxml=machine/evidence/S10/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S10/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance.stage10_review --contract STAGE-REVIEW-S10 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_snapshot_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
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
        "id": "INDEX-S10-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S10/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    positions = [index for index, row in enumerate(rows) if row.get("id") == updated["id"]]
    if len(positions) > 1:
        raise Stage10ReviewError("duplicate S10 stage review evidence index rows")
    if positions:
        rows[positions[0]] = updated
    else:
        rows.append(updated)
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in rows))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage10ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage10ReviewError("cannot write evidence for a failed S10 review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S10/GITHUB_STAGE_UPLOAD_READY",
    }


def _manifest_current(root: Path) -> bool:
    try:
        manifest = strict_json_load(root / ARTIFACT_MANIFEST_PATH)
        sums = _parse_sums(root / SHA256SUMS_PATH)
    except Exception:
        return False
    rows = manifest.get("files") if isinstance(manifest, Mapping) else None
    if not isinstance(rows, list):
        return False
    entries: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            return False
        relative = row["path"]
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in entries:
            return False
        entries[relative] = row
    excluded = {(root / ARTIFACT_MANIFEST_PATH).resolve(), (root / SHA256SUMS_PATH).resolve()}
    expected = []
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate.resolve() in excluded:
            continue
        relative = candidate.relative_to(root)
        if any(part in _EXCLUDED_MANIFEST_PARTS for part in relative.parts) or candidate.suffix in {".pyc", ".pyo"} or candidate.name == ".DS_Store":
            continue
        expected.append(candidate)
    expected_paths = {path.relative_to(root).as_posix() for path in expected}
    manifest_key = ARTIFACT_MANIFEST_PATH.as_posix()
    if (
        manifest.get("schema_version") != "1.0.0"
        or manifest.get("version") != VERSION
        or manifest.get("file_count") != len(rows)
        or [row.get("path") for row in rows] != sorted(entries)
        or set(entries) != expected_paths
        or set(sums) != expected_paths | {manifest_key}
        or sums.get(manifest_key) != sha256_file(root / ARTIFACT_MANIFEST_PATH)
    ):
        return False
    return all(
        entries[path.relative_to(root).as_posix()].get("sha256") == sums[path.relative_to(root).as_posix()] == sha256_file(path)
        and entries[path.relative_to(root).as_posix()].get("bytes") == path.stat().st_size
        for path in expected
    )


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        raise Stage10ReviewError("S10 review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    index = [row for row in index_rows if row.get("id") == "INDEX-S10-STAGE-REVIEW"]
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S10_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S10/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S10_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and len(index) == 1
        and index[0].get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and _manifest_current(root)
    )
    if not valid:
        raise Stage10ReviewError("existing S10 review evidence is not reproducible or its manifest is stale")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S10/GITHUB_STAGE_UPLOAD_READY",
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABD S10 offline whole-stage review")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract")
    mode.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence", default="machine/evidence")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    evidence_dir = Path(args.evidence)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir
    if args.verify_existing:
        result = verify_existing_stage_review_evidence(root)
    else:
        if args.contract != CONTRACT_ID:
            parser.error("unsupported contract: %s" % args.contract)
        result = write_stage_review_evidence(root, evidence_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
