"""Independent fail-closed acceptance oracle for ABD S13/P02.

Only frozen synthetic tickets and visible-page snapshots are replayed here.
The verifier never opens a platform, reads a real account, installs a browser
extension, submits an order, or waits for elapsed real time.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ET

from quote_check import (
    CLAIM_BOUNDARY,
    GREEN_STATUS,
    OPEN_MODE,
    OWNER_ACTION,
    RED_STATUS,
    REVOKE_ACTION,
    QuoteCheckError,
    apply_adverse_perturbation,
    build_copy_instruction,
    evaluate_quote,
    replay_match_fixtures,
    validate_match_fixtures,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S13-P02"
REQUIREMENT_ID = "REQ-S13-P02"
STAGE_ID = "S13"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
DECIMAL_PRECISION = 50
ODDS_STEP = Decimal("0.000001")

RUNTIME_PATH = Path("quote_check.py")
FIXTURES_PATH = Path("match_fixtures.json")
COMPANION_PATH = Path("browser_companion")
COMPANION_FILES = (
    COMPANION_PATH / "manifest.json",
    COMPANION_PATH / "background.js",
    COMPANION_PATH / "content.js",
    COMPANION_PATH / "README.md",
)
ORACLE_PATH = Path("abd_acceptance/platform_quote_check.py")
TEST_PATH = Path("tests/S13/P02_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S13_P02.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S13-P01.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S13/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S13/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "ui:browser_companion_visible_quote_check"
_FACT_PATHS = (
    Path("machine/facts/canonical_facts.json"),
    Path("machine/facts/parameters.json"),
    Path("machine/facts/provider_contracts.json"),
    Path("machine/facts/requirements.json"),
    Path("machine/facts/acceptance_contracts.json"),
    Path("machine/facts/task_graph.json"),
    Path("machine/facts/traceability_matrix.json"),
    Path("machine/facts/roadmap.json"),
)


class PlatformQuoteCheckAcceptanceError(ValueError):
    """Raised when a S13/P02 delivery cannot be replayed safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


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
        raise PlatformQuoteCheckAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise PlatformQuoteCheckAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise PlatformQuoteCheckAcceptanceError("blank evidence-index row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise PlatformQuoteCheckAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(value)
    return rows


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PlatformQuoteCheckAcceptanceError("timestamp lacks timezone")
    return parsed


def _decimal_odds(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PlatformQuoteCheckAcceptanceError("odds are invalid") from exc
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if not parsed.is_finite() or parsed <= Decimal("1") or parsed.quantize(ODDS_STEP) != parsed:
            raise PlatformQuoteCheckAcceptanceError("odds differ from frozen scale")
    return parsed


def _reference_outcome(ticket: Mapping[str, Any], snapshot: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    """Independent minimal reference for the red/green decision, not the runner."""

    failures: list[str] = []
    if snapshot["visible_fields_complete"] is not True:
        failures.append("VISIBLE_FIELDS_UNAVAILABLE")
    if snapshot["provider_id"] != ticket["provider_id"]:
        failures.append("PROVIDER_IDENTITY_MISMATCH")
    if snapshot["event_id"] != ticket["event_id"]:
        failures.append("EVENT_IDENTITY_MISMATCH")
    if snapshot["market_id"] != ticket["market_id"]:
        failures.append("MARKET_IDENTITY_MISMATCH")
    if snapshot["selection_id"] != ticket["selection_id"]:
        failures.append("SELECTION_IDENTITY_MISMATCH")
    if _decimal_odds(snapshot["current_odds"]) < _decimal_odds(ticket["minimum_odds"]):
        failures.append("CURRENT_ODDS_BELOW_MINIMUM")
    if _parse_timestamp(snapshot["observed_at"]) >= _parse_timestamp(ticket["advice_expires_at"]):
        failures.append("ADVICE_EXPIRED")
    if snapshot["risk_feature_enabled"] is not True:
        failures.append("RISK_FEATURE_DISABLED")
    return (GREEN_STATUS, OWNER_ACTION, failures) if not failures else (RED_STATUS, REVOKE_ACTION, failures)


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S13P02-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S13P02-CONTRACTS-PARSE")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S13P02-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S13P02-TRACEABILITY-PARSE")
    roadmap = _safe_load(root, Path("machine/facts/roadmap.json"), checks, "S13P02-ROADMAP-PARSE")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(graph, Mapping) or not isinstance(traceability, list) or not isinstance(roadmap, Mapping):
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [item for item in graph.get("tasks", []) if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        stages = [item for item in roadmap.get("stages", []) if isinstance(item, Mapping) and item.get("id") == STAGE_ID]
        phase = next((item for item in stages[0].get("phases", []) if item.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
        expected_scope = ["browser_companion", "quote_check.py", "match_fixtures.json"]
        expected_tasks = ["T-S13-P02-01", "T-S13-P02-02", "T-S13-P02-03"]
        task_outputs = {output for task in tasks for output in task.get("outputs", [])}
        exact = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "低于最低赔率、身份不符或过期立即红色撤销。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == {
                "type": "EXECUTABLE",
                "command": "python -m abd_acceptance --contract AC-S13-P02 --evidence machine/evidence",
                "rule": "低于最低赔率、身份不符或过期立即红色撤销。",
            }
            and contract.get("pass_gate") == requirement.get("target")
            and phase.get("outputs") == expected_scope
            and phase.get("pass_gate") == requirement.get("target")
        )
        _add(checks, "S13P02-TASKPACK-EXACT", exact, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == expected_tasks
            and tasks[0].get("depends_on") == ["T-S13-P01-03"]
            and tasks[1].get("depends_on") == ["T-S13-P02-01"]
            and tasks[2].get("depends_on") == ["T-S13-P02-02"]
            and all(item in task_outputs for item in expected_scope + [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(), EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()])
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == expected_tasks
            and trace.get("test_ids") == ["TEST-S13-P02", "TEST-S13-P02-BOUNDARY", "TEST-S13-P02-REPLAY"]
            and trace.get("evidence_id") == "EVD-S13-P02"
            and trace.get("artifact_ids") == ["ART-S13-P02-01", "ART-S13-P02-02", "ART-S13-P02-03"]
        )
        _add(checks, "S13P02-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S13P02-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, PREDECESSOR_PATH, checks, "S13P02-P01-PREDECESSOR-PARSE")
    try:
        actual_hash = sha256_file(root / PREDECESSOR_PATH)
        hashes[PREDECESSOR_PATH.as_posix()] = actual_hash
    except Exception as exc:
        _add(checks, "S13P02-P01-PREDECESSOR-INDEXED", False, "%s: %s" % (type(exc).__name__, exc))
        return
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        index = _row(rows, "INDEX-AC-S13-P01")
        indexed = index.get("actual_artifact") == PREDECESSOR_PATH.as_posix() and index.get("artifact_sha256") == actual_hash
    except Exception as exc:
        indexed = False
        index = "%s: %s" % (type(exc).__name__, exc)
    signed = (
        isinstance(evidence, Mapping)
        and evidence.get("contract_id") == "AC-S13-P01"
        and evidence.get("status") == "PASS"
        and evidence.get("next") == "S13/P02_READY_NOT_STARTED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
    )
    _add(checks, "S13P02-P01-PREDECESSOR-SIGNED", signed, evidence.get("status") if isinstance(evidence, Mapping) else evidence)
    _add(checks, "S13P02-P01-PREDECESSOR-INDEXED", indexed, index)


def _check_parameters_and_provider_contracts(root: Path, checks: List[Dict[str, Any]]) -> None:
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S13P02-PARAMETERS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/provider_contracts.json"), checks, "S13P02-PROVIDER-CONTRACTS-PARSE")
    if not isinstance(parameters, Mapping) or not isinstance(contracts, Mapping):
        return
    numeric = parameters.get("numeric_determinism")
    numeric_ok = isinstance(numeric, Mapping) and (
        numeric.get("authoritative_decimal_precision_digits") == 50
        and numeric.get("odds_storage_scale") == "1e-6"
        and numeric.get("boundary_perturbation_absolute_threshold") == "0.0001"
        and numeric.get("boundary_perturbation_time_adverse_seconds") == 2
        and numeric.get("odds_perturbation") == "ONE_PROVIDER_TICK_ADVERSE"
        and numeric.get("unstable_action") == "NO_RECOMMENDATION"
    )
    _add(checks, "S13P02-NUMERIC-BOUNDARY-PARAMETERS-EXACT", numeric_ok, numeric)
    capabilities = contracts.get("capabilities")
    overlay = next((item for item in capabilities if isinstance(item, Mapping) and item.get("mode") == "OWNER_DEVICE_OVERLAY"), None) if isinstance(capabilities, list) else None
    provider_ok = isinstance(overlay, Mapping) and overlay == {
        "mode": "OWNER_DEVICE_OVERLAY",
        "name_zh": "用户页面即时校验",
        "default": "ENABLED_WHEN_INSTALLED",
        "requirements": ["只读取当前可见赛事/盘口/赔率", "不自动提交", "不把页面文字当指令"],
        "failure": "SHOW_MANUAL_CHECK_OR_CANCEL_TICKET",
    }
    _add(checks, "S13P02-OWNER-DEVICE-OVERLAY-CONTRACT-EXACT", provider_ok, overlay)


def _check_runner_and_fixture(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, FIXTURES_PATH, checks, "S13P02-MATCH-FIXTURES-PARSE")
    if not isinstance(fixture, Mapping):
        return
    try:
        normalized = validate_match_fixtures(fixture)
        fixture_contract_ok = (
            normalized.get("fixture_id") == "FIX-S13-P02-VISIBLE-QUOTE-CHECK"
            and normalized.get("fixed_clock") == FIXED_CLOCK
            and len(normalized.get("cases", [])) == 10
            and len(normalized.get("adverse_scenarios", [])) == 2
            and normalized.get("claim_boundary") == CLAIM_BOUNDARY
        )
        _add(checks, "S13P02-FIXTURE-CONTRACT-EXACT", fixture_contract_ok, {"fixture_id": normalized.get("fixture_id"), "case_count": len(normalized.get("cases", [])), "adverse_scenario_count": len(normalized.get("adverse_scenarios", []))})
        binding_ok = (
            normalized["ticket"].get("parameters_sha256") == sha256_file(root / "machine/facts/parameters.json")
            and normalized["ticket"].get("provider_contracts_sha256") == sha256_file(root / "machine/facts/provider_contracts.json")
        )
        _add(checks, "S13P02-TICKET-PARAMETER-AND-PROVIDER-HASHES-EXACT", binding_ok, {"parameters_sha256": normalized["ticket"].get("parameters_sha256"), "provider_contracts_sha256": normalized["ticket"].get("provider_contracts_sha256")})
        replay = replay_match_fixtures(normalized)
        case_outputs: list[Dict[str, Any]] = []
        case_ok = True
        case_by_id = {case["case_id"]: case for case in normalized["cases"]}
        for case in normalized["cases"]:
            status, action, failures = _reference_outcome(normalized["ticket"], case["snapshot"])
            actual = evaluate_quote(normalized["ticket"], case["snapshot"])
            exact = (
                status == case["expected_status"] == actual.get("status")
                and action == case["expected_action"] == actual.get("action")
                and failures == case["expected_failed_gate_ids"] == actual.get("failed_gate_ids")
                and actual.get("automatic_platform_open_performed") is False
                and actual.get("order_submission_enabled") is False
                and actual.get("claim_boundary") == CLAIM_BOUNDARY
            )
            case_ok = case_ok and exact
            case_outputs.append({"case_id": case["case_id"], "status": actual.get("status"), "failed_gate_ids": actual.get("failed_gate_ids")})
        _add(checks, "S13P02-FROZEN-VISIBLE-QUOTE-REPLAY-EXACT", case_ok, case_outputs)
        adverse_outputs: list[Dict[str, Any]] = []
        adverse_ok = True
        for scenario in normalized["adverse_scenarios"]:
            base = case_by_id[scenario["base_case_id"]]["snapshot"]
            altered = apply_adverse_perturbation(
                base,
                odds_down_ticks=scenario["odds_down_ticks"],
                seconds_later=scenario["seconds_later"],
            )
            status, _action, failures = _reference_outcome(normalized["ticket"], altered)
            actual = evaluate_quote(normalized["ticket"], altered)
            exact = (
                status == scenario["expected_status"] == actual.get("status")
                and failures == scenario["expected_failed_gate_ids"] == actual.get("failed_gate_ids")
            )
            adverse_ok = adverse_ok and exact
            adverse_outputs.append({"scenario_id": scenario["scenario_id"], "status": actual.get("status"), "failed_gate_ids": actual.get("failed_gate_ids")})
        _add(checks, "S13P02-ONE_IN_TEN_THOUSAND_BOUNDARY-REVOKES", adverse_ok, adverse_outputs)
        expected_replay = [
            {"case_id": item["case_id"], "status": item["expected_status"], "action": item["expected_action"], "failed_gate_ids": item["expected_failed_gate_ids"]}
            for item in normalized["cases"]
        ]
        replay_ok = [
            {"case_id": item["case_id"], "status": item["status"], "action": item["action"], "failed_gate_ids": item["failed_gate_ids"]}
            for item in replay["case_results"]
        ] == expected_replay
        _add(checks, "S13P02-DETERMINISTIC-REPLAY-EXACT", replay_ok, replay.get("replay_sha256"))
        copy_instruction = build_copy_instruction(normalized["ticket"])
        copy_ok = (
            copy_instruction.get("open_mode") == OPEN_MODE
            and copy_instruction.get("deep_link_status") == "UNAVAILABLE_WITHOUT_VERIFIED_PROVIDER_CONTRACT"
            and copy_instruction.get("automatic_platform_open_performed") is False
            and copy_instruction.get("external_network_accessed") is False
            and copy_instruction.get("order_submission_enabled") is False
            and copy_instruction.get("synthetic_test_only") is True
        )
        _add(checks, "S13P02-COPY-INSTRUCTION-ONLY-NO-AUTO-OPEN", copy_ok, copy_instruction)
        for relative in (RUNTIME_PATH, FIXTURES_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except Exception as exc:
        _add(checks, "S13P02-RUNNER-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_browser_companion(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        manifest = strict_json_load(root / COMPANION_FILES[0])
        background = (root / COMPANION_FILES[1]).read_text(encoding="utf-8")
        content = (root / COMPANION_FILES[2]).read_text(encoding="utf-8")
        readme = (root / COMPANION_FILES[3]).read_text(encoding="utf-8")
        manifest_ok = (
            isinstance(manifest, Mapping)
            and manifest.get("manifest_version") == 3
            and manifest.get("version") == VERSION
            and manifest.get("permissions") == ["activeTab", "scripting"]
            and "host_permissions" not in manifest
            and "externally_connectable" not in manifest
            and manifest.get("background") == {"service_worker": "background.js"}
            and manifest.get("action") == {"default_title": "即时校验"}
        )
        _add(checks, "S13P02-BROWSER-COMPANION-LEAST-PRIVILEGE", manifest_ok, manifest)
        prohibited = ("fetch" + "(", "XMLHttpRequest", "WebSocket", "window." + "open", ".sub" + "mit(", ".cl" + "ick(", "localStorage", "indexedDB", "document.cookie", "new " + "Date")
        source_ok = (
            all(token not in background and token not in content for token in prohibited)
            and "ABD_SET_LOCAL_TICKET" in background
            and "ABD_VISIBLE_QUOTE_SNAPSHOT" in background
            and "data-abd-visible-field" in content
            and "OWNER_FINAL_ORDER_MANUAL_ONLY" in background
            and "RED_REVOKE_DO_NOT_ORDER" in background
        )
        _add(checks, "S13P02-BROWSER-COMPANION-NO-NETWORK-CLICK-OR-ORDER", source_ok, "static component boundary")
        documentation_ok = all(token in readme for token in ["没有站点权限", "红色撤销", "不自动打开平台", "真实浏览器运行证据均不在 S13/P02"])
        _add(checks, "S13P02-BROWSER-COMPANION-BOUNDARY-DOCUMENTED", documentation_ok, COMPANION_FILES[3].as_posix())
        for relative in COMPANION_FILES:
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except Exception as exc:
        _add(checks, "S13P02-BROWSER-COMPANION-STATIC", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "asyncio", "time", "random", "os"}
    prohibited_literals = {"sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "web" + "hook", "smtp" + "lib"}
    failures: list[Any] = []
    try:
        source = (root / RUNTIME_PATH).read_text(encoding="utf-8")
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
            failures.append({"path": RUNTIME_PATH.as_posix(), "imports": bad_imports, "literals": bad_literals})
    except Exception as exc:
        failures.append({"path": RUNTIME_PATH.as_posix(), "error": "%s: %s" % (type(exc).__name__, exc)})
    _add(checks, "S13P02-STATIC-NO-NETWORK-SOAK-OR-ORDER", not failures, failures or "static boundary intact")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        scan = scan_dependency_budget(root)
        passed = scan.get("status") == "PASS" and scan.get("summary", {}).get("paid_or_unknown_dependencies") == 0
        _add(checks, "S13P02-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", passed, scan.get("summary"))
    except Exception as exc:
        _add(checks, "S13P02-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
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
        cases = list(ET.parse(root / JUNIT_PATH).getroot().iter("testcase"))
        passed = summary["tests"] >= 16 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and all(case.attrib.get("time") == "0.000" for case in cases)
        _add(checks, "S13P02-TARGETED-JUNIT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S13P02-TARGETED-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S13P02-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S13P02-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S13P02-TASKPACK-REPORT-PARSE")
    _add(checks, "S13P02-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "BROWSER_COMPANION_AND_LOCAL_VISIBLE_QUOTE_CHECK_READY_POST_ADVICE_EVIDENCE_REQUIRED" if passed else "S13/P02_BLOCKED",
        "next": "S13/P03_READY_NOT_STARTED" if passed else "S13/P02_REMEDIATION_REQUIRED",
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
    _check_predecessor(root, checks, hashes)
    _check_parameters_and_provider_contracts(root, checks)
    _check_runner_and_fixture(root, checks, hashes)
    _check_browser_companion(root, checks, hashes)
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
        for relative in (RUNTIME_PATH, FIXTURES_PATH, *COMPANION_FILES, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_BROWSER_COMPANION_VISIBLE_QUOTE_CHECK_RESTORE_SIGNED_S13_P01_KEEP_ALL_EVIDENCE",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, RUNTIME_PATH, FIXTURES_PATH, *COMPANION_FILES, TEST_PATH, FIXTURE_PATH, *_FACT_PATHS, PREDECESSOR_PATH]
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
        "evidence_id": "EVD-S13-P02",
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
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S13/P02/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S13/P02_test.py --junitxml=machine/evidence/S13/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S13/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S13-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"case_count": 10, "adverse_scenario_count": 2, "real_time_wait_performed": False},
        "external_effect_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S13_P02_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED",
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
        raise PlatformQuoteCheckAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-AC-S13-P02",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S13/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = sum(row.get("id") == replacement["id"] for row in rows)
    if matches != 1:
        raise PlatformQuoteCheckAcceptanceError("S13/P02 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise PlatformQuoteCheckAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise PlatformQuoteCheckAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/P03_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise PlatformQuoteCheckAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "BROWSER_COMPANION_AND_LOCAL_VISIBLE_QUOTE_CHECK_READY_POST_ADVICE_EVIDENCE_REQUIRED"
        and evidence.get("next") == "S13/P03_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
    )
    if not valid:
        raise PlatformQuoteCheckAcceptanceError("existing S13/P02 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/P03_READY_NOT_STARTED",
    }
