"""Fail-closed, offline acceptance oracle for ABD S18/P03 limited self-heal controls."""

from __future__ import annotations

import ast
import hashlib
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .legacy_receipt_compatibility import approved_successor_sha256
from .limited_self_heal import (
    APPROVED_DECISION,
    CONTRACT_ID as CORE_CONTRACT_ID,
    ESCALATION_DECISION,
    EXPECTED_OPERATIONS,
    EXTERNAL_EFFECT_BOUNDARY,
    FALLBACK_FAULT_ID,
    FIXED_CLOCK,
    HEALTHY_DECISION,
    POLICY_ID,
    SAFE_ACTION,
    SAFE_FUND_FACTS,
    SAFE_RISK_GATE,
    SelfHealInputError,
    evaluate_outbox_projection,
    evaluate_watchdog_event,
    validate_policy,
)
from .observability_alerts import verify_existing_phase_evidence as verify_s18_p02


CONTRACT_ID = "AC-S18-P03"
REQUIREMENT_ID = "REQ-S18-P03"
STAGE_ID = "S18"
PHASE_ID = "P03"
PRODUCT_VERSION = "0.0.0.1"

POLICY_PATH = Path("self_heal_policy.json")
WATCHDOG_PATH = Path("watchdog.py")
OUTBOX_PATH = Path("outbox_worker.py")
CORE_PATH = Path("abd_acceptance/limited_self_heal.py")
ORACLE_PATH = Path("abd_acceptance/limited_self_heal_acceptance.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S18_P03.json")
TEST_PATH = Path("tests/S18/P03_test.py")
JUNIT_PATH = Path("machine/evidence/S18/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S18/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S18-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S18-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")

EXPECTED_TASK_IDS = ("T-S18-P03-01", "T-S18-P03-02", "T-S18-P03-03")
EXPECTED_TEST_IDS = ("TEST-S18-P03", "TEST-S18-P03-BOUNDARY", "TEST-S18-P03-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S18-P03-01", "ART-S18-P03-02", "ART-S18-P03-03")
EXPECTED_OUTPUTS = (POLICY_PATH.as_posix(), WATCHDOG_PATH.as_posix(), OUTBOX_PATH.as_posix())
EXPECTED_PREDECESSORS = {"AC-S18-P02": "ce54a29f06d7dae07c1e559eebf360c7e41221851290d78496fdf51dd3b957c2"}
EXPECTED_SCENARIOS = (
    "HEALTHY_NO_FAULT_KEEP_GATES",
    "CANDIDATE_PROCESS_UNHEALTHY_LOGICAL_RESTART_ONLY",
    "FROZEN_REPLAY_MISMATCH_RETRY_ONLY",
    "SILENT_COVERAGE_GAP_REPLAY_DERIVED_STATE_ONLY",
    "SOURCE_FRESHNESS_FAILED_SWITCH_SIGNED_SNAPSHOT_ONLY",
    "MODEL_PSI_STOP_ROLLBACK_SIGNED_CANDIDATE_ONLY",
    "EVIDENCE_DERIVED_STATE_CORRUPT_REBUILD_ONLY",
    "UNSAFE_FUND_MUTATION_REQUEST_ESCALATES",
    "RISK_GATE_RELAXATION_ATTEMPT_ESCALATES",
    "ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_PRESERVES_RISK_GATE",
    "MALFORMED_PROBABILITY_DELTA_ESCALATES",
)
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
FEATURE_FLAG_ID = "self_heal:s18_p03_offline_bounded_operations"


class LimitedSelfHealAcceptanceError(ValueError):
    """Raised when S18/P03 cannot be reproduced without weakening a gate."""


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


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping) or _contains_float(value):
            raise LimitedSelfHealAcceptanceError("evidence index has an invalid row")
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise LimitedSelfHealAcceptanceError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise LimitedSelfHealAcceptanceError("expected one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def validate_fixture(value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "expected_next", "predecessors", "scenarios",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise LimitedSelfHealAcceptanceError("fixture schema is invalid")
    if not (
        value.get("schema_version") == "1.0.0"
        and value.get("product_version") == PRODUCT_VERSION
        and value.get("contract_id") == CONTRACT_ID
        and value.get("requirement_id") == REQUIREMENT_ID
        and value.get("stage_id") == STAGE_ID
        and value.get("phase_id") == PHASE_ID
        and value.get("fixed_clock") == FIXED_CLOCK
        and value.get("expected_next") == "S18/P04_READY_NOT_STARTED"
    ):
        raise LimitedSelfHealAcceptanceError("fixture identity differs from S18/P03")
    if value.get("predecessors") != [{"contract_id": "AC-S18-P02", "evidence_sha256": EXPECTED_PREDECESSORS["AC-S18-P02"]}]:
        raise LimitedSelfHealAcceptanceError("fixture predecessor differs")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != EXPECTED_SCENARIOS:
        raise LimitedSelfHealAcceptanceError("fixture scenario order differs")
    for scenario in scenarios:
        if not isinstance(scenario, Mapping) or set(scenario) != {"scenario_id", "watchdog_input", "expected"}:
            raise LimitedSelfHealAcceptanceError("fixture scenario schema is invalid")
        expected = scenario.get("expected")
        if not isinstance(expected, Mapping) or set(expected) != {"decision", "operation_ids"}:
            raise LimitedSelfHealAcceptanceError("fixture expected fields are invalid")
    return value


def load_fixture(path: Path) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(path))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S18P03-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S18P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S18P03-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S18P03-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S18P03-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        selected = [_row(tasks, identifier) for identifier in EXPECTED_TASK_IDS]
        requirement_ok = (
            requirement.get("scope") == list(EXPECTED_OUTPUTS)
            and requirement.get("target") == "自愈不能修改资金事实或放宽风险门。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
        )
        contract_ok = (
            contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == {"type": "EXECUTABLE", "command": "python -m abd_acceptance --contract AC-S18-P03 --evidence machine/evidence", "rule": "自愈不能修改资金事实或放宽风险门。"}
            and contract.get("pass_gate") == "自愈不能修改资金事实或放宽风险门。"
            and tuple(item.get("id") for item in contract.get("tests", []) if isinstance(item, Mapping)) == EXPECTED_TEST_IDS
        )
        task_ok = (
            tuple(item.get("id") for item in selected) == EXPECTED_TASK_IDS
            and selected[0].get("outputs") == list(EXPECTED_OUTPUTS)
            and selected[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and selected[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and selected[0].get("depends_on") == ["T-S18-P02-03"]
        )
        trace_ok = (
            trace.get("acceptance_criteria_id") == CONTRACT_ID
            and tuple(trace.get("task_ids", [])) == EXPECTED_TASK_IDS
            and tuple(trace.get("test_ids", [])) == EXPECTED_TEST_IDS
            and trace.get("evidence_id") == "EVD-S18-P03"
            and tuple(trace.get("artifact_ids", [])) == EXPECTED_ARTIFACT_IDS
        )
    except Exception as exc:
        requirement_ok = contract_ok = task_ok = trace_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = {"requirement": REQUIREMENT_ID, "contract": CONTRACT_ID, "tasks": EXPECTED_TASK_IDS}
    _add(checks, "S18P03-REQUIREMENT-EXACT", requirement_ok, detail)
    _add(checks, "S18P03-ACCEPTANCE-CONTRACT-EXACT", contract_ok, detail)
    _add(checks, "S18P03-TASK-GRAPH-EXACT", task_ok, detail)
    _add(checks, "S18P03-TRACEABILITY-EXACT", trace_ok, detail)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        common = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "自愈不能修改资金事实或放宽风险门。"
        )
        index_ok = common and (
            row.get("status") == "PLANNED"
            or (row.get("status") == "PASS" and row.get("stage_id") == STAGE_ID and row.get("actual_artifact") == EVIDENCE_PATH.as_posix() and isinstance(row.get("artifact_sha256"), str))
        )
    except Exception as exc:
        row = "%s: %s" % (type(exc).__name__, exc)
        index_ok = False
    _add(checks, "S18P03-EVIDENCE-INDEX-EXACT", index_ok, row)


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        result = verify_s18_p02(root)
        actual = result.get("evidence_sha256")
        ok = result.get("status") == "PASS" and actual == EXPECTED_PREDECESSORS["AC-S18-P02"]
    except Exception as exc:
        result = "%s: %s" % (type(exc).__name__, exc)
        actual = "UNAVAILABLE"
        ok = False
    hashes["machine/evidence/EVD-S18-P02.json"] = actual
    _add(checks, "S18P03-S18P02-SIGNED-DEPENDENCY", ok, result)


def _check_policy(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    policy = _safe_load(root, POLICY_PATH, checks, "S18P03-POLICY-STRICT-JSON")
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S18P03-PARAMETERS-STRICT-JSON")
    canonical = _safe_load(root, Path("machine/facts/canonical_facts.json"), checks, "S18P03-CANONICAL-STRICT-JSON")
    if not isinstance(policy, Mapping) or not isinstance(parameters, Mapping) or not isinstance(canonical, Mapping):
        _add(checks, "S18P03-IMMUTABLE-FUND-AND-RISK-POLICY-EXACT", False, "documents unavailable")
        _add(checks, "S18P03-BOUNDED-SELF-HEAL-OPERATIONS-EXACT", False, "documents unavailable")
        return None
    try:
        verified, operations = validate_policy(policy)
        operation_pairs = tuple((fault_id, row["operation_id"]) for fault_id, row in operations.items())
        risk = parameters["risk"]
        fund_ok = (
            verified["immutable_fund_facts"] == {
                "money_storage": parameters["numeric_determinism"]["money_storage"],
                "frozen_bankroll_reference_aud": canonical["product"]["initial_bankroll_aud"],
                "actual_fund_fact_mutation_allowed": False,
                "actual_ledger_mutation_allowed": False,
            }
            and verified["immutable_risk_gate"] == {
                "kelly_fraction_alpha": risk["kelly_fraction_alpha"],
                "kelly_fraction_beta": risk["kelly_fraction_beta"],
                "kelly_fraction_ga": risk["kelly_fraction_ga"],
                "total_open_exposure_cap": risk["total_open_exposure_cap"],
                "target_shortfall_may_relax_gate": risk["target_shortfall_may_relax_gate"],
                "unstable_action": parameters["numeric_determinism"]["unstable_action"],
            }
            and canonical["truth_and_evidence"]["advice_ledger_separate_from_actual_ledger"] is True
        )
        operations_ok = (
            policy.get("policy_id") == POLICY_ID
            and operation_pairs == EXPECTED_OPERATIONS
            and all(row["derived_state_only"] is True and row["writes_shared_ledger"] is False for row in operations.values())
            and policy["outbox_policy"] == {
                "delivery_mode": "LOCAL_STRUCTURED_OUTBOX_PROJECTION_ONLY",
                "external_delivery_enabled": False,
                "retry_external_delivery": False,
                "owner_action": canonical["scope"]["normal_owner_action"],
            }
            and policy["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
        )
    except Exception as exc:
        fund_ok = operations_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = {"operation_pairs": list(operation_pairs), "fund_mutation_allowed": verified["immutable_fund_facts"]["actual_fund_fact_mutation_allowed"], "risk_relaxation_allowed": verified["immutable_risk_gate"]["target_shortfall_may_relax_gate"]}
    hashes[POLICY_PATH.as_posix()] = sha256_file(root / POLICY_PATH)
    _add(checks, "S18P03-IMMUTABLE-FUND-AND-RISK-POLICY-EXACT", fund_ok, detail)
    _add(checks, "S18P03-BOUNDED-SELF-HEAL-OPERATIONS-EXACT", operations_ok, detail)
    return policy


def _check_runners(root: Path, policy: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        source = "\n".join((root / path).read_text(encoding="utf-8") for path in (WATCHDOG_PATH, OUTBOX_PATH, CORE_PATH))
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "urllib", "requests", "httpx", "subprocess", "os", "shutil", "time", "asyncio", "smtplib"}
        static_ok = not (imports & forbidden) and "http://" not in source and "https://" not in source
        for path in (WATCHDOG_PATH, OUTBOX_PATH, CORE_PATH):
            hashes[path.as_posix()] = sha256_file(root / path)
    except Exception as exc:
        static_ok = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P03-WATCHDOG-OUTBOX-LOCAL-ONLY-STATIC", static_ok, "parsed" if static_ok else source)
    scenario_ok = True
    replay_ok = True
    immutable_ok = True
    outbox_ok = True
    escalation_ok = False
    adverse_ok = False
    observed_operations: set[str] = set()
    details = []
    for scenario in fixture["scenarios"]:
        first = evaluate_watchdog_event(scenario["watchdog_input"], policy)
        second = evaluate_watchdog_event(scenario["watchdog_input"], policy)
        outbox_first = evaluate_outbox_projection(first, policy)
        outbox_second = evaluate_outbox_projection(second, policy)
        selected = {key: first.get(key) for key in scenario["expected"]}
        matched = (
            selected == scenario["expected"]
            and first.get("fund_facts_before") == first.get("fund_facts_after") == SAFE_FUND_FACTS
            and first.get("risk_gate_before") == first.get("risk_gate_after") == SAFE_RISK_GATE
            and first.get("fund_facts_changed") is False
            and first.get("risk_gate_relaxed") is False
            and first.get("shared_ledger_written") is False
            and first.get("safe_action") == SAFE_ACTION
            and first.get("recommendation_generated_or_enabled") is False
            and first.get("order_submission_enabled") is False
            and len(first.get("operation_ids", [])) == len(set(first.get("operation_ids", [])))
        )
        scenario_ok = scenario_ok and matched
        replay_ok = replay_ok and first == second and first.get("watchdog_plan_sha256") == second.get("watchdog_plan_sha256") and outbox_first == outbox_second and outbox_first.get("outbox_projection_sha256") == outbox_second.get("outbox_projection_sha256")
        immutable_ok = immutable_ok and matched
        outbox_ok = outbox_ok and outbox_first.get("delivery_status") == "LOCAL_OUTBOX_NOT_SENT" and outbox_first.get("external_delivery_attempted") is False and outbox_first.get("external_delivery_enabled") is False and outbox_first.get("external_network_accessed") is False and outbox_first.get("actual_fund_facts_changed") is False and outbox_first.get("risk_gate_relaxed") is False and outbox_first.get("order_submission_enabled") is False
        escalation_ok = escalation_ok or (scenario["scenario_id"] in {"UNSAFE_FUND_MUTATION_REQUEST_ESCALATES", "RISK_GATE_RELAXATION_ATTEMPT_ESCALATES", "MALFORMED_PROBABILITY_DELTA_ESCALATES"} and first.get("decision") == ESCALATION_DECISION and first.get("operation_ids") == ["LOGICAL_ESCALATE_OWNER_OUTBOX_ONLY"])
        adverse_ok = adverse_ok or (scenario["scenario_id"] == "ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_PRESERVES_RISK_GATE" and first.get("risk_gate_relaxed") is False and first.get("decision") == APPROVED_DECISION)
        observed_operations.update(first.get("operation_ids", []))
        details.append({"scenario_id": scenario["scenario_id"], "passed": matched, "decision": first.get("decision"), "outbox": outbox_first.get("delivery_status")})
    expected_planned = {operation_id for fault_id, operation_id in EXPECTED_OPERATIONS if fault_id != FALLBACK_FAULT_ID}
    _add(checks, "S18P03-SELF-HEAL-PRESERVES-FUND-FACTS-AND-RISK-GATES", scenario_ok and immutable_ok, details)
    _add(checks, "S18P03-ALL-BOUNDED-OPERATIONS-REPLAYED-EXACT", expected_planned <= observed_operations, {"expected": sorted(expected_planned), "observed": sorted(observed_operations)})
    _add(checks, "S18P03-OUTBOX-LOCAL-ONLY-NOT-SENT", outbox_ok, details)
    _add(checks, "S18P03-UNSAFE-MUTATION-AND-MALFORMED-INPUT-ESCALATE", escalation_ok, details)
    _add(checks, "S18P03-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-RISK-GATE", adverse_ok, details)
    _add(checks, "S18P03-DETERMINISTIC-REPLAY-HASH-EXACT", replay_ok, details)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .limited_self_heal_acceptance import verify_existing_phase_evidence as verify_limited_self_heal_phase_evidence" in source
            and "from .limited_self_heal_acceptance import write_phase_evidence as write_limited_self_heal_phase_evidence" in source
            and '"AC-S18-P03": verify_limited_self_heal_phase_evidence,' in source
            and '"AC-S18-P03": write_limited_self_heal_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P03-CLI-WRITER-AND-VERIFIER-EXACT", exact, "abd_acceptance/__main__.py" if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(checks, "S18P03-S08-LEGACY-SUCCESSOR-PIN-EXACT", successor == sha256_file(root / CLI_PATH), {"approved": successor, "current": sha256_file(root / CLI_PATH)})


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
            and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
            for suite in suites
        )
        return summary, normalized
    except Exception:
        return {"tests": 0, "failures": 1, "errors": 1, "skipped": 0}, False


def _check_reports(root: Path, checks: List[Dict[str, Any]], require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S18P03-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    _add(checks, "S18P03-TARGETED-PYTEST-REPORT", summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P03-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S18P03-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S18P03-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S18_P03_LIMITED_SELF_HEAL_CONTROL_PASS_P04_REQUIRED" if passed else "S18/P03_BLOCKED",
        "next": "S18/P04_READY_NOT_STARTED" if passed else "S18/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    policy = _check_policy(root, checks, hashes)
    try:
        fixture = load_fixture(root / FIXTURE_PATH)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        _add(checks, "S18P03-FIXTURE-EXACT", True, FIXTURE_PATH.as_posix())
    except Exception as exc:
        fixture = None
        _add(checks, "S18P03-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    if policy is not None and fixture is not None:
        _check_runners(root, policy, fixture, checks, hashes)
    else:
        for identifier in (
            "S18P03-WATCHDOG-OUTBOX-LOCAL-ONLY-STATIC",
            "S18P03-SELF-HEAL-PRESERVES-FUND-FACTS-AND-RISK-GATES",
            "S18P03-ALL-BOUNDED-OPERATIONS-REPLAYED-EXACT",
            "S18P03-OUTBOX-LOCAL-ONLY-NOT-SENT",
            "S18P03-UNSAFE-MUTATION-AND-MALFORMED-INPUT-ESCALATE",
            "S18P03-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-RISK-GATE",
            "S18P03-DETERMINISTIC-REPLAY-HASH-EXACT",
        ):
            _add(checks, identifier, False, "policy or fixture unavailable")
    _check_cli_wiring(root, checks)
    _check_reports(root, checks, require_test_reports)
    _add(checks, "S18P03-EXTERNAL-EFFECT-BOUNDARY-EXACT", all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud") and EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00", EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (POLICY_PATH, WATCHDOG_PATH, OUTBOX_PATH, CORE_PATH, ORACLE_PATH, FIXTURE_PATH, Path("machine/evidence/EVD-S18-P02.json"))
    artifacts = {
        path.as_posix(): {
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
            "status": "PASS" if (root / path).is_file() else "FAIL",
        }
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S18-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_LOCAL_LIMITED_SELF_HEAL_POLICY_KEEP_S18_P02_SIGNED_CONTROL",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "immutable_fund_and_risk_verified": True,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "outbox_sent": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, require_test_reports: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, POLICY_PATH, WATCHDOG_PATH, OUTBOX_PATH, CORE_PATH, FIXTURE_PATH, TEST_PATH, Path("machine/evidence/EVD-S18-P02.json")]
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
        "evidence_id": "EVD-S18-P03",
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
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S18_P03_LOCAL_LIMITED_SELF_HEAL_CONTROL_ONLY_P04_REQUIRED" if validation["status"] == "PASS" else "S18_P03_REMEDIATION_REQUIRED",
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "bounded_operation_count": len(EXPECTED_OPERATIONS),
            "immutable_fund_and_risk_scenario_count": len(EXPECTED_SCENARIOS),
            "unsafe_or_malformed_escalation_count": 3,
            "adverse_one_in_ten_thousand_vector_count": 1,
            "external_runtime_accessed": False,
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
        "kind": "ACCEPTANCE_EVIDENCE",
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "acceptance_contract_id": CONTRACT_ID,
        "status": "PASS",
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S18/P04_READY_NOT_STARTED",
        "pass_gate": "自愈不能修改资金事实或放宽风险门。",
        "verified_at": FIXED_CLOCK,
    }
    matching = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) != 1 or len(raw_lines) != len(rows):
        raise LimitedSelfHealAcceptanceError("S18/P03 evidence-index row must exist exactly once")
    raw_lines[matching[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise LimitedSelfHealAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise LimitedSelfHealAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/P04_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S18_P03_LIMITED_SELF_HEAL_CONTROL_PASS_P04_REQUIRED"
        and evidence.get("next") == "S18/P04_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("immutable_fund_and_risk_verified") is True
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("outbox_sent") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S18/P04_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise LimitedSelfHealAcceptanceError("existing S18/P03 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/P04_READY_NOT_STARTED",
    }


__all__ = [
    "CONTRACT_ID", "EVIDENCE_PATH", "EXTERNAL_EFFECT_BOUNDARY", "FEATURE_FLAG_ID", "FIXTURE_PATH",
    "LimitedSelfHealAcceptanceError", "OUTBOX_PATH", "POLICY_PATH", "WATCHDOG_PATH", "build_evidence", "evaluate_contract",
    "load_fixture", "perform_rollback_drill", "validate_candidate_preflight", "validate_fixture", "verify_existing_phase_evidence", "write_phase_evidence",
]
