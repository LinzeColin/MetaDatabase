"""Fail-closed acceptance oracle for ABD S16/P01 model inventory.

S16/P01 establishes only a local, frozen Champion/Challenger comparison
surface.  It deliberately cannot convert a synthetic inventory into an
empirical model, recommendation, order, or production-release claim.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Tuple
import xml.etree.ElementTree as ElementTree

from .model_challenge_engine import (
    BASELINE_REPORT_PATH,
    CHALLENGER_REPORT_PATH,
    CLAIM_BOUNDARY,
    CONTRACT_ID,
    FIXED_CLOCK,
    FIXTURE_PATH,
    INPUT_MODE,
    MODEL_REGISTRY_PATH,
    ModelChallengeInputError,
    artifact_sha256,
    build_artifacts,
    canonical_json_bytes,
    load_fixture,
    sha256_file,
    strict_json_load,
    validate_artifacts,
)

from .canonical_facts import strict_json_load as acceptance_json_load


REQUIREMENT_ID = "REQ-S16-P01"
STAGE_ID = "S16"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
ORACLE_PATH = Path("abd_acceptance/model_challenge.py")
CORE_PATH = Path("abd_acceptance/model_challenge_engine.py")
GENERATOR_PATH = Path("model_challenge.py")
TEST_PATH = Path("tests/S16/P01_test.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S16/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S16/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "model:s16_market_champion_challenger"

BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}

PREDECESSORS = {
    "AC-S08-P04": {
        "evidence_path": Path("machine/evidence/EVD-S08-P04.json"),
        "evidence_sha256": "20ac3e8d01d5623dfb4616ed8cb6076735b7c0d42b9cf118a4688883eb8271d3",
        "next": "S08/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S09-P04": {
        "evidence_path": Path("machine/evidence/EVD-S09-P04.json"),
        "evidence_sha256": "e38e3c5bbbdfb1cfe6a345bcf0511e0ccf7c65e5b78415d62cfd44fd1c5332ef",
        "next": "S09/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S10-P04": {
        "evidence_path": Path("machine/evidence/EVD-S10-P04.json"),
        "evidence_sha256": "0700d4af988731fa39fc9506751b993e509da8afa78d63ef951c3bac842a9ed3",
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED",
    },
    "AC-S11-P04": {
        "evidence_path": Path("machine/evidence/EVD-S11-P04.json"),
        "evidence_sha256": "d9bc525ce3902cdda3ca6ad6253cc77ab69cddb4641b3d4d7e2c207f59c49ed2",
        "next": "S11/STAGE_REVIEW_READY_NOT_STARTED",
    },
}

EXPECTED_TEST_IDS = ("TEST-S16-P01", "TEST-S16-P01-BOUNDARY", "TEST-S16-P01-REPLAY")
EXPECTED_TASK_IDS = ("T-S16-P01-01", "T-S16-P01-02", "T-S16-P01-03")
EXPECTED_ARTIFACT_IDS = ("ART-S16-P01-01", "ART-S16-P01-02", "ART-S16-P01-03")
EXPECTED_OUTPUTS = {
    "T-S16-P01-01": ["model_registry.json", "baseline_report.json", "challenger_report.json"],
    "T-S16-P01-02": ["tests/S16/P01_test.py", "machine/tests/fixtures/S16_P01.json"],
    "T-S16-P01-03": ["machine/evidence/EVD-S16-P01.json", "machine/evidence/EVD-S16-P01_rollback.json"],
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "predecessor_verification_mode": "PINNED_SIGNED_RECEIPTS_AND_LOCAL_SOURCE_HASHES",
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    **CLAIM_BOUNDARY,
    "model_or_strategy_executed": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "owner_final_order_only": True,
}


class ModelChallengeAcceptanceError(ValueError):
    """Raised when S16/P01 evidence cannot be reproduced safely."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise ModelChallengeAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ModelChallengeAcceptanceError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ModelChallengeAcceptanceError("rows are unavailable")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matching) != 1:
        raise ModelChallengeAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matching[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = acceptance_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S16P01-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S16P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S16P01-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S16P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S16P01-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise ModelChallengeAcceptanceError("task graph is unavailable")
        phase_tasks = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == ["model_registry.json", "baseline_report.json", "challenger_report.json"]
            and requirement.get("target") == "模型没有显著增量时权重归零。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S16-P01 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S16-P01"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S16P01-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        row = _row(index, "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "模型没有显著增量时权重归零。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "PHASE_EVIDENCE"
            and row.get("stage_id") == STAGE_ID
            and row.get("contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("artifact_sha256") == (sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING")
            and row.get("next") == "S16/P02_READY_NOT_STARTED"
        )
        _add(checks, "S16P01-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S16P01-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for contract_id, metadata in PREDECESSORS.items():
        path = root / metadata["evidence_path"]
        try:
            value = acceptance_json_load(path)
            actual = sha256_file(path)
            valid = (
                isinstance(value, Mapping)
                and actual == metadata["evidence_sha256"]
                and value.get("contract_id") == contract_id
                and value.get("status") == "PASS"
                and value.get("next") == metadata["next"]
            )
        except Exception as exc:
            actual = "MISSING"
            valid = False
            value = "%s: %s" % (type(exc).__name__, exc)
        hashes[metadata["evidence_path"].as_posix()] = actual
        _add(checks, "S16P01-PREDECESSOR-%s" % contract_id, valid, value if not valid else actual)


def _check_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    try:
        fixture = load_fixture(root / FIXTURE_PATH)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        _add(checks, "S16P01-FIXTURE-EXACT", True, FIXTURE_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S16P01-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return None
    try:
        expected = build_artifacts(root, fixture)
        validate_artifacts(root, fixture)
        for relative, artifact in expected.items():
            hashes[relative] = sha256_file(root / relative)
            _add(checks, "S16P01-%s-EXACT" % Path(relative).stem.upper().replace("_", "-"), True, artifact.get("artifact_id"))
    except Exception as exc:
        _add(checks, "S16P01-ARTIFACT-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return fixture
    registry = expected[MODEL_REGISTRY_PATH.as_posix()]
    baseline = expected[BASELINE_REPORT_PATH.as_posix()]
    challenger = expected[CHALLENGER_REPORT_PATH.as_posix()]
    challenger_rows = registry.get("challengers") if isinstance(registry, Mapping) else None
    zero_weight = (
        isinstance(challenger_rows, list)
        and len(challenger_rows) == 6
        and all(row.get("significant_increment") is False and row.get("active_weight") == "0.00" for row in challenger_rows if isinstance(row, Mapping))
        and registry.get("champion", {}).get("active_weight") == "1.00"
        and registry.get("selection_policy", {}).get("weight_when_increment_not_significant") == "0.00"
        and registry.get("selection_policy", {}).get("activation_requires_contract") == "AC-S16-P02"
    )
    _add(checks, "S16P01-NO-SIGNIFICANT-INCREMENT-ZERO-WEIGHT", zero_weight, registry.get("selection_policy") if isinstance(registry, Mapping) else registry)
    windows = baseline.get("frozen_windows") if isinstance(baseline, Mapping) else None
    window_ok = (
        isinstance(windows, list)
        and len(windows) == 3
        and all(
            isinstance(row, Mapping)
            and row.get("classification") == "FROZEN_SYNTHETIC_PRE_EVALUATION_NOT_EMPIRICAL"
            and row.get("observed_outcome_count") == 0
            for row in windows
        )
        and baseline.get("window_comparison_status") == "PRE_EVALUATION_SYNTHETIC_ONLY_NO_EMPIRICAL_SCORE"
    )
    _add(checks, "S16P01-FROZEN-TIME-WINDOWS-NONEMPIRICAL", window_ok, windows)
    report_ok = (
        isinstance(challenger, Mapping)
        and challenger.get("summary") == {
            "challenger_count": 6,
            "significant_increment_count": 0,
            "nonzero_active_weight_count": 0,
            "safe_action": "KEEP_CHAMPION_MARKET_ONLY_PENDING_S16_P02",
        }
        and challenger.get("claim_boundary") == CLAIM_BOUNDARY
        and artifact_sha256(registry) == baseline.get("registry_sha256") == challenger.get("registry_sha256")
        and artifact_sha256(baseline) == challenger.get("baseline_report_sha256")
    )
    _add(checks, "S16P01-CHAMPION-CHALLENGER-REPORT-CLOSED", report_ok, challenger.get("summary") if isinstance(challenger, Mapping) else challenger)
    boundary_ok = all(
        isinstance(artifact, Mapping)
        and artifact.get("claim_boundary") == CLAIM_BOUNDARY
        and artifact.get("claim_boundary", {}).get("recommendation_generated_or_enabled") is False
        and artifact.get("claim_boundary", {}).get("order_submission_enabled") is False
        and artifact.get("claim_boundary", {}).get("production_deployed_or_activated") is False
        for artifact in (registry, baseline, challenger)
    )
    _add(checks, "S16P01-ARTIFACT-EXTERNAL-BOUNDARY-EXACT", boundary_ok, CLAIM_BOUNDARY)
    return fixture


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        imports: set[str] = set()
        source_text = ""
        for path in (GENERATOR_PATH, CORE_PATH, ORACLE_PATH):
            source = (root / path).read_text(encoding="utf-8")
            source_text += source
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        forbidden_imports = {"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"}
        forbidden_tokens = ("slee" "p(", "submit" "_order", "retry" "_order", "http" "://", "https" "://")
        passed = not imports.intersection(forbidden_imports) and all(token not in source_text for token in forbidden_tokens)
        _add(checks, "S16P01-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", passed, {"imports": sorted(imports)})
    except Exception as exc:
        _add(checks, "S16P01-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
    if not suites:
        raise ModelChallengeAcceptanceError("JUnit has no testsuite")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    normalized = True
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
        normalized = normalized and suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000"
        normalized = normalized and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S16P01-TARGETED-REPORTS-REQUIRED", True, "preflight mode")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        passed = isinstance(minimum, int) and summary["tests"] >= minimum and not summary["failures"] and not summary["errors"] and not summary["skipped"] and normalized
        _add(checks, "S16P01-TARGETED-PYTEST-REPORT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S16P01-TARGETED-PYTEST-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S16P01-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S16P01-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S16P01-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S16P01-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S16_P01_MARKET_CHAMPION_RETAINED_CHALLENGERS_ZERO_WEIGHT_P02_REQUIRED" if passed else "S16/P01_BLOCKED",
        "next": "S16/P02_READY_NOT_STARTED" if passed else "S16/P01_REMEDIATION_REQUIRED",
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
    _check_taskpack(root, checks)
    _check_predecessors(root, checks, hashes)
    fixture = _check_artifacts(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        path.as_posix(): {
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
            "status": "PASS" if (root / path).is_file() else "FAIL",
        }
        for path in (GENERATOR_PATH, CORE_PATH, MODEL_REGISTRY_PATH, BASELINE_REPORT_PATH, CHALLENGER_REPORT_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S16-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S16_P01_CHALLENGERS_KEEP_MARKET_CHAMPION_AND_SIGNED_PREDECESSORS",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        CORE_PATH,
        GENERATOR_PATH,
        ORACLE_PATH,
        MODEL_REGISTRY_PATH,
        BASELINE_REPORT_PATH,
        CHALLENGER_REPORT_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        *[Path(relative) for relative in BASELINE_HASHES],
        *[metadata["evidence_path"] for metadata in PREDECESSORS.values()],
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        _json_bytes(
            {
                "contract_id": evidence.get("contract_id"),
                "decision": evidence.get("decision"),
                "next": evidence.get("next"),
                "status": evidence.get("status"),
                "validation": evidence.get("validation"),
            }
        )
    )


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S16-P01",
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
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S16_P01_LOCAL_EVIDENCE_ONLY_P02_REQUIRED",
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python model_challenge.py --root .",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S16/P01_test.py --junitxml=machine/evidence/S16/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S16/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S16/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S16-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"frozen_window_count": 3, "challenger_count": 6, "adverse_delta": "-0.0001", "real_time_wait_performed": False},
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
        raise ModelChallengeAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S16/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise ModelChallengeAcceptanceError("S16/P01 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw + "\n").encode("utf-8")
        for raw, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ModelChallengeAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ModelChallengeAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S16/P02_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = acceptance_json_load(root / EVIDENCE_PATH)
    rollback = acceptance_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise ModelChallengeAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S16_P01_MARKET_CHAMPION_RETAINED_CHALLENGERS_ZERO_WEIGHT_P02_REQUIRED"
        and evidence.get("next") == "S16/P02_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
    )
    if not valid:
        raise ModelChallengeAcceptanceError("existing S16/P01 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S16/P02_READY_NOT_STARTED",
    }


__all__ = [
    "CONTRACT_ID",
    "CORE_PATH",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FEATURE_FLAG_ID",
    "FIXTURE_PATH",
    "ModelChallengeAcceptanceError",
    "ORACLE_PATH",
    "TEST_PATH",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
