"""Fail-closed acceptance oracle for ABD S19/P01 walking skeleton and alpha."""

from __future__ import annotations

import ast
import hashlib
import json
import xml.etree.ElementTree as ElementTree
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .journey_paths import verify_existing_phase_evidence as verify_s13_p04
from .legacy_receipt_compatibility import approved_successor_sha256
from .operations_automation_acceptance import verify_existing_phase_evidence as verify_s18_p04
from .recovery import verify_existing_phase_evidence as verify_s17_p04
from .target_falsification_gate import verify_existing_phase_evidence as verify_s12_p04
from .walking_skeleton import (
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXED_CLOCK,
    LIFECYCLE_STEPS,
    SAFE_FUND_FACTS,
    SAFE_RISK_GATE,
    WalkingSkeletonInputError,
    build_software_alpha_artifact,
    build_walking_skeleton_artifact,
    canonical_json_bytes,
    evaluate_walking_skeleton,
)


CONTRACT_ID = "AC-S19-P01"
REQUIREMENT_ID = "REQ-S19-P01"
STAGE_ID = "S19"
PHASE_ID = "P01"
PRODUCT_VERSION = "0.0.0.1"

CORE_PATH = Path("abd_acceptance/walking_skeleton.py")
ORACLE_PATH = Path("abd_acceptance/walking_skeleton_acceptance.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S19_P01.json")
TEST_PATH = Path("tests/S19/P01_test.py")
WALKING_ARTIFACT_PATH = Path("walking_skeleton_evidence.json")
ALPHA_ARTIFACT_PATH = Path("software_alpha_gate.json")
JUNIT_PATH = Path("machine/evidence/S19/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S19/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")

EXPECTED_TASK_IDS = ("T-S19-P01-01", "T-S19-P01-02", "T-S19-P01-03")
EXPECTED_TEST_IDS = ("TEST-S19-P01", "TEST-S19-P01-BOUNDARY", "TEST-S19-P01-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S19-P01-01", "ART-S19-P01-02")
EXPECTED_SCENARIOS = (
    "GOLDEN_LOCAL_CLOSED_LOOP",
    "ADVERSE_ONE_IN_TEN_THOUSAND_PRESERVES_NO_ORDER",
    "EXTERNAL_EXECUTION_ATTEMPT_FAILS_CLOSED",
    "ACTUAL_ORDER_ATTEMPT_FAILS_CLOSED",
    "REAL_FUND_MUTATION_ATTEMPT_FAILS_CLOSED",
    "REAL_MAIL_SEND_ATTEMPT_FAILS_CLOSED",
    "PRODUCTION_DEPLOY_ATTEMPT_FAILS_CLOSED",
    "RISK_GATE_RELAXATION_ATTEMPT_FAILS_CLOSED",
)
EXPECTED_PREDECESSORS = {
    "AC-S12-P04": "73d7574576fbc86fae29e0de7f9e671204c934e078f847037115a50c9c50441b",
    "AC-S13-P04": "1c4d9febd44b30dddfa780daa0aad56a70ab8d477ab9cdafc905107760d7c81e",
    "AC-S17-P04": "08e1d389d3b0d80d6c729d9835dc27343018985cd8cc1796a9528b5ed7d6e708",
    "AC-S18-P04": "b196f207508350f8dbdb51efcd880f1fe616880e490af344bd3b2d238c142931",
}
PREDECESSOR_PATHS = {
    "AC-S12-P04": Path("machine/evidence/EVD-S12-P04.json"),
    "AC-S13-P04": Path("machine/evidence/EVD-S13-P04.json"),
    "AC-S17-P04": Path("machine/evidence/EVD-S17-P04.json"),
    "AC-S18-P04": Path("machine/evidence/EVD-S18-P04.json"),
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
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "production_equivalent_config_schema_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "incremental_cash_spent_aud": "0.00",
}


class WalkingSkeletonAcceptanceError(RuntimeError):
    """Raised if this phase cannot prove a local closed loop safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, path.as_posix())
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise WalkingSkeletonAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise WalkingSkeletonAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise WalkingSkeletonAcceptanceError("blank evidence index row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping) or _contains_float(value):
            raise WalkingSkeletonAcceptanceError("invalid evidence index row %d" % number)
        rows.append(value)
    return rows


def load_fixture(path: Path) -> Mapping[str, Any]:
    value = strict_json_load(path)
    if not isinstance(value, Mapping) or _contains_float(value):
        raise WalkingSkeletonAcceptanceError("fixture must be a non-float object")
    return value


def validate_fixture(value: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {
        "schema_version", "fixture_id", "contract_id", "requirement_id", "stage_id", "phase_id", "fixed_clock",
        "expected_next", "predecessors", "market", "lifecycle_steps", "fund_facts_snapshot", "risk_gate_snapshot",
        "scenarios", "malformed_inputs",
    }
    if set(value) != required:
        raise WalkingSkeletonAcceptanceError("fixture keys do not match the frozen schema")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("fixture_id") != "FIX-S19-P01-WALKING-SKELETON"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("expected_next") != "S19/P02_READY_NOT_STARTED"
        or value.get("predecessors") != EXPECTED_PREDECESSORS
        or value.get("fund_facts_snapshot") != SAFE_FUND_FACTS
        or value.get("risk_gate_snapshot") != SAFE_RISK_GATE
        or tuple(value.get("lifecycle_steps", [])) != LIFECYCLE_STEPS
    ):
        raise WalkingSkeletonAcceptanceError("fixture does not pin the S19/P01 contract")
    if not isinstance(value.get("market"), Mapping):
        raise WalkingSkeletonAcceptanceError("fixture market is unavailable")
    expected_market = {
        "market_id": "SYNTHETIC-MARKET-S19-P01",
        "source_kind": "FROZEN_LOCAL_FIXTURE",
        "evidence_tier": "E0_SYNTHETIC_TEST_ONLY",
        "implied_probability": "0.500000000",
    }
    if dict(value["market"]) != expected_market:
        raise WalkingSkeletonAcceptanceError("fixture market is not local synthetic evidence")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != EXPECTED_SCENARIOS:
        raise WalkingSkeletonAcceptanceError("fixture scenarios are incomplete or reordered")
    for item in scenarios:
        if not isinstance(item, Mapping) or set(item) != {"scenario_id", "cycle_input", "expected"}:
            raise WalkingSkeletonAcceptanceError("fixture scenario has an invalid shape")
        plan = evaluate_walking_skeleton(item["cycle_input"])
        expected = item["expected"]
        if not isinstance(expected, Mapping) or {key: plan.get(key) for key in expected} != dict(expected):
            raise WalkingSkeletonAcceptanceError("fixture scenario does not match the core result")
    malformed = value.get("malformed_inputs")
    if not isinstance(malformed, list) or [item.get("case_id") for item in malformed if isinstance(item, Mapping)] != [
        "DUPLICATED_LIFECYCLE_STEP", "FLOAT_PROBABILITY_DELTA", "UNFROZEN_MARKET"
    ]:
        raise WalkingSkeletonAcceptanceError("fixture malformed-input coverage changed")
    return value


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P01-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S19P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S19P01-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S19P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S19P01-TRACEABILITY-STRICT-JSON")
    roadmap = _safe_load(root, Path("machine/facts/roadmap.json"), checks, "S19P01-ROADMAP-STRICT-JSON")
    if not all(value is not None for value in (requirements, contracts, graph, traceability, roadmap)):
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [item for item in graph.get("tasks", []) if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        stages = [item for item in roadmap.get("stages", []) if isinstance(item, Mapping) and item.get("id") == STAGE_ID]
        phase = next((item for item in stages[0].get("phases", []) if item.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
        expected_scope = [WALKING_ARTIFACT_PATH.as_posix(), ALPHA_ARTIFACT_PATH.as_posix()]
        expected_oracle = {"type": "EXECUTABLE", "command": "python -m abd_acceptance --contract AC-S19-P01 --evidence machine/evidence", "rule": "不使用真实资金即可确定性闭环。"}
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "不使用真实资金即可确定性闭环。"
            and requirement.get("value") == "用一个市场完成发现、建议、失效、结果、重放、邮件和恢复闭环。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == expected_oracle
            and contract.get("pass_gate") == requirement.get("target")
            and phase.get("outputs") == expected_scope
            and phase.get("pass_gate") == requirement.get("target")
        )
        _add(checks, "S19P01-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        task_outputs = {output for task in tasks for output in task.get("outputs", [])}
        trace_ok = (
            tuple(task.get("id") for task in tasks) == EXPECTED_TASK_IDS
            and tasks[0].get("depends_on") == ["T-S12-P04-03", "T-S13-P04-03", "T-S17-P04-03", "T-S18-P04-03"]
            and tasks[1].get("depends_on") == ["T-S19-P01-01"]
            and tasks[2].get("depends_on") == ["T-S19-P01-02"]
            and all(output in task_outputs for output in [WALKING_ARTIFACT_PATH.as_posix(), ALPHA_ARTIFACT_PATH.as_posix(), TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(), EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()])
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
            and trace.get("evidence_id") == "EVD-S19-P01"
        )
        _add(checks, "S19P01-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S19P01-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    verifiers = {
        "AC-S12-P04": verify_s12_p04,
        "AC-S13-P04": verify_s13_p04,
        "AC-S17-P04": verify_s17_p04,
        "AC-S18-P04": verify_s18_p04,
    }
    for contract_id, expected_hash in EXPECTED_PREDECESSORS.items():
        path = PREDECESSOR_PATHS[contract_id]
        try:
            result = verifiers[contract_id](root)
            actual_hash = sha256_file(root / path)
            hashes[path.as_posix()] = actual_hash
            passed = (
                result.get("contract_id") == contract_id
                and result.get("status") == "PASS"
                and result.get("evidence_sha256") == expected_hash
                and actual_hash == expected_hash
            )
            detail: Any = {"expected": expected_hash, "actual": actual_hash, "next": result.get("next")}
        except Exception as exc:
            passed = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S19P01-PREDECESSOR-%s-CURRENT" % contract_id.replace("-", ""), passed, detail)


def _fixture_and_expected_artifacts(root: Path) -> Tuple[Mapping[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    fixture = validate_fixture(load_fixture(root / FIXTURE_PATH))
    golden = next(item for item in fixture["scenarios"] if item["scenario_id"] == "GOLDEN_LOCAL_CLOSED_LOOP")
    plan = evaluate_walking_skeleton(golden["cycle_input"])
    walking = build_walking_skeleton_artifact(
        plan,
        fixture_sha256=sha256_file(root / FIXTURE_PATH),
        predecessor_evidence_sha256=EXPECTED_PREDECESSORS,
    )
    alpha = build_software_alpha_artifact(walking)
    return fixture, plan, walking, alpha


def _check_core_and_fixture(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        fixture, plan, walking, alpha = _fixture_and_expected_artifacts(root)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        hashes[CORE_PATH.as_posix()] = sha256_file(root / CORE_PATH)
        fixture_ok = tuple(item["scenario_id"] for item in fixture["scenarios"]) == EXPECTED_SCENARIOS
        _add(checks, "S19P01-FIXTURE-EXACT", fixture_ok, {"scenarios": [item["scenario_id"] for item in fixture["scenarios"]]})
        scenario_results = []
        replay_ok = True
        for scenario in fixture["scenarios"]:
            first = evaluate_walking_skeleton(scenario["cycle_input"])
            second = evaluate_walking_skeleton(scenario["cycle_input"])
            expected = scenario["expected"]
            matched = {key: first.get(key) for key in expected} == dict(expected)
            replay_ok = replay_ok and first == second and first["walking_skeleton_plan_sha256"] == second["walking_skeleton_plan_sha256"]
            scenario_results.append({"scenario_id": scenario["scenario_id"], "matched": matched, "status": first["status"], "failure_codes": first["failure_codes"]})
        _add(checks, "S19P01-FROZEN-SCENARIOS-EXACT", all(item["matched"] for item in scenario_results), scenario_results)
        _add(checks, "S19P01-DETERMINISTIC-REPLAY-HASH-EXACT", replay_ok, {"scenario_count": len(scenario_results)})
        _add(checks, "S19P01-GOLDEN-CLOSED-LOOP-NO-FUNDS", plan["status"] == "PASS" and plan["action"] == "NO_RECOMMENDATION" and [item["step"] for item in plan["lifecycle"]] == list(LIFECYCLE_STEPS), plan["decision"])
        _add(checks, "S19P01-ARTIFACT-BUILD-EXACT", walking.get("artifact_id") == EXPECTED_ARTIFACT_IDS[0] and alpha.get("artifact_id") == EXPECTED_ARTIFACT_IDS[1] and alpha.get("alpha_status") == "SOFTWARE_ALPHA_LOCAL_ONLY_NOT_DEPLOYED", {"walking": walking.get("walking_skeleton_evidence_sha256"), "alpha": alpha.get("software_alpha_gate_sha256")})
        source = (root / CORE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "time", "asyncio", "os", "random"}
        source_ok = not imports.intersection(forbidden) and all(token not in source for token in ("sleep(", "submit_order", "retry_order", "http://", "https://", "smtplib"))
        _add(checks, "S19P01-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY", source_ok, sorted(imports.intersection(forbidden)))
    except Exception as exc:
        _add(checks, "S19P01-CORE-OR-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_generated_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str], required: bool) -> None:
    if not required:
        _add(checks, "S19P01-GENERATED-ARTIFACTS-DEFERRED-PREFLIGHT", True, "pre-signing source and fixture preflight")
        return
    try:
        _, _, walking, alpha = _fixture_and_expected_artifacts(root)
        actual_walking = strict_json_load(root / WALKING_ARTIFACT_PATH)
        actual_alpha = strict_json_load(root / ALPHA_ARTIFACT_PATH)
        hashes[WALKING_ARTIFACT_PATH.as_posix()] = sha256_file(root / WALKING_ARTIFACT_PATH)
        hashes[ALPHA_ARTIFACT_PATH.as_posix()] = sha256_file(root / ALPHA_ARTIFACT_PATH)
        exact = actual_walking == walking and actual_alpha == alpha
        _add(checks, "S19P01-GENERATED-ARTIFACTS-REPLAY-EXACT", exact, {"walking": hashes[WALKING_ARTIFACT_PATH.as_posix()], "alpha": hashes[ALPHA_ARTIFACT_PATH.as_posix()]})
        alpha_gate_ok = (
            actual_alpha.get("status") == "PASS"
            and actual_alpha.get("walking_skeleton_evidence_sha256") == actual_walking.get("walking_skeleton_evidence_sha256")
            and actual_alpha.get("next_required_gate") == "S19/P02_READY_NOT_STARTED"
            and actual_alpha.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and actual_alpha.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        )
        _add(checks, "S19P01-SOFTWARE-ALPHA-LOCAL-ONLY", alpha_gate_ok, actual_alpha.get("alpha_status"))
    except Exception as exc:
        _add(checks, "S19P01-GENERATED-ARTIFACTS-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S19P01-SOFTWARE-ALPHA-LOCAL-ONLY", False, "generated artifacts unavailable")


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .walking_skeleton_acceptance import verify_existing_phase_evidence as verify_walking_skeleton_phase_evidence" in source
            and "from .walking_skeleton_acceptance import write_phase_evidence as write_walking_skeleton_phase_evidence" in source
            and '"AC-S19-P01": verify_walking_skeleton_phase_evidence,' in source
            and '"AC-S19-P01": write_walking_skeleton_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P01-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(checks, "S19P01-S08-LEGACY-SUCCESSOR-PIN-EXACT", successor == sha256_file(root / CLI_PATH), {"approved": successor, "current": sha256_file(root / CLI_PATH)})


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    try:
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
        summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for suite in suites:
            for key in summary:
                summary[key] += int(suite.attrib.get(key, "0"))
        normalized = bool(suites) and all(
            suite.attrib.get("timestamp") == "2026-07-19T00:00:00+10:00"
            and suite.attrib.get("time") == "0.000"
            and "hostname" not in suite.attrib
            and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
            for suite in suites
        )
        return summary, normalized
    except Exception:
        return {"tests": 0, "failures": 1, "errors": 1, "skipped": 0}, False


def _check_reports(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str], required: bool) -> None:
    if not required:
        _add(checks, "S19P01-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    if (root / JUNIT_PATH).is_file():
        hashes[JUNIT_PATH.as_posix()] = sha256_file(root / JUNIT_PATH)
    report_ok = summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
    _add(checks, "S19P01-TARGETED-PYTEST-REPORT", report_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        scan_ok = "STATUS: PASS" in scan and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in scan and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S19P01-TASKPACK-REPORT-STRICT-JSON")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    _add(checks, "S19P01-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S19_P01_WALKING_SKELETON_AND_SOFTWARE_ALPHA_PASS_P02_REQUIRED" if passed else "S19/P01_BLOCKED",
        "next": "S19/P02_READY_NOT_STARTED" if passed else "S19/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": EXECUTION_POLICY,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, *, require_test_reports: bool = False, require_generated_artifacts: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessors(root, checks, hashes)
    _check_core_and_fixture(root, checks, hashes)
    _check_generated_artifacts(root, checks, hashes, require_generated_artifacts)
    _check_cli_wiring(root, checks)
    _check_reports(root, checks, hashes, require_test_reports)
    boundary_ok = (
        all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key not in {"incremental_cash_spent_aud", "owner_final_order_only"})
        and EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
        and EXTERNAL_EFFECT_BOUNDARY["owner_final_order_only"] is True
    )
    _add(checks, "S19P01-EXTERNAL-EFFECT-BOUNDARY-EXACT", boundary_ok, EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False, require_generated_artifacts=False)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_core_artifacts(root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    _, _, walking, alpha = _fixture_and_expected_artifacts(root)
    _atomic_write(root / WALKING_ARTIFACT_PATH, _json_bytes(walking))
    _atomic_write(root / ALPHA_ARTIFACT_PATH, _json_bytes(alpha))
    return walking, alpha


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (CORE_PATH, ORACLE_PATH, FIXTURE_PATH, TEST_PATH, WALKING_ARTIFACT_PATH, ALPHA_ARTIFACT_PATH, *PREDECESSOR_PATHS.values())
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING", "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S19_P01_LOCAL_FEATURE_RESTORE_SIGNED_S18_P04_EVIDENCE",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "previous_signed_artifact": PREDECESSOR_PATHS["AC-S18-P04"].as_posix(),
        "immutable_evidence_and_replay_preserved": True,
        "external_state_changed": False,
        "production_state_changed": False,
        "order_submission_enabled": False,
        "mail_sent": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool, require_generated_artifacts: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, CORE_PATH, FIXTURE_PATH, TEST_PATH, *PREDECESSOR_PATHS.values(), *[Path(path) for path in BASELINE_HASHES]]
    if require_generated_artifacts:
        paths.extend([WALKING_ARTIFACT_PATH, ALPHA_ARTIFACT_PATH])
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, *, require_test_reports: bool = False, require_generated_artifacts: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports, require_generated_artifacts=require_generated_artifacts)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "execution_policy": EXECUTION_POLICY,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S19_P01_LOCAL_SOFTWARE_ALPHA_ONLY_P02_REQUIRED" if validation["status"] == "PASS" else "S19_P01_REMEDIATION_REQUIRED",
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports, require_generated_artifacts=require_generated_artifacts),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "lifecycle_step_count": len(LIFECYCLE_STEPS),
            "adverse_one_in_ten_thousand_vector_count": 1,
            "unsafe_request_vector_count": 6,
            "external_runtime_accessed": False,
            "real_time_wait_performed": False,
        },
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "ACCEPTANCE_EVIDENCE",
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "acceptance_contract_id": CONTRACT_ID,
        "status": "PASS",
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S19/P02_READY_NOT_STARTED",
        "pass_gate": "不使用真实资金即可确定性闭环。",
        "verified_at": FIXED_CLOCK,
    }
    matches = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matches) != 1 or len(raw_lines) != len(rows):
        raise WalkingSkeletonAcceptanceError("S19/P01 evidence-index row must exist exactly once")
    raw_lines[matches[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise WalkingSkeletonAcceptanceError("evidence directory must be canonical machine/evidence")
    preflight = validate_candidate_preflight(root)
    if preflight["status"] != "PASS":
        raise WalkingSkeletonAcceptanceError("cannot sign a failed S19/P01 preflight")
    write_core_artifacts(root)
    evidence, rollback = build_evidence(root, require_test_reports=True, require_generated_artifacts=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise WalkingSkeletonAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/P02_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    validation = evaluate_contract(root, require_test_reports=True, require_generated_artifacts=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S19_P01_WALKING_SKELETON_AND_SOFTWARE_ALPHA_PASS_P02_REQUIRED"
        and evidence.get("next") == "S19/P02_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True, require_generated_artifacts=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("previous_signed_artifact") == PREDECESSOR_PATHS["AC-S18-P04"].as_posix()
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("mail_sent") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S19/P02_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise WalkingSkeletonAcceptanceError("existing S19/P01 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/P02_READY_NOT_STARTED"}


__all__ = [
    "ALPHA_ARTIFACT_PATH", "CONTRACT_ID", "CORE_PATH", "EVIDENCE_PATH", "FIXTURE_PATH", "ORACLE_PATH", "TEST_PATH",
    "WALKING_ARTIFACT_PATH", "WalkingSkeletonAcceptanceError", "build_evidence", "evaluate_contract", "load_fixture",
    "perform_rollback_drill", "validate_candidate_preflight", "validate_fixture", "verify_existing_phase_evidence", "write_core_artifacts", "write_phase_evidence",
]
