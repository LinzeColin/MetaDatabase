"""Independent fail-closed acceptance oracle for ABD S10/P04.

The oracle replays only frozen synthetic adverse-boundary vectors.  It binds
the one-in-ten-thousand perturbation gate to reproducible local evidence and
never reaches a provider, account, market, order channel, deployment target,
or wall clock.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from robustness_gate import (
    CONTRACT_ID as RUNNER_CONTRACT_ID,
    EXTERNAL_EFFECT_BOUNDARY as RUNNER_EXTERNAL_EFFECT_BOUNDARY,
    RobustnessGateError,
    build_report,
    report_sha256,
    validate_registry,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S10-P04"
REQUIREMENT_ID = "REQ-S10-P04"
STAGE_ID = "S10"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

GATE_PATH = Path("robustness_gate.py")
VECTORS_PATH = Path("boundary_vectors.json")
REPORT_PATH = Path("robustness_report.json")
ORACLE_PATH = Path("abd_acceptance/robustness_gate.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
TEST_PATH = Path("tests/S10/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S10_P04.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S10-P03.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S10-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S10-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S10/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S10/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "model:adverse_perturbation_gate"
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH,)

_PREDECESSOR_SHA256 = "7b848a4e885b5f1b9b31752b88c8b136e1b66f734ed0cdf30926b325bbc0f55c"
_ROLLBACK_ARTIFACTS = (GATE_PATH, VECTORS_PATH, REPORT_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
_TASKPACK_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
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
_ADVERSE_SCENARIOS = {
    "probability_minus",
    "threshold_plus",
    "friction_plus",
    "time_plus",
    "odds_adverse",
    "parameter_worst_case",
    "all_adverse",
}
EXTERNAL_EFFECT_BOUNDARY = {
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


class RobustnessGateAcceptanceError(ValueError):
    """Raised when S10/P04 evidence cannot be replayed or trusted."""


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
        raise RobustnessGateAcceptanceError("rows are not a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise RobustnessGateAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise RobustnessGateAcceptanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise RobustnessGateAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    return rows


def _check_taskpack_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _TASKPACK_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S10P04-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "S10P04-BASELINE-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        requirements = strict_json_load(root / "machine/facts/requirements.json")
        contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
        graph = strict_json_load(root / "machine/facts/task_graph.json")
        traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [task for task in graph.get("tasks", []) if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        expected_scope = [GATE_PATH.as_posix(), VECTORS_PATH.as_posix(), REPORT_PATH.as_posix()]
        outputs = {output for task in tasks for output in task.get("outputs", [])}
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("value") == "对概率、阈值、摩擦、时间和赔率做不利扰动，动作翻转即不建议。"
            and requirement.get("target") == "所有硬边界±0.0001用例100%符合预期。"
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle")
            == {
                "type": "EXECUTABLE",
                "command": "python -m abd_acceptance --contract AC-S10-P04 --evidence machine/evidence",
                "rule": requirement.get("target"),
            }
            and contract.get("pass_gate") == requirement.get("target")
        )
        _add(checks, "S10P04-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == ["T-S10-P04-01", "T-S10-P04-02", "T-S10-P04-03"]
            and all(item in outputs for item in expected_scope)
            and TEST_PATH.as_posix() in outputs
            and FIXTURE_PATH.as_posix() in outputs
            and EVIDENCE_PATH.as_posix() in outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in outputs
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == ["T-S10-P04-01", "T-S10-P04-02", "T-S10-P04-03"]
            and trace.get("test_ids") == ["TEST-S10-P04", "TEST-S10-P04-BOUNDARY", "TEST-S10-P04-REPLAY"]
            and trace.get("evidence_id") == "EVD-S10-P04"
            and trace.get("artifact_ids") == ["ART-S10-P04-01", "ART-S10-P04-02", "ART-S10-P04-03"]
        )
        _add(checks, "S10P04-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(outputs)})
    except Exception as exc:
        _add(checks, "S10P04-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    value = _safe_load(root, PREDECESSOR_PATH, checks, "S10P04-P03-PREDECESSOR-STRICT-JSON")
    try:
        actual = sha256_file(root / PREDECESSOR_PATH)
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        index = _row(rows, "INDEX-AC-S10-P03")
    except Exception as exc:
        _add(checks, "S10P04-P03-PREDECESSOR-HASH", False, "%s: %s" % (type(exc).__name__, exc))
        return
    hashes[PREDECESSOR_PATH.as_posix()] = actual
    index_ok = index == {
        "actual_artifact": PREDECESSOR_PATH.as_posix(),
        "artifact_sha256": _PREDECESSOR_SHA256,
        "contract_id": "AC-S10-P03",
        "id": "INDEX-AC-S10-P03",
        "kind": "PHASE_EVIDENCE",
        "next": "S10/P04_READY_NOT_STARTED",
        "requirement_id": "REQ-S10-P03",
        "stage_id": "S10",
        "status": "PASS",
        "verified_at": FIXED_CLOCK,
    }
    passed = (
        isinstance(value, Mapping)
        and actual == _PREDECESSOR_SHA256
        and value.get("contract_id") == "AC-S10-P03"
        and value.get("status") == "PASS"
        and value.get("next") == "S10/P04_READY_NOT_STARTED"
        and index_ok
    )
    _add(
        checks,
        "S10P04-P03-PREDECESSOR-HASH",
        passed,
        {"expected": _PREDECESSOR_SHA256, "actual": actual, "index_bound": index_ok},
    )


def _validate_fixture(fixture: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "vectors_path",
        "parameters_path",
        "report_path",
        "predecessor",
        "claim_boundary",
        "expected_report_sha256",
    }
    if not isinstance(fixture, Mapping) or set(fixture) != fields:
        raise RobustnessGateAcceptanceError("fixture has an unexpected shape")
    identity_ok = (
        fixture["schema_version"] == "1.0.0"
        and fixture["fixture_id"] == "FIX-S10-P04-ADVERSE-ROBUSTNESS"
        and fixture["contract_id"] == CONTRACT_ID
        and fixture["requirement_id"] == REQUIREMENT_ID
        and fixture["stage_id"] == STAGE_ID
        and fixture["phase_id"] == PHASE_ID
        and fixture["product_version"] == VERSION
        and fixture["fixed_clock"] == FIXED_CLOCK
        and fixture["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        and fixture["vectors_path"] == VECTORS_PATH.as_posix()
        and fixture["parameters_path"] == "machine/facts/parameters.json"
        and fixture["report_path"] == REPORT_PATH.as_posix()
    )
    if not identity_ok:
        raise RobustnessGateAcceptanceError("fixture identity is invalid")
    predecessor = fixture["predecessor"]
    if predecessor != {"contract_id": "AC-S10-P03", "evidence_path": PREDECESSOR_PATH.as_posix(), "sha256": _PREDECESSOR_SHA256}:
        raise RobustnessGateAcceptanceError("fixture predecessor is invalid")
    boundary = fixture["claim_boundary"]
    if boundary != {
        "network_accessed": False,
        "actual_market_or_odds_observed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise RobustnessGateAcceptanceError("fixture claim boundary is unsafe")
    expected = fixture["expected_report_sha256"]
    if not isinstance(expected, str) or len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise RobustnessGateAcceptanceError("fixture expected_report_sha256 is invalid")
    return fixture


def _check_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S10P04-PARAMETERS-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S10P04-FIXTURE-STRICT-JSON")
    registry = _safe_load(root, VECTORS_PATH, checks, "S10P04-VECTORS-STRICT-JSON")
    stored_report = _safe_load(root, REPORT_PATH, checks, "S10P04-REPORT-STRICT-JSON")
    if not isinstance(parameters, Mapping) or not isinstance(fixture, Mapping) or not isinstance(registry, Mapping) or not isinstance(stored_report, Mapping):
        return
    try:
        validated_fixture = _validate_fixture(fixture)
        validated_registry = validate_registry(registry, parameters)
        rebuilt = build_report(validated_registry, parameters)
        digest = report_sha256(rebuilt)
        report_ok = (
            rebuilt.get("report_sha256") == digest
            and validated_fixture.get("expected_report_sha256") == digest
            and stored_report == rebuilt
            and rebuilt.get("report_id") == "RPT-S10-P04-ADVERSE-ROBUSTNESS"
            and rebuilt.get("contract_id") == CONTRACT_ID
            and rebuilt.get("requirement_id") == REQUIREMENT_ID
            and rebuilt.get("stage_id") == STAGE_ID
            and rebuilt.get("phase_id") == PHASE_ID
            and rebuilt.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        )
        _add(
            checks,
            "S10P04-FROZEN-ROBUSTNESS-REPLAY-EXACT",
            report_ok,
            {"expected": validated_fixture.get("expected_report_sha256"), "actual": digest, "stored_matches": stored_report == rebuilt},
        )
        _add(checks, "S10P04-NUMERIC-CONTRACT-EXACT", rebuilt.get("numeric_determinism") == _NUMERIC_DETERMINISM, rebuilt.get("numeric_determinism"))
        results = rebuilt.get("results")
        result_rows_ok = (
            isinstance(results, list)
            and len(results) == 12
            and all(
                isinstance(item, Mapping)
                and item.get("all_expected_matches") is True
                and item.get("baseline", {}).get("action") in {"NO_ORDER_NUMERIC_CANDIDATE", "NO_RECOMMENDATION"}
                and item.get("gate_action") in {"NO_ORDER_NUMERIC_CANDIDATE", "NO_RECOMMENDATION"}
                and set(item.get("scenarios", {}))
                == {
                    "baseline",
                    "probability_minus",
                    "probability_plus",
                    "threshold_minus",
                    "threshold_plus",
                    "friction_plus",
                    "time_plus",
                    "odds_adverse",
                    "parameter_worst_case",
                    "all_adverse",
                }
                and (not item.get("adverse_flip_dimensions") or item.get("gate_action") == "NO_RECOMMENDATION")
                for item in results
            )
        )
        _add(checks, "S10P04-ALL-HARD-BOUNDARY-EXPECTATIONS-EXACT", result_rows_ok, results)
        by_id = {item.get("vector_id"): item for item in results} if isinstance(results, list) else {}
        semantic_ok = (
            "probability_minus" in by_id.get("V02-PROBABILITY-MINUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "threshold_plus" in by_id.get("V04-THRESHOLD-PLUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "friction_plus" in by_id.get("V05-FRICTION-PLUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "time_plus" in by_id.get("V06-TIME-PLUS-FLIPS", {}).get("adverse_flip_dimensions", [])
            and "odds_adverse" in by_id.get("V08-ODDS-TICK-FLIPS", {}).get("adverse_flip_dimensions", [])
            and by_id.get("V11-COMBINED-ONLY-FLIPS", {}).get("adverse_flip_dimensions") == ["all_adverse"]
            and by_id.get("V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES", {}).get("baseline", {}).get("action") == "NO_RECOMMENDATION"
            and by_id.get("V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES", {}).get("gate_action") == "NO_RECOMMENDATION"
            and by_id.get("V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES", {}).get("scenarios", {}).get("probability_plus", {}).get("action") == "NO_ORDER_NUMERIC_CANDIDATE"
            and by_id.get("V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES", {}).get("scenarios", {}).get("threshold_minus", {}).get("action") == "NO_ORDER_NUMERIC_CANDIDATE"
        )
        _add(checks, "S10P04-EACH-ADVERSE-DIMENSION-AND-FAIL-CLOSED-SEMANTICS", semantic_ok, by_id)
        _add(
            checks,
            "S10P04-DECISION-AND-NEXT-EXACT",
            rebuilt.get("all_hard_boundary_expectations_match") is True
            and rebuilt.get("all_adverse_action_flips_force_no_recommendation") is True
            and rebuilt.get("base_no_recommendations_remain_closed") is True
            and rebuilt.get("decision") == "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED"
            and rebuilt.get("next") == "S10/STAGE_REVIEW_READY_NOT_STARTED",
            {"decision": rebuilt.get("decision"), "next": rebuilt.get("next")},
        )
        _add(
            checks,
            "S10P04-NO-EXTERNAL-RUNTIME-OR-ORDER-CLAIM",
            rebuilt.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY == RUNNER_EXTERNAL_EFFECT_BOUNDARY,
            rebuilt.get("external_effect_boundary"),
        )
        _add(
            checks,
            "S10P04-FINANCIAL-AND-PRODUCTION-STATUS-EXACT",
            rebuilt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED" and rebuilt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED",
            {"financial_target_status": rebuilt.get("financial_target_status"), "production_status": rebuilt.get("production_status")},
        )
        for relative in _ROLLBACK_ARTIFACTS:
            try:
                hashes[relative.as_posix()] = sha256_file(root / relative)
            except Exception as exc:
                _add(checks, "S10P04-ARTIFACT-%s" % relative.stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
    except (RobustnessGateError, RobustnessGateAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S10P04-FIXTURE-REGISTRY-AND-REPORT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    try:
        source = (root / GATE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        _add(checks, "S10P04-STATIC-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    imports: set[str] = set()
    forbidden_calls: list[str] = []
    float_literals: list[Any] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen", "urlopen"}:
            forbidden_calls.append(node.func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            float_literals.append(node.value)
    static_ok = (
        not (imports & prohibited_imports)
        and not forbidden_calls
        and not float_literals
        and "float(" not in source
        and "submit_order" not in source
        and "retry_order" not in source
    )
    _add(
        checks,
        "S10P04-STATIC-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER",
        static_ok,
        {"imports": sorted(imports), "calls": sorted(forbidden_calls), "float_literals": float_literals},
    )


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S10P04-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _junit_summary(path: Path) -> dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise RobustnessGateAcceptanceError("JUnit contains no suites")
    fields = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for field in fields:
            fields[field] += int(suite.attrib.get(field, "0"))
    return fields


def _junit_normalized(path: Path) -> bool:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
        for suite in suites
    )


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        passed = summary["tests"] >= 18 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and _junit_normalized(root / JUNIT_PATH)
        _add(checks, "S10P04-TARGETED-PYTEST-REPORT", passed, summary)
    except Exception as exc:
        _add(checks, "S10P04-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S10P04-SCAN-REPORT", "STATUS: PASS" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S10P04-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S10P04-PACK-REPORT-STRICT-JSON")
    _add(checks, "S10P04-PACK-REPORT-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("summary") if isinstance(report, Mapping) else "unavailable")


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
        "decision": "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S10/P04_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "hashes": dict(hashes),
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _add(checks, "S10P04-CONTRACT-ID-BOUND", RUNNER_CONTRACT_ID == CONTRACT_ID, RUNNER_CONTRACT_ID)
    _check_taskpack_hashes(root, checks, hashes)
    _check_taskpack_trace(root, checks)
    _check_predecessor(root, checks, hashes)
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
        "evidence_id": "EVD-S10-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_ADVERSE_PERTURBATION_GATE_RESTORE_SIGNED_S10_P03_KEEP_ALL_EVIDENCE",
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
    paths = [
        GATE_PATH,
        VECTORS_PATH,
        REPORT_PATH,
        ORACLE_PATH,
        TEST_PATH,
        FIXTURE_PATH,
        PREDECESSOR_PATH,
        *tuple(Path(path) for path in _TASKPACK_HASHES),
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "later dispatcher evolution must not invalidate phase-owned frozen evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        _json_bytes(
            {
                "contract_id": evidence.get("contract_id"),
                "decision": evidence.get("decision"),
                "next": evidence.get("next"),
                "validation": evidence.get("validation"),
            }
        )
    )


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S10-P04",
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
            "uv run --frozen --python 3.12 python robustness_gate.py --vectors boundary_vectors.json --parameters machine/facts/parameters.json --output robustness_report.json",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S10/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S10/P04_test.py --junitxml=machine/evidence/S10/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S10/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S10-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"vector_count": 12, "adverse_scenario_count": 7, "real_time_wait_performed": False},
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S10_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
    replacement = {
        "id": "INDEX-AC-S10-P04",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [replacement if row.get("id") == replacement["id"] else row for row in rows]
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise RobustnessGateAcceptanceError("planned S10/P04 evidence-index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def _evidence_index_is_bound(root: Path, evidence_hash: str) -> bool:
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception:
        return False
    expected = {
        "id": "INDEX-AC-S10-P04",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = [row for row in rows if row.get("id") == expected["id"]]
    return len(matches) == 1 and matches[0] == expected


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise RobustnessGateAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise RobustnessGateAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise RobustnessGateAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    evidence_hash = sha256_file(root / EVIDENCE_PATH)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S10/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and _evidence_index_is_bound(root, evidence_hash)
    )
    if not valid:
        raise RobustnessGateAcceptanceError("existing S10/P04 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED",
    }
