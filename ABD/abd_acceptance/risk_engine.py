"""Independent fail-closed acceptance oracle for ABD S11/P04.

The oracle replays only frozen synthetic constrained-Kelly vectors.  It binds
the S11/P03 signed route to risk controls and rejects any allocation that can
cross a single-ticket, event, correlation-cluster, or total-open cap.  It has
no provider, account, market, order, deployment, or real-time capability.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from platform_router import build_report as build_platform_report

from risk_engine import (
    CONTRACT_ID as RUNNER_CONTRACT_ID,
    EXTERNAL_EFFECT_BOUNDARY as RUNNER_EXTERNAL_EFFECT_BOUNDARY,
    RiskEngineError,
    artifact_sha256,
    build_report,
    validate_correlation_graph,
    validate_registry,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .platform_router import verify_existing_phase_evidence as verify_platform_router_phase_evidence


CONTRACT_ID = "AC-S11-P04"
REQUIREMENT_ID = "REQ-S11-P04"
STAGE_ID = "S11"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

ENGINE_PATH = Path("risk_engine.py")
GRAPH_PATH = Path("correlation_graph.json")
VECTORS_PATH = Path("risk_vectors.json")
ORACLE_PATH = Path("abd_acceptance/risk_engine.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
BUDGET_PATH = Path("abd_acceptance/budget.py")
TEST_PATH = Path("tests/S11/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S11_P04.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S11-P03.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S11-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S11-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S11/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S11/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "model:constrained_kelly_and_correlated_portfolio"
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, BUDGET_PATH)

_PREDECESSOR_SHA256 = "c3d0c61870a37e6c8ee3e71650008fdcf23d4bc2da4d1ec9e83e8e846a4b12d4"
_ROLLBACK_ARTIFACTS = (ENGINE_PATH, GRAPH_PATH, VECTORS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
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
_BASELINE_ACTIONS = [
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "NO_RECOMMENDATION",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
]
_FINAL_ACTIONS = [
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "NO_RECOMMENDATION",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE",
]
_FINAL_STAKES = [600, 450, 0, 100, 100, 100, 0, 0, 0, 0, 0, 600]
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


class RiskEngineAcceptanceError(ValueError):
    """Raised when S11/P04 evidence is incomplete, changed, or unreplayable."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RiskEngineAcceptanceError("%s has an unexpected shape" % label)
    return value


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise RiskEngineAcceptanceError("rows are not a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise RiskEngineAcceptanceError("expected exactly one %s=%s" % (key, identifier))
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
            raise RiskEngineAcceptanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise RiskEngineAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    return rows


def _check_taskpack_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _TASKPACK_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S11P04-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S11P04-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        requirements = strict_json_load(root / "machine/facts/requirements.json")
        contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
        graph = strict_json_load(root / "machine/facts/task_graph.json")
        traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [row for row in graph.get("tasks", []) if row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        expected_scope = ["risk_engine.py", "correlation_graph.json", "risk_vectors.json"]
        task_outputs = {output for task in tasks for output in task.get("outputs", [])}
        expected_oracle = {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S11-P04 --evidence machine/evidence",
            "rule": "任意属性测试不能越过风险上限。",
        }
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "任意属性测试不能越过风险上限。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == expected_oracle
            and contract.get("pass_gate") == requirement.get("target")
            and contract.get("environment") == [
                "Ubuntu Linux 持续集成环境",
                "固定时钟",
                "冻结测试夹具",
                "无外部网络的确定性测试模式",
                "生产等价配置Schema",
            ]
        )
        _add(checks, "S11P04-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == ["T-S11-P04-01", "T-S11-P04-02", "T-S11-P04-03"]
            and expected_scope == [item for item in expected_scope if item in task_outputs]
            and TEST_PATH.as_posix() in task_outputs
            and FIXTURE_PATH.as_posix() in task_outputs
            and EVIDENCE_PATH.as_posix() in task_outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in task_outputs
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == ["T-S11-P04-01", "T-S11-P04-02", "T-S11-P04-03"]
            and trace.get("test_ids") == ["TEST-S11-P04", "TEST-S11-P04-BOUNDARY", "TEST-S11-P04-REPLAY"]
            and trace.get("evidence_id") == "EVD-S11-P04"
            and trace.get("artifact_ids") == ["ART-S11-P04-01", "ART-S11-P04-02", "ART-S11-P04-03"]
        )
        _add(checks, "S11P04-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S11P04-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, PREDECESSOR_PATH, checks, "S11P04-PREDECESSOR-STRICT-JSON")
    try:
        result = verify_platform_router_phase_evidence(root)
        current_hash = sha256_file(root / PREDECESSOR_PATH)
        hashes[PREDECESSOR_PATH.as_posix()] = current_hash
        passed = (
            current_hash == _PREDECESSOR_SHA256
            and isinstance(evidence, Mapping)
            and evidence.get("contract_id") == "AC-S11-P03"
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S11/P04_READY_NOT_STARTED"
            and result.get("status") == "PASS"
        )
        _add(checks, "S11P04-PREDECESSOR-P03-SIGNED-AND-REPLAYABLE", passed, {"expected": _PREDECESSOR_SHA256, "actual": current_hash, "verifier": result})
    except Exception as exc:
        _add(checks, "S11P04-PREDECESSOR-P03-SIGNED-AND-REPLAYABLE", False, "%s: %s" % (type(exc).__name__, exc))


def _validate_fixture(value: Any) -> Mapping[str, Any]:
    fixture = _strict_object(
        value,
        {
            "schema_version",
            "fixture_id",
            "contract_id",
            "requirement_id",
            "stage_id",
            "phase_id",
            "product_version",
            "fixed_clock",
            "input_mode",
            "expected_correlation_graph_sha256",
            "expected_report_sha256",
            "expected_baseline_actions",
            "expected_final_actions",
            "expected_final_stakes_cents",
            "expected_candidate_vector_ids",
            "expected_unstable_vector_ids",
            "expected_hard_stop_reason_codes",
            "p03_route_binding",
            "claim_boundary",
        },
        label="S11/P04 fixture",
    )
    identity_ok = (
        fixture["schema_version"] == "1.0.0"
        and fixture["fixture_id"] == "FIX-S11-P04-CONSTRAINED-KELLY-CORRELATED-PORTFOLIO"
        and fixture["contract_id"] == CONTRACT_ID
        and fixture["requirement_id"] == REQUIREMENT_ID
        and fixture["stage_id"] == STAGE_ID
        and fixture["phase_id"] == PHASE_ID
        and fixture["product_version"] == VERSION
        and fixture["fixed_clock"] == FIXED_CLOCK
        and fixture["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    )
    if not identity_ok:
        raise RiskEngineAcceptanceError("fixture identity differs")
    for field in ("expected_correlation_graph_sha256", "expected_report_sha256"):
        value = fixture[field]
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise RiskEngineAcceptanceError("%s must be a lowercase SHA-256" % field)
    if fixture["expected_baseline_actions"] != _BASELINE_ACTIONS:
        raise RiskEngineAcceptanceError("expected baseline actions differ")
    if fixture["expected_final_actions"] != _FINAL_ACTIONS or fixture["expected_final_stakes_cents"] != _FINAL_STAKES:
        raise RiskEngineAcceptanceError("expected final risk results differ")
    if fixture["expected_candidate_vector_ids"] != [
        "K01-GA-P03-ROUTE-STABLE",
        "K02-BETA-SINGLE-TICKET-CAP",
        "K04-EVENT-CAP-REMAINING-CAPACITY",
        "K05-CLUSTER-CAP-REMAINING-CAPACITY",
        "K06-OPEN-CAP-REMAINING-CAPACITY",
        "K12-TARGET-SHORTFALL-DIAGNOSTIC-ONLY",
    ]:
        raise RiskEngineAcceptanceError("expected candidate vectors differ")
    if fixture["expected_unstable_vector_ids"] != ["K11-RISK-THRESHOLD-POINT-0001-FLIP"]:
        raise RiskEngineAcceptanceError("expected unstable vectors differ")
    if fixture["expected_hard_stop_reason_codes"] != [
        "STAGE_COEFFICIENT_ZERO",
        "STAKE_BELOW_PROVIDER_MINIMUM",
        "DAILY_LOSS_SOFT_STOP",
        "STRATEGY_SLICE_DRAWDOWN_KILL",
        "LEDGER_DIFFERENCE_HARD_STOP",
    ]:
        raise RiskEngineAcceptanceError("expected hard-stop reason codes differ")
    if fixture["p03_route_binding"] != {
        "route_vector_id": "R01-UNIQUE-STABLE-SYNTHETIC-PLATFORM",
        "provider_id": "SYNTHETIC_PROVIDER_ALPHA",
        "route_action": "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
        "conservative_probability": "0.6",
        "odds": "2.000000",
        "stake_increment_cents": 5,
        "minimum_stake_cents": 100,
    }:
        raise RiskEngineAcceptanceError("P03 route binding differs")
    if fixture["claim_boundary"] != {
        "network_accessed": False,
        "actual_market_or_odds_observed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise RiskEngineAcceptanceError("fixture external-effect boundary differs")
    return fixture


def _check_p03_route_binding(root: Path, registry: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        parameters = strict_json_load(root / "machine/facts/parameters.json")
        score = strict_json_load(root / "provider_score.json")
        routing = strict_json_load(root / "routing_fixtures.json")
        p03 = build_platform_report(score, routing, parameters)
        primary = registry["vectors"][0]
        routed = p03["results"][0]
        selected = routed["baseline"]
        expected = fixture["p03_route_binding"]
        passed = (
            p03["report_sha256"] == strict_json_load(root / "machine/tests/fixtures/S11_P03.json")["expected_report_sha256"]
            and routed["vector_id"] == expected["route_vector_id"]
            and routed["action"] == expected["route_action"]
            and selected["selected_provider_id"] == expected["provider_id"]
            and primary["upstream_route_vector_id"] == expected["route_vector_id"]
            and primary["upstream_route_action"] == expected["route_action"]
            and primary["upstream_provider_id"] == expected["provider_id"]
            and primary["conservative_probability"] == expected["conservative_probability"]
            and primary["odds"] == expected["odds"]
            and primary["stake_increment_cents"] == expected["stake_increment_cents"]
            and primary["minimum_stake_cents"] == expected["minimum_stake_cents"]
        )
        _add(checks, "S11P04-P03-UNIQUE-ROUTE-BINDING-EXACT", passed, {"route": routed.get("vector_id"), "provider": selected.get("selected_provider_id"), "p03_report": p03["report_sha256"]})
    except Exception as exc:
        _add(checks, "S11P04-P03-UNIQUE-ROUTE-BINDING-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S11P04-PARAMETERS-STRICT-JSON")
    graph = _safe_load(root, GRAPH_PATH, checks, "S11P04-CORRELATION-GRAPH-STRICT-JSON")
    registry = _safe_load(root, VECTORS_PATH, checks, "S11P04-RISK-VECTORS-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S11P04-FIXTURE-STRICT-JSON")
    if not all(isinstance(item, Mapping) for item in (parameters, graph, registry, fixture)):
        return
    try:
        frozen_fixture = _validate_fixture(fixture)
        rebuilt_graph = validate_correlation_graph(graph, parameters)
        validate_registry(registry, rebuilt_graph, parameters)
        report = build_report(rebuilt_graph, registry, parameters)
        graph_hash = artifact_sha256(rebuilt_graph)
        exact_replay = (
            graph == rebuilt_graph
            and frozen_fixture["expected_correlation_graph_sha256"] == graph_hash
            and registry.get("correlation_graph_sha256") == graph_hash
            and frozen_fixture["expected_report_sha256"] == report["report_sha256"]
            and registry.get("expected_report_sha256") == report["report_sha256"]
        )
        _add(checks, "S11P04-FROZEN-GRAPH-VECTORS-AND-REPORT-REPLAY-EXACT", exact_replay, {"graph": graph_hash, "report": report["report_sha256"]})
        results = report.get("results", [])
        baseline_actions = [item.get("baseline", {}).get("action") for item in results if isinstance(item, Mapping)]
        final_actions = [item.get("action") for item in results if isinstance(item, Mapping)]
        final_stakes = [item.get("stake_cents") for item in results if isinstance(item, Mapping)]
        expected_ok = len(results) == 12 and all(item.get("all_expected_matches") is True for item in results if isinstance(item, Mapping))
        _add(checks, "S11P04-CONSTRAINED-KELLY-EXPECTED-VECTORS-EXACT", expected_ok and baseline_actions == frozen_fixture["expected_baseline_actions"] and final_actions == frozen_fixture["expected_final_actions"] and final_stakes == frozen_fixture["expected_final_stakes_cents"], {"baseline": baseline_actions, "final": final_actions, "stakes": final_stakes})
        summary = report.get("summary", {})
        candidate_ids = [item.get("vector_id") for item in results if item.get("action") == "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE"]
        unstable_ids = [item.get("vector_id") for item in results if item.get("adverse_flip_dimensions")]
        caps_ok = bool(summary.get("all_risk_invariants_hold")) and candidate_ids == frozen_fixture["expected_candidate_vector_ids"] and unstable_ids == frozen_fixture["expected_unstable_vector_ids"]
        _add(checks, "S11P04-ALL-ALLOCATIONS-NEVER-CROSS-RISK-CAPS", caps_ok, {"candidates": candidate_ids, "unstable": unstable_ids, "summary": summary})
        hard_stop_reasons = [
            next(item for item in results if item.get("vector_id") == vector_id).get("reason_code")
            for vector_id in (
                "K03-ALPHA-COEFFICIENT-ZERO",
                "K07-BELOW-PROVIDER-MINIMUM-NO-UPROUND",
                "K08-DAILY-LOSS-SOFT-STOP",
                "K09-STRATEGY-SLICE-DRAWDOWN-KILL",
                "K10-LEDGER-DIFFERENCE-HARD-STOP",
            )
        ]
        _add(checks, "S11P04-LOSS-DRAWDOWN-LEDGER-AND-MINIMUM-STAKE-HARD-STOPS", hard_stop_reasons == frozen_fixture["expected_hard_stop_reason_codes"], hard_stop_reasons)
        target = next(item for item in results if item.get("vector_id") == "K12-TARGET-SHORTFALL-DIAGNOSTIC-ONLY")
        primary = next(item for item in results if item.get("vector_id") == "K01-GA-P03-ROUTE-STABLE")
        target_ok = (
            target["action"] == primary["action"]
            and target["stake_cents"] == primary["stake_cents"]
            and "TARGET_SHORTFALL_DIAGNOSTIC_ONLY_NO_GATE_RELAXATION" in target["baseline"]["diagnostics"]
        )
        _add(checks, "S11P04-TARGET-SHORTFALL-NEVER-RELAXES-RISK-GATES", target_ok, {"primary_stake": primary["stake_cents"], "target_stake": target["stake_cents"], "diagnostics": target["baseline"]["diagnostics"]})
        for relative in (ENGINE_PATH, GRAPH_PATH, VECTORS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
        _check_p03_route_binding(root, registry, frozen_fixture, checks)
    except Exception as exc:
        _add(checks, "S11P04-FROZEN-RISK-REPLAY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ENGINE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
        source_ok = (
            not imports.intersection(prohibited)
            and "sleep(" not in source
            and "submit_order" not in source
            and "confirm_order" not in source
            and "retry_order" not in source
            and "float(" not in source
        )
        _add(checks, "S11P04-NO-NETWORK-ACCOUNT-ORDER-SOAK-OR-FLOAT-CAPABILITY", source_ok, {"imports": sorted(imports)})
    except Exception as exc:
        _add(checks, "S11P04-NO-NETWORK-ACCOUNT-ORDER-SOAK-OR-FLOAT-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S11P04-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _junit_summary(path: Path) -> dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise RiskEngineAcceptanceError("JUnit contains no suites")
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
        passed = summary["tests"] >= 24 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and _junit_normalized(root / JUNIT_PATH)
        _add(checks, "S11P04-TARGETED-PYTEST-REPORT", passed, summary)
    except Exception as exc:
        _add(checks, "S11P04-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S11P04-SCAN-REPORT", "STATUS: PASS" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S11P04-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S11P04-PACK-REPORT-STRICT-JSON")
    _add(checks, "S11P04-PACK-REPORT-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("summary") if isinstance(report, Mapping) else "unavailable")


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
        "decision": "CONSTRAINED_KELLY_RISK_CAPS_REPLAYED_SYNTHETIC_ONLY_STAGE_REVIEW_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S11/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S11/P04_BLOCKED",
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
    _add(checks, "S11P04-CONTRACT-ID-BOUND", RUNNER_CONTRACT_ID == CONTRACT_ID, RUNNER_CONTRACT_ID)
    _add(checks, "S11P04-EXTERNAL-BOUNDARY-EXACT", RUNNER_EXTERNAL_EFFECT_BOUNDARY == EXTERNAL_EFFECT_BOUNDARY, RUNNER_EXTERNAL_EFFECT_BOUNDARY)
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
        "evidence_id": "EVD-S11-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_CONSTRAINED_KELLY_RESTORE_SIGNED_S11_P03_KEEP_ALL_EVIDENCE",
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
        ENGINE_PATH,
        GRAPH_PATH,
        VECTORS_PATH,
        ORACLE_PATH,
        TEST_PATH,
        FIXTURE_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        PREDECESSOR_PATH,
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "later dispatcher or dependency-scanner evolution must not invalidate phase-owned frozen evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S11-P04",
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
        "hashes": {"code": sha256_file(root / ORACLE_PATH), "inputs": _input_hashes(root, require_test_reports=require_test_reports), "rollback_evidence": _sha256_bytes(_json_bytes(rollback))},
        "shared_runtime_contract": _shared_runtime_contract(),
        "commands": [
            "uv run --frozen --python 3.12 python risk_engine.py --parameters machine/facts/parameters.json --correlation-graph correlation_graph.json --risk-vectors risk_vectors.json",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S11/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S11/P04_test.py --junitxml=machine/evidence/S11/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S11/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S11-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"risk_vectors": 12, "adverse_scenarios_per_candidate": 4, "real_time_wait_performed": False},
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S11_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S11-P04",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S11/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [replacement if row.get("id") == replacement["id"] else row for row in rows]
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise RiskEngineAcceptanceError("planned S11/P04 evidence-index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise RiskEngineAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise RiskEngineAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S11/STAGE_REVIEW_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise RiskEngineAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        indexed = _row(index, "INDEX-AC-S11-P04")
    except Exception as exc:
        raise RiskEngineAcceptanceError("evidence index is unavailable: %s" % exc) from exc
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "CONSTRAINED_KELLY_RISK_CAPS_REPLAYED_SYNTHETIC_ONLY_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S11/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and indexed.get("status") == "PASS"
        and indexed.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
    )
    if not valid:
        raise RiskEngineAcceptanceError("existing S11/P04 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S11/STAGE_REVIEW_READY_NOT_STARTED"}
