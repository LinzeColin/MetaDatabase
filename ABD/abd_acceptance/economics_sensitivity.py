"""Fail-closed acceptance oracle for ABD S12/P03 economics sensitivity."""

from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping

from economics import EconomicsError, EXTERNAL_EFFECT_BOUNDARY, build_reports, canonical_json_bytes

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S12-P03"
REQUIREMENT_ID = "REQ-S12-P03"
STAGE_ID = "S12"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"

MODEL_PATH = Path("economics.py")
GRID_PATH = Path("sensitivity_grid.json")
OPPORTUNITY_COST_PATH = Path("opportunity_cost.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S12_P03.json")
CAPACITY_REPORT_PATH = Path("capacity_report.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S12-P01.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S12-P02.json")
TEST_PATH = Path("tests/S12/P03_test.py")
JUNIT_PATH = Path("machine/evidence/S12/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S12/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S12-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S12-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

_FACT_PATHS = (
    Path("machine/facts/canonical_facts.json"),
    Path("machine/facts/parameters.json"),
    Path("machine/facts/costs.json"),
    Path("machine/facts/roadmap.json"),
    Path("machine/facts/requirements.json"),
    Path("machine/facts/acceptance_contracts.json"),
    Path("machine/facts/task_graph.json"),
    Path("machine/facts/traceability_matrix.json"),
)
_ROLLBACK_ARTIFACTS = (MODEL_PATH, GRID_PATH, OPPORTUNITY_COST_PATH, FIXTURE_PATH, TEST_PATH)
_SHARED_RUNTIME_EXCLUSIONS = ("abd_acceptance/__main__.py", "abd_acceptance/budget.py")


class EconomicsSensitivityAcceptanceError(RuntimeError):
    """Raised when S12/P03 cannot be accepted without weakening a gate."""


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
        raise EconomicsSensitivityAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise EconomicsSensitivityAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise EconomicsSensitivityAcceptanceError("blank evidence-index row %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise EconomicsSensitivityAcceptanceError("evidence-index row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S12P03-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S12P03-CONTRACTS-PARSE")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S12P03-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S12P03-TRACEABILITY-PARSE")
    roadmap = _safe_load(root, Path("machine/facts/roadmap.json"), checks, "S12P03-ROADMAP-PARSE")
    if not all(isinstance(value, (list, Mapping)) for value in (requirements, contracts, graph, traceability, roadmap)):
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [item for item in graph.get("tasks", []) if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        stages = [item for item in roadmap.get("stages", []) if isinstance(item, Mapping) and item.get("id") == STAGE_ID]
        phase = next((item for item in stages[0].get("phases", []) if item.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
        expected_scope = ["economics.py", "sensitivity_grid.json", "opportunity_cost.json"]
        expected_tasks = ["T-S12-P03-01", "T-S12-P03-02", "T-S12-P03-03"]
        expected_oracle = {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S12-P03 --evidence machine/evidence",
            "rule": "所有收益带区间、置信度和失败概率，不输出保证。",
        }
        task_outputs = {output for task in tasks for output in task.get("outputs", [])}
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "所有收益带区间、置信度和失败概率，不输出保证。"
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
        _add(checks, "S12P03-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == expected_tasks
            and tasks[0].get("depends_on") == ["T-S12-P02-03"]
            and tasks[1].get("depends_on") == ["T-S12-P03-01"]
            and tasks[2].get("depends_on") == ["T-S12-P03-02"]
            and all(output in task_outputs for output in expected_scope + [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(), EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()])
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == expected_tasks
            and trace.get("test_ids") == ["TEST-S12-P03", "TEST-S12-P03-BOUNDARY", "TEST-S12-P03-REPLAY"]
            and trace.get("evidence_id") == "EVD-S12-P03"
            and trace.get("artifact_ids") == ["ART-S12-P03-01", "ART-S12-P03-02", "ART-S12-P03-03"]
        )
        _add(checks, "S12P03-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S12P03-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _signed_predecessor(
    index: Mapping[str, Mapping[str, Any]],
    evidence: Any,
    evidence_hash: str,
    *,
    index_id: str,
    contract_id: str,
    decision: str,
    next_state: str,
) -> bool:
    row = index.get(index_id, {})
    return (
        isinstance(evidence, Mapping)
        and evidence.get("contract_id") == contract_id
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == decision
        and evidence.get("next") == next_state
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("release_status") == "%s_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD" % contract_id.replace("AC-", "").replace("-", "_")
        and row.get("id") == index_id
        and row.get("kind") == "PHASE_EVIDENCE"
        and row.get("contract_id") == contract_id
        and row.get("status") == "PASS"
        and row.get("actual_artifact") == (P01_EVIDENCE_PATH if contract_id == "AC-S12-P01" else P02_EVIDENCE_PATH).as_posix()
        and row.get("artifact_sha256") == evidence_hash
        and row.get("next") == next_state
    )


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        index = {row.get("id"): row for row in index_rows}
        _add(checks, "S12P03-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
        p01 = _safe_load(root, P01_EVIDENCE_PATH, checks, "S12P03-PREDECESSOR-P01-PARSE")
        p02 = _safe_load(root, P02_EVIDENCE_PATH, checks, "S12P03-PREDECESSOR-P02-PARSE")
        p01_hash = sha256_file(root / P01_EVIDENCE_PATH)
        p02_hash = sha256_file(root / P02_EVIDENCE_PATH)
        hashes[P01_EVIDENCE_PATH.as_posix()] = p01_hash
        hashes[P02_EVIDENCE_PATH.as_posix()] = p02_hash
        p01_ok = _signed_predecessor(
            index,
            p01,
            p01_hash,
            index_id="INDEX-AC-S12-P01",
            contract_id="AC-S12-P01",
            decision="TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED",
            next_state="S12/P02_READY_NOT_STARTED",
        )
        p02_ok = _signed_predecessor(
            index,
            p02,
            p02_hash,
            index_id="INDEX-AC-S12-P02",
            contract_id="AC-S12-P02",
            decision="CAPACITY_CORRELATION_READY_DOWNSTREAM_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED",
            next_state="S12/P03_READY_NOT_STARTED",
        )
        _add(checks, "S12P03-PREDECESSOR-P01-SIGNED", p01_ok, index.get("INDEX-AC-S12-P01", {}))
        _add(checks, "S12P03-PREDECESSOR-P02-SIGNED", p02_ok, index.get("INDEX-AC-S12-P02", {}))
    except Exception as exc:
        _add(checks, "S12P03-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S12P03-PREDECESSOR-P01-SIGNED", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S12P03-PREDECESSOR-P02-SIGNED", False, "%s: %s" % (type(exc).__name__, exc))


def _probability_text_in_range(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return Decimal("0") <= Decimal(value) <= Decimal("1")
    except InvalidOperation:
        return False


def _check_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S12P03-FIXTURE-PARSE")
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S12P03-PARAMETERS-PARSE")
    costs = _safe_load(root, Path("machine/facts/costs.json"), checks, "S12P03-COSTS-PARSE")
    capacity = _safe_load(root, CAPACITY_REPORT_PATH, checks, "S12P03-CAPACITY-PARSE")
    p01 = _safe_load(root, P01_EVIDENCE_PATH, checks, "S12P03-P01-EVIDENCE-PARSE")
    p02 = _safe_load(root, P02_EVIDENCE_PATH, checks, "S12P03-P02-EVIDENCE-PARSE")
    grid = _safe_load(root, GRID_PATH, checks, "S12P03-GRID-PARSE")
    opportunity = _safe_load(root, OPPORTUNITY_COST_PATH, checks, "S12P03-OPPORTUNITY-COST-PARSE")
    if not all(isinstance(value, Mapping) for value in (fixture, parameters, costs, capacity, p01, p02, grid, opportunity)):
        return
    try:
        rebuilt_grid, rebuilt_opportunity = build_reports(
            fixture,
            parameters,
            costs,
            capacity,
            p01,
            p02,
            sha256_file(root / P01_EVIDENCE_PATH),
            sha256_file(root / P02_EVIDENCE_PATH),
            sha256_file(root / CAPACITY_REPORT_PATH),
        )
        replay_ok = (
            rebuilt_grid == grid
            and rebuilt_opportunity == opportunity
            and rebuilt_grid.get("sensitivity_grid_sha256") == fixture.get("expected_sensitivity_grid_sha256")
            and rebuilt_opportunity.get("opportunity_cost_sha256") == fixture.get("expected_opportunity_cost_sha256")
        )
        _add(
            checks,
            "S12P03-FROZEN-ECONOMICS-REPLAY-EXACT",
            replay_ok,
            {
                "expected_grid": fixture.get("expected_sensitivity_grid_sha256"),
                "actual_grid": rebuilt_grid.get("sensitivity_grid_sha256"),
                "expected_opportunity_cost": fixture.get("expected_opportunity_cost_sha256"),
                "actual_opportunity_cost": rebuilt_opportunity.get("opportunity_cost_sha256"),
            },
        )
        bands = rebuilt_grid.get("return_bands", [])
        bands_ok = (
            len(bands) == 3
            and all(
                isinstance(item, Mapping)
                and set(item.get("return_band_cents", {})) == {"low", "central", "high"}
                and item["return_band_cents"]["low"] <= item["return_band_cents"]["central"] <= item["return_band_cents"]["high"]
                and _probability_text_in_range(item.get("confidence"))
                and _probability_text_in_range(item.get("failure_probability"))
                and item.get("target_covered") is False
                and item.get("action") == "SYNTHETIC_SENSITIVITY_NOT_ACTIONABLE"
                for item in bands
            )
            and rebuilt_grid.get("summary", {}).get("available_capacity_cents_from_signed_p02") == 4000
            and rebuilt_grid.get("summary", {}).get("highest_upper_band_cents") == 800
            and rebuilt_grid.get("summary", {}).get("lowest_upper_band_target_shortfall_cents") == 8200
        )
        _add(checks, "S12P03-ALL-RETURN-BANDS-CONFIDENCE-FAILURE-EXACT", bands_ok, rebuilt_grid.get("summary"))
        boundary_ok = (
            rebuilt_grid.get("decision") == "SYNTHETIC_ECONOMICS_SENSITIVITY_TARGET_UNVERIFIED_NO_RECOMMENDATION"
            and rebuilt_grid.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and rebuilt_grid.get("summary", {}).get("all_scenarios_leave_target_unverified") is True
            and rebuilt_grid.get("summary", {}).get("return_bands_are_synthetic_sensitivity_not_revenue") is True
            and rebuilt_grid.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        )
        _add(checks, "S12P03-NO-GUARANTEE-NO-TARGET-GATE-RELAXATION", boundary_ok, rebuilt_grid.get("decision"))
        operating = rebuilt_opportunity.get("operating_cost", {})
        cost_boundary = rebuilt_opportunity.get("return_cost_boundary", {})
        opportunity_ok = (
            operating.get("incremental_cash_budget_cents") == 0
            and operating.get("incremental_cash_spent_cents") == 0
            and operating.get("existing_resources_are_not_relabelled_zero") is True
            and operating.get("existing_recurring_cost_status") == "UNKNOWN_ACCOUNT_SPECIFIC_NO_BILLING_ACCESS"
            and len(rebuilt_opportunity.get("opportunity_cost_bands", [])) == 4
            and all(item.get("classification") == "SENSITIVITY_ONLY_NOT_OWNER_TIME_VALUATION" for item in rebuilt_opportunity.get("opportunity_cost_bands", []) if isinstance(item, Mapping))
            and cost_boundary.get("return_bands_are_not_realized_revenue") is True
            and cost_boundary.get("roi_reported") is False
            and cost_boundary.get("target_curve_or_sensitivity_may_substitute_for_actual_return") is False
        )
        _add(checks, "S12P03-ZERO-NEW-CASH-AND-OPPORTUNITY-COST-DISCLOSED", opportunity_ok, operating)
        for relative in (MODEL_PATH, GRID_PATH, OPPORTUNITY_COST_PATH, FIXTURE_PATH, CAPACITY_REPORT_PATH, P01_EVIDENCE_PATH, P02_EVIDENCE_PATH, TEST_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (EconomicsError, ValueError, KeyError, TypeError) as exc:
        _add(checks, "S12P03-ECONOMICS-RUNNER", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    prohibited_literals = {"sleep(", "submit_order", "retry_order", "gmail", "cloudflare", "ovh", "float("}
    try:
        source = (root / MODEL_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        prohibited = sorted(imports.intersection(prohibited_imports))
        literals = sorted(value for value in prohibited_literals if value in source)
        _add(checks, "S12P03-STATIC-NO-NETWORK-SOAK-ORDER-OR-PRODUCTION-CAPABILITY", not prohibited and not literals, {"imports": prohibited, "literals": literals})
    except Exception as exc:
        _add(checks, "S12P03-STATIC-NO-NETWORK-SOAK-ORDER-OR-PRODUCTION-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        scan = scan_dependency_budget(root)
        passed = scan.get("status") == "PASS" and scan.get("summary", {}).get("paid_or_unknown_dependencies") == 0
        _add(checks, "S12P03-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", passed, scan.get("summary"))
    except Exception as exc:
        _add(checks, "S12P03-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", False, "%s: %s" % (type(exc).__name__, exc))


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
        _add(checks, "S12P03-TARGETED-JUNIT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S12P03-TARGETED-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S12P03-PAID-DEPENDENCY-REPORT-PASS", all(line in scan for line in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S12P03-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S12P03-TASKPACK-REPORT-PARSE")
    _add(checks, "S12P03-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "ECONOMICS_SENSITIVITY_READY_DOWNSTREAM_FALSIFICATION_GATE_REQUIRED" if not failed else "S12/P03_BLOCKED",
        "next": "S12/P04_READY_NOT_STARTED" if not failed else "S12/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "hashes": dict(hashes),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
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
        "evidence_id": "EVD-S12-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_ECONOMICS_SENSITIVITY_DISCLOSURE_RESTORE_SIGNED_P02_KEEP_ALL_EVIDENCE",
        "feature_flag_id": "economics:sensitivity_disclosure",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [MODEL_PATH, GRID_PATH, OPPORTUNITY_COST_PATH, FIXTURE_PATH, CAPACITY_REPORT_PATH, P01_EVIDENCE_PATH, P02_EVIDENCE_PATH, TEST_PATH, *_FACT_PATHS]
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
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S12-P03",
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
            "code": sha256_file(root / Path("abd_acceptance/economics_sensitivity.py")),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "shared_runtime_contract": _shared_runtime_contract(),
        "commands": [
            "uv run --frozen --python 3.12 python economics.py --fixture machine/tests/fixtures/S12_P03.json --parameters machine/facts/parameters.json --costs machine/facts/costs.json --capacity-report capacity_report.json --p01-evidence machine/evidence/EVD-S12-P01.json --p02-evidence machine/evidence/EVD-S12-P02.json --sensitivity-grid sensitivity_grid.json --opportunity-cost opportunity_cost.json",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S12/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S12/P03_test.py --junitxml=machine/evidence/S12/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S12/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S12-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"return_band_scenarios": 3, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S12_P03_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        raise EconomicsSensitivityAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-AC-S12-P03",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S12/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = sum(row.get("id") == replacement["id"] for row in rows)
    if matches > 1:
        raise EconomicsSensitivityAcceptanceError("S12/P03 evidence-index row is duplicated")
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
        raise EconomicsSensitivityAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise EconomicsSensitivityAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S12/P04_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise EconomicsSensitivityAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "ECONOMICS_SENSITIVITY_READY_DOWNSTREAM_FALSIFICATION_GATE_REQUIRED"
        and evidence.get("next") == "S12/P04_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == "economics:sensitivity_disclosure"
        and rollback.get("external_state_changed") is False
    )
    if not valid:
        raise EconomicsSensitivityAcceptanceError("existing S12/P03 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S12/P04_READY_NOT_STARTED"}
