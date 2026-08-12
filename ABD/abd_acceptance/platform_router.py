"""Independent, fail-closed acceptance oracle for ABD S11/P03.

The oracle replays frozen synthetic platform-routing vectors only.  It binds
each routed candidate to the signed P02 decision gate, rejects ambiguous or
unstable provider selection, and never touches a platform, account, order
path, wall clock, or real-time soak.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from decision_gate import build_report as build_p02_report
from platform_router import (
    CONTRACT_ID as RUNNER_CONTRACT_ID,
    _ADVERSE_SCENARIOS,
    _P02_CANDIDATE_ACTION,
    artifact_sha256,
    build_provider_score,
    build_report,
    validate_provider_score,
    validate_registry,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .decision_gate import verify_existing_phase_evidence as verify_decision_gate_phase_evidence


CONTRACT_ID = "AC-S11-P03"
REQUIREMENT_ID = "REQ-S11-P03"
STAGE_ID = "S11"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

ROUTER_PATH = Path("platform_router.py")
SCORE_PATH = Path("provider_score.json")
FIXTURES_PATH = Path("routing_fixtures.json")
ORACLE_PATH = Path("abd_acceptance/platform_router.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
BUDGET_PATH = Path("abd_acceptance/budget.py")
TEST_PATH = Path("tests/S11/P03_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S11_P03.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S11-P02.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S11-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S11-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S11/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S11/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "model:dynamic_platform_routing"
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, BUDGET_PATH)

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
_PREDECESSOR_SHA256 = "59e814b20d237eff982ff763bb3573ba8c129e6817c4c1cf61e273c366bab065"
_ROLLBACK_ARTIFACTS = (ROUTER_PATH, SCORE_PATH, FIXTURES_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
_BASELINE_ACTIONS = [
    "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
    "NO_RECOMMENDATION",
    "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
    "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "NO_RECOMMENDATION",
    "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
    "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES",
]
_FINAL_ACTIONS = ["ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES"] + ["NO_RECOMMENDATION"] * 11
_SELECTED_PROVIDER_IDS = [
    "SYNTHETIC_PROVIDER_ALPHA",
    None,
    "SYNTHETIC_PROVIDER_ALPHA",
    "SYNTHETIC_PROVIDER_ALPHA",
    None,
    None,
    None,
    None,
    None,
    None,
    "SYNTHETIC_PROVIDER_ALPHA",
    "SYNTHETIC_PROVIDER_ALPHA",
]
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


class PlatformRouterAcceptanceError(ValueError):
    """Raised when S11/P03 evidence cannot be replayed or trusted."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise PlatformRouterAcceptanceError("%s has an unexpected shape" % label)
    return value


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise PlatformRouterAcceptanceError("rows are not a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise PlatformRouterAcceptanceError("expected exactly one %s=%s" % (key, identifier))
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
            raise PlatformRouterAcceptanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise PlatformRouterAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    return rows


def _check_taskpack_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _TASKPACK_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S11P03-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S11P03-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


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
        expected_scope = ["platform_router.py", "provider_score.json", "routing_fixtures.json"]
        task_outputs = {output for task in tasks for output in task.get("outputs", [])}
        expected_oracle = {
            "type": "EXECUTABLE",
            "command": "python -m abd_acceptance --contract AC-S11-P03 --evidence machine/evidence",
            "rule": "只显示一个最高分且全部门通过的平台。",
        }
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "只显示一个最高分且全部门通过的平台。"
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
        _add(checks, "S11P03-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == ["T-S11-P03-01", "T-S11-P03-02", "T-S11-P03-03"]
            and expected_scope == [item for item in expected_scope if item in task_outputs]
            and TEST_PATH.as_posix() in task_outputs
            and FIXTURE_PATH.as_posix() in task_outputs
            and EVIDENCE_PATH.as_posix() in task_outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in task_outputs
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == ["T-S11-P03-01", "T-S11-P03-02", "T-S11-P03-03"]
            and trace.get("test_ids") == ["TEST-S11-P03", "TEST-S11-P03-BOUNDARY", "TEST-S11-P03-REPLAY"]
            and trace.get("evidence_id") == "EVD-S11-P03"
            and trace.get("artifact_ids") == ["ART-S11-P03-01", "ART-S11-P03-02", "ART-S11-P03-03"]
        )
        _add(checks, "S11P03-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S11P03-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, PREDECESSOR_PATH, checks, "S11P03-PREDECESSOR-STRICT-JSON")
    try:
        result = verify_decision_gate_phase_evidence(root)
        current_hash = sha256_file(root / PREDECESSOR_PATH)
        hashes[PREDECESSOR_PATH.as_posix()] = current_hash
        passed = (
            current_hash == _PREDECESSOR_SHA256
            and isinstance(evidence, Mapping)
            and evidence.get("contract_id") == "AC-S11-P02"
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S11/P03_READY_NOT_STARTED"
            and result.get("status") == "PASS"
        )
        _add(checks, "S11P03-PREDECESSOR-P02-SIGNED-AND-REPLAYABLE", passed, {"expected": _PREDECESSOR_SHA256, "actual": current_hash, "verifier": result})
    except Exception as exc:
        _add(checks, "S11P03-PREDECESSOR-P02-SIGNED-AND-REPLAYABLE", False, "%s: %s" % (type(exc).__name__, exc))


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
            "expected_provider_score_sha256",
            "expected_routing_fixtures_sha256",
            "expected_report_sha256",
            "expected_baseline_actions",
            "expected_final_actions",
            "expected_selected_provider_ids",
            "expected_unstable_vector_ids",
            "expected_time_bands",
            "required_provider_reason_codes",
            "claim_boundary",
        },
        label="S11/P03 fixture",
    )
    identity_ok = (
        fixture["schema_version"] == "1.0.0"
        and fixture["fixture_id"] == "FIX-S11-P03-UNIQUE-SYNTHETIC-PLATFORM-ROUTING"
        and fixture["contract_id"] == CONTRACT_ID
        and fixture["requirement_id"] == REQUIREMENT_ID
        and fixture["stage_id"] == STAGE_ID
        and fixture["phase_id"] == PHASE_ID
        and fixture["product_version"] == VERSION
        and fixture["fixed_clock"] == FIXED_CLOCK
        and fixture["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    )
    if not identity_ok:
        raise PlatformRouterAcceptanceError("fixture identity differs")
    for field in ("expected_provider_score_sha256", "expected_routing_fixtures_sha256", "expected_report_sha256"):
        value = fixture[field]
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise PlatformRouterAcceptanceError("%s must be a lowercase SHA-256" % field)
    if fixture["expected_baseline_actions"] != _BASELINE_ACTIONS:
        raise PlatformRouterAcceptanceError("expected baseline actions differ")
    if fixture["expected_final_actions"] != _FINAL_ACTIONS:
        raise PlatformRouterAcceptanceError("expected final actions differ")
    if fixture["expected_selected_provider_ids"] != _SELECTED_PROVIDER_IDS:
        raise PlatformRouterAcceptanceError("expected selected provider ids differ")
    if fixture["expected_unstable_vector_ids"] != [
        "R03-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP",
        "R04-MINIMUM-ODDS-BOUNDARY-ADVERSE-FLIP",
        "R11-RETURN-POINT-0001-ADVERSE-FLIP",
        "R12-LIVE-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP",
    ]:
        raise PlatformRouterAcceptanceError("expected unstable vector ids differ")
    if fixture["expected_time_bands"] != ["more_than_24h", "2h_to_24h", "15m_to_2h", "0_to_15m", "live"]:
        raise PlatformRouterAcceptanceError("expected time bands differ")
    reasons = fixture["required_provider_reason_codes"]
    if not isinstance(reasons, list) or len(reasons) != len(set(reasons)) or any(not isinstance(item, str) or not item for item in reasons):
        raise PlatformRouterAcceptanceError("required provider reason codes are invalid")
    if fixture["claim_boundary"] != {
        "network_accessed": False,
        "actual_market_or_odds_observed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise PlatformRouterAcceptanceError("fixture external-effect boundary differs")
    return fixture


def _check_p02_candidate_bindings(root: Path, registry: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        parameters = strict_json_load(root / "machine/facts/parameters.json")
        tiers = strict_json_load(root / "evidence_tiers.json")
        vectors = strict_json_load(root / "threshold_vectors.json")
        p02 = build_p02_report(tiers, vectors, parameters)
        p02_results = {item["vector_id"]: item for item in p02["results"]}
        errors = []
        for routing_vector in registry["vectors"]:
            for provider in routing_vector["providers"]:
                upstream = p02_results.get(provider["p02_vector_id"])
                if not isinstance(upstream, Mapping):
                    errors.append({"provider": provider["provider_id"], "reason": "missing_p02_vector"})
                    continue
                if provider["p02_candidate_action"] != upstream.get("action"):
                    errors.append({"provider": provider["provider_id"], "reason": "p02_action_mismatch"})
                    continue
                if upstream.get("action") == _P02_CANDIDATE_ACTION:
                    baseline = upstream.get("baseline", {})
                    if (
                        provider["robust_net_expected_return"] != baseline.get("robust_net_expected_return")
                        or provider["minimum_acceptable_odds"] != baseline.get("minimum_acceptable_odds")
                    ):
                        errors.append({"provider": provider["provider_id"], "reason": "p02_numeric_binding_mismatch"})
        _add(checks, "S11P03-P02-CANDIDATE-AND-NUMERIC-BINDINGS-EXACT", not errors, errors or "all providers bind to frozen P02 results")
    except Exception as exc:
        _add(checks, "S11P03-P02-CANDIDATE-AND-NUMERIC-BINDINGS-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S11P03-PARAMETERS-STRICT-JSON")
    score = _safe_load(root, SCORE_PATH, checks, "S11P03-PROVIDER-SCORE-STRICT-JSON")
    registry = _safe_load(root, FIXTURES_PATH, checks, "S11P03-ROUTING-FIXTURES-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S11P03-FIXTURE-STRICT-JSON")
    if not all(isinstance(item, Mapping) for item in (parameters, score, registry, fixture)):
        return
    try:
        frozen_fixture = _validate_fixture(fixture)
        rebuilt_score = build_provider_score(parameters)
        validate_provider_score(score, parameters)
        validate_registry(registry, score, parameters)
        report = build_report(score, registry, parameters)
        exact_replay = (
            score == rebuilt_score
            and frozen_fixture["expected_provider_score_sha256"] == artifact_sha256(rebuilt_score)
            and frozen_fixture["expected_routing_fixtures_sha256"] == artifact_sha256(registry)
            and frozen_fixture["expected_report_sha256"] == report["report_sha256"]
            and registry.get("expected_report_sha256") == report["report_sha256"]
        )
        _add(checks, "S11P03-FROZEN-SCORE-FIXTURES-AND-REPORT-REPLAY-EXACT", exact_replay, {"score": artifact_sha256(rebuilt_score), "fixtures": artifact_sha256(registry), "report": report["report_sha256"]})
        results = report.get("results", [])
        baseline_actions = [item.get("baseline", {}).get("action") for item in results if isinstance(item, Mapping)]
        final_actions = [item.get("action") for item in results if isinstance(item, Mapping)]
        selected = [item.get("baseline", {}).get("selected_provider_id") for item in results if isinstance(item, Mapping)]
        expected_ok = len(results) == 12 and all(item.get("all_expected_matches") is True for item in results if isinstance(item, Mapping))
        _add(checks, "S11P03-UNIQUE-ROUTE-AND-FAIL-CLOSED-VECTORS-EXACT", expected_ok and baseline_actions == frozen_fixture["expected_baseline_actions"] and final_actions == frozen_fixture["expected_final_actions"] and selected == frozen_fixture["expected_selected_provider_ids"], {"baseline": baseline_actions, "final": final_actions, "selected": selected})
        unstable = [item.get("vector_id") for item in results if isinstance(item, Mapping) and item.get("adverse_flip_dimensions")]
        _add(checks, "S11P03-ONE-IN-TEN-THOUSAND-TIME-AND-ODDS-STABILITY-GATE", unstable == frozen_fixture["expected_unstable_vector_ids"], {"unstable": unstable})
        bands = []
        provider_reasons = set()
        for item in results:
            if not isinstance(item, Mapping):
                continue
            for provider in item.get("baseline", {}).get("providers", []):
                if isinstance(provider, Mapping):
                    provider_reasons.add(provider.get("reason_code"))
            source_vector = next((row for row in registry["vectors"] if row["vector_id"] == item.get("vector_id")), None)
            if isinstance(source_vector, Mapping):
                bands.extend(provider["time_band"] for provider in source_vector["providers"])
        hard_gate_ok = set(frozen_fixture["required_provider_reason_codes"]) <= provider_reasons and set(frozen_fixture["expected_time_bands"]) <= set(bands)
        _add(checks, "S11P03-SOURCE-SETTLEMENT-MINIMUM-STAKE-ACTION-AND-TIME-GATES", hard_gate_ok, {"reasons": sorted(str(reason) for reason in provider_reasons), "bands": sorted(set(bands))})
        summary = report.get("summary", {})
        candidate_boundary_ok = (
            isinstance(summary, Mapping)
            and summary.get("routed_candidate_pending_constrained_kelly_and_risk_count") == 1
            and summary.get("no_recommendation_count") == 11
            and report.get("decision") == "UNIQUE_SYNTHETIC_PLATFORM_CANDIDATE_READY_DOWNSTREAM_CONSTRAINED_KELLY_AND_RISK_REQUIRED"
            and report.get("next") == "S11/P04_READY_NOT_STARTED"
        )
        _add(checks, "S11P03-ROUTED-CANDIDATE-IS-NOT-FINAL-RECOMMENDATION-OR-ORDER", candidate_boundary_ok, summary)
        _add(checks, "S11P03-NO-EXTERNAL-RUNTIME-OR-ORDER-CLAIM", report.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY, report.get("external_effect_boundary"))
        _check_p02_candidate_bindings(root, registry, checks)
        for relative in (ROUTER_PATH, SCORE_PATH, FIXTURES_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except Exception as exc:
        _add(checks, "S11P03-SCORE-FIXTURES-AND-REPORT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    try:
        source = (root / ROUTER_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        _add(checks, "S11P03-STATIC-PARSE-ROUTER", False, "%s: %s" % (type(exc).__name__, exc))
        return
    imports = set()
    forbidden_calls = []
    float_literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen", "urlopen"}:
            forbidden_calls.append(node.func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            float_literals.append(node.value)
    passed = not (imports & prohibited_imports) and not forbidden_calls and not float_literals and "float(" not in source and "submit_order" not in source and "retry_order" not in source
    _add(checks, "S11P03-STATIC-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER", passed, {"imports": sorted(imports), "calls": sorted(forbidden_calls), "float_literals": float_literals})


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S11P03-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _junit_summary(path: Path) -> dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise PlatformRouterAcceptanceError("JUnit contains no suites")
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
        passed = summary["tests"] >= 20 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and _junit_normalized(root / JUNIT_PATH)
        _add(checks, "S11P03-TARGETED-PYTEST-REPORT", passed, summary)
    except Exception as exc:
        _add(checks, "S11P03-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S11P03-SCAN-REPORT", "STATUS: PASS" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S11P03-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S11P03-PACK-REPORT-STRICT-JSON")
    _add(checks, "S11P03-PACK-REPORT-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("summary") if isinstance(report, Mapping) else "unavailable")


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
        "decision": "UNIQUE_SYNTHETIC_PLATFORM_ROUTE_READY_DOWNSTREAM_CONSTRAINED_KELLY_AND_RISK_GATES_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S11/P04_READY_NOT_STARTED" if status == "PASS" else "S11/P03_BLOCKED",
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
    _add(checks, "S11P03-CONTRACT-ID-BOUND", RUNNER_CONTRACT_ID == CONTRACT_ID, RUNNER_CONTRACT_ID)
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
        "evidence_id": "EVD-S11-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_DYNAMIC_PLATFORM_ROUTING_RESTORE_SIGNED_S11_P02_KEEP_ALL_EVIDENCE",
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
        ROUTER_PATH,
        SCORE_PATH,
        FIXTURES_PATH,
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
        "evidence_id": "EVD-S11-P03",
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
            "uv run --frozen --python 3.12 python platform_router.py --parameters machine/facts/parameters.json --provider-score provider_score.json --routing-fixtures routing_fixtures.json",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S11/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S11/P03_test.py --junitxml=machine/evidence/S11/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S11/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S11-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"routing_vectors": 12, "adverse_scenarios_per_routed_candidate": len(_ADVERSE_SCENARIOS), "real_time_wait_performed": False},
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S11_P03_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S11-P03",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S11/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [replacement if row.get("id") == replacement["id"] else row for row in rows]
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise PlatformRouterAcceptanceError("planned S11/P03 evidence-index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise PlatformRouterAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise PlatformRouterAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S11/P04_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise PlatformRouterAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "UNIQUE_SYNTHETIC_PLATFORM_ROUTE_READY_DOWNSTREAM_CONSTRAINED_KELLY_AND_RISK_GATES_REQUIRED"
        and evidence.get("next") == "S11/P04_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
    )
    if not valid:
        raise PlatformRouterAcceptanceError("existing S11/P03 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S11/P04_READY_NOT_STARTED"}
