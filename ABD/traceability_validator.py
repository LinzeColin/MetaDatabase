"""Fail-closed requirement-to-release traceability gate for ABD S15/P04.

This oracle checks only frozen local artifacts.  It proves the declared S15
chain from requirement through acceptance contract, task graph, tests,
evidence-index, and delivery artifacts.  It deliberately does not contact a
host, edge, browser, TAB, Gmail, database, account, or order endpoint.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from abd_acceptance.canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S15-P04"
REQUIREMENT_ID = "REQ-S15-P04"
STAGE_ID = "S15"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

ORACLE_PATH = Path("traceability_validator.py")
CLI_PROXY_PATH = Path("abd_acceptance/traceability_proxy.py")
SOFTWARE_GATE_PATH = Path("software_gate.json")
TEST_PATH = Path("tests/S15/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S15_P04.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S15/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S15/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
ROADMAP_PATH = Path("machine/facts/roadmap.json")
CANONICAL_FACTS_PATH = Path("machine/facts/canonical_facts.json")

P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S15-P03_rollback.json")
P03_EVIDENCE_SHA256 = "c669a73781f28bb8fd1a5521f284c24f47bbe9595ad12f95ad9c47c27c809c29"
P03_ROLLBACK_SHA256 = "6761c0afe059c562d2147c0d1c731e3b9dc52f1d5dd6c71da08195554c99e258"
P03_E2E_TESTS_PATH = Path("e2e_tests.json")
P03_E2E_EVIDENCE_PATH = Path("e2e_evidence.json")

FEATURE_FLAG_ID = "quality:s15-p04-traceability-software-gate"
EXPECTED_TASK_IDS = ("T-S15-P04-01", "T-S15-P04-02", "T-S15-P04-03")
EXPECTED_TEST_IDS = ("TEST-S15-P04", "TEST-S15-P04-BOUNDARY", "TEST-S15-P04-REPLAY")
EXPECTED_ARTIFACTS = {
    "ART-S15-P04-01": ORACLE_PATH,
    "ART-S15-P04-02": SOFTWARE_GATE_PATH,
}
EXPECTED_TASK_OUTPUTS = {
    "T-S15-P04-01": ["traceability_validator.py", "software_gate.json"],
    "T-S15-P04-02": ["tests/S15/P04_test.py", "machine/tests/fixtures/S15_P04.json"],
    "T-S15-P04-03": ["machine/evidence/EVD-S15-P04.json", "machine/evidence/EVD-S15-P04_rollback.json"],
}

CRITICAL_PHASE_SPECS = (
    {
        "phase_id": "P01",
        "requirement_id": "REQ-S15-P01",
        "contract_id": "AC-S15-P01",
        "evidence_id": "EVD-S15-P01",
        "evidence_index_id": "INDEX-AC-S15-P01",
        "evidence_path": "machine/evidence/EVD-S15-P01.json",
        "next": "S15/P02_READY_NOT_STARTED",
        "signed_required": True,
    },
    {
        "phase_id": "P02",
        "requirement_id": "REQ-S15-P02",
        "contract_id": "AC-S15-P02",
        "evidence_id": "EVD-S15-P02",
        "evidence_index_id": "INDEX-AC-S15-P02",
        "evidence_path": "machine/evidence/EVD-S15-P02.json",
        "next": "S15/P03_READY_NOT_STARTED",
        "signed_required": True,
    },
    {
        "phase_id": "P03",
        "requirement_id": "REQ-S15-P03",
        "contract_id": "AC-S15-P03",
        "evidence_id": "EVD-S15-P03",
        "evidence_index_id": "INDEX-AC-S15-P03",
        "evidence_path": "machine/evidence/EVD-S15-P03.json",
        "next": "S15/P04_READY_NOT_STARTED",
        "signed_required": True,
    },
    {
        "phase_id": "P04",
        "requirement_id": REQUIREMENT_ID,
        "contract_id": CONTRACT_ID,
        "evidence_id": "EVD-S15-P04",
        "evidence_index_id": "INDEX-AC-S15-P04",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
        "signed_required": False,
    },
)
CRITICAL_PHASE_IDS = tuple(item["phase_id"] for item in CRITICAL_PHASE_SPECS)

GATE_SCOPE = {
    "stage_id": STAGE_ID,
    "critical_phase_ids": list(CRITICAL_PHASE_IDS),
    "next_gate": "STAGE-REVIEW-S15",
    "future_stage_status": "NOT_EVALUATED_BY_S15_P04",
}
GATE_DEFINITIONS = (
    {
        "id": "GATE-S15-P04-CANONICAL-FACTS",
        "rule": "冻结机器事实哈希必须精确匹配。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
    {
        "id": "GATE-S15-P04-CHAIN-COMPLETE",
        "rule": "每个S15关键阶段必须有需求、合同、任务、测试、证据和制品链接。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
    {
        "id": "GATE-S15-P04-NO-ORPHANS",
        "rule": "S15关键节点不得孤儿、重复或脱离其合同。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
    {
        "id": "GATE-S15-P04-DAG-ACYCLIC",
        "rule": "全任务图依赖必须存在且无循环。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
    {
        "id": "GATE-S15-P04-PREDECESSOR-SIGNED",
        "rule": "P03必须是哈希固定且未声明外部生产动作的已签名前置证据。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
    {
        "id": "GATE-S15-P04-BOUNDARY-ONE-IN-TEN-THOUSAND",
        "rule": "P03的有利与不利万分之一冻结案例必须分别保持允许和拒绝动作。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
    {
        "id": "GATE-S15-P04-LOCAL-ONLY",
        "rule": "本门只接受无外部副作用的确定性本地重放。",
        "failure_action": "BLOCK_STAGE_REVIEW",
    },
)
GATE_IDS = tuple(item["id"] for item in GATE_DEFINITIONS)

BOUNDARY_SPEC = {
    "delta": "0.0001",
    "favourable_case_id": "S15-P03-GOLDEN-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
    "favourable_source_case_id": "S15-P02-ODDS-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
    "favourable_status": "E2E_GOLDEN_LOCAL_PASS_NO_EXTERNAL_ACTION",
    "adverse_case_id": "S15-P03-BLACK-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
    "adverse_source_case_id": "S15-P02-ODDS-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
    "adverse_status": "E2E_BLACK_REVOKED_NO_ORDER",
    "adverse_must_fail_closed": True,
}

EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "production_equivalent_config_schema_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "cloudflare_account_dns_or_tunnel_accessed": False,
    "database_connection_opened": False,
    "desktop_or_mobile_browser_exercised": False,
    "browser_component_installed_or_run": False,
    "tab_or_provider_runtime_accessed": False,
    "gmail_account_or_api_accessed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
BASELINE_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
NEGATIVE_MUTATION_IDS = (
    "MUT-S15-P04-UNKNOWN-GATE-FIELD",
    "MUT-S15-P04-ORPHAN-S15-TASK",
    "MUT-S15-P04-CYCLIC-TASK-GRAPH",
    "MUT-S15-P04-UNPASSED-CRITICAL-PREDECESSOR",
    "MUT-S15-P04-BOUNDARY-CASE-MISMATCH",
)


class TraceabilityGateError(ValueError):
    """Raised when a traceability gate input is not exact."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _closed_mapping(value: Any, fields: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise TraceabilityGateError("%s fields are not exact" % label)
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        raise TraceabilityGateError("JSONL file is missing: %s" % path)
    rows: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            raise TraceabilityGateError("blank JSONL row at %s:%s" % (path, number))
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceabilityGateError("invalid JSONL row at %s:%s" % (path, number)) from exc
        if not isinstance(value, dict):
            raise TraceabilityGateError("JSONL row must be object at %s:%s" % (path, number))
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise TraceabilityGateError("expected exactly one %s=%s row" % (key, identifier))
    return matches[0]


def _strict_row_map(rows: Sequence[Mapping[str, Any]], *, key: str) -> Dict[str, Mapping[str, Any]]:
    mapped: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        identifier = row.get(key)
        if not isinstance(identifier, str) or not identifier or identifier in mapped:
            raise TraceabilityGateError("rows must have unique nonempty %s" % key)
        mapped[identifier] = row
    return mapped


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.as_posix())
    return value


def _expected_gate_chain() -> List[Dict[str, Any]]:
    return [dict(item) for item in CRITICAL_PHASE_SPECS]


def validate_software_gate(document: Any) -> Mapping[str, Any]:
    fields = (
        "schema_version",
        "artifact_id",
        "gate_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "scope",
        "critical_chain",
        "gate_definitions",
        "boundary",
        "baseline_hashes",
        "execution_policy",
        "external_effect_boundary",
    )
    gate = _closed_mapping(document, fields, "software gate")
    valid = (
        gate["schema_version"] == "1.0.0"
        and gate["artifact_id"] == "ART-S15-P04-02"
        and gate["gate_id"] == "S15-P04-TRACEABILITY-SOFTWARE-GATE"
        and gate["contract_id"] == CONTRACT_ID
        and gate["requirement_id"] == REQUIREMENT_ID
        and gate["stage_id"] == STAGE_ID
        and gate["phase_id"] == PHASE_ID
        and gate["product_version"] == VERSION
        and gate["fixed_clock"] == FIXED_CLOCK
        and gate["scope"] == GATE_SCOPE
        and gate["critical_chain"] == _expected_gate_chain()
        and gate["gate_definitions"] == list(GATE_DEFINITIONS)
        and gate["boundary"] == BOUNDARY_SPEC
        and gate["baseline_hashes"] == BASELINE_HASHES
        and gate["execution_policy"] == EXECUTION_POLICY
        and gate["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise TraceabilityGateError("software gate content is not exact")
    return gate


def validate_fixture(document: Any) -> Mapping[str, Any]:
    fields = (
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "parameters_sha256",
        "predecessor",
        "execution_policy",
        "minimum_targeted_pytest_cases",
        "expected_critical_phase_ids",
        "expected_gate_ids",
        "expected_negative_mutation_ids",
        "expected_decision",
        "expected_next",
    )
    fixture = _closed_mapping(document, fields, "S15 P04 fixture")
    predecessor = {
        "contract_id": "AC-S15-P03",
        "evidence_path": P03_EVIDENCE_PATH.as_posix(),
        "evidence_sha256": P03_EVIDENCE_SHA256,
        "rollback_path": P03_ROLLBACK_PATH.as_posix(),
        "rollback_sha256": P03_ROLLBACK_SHA256,
        "next": "S15/P04_READY_NOT_STARTED",
    }
    valid = (
        fixture["schema_version"] == "1.0.0"
        and fixture["fixture_id"] == "FIX-S15-P04-TRACEABILITY-SOFTWARE-GATE"
        and fixture["contract_id"] == CONTRACT_ID
        and fixture["requirement_id"] == REQUIREMENT_ID
        and fixture["stage_id"] == STAGE_ID
        and fixture["phase_id"] == PHASE_ID
        and fixture["product_version"] == VERSION
        and fixture["fixed_clock"] == FIXED_CLOCK
        and fixture["parameters_sha256"] == BASELINE_HASHES[PARAMETERS_PATH.as_posix()]
        and fixture["predecessor"] == predecessor
        and fixture["execution_policy"] == EXECUTION_POLICY
        and fixture["minimum_targeted_pytest_cases"] == 18
        and fixture["expected_critical_phase_ids"] == list(CRITICAL_PHASE_IDS)
        and fixture["expected_gate_ids"] == list(GATE_IDS)
        and fixture["expected_negative_mutation_ids"] == list(NEGATIVE_MUTATION_IDS)
        and fixture["expected_decision"] == "S15_P04_TRACEABILITY_GATE_PASS_STAGE_REVIEW_REQUIRED"
        and fixture["expected_next"] == "S15/STAGE_REVIEW_READY_NOT_STARTED"
    )
    if not valid:
        raise TraceabilityGateError("S15 P04 fixture is not exact")
    return fixture


def _task_graph_topology(tasks: Sequence[Mapping[str, Any]]) -> Tuple[bool, List[str], List[str]]:
    try:
        mapped = _strict_row_map(tasks, key="id")
    except TraceabilityGateError as exc:
        return False, [], [str(exc)]
    indegree = {identifier: 0 for identifier in mapped}
    children: Dict[str, List[str]] = {identifier: [] for identifier in mapped}
    missing_dependencies: List[str] = []
    for identifier, task in mapped.items():
        dependencies = task.get("depends_on")
        if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
            missing_dependencies.append("%s:invalid-depends-on" % identifier)
            continue
        for dependency in dependencies:
            if dependency not in mapped:
                missing_dependencies.append("%s:%s" % (identifier, dependency))
                continue
            indegree[identifier] += 1
            children[dependency].append(identifier)
    if missing_dependencies:
        return False, [], sorted(missing_dependencies)
    ready = sorted(identifier for identifier, degree in indegree.items() if degree == 0)
    ordered: List[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    cycles = sorted(identifier for identifier, degree in indegree.items() if degree > 0)
    return len(ordered) == len(mapped), ordered, cycles


def _index_phase_status(
    evidence_index: Sequence[Mapping[str, Any]], spec: Mapping[str, Any]
) -> Tuple[bool, str]:
    try:
        row = _row(evidence_index, str(spec["evidence_index_id"]))
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    if spec["signed_required"]:
        valid = (
            row.get("kind") == "PHASE_EVIDENCE"
            and row.get("stage_id") == STAGE_ID
            and row.get("contract_id") == spec["contract_id"]
            and row.get("requirement_id") == spec["requirement_id"]
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == spec["evidence_path"]
            and isinstance(row.get("artifact_sha256"), str)
            and len(str(row.get("artifact_sha256"))) == 64
            and row.get("next") == spec["next"]
        )
        return valid, "SIGNED_PASS" if valid else "SIGNED_RECEIPT_MISMATCH"
    planned = (
        row.get("kind") == "ACCEPTANCE_EVIDENCE"
        and row.get("acceptance_contract_id") == CONTRACT_ID
        and row.get("requirement_id") == REQUIREMENT_ID
        and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
        and row.get("pass_gate") == "无孤儿、无循环、无未通过关键验收。"
        and row.get("status") == "PLANNED"
    )
    signed = (
        row.get("kind") == "PHASE_EVIDENCE"
        and row.get("stage_id") == STAGE_ID
        and row.get("contract_id") == CONTRACT_ID
        and row.get("requirement_id") == REQUIREMENT_ID
        and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and isinstance(row.get("artifact_sha256"), str)
        and len(str(row.get("artifact_sha256"))) == 64
        and row.get("next") == "S15/STAGE_REVIEW_READY_NOT_STARTED"
        and row.get("status") == "PASS"
    )
    return planned or signed, "PLANNED_CANDIDATE" if planned else "SIGNED_PASS" if signed else "P04_INDEX_MISMATCH"


def evaluate_traceability_graph(
    requirements: Any,
    contracts: Any,
    graph: Any,
    traceability: Any,
    evidence_index: Any,
    gate: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate the S15 requirement-to-evidence graph without external state."""

    checks: List[Dict[str, Any]] = []
    try:
        validate_software_gate(gate)
        if not all(isinstance(value, list) for value in (requirements, contracts, traceability, evidence_index)):
            raise TraceabilityGateError("requirements, contracts, traceability, and evidence index must be lists")
        if not isinstance(graph, Mapping) or not isinstance(graph.get("tasks"), list):
            raise TraceabilityGateError("task graph tasks are unavailable")
        requirement_rows = [row for row in requirements if isinstance(row, Mapping)]
        contract_rows = [row for row in contracts if isinstance(row, Mapping)]
        trace_rows = [row for row in traceability if isinstance(row, Mapping)]
        index_rows = [row for row in evidence_index if isinstance(row, Mapping)]
        task_rows = [row for row in graph["tasks"] if isinstance(row, Mapping)]
        if len(requirement_rows) != len(requirements) or len(contract_rows) != len(contracts) or len(trace_rows) != len(traceability) or len(index_rows) != len(evidence_index) or len(task_rows) != len(graph["tasks"]):
            raise TraceabilityGateError("graph inputs contain non-object rows")
        requirement_by_id = _strict_row_map(requirement_rows, key="id")
        contract_by_id = _strict_row_map(contract_rows, key="id")
        trace_by_requirement = _strict_row_map(trace_rows, key="requirement_id")
        task_by_id = _strict_row_map(task_rows, key="id")
        _strict_row_map(index_rows, key="id")
    except Exception as exc:
        _add(checks, "S15P04-GRAPH-INPUTS-STRUCTURED", False, "%s: %s" % (type(exc).__name__, exc))
        return _trace_result(checks, orphan_count=1, cycle_count=1, unpassed_count=1)

    _add(checks, "S15P04-GRAPH-INPUTS-STRUCTURED", True, {"tasks": len(task_rows), "requirements": len(requirement_rows)})
    acyclic, ordered, topology_failures = _task_graph_topology(task_rows)
    _add(
        checks,
        "S15P04-TASK-GRAPH-DEPENDENCIES-EXIST-AND-ACYCLIC",
        acyclic,
        {"ordered_task_count": len(ordered), "topology_failures": topology_failures},
    )

    expected_requirement_ids = {str(item["requirement_id"]) for item in CRITICAL_PHASE_SPECS}
    expected_contract_ids = {str(item["contract_id"]) for item in CRITICAL_PHASE_SPECS}
    expected_trace_ids = expected_requirement_ids
    expected_task_ids: set[str] = set()
    expected_test_ids: set[str] = set()
    phase_failures: List[str] = []
    for spec in CRITICAL_PHASE_SPECS:
        phase_id = str(spec["phase_id"])
        requirement_id = str(spec["requirement_id"])
        contract_id = str(spec["contract_id"])
        try:
            requirement = requirement_by_id[requirement_id]
            contract = contract_by_id[contract_id]
            trace = trace_by_requirement[requirement_id]
            task_ids = trace.get("task_ids")
            test_ids = trace.get("test_ids")
            if not isinstance(task_ids, list) or not isinstance(test_ids, list):
                raise TraceabilityGateError("trace task_ids/test_ids unavailable")
            phase_tasks = [
                task
                for task in task_rows
                if task.get("stage_id") == STAGE_ID and task.get("phase_id") == phase_id
            ]
            observed_task_ids = [task.get("id") for task in phase_tasks]
            valid = (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase_id
                and requirement.get("primary_acceptance_criteria_id") == contract_id
                and contract.get("requirement_id") == requirement_id
                and contract.get("pass_gate") == requirement.get("target")
                and trace.get("stage_id") == STAGE_ID
                and trace.get("phase_id") == phase_id
                and trace.get("acceptance_criteria_id") == contract_id
                and list(task_ids) == observed_task_ids
                and [item.get("id") for item in contract.get("tests", []) if isinstance(item, Mapping)] == list(test_ids)
                and all(
                    task.get("requirement_ids") == [requirement_id]
                    and task.get("acceptance_criteria_ids") == [contract_id]
                    for task in phase_tasks
                )
            )
            if phase_id == PHASE_ID:
                valid = (
                    valid
                    and list(task_ids) == list(EXPECTED_TASK_IDS)
                    and list(test_ids) == list(EXPECTED_TEST_IDS)
                    and trace.get("evidence_id") == "EVD-S15-P04"
                    and trace.get("artifact_ids") == list(EXPECTED_ARTIFACTS)
                    and {task_id: task_by_id[task_id].get("outputs") for task_id in EXPECTED_TASK_IDS} == EXPECTED_TASK_OUTPUTS
                )
            expected_task_ids.update(str(task_id) for task_id in task_ids)
            expected_test_ids.update(str(test_id) for test_id in test_ids)
            _add(checks, "S15P04-CHAIN-%s-COMPLETE" % phase_id, valid, {"tasks": observed_task_ids, "tests": test_ids})
            if not valid:
                phase_failures.append(phase_id)
        except Exception as exc:
            _add(checks, "S15P04-CHAIN-%s-COMPLETE" % phase_id, False, "%s: %s" % (type(exc).__name__, exc))
            phase_failures.append(phase_id)

    actual_requirement_ids = {str(row.get("id")) for row in requirement_rows if row.get("stage_id") == STAGE_ID}
    actual_contract_ids = {str(row.get("id")) for row in contract_rows if row.get("id") in expected_contract_ids}
    actual_trace_ids = {str(row.get("requirement_id")) for row in trace_rows if row.get("stage_id") == STAGE_ID}
    actual_task_ids = {str(task.get("id")) for task in task_rows if task.get("stage_id") == STAGE_ID}
    orphan_sets = {
        "requirements": sorted(actual_requirement_ids.symmetric_difference(expected_requirement_ids)),
        "contracts": sorted(actual_contract_ids.symmetric_difference(expected_contract_ids)),
        "traceability": sorted(actual_trace_ids.symmetric_difference(expected_trace_ids)),
        "tasks": sorted(actual_task_ids.symmetric_difference(expected_task_ids)),
        "tests": sorted(expected_test_ids.difference({str(item.get("id")) for contract in contract_rows for item in contract.get("tests", []) if isinstance(item, Mapping)})),
    }
    orphan_count = sum(len(value) for value in orphan_sets.values())
    _add(checks, "S15P04-NO-ORPHAN-OR-DUPLICATE-S15-CRITICAL-NODES", orphan_count == 0 and not phase_failures, {"orphans": orphan_sets, "phase_failures": phase_failures})

    unpassed: List[str] = []
    for spec in CRITICAL_PHASE_SPECS:
        passed, status = _index_phase_status(index_rows, spec)
        phase_id = str(spec["phase_id"])
        _add(checks, "S15P04-INDEX-%s-VALID" % phase_id, passed, status)
        if not passed:
            unpassed.append(phase_id)
    _add(checks, "S15P04-NO-UNPASSED-CRITICAL-ACCEPTANCE", not unpassed, unpassed)
    return _trace_result(checks, orphan_count=orphan_count + len(phase_failures), cycle_count=0 if acyclic else max(1, len(topology_failures)), unpassed_count=len(unpassed))


def _trace_result(checks: List[Dict[str, Any]], *, orphan_count: int, cycle_count: int, unpassed_count: int) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    return {
        "status": "PASS" if not failed else "FAIL",
        "summary": {
            "checks": len(checks),
            "passed": sum(item["passed"] for item in checks),
            "failed": len(failed),
            "failed_check_ids": failed,
            "orphan_count": orphan_count,
            "cycle_count": cycle_count,
            "unpassed_critical_acceptance_count": unpassed_count,
        },
        "checks": checks,
    }


def validate_boundary_documents(gate: Mapping[str, Any], e2e_tests: Any, e2e_evidence: Any) -> Mapping[str, Any]:
    validate_software_gate(gate)
    if not isinstance(e2e_tests, Mapping) or not isinstance(e2e_evidence, Mapping):
        raise TraceabilityGateError("P03 boundary documents must be objects")
    scenarios = e2e_tests.get("scenarios")
    outcomes = e2e_evidence.get("expected_outcomes")
    if not isinstance(scenarios, list) or not isinstance(outcomes, list):
        raise TraceabilityGateError("P03 boundary scenarios are unavailable")
    scenario_by_id = _strict_row_map([item for item in scenarios if isinstance(item, Mapping)], key="case_id")
    outcome_by_id = _strict_row_map([item for item in outcomes if isinstance(item, Mapping)], key="case_id")
    favourable = scenario_by_id.get(BOUNDARY_SPEC["favourable_case_id"])
    adverse = scenario_by_id.get(BOUNDARY_SPEC["adverse_case_id"])
    favourable_outcome = outcome_by_id.get(BOUNDARY_SPEC["favourable_case_id"])
    adverse_outcome = outcome_by_id.get(BOUNDARY_SPEC["adverse_case_id"])
    valid = (
        favourable is not None
        and adverse is not None
        and favourable_outcome is not None
        and adverse_outcome is not None
        and favourable.get("source_replay_case_id") == BOUNDARY_SPEC["favourable_source_case_id"]
        and favourable.get("journey_class") == "GOLDEN"
        and favourable.get("expected", {}).get("status") == BOUNDARY_SPEC["favourable_status"]
        and favourable_outcome.get("status") == BOUNDARY_SPEC["favourable_status"]
        and adverse.get("source_replay_case_id") == BOUNDARY_SPEC["adverse_source_case_id"]
        and adverse.get("journey_class") == "BLACK"
        and adverse.get("expected", {}).get("status") == BOUNDARY_SPEC["adverse_status"]
        and adverse_outcome.get("status") == BOUNDARY_SPEC["adverse_status"]
    )
    if not valid:
        raise TraceabilityGateError("one-in-ten-thousand boundary chain is not exact")
    return {
        "delta": BOUNDARY_SPEC["delta"],
        "favourable_case_id": BOUNDARY_SPEC["favourable_case_id"],
        "adverse_case_id": BOUNDARY_SPEC["adverse_case_id"],
        "adverse_must_fail_closed": True,
    }


def validate_signed_p03_receipt(root: Path) -> Mapping[str, Any]:
    root = root.resolve()
    evidence_hash = sha256_file(root / P03_EVIDENCE_PATH) if (root / P03_EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / P03_ROLLBACK_PATH) if (root / P03_ROLLBACK_PATH).is_file() else "MISSING"
    if evidence_hash != P03_EVIDENCE_SHA256 or rollback_hash != P03_ROLLBACK_SHA256:
        raise TraceabilityGateError("P03 signed receipt hashes differ")
    evidence = strict_json_load(root / P03_EVIDENCE_PATH)
    rollback = strict_json_load(root / P03_ROLLBACK_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise TraceabilityGateError("P03 signed receipt is not structured")
    p03_boundary = {
        "local_multi_surface_contract_replayed": True,
        "actual_ovh_host_exercised": False,
        "actual_cloudflare_edge_exercised": False,
        "actual_desktop_or_mobile_browser_exercised": False,
        "actual_browser_component_installed": False,
        "actual_network_outage_exercised": False,
        "external_network_accessed": False,
    }
    valid = (
        evidence.get("contract_id") == "AC-S15-P03"
        and evidence.get("status") == "PASS"
        and evidence.get("next") == "S15/P04_READY_NOT_STARTED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("claim_boundary") == p03_boundary
        and evidence.get("external_effect_boundary", {}).get("external_network_accessed") is False
        and evidence.get("external_effect_boundary", {}).get("production_deployed_or_activated") is False
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and rollback.get("contract_id") == "AC-S15-P03"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
    )
    if not valid:
        raise TraceabilityGateError("P03 signed receipt semantics differ")
    return evidence


def _check_taskpack(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S15P04-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S15P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S15P04-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S15P04-TASKS-STRICT-JSON")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S15P04-TRACEABILITY-STRICT-JSON")
    gate = _safe_load(root, SOFTWARE_GATE_PATH, checks, "S15P04-SOFTWARE-GATE-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S15P04-FIXTURE-STRICT-JSON")
    try:
        evidence_index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S15P04-EVIDENCE-INDEX-STRICT-JSONL", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        evidence_index = []
        _add(checks, "S15P04-EVIDENCE-INDEX-STRICT-JSONL", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        validate_software_gate(gate)
        hashes[SOFTWARE_GATE_PATH.as_posix()] = sha256_file(root / SOFTWARE_GATE_PATH)
        _add(checks, "S15P04-SOFTWARE-GATE-EXACT", True, SOFTWARE_GATE_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P04-SOFTWARE-GATE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        validate_fixture(fixture)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        _add(checks, "S15P04-FIXTURE-EXACT", True, FIXTURE_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P04-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        rows = graph.get("tasks") if isinstance(graph, Mapping) else None
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [row for row in rows if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID] if isinstance(rows, list) else []
        outputs = {row.get("id"): row.get("outputs") for row in tasks}
        valid = (
            requirement.get("scope") == ["traceability_validator.py", "software_gate.json"]
            and requirement.get("target") == "无孤儿、无循环、无未通过关键验收。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S15-P04 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in tasks] == list(EXPECTED_TASK_IDS)
            and outputs == EXPECTED_TASK_OUTPUTS
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S15-P04"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACTS)
        )
    except Exception as exc:
        valid = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S15P04-TASKPACK-SCOPE-TRACE-EXACT", valid, requirement if not valid else list(EXPECTED_TASK_IDS))
    graph_result = evaluate_traceability_graph(requirements, contracts, graph, traceability, evidence_index, gate) if isinstance(gate, Mapping) else _trace_result([], orphan_count=1, cycle_count=1, unpassed_count=1)
    for check in graph_result["checks"]:
        _add(checks, str(check["id"]), bool(check["passed"]), check["detail"])
    return gate if isinstance(gate, Mapping) else None, fixture if isinstance(fixture, Mapping) else None


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence_hash = sha256_file(root / P03_EVIDENCE_PATH) if (root / P03_EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / P03_ROLLBACK_PATH) if (root / P03_ROLLBACK_PATH).is_file() else "MISSING"
    hashes[P03_EVIDENCE_PATH.as_posix()] = evidence_hash
    hashes[P03_ROLLBACK_PATH.as_posix()] = rollback_hash
    try:
        receipt = validate_signed_p03_receipt(root)
        valid = receipt.get("status") == "PASS" and evidence_hash == P03_EVIDENCE_SHA256 and rollback_hash == P03_ROLLBACK_SHA256
    except Exception as exc:
        valid = False
        receipt = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S15P04-P03-SIGNED-PREDECESSOR-EXACT", valid, receipt if not valid else P03_EVIDENCE_SHA256)


def _check_boundary(root: Path, gate: Mapping[str, Any] | None, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    if gate is None:
        _add(checks, "S15P04-ONE-IN-TEN-THOUSAND-BOUNDARY-CHAIN", False, "software gate unavailable")
        return
    e2e_tests = _safe_load(root, P03_E2E_TESTS_PATH, checks, "S15P04-P03-E2E-TESTS-STRICT-JSON")
    e2e_evidence = _safe_load(root, P03_E2E_EVIDENCE_PATH, checks, "S15P04-P03-E2E-EVIDENCE-STRICT-JSON")
    try:
        outcome = validate_boundary_documents(gate, e2e_tests, e2e_evidence)
        hashes[P03_E2E_TESTS_PATH.as_posix()] = sha256_file(root / P03_E2E_TESTS_PATH)
        hashes[P03_E2E_EVIDENCE_PATH.as_posix()] = sha256_file(root / P03_E2E_EVIDENCE_PATH)
        _add(checks, "S15P04-ONE-IN-TEN-THOUSAND-BOUNDARY-CHAIN", True, outcome)
    except Exception as exc:
        _add(checks, "S15P04-ONE-IN-TEN-THOUSAND-BOUNDARY-CHAIN", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"}
        forbidden_tokens = ("slee" "p(", "submit" "_order", "retry" "_order", "http" "://", "https" "://")
        passed = not imports.intersection(forbidden) and all(token not in source for token in forbidden_tokens)
        _add(checks, "S15P04-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", passed, {"imports": sorted(imports), "forbidden": sorted(imports.intersection(forbidden))})
    except Exception as exc:
        _add(checks, "S15P04-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
    if not suites:
        raise TraceabilityGateError("JUnit has no testsuite")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    normalized = True
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
        normalized = normalized and suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000"
        normalized = normalized and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S15P04-TARGETED-REPORTS-REQUIRED", True, "preflight mode")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        passed = isinstance(minimum, int) and summary["tests"] >= minimum and not summary["failures"] and not summary["errors"] and not summary["skipped"] and normalized
        _add(checks, "S15P04-TARGETED-PYTEST-REPORT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S15P04-TARGETED-PYTEST-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S15P04-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P04-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S15P04-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S15P04-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S15_P04_TRACEABILITY_GATE_PASS_STAGE_REVIEW_REQUIRED" if passed else "S15/P04_BLOCKED",
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED" if passed else "S15/P04_REMEDIATION_REQUIRED",
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
    gate, fixture = _check_taskpack(root, checks, hashes)
    _check_predecessor(root, checks, hashes)
    _check_boundary(root, gate, checks, hashes)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = [ORACLE_PATH, CLI_PROXY_PATH, SOFTWARE_GATE_PATH, TEST_PATH, FIXTURE_PATH, P03_EVIDENCE_PATH, P03_ROLLBACK_PATH]
    artifacts = {
        path.as_posix(): {
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
            "status": "PASS" if (root / path).is_file() else "FAIL",
        }
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S15_P04_TRACEABILITY_GATE_KEEP_SIGNED_S15_P03",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "database_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "actual_return_claimed": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        ORACLE_PATH,
        CLI_PROXY_PATH,
        SOFTWARE_GATE_PATH,
        TEST_PATH,
        FIXTURE_PATH,
        P03_EVIDENCE_PATH,
        P03_ROLLBACK_PATH,
        P03_E2E_TESTS_PATH,
        P03_E2E_EVIDENCE_PATH,
        *[Path(relative) for relative in BASELINE_HASHES],
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _canonical_sha256(
        {
            "contract_id": evidence.get("contract_id"),
            "decision": evidence.get("decision"),
            "next": evidence.get("next"),
            "status": evidence.get("status"),
            "validation": evidence.get("validation"),
        }
    )


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P04",
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
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "traceability_gate": {
            "critical_phase_ids": list(CRITICAL_PHASE_IDS),
            "gate_ids": list(GATE_IDS),
            "predecessor_validation_mode": "PINNED_RECEIPT_AND_INDEX_ONLY_NO_REEXECUTION",
            "boundary_delta": BOUNDARY_SPEC["delta"],
            "future_stage_status": GATE_SCOPE["future_stage_status"],
        },
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S15_PHASES_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED",
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S15/P04_test.py --junitxml=machine/evidence/S15/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S15/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S15/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S15-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {
            "critical_phase_count": len(CRITICAL_PHASE_IDS),
            "gate_count": len(GATE_IDS),
            "boundary_delta": BOUNDARY_SPEC["delta"],
            "actual_network_or_device_execution_performed": False,
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
    if len(raw_lines) != len(rows):
        raise TraceabilityGateError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise TraceabilityGateError("S15/P04 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise TraceabilityGateError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise TraceabilityGateError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise TraceabilityGateError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    try:
        index_row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    except Exception as exc:
        raise TraceabilityGateError("existing P04 evidence index is unavailable") from exc
    expected_traceability_gate = {
        "critical_phase_ids": list(CRITICAL_PHASE_IDS),
        "gate_ids": list(GATE_IDS),
        "predecessor_validation_mode": "PINNED_RECEIPT_AND_INDEX_ONLY_NO_REEXECUTION",
        "boundary_delta": BOUNDARY_SPEC["delta"],
        "future_stage_status": GATE_SCOPE["future_stage_status"],
    }
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S15_P04_TRACEABILITY_GATE_PASS_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S15/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("traceability_gate") == expected_traceability_gate
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("database_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("actual_return_claimed") is False
        and index_row.get("kind") == "PHASE_EVIDENCE"
        and index_row.get("status") == "PASS"
        and index_row.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index_row.get("next") == "S15/STAGE_REVIEW_READY_NOT_STARTED"
    )
    if not valid:
        raise TraceabilityGateError("existing S15/P04 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
    }


__all__ = [
    "BOUNDARY_SPEC",
    "CONTRACT_ID",
    "CRITICAL_PHASE_IDS",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXPECTED_ARTIFACTS",
    "EXPECTED_TASK_IDS",
    "EXPECTED_TEST_IDS",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "GATE_IDS",
    "NEGATIVE_MUTATION_IDS",
    "ORACLE_PATH",
    "SOFTWARE_GATE_PATH",
    "TEST_PATH",
    "TraceabilityGateError",
    "evaluate_contract",
    "evaluate_traceability_graph",
    "perform_rollback_drill",
    "validate_boundary_documents",
    "validate_candidate_preflight",
    "validate_fixture",
    "validate_signed_p03_receipt",
    "validate_software_gate",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
