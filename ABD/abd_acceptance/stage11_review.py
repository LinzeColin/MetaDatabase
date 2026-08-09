"""Fail-closed, offline whole-stage review for ABD S11.

The frozen Task Pack defines S11/P01--P04 but no stage-review task.  This
independent local addendum verifies those signed receipts without changing the
frozen phase baseline.  It is intentionally a small, targeted review: it does
not rerun phase test suites, run a full regression, wait in real time, access
the network, or enable a recommendation, account, deployment, or order path.
"""

from __future__ import annotations

import argparse
import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from decision_gate import artifact_sha256 as decision_gate_artifact_sha256
from platform_router import artifact_sha256 as platform_router_artifact_sha256
from risk_engine import artifact_sha256 as risk_engine_artifact_sha256

from .canonical_facts import sha256_file, strict_json_load
from .decision_gate import verify_existing_phase_evidence as verify_p02
from .friction import verify_existing_phase_evidence as verify_p01
from .platform_router import verify_existing_phase_evidence as verify_p03
from .risk_engine import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S11"
REVIEW_ID = "ABD-S11-WHOLE-STAGE-REVIEW"
STAGE_ID = "S11"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage11_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S11/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S11_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S11/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S11/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S11/STAGE_REVIEW/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S11-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S11-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
ORACLE_PATH = Path("abd_acceptance/stage11_review.py")

PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    "P01": {
        "requirement_id": "REQ-S11-P01",
        "contract_id": "AC-S11-P01",
        "target": "有效摩擦取默认与实测95分位较大者。",
        "outputs": ["friction.py", "friction_model.json", "friction_backtest.json"],
        "module_path": "abd_acceptance/friction.py",
        "test_path": "tests/S11/P01_test.py",
        "fixture_path": "machine/tests/fixtures/S11_P01.json",
        "evidence_path": "machine/evidence/EVD-S11-P01.json",
        "evidence_sha256": "4bf25a1a68e3078f512a7cbf0992285e2890d62b5284de24eefd750390b7e2f8",
        "rollback_path": "machine/evidence/EVD-S11-P01_rollback.json",
        "rollback_sha256": "24b22dbf26bd39184a5d84be3c55d8797464d40cb8616ce7a750763e33f7ca39",
        "decision": "FRICTION_READY_DOWNSTREAM_THRESHOLD_AND_RISK_GATES_REQUIRED",
        "next": "S11/P02_READY_NOT_STARTED",
        "release_status": "S11_P01_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
    },
    "P02": {
        "requirement_id": "REQ-S11-P02",
        "contract_id": "AC-S11-P02",
        "target": "所有阈值边界及万分之一扰动通过。",
        "outputs": ["decision_gate.py", "evidence_tiers.json", "threshold_vectors.json"],
        "module_path": "abd_acceptance/decision_gate.py",
        "test_path": "tests/S11/P02_test.py",
        "fixture_path": "machine/tests/fixtures/S11_P02.json",
        "evidence_path": "machine/evidence/EVD-S11-P02.json",
        "evidence_sha256": "59e814b20d237eff982ff763bb3573ba8c129e6817c4c1cf61e273c366bab065",
        "rollback_path": "machine/evidence/EVD-S11-P02_rollback.json",
        "rollback_sha256": "f6f68ab4a8ac3ceac8a672c48fb7e965679845f2e47002a65e8d35c8cffab118",
        "decision": "EVIDENCE_TIER_AND_MINIMUM_ODDS_READY_DOWNSTREAM_PLATFORM_AND_RISK_GATES_REQUIRED",
        "next": "S11/P03_READY_NOT_STARTED",
        "release_status": "S11_P02_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
    },
    "P03": {
        "requirement_id": "REQ-S11-P03",
        "contract_id": "AC-S11-P03",
        "target": "只显示一个最高分且全部门通过的平台。",
        "outputs": ["platform_router.py", "provider_score.json", "routing_fixtures.json"],
        "module_path": "abd_acceptance/platform_router.py",
        "test_path": "tests/S11/P03_test.py",
        "fixture_path": "machine/tests/fixtures/S11_P03.json",
        "evidence_path": "machine/evidence/EVD-S11-P03.json",
        "evidence_sha256": "c3d0c61870a37e6c8ee3e71650008fdcf23d4bc2da4d1ec9e83e8e846a4b12d4",
        "rollback_path": "machine/evidence/EVD-S11-P03_rollback.json",
        "rollback_sha256": "59abddacdf3c055a4a7fff7d10a2aa9c1b2d3386e8358204c54d642ee62f3ac7",
        "decision": "UNIQUE_SYNTHETIC_PLATFORM_ROUTE_READY_DOWNSTREAM_CONSTRAINED_KELLY_AND_RISK_GATES_REQUIRED",
        "next": "S11/P04_READY_NOT_STARTED",
        "release_status": "S11_P03_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
    },
    "P04": {
        "requirement_id": "REQ-S11-P04",
        "contract_id": "AC-S11-P04",
        "target": "任意属性测试不能越过风险上限。",
        "outputs": ["risk_engine.py", "correlation_graph.json", "risk_vectors.json"],
        "module_path": "abd_acceptance/risk_engine.py",
        "test_path": "tests/S11/P04_test.py",
        "fixture_path": "machine/tests/fixtures/S11_P04.json",
        "evidence_path": "machine/evidence/EVD-S11-P04.json",
        "evidence_sha256": "d9bc525ce3902cdda3ca6ad6253cc77ab69cddb4641b3d4d7e2c207f59c49ed2",
        "rollback_path": "machine/evidence/EVD-S11-P04_rollback.json",
        "rollback_sha256": "5d0ae695f8eb47c05d568a062a0cb4c8150fdc4757b8f7cf97f463ecaa504508",
        "decision": "CONSTRAINED_KELLY_RISK_CAPS_REPLAYED_SYNTHETIC_ONLY_STAGE_REVIEW_REQUIRED",
        "next": "S11/STAGE_REVIEW_READY_NOT_STARTED",
        "release_status": "S11_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
    },
}

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

PHASE_EXTERNAL_BOUNDARY = {
    "external_network_accessed": False,
    "actual_market_or_odds_observed": False,
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
REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "FRICTION_EXECUTABLE_NET_EXPECTATION_GATE_PRESERVED",
    "EVIDENCE_TIER_MINIMUM_ODDS_AND_ONE_IN_TEN_THOUSAND_GATE_PRESERVED",
    "UNIQUE_SYNTHETIC_PLATFORM_ROUTE_GATE_PRESERVED",
    "CONSTRAINED_KELLY_CORRELATION_AND_RISK_CAPS_PRESERVED",
    "NO_NETWORK_ORDER_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_REVIEW_FINDINGS_RESOLVED",
    "NO_FULL_REGRESSION_EXECUTED",
]
ROLLBACK_ARTIFACTS = (
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
    *(Path(spec["evidence_path"]) for spec in PHASE_SPECS.values()),
    *(Path(spec["rollback_path"]) for spec in PHASE_SPECS.values()),
)
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")
_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}


class Stage11ReviewError(ValueError):
    """Raised when S11 whole-stage review evidence is not reproducible."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage11ReviewError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage11ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative)
    return value


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise Stage11ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage11ReviewError("JSONL row %d is not an object" % number)
        rows.append(value)
    return rows


def _parse_sums(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise Stage11ReviewError("invalid SHA256SUMS line %d" % number)
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in parsed:
            raise Stage11ReviewError("unsafe or duplicate checksum path")
        parsed[relative] = digest
    if not parsed:
        raise Stage11ReviewError("SHA256SUMS is empty")
    return parsed


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise Stage11ReviewError("JUnit contains no suites")
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
    return bool(suites) and all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK for suite in suites)


def _portable(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_portable(item) for item in value)
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return not (
            normalized.startswith("/")
            or normalized.startswith("file:")
            or "/" + "Users/" in normalized
            or "/home/" in normalized
            or re.match(r"^[A-Za-z]:/", normalized) is not None
        )
    return True


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise Stage11ReviewError("expected decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise Stage11ReviewError("invalid decimal") from exc
    if not parsed.is_finite():
        raise Stage11ReviewError("decimal must be finite")
    return parsed


def _phase_records() -> List[Dict[str, Any]]:
    return [
        {
            "phase_id": phase,
            "requirement_id": spec["requirement_id"],
            "acceptance_contract_id": spec["contract_id"],
            "target": spec["target"],
            "outputs": spec["outputs"],
            "evidence_path": spec["evidence_path"],
            "evidence_sha256": spec["evidence_sha256"],
            "rollback_path": spec["rollback_path"],
            "rollback_sha256": spec["rollback_sha256"],
            "expected_decision": spec["decision"],
            "expected_next": spec["next"],
        }
        for phase, spec in PHASE_SPECS.items()
    ]


def _review_scope() -> Dict[str, Any]:
    return {
        "phase_ids": list(PHASE_SPECS),
        "requirement_ids": [spec["requirement_id"] for spec in PHASE_SPECS.values()],
        "acceptance_contract_ids": [spec["contract_id"] for spec in PHASE_SPECS.values()],
        "task_ids": ["T-S11-%s-%02d" % (phase, number) for phase in PHASE_SPECS for number in (1, 2, 3)],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one immutable S11 review snapshot without enabling action."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "friction_gate_preserved",
        "evidence_tier_and_minimum_odds_gate_preserved",
        "unique_platform_route_gate_preserved",
        "constrained_kelly_and_risk_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage11ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage11ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage11ReviewError("findings_open must be a nonnegative integer")
    reason_map = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("friction_gate_preserved", "FRICTION_GATE_RELAXED"),
        ("evidence_tier_and_minimum_odds_gate_preserved", "EVIDENCE_TIER_OR_MINIMUM_ODDS_GATE_RELAXED"),
        ("unique_platform_route_gate_preserved", "UNIQUE_PLATFORM_ROUTE_GATE_RELAXED"),
        ("constrained_kelly_and_risk_gate_preserved", "CONSTRAINED_KELLY_OR_RISK_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S11_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S11_STAGE_REVIEW_REJECTED_NO_ACTION",
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
        _add(checks, "S11REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "targeted_test_command": "pytest -q tests/S11/stage_review_test.py",
        "release_status_on_pass": "S11_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S11/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S11/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S11REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S11REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S11REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S11REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    policy = {
        "offline_deterministic_only": True,
        "phase_test_rerun_allowed": False,
        "full_regression_or_real_time_soak_allowed": False,
        "single_pass_fixture_cases_only": True,
        "github_upload_performed_by_local_review": False,
        "production_deployed_or_activated": False,
        "incremental_cash_spent_aud": "0.00",
    }
    _add(checks, "S11REVIEW-NO-FULL-REGRESSION-OR-REALTIME-POLICY", contract.get("execution_policy") == policy, contract.get("execution_policy"))
    _add(checks, "S11REVIEW-REQUIRED-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S11-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": 9,
        "minimum_targeted_pytest_cases": 21,
        "expected_next": "S11/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S11_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
    }
    _add(checks, "S11REVIEW-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    _add(
        checks,
        "S11REVIEW-FIXTURE-PHASE-RECEIPT-PINS-EXACT",
        fixture.get("expected_phase_evidence_sha256") == {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()}
        and fixture.get("expected_phase_rollback_sha256") == {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        {"evidence": fixture.get("expected_phase_evidence_sha256"), "rollback": fixture.get("expected_phase_rollback_sha256")},
    )
    finding = findings.get("findings")
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_clock") == FIXED_CLOCK
        and findings.get("summary") == {"total": 1, "open": 0, "resolved": 1, "blocked": 0}
        and isinstance(finding, list)
        and len(finding) == 1
        and isinstance(finding[0], Mapping)
        and finding[0].get("id") == "S11-REVIEW-001"
        and finding[0].get("category") == "REVIEW_CONTRACT_GAP"
        and finding[0].get("status") == "RESOLVED_IN_STAGE_REVIEW"
    )
    _add(checks, "S11REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected = contract.get("baseline_hashes")
    if expected != BASELINE_HASHES:
        _add(checks, "S11REVIEW-BASELINE-CONTRACT-PINS-EXACT", False, expected)
        return
    _add(checks, "S11REVIEW-BASELINE-CONTRACT-PINS-EXACT", True, sorted(BASELINE_HASHES))
    all_match = True
    for relative, digest in sorted(BASELINE_HASHES.items()):
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            passed = actual == digest
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            passed = False
        all_match = all_match and passed
        _add(checks, "S11REVIEW-BASELINE-%s" % Path(relative).stem.upper(), passed, {"expected": digest, "actual": actual})
    _add(checks, "S11REVIEW-BASELINE-CRITICAL-HASHES", all_match, "all frozen baseline hashes match" if all_match else "frozen baseline drift")


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S11REVIEW-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S11REVIEW-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S11REVIEW-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, root / "machine/facts/traceability_matrix.json", checks, "S11REVIEW-TRACE-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(graph, Mapping) or not isinstance(traceability, list):
        _add(checks, "S11REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "task pack inputs malformed")
        return False
    tasks = graph.get("tasks")
    if not isinstance(tasks, list):
        _add(checks, "S11REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "task graph tasks unavailable")
        return False
    valid = True
    detail: Dict[str, Any] = {}
    for phase, spec in PHASE_SPECS.items():
        try:
            requirement = _row(requirements, spec["requirement_id"])
            acceptance = _row(contracts, spec["contract_id"])
            trace = _row(traceability, spec["requirement_id"], key="requirement_id")
            phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == phase]
            expected_task_ids = ["T-S11-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            task_ids = [task.get("id") for task in phase_tasks]
            task_outputs = {output for task in phase_tasks for output in task.get("outputs", [])}
            required_outputs = set(spec["outputs"]) | {
                spec["test_path"],
                spec["fixture_path"],
                spec["evidence_path"],
                spec["rollback_path"],
            }
            expected_oracle = {
                "type": "EXECUTABLE",
                "command": "python -m abd_acceptance --contract %s --evidence machine/evidence" % spec["contract_id"],
                "rule": spec["target"],
            }
            current = (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("scope") == spec["outputs"]
                and requirement.get("target") == spec["target"]
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and acceptance.get("requirement_id") == spec["requirement_id"]
                and acceptance.get("oracle") == expected_oracle
                and acceptance.get("pass_gate") == spec["target"]
                and task_ids == expected_task_ids
                and required_outputs.issubset(task_outputs)
                and (root / spec["module_path"]).is_file()
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == expected_task_ids
                and trace.get("test_ids") == ["TEST-S11-%s" % phase, "TEST-S11-%s-BOUNDARY" % phase, "TEST-S11-%s-REPLAY" % phase]
                and trace.get("evidence_id") == "EVD-S11-%s" % phase
                and trace.get("artifact_ids") == ["ART-S11-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            )
        except Exception as exc:
            current = False
            task_ids = "%s: %s" % (type(exc).__name__, exc)
        valid = valid and current
        detail[phase] = {"passed": current, "task_ids": task_ids}
    _add(checks, "S11REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", valid, detail)
    return valid


def _check_phase_receipts(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> Tuple[bool, bool, bool]:
    records = contract.get("phase_records")
    if records != _phase_records():
        _add(checks, "S11REVIEW-PHASE-RECORDS-AVAILABLE", False, records)
        return False, False, False
    _add(checks, "S11REVIEW-PHASE-RECORDS-AVAILABLE", True, list(PHASE_SPECS))
    phase_ok = True
    portable_ok = True
    boundary_ok = True
    for phase, spec in PHASE_SPECS.items():
        evidence_path = root / spec["evidence_path"]
        rollback_path = root / spec["rollback_path"]
        evidence = _safe_load(root, evidence_path, checks, "S11REVIEW-%s-EVIDENCE-STRICT-JSON" % phase)
        rollback = _safe_load(root, rollback_path, checks, "S11REVIEW-%s-ROLLBACK-STRICT-JSON" % phase)
        try:
            evidence_hash = sha256_file(evidence_path)
            rollback_hash = sha256_file(rollback_path)
            hashes[spec["evidence_path"]] = evidence_hash
            hashes[spec["rollback_path"]] = rollback_hash
            pin_ok = (
                evidence_hash == spec["evidence_sha256"]
                and rollback_hash == spec["rollback_sha256"]
                and fixture.get("expected_phase_evidence_sha256", {}).get(phase) == evidence_hash
                and fixture.get("expected_phase_rollback_sha256", {}).get(phase) == rollback_hash
            )
            _add(checks, "S11REVIEW-%s-RECEIPT-HASHES" % phase, pin_ok, {"evidence": evidence_hash, "rollback": rollback_hash})
        except Exception as exc:
            pin_ok = False
            _add(checks, "S11REVIEW-%s-RECEIPT-HASHES" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            verified = PHASE_VERIFIERS[phase](root)
            verifier_ok = (
                verified.get("status") == "PASS"
                and verified.get("contract_id") == spec["contract_id"]
                and verified.get("evidence_path") == spec["evidence_path"]
                and verified.get("evidence_sha256") == spec["evidence_sha256"]
                and verified.get("next") == spec["next"]
            )
        except Exception as exc:
            verified = "%s: %s" % (type(exc).__name__, exc)
            verifier_ok = False
        _add(checks, "S11REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, verifier_ok, verified)
        receipt_ok = (
            isinstance(evidence, Mapping)
            and evidence.get("status") == "PASS"
            and evidence.get("contract_id") == spec["contract_id"]
            and evidence.get("requirement_id") == spec["requirement_id"]
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == phase
            and evidence.get("decision") == spec["decision"]
            and evidence.get("next") == spec["next"]
            and evidence.get("release_status") == spec["release_status"]
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("external_effect_boundary") == PHASE_EXTERNAL_BOUNDARY
            and isinstance(rollback, Mapping)
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and rollback.get("production_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_time_soak_waited") is False
            and rollback.get("incremental_cash_spent_aud") == "0.00"
        )
        _add(checks, "S11REVIEW-%s-RECEIPT-AND-BOUNDARY-EXACT" % phase, receipt_ok, {"decision": evidence.get("decision") if isinstance(evidence, Mapping) else None, "next": evidence.get("next") if isinstance(evidence, Mapping) else None})
        try:
            index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % spec["contract_id"])
            index_ok = (
                index.get("kind") == "PHASE_EVIDENCE"
                and index.get("stage_id") == STAGE_ID
                and index.get("contract_id") == spec["contract_id"]
                and index.get("requirement_id") == spec["requirement_id"]
                and index.get("status") == "PASS"
                and index.get("actual_artifact") == spec["evidence_path"]
                and index.get("artifact_sha256") == spec["evidence_sha256"]
                and index.get("next") == spec["next"]
                and index.get("verified_at") == FIXED_CLOCK
            )
        except Exception as exc:
            index = "%s: %s" % (type(exc).__name__, exc)
            index_ok = False
        _add(checks, "S11REVIEW-%s-EVIDENCE-INDEX-BINDING" % phase, index_ok, index)
        current_portable = _portable(evidence) and _portable(rollback)
        _add(checks, "S11REVIEW-%s-EVIDENCE-PORTABLE" % phase, current_portable, "portable" if current_portable else "local path detected")
        phase_ok = phase_ok and pin_ok and verifier_ok and receipt_ok and index_ok
        portable_ok = portable_ok and current_portable
        boundary_ok = boundary_ok and receipt_ok
    _add(checks, "S11REVIEW-PHASE-RECEIPTS-CURRENT", phase_ok, "all signed P01--P04 receipts current" if phase_ok else "one or more phase receipts are stale")
    _add(checks, "S11REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS", portable_ok, "portable" if portable_ok else "local path detected")
    _add(checks, "S11REVIEW-PHASE-EXTERNAL-BOUNDARY-EXACT", boundary_ok, "all phase boundaries checked" if boundary_ok else "boundary mismatch")
    return phase_ok, portable_ok, boundary_ok


def _identity(document: Mapping[str, Any], phase: str) -> bool:
    spec = PHASE_SPECS[phase]
    return (
        document.get("schema_version") == "1.0.0"
        and document.get("contract_id") == spec["contract_id"]
        and document.get("requirement_id") == spec["requirement_id"]
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == phase
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    )


def _vector(rows: Any, identifier: str) -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage11ReviewError("vectors unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get("vector_id") == identifier]
    if len(matches) != 1:
        raise Stage11ReviewError("expected exactly one vector=%s" % identifier)
    return matches[0]


def _check_stage_controls(root: Path, checks: List[Dict[str, Any]]) -> Tuple[bool, bool, bool, bool]:
    friction_model = _safe_load(root, root / "friction_model.json", checks, "S11REVIEW-FRICTION-MODEL-STRICT-JSON")
    friction_backtest = _safe_load(root, root / "friction_backtest.json", checks, "S11REVIEW-FRICTION-BACKTEST-STRICT-JSON")
    tiers = _safe_load(root, root / "evidence_tiers.json", checks, "S11REVIEW-EVIDENCE-TIERS-STRICT-JSON")
    thresholds = _safe_load(root, root / "threshold_vectors.json", checks, "S11REVIEW-THRESHOLD-VECTORS-STRICT-JSON")
    score = _safe_load(root, root / "provider_score.json", checks, "S11REVIEW-PROVIDER-SCORE-STRICT-JSON")
    routes = _safe_load(root, root / "routing_fixtures.json", checks, "S11REVIEW-ROUTING-FIXTURES-STRICT-JSON")
    graph = _safe_load(root, root / "correlation_graph.json", checks, "S11REVIEW-CORRELATION-GRAPH-STRICT-JSON")
    risks = _safe_load(root, root / "risk_vectors.json", checks, "S11REVIEW-RISK-VECTORS-STRICT-JSON")

    friction_ok = False
    try:
        methodology = {
            "effective_rule": "MAX(DEFAULT, ROLLING_OBSERVED_P95)",
            "observed_friction_components": ["price_worsening", "rejection", "settlement", "operational"],
            "rolling_percentile": "UPPER_NEAREST_RANK_P95",
            "rolling_window_selection": "LAST_ORDERED_SYNTHETIC_OBSERVATIONS",
            "rounding": "DECIMAL_FRICTION_UP_1E-9",
        }
        boundary = {
            "actual_market_or_odds_observed": False,
            "network_accessed": False,
            "recommendation_generated": False,
            "order_submission_enabled": False,
            "real_time_soak_required": False,
            "incremental_cash_spent_aud": "0.00",
        }
        bands = friction_model.get("time_bands") if isinstance(friction_model, Mapping) else None
        band_ok = isinstance(bands, list) and len(bands) == 4 and all(
            isinstance(band, Mapping)
            and band.get("observation_count") == 5
            and band.get("rolling_window_observation_count") == 5
            and _decimal(band["effective_friction"]) == max(_decimal(band["default_friction"]), _decimal(band["rolling_observed_p95"]))
            for band in bands
        )
        friction_ok = (
            isinstance(friction_model, Mapping)
            and isinstance(friction_backtest, Mapping)
            and _identity(friction_model, "P01")
            and _identity(friction_backtest, "P01")
            and friction_model.get("methodology") == methodology
            and friction_model.get("claim_boundary") == boundary
            and friction_backtest.get("claim_boundary") == boundary
            and band_ok
            and friction_backtest.get("summary") == {
                "candidate_count": 4,
                "positive_net_expected_count": 3,
                "recommendations_enabled": False,
                "order_actions_enabled": False,
            }
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        friction_ok = False
    _add(checks, "S11REVIEW-FRICTION-EXECUTABLE-NET-EXPECTATION-GATE-PRESERVED", friction_ok, {"time_bands": len(friction_model.get("time_bands", [])) if isinstance(friction_model, Mapping) else None})

    threshold_ok = False
    try:
        v02 = _vector(thresholds.get("vectors"), "V02-E4-EXACT-MINIMUM-ODDS-ADVERSE-FLIP")
        v06 = _vector(thresholds.get("vectors"), "V06-E0-NONPRICE-SOURCES-BELOW-MINIMUM")
        threshold_ok = (
            isinstance(tiers, Mapping)
            and isinstance(thresholds, Mapping)
            and _identity(tiers, "P02")
            and _identity(thresholds, "P02")
            and [row.get("tier") for row in tiers.get("tiers", [])] == ["E4", "E3", "E2", "E1"]
            and tiers.get("e0_action") == "NO_RECOMMENDATION"
            and thresholds.get("evidence_tiers_sha256") == decision_gate_artifact_sha256(tiers)
            and isinstance(thresholds.get("vectors"), list)
            and len(thresholds["vectors"]) == 12
            and v02.get("expected") == {
                "action": "NO_RECOMMENDATION",
                "base_action": "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES",
                "tier": "E4",
                "minimum_acceptable_odds": "1.733334",
                "reason_code": "ADVERSE_STABILITY_FLIP",
                "adverse_flip_dimensions": ["probability_minus", "threshold_plus", "friction_plus", "odds_adverse", "all_adverse"],
            }
            and v06.get("expected", {}).get("action") == "NO_RECOMMENDATION"
            and v06.get("expected", {}).get("tier") == "E0"
        )
    except (KeyError, TypeError, ValueError):
        threshold_ok = False
    _add(checks, "S11REVIEW-EVIDENCE-TIER-MINIMUM-ODDS-AND-ONE-IN-TEN-THOUSAND-GATE-PRESERVED", threshold_ok, {"vector_count": len(thresholds.get("vectors", [])) if isinstance(thresholds, Mapping) else None})

    route_ok = False
    try:
        r01 = _vector(routes.get("vectors"), "R01-UNIQUE-STABLE-SYNTHETIC-PLATFORM")
        r02 = _vector(routes.get("vectors"), "R02-TOP-SCORE-TIE-FAILS-CLOSED")
        hard_gates = {
            "action_channel_must_be_available": True,
            "adverse_stability_must_preserve_action_and_provider": True,
            "minimum_stake_must_not_exceed_routing_stake": True,
            "observed_odds_must_meet_minimum": True,
            "p02_candidate_action_required": "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES",
            "routing_stake_must_align_to_provider_increment": True,
            "score_must_be_strictly_positive": True,
            "settlement_rules_must_be_clear": True,
            "source_contract_must_pass": True,
            "unique_highest_score_required": True,
        }
        route_ok = (
            isinstance(score, Mapping)
            and isinstance(routes, Mapping)
            and _identity(score, "P03")
            and _identity(routes, "P03")
            and score.get("hard_gates") == hard_gates
            and routes.get("provider_score_sha256") == platform_router_artifact_sha256(score)
            and isinstance(routes.get("vectors"), list)
            and len(routes["vectors"]) == 12
            and r01.get("expected") == {
                "baseline_action": "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
                "reason_code": "ALL_PLATFORM_GATES_AND_UNIQUE_ROUTE_STABLE",
                "selected_provider_id": "SYNTHETIC_PROVIDER_ALPHA",
                "adverse_flip_dimensions": [],
            }
            and r02.get("expected") == {
                "baseline_action": "NO_RECOMMENDATION",
                "reason_code": "TOP_PLATFORM_SCORE_TIED",
                "selected_provider_id": None,
                "adverse_flip_dimensions": [],
            }
        )
    except (KeyError, TypeError, ValueError):
        route_ok = False
    _add(checks, "S11REVIEW-UNIQUE-SYNTHETIC-PLATFORM-ROUTE-GATE-PRESERVED", route_ok, {"vector_count": len(routes.get("vectors", [])) if isinstance(routes, Mapping) else None})

    risk_ok = False
    try:
        k11 = _vector(risks.get("vectors"), "K11-RISK-THRESHOLD-POINT-0001-FLIP")
        hard_caps = {
            "single_ticket_cap_by_stage": {"ALPHA": "0", "BETA": "0.015", "GA": "0.02"},
            "event_cap": "0.05",
            "correlation_cluster_cap": "0.05",
            "total_open_exposure_cap": "0.15",
        }
        controls = {
            "daily_loss_soft_stop": "0.03",
            "seven_day_drawdown_diagnostic": "0.075",
            "strategy_slice_kill_drawdown": "0.1",
            "absolute_disaster_line": "0.7",
            "chase_loss_prohibited": True,
            "target_shortfall_may_relax_gate": False,
        }
        graph_clusters = graph.get("clusters") if isinstance(graph, Mapping) else None
        clusters_ok = isinstance(graph_clusters, list) and len(graph_clusters) == 6 and all(
            isinstance(cluster, Mapping) and cluster.get("cap_fraction") == "0.05" for cluster in graph_clusters
        )
        risk_ok = (
            isinstance(graph, Mapping)
            and isinstance(risks, Mapping)
            and _identity(graph, "P04")
            and _identity(risks, "P04")
            and graph.get("hard_caps") == hard_caps
            and graph.get("risk_controls") == controls
            and clusters_ok
            and risks.get("correlation_graph_sha256") == risk_engine_artifact_sha256(graph)
            and isinstance(risks.get("vectors"), list)
            and len(risks["vectors"]) == 12
            and k11.get("expected") == {
                "action": "NO_RECOMMENDATION",
                "baseline_action": "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
                "reason_code": "ADVERSE_RISK_STABILITY_FLIP",
                "stake_cents": 0,
                "adverse_flip_dimensions": ["risk_threshold_tightened", "all_adverse"],
            }
        )
    except (KeyError, TypeError, ValueError):
        risk_ok = False
    _add(checks, "S11REVIEW-CONSTRAINED-KELLY-CORRELATION-AND-RISK-CAPS-PRESERVED", risk_ok, {"vector_count": len(risks.get("vectors", [])) if isinstance(risks, Mapping) else None})
    return friction_ok, threshold_ok, route_ok, risk_ok


def _check_snapshot_cases(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S11REVIEW-SINGLE-PASS-FIXTURE-CASES", False, "cases unavailable")
        return {}
    case_ids = [row.get("case_id") for row in cases if isinstance(row, Mapping)]
    shape_ok = len(cases) == 9 and len(case_ids) == len(cases) and len(set(case_ids)) == len(cases)
    _add(checks, "S11REVIEW-SINGLE-PASS-FIXTURE-CASES", shape_ok, {"case_count": len(cases), "case_ids": case_ids})
    results: Dict[str, Dict[str, Any]] = {}
    for row in cases:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("expected"), Mapping):
            _add(checks, "S11REVIEW-SINGLE-PASS-CASE-SHAPE", False, row)
            continue
        try:
            actual = evaluate_stage_snapshot(row["snapshot"])
            expected = row["expected"]
            passed = (
                actual.get("status") == expected.get("status")
                and actual.get("reason_codes") == expected.get("reason_codes")
                and actual.get("recommendation_generated") is False
                and actual.get("order_submission_enabled") is False
                and actual.get("external_network_used") is False
                and actual.get("real_time_soak_waited") is False
            )
            _add(checks, "S11REVIEW-CASE-%s" % row["case_id"], passed, {"actual": actual, "expected": expected})
            results[row["case_id"]] = actual
        except Exception as exc:
            _add(checks, "S11REVIEW-CASE-%s" % row["case_id"], False, "%s: %s" % (type(exc).__name__, exc))
    positive = results.get("POSITIVE_EXACT_STAGE")
    positive_ok = positive is not None and positive.get("status") == "S11_STAGE_REVIEW_VERIFIED_NO_ACTION"
    _add(checks, "S11REVIEW-CURRENT-FIXED-SNAPSHOT-NO-ACTION", positive_ok, positive)
    _add(checks, "S11REVIEW-NO-REPEATED-REPLAY-OR-SOAK", fixture.get("single_pass_case_count") == 9, "each frozen snapshot is evaluated once")
    return results


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        calls: list[str] = []
        forbidden_calls = {"sleep", "run", "Popen", "float", "submit_order"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
                if name in forbidden_calls:
                    calls.append(name)
        prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
        passed = not (imports & prohibited_imports) and not calls and ("float" + "(") not in source
        _add(checks, "S11REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", passed, {"imports": sorted(imports), "calls": sorted(calls)})
    except Exception as exc:
        _add(checks, "S11REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        junit_ok = (
            summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and not summary["failures"]
            and not summary["errors"]
            and not summary["skipped"]
            and _junit_is_normalized(root / JUNIT_PATH)
        )
        _add(checks, "S11REVIEW-TARGETED-PYTEST-REPORT", junit_ok, {"summary": summary, "normalized": _junit_is_normalized(root / JUNIT_PATH)})
    except Exception as exc:
        _add(checks, "S11REVIEW-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S11REVIEW-PAID-DEPENDENCY-SCAN-PASS", "STATUS: PASS" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S11REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, root / PACK_REPORT_PATH, checks, "S11REVIEW-PACK-REPORT-STRICT-JSON")
    _add(checks, "S11REVIEW-PACK-REPORT-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("summary") if isinstance(report, Mapping) else "unavailable")


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
        "stage_status": "S11_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S11_WHOLE_STAGE_REVIEW_BLOCKED",
        "decision": "S11_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S11/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S11/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "release_status": "S11_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if status == "PASS" else "S11_RELEASE_BLOCKED",
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
    contract = _safe_load(root, root / CONTRACT_PATH, checks, "S11REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root, root / FINDINGS_PATH, checks, "S11REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S11REVIEW-FIXTURE-STRICT-JSON")
    if not isinstance(contract, Mapping) or not isinstance(findings, Mapping) or not isinstance(fixture, Mapping):
        return _result(checks, hashes, None)
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, contract, checks, hashes)
    taskpack_ok = _check_taskpack(root, checks)
    phase_ok, portable_ok, boundary_ok = _check_phase_receipts(root, contract, fixture, checks, hashes)
    friction_ok, threshold_ok, route_ok, risk_ok = _check_stage_controls(root, checks)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings.get("summary"), Mapping) else -1
    snapshot = {
        "phase_receipts_current": phase_ok,
        "taskpack_trace_closed": taskpack_ok,
        "friction_gate_preserved": friction_ok,
        "evidence_tier_and_minimum_odds_gate_preserved": threshold_ok,
        "unique_platform_route_gate_preserved": route_ok,
        "constrained_kelly_and_risk_gate_preserved": risk_ok,
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable_ok,
        "findings_open": findings_open,
    }
    stage_snapshot = evaluate_stage_snapshot(snapshot)
    _add(checks, "S11REVIEW-CURRENT-STAGE-SNAPSHOT-NO-ACTION", stage_snapshot["status"] == "S11_STAGE_REVIEW_VERIFIED_NO_ACTION", stage_snapshot)
    return _result(checks, hashes, stage_snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path), "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in ROLLBACK_ARTIFACTS
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S11-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S11_STAGE_REVIEW_CANDIDATE_KEEP_SIGNED_PHASE_RECEIPTS_AND_REPLAY_OFFLINE",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    phase_paths = [Path(path) for spec in PHASE_SPECS.values() for path in (*spec["outputs"], spec["module_path"], spec["evidence_path"], spec["rollback_path"])]
    paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, *(Path(path) for path in BASELINE_HASHES), *phase_paths]
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
        "evidence_id": "EVD-S11-STAGE-REVIEW",
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
                "evidence_path": spec["evidence_path"],
                "evidence_sha256": sha256_file(root / spec["evidence_path"]),
                "rollback_path": spec["rollback_path"],
                "rollback_sha256": sha256_file(root / spec["rollback_path"]),
            }
            for phase, spec in PHASE_SPECS.items()
        },
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S11-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S11-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S11-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S11-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S11/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S11/stage_review_test.py --junitxml=machine/evidence/S11/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S11/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S11 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_review": {"single_pass_fixture_cases": 9, "phase_test_suites_rerun": False, "full_regression_executed": False, "real_time_wait_performed": False},
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
        "id": "INDEX-S11-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S11/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    positions = [index for index, row in enumerate(rows) if row.get("id") == updated["id"]]
    if len(positions) > 1:
        raise Stage11ReviewError("duplicate S11 stage-review evidence index rows")
    if positions:
        rows[positions[0]] = updated
    else:
        rows.append(updated)
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in rows))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage11ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage11ReviewError("cannot write evidence for a failed S11 review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S11/GITHUB_STAGE_UPLOAD_READY",
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
    expected: List[Path] = []
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
        raise Stage11ReviewError("S11 review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    index = [row for row in index_rows if row.get("id") == "INDEX-S11-STAGE-REVIEW"]
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S11_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S11/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S11_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and len(index) == 1
        and index[0].get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and _manifest_current(root)
    )
    if not valid:
        raise Stage11ReviewError("existing S11 review evidence is not reproducible or its manifest is stale")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S11/GITHUB_STAGE_UPLOAD_READY",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABD S11 offline whole-stage review")
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
