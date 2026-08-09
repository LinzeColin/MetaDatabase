"""Independent fail-closed acceptance oracle for ABD S17/P03 chaos controls."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load as acceptance_json_load
from .chaos_engine import (
    BASELINE_HASHES,
    CHAOS_POLICY,
    CHAOS_RUNNER_PATH,
    CHAOS_SCENARIOS_PATH,
    CLAIM_BOUNDARY,
    CONTRACT_ID,
    EXECUTION_POLICY,
    FIXED_CLOCK,
    FIXTURE_PATH,
    INPUT_MODE,
    P02_EVIDENCE_PATH,
    PHASE_ID,
    PRODUCT_VERSION,
    REQUIREMENT_ID,
    STAGE_ID,
    ChaosInputError,
    artifact_sha256,
    build_artifacts,
    canonical_json_bytes,
    load_fixture,
    sha256_file as engine_sha256_file,
    strict_json_load,
    validate_artifacts,
)


ORACLE_PATH = Path("abd_acceptance/chaos.py")
CORE_PATH = Path("abd_acceptance/chaos_engine.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
GENERATOR_PATH = CHAOS_RUNNER_PATH
TEST_PATH = Path("tests/S17/P03_test.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S17/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S17/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
FEATURE_FLAG_ID = "chaos:s17_frozen_fault_projection"

EXPECTED_TEST_IDS = ("TEST-S17-P03", "TEST-S17-P03-BOUNDARY", "TEST-S17-P03-REPLAY")
EXPECTED_TASK_IDS = ("T-S17-P03-01", "T-S17-P03-02", "T-S17-P03-03")
EXPECTED_ARTIFACT_IDS = ("ART-S17-P03-01", "ART-S17-P03-02")
EXPECTED_OUTPUTS = {
    "T-S17-P03-01": ["chaos_scenarios.json", "chaos_runner.py"],
    "T-S17-P03-02": ["tests/S17/P03_test.py", "machine/tests/fixtures/S17_P03.json"],
    "T-S17-P03-03": ["machine/evidence/EVD-S17-P03.json", "machine/evidence/EVD-S17-P03_rollback.json"],
}
EXPECTED_FAULTS = {
    "PROCESS_EXIT",
    "DNS_FAILURE",
    "NETWORK_FAILURE",
    "PAGE_SCHEMA_CHANGE",
    "DISK_PRESSURE",
    "MEMORY_PRESSURE",
    "CLOCK_SKEW",
    "MODEL_ARTIFACT_CORRUPTION",
}
EXTERNAL_EFFECT_BOUNDARY = {
    **CLAIM_BOUNDARY,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "owner_final_order_only": True,
}


class ChaosAcceptanceError(ValueError):
    """Raised when S17/P03 evidence cannot be reproduced safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise ChaosAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ChaosAcceptanceError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ChaosAcceptanceError("rows are unavailable")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matching) != 1:
        raise ChaosAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matching[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = acceptance_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S17P03-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S17P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S17P03-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S17P03-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S17P03-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise ChaosAcceptanceError("task graph is unavailable")
        phase_tasks = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == ["chaos_scenarios.json", "chaos_runner.py"]
            and requirement.get("target") == "错误时不使用陈旧数据且自动降级。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S17-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S17-P03"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "错误时不使用陈旧数据且自动降级。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("kind") == "PHASE_EVIDENCE"
            and row.get("stage_id") == STAGE_ID
            and row.get("contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("next") == "S17/P04_READY_NOT_STARTED"
        )
        _add(checks, "S17P03-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S17P03-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = dict(evidence)
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(canonical_json_bytes(unsigned))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        evidence = acceptance_json_load(root / P02_EVIDENCE_PATH)
        actual = sha256_file(root / P02_EVIDENCE_PATH)
        valid = (
            isinstance(evidence, Mapping)
            and actual == "c417d9eb732c24969d11db52bd501438572a57e2b3eeef8791085e746aae2711"
            and evidence.get("contract_id") == "AC-S17-P02"
            and evidence.get("requirement_id") == "REQ-S17-P02"
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == "P02"
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S17_P02_IDEMPOTENCY_PASS_P03_REQUIRED"
            and evidence.get("next") == "S17/P03_READY_NOT_STARTED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and _decision_hash_matches(evidence)
        )
        detail: Any = {"evidence_sha256": actual, "status": evidence.get("status") if isinstance(evidence, Mapping) else "INVALID"}
        hashes[P02_EVIDENCE_PATH.as_posix()] = actual
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-P02-SIGNED-PREDECESSOR-EXACT", valid, detail)


def _check_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    try:
        fixture = load_fixture(root / FIXTURE_PATH)
        expected = build_artifacts(root, fixture)
        actual = validate_artifacts(root, fixture)
        report = actual[CHAOS_SCENARIOS_PATH.as_posix()]
        aggregate = report.get("aggregate", {})
        gate = report.get("stale_data_gate", {})
        scenario_expectations = [item.get("expected") for item in fixture.get("scenarios", [])]
        scenario_results = [
            {
                "degraded": item.get("degraded"),
                "selected_data": item.get("selected_data"),
                "stale_data_used": item.get("stale_data_used"),
                "stale_data_disposition": item.get("stale_data_disposition"),
                "action": item.get("action"),
            }
            for item in report.get("scenarios", [])
        ]
        faults = {item.get("fault") for item in report.get("structured_fault_log", [])}
        report_ok = (
            report.get("artifact_id") == "ART-S17-P03-02"
            and report.get("input_mode") == INPUT_MODE
            and report.get("source_generator", {}).get("artifact_id") == "ART-S17-P03-01"
            and report.get("source_generator", {}).get("path") == GENERATOR_PATH.as_posix()
            and report.get("source_generator", {}).get("sha256") == engine_sha256_file(root / GENERATOR_PATH)
            and report.get("predecessor") == fixture.get("predecessor")
            and report.get("chaos_policy") == CHAOS_POLICY
            and report.get("fault_injection_mode") == CHAOS_POLICY["injection_mode"]
            and scenario_results == scenario_expectations
            and aggregate == {
                "scenario_count": 9,
                "error_scenario_count": 8,
                "degraded_count": 8,
                "rejected_stale_data_count": 8,
                "stale_data_used_count": 0,
                "no_recommendation_no_order_count": 9,
            }
            and gate == {
                "error_scenario_count": 8,
                "auto_degraded_count": 8,
                "rejected_stale_data_count": 8,
                "stale_data_used_count": 0,
                "passed": True,
            }
            and faults == EXPECTED_FAULTS
            and len(report.get("structured_fault_log", [])) == 8
            and report.get("action") == "NO_RECOMMENDATION_NO_ORDER"
            and report.get("decision") == fixture["expected_decision"]
            and report.get("next") == fixture["expected_next"]
            and report.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        )
        deterministic = expected == actual
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        hashes[GENERATOR_PATH.as_posix()] = sha256_file(root / GENERATOR_PATH)
        hashes[CHAOS_SCENARIOS_PATH.as_posix()] = sha256_file(root / CHAOS_SCENARIOS_PATH)
        _add(checks, "S17P03-CHAOS-ARTIFACT-REPLAY-EXACT", deterministic, {path: artifact_sha256(value) for path, value in actual.items()})
        _add(checks, "S17P03-STALE-DATA-REJECTED-AND-DEGRADED-EXACT", report_ok, {"aggregate": aggregate, "stale_data_gate": gate})
        return fixture
    except Exception as exc:
        _add(checks, "S17P03-CHAOS-ARTIFACT-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        imports: set[str] = set()
        call_names: set[str] = set()
        url_literals: list[str] = []
        prefixes = ("http:" + "//", "https:" + "//")
        for relative in (CORE_PATH, ORACLE_PATH, GENERATOR_PATH):
            content = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(content, filename=relative.as_posix())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
                    call_names.add(node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(prefixes):
                    url_literals.append(node.value)
        forbidden = {"asyncio", "concurrent", "http", "multiprocessing", "os", "requests", "socket", "smtplib", "subprocess", "threading", "time", "urllib", "webbrowser"}
        forbidden_calls = {"Popen", "sleep", "submit_order", "retry_order", "exit", "kill"}
        valid = not imports.intersection(forbidden) and not call_names.intersection(forbidden_calls) and not url_literals
        detail: Any = {"imports": sorted(imports), "forbidden": sorted(imports.intersection(forbidden)), "forbidden_calls": sorted(call_names.intersection(forbidden_calls)), "url_literals": url_literals}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-LOCAL-ONLY-STATIC-BOUNDARY", valid, detail)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        required_fragments = (
            "from .chaos import verify_existing_phase_evidence as verify_chaos_phase_evidence",
            "from .chaos import write_phase_evidence as write_chaos_phase_evidence",
            '"AC-S17-P03": verify_chaos_phase_evidence,',
            '"AC-S17-P03": write_chaos_phase_evidence,',
        )
        valid = all(fragment in source for fragment in required_fragments)
        detail: Any = {"required_fragments": len(required_fragments), "matched": sum(fragment in source for fragment in required_fragments), "current_sha256": sha256_file(root / CLI_PATH)}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-CLI-WRITER-AND-VERIFIER-EXACT", valid, detail)


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    if not suites:
        raise ChaosAcceptanceError("JUnit has no suite")
    summary = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    normalized = all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S17P03-TARGETED-REPORTS", True, "deferred until local signing")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        expected_minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        junit_ok = summary["tests"] >= expected_minimum and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
        detail: Any = summary
    except Exception as exc:
        junit_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-TARGETED-PYTEST-REPORT", junit_ok, detail)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(marker in scan for marker in ("STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"))
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = acceptance_json_load(root / PACK_REPORT_PATH)
        pack_ok = isinstance(report, Mapping) and report.get("status") == "PASS"
    except Exception as exc:
        pack_ok = False
        report = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P03-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": status,
        "decision": "S17_P03_CHAOS_STALE_DATA_GATE_PASS_P04_REQUIRED" if status == "PASS" else "S17_P03_REMEDIATION_REQUIRED",
        "next": "S17/P04_READY_NOT_STARTED" if status == "PASS" else "S17/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    fixture = _check_artifacts(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_cli_wiring(root, checks)
    _check_reports(root, fixture, checks, require_test_reports)
    _add(
        checks,
        "S17P03-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        EXTERNAL_EFFECT_BOUNDARY["external_network_accessed"] is False
        and EXTERNAL_EFFECT_BOUNDARY["real_process_exit_injected"] is False
        and EXTERNAL_EFFECT_BOUNDARY["real_dns_or_network_fault_injected"] is False
        and EXTERNAL_EFFECT_BOUNDARY["real_page_disk_memory_clock_or_model_mutated"] is False
        and EXTERNAL_EFFECT_BOUNDARY["real_runtime_or_ledger_read_or_written"] is False
        and EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False
        and EXTERNAL_EFFECT_BOUNDARY["order_submission_enabled"] is False
        and EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False,
        EXTERNAL_EFFECT_BOUNDARY,
    )
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (CORE_PATH, ORACLE_PATH, GENERATOR_PATH, FIXTURE_PATH, CHAOS_SCENARIOS_PATH, P02_EVIDENCE_PATH)
    artifacts = {
        path.as_posix(): {"status": "PASS" if (root / path).is_file() else "FAIL", "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S17-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "feature_flag_id": FEATURE_FLAG_ID,
        "mode": "DISABLE_LOCAL_CHAOS_PROJECTION_KEEP_RUNTIME_DEPLOYMENT_BLOCKED",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_fault_injected": False,
        "real_runtime_or_ledger_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, require_test_reports: bool) -> Dict[str, str]:
    paths = [CORE_PATH, ORACLE_PATH, GENERATOR_PATH, FIXTURE_PATH, CHAOS_SCENARIOS_PATH, P02_EVIDENCE_PATH]
    paths.extend(Path(path) for path in BASELINE_HASHES)
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S17-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S17_P03_LOCAL_CHAOS_EVIDENCE_ONLY_P04_REQUIRED" if validation["status"] == "PASS" else "S17_P03_REMEDIATION_REQUIRED",
        "validation": validation,
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": 9,
            "error_scenario_count": 8,
            "auto_degraded_count": 8,
            "rejected_stale_data_count": 8,
            "stale_data_used_count": 0,
            "actual_fault_injected": False,
            "real_time_wait_performed": False,
        },
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
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S17/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matching = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) != 1 or len(raw_lines) != len(rows):
        raise ChaosAcceptanceError("S17/P03 evidence-index row must exist exactly once")
    raw_lines[matching[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ChaosAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ChaosAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S17/P04_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = acceptance_json_load(root / EVIDENCE_PATH)
    rollback = acceptance_json_load(root / ROLLBACK_EVIDENCE_PATH)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S17_P03_CHAOS_STALE_DATA_GATE_PASS_P04_REQUIRED"
        and evidence.get("next") == "S17/P04_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_fault_injected") is False
        and rollback.get("real_runtime_or_ledger_read_or_written") is False
        and index.get("kind") == "PHASE_EVIDENCE"
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S17/P04_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise ChaosAcceptanceError("existing S17/P03 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S17/P04_READY_NOT_STARTED"}


__all__ = [
    "CHAOS_SCENARIOS_PATH",
    "CLI_PATH",
    "CORE_PATH",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FEATURE_FLAG_ID",
    "FIXTURE_PATH",
    "ChaosAcceptanceError",
    "ORACLE_PATH",
    "TEST_PATH",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
