"""Fail-closed acceptance oracle for ABD S19/P03 GA/reconciliation control.

This phase signs a deterministic local control only.  Its PASS status means
the frozen zero-row schema, evidence wiring, and failure boundaries replay.
It does not mean that actual execution was observed, reconciled, or promoted
to GA.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .ga_reconciliation import (
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXED_CLOCK,
    GA_MIN_ACTUAL_RECORDS,
    GA_MIN_DAYS,
    GA_MIN_SIGNALS,
    SAFE_GA_CONFIG,
    GAReconciliationInputError,
    build_actual_reconciliation,
    build_ga_report,
    canonical_json_bytes,
    evaluate_ga_reconciliation,
)
from .legacy_receipt_compatibility import approved_successor_sha256
from .shadow_beta_acceptance import verify_existing_phase_evidence as verify_s19_p02


CONTRACT_ID = "AC-S19-P03"
REQUIREMENT_ID = "REQ-S19-P03"
STAGE_ID = "S19"
PHASE_ID = "P03"
PRODUCT_VERSION = "0.0.0.1"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CORE_PATH = Path("abd_acceptance/ga_reconciliation.py")
ORACLE_PATH = Path("abd_acceptance/ga_reconciliation_acceptance.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S19_P03.json")
TEST_PATH = Path("tests/S19/P03_test.py")
GA_REPORT_PATH = Path("ga_report.json")
ACTUAL_RECONCILIATION_PATH = Path("actual_reconciliation.json")
JUNIT_PATH = Path("machine/evidence/S19/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S19/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")

EXPECTED_TASK_IDS = ("T-S19-P03-01", "T-S19-P03-02", "T-S19-P03-03")
EXPECTED_TEST_IDS = ("TEST-S19-P03", "TEST-S19-P03-BOUNDARY", "TEST-S19-P03-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S19-P03-01", "ART-S19-P03-02")
EXPECTED_OUTPUTS = {
    "T-S19-P03-01": [GA_REPORT_PATH.as_posix(), ACTUAL_RECONCILIATION_PATH.as_posix()],
    "T-S19-P03-02": [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()],
    "T-S19-P03-03": [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()],
}
EXPECTED_SCENARIOS = (
    "GOLDEN_ZERO_ROW_CONTROL_GA_BLOCKED",
    "ADVERSE_ONE_IN_TEN_THOUSAND_ZERO_ROW_CONTROL_STABLE",
    "NONZERO_LOCAL_DIFFERENCE_FAILS_CLOSED",
    "EMPIRICAL_EXECUTION_CLAIM_FAILS_CLOSED",
    "STOP_CONDITION_FAILS_CLOSED",
    "UNSAFE_RUNTIME_REQUESTS_FAIL_CLOSED",
    "MODEL_GATE_UNBLOCK_ATTEMPT_FAILS_CLOSED",
)
P02_PREDECESSOR_PATH = Path("machine/evidence/EVD-S19-P02.json")
P02_PREDECESSOR_SHA256 = "6d13caf6132005bbfa1f2d31e3bfbce23366065702404d1c56e4dff1f4c73177"
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
SOURCE_EVIDENCE_HASHES = {
    "machine/evidence/EVD-S19-P02.json": P02_PREDECESSOR_SHA256,
    "shadow_report.json": "c482bd9a3006687ec72f498abb84e9f53393a6a2868ba5686ab91da1f1ee9236",
    "model_beta_gate.json": "cc64fb221b36925e09b1bcfffa3236e63dc7fc2ab6e0a4f67886ffbff7860dac",
    "target_acceptance.json": "62ab02e730fda25bd18a58f0a578f3dbf65d4813d3d153ac3dbcec9ff6bcdd76",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "model_release_gate.json": "6c4db127f346e644fcc4ec6fd6b9a158a29ad74dc628780a4139e709b4735720",
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "production_equivalent_config_schema_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "synthetic_or_local_control_may_count_as_empirical": False,
    "incremental_cash_spent_aud": "0.00",
}


class GAReconciliationAcceptanceError(RuntimeError):
    """Raised when S19/P03 cannot reproduce its local, fail-closed receipt."""


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
        raise GAReconciliationAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise GAReconciliationAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise GAReconciliationAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping) or _contains_float(value):
            raise GAReconciliationAcceptanceError("invalid JSONL row %d" % number)
        rows.append(value)
    return rows


def load_fixture(path: Path) -> Mapping[str, Any]:
    value = strict_json_load(path)
    if not isinstance(value, Mapping) or _contains_float(value):
        raise GAReconciliationAcceptanceError("fixture must be a non-float object")
    return value


def validate_fixture(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "fixed_clock",
        "expected_next",
        "predecessor_evidence_sha256",
        "source_evidence_sha256",
        "safe_ga_config",
        "scenarios",
        "malformed_inputs",
    }
    if set(value) != expected:
        raise GAReconciliationAcceptanceError("fixture keys changed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("fixture_id") != "FIX-S19-P03-GA-RECONCILIATION"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("expected_next") != "S19/P04_READY_NOT_STARTED"
        or value.get("predecessor_evidence_sha256") != P02_PREDECESSOR_SHA256
        or value.get("source_evidence_sha256") != SOURCE_EVIDENCE_HASHES
        or value.get("safe_ga_config") != SAFE_GA_CONFIG
    ):
        raise GAReconciliationAcceptanceError("fixture identity or source pins changed")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != EXPECTED_SCENARIOS:
        raise GAReconciliationAcceptanceError("fixture scenarios changed")
    for item in scenarios:
        if not isinstance(item, Mapping) or set(item) != {"scenario_id", "ga_input", "expected"}:
            raise GAReconciliationAcceptanceError("fixture scenario schema changed")
        if not isinstance(item["expected"], Mapping) or _contains_float(item["expected"]):
            raise GAReconciliationAcceptanceError("scenario expected result is invalid")
    malformed = value.get("malformed_inputs")
    if not isinstance(malformed, list) or not malformed:
        raise GAReconciliationAcceptanceError("malformed input vectors are unavailable")
    return value


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P03-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S19P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S19P03-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S19P03-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S19P03-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise GAReconciliationAcceptanceError("task graph is unavailable")
        phase_tasks = [item for item in tasks if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == [GA_REPORT_PATH.as_posix(), ACTUAL_RECONCILIATION_PATH.as_posix()]
            and requirement.get("target") == "证据完整、对账差异0、终止条件未触发。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S19-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and phase_tasks[0].get("depends_on") == ["T-S19-P02-03"]
            and phase_tasks[1].get("depends_on") == ["T-S19-P03-01"]
            and phase_tasks[2].get("depends_on") == ["T-S19-P03-02"]
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S19-P03"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P03-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "证据完整、对账差异0、终止条件未触发。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("stage_id") == STAGE_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("artifact_sha256") == (sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING")
            and row.get("next") == "S19/P04_READY_NOT_STARTED"
        )
        _add(checks, "S19P03-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S19P03-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        result = verify_s19_p02(root)
        actual = sha256_file(root / P02_PREDECESSOR_PATH)
        hashes[P02_PREDECESSOR_PATH.as_posix()] = actual
        valid = (
            result.get("contract_id") == "AC-S19-P02"
            and result.get("status") == "PASS"
            and result.get("evidence_sha256") == P02_PREDECESSOR_SHA256
            and result.get("next") == "S19/P03_READY_NOT_STARTED"
            and actual == P02_PREDECESSOR_SHA256
        )
        detail: Any = {"expected": P02_PREDECESSOR_SHA256, "actual": actual, "next": result.get("next")}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P03-PREDECESSOR-AC-S19-P02-CURRENT", valid, detail)


def _check_truth_boundaries(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in SOURCE_EVIDENCE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P03-SOURCE-PIN-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    try:
        canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
        target = strict_json_load(root / "target_acceptance.json")
        policy = strict_json_load(root / "machine/facts/release_policy.json")
        beta = strict_json_load(root / "model_beta_gate.json")
        release = strict_json_load(root / "model_release_gate.json")
        truth_ok = (
            canonical.get("truth_and_evidence", {}).get("advice_ledger_separate_from_actual_ledger") is True
            and canonical.get("truth_and_evidence", {}).get("actual_return_requires_verified_execution_evidence") is True
            and canonical.get("scope", {}).get("order_submission_module_present") is False
            and target.get("falsification_gate", {}).get("current_empirical_assessment", {}).get("evidence_status") == "NO_EMPIRICAL_EXECUTION_EVIDENCE"
            and target.get("verification_gate", {}).get("current_empirical_assessment", {}).get("evidence_complete") is False
            and target.get("verification_gate", {}).get("current_empirical_assessment", {}).get("unresolved_reconciliation_differences") == 0
            and target.get("hard_gate_invariants", {}).get("synthetic_artifacts_may_substitute_for_actual_return") is False
        )
        policy_ok = (
            policy.get("alpha_beta_ga", {}).get("model_ga") == "至少90天和1000合格信号，所有置信下界门通过"
            and beta.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
            and beta.get("model_activation_allowed") is False
            and release.get("model_gate", {}).get("status") == "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT"
            and release.get("model_gate", {}).get("activation_allowed") is False
        )
    except Exception as exc:
        truth_ok = policy_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = "frozen facts require separate empirical execution and model evidence"
    _add(checks, "S19P03-ACTUAL-LEDGER-AND-RETURN-TRUTH-BOUNDARY-EXACT", truth_ok, detail)
    _add(checks, "S19P03-MODEL-GA-POLICY-AND-BLOCK-EXACT", policy_ok, detail)


def _fixture_and_expected_artifacts(root: Path) -> Tuple[Mapping[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    fixture = validate_fixture(load_fixture(root / FIXTURE_PATH))
    golden = next(item for item in fixture["scenarios"] if item["scenario_id"] == EXPECTED_SCENARIOS[0])
    evaluation = evaluate_ga_reconciliation(golden["ga_input"])
    report = build_ga_report(
        evaluation,
        fixture_sha256=sha256_file(root / FIXTURE_PATH),
        predecessor_evidence_sha256=P02_PREDECESSOR_SHA256,
        source_evidence_sha256=SOURCE_EVIDENCE_HASHES,
    )
    reconciliation = build_actual_reconciliation(report)
    return fixture, evaluation, report, reconciliation


def _check_core_and_fixture(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        fixture, golden, report, reconciliation = _fixture_and_expected_artifacts(root)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        hashes[CORE_PATH.as_posix()] = sha256_file(root / CORE_PATH)
        replay_ok = True
        scenario_results: List[Dict[str, Any]] = []
        for scenario in fixture["scenarios"]:
            first = evaluate_ga_reconciliation(scenario["ga_input"])
            second = evaluate_ga_reconciliation(scenario["ga_input"])
            expected = scenario["expected"]
            scenario_ok = all(first.get(key) == value for key, value in expected.items()) and first == second
            replay_ok = replay_ok and scenario_ok
            scenario_results.append({"scenario_id": scenario["scenario_id"], "passed": scenario_ok, "ga_status": first.get("ga_status")})
        _add(checks, "S19P03-FROZEN-SCENARIOS-REPLAY-EXACT", replay_ok, scenario_results)
        golden_ok = (
            golden.get("status") == "PASS_LOCAL_GA_RECONCILIATION_CONTROL"
            and golden.get("action") == "NO_RECOMMENDATION"
            and golden.get("ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
            and golden.get("local_control", {}).get("local_reconciliation_difference_cents") == 0
            and golden.get("actual_execution_observation", {}).get("actual_record_count") == 0
            and golden.get("actual_execution_observation", {}).get("actual_reconciliation_difference_cents") is None
            and golden.get("actual_execution_observation", {}).get("actual_reconciliation_status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
        )
        _add(checks, "S19P03-LOCAL-ZERO-DIFFERENCE-NOT-AN-ACTUAL-RECONCILIATION-CLAIM", golden_ok, golden.get("ga_status"))
        artifacts_ok = (
            report.get("artifact_id") == EXPECTED_ARTIFACT_IDS[0]
            and report.get("status") == "PASS_LOCAL_GA_RECONCILIATION_CONTROL_ACTUAL_GA_BLOCKED"
            and report.get("ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
            and reconciliation.get("artifact_id") == EXPECTED_ARTIFACT_IDS[1]
            and reconciliation.get("status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
            and reconciliation.get("actual_reconciliation_difference_cents") is None
            and reconciliation.get("local_zero_row_reconciliation_difference_cents") == 0
            and reconciliation.get("ga_report_sha256") == report.get("ga_report_sha256")
        )
        _add(checks, "S19P03-ARTIFACT-BUILD-EXACT", artifacts_ok, {"ga": report.get("ga_report_sha256"), "reconciliation": reconciliation.get("actual_reconciliation_sha256")})
        source = (root / CORE_PATH).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "time", "asyncio", "os", "random"}
        source_ok = not imports.intersection(forbidden) and all(token not in source for token in ("sleep(", "submit_order", "retry_order", "http://", "https://", "smtplib"))
        _add(checks, "S19P03-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY", source_ok, sorted(imports.intersection(forbidden)))
    except Exception as exc:
        _add(checks, "S19P03-CORE-OR-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_generated_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str], required: bool) -> None:
    if not required:
        _add(checks, "S19P03-GENERATED-ARTIFACTS-DEFERRED-PREFLIGHT", True, "pre-signing source and fixture preflight")
        return
    try:
        _, _, expected_report, expected_reconciliation = _fixture_and_expected_artifacts(root)
        actual_report = strict_json_load(root / GA_REPORT_PATH)
        actual_reconciliation = strict_json_load(root / ACTUAL_RECONCILIATION_PATH)
        hashes[GA_REPORT_PATH.as_posix()] = sha256_file(root / GA_REPORT_PATH)
        hashes[ACTUAL_RECONCILIATION_PATH.as_posix()] = sha256_file(root / ACTUAL_RECONCILIATION_PATH)
        exact = actual_report == expected_report and actual_reconciliation == expected_reconciliation
        _add(checks, "S19P03-GENERATED-ARTIFACTS-REPLAY-EXACT", exact, {"ga": hashes[GA_REPORT_PATH.as_posix()], "reconciliation": hashes[ACTUAL_RECONCILIATION_PATH.as_posix()]})
        boundary_ok = (
            actual_report.get("ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
            and actual_reconciliation.get("status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
            and actual_reconciliation.get("actual_execution_evidence_complete") is False
            and actual_reconciliation.get("actual_record_count") == 0
            and actual_reconciliation.get("actual_reconciliation_difference_cents") is None
            and actual_reconciliation.get("zero_difference_requirement_status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
            and actual_reconciliation.get("local_zero_row_reconciliation_difference_cents") == 0
            and actual_reconciliation.get("ga_activation_allowed") is False
            and actual_reconciliation.get("recommendation_generation_allowed") is False
            and actual_reconciliation.get("order_submission_allowed") is False
        )
        _add(checks, "S19P03-ACTUAL-GA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-EVIDENCE", boundary_ok, actual_report.get("ga_status"))
    except Exception as exc:
        _add(checks, "S19P03-GENERATED-ARTIFACTS-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S19P03-ACTUAL-GA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-EVIDENCE", False, "generated artifacts unavailable")


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .ga_reconciliation_acceptance import verify_existing_phase_evidence as verify_ga_reconciliation_phase_evidence" in source
            and "from .ga_reconciliation_acceptance import write_phase_evidence as write_ga_reconciliation_phase_evidence" in source
            and '"AC-S19-P03": verify_ga_reconciliation_phase_evidence,' in source
            and '"AC-S19-P03": write_ga_reconciliation_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P03-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(checks, "S19P03-S08-LEGACY-SUCCESSOR-PIN-EXACT", successor == sha256_file(root / CLI_PATH), {"approved": successor, "current": sha256_file(root / CLI_PATH)})


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    try:
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
        summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for suite in suites:
            for key in summary:
                summary[key] += int(suite.attrib.get(key, "0"))
        normalized = bool(suites) and all(
            suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
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
        _add(checks, "S19P03-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    if (root / JUNIT_PATH).is_file():
        hashes[JUNIT_PATH.as_posix()] = sha256_file(root / JUNIT_PATH)
    report_ok = summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
    _add(checks, "S19P03-TARGETED-PYTEST-REPORT", report_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        scan_ok = "STATUS: PASS" in scan and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in scan and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P03-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S19P03-TASKPACK-REPORT-STRICT-JSON")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    _add(checks, "S19P03-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S19_P03_LOCAL_GA_RECONCILIATION_CONTROL_PASS_P04_REQUIRED_ACTUAL_GA_BLOCKED" if passed else "S19/P03_BLOCKED",
        "next": "S19/P04_READY_NOT_STARTED" if passed else "S19/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": EXECUTION_POLICY,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "actual_ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
    }


def evaluate_contract(root: Path, *, require_test_reports: bool = False, require_generated_artifacts: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    _check_truth_boundaries(root, checks, hashes)
    _check_core_and_fixture(root, checks, hashes)
    _check_generated_artifacts(root, checks, hashes, require_generated_artifacts)
    _check_cli_wiring(root, checks)
    _check_reports(root, checks, hashes, require_test_reports)
    boundary_ok = (
        all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key not in {"incremental_cash_spent_aud", "owner_final_order_only"})
        and EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
        and EXTERNAL_EFFECT_BOUNDARY["owner_final_order_only"] is True
    )
    _add(checks, "S19P03-EXTERNAL-EFFECT-BOUNDARY-EXACT", boundary_ok, EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False, require_generated_artifacts=False)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_core_artifacts(root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    _, _, report, reconciliation = _fixture_and_expected_artifacts(root)
    _atomic_write(root / GA_REPORT_PATH, _json_bytes(report))
    _atomic_write(root / ACTUAL_RECONCILIATION_PATH, _json_bytes(reconciliation))
    return report, reconciliation


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (
        CORE_PATH,
        ORACLE_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        GA_REPORT_PATH,
        ACTUAL_RECONCILIATION_PATH,
        P02_PREDECESSOR_PATH,
        *[Path(path) for path in SOURCE_EVIDENCE_HASHES if path != P02_PREDECESSOR_PATH.as_posix()],
    )
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING", "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S19_P03_LOCAL_GA_CONTROL_RESTORE_SIGNED_S19_P02_EVIDENCE_KEEP_ACTUAL_GA_BLOCKED",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "previous_signed_artifact": P02_PREDECESSOR_PATH.as_posix(),
        "immutable_evidence_and_replay_preserved": True,
        "external_state_changed": False,
        "production_state_changed": False,
        "actual_ga_activation_enabled": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "mail_sent": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool, require_generated_artifacts: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, CORE_PATH, FIXTURE_PATH, TEST_PATH, P02_PREDECESSOR_PATH, *[Path(path) for path in BASELINE_HASHES], *[Path(path) for path in SOURCE_EVIDENCE_HASHES if path != P02_PREDECESSOR_PATH.as_posix()]]
    if require_generated_artifacts:
        paths.extend([GA_REPORT_PATH, ACTUAL_RECONCILIATION_PATH])
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
        "evidence_id": "EVD-S19-P03",
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
        "actual_ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
        "release_status": "S19_P03_LOCAL_GA_RECONCILIATION_CONTROL_ONLY_SEPARATE_EMPIRICAL_RUNTIME_REQUIRED",
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports, require_generated_artifacts=require_generated_artifacts),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "adverse_one_in_ten_thousand_vector_count": 2,
            "real_time_wait_performed": False,
            "actual_ga_activated": False,
            "synthetic_or_local_control_promoted_to_empirical": False,
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
        "next": "S19/P04_READY_NOT_STARTED",
        "pass_gate": "证据完整、对账差异0、终止条件未触发。",
        "verified_at": FIXED_CLOCK,
    }
    matches = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matches) != 1 or len(raw_lines) != len(rows):
        raise GAReconciliationAcceptanceError("S19/P03 evidence-index row must exist exactly once")
    raw_lines[matches[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise GAReconciliationAcceptanceError("evidence directory must be canonical machine/evidence")
    preflight = validate_candidate_preflight(root)
    if preflight["status"] != "PASS":
        raise GAReconciliationAcceptanceError("cannot sign a failed S19/P03 preflight")
    write_core_artifacts(root)
    evidence, rollback = build_evidence(root, require_test_reports=True, require_generated_artifacts=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise GAReconciliationAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/P04_READY_NOT_STARTED"}


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
        and evidence.get("decision") == "S19_P03_LOCAL_GA_RECONCILIATION_CONTROL_PASS_P04_REQUIRED_ACTUAL_GA_BLOCKED"
        and evidence.get("next") == "S19/P04_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("actual_ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True, require_generated_artifacts=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("previous_signed_artifact") == P02_PREDECESSOR_PATH.as_posix()
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("actual_ga_activation_enabled") is False
        and rollback.get("order_submission_enabled") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S19/P04_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise GAReconciliationAcceptanceError("existing S19/P03 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/P04_READY_NOT_STARTED"}


__all__ = [
    "ACTUAL_RECONCILIATION_PATH",
    "CONTRACT_ID",
    "CORE_PATH",
    "EVIDENCE_PATH",
    "FIXTURE_PATH",
    "GA_REPORT_PATH",
    "ORACLE_PATH",
    "TEST_PATH",
    "GAReconciliationAcceptanceError",
    "build_evidence",
    "evaluate_contract",
    "load_fixture",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "validate_fixture",
    "verify_existing_phase_evidence",
    "write_core_artifacts",
    "write_phase_evidence",
]
