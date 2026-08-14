"""Fail-closed acceptance oracle for ABD S12/P01 target governance."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence

from target_engine import TargetInputError, artifact_sha256, build_artifacts, canonical_json_bytes

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S12-P01"
REQUIREMENT_ID = "REQ-S12-P01"
STAGE_ID = "S12"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"

TARGET_ENGINE_PATH = Path("target_engine.py")
CASHFLOW_PATH = Path("cashflow_adjustment.py")
VECTORS_PATH = Path("target_vectors.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S12_P01.json")
TEST_PATH = Path("tests/S12/P01_test.py")
JUNIT_PATH = Path("machine/evidence/S12/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S12/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S12-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S12-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

_FACT_PATHS = (
    Path("machine/facts/canonical_facts.json"),
    Path("machine/facts/parameters.json"),
    Path("machine/facts/roadmap.json"),
    Path("machine/facts/requirements.json"),
    Path("machine/facts/acceptance_contracts.json"),
    Path("machine/facts/task_graph.json"),
    Path("machine/facts/traceability_matrix.json"),
)
_PREDECESSORS = (
    Path("machine/evidence/EVD-S01-P04.json"),
    Path("machine/evidence/S01/STAGE_REVIEW/github_delivery_receipt.json"),
    Path("machine/evidence/EVD-S10-P04.json"),
    Path("machine/evidence/EVD-S11-P04.json"),
)
_ROLLBACK_ARTIFACTS = (TARGET_ENGINE_PATH, CASHFLOW_PATH, VECTORS_PATH, FIXTURE_PATH, TEST_PATH)
_SHARED_RUNTIME_EXCLUSIONS = ("abd_acceptance/__main__.py", "abd_acceptance/budget.py")
_BOUNDARY = {
    "external_network_accessed": False,
    "real_account_balance_read_or_written": False,
    "financial_return_verified_or_guaranteed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class TargetCurveAcceptanceError(RuntimeError):
    """Raised when S12/P01 evidence cannot be accepted fail-closed."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        raise TargetCurveAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise TargetCurveAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise TargetCurveAcceptanceError("blank evidence-index row %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise TargetCurveAcceptanceError("evidence-index row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S12P01-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S12P01-CONTRACTS-PARSE")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S12P01-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S12P01-TRACEABILITY-PARSE")
    roadmap = _safe_load(root, Path("machine/facts/roadmap.json"), checks, "S12P01-ROADMAP-PARSE")
    if not all(isinstance(value, (list, Mapping)) for value in (requirements, contracts, graph, traceability, roadmap)):
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [row for row in graph.get("tasks", []) if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        stages = [row for row in roadmap.get("stages", []) if isinstance(row, Mapping) and row.get("id") == STAGE_ID]
        phase = next((row for row in stages[0].get("phases", []) if row.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
        expected_scope = ["target_engine.py", "cashflow_adjustment.py", "target_vectors.json"]
        expected_tasks = ["T-S12-P01-01", "T-S12-P01-02", "T-S12-P01-03"]
        expected_oracle = {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S12-P01 --evidence machine/evidence",
            "rule": "固定时钟下目标曲线与高精度参考一致。",
        }
        task_outputs = {item for task in tasks for item in task.get("outputs", [])}
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "固定时钟下目标曲线与高精度参考一致。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == expected_oracle
            and contract.get("pass_gate") == requirement.get("target")
            and phase.get("outputs") == expected_scope
            and phase.get("pass_gate") == requirement.get("target")
        )
        _add(checks, "S12P01-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == expected_tasks
            and tasks[0].get("depends_on") == ["T-S01-P04-03", "T-S10-P04-03", "T-S11-P04-03"]
            and tasks[1].get("depends_on") == ["T-S12-P01-01"]
            and tasks[2].get("depends_on") == ["T-S12-P01-02"]
            and all(item in task_outputs for item in expected_scope + [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(), EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()])
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == expected_tasks
            and trace.get("test_ids") == ["TEST-S12-P01", "TEST-S12-P01-BOUNDARY", "TEST-S12-P01-REPLAY"]
            and trace.get("evidence_id") == "EVD-S12-P01"
            and trace.get("artifact_ids") == ["ART-S12-P01-01", "ART-S12-P01-02", "ART-S12-P01-03"]
        )
        _add(checks, "S12P01-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S12P01-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S12P01-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
        index_by_id = {row.get("id"): row for row in index_rows}
        s01 = _safe_load(root, _PREDECESSORS[0], checks, "S12P01-PREDECESSOR-S01-P04-PARSE")
        s01_delivery = _safe_load(root, _PREDECESSORS[1], checks, "S12P01-PREDECESSOR-S01-DELIVERY-PARSE")
        s10 = _safe_load(root, _PREDECESSORS[2], checks, "S12P01-PREDECESSOR-S10-P04-PARSE")
        s11 = _safe_load(root, _PREDECESSORS[3], checks, "S12P01-PREDECESSOR-S11-P04-PARSE")
        for relative in _PREDECESSORS:
            hashes[relative.as_posix()] = sha256_file(root / relative)
        s01_hash = hashes[_PREDECESSORS[0].as_posix()]
        s01_index = index_by_id.get("INDEX-AC-S01-P04", {})
        s01_ok = (
            isinstance(s01, Mapping)
            and s01.get("contract_id") == "AC-S01-P04"
            and s01.get("status") == "PASS"
            and isinstance(s01_delivery, Mapping)
            and s01_delivery.get("stage_id") == "S01"
            and s01_delivery.get("delivery_status") == "VERIFIED_MERGED_AND_MAIN_CI_PASS"
            and s01_delivery.get("all_required_main_checks_passed") is True
            and s01_delivery.get("next") == "S02/P01_READY_NOT_STARTED"
            and s01_index.get("actual_artifact") == _PREDECESSORS[0].as_posix()
            and s01_index.get("artifact_sha256") == s01_hash
            and s01_index.get("status") == "PASS"
        )
        s10_ok = isinstance(s10, Mapping) and s10.get("contract_id") == "AC-S10-P04" and s10.get("status") == "PASS"
        s11_ok = isinstance(s11, Mapping) and s11.get("contract_id") == "AC-S11-P04" and s11.get("status") == "PASS"
        _add(checks, "S12P01-PREDECESSOR-S01-SIGNED-AND-DELIVERED", s01_ok, s01_index)
        _add(checks, "S12P01-PREDECESSOR-S10-P04-SIGNED", s10_ok, s10.get("status") if isinstance(s10, Mapping) else s10)
        _add(checks, "S12P01-PREDECESSOR-S11-P04-SIGNED", s11_ok, s11.get("status") if isinstance(s11, Mapping) else s11)
    except Exception as exc:
        _add(checks, "S12P01-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S12P01-PREDECESSOR-CHAIN", False, "%s: %s" % (type(exc).__name__, exc))


def _check_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S12P01-FIXTURE-PARSE")
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S12P01-PARAMETERS-PARSE")
    vectors = _safe_load(root, VECTORS_PATH, checks, "S12P01-VECTORS-PARSE")
    if not all(isinstance(value, Mapping) for value in (fixture, parameters, vectors)):
        return
    try:
        rebuilt = build_artifacts(fixture, parameters)
        replay_ok = artifact_sha256(rebuilt) == fixture.get("expected_target_vectors_sha256") and rebuilt == vectors
        _add(checks, "S12P01-FROZEN-TARGET-VECTOR-REPLAY-EXACT", replay_ok, {"expected": fixture.get("expected_target_vectors_sha256"), "actual": artifact_sha256(rebuilt)})
        rows = rebuilt.get("monthly_rows", [])
        formula_ok = (
            [row.get("baseline_target_start_cents") for row in rows] == [30000, 39000, 50700, 65910]
            and [row.get("baseline_target_end_cents") for row in rows] == [39000, 50700, 65910, 85683]
            and rebuilt.get("target_curve", {}).get("target_rounding") == "UP_TO_INTEGER_CENT_FOR_CONSERVATIVE_TARGET"
        )
        _add(checks, "S12P01-A300-X-1POINT3N-HIGH-PRECISION-TARGET", formula_ok, rebuilt.get("target_curve"))
        cashflow_row = rows[2] if len(rows) >= 3 else {}
        cashflow_ok = (
            cashflow_row.get("month_start_external_cashflow_cents") == 10000
            and cashflow_row.get("month_end_external_cashflow_cents") == -5000
            and cashflow_row.get("cashflow_adjusted_opening_cents") == 60700
            and cashflow_row.get("cashflow_adjusted_closing_before_end_flows_cents") == 78910
            and cashflow_row.get("cashflow_adjusted_return") == "0.3"
            and cashflow_row.get("cashflow_adjusted_target_end_cents") == 73910
        )
        _add(checks, "S12P01-MONTH-START-END-CASHFLOW-ADJUSTMENT-EXACT", cashflow_ok, cashflow_row)
        shortfall_rows = [row for row in rows if row.get("target_status") == "TARGET_SHORTFALL_REPORT_ONLY"]
        shortfall_ok = (
            len(shortfall_rows) == 1
            and shortfall_rows[0].get("target_gap_cents") == -6083
            and shortfall_rows[0].get("shortfall_action") == "REPORT_ONLY_NO_GATE_RELAXATION"
            and rebuilt.get("summary", {}).get("target_shortfall_may_relax_gate") is False
            and rebuilt.get("summary", {}).get("chase_loss_prohibited") is True
        )
        _add(checks, "S12P01-SHORTFALL-REPORT-ONLY-NO-GATE-RELAXATION", shortfall_ok, shortfall_rows)
        boundary_ok = (
            rebuilt.get("claim_boundary") == _BOUNDARY
            and rebuilt.get("summary", {}).get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and rebuilt.get("summary", {}).get("actual_execution_or_account_evidence_claimed") is False
            and rebuilt.get("next") == "S12/P02_READY_NOT_STARTED"
        )
        _add(checks, "S12P01-NO-ACTUAL-RETURN-ORDER-OR-PRODUCTION-CLAIM", boundary_ok, rebuilt.get("claim_boundary"))
        for relative in (TARGET_ENGINE_PATH, CASHFLOW_PATH, VECTORS_PATH, FIXTURE_PATH, TEST_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (TargetInputError, ValueError, KeyError, TypeError) as exc:
        _add(checks, "S12P01-TARGET-RUNNER", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    prohibited_literals = {"sleep(", "submit_order", "retry_order", "gmail", "cloudflare", "ovh"}
    failures: list[Any] = []
    for relative in (TARGET_ENGINE_PATH, CASHFLOW_PATH):
        try:
            source = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as exc:
            failures.append({"path": relative.as_posix(), "error": "%s: %s" % (type(exc).__name__, exc)})
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        prohibited = sorted(imports.intersection(prohibited_imports))
        literals = sorted(value for value in prohibited_literals if value in source)
        if prohibited or literals or "float(" in source:
            failures.append({"path": relative.as_posix(), "imports": prohibited, "literals": literals, "float": "float(" in source})
    _add(checks, "S12P01-STATIC-NO-NETWORK-SOAK-ORDER-OR-PRODUCTION-CAPABILITY", not failures, failures or "static boundary intact")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        scan = scan_dependency_budget(root)
        passed = scan.get("status") == "PASS" and scan.get("summary", {}).get("paid_or_unknown_dependencies") == 0
        _add(checks, "S12P01-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", passed, scan.get("summary"))
    except Exception as exc:
        _add(checks, "S12P01-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    }


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        cases = list(ElementTree.parse(root / JUNIT_PATH).getroot().iter("testcase"))
        passed = summary["tests"] >= 14 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and all(case.attrib.get("time") == "0.000" for case in cases)
        _add(checks, "S12P01-TARGETED-JUNIT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S12P01-TARGETED-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(
            checks,
            "S12P01-PAID-DEPENDENCY-REPORT-PASS",
            all(line in report for line in required),
            SCAN_REPORT_PATH.as_posix(),
        )
    except Exception as exc:
        _add(checks, "S12P01-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S12P01-TASKPACK-REPORT-PARSE")
    _add(checks, "S12P01-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED" if passed else "S12/P01_BLOCKED",
        "next": "S12/P02_READY_NOT_STARTED" if passed else "S12/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "hashes": dict(hashes),
        "external_effect_boundary": dict(_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack_trace(root, checks)
    _check_predecessors(root, checks, hashes)
    _check_runner(root, checks, hashes)
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
        "evidence_id": "EVD-S12-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_TARGET_CURVE_SCOPED_FLAG_RESTORE_SIGNED_S01_S10_S11_PREDECESSORS_KEEP_ALL_EVIDENCE",
        "feature_flag_id": "target:cashflow_adjusted_curve",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [TARGET_ENGINE_PATH, CASHFLOW_PATH, VECTORS_PATH, FIXTURE_PATH, TEST_PATH, *_FACT_PATHS, *_PREDECESSORS]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": list(_SHARED_RUNTIME_EXCLUSIONS),
        "current_validation": "evaluate_contract",
        "reason": "later dispatcher and dependency-scan evolution must not invalidate phase-owned frozen evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S12-P01",
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
            "code": sha256_file(root / Path("abd_acceptance/target_curve.py")),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "shared_runtime_contract": _shared_runtime_contract(),
        "commands": [
            "uv run --frozen --python 3.12 python target_engine.py --fixture machine/tests/fixtures/S12_P01.json --parameters machine/facts/parameters.json --output target_vectors.json",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S12/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S12/P01_test.py --junitxml=machine/evidence/S12/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S12/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S12-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"monthly_records": 4, "real_time_wait_performed": False},
        "external_effect_boundary": dict(_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S12_P01_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        raise TargetCurveAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-AC-S12-P01",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S12/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = sum(row.get("id") == replacement["id"] for row in rows)
    if matches > 1:
        raise TargetCurveAcceptanceError("S12/P01 evidence-index row is duplicated")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    if matches == 0:
        output.append(_jsonl_bytes(replacement))
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise TargetCurveAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise TargetCurveAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S12/P02_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise TargetCurveAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"
        and evidence.get("next") == "S12/P02_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == "target:cashflow_adjusted_curve"
        and rollback.get("external_state_changed") is False
    )
    if not valid:
        raise TargetCurveAcceptanceError("existing S12/P01 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S12/P02_READY_NOT_STARTED"}
