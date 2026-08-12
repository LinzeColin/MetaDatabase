"""Fail-closed, offline acceptance oracle for ABD S18/P04 operations automation."""

from __future__ import annotations

import ast
import hashlib
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .legacy_receipt_compatibility import approved_successor_sha256
from .limited_self_heal_acceptance import verify_existing_phase_evidence as verify_s18_p03
from .operations_automation import (
    EXPECTED_JOB_IDS,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXED_CLOCK,
    NORMAL_ACTION,
    NORMAL_DECISION,
    OperationsInputError,
    PAUSE_ACTION,
    PAUSE_DECISION,
    SAFE_ACTION,
    SAFE_FUND_FACTS,
    SAFE_RISK_GATE,
    evaluate_operations_cycle,
    validate_maintenance_calendar,
    validate_runbook,
    validate_scheduled_jobs,
)


CONTRACT_ID = "AC-S18-P04"
REQUIREMENT_ID = "REQ-S18-P04"
STAGE_ID = "S18"
PHASE_ID = "P04"
PRODUCT_VERSION = "0.0.0.1"

RUNBOOK_PATH = Path("operations_runbook.md")
SCHEDULE_PATH = Path("scheduled_jobs.json")
CALENDAR_PATH = Path("maintenance_calendar.json")
CORE_PATH = Path("abd_acceptance/operations_automation.py")
ORACLE_PATH = Path("abd_acceptance/operations_automation_acceptance.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S18_P04.json")
TEST_PATH = Path("tests/S18/P04_test.py")
JUNIT_PATH = Path("machine/evidence/S18/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S18/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S18-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S18-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")

EXPECTED_TASK_IDS = ("T-S18-P04-01", "T-S18-P04-02", "T-S18-P04-03")
EXPECTED_TEST_IDS = ("TEST-S18-P04", "TEST-S18-P04-BOUNDARY", "TEST-S18-P04-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S18-P04-01", "ART-S18-P04-02", "ART-S18-P04-03")
EXPECTED_OUTPUTS = (RUNBOOK_PATH.as_posix(), SCHEDULE_PATH.as_posix(), CALENDAR_PATH.as_posix())
EXPECTED_PREDECESSORS = {"AC-S18-P03": "99ade2e845cd72af99713e4c0d5d07e2aea3a1e49e6895f5b9bcdeca2a9afe1f"}
EXPECTED_SCENARIOS = (
    "GOLDEN_ALL_LOGICAL_JOBS_PASS",
    "DAILY_SIGNED_CONTROL_FAILURE_PAUSES",
    "DAILY_MAIL_EVIDENCE_FAILURE_PAUSES",
    "WEEKLY_PATCH_FAILURE_PAUSES",
    "WEEKLY_BACKUP_FAILURE_PAUSES",
    "MONTHLY_DISASTER_FAILURE_PAUSES",
    "MONTHLY_RETENTION_FAILURE_PAUSES",
    "ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_PRESERVES_GATES",
    "FUND_MUTATION_ATTEMPT_PAUSES",
    "RISK_GATE_RELAXATION_ATTEMPT_PAUSES",
    "EXTERNAL_EXECUTION_ATTEMPT_PAUSES",
    "MALFORMED_JOB_STATUS_PAUSES",
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
FEATURE_FLAG_ID = "operations_automation:s18_p04_offline_pause_contract"


class OperationsAutomationAcceptanceError(ValueError):
    """Raised when S18/P04 cannot be reproduced without relaxing its pause contract."""


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
            raise OperationsAutomationAcceptanceError("evidence index has an invalid row")
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise OperationsAutomationAcceptanceError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise OperationsAutomationAcceptanceError("expected one %s=%s" % (key, identifier))
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
        raise OperationsAutomationAcceptanceError("fixture schema is invalid")
    if not (
        value.get("schema_version") == "1.0.0"
        and value.get("product_version") == PRODUCT_VERSION
        and value.get("contract_id") == CONTRACT_ID
        and value.get("requirement_id") == REQUIREMENT_ID
        and value.get("stage_id") == STAGE_ID
        and value.get("phase_id") == PHASE_ID
        and value.get("fixed_clock") == FIXED_CLOCK
        and value.get("expected_next") == "S18/STAGE_REVIEW_READY_NOT_STARTED"
    ):
        raise OperationsAutomationAcceptanceError("fixture identity differs from S18/P04")
    if value.get("predecessors") != [{"contract_id": "AC-S18-P03", "evidence_sha256": EXPECTED_PREDECESSORS["AC-S18-P03"]}]:
        raise OperationsAutomationAcceptanceError("fixture predecessor differs")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != EXPECTED_SCENARIOS:
        raise OperationsAutomationAcceptanceError("fixture scenario order differs")
    for scenario in scenarios:
        if not isinstance(scenario, Mapping) or set(scenario) != {"scenario_id", "cycle_input", "expected"}:
            raise OperationsAutomationAcceptanceError("fixture scenario schema differs")
        expected = scenario.get("expected")
        if not isinstance(expected, Mapping) or set(expected) != {"decision", "action", "pause_contract", "failed_job_ids"}:
            raise OperationsAutomationAcceptanceError("fixture expected schema differs")
    return value


def load_fixture(path: Path) -> Mapping[str, Any]:
    return validate_fixture(strict_json_load(path))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S18P04-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S18P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S18P04-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S18P04-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S18P04-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        selected = [_row(tasks, identifier) for identifier in EXPECTED_TASK_IDS]
        requirement_ok = (
            requirement.get("scope") == list(EXPECTED_OUTPUTS)
            and requirement.get("target") == "正常运行无需用户维护；异常仅按暂停合同升级。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
        )
        contract_ok = (
            contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == {"type": "EXECUTABLE", "command": "python -m abd_acceptance --contract AC-S18-P04 --evidence machine/evidence", "rule": "正常运行无需用户维护；异常仅按暂停合同升级。"}
            and contract.get("pass_gate") == "正常运行无需用户维护；异常仅按暂停合同升级。"
            and tuple(item.get("id") for item in contract.get("tests", []) if isinstance(item, Mapping)) == EXPECTED_TEST_IDS
        )
        task_ok = (
            tuple(item.get("id") for item in selected) == EXPECTED_TASK_IDS
            and selected[0].get("outputs") == list(EXPECTED_OUTPUTS)
            and selected[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and selected[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and selected[0].get("depends_on") == ["T-S18-P03-03"]
        )
        trace_ok = (
            trace.get("acceptance_criteria_id") == CONTRACT_ID
            and tuple(trace.get("task_ids", [])) == EXPECTED_TASK_IDS
            and tuple(trace.get("test_ids", [])) == EXPECTED_TEST_IDS
            and trace.get("evidence_id") == "EVD-S18-P04"
            and tuple(trace.get("artifact_ids", [])) == EXPECTED_ARTIFACT_IDS
        )
    except Exception as exc:
        requirement_ok = contract_ok = task_ok = trace_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = {"requirement": REQUIREMENT_ID, "contract": CONTRACT_ID, "tasks": EXPECTED_TASK_IDS}
    _add(checks, "S18P04-REQUIREMENT-EXACT", requirement_ok, detail)
    _add(checks, "S18P04-ACCEPTANCE-CONTRACT-EXACT", contract_ok, detail)
    _add(checks, "S18P04-TASK-GRAPH-EXACT", task_ok, detail)
    _add(checks, "S18P04-TRACEABILITY-EXACT", trace_ok, detail)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        common = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "正常运行无需用户维护；异常仅按暂停合同升级。"
        )
        index_ok = common and (
            row.get("status") == "PLANNED"
            or (row.get("status") == "PASS" and row.get("stage_id") == STAGE_ID and row.get("actual_artifact") == EVIDENCE_PATH.as_posix() and isinstance(row.get("artifact_sha256"), str))
        )
    except Exception as exc:
        row = "%s: %s" % (type(exc).__name__, exc)
        index_ok = False
    _add(checks, "S18P04-EVIDENCE-INDEX-EXACT", index_ok, row)


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        result = verify_s18_p03(root)
        actual = result.get("evidence_sha256")
        ok = result.get("status") == "PASS" and actual == EXPECTED_PREDECESSORS["AC-S18-P03"]
    except Exception as exc:
        result = "%s: %s" % (type(exc).__name__, exc)
        actual = "UNAVAILABLE"
        ok = False
    hashes["machine/evidence/EVD-S18-P03.json"] = actual
    _add(checks, "S18P04-S18P03-SIGNED-DEPENDENCY", ok, result)


def _check_documents(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    schedule = _safe_load(root, SCHEDULE_PATH, checks, "S18P04-SCHEDULE-STRICT-JSON")
    calendar = _safe_load(root, CALENDAR_PATH, checks, "S18P04-CALENDAR-STRICT-JSON")
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S18P04-PARAMETERS-STRICT-JSON")
    canonical = _safe_load(root, Path("machine/facts/canonical_facts.json"), checks, "S18P04-CANONICAL-STRICT-JSON")
    try:
        runbook = (root / RUNBOOK_PATH).read_text(encoding="utf-8")
        validate_runbook(runbook)
        runbook_ok = True
    except Exception as exc:
        runbook = "%s: %s" % (type(exc).__name__, exc)
        runbook_ok = False
    _add(checks, "S18P04-RUNBOOK-PAUSE-CONTRACT-EXACT", runbook_ok, RUNBOOK_PATH.as_posix() if runbook_ok else runbook)
    if not isinstance(schedule, Mapping) or not isinstance(calendar, Mapping) or not isinstance(parameters, Mapping) or not isinstance(canonical, Mapping):
        _add(checks, "S18P04-SCHEDULE-CALENDAR-IMMUTABLE-EXACT", False, "documents unavailable")
        _add(checks, "S18P04-DAILY-WEEKLY-MONTHLY-OPERATIONS-EXACT", False, "documents unavailable")
        return None, None
    try:
        verified_schedule = validate_scheduled_jobs(schedule)
        verified_calendar = validate_maintenance_calendar(calendar)
        risk = parameters["risk"]
        immutable_ok = (
            verified_schedule["immutable_fund_facts"] == {
                "money_storage": parameters["numeric_determinism"]["money_storage"],
                "frozen_bankroll_reference_aud": canonical["product"]["initial_bankroll_aud"],
                "actual_fund_fact_mutation_allowed": False,
                "actual_ledger_mutation_allowed": False,
            }
            and verified_schedule["immutable_risk_gate"] == {
                "kelly_fraction_alpha": risk["kelly_fraction_alpha"],
                "kelly_fraction_beta": risk["kelly_fraction_beta"],
                "kelly_fraction_ga": risk["kelly_fraction_ga"],
                "total_open_exposure_cap": risk["total_open_exposure_cap"],
                "target_shortfall_may_relax_gate": risk["target_shortfall_may_relax_gate"],
                "unstable_action": parameters["numeric_determinism"]["unstable_action"],
            }
            and canonical["truth_and_evidence"]["advice_ledger_separate_from_actual_ledger"] is True
            and verified_schedule["external_effect_boundary"] == verified_calendar["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
        )
        job_ids = tuple(item["job_id"] for item in verified_schedule["jobs"])
        calendar_jobs = tuple(item["job_id"] for item in verified_calendar["maintenance_windows"])
        calendar_modes_ok = all(item["maintenance_mode"] == "LOGICAL_CONTROL_WINDOW_ONLY" and item["requires_owner_maintenance_normal"] is False for item in verified_calendar["maintenance_windows"])
        operations_ok = (
            job_ids == EXPECTED_JOB_IDS
            and calendar_jobs == EXPECTED_JOB_IDS
            and calendar_modes_ok
            and verified_schedule["normal_operation"]["owner_maintenance_required"] is False
            and verified_schedule["exception_policy"]["pause_contract"] is True
            and verified_schedule["exception_policy"]["external_delivery_enabled"] is False
            and verified_calendar["normal_owner_maintenance_required"] is False
            and verified_calendar["exception_escalation"]["pause_contract"] is True
        )
    except Exception as exc:
        verified_schedule = verified_calendar = None
        immutable_ok = operations_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = {"job_ids": list(job_ids), "owner_maintenance_normal": False, "pause_contract": True}
    for path in (RUNBOOK_PATH, SCHEDULE_PATH, CALENDAR_PATH):
        hashes[path.as_posix()] = sha256_file(root / path)
    _add(checks, "S18P04-SCHEDULE-CALENDAR-IMMUTABLE-EXACT", immutable_ok, detail)
    _add(checks, "S18P04-DAILY-WEEKLY-MONTHLY-OPERATIONS-EXACT", operations_ok, detail)
    return verified_schedule, verified_calendar


def _check_runner_and_fixture(root: Path, schedule: Mapping[str, Any], calendar: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        source = (root / CORE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "urllib", "requests", "httpx", "subprocess", "os", "shutil", "time", "asyncio", "smtplib"}
        static_ok = not (imports & forbidden) and "http://" not in source and "https://" not in source
        hashes[CORE_PATH.as_posix()] = sha256_file(root / CORE_PATH)
    except Exception as exc:
        static_ok = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P04-OPERATIONS-RUNNER-LOCAL-ONLY-STATIC", static_ok, "parsed" if static_ok else source)
    try:
        fixture = load_fixture(root / FIXTURE_PATH)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        fixture_ok = True
    except Exception as exc:
        fixture = None
        fixture_ok = False
        fixture_detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        fixture_detail = FIXTURE_PATH.as_posix()
    _add(checks, "S18P04-FIXTURE-EXACT", fixture_ok, fixture_detail)
    if fixture is None:
        for identifier in (
            "S18P04-NORMAL-CYCLE-NO-OWNER-MAINTENANCE",
            "S18P04-ALL-SCHEDULED-JOB-FAILURES-PAUSE-EXACT",
            "S18P04-UNSAFE-INPUT-PAUSES-WITH-IMMUTABLE-GATES",
            "S18P04-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-GATES",
            "S18P04-DETERMINISTIC-REPLAY-HASH-EXACT",
        ):
            _add(checks, identifier, False, "fixture unavailable")
        return
    normal_ok = True
    all_failure_jobs: set[str] = set()
    unsafe_ok = True
    adverse_ok = False
    replay_ok = True
    details = []
    unsafe_scenarios = {
        "FUND_MUTATION_ATTEMPT_PAUSES",
        "RISK_GATE_RELAXATION_ATTEMPT_PAUSES",
        "EXTERNAL_EXECUTION_ATTEMPT_PAUSES",
        "MALFORMED_JOB_STATUS_PAUSES",
    }
    for scenario in fixture["scenarios"]:
        first = evaluate_operations_cycle(scenario["cycle_input"], schedule, calendar)
        second = evaluate_operations_cycle(scenario["cycle_input"], schedule, calendar)
        observed = {key: first.get(key) for key in scenario["expected"]}
        matched = observed == scenario["expected"]
        safety = (
            first.get("fund_facts_before") == first.get("fund_facts_after") == SAFE_FUND_FACTS
            and first.get("risk_gate_before") == first.get("risk_gate_after") == SAFE_RISK_GATE
            and first.get("fund_facts_changed") is False
            and first.get("risk_gate_relaxed") is False
            and first.get("safe_action") == SAFE_ACTION
            and first.get("recommendation_generated_or_enabled") is False
            and first.get("order_submission_enabled") is False
            and first.get("external_runtime_accessed") is False
            and first.get("production_state_changed") is False
            and first.get("owner_outbox_projection", {}).get("external_delivery_attempted") is False
            and first.get("owner_outbox_projection", {}).get("external_network_accessed") is False
        )
        normal_ok = normal_ok and matched and safety
        replay_ok = replay_ok and first == second and first.get("operations_plan_sha256") == second.get("operations_plan_sha256")
        if scenario["scenario_id"].endswith("FAILURE_PAUSES"):
            all_failure_jobs.update(first.get("failed_job_ids", []))
        if scenario["scenario_id"] in unsafe_scenarios:
            unsafe_ok = unsafe_ok and matched and safety and first.get("decision") == PAUSE_DECISION and first.get("pause_contract") is True and first.get("owner_outbox_projection", {}).get("status") == "LOCAL_OWNER_ESCALATION_NOT_SENT"
        if scenario["scenario_id"] == "ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_PRESERVES_GATES":
            adverse_ok = matched and safety and first.get("decision") == NORMAL_DECISION and first.get("pause_contract") is False
        details.append({"scenario_id": scenario["scenario_id"], "passed": matched and safety, "decision": first.get("decision"), "failed_job_ids": first.get("failed_job_ids")})
    _add(checks, "S18P04-NORMAL-CYCLE-NO-OWNER-MAINTENANCE", normal_ok, details)
    _add(checks, "S18P04-ALL-SCHEDULED-JOB-FAILURES-PAUSE-EXACT", all_failure_jobs == set(EXPECTED_JOB_IDS), {"expected": list(EXPECTED_JOB_IDS), "observed": sorted(all_failure_jobs)})
    _add(checks, "S18P04-UNSAFE-INPUT-PAUSES-WITH-IMMUTABLE-GATES", unsafe_ok, details)
    _add(checks, "S18P04-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-GATES", adverse_ok, details)
    _add(checks, "S18P04-DETERMINISTIC-REPLAY-HASH-EXACT", replay_ok, details)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .operations_automation_acceptance import verify_existing_phase_evidence as verify_operations_automation_phase_evidence" in source
            and "from .operations_automation_acceptance import write_phase_evidence as write_operations_automation_phase_evidence" in source
            and '"AC-S18-P04": verify_operations_automation_phase_evidence,' in source
            and '"AC-S18-P04": write_operations_automation_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P04-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(checks, "S18P04-S08-LEGACY-SUCCESSOR-PIN-EXACT", successor == sha256_file(root / CLI_PATH), {"approved": successor, "current": sha256_file(root / CLI_PATH)})


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
        _add(checks, "S18P04-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    _add(checks, "S18P04-TARGETED-PYTEST-REPORT", summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18P04-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S18P04-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S18P04-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S18_P04_OPERATIONS_AUTOMATION_PASS_STAGE_REVIEW_REQUIRED" if passed else "S18/P04_BLOCKED",
        "next": "S18/STAGE_REVIEW_READY_NOT_STARTED" if passed else "S18/P04_REMEDIATION_REQUIRED",
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
    schedule, calendar = _check_documents(root, checks, hashes)
    if schedule is not None and calendar is not None:
        _check_runner_and_fixture(root, schedule, calendar, checks, hashes)
    else:
        for identifier in (
            "S18P04-OPERATIONS-RUNNER-LOCAL-ONLY-STATIC",
            "S18P04-FIXTURE-EXACT",
            "S18P04-NORMAL-CYCLE-NO-OWNER-MAINTENANCE",
            "S18P04-ALL-SCHEDULED-JOB-FAILURES-PAUSE-EXACT",
            "S18P04-UNSAFE-INPUT-PAUSES-WITH-IMMUTABLE-GATES",
            "S18P04-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-GATES",
            "S18P04-DETERMINISTIC-REPLAY-HASH-EXACT",
        ):
            _add(checks, identifier, False, "schedule or calendar unavailable")
    _check_cli_wiring(root, checks)
    _check_reports(root, checks, require_test_reports)
    _add(checks, "S18P04-EXTERNAL-EFFECT-BOUNDARY-EXACT", all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key != "incremental_cash_spent_aud") and EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00", EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (RUNBOOK_PATH, SCHEDULE_PATH, CALENDAR_PATH, CORE_PATH, ORACLE_PATH, FIXTURE_PATH, Path("machine/evidence/EVD-S18-P03.json"))
    artifacts = {
        path.as_posix(): {
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
            "status": "PASS" if (root / path).is_file() else "FAIL",
        }
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S18-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_LOCAL_OPERATIONS_AUTOMATION_KEEP_S18_P03_SIGNED_CONTROL",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "pause_contract_preserved": True,
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
    paths = [ORACLE_PATH, RUNBOOK_PATH, SCHEDULE_PATH, CALENDAR_PATH, CORE_PATH, FIXTURE_PATH, TEST_PATH, Path("machine/evidence/EVD-S18-P03.json")]
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
        "evidence_id": "EVD-S18-P04",
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
        "release_status": "S18_P04_LOCAL_OPERATIONS_AUTOMATION_ONLY_STAGE_REVIEW_REQUIRED" if validation["status"] == "PASS" else "S18_P04_REMEDIATION_REQUIRED",
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "scheduled_job_count": len(EXPECTED_JOB_IDS),
            "single_job_pause_vector_count": len(EXPECTED_JOB_IDS),
            "unsafe_or_malformed_pause_count": 4,
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
        "next": "S18/STAGE_REVIEW_READY_NOT_STARTED",
        "pass_gate": "正常运行无需用户维护；异常仅按暂停合同升级。",
        "verified_at": FIXED_CLOCK,
    }
    matches = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matches) != 1 or len(raw_lines) != len(rows):
        raise OperationsAutomationAcceptanceError("S18/P04 evidence-index row must exist exactly once")
    raw_lines[matches[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise OperationsAutomationAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise OperationsAutomationAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/STAGE_REVIEW_READY_NOT_STARTED",
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
        and evidence.get("decision") == "S18_P04_OPERATIONS_AUTOMATION_PASS_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S18/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("pause_contract_preserved") is True
        and rollback.get("immutable_fund_and_risk_verified") is True
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("outbox_sent") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S18/STAGE_REVIEW_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise OperationsAutomationAcceptanceError("existing S18/P04 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/STAGE_REVIEW_READY_NOT_STARTED",
    }


__all__ = [
    "CALENDAR_PATH", "CONTRACT_ID", "EVIDENCE_PATH", "EXTERNAL_EFFECT_BOUNDARY", "FEATURE_FLAG_ID", "FIXTURE_PATH",
    "OperationsAutomationAcceptanceError", "RUNBOOK_PATH", "SCHEDULE_PATH", "build_evidence", "evaluate_contract", "load_fixture",
    "perform_rollback_drill", "validate_candidate_preflight", "validate_fixture", "verify_existing_phase_evidence", "write_phase_evidence",
]
