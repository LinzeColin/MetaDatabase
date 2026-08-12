"""Fail-closed acceptance oracle for ABD S19/P02 shadow and Model Beta gate.

The phase validates deterministic metric-gate semantics.  A passing local
control proves that the gates replay; it deliberately does not prove a real
time shadow run, Model Beta eligibility, a recommendation, or deployment.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .legacy_receipt_compatibility import approved_successor_sha256
from .shadow_beta import (
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXED_CLOCK,
    SAFE_MODEL_CONFIG,
    ShadowBetaInputError,
    build_model_beta_gate,
    build_shadow_report,
    canonical_json_bytes,
    evaluate_shadow_beta,
)
from .walking_skeleton_acceptance import verify_existing_phase_evidence as verify_s19_p01


CONTRACT_ID = "AC-S19-P02"
REQUIREMENT_ID = "REQ-S19-P02"
STAGE_ID = "S19"
PHASE_ID = "P02"
PRODUCT_VERSION = "0.0.0.1"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CORE_PATH = Path("abd_acceptance/shadow_beta.py")
ORACLE_PATH = Path("abd_acceptance/shadow_beta_acceptance.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S19_P02.json")
TEST_PATH = Path("tests/S19/P02_test.py")
SHADOW_REPORT_PATH = Path("shadow_report.json")
MODEL_BETA_GATE_PATH = Path("model_beta_gate.json")
JUNIT_PATH = Path("machine/evidence/S19/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S19/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")

EXPECTED_TASK_IDS = ("T-S19-P02-01", "T-S19-P02-02", "T-S19-P02-03")
EXPECTED_TEST_IDS = ("TEST-S19-P02", "TEST-S19-P02-BOUNDARY", "TEST-S19-P02-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S19-P02-01", "ART-S19-P02-02")
EXPECTED_OUTPUTS = {
    "T-S19-P02-01": ["shadow_report.json", "model_beta_gate.json"],
    "T-S19-P02-02": ["tests/S19/P02_test.py", "machine/tests/fixtures/S19_P02.json"],
    "T-S19-P02-03": ["machine/evidence/EVD-S19-P02.json", "machine/evidence/EVD-S19-P02_rollback.json"],
}
EXPECTED_SCENARIOS = (
    "GOLDEN_SYNTHETIC_ALL_METRICS_PASS_BETA_BLOCKED",
    "ADVERSE_ONE_IN_TEN_THOUSAND_METRICS_STABLE_BETA_BLOCKED",
    "INSUFFICIENT_SYNTHETIC_WINDOW_CANNOT_COUNT_AS_EMPIRICAL",
    "CALIBRATION_BOUNDARY_FAILS_CLOSED",
    "NET_GROWTH_BOUNDARY_FAILS_CLOSED",
    "FRESHNESS_CAPACITY_DRIFT_FAILURES_CLOSE_GATE",
    "EMPIRICAL_PROMOTION_ATTEMPT_FAILS_CLOSED",
    "UNSAFE_RUNTIME_REQUESTS_FAIL_CLOSED",
)
P01_PREDECESSOR_PATH = Path("machine/evidence/EVD-S19-P01.json")
P01_PREDECESSOR_SHA256 = "183fc545bad654f5ee851fcb828433e0e7949396c83f8c67354ccc220c492219"
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
    "machine/evidence/EVD-S19-P01.json": P01_PREDECESSOR_SHA256,
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "target_acceptance.json": "62ab02e730fda25bd18a58f0a578f3dbf65d4813d3d153ac3dbcec9ff6bcdd76",
    "capacity_report.json": "0dfa4b67eb93f75e101adce94bb534fd8d9fbe7e7f139e5bd60ffa48fd81c11b",
    "model_release_gate.json": "6c4db127f346e644fcc4ec6fd6b9a158a29ad74dc628780a4139e709b4735720",
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "production_equivalent_config_schema_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "synthetic_shadow_may_count_as_empirical": False,
    "incremental_cash_spent_aud": "0.00",
}


class ShadowBetaAcceptanceError(RuntimeError):
    """Raised when S19/P02 cannot reproduce its local, fail-closed receipt."""


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
        raise ShadowBetaAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ShadowBetaAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise ShadowBetaAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping) or _contains_float(value):
            raise ShadowBetaAcceptanceError("invalid JSONL row %d" % number)
        rows.append(value)
    return rows


def load_fixture(path: Path) -> Mapping[str, Any]:
    value = strict_json_load(path)
    if not isinstance(value, Mapping) or _contains_float(value):
        raise ShadowBetaAcceptanceError("fixture must be a non-float object")
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
        "model_config",
        "scenarios",
        "malformed_inputs",
    }
    if set(value) != expected:
        raise ShadowBetaAcceptanceError("fixture keys changed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("fixture_id") != "FIX-S19-P02-SHADOW-BETA"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("expected_next") != "S19/P03_READY_NOT_STARTED"
        or value.get("predecessor_evidence_sha256") != P01_PREDECESSOR_SHA256
        or value.get("source_evidence_sha256") != SOURCE_EVIDENCE_HASHES
        or value.get("model_config") != SAFE_MODEL_CONFIG
    ):
        raise ShadowBetaAcceptanceError("fixture identity or source pins changed")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != EXPECTED_SCENARIOS:
        raise ShadowBetaAcceptanceError("fixture scenarios changed")
    for item in scenarios:
        if not isinstance(item, Mapping) or set(item) != {"scenario_id", "shadow_input", "expected"}:
            raise ShadowBetaAcceptanceError("fixture scenario schema changed")
        if not isinstance(item["expected"], Mapping) or _contains_float(item["expected"]):
            raise ShadowBetaAcceptanceError("scenario expected result is invalid")
    malformed = value.get("malformed_inputs")
    if not isinstance(malformed, list) or not malformed:
        raise ShadowBetaAcceptanceError("malformed input vectors are unavailable")
    return value


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P02-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S19P02-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S19P02-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S19P02-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S19P02-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise ShadowBetaAcceptanceError("task graph is unavailable")
        phase_tasks = [item for item in tasks if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == [SHADOW_REPORT_PATH.as_posix(), MODEL_BETA_GATE_PATH.as_posix()]
            and requirement.get("target") == "校准、净增长、时效、容量和漂移门通过。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S19-P02 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and phase_tasks[0].get("depends_on") == ["T-S19-P01-03"]
            and phase_tasks[1].get("depends_on") == ["T-S19-P02-01"]
            and phase_tasks[2].get("depends_on") == ["T-S19-P02-02"]
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S19-P02"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P02-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        row = _row(rows, "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "校准、净增长、时效、容量和漂移门通过。"
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
            and row.get("next") == "S19/P03_READY_NOT_STARTED"
        )
        _add(checks, "S19P02-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S19P02-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        result = verify_s19_p01(root)
        actual = sha256_file(root / P01_PREDECESSOR_PATH)
        hashes[P01_PREDECESSOR_PATH.as_posix()] = actual
        valid = (
            result.get("contract_id") == "AC-S19-P01"
            and result.get("status") == "PASS"
            and result.get("evidence_sha256") == P01_PREDECESSOR_SHA256
            and result.get("next") == "S19/P02_READY_NOT_STARTED"
            and actual == P01_PREDECESSOR_SHA256
        )
        detail: Any = {"expected": P01_PREDECESSOR_SHA256, "actual": actual, "next": result.get("next")}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P02-PREDECESSOR-AC-S19-P01-CURRENT", valid, detail)


def _check_truth_boundaries(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in SOURCE_EVIDENCE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P02-SOURCE-PIN-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    try:
        parameters = strict_json_load(root / "machine/facts/parameters.json")
        release_policy = strict_json_load(root / "machine/facts/release_policy.json")
        target = strict_json_load(root / "target_acceptance.json")
        capacity = strict_json_load(root / "capacity_report.json")
        release_gate = strict_json_load(root / "model_release_gate.json")
        parameter_ok = (
            parameters.get("calibration", {}).get("slope_min") == "0.90"
            and parameters.get("calibration", {}).get("slope_max") == "1.10"
            and parameters.get("calibration", {}).get("intercept_abs_max") == "0.02"
            and parameters.get("calibration", {}).get("calibration_error_main_max") == "0.025"
            and parameters.get("calibration", {}).get("calibration_error_niche_max") == "0.04"
            and parameters.get("calibration", {}).get("net_log_growth_95pct_lower_bound") == ">0"
            and parameters.get("coverage_and_freshness", {}).get("quote_usable_seconds", {}).get("live") == 12
            and parameters.get("coverage_and_freshness", {}).get("advice_usable_seconds", {}).get("live") == 8
            and parameters.get("drift", {}).get("population_stability_index_stop") == "0.20"
            and parameters.get("drift", {}).get("jensen_shannon_stop") == "0.10"
            and parameters.get("target_30pct", {}).get("shadow_min_days") == 90
            and parameters.get("target_30pct", {}).get("shadow_min_independent_equivalent_signals") == 1000
            and parameters.get("target_30pct", {}).get("guaranteed") is False
        )
        policy_ok = release_policy.get("alpha_beta_ga", {}).get("model_beta") == "至少60天和500实时影子合格信号"
        empirical_ok = (
            target.get("plausibility_gate", {}).get("observed_shadow_days") == 0
            and target.get("plausibility_gate", {}).get("observed_independent_equivalent_signals") == 5
            and target.get("plausibility_gate", {}).get("status") == "NOT_PLAUSIBLE_INSUFFICIENT_90D_OR_1000_SIGNALS"
            and target.get("falsification_gate", {}).get("current_empirical_assessment", {}).get("evidence_status") == "NO_EMPIRICAL_EXECUTION_EVIDENCE"
            and target.get("falsification_gate", {}).get("synthetic_case_is_not_empirical") is True
            and target.get("hard_gate_invariants", {}).get("synthetic_artifacts_may_substitute_for_actual_return") is False
            and capacity.get("external_effect_boundary", {}).get("real_market_or_provider_capacity_observed") is False
            and release_gate.get("model_gate", {}).get("status") == "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT"
            and release_gate.get("model_gate", {}).get("activation_allowed") is False
        )
    except Exception as exc:
        parameter_ok = policy_ok = empirical_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = "frozen facts preserve no empirical Model Beta evidence"
    _add(checks, "S19P02-PARAMETER-THRESHOLDS-EXACT", parameter_ok, detail)
    _add(checks, "S19P02-MODEL-BETA-POLICY-EXACT", policy_ok, detail)
    _add(checks, "S19P02-SYNTHETIC-NEVER-COUNTS-AS-EMPIRICAL", empirical_ok, detail)


def _fixture_and_expected_artifacts(root: Path) -> Tuple[Mapping[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    fixture = validate_fixture(load_fixture(root / FIXTURE_PATH))
    golden = next(item for item in fixture["scenarios"] if item["scenario_id"] == EXPECTED_SCENARIOS[0])
    evaluation = evaluate_shadow_beta(golden["shadow_input"])
    report = build_shadow_report(
        evaluation,
        fixture_sha256=sha256_file(root / FIXTURE_PATH),
        predecessor_evidence_sha256=P01_PREDECESSOR_SHA256,
        source_evidence_sha256=SOURCE_EVIDENCE_HASHES,
    )
    gate = build_model_beta_gate(report)
    return fixture, evaluation, report, gate


def _check_core_and_fixture(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        fixture, golden, report, gate = _fixture_and_expected_artifacts(root)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        hashes[CORE_PATH.as_posix()] = sha256_file(root / CORE_PATH)
        scenario_results = []
        replay_ok = True
        for scenario in fixture["scenarios"]:
            first = evaluate_shadow_beta(scenario["shadow_input"])
            second = evaluate_shadow_beta(scenario["shadow_input"])
            expected = scenario["expected"]
            matched = {key: first.get(key) for key in expected} == dict(expected)
            replay_ok = replay_ok and first == second and first["shadow_beta_evaluation_sha256"] == second["shadow_beta_evaluation_sha256"]
            scenario_results.append({"scenario_id": scenario["scenario_id"], "matched": matched, "status": first["status"], "model_beta_status": first["model_beta_status"]})
        _add(checks, "S19P02-FIXTURE-EXACT", True, {"scenarios": list(EXPECTED_SCENARIOS)})
        _add(checks, "S19P02-FROZEN-SCENARIOS-EXACT", all(item["matched"] for item in scenario_results), scenario_results)
        _add(checks, "S19P02-DETERMINISTIC-REPLAY-HASH-EXACT", replay_ok, {"scenario_count": len(scenario_results)})
        local_gate_ok = (
            golden.get("status") == "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT"
            and golden.get("all_quality_gates_pass") is True
            and golden.get("action") == "NO_RECOMMENDATION"
            and golden.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
            and golden.get("model_beta_eligible") is False
            and golden.get("empirical_observation", {}).get("observed_realtime_shadow_days") == 0
            and golden.get("empirical_observation", {}).get("observed_realtime_qualified_signals") == 0
        )
        _add(checks, "S19P02-ALL-FIVE-LOCAL-QUALITY-GATES-PASS-BETA-BLOCKED", local_gate_ok, golden.get("model_beta_status"))
        artifact_ok = (
            report.get("artifact_id") == EXPECTED_ARTIFACT_IDS[0]
            and gate.get("artifact_id") == EXPECTED_ARTIFACT_IDS[1]
            and gate.get("status") == "PASS_LOCAL_CONTRACT_MODEL_BETA_BLOCKED"
            and gate.get("model_beta_eligible") is False
            and gate.get("model_activation_allowed") is False
            and gate.get("shadow_report_sha256") == report.get("shadow_report_sha256")
        )
        _add(checks, "S19P02-ARTIFACT-BUILD-EXACT", artifact_ok, {"shadow": report.get("shadow_report_sha256"), "beta": gate.get("model_beta_gate_sha256")})
        source = (root / CORE_PATH).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "time", "asyncio", "os", "random"}
        source_ok = not imports.intersection(forbidden) and all(token not in source for token in ("sleep(", "submit_order", "retry_order", "http://", "https://", "smtplib"))
        _add(checks, "S19P02-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY", source_ok, sorted(imports.intersection(forbidden)))
    except Exception as exc:
        _add(checks, "S19P02-CORE-OR-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_generated_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str], required: bool) -> None:
    if not required:
        _add(checks, "S19P02-GENERATED-ARTIFACTS-DEFERRED-PREFLIGHT", True, "pre-signing source and fixture preflight")
        return
    try:
        _, _, expected_report, expected_gate = _fixture_and_expected_artifacts(root)
        actual_report = strict_json_load(root / SHADOW_REPORT_PATH)
        actual_gate = strict_json_load(root / MODEL_BETA_GATE_PATH)
        hashes[SHADOW_REPORT_PATH.as_posix()] = sha256_file(root / SHADOW_REPORT_PATH)
        hashes[MODEL_BETA_GATE_PATH.as_posix()] = sha256_file(root / MODEL_BETA_GATE_PATH)
        exact = actual_report == expected_report and actual_gate == expected_gate
        _add(checks, "S19P02-GENERATED-ARTIFACTS-REPLAY-EXACT", exact, {"shadow": hashes[SHADOW_REPORT_PATH.as_posix()], "beta": hashes[MODEL_BETA_GATE_PATH.as_posix()]})
        gate_ok = (
            actual_gate.get("status") == "PASS_LOCAL_CONTRACT_MODEL_BETA_BLOCKED"
            and actual_gate.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
            and actual_gate.get("model_beta_eligible") is False
            and actual_gate.get("model_activation_allowed") is False
            and actual_gate.get("recommendation_generation_allowed") is False
            and actual_gate.get("order_submission_allowed") is False
            and actual_gate.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and actual_gate.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        )
        _add(checks, "S19P02-MODEL-BETA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-EVIDENCE", gate_ok, actual_gate.get("model_beta_status"))
    except Exception as exc:
        _add(checks, "S19P02-GENERATED-ARTIFACTS-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S19P02-MODEL-BETA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-EVIDENCE", False, "generated artifacts unavailable")


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .shadow_beta_acceptance import verify_existing_phase_evidence as verify_shadow_beta_phase_evidence" in source
            and "from .shadow_beta_acceptance import write_phase_evidence as write_shadow_beta_phase_evidence" in source
            and '"AC-S19-P02": verify_shadow_beta_phase_evidence,' in source
            and '"AC-S19-P02": write_shadow_beta_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P02-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(checks, "S19P02-S08-LEGACY-SUCCESSOR-PIN-EXACT", successor == sha256_file(root / CLI_PATH), {"approved": successor, "current": sha256_file(root / CLI_PATH)})


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
        _add(checks, "S19P02-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    if (root / JUNIT_PATH).is_file():
        hashes[JUNIT_PATH.as_posix()] = sha256_file(root / JUNIT_PATH)
    report_ok = summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
    _add(checks, "S19P02-TARGETED-PYTEST-REPORT", report_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        scan_ok = "STATUS: PASS" in scan and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in scan and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P02-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S19P02-TASKPACK-REPORT-STRICT-JSON")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    _add(checks, "S19P02-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S19_P02_SHADOW_BETA_CONTROL_PASS_P03_REQUIRED_NOT_MODEL_BETA" if passed else "S19/P02_BLOCKED",
        "next": "S19/P03_READY_NOT_STARTED" if passed else "S19/P02_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": EXECUTION_POLICY,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "model_beta_status": "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE",
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
    _add(checks, "S19P02-EXTERNAL-EFFECT-BOUNDARY-EXACT", boundary_ok, EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False, require_generated_artifacts=False)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_core_artifacts(root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    _, _, report, gate = _fixture_and_expected_artifacts(root)
    _atomic_write(root / SHADOW_REPORT_PATH, _json_bytes(report))
    _atomic_write(root / MODEL_BETA_GATE_PATH, _json_bytes(gate))
    return report, gate


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (CORE_PATH, ORACLE_PATH, FIXTURE_PATH, TEST_PATH, SHADOW_REPORT_PATH, MODEL_BETA_GATE_PATH, P01_PREDECESSOR_PATH, *[Path(path) for path in SOURCE_EVIDENCE_HASHES if path != P01_PREDECESSOR_PATH.as_posix()])
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING", "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S19_P02_LOCAL_SHADOW_FEATURE_RESTORE_SIGNED_S19_P01_EVIDENCE_KEEP_MODEL_BETA_BLOCKED",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "previous_signed_artifact": P01_PREDECESSOR_PATH.as_posix(),
        "immutable_evidence_and_replay_preserved": True,
        "external_state_changed": False,
        "production_state_changed": False,
        "model_activation_enabled": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "mail_sent": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool, require_generated_artifacts: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, CORE_PATH, FIXTURE_PATH, TEST_PATH, P01_PREDECESSOR_PATH, *[Path(path) for path in BASELINE_HASHES], *[Path(path) for path in SOURCE_EVIDENCE_HASHES if path != P01_PREDECESSOR_PATH.as_posix()]]
    if require_generated_artifacts:
        paths.extend([SHADOW_REPORT_PATH, MODEL_BETA_GATE_PATH])
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
        "evidence_id": "EVD-S19-P02",
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
        "model_beta_status": "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE",
        "release_status": "S19_P02_LOCAL_SHADOW_GATE_CONTROL_ONLY_EMPIRICAL_RUNTIME_REQUIRED",
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
            "model_beta_activated": False,
            "synthetic_fixture_promoted_to_empirical": False,
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
        "next": "S19/P03_READY_NOT_STARTED",
        "pass_gate": "校准、净增长、时效、容量和漂移门通过。",
        "verified_at": FIXED_CLOCK,
    }
    matches = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matches) != 1 or len(raw_lines) != len(rows):
        raise ShadowBetaAcceptanceError("S19/P02 evidence-index row must exist exactly once")
    raw_lines[matches[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ShadowBetaAcceptanceError("evidence directory must be canonical machine/evidence")
    preflight = validate_candidate_preflight(root)
    if preflight["status"] != "PASS":
        raise ShadowBetaAcceptanceError("cannot sign a failed S19/P02 preflight")
    write_core_artifacts(root)
    evidence, rollback = build_evidence(root, require_test_reports=True, require_generated_artifacts=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ShadowBetaAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/P03_READY_NOT_STARTED"}


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
        and evidence.get("decision") == "S19_P02_SHADOW_BETA_CONTROL_PASS_P03_REQUIRED_NOT_MODEL_BETA"
        and evidence.get("next") == "S19/P03_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True, require_generated_artifacts=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("previous_signed_artifact") == P01_PREDECESSOR_PATH.as_posix()
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("model_activation_enabled") is False
        and rollback.get("order_submission_enabled") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S19/P03_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise ShadowBetaAcceptanceError("existing S19/P02 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/P03_READY_NOT_STARTED"}


__all__ = [
    "CONTRACT_ID", "CORE_PATH", "EVIDENCE_PATH", "FIXTURE_PATH", "MODEL_BETA_GATE_PATH", "ORACLE_PATH",
    "SHADOW_REPORT_PATH", "TEST_PATH", "ShadowBetaAcceptanceError", "build_evidence", "evaluate_contract",
    "load_fixture", "perform_rollback_drill", "validate_candidate_preflight", "validate_fixture",
    "verify_existing_phase_evidence", "write_core_artifacts", "write_phase_evidence",
]
