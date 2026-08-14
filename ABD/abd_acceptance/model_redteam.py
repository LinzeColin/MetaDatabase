"""Fail-closed acceptance oracle for ABD S16/P03 frozen red-team review."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import strict_json_load as acceptance_json_load
from .model_redteam_engine import (
    ATTACK_CATEGORIES,
    CLAIM_BOUNDARY,
    CONTRACT_ID,
    CROSS_MODEL_REVIEW_PATH,
    FIXED_CLOCK,
    FIXTURE_PATH,
    INPUT_MODE,
    MODEL_REDTEAM_PATH,
    P02_EVIDENCE_PATH,
    PRODUCT_VERSION,
    REDTEAM_ARTIFACT_ID,
    REVIEW_ARTIFACT_ID,
    ModelRedteamInputError,
    build_artifacts,
    canonical_json_bytes,
    load_fixture,
    sha256_file,
    strict_json_load,
    validate_artifacts,
)


REQUIREMENT_ID = "REQ-S16-P03"
STAGE_ID = "S16"
PHASE_ID = "P03"
VERSION = PRODUCT_VERSION
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
ORACLE_PATH = Path("abd_acceptance/model_redteam.py")
CORE_PATH = Path("abd_acceptance/model_redteam_engine.py")
GENERATOR_PATH = Path("model_redteam.py")
TEST_PATH = Path("tests/S16/P03_test.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S16/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S16/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "model:s16_redteam_cross_model_review"

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
    "machine/facts/strategy_spec.json": "d77f047219632145a71f0f2932149654ae24205bbdc291fa604b93bfcff5117d",
    "machine/facts/risk_register.json": "6f50e159f000ac4a1c714d08cff239e524a58c679cd77c05d7b4944a7b602888",
}
P02_PREDECESSOR = {
    "evidence_path": P02_EVIDENCE_PATH,
    "evidence_sha256": "f9769b776bca121d1a048f312b107d91028550f640826023ac0d32db702aef6a",
    "next": "S16/P03_READY_NOT_STARTED",
}
EXPECTED_TEST_IDS = ("TEST-S16-P03", "TEST-S16-P03-BOUNDARY", "TEST-S16-P03-REPLAY")
EXPECTED_TASK_IDS = ("T-S16-P03-01", "T-S16-P03-02", "T-S16-P03-03")
EXPECTED_ARTIFACT_IDS = ("ART-S16-P03-01", "ART-S16-P03-02")
EXPECTED_OUTPUTS = {
    "T-S16-P03-01": ["model_redteam.json", "cross_model_review.json"],
    "T-S16-P03-02": ["tests/S16/P03_test.py", "machine/tests/fixtures/S16_P03.json"],
    "T-S16-P03-03": ["machine/evidence/EVD-S16-P03.json", "machine/evidence/EVD-S16-P03_rollback.json"],
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "frozen_adversarial_attack_count": 6,
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    **CLAIM_BOUNDARY,
    "model_or_strategy_executed": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "owner_final_order_only": True,
}


class ModelRedteamAcceptanceError(ValueError):
    """Raised when the S16/P03 receipt cannot be reproduced safely."""


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
            raise ModelRedteamAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ModelRedteamAcceptanceError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ModelRedteamAcceptanceError("rows are unavailable")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matching) != 1:
        raise ModelRedteamAcceptanceError("expected exactly one %s=%s" % (key, identifier))
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
        _add(checks, "S16P03-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S16P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S16P03-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S16P03-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S16P03-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise ModelRedteamAcceptanceError("task graph is unavailable")
        phase_tasks = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == ["model_redteam.json", "cross_model_review.json"]
            and requirement.get("target") == "任何可绕过门的攻击为阻断缺陷。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S16-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S16-P03"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S16P03-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        row = _row(index, "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "任何可绕过门的攻击为阻断缺陷。"
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
            and row.get("next") == "S16/P04_READY_NOT_STARTED"
        )
        _add(checks, "S16P03-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S16P03-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_p02_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    path = root / P02_PREDECESSOR["evidence_path"]
    try:
        evidence = acceptance_json_load(path)
        actual = sha256_file(path)
        valid = (
            isinstance(evidence, Mapping)
            and actual == P02_PREDECESSOR["evidence_sha256"]
            and evidence.get("contract_id") == "AC-S16-P02"
            and evidence.get("status") == "PASS"
            and evidence.get("next") == P02_PREDECESSOR["next"]
        )
    except Exception as exc:
        actual = "MISSING"
        valid = False
        evidence = "%s: %s" % (type(exc).__name__, exc)
    hashes[P02_PREDECESSOR["evidence_path"].as_posix()] = actual
    _add(checks, "S16P03-PREDECESSOR-AC-S16-P02", valid, evidence if not valid else actual)


def _check_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    try:
        fixture = load_fixture(root)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        _add(checks, "S16P03-FIXTURE-EXACT", True, FIXTURE_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S16P03-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return None
    try:
        expected = build_artifacts(root, fixture["fixture"])
        validate_artifacts(root, fixture["fixture"])
        for relative, artifact in expected.items():
            hashes[relative] = sha256_file(root / relative)
            _add(checks, "S16P03-%s-EXACT" % Path(relative).stem.upper().replace("_", "-"), True, artifact.get("artifact_id"))
        hashes[GENERATOR_PATH.as_posix()] = sha256_file(root / GENERATOR_PATH)
        hashes[CORE_PATH.as_posix()] = sha256_file(root / CORE_PATH)
    except Exception as exc:
        _add(checks, "S16P03-ARTIFACT-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return fixture
    redteam = expected[MODEL_REDTEAM_PATH.as_posix()]
    review = expected[CROSS_MODEL_REVIEW_PATH.as_posix()]
    results = redteam.get("attack_results") if isinstance(redteam, Mapping) else None
    attacks_ok = (
        isinstance(results, list)
        and [item.get("category") for item in results if isinstance(item, Mapping)] == list(ATTACK_CATEGORIES)
        and all(
            isinstance(item, Mapping)
            and item.get("expected_outcome") == "BLOCKED"
            and item.get("observed_outcome") == "BLOCKED"
            and item.get("attack_blocked") is True
            and item.get("safe_action") == "NO_RECOMMENDATION_NO_ORDER"
            for item in results
        )
        and redteam.get("summary") == {
            "attack_count": 6,
            "blocked_count": 6,
            "bypass_count": 0,
            "all_attack_paths_blocked": True,
            "any_bypass_is_blocking_defect": True,
        }
    )
    _add(checks, "S16P03-ALL-SIX-FROZEN-ATTACKS-BLOCKED", attacks_ok, redteam.get("summary") if isinstance(redteam, Mapping) else redteam)
    artifact_ids_ok = (
        redteam.get("artifact_id") == REDTEAM_ARTIFACT_ID
        and review.get("artifact_id") == REVIEW_ARTIFACT_ID
        and review.get("redteam_artifact_sha256") == _sha256_bytes(_json_bytes(redteam))
    )
    _add(checks, "S16P03-ARTIFACT-IDENTITIES-EXACT", artifact_ids_ok, list(EXPECTED_ARTIFACT_IDS))
    consensus = review.get("review_consensus") if isinstance(review, Mapping) else None
    reviewed_models = review.get("reviewed_models") if isinstance(review, Mapping) else None
    review_ok = (
        isinstance(reviewed_models, list)
        and reviewed_models == [
            {
                "model_id": "MARKET_CONSENSUS_CHAMPION",
                "role": "CHAMPION",
                "p01_active_weight": "1.00",
                "p02_evaluation_candidate": False,
                "review_verdict": "BLOCK_PROMOTION_PENDING_S16_P04",
            },
            {
                "model_id": "GENERIC_RESIDUAL_CHALLENGER",
                "role": "CHALLENGER",
                "p01_active_weight": "0.00",
                "p02_evaluation_candidate": True,
                "review_verdict": "BLOCK_PROMOTION_PENDING_S16_P04",
            },
        ]
        and consensus == {
            "all_required_attacks_blocked": True,
            "all_model_views_agree": True,
            "model_promotion_allowed": False,
            "activation_status": "NOT_ACTIVATED_PENDING_S16_P04",
            "next_required_gate": "AC-S16-P04",
            "decision": "S16_P03_REDTEAM_AND_CROSS_MODEL_REVIEW_PASS_P04_REQUIRED",
        }
        and review.get("review_scope") == "FROZEN_CONTROL_REVIEW_NOT_MODEL_INFERENCE_OR_MARKET_EVALUATION"
    )
    _add(checks, "S16P03-CROSS-MODEL-REVIEW-UNANIMOUS-AND-NO-PROMOTION", review_ok, consensus)
    boundary_ok = (
        redteam.get("claim_boundary") == CLAIM_BOUNDARY
        and review.get("claim_boundary") == CLAIM_BOUNDARY
        and redteam.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and review.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and redteam.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and review.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and review.get("p02_promotion_before_review", {}).get("weight_after") == "0.00"
    )
    _add(checks, "S16P03-NO-EMPIRICAL-ACTIVATION-OR-RETURN-CLAIM", boundary_ok, CLAIM_BOUNDARY)
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
        _add(checks, "S16P03-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", passed, {"imports": sorted(imports)})
    except Exception as exc:
        _add(checks, "S16P03-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
    if not suites:
        raise ModelRedteamAcceptanceError("JUnit has no testsuite")
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
        _add(checks, "S16P03-TARGETED-REPORTS-REQUIRED", True, "preflight mode")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        raw_fixture = fixture.get("fixture") if isinstance(fixture, Mapping) else None
        minimum = raw_fixture.get("minimum_targeted_pytest_cases") if isinstance(raw_fixture, Mapping) else None
        passed = isinstance(minimum, int) and summary["tests"] >= minimum and not summary["failures"] and not summary["errors"] and not summary["skipped"] and normalized
        _add(checks, "S16P03-TARGETED-PYTEST-REPORT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S16P03-TARGETED-PYTEST-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S16P03-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S16P03-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S16P03-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S16P03-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S16_P03_REDTEAM_AND_CROSS_MODEL_REVIEW_PASS_P04_REQUIRED" if passed else "S16/P03_BLOCKED",
        "next": "S16/P04_READY_NOT_STARTED" if passed else "S16/P03_REMEDIATION_REQUIRED",
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
    _check_p02_predecessor(root, checks, hashes)
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
        for path in (
            GENERATOR_PATH,
            CORE_PATH,
            MODEL_REDTEAM_PATH,
            CROSS_MODEL_REVIEW_PATH,
            P02_EVIDENCE_PATH,
            ORACLE_PATH,
            TEST_PATH,
            FIXTURE_PATH,
        )
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S16-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S16_P03_REDTEAM_REVIEW_KEEP_P02_ZERO_WEIGHT_AND_NO_PROMOTION",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "model_weight_changed": False,
        "model_promotion_allowed": False,
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
        MODEL_REDTEAM_PATH,
        CROSS_MODEL_REVIEW_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        P02_EVIDENCE_PATH,
        Path("model_registry.json"),
        Path("eval_catalog.json"),
        Path("eval_report.json"),
        *[Path(relative) for relative in BASELINE_HASHES],
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
        "evidence_id": "EVD-S16-P03",
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
        "release_status": "S16_P03_LOCAL_SYNTHETIC_REDTEAM_ONLY_P04_REQUIRED",
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python model_redteam.py --root .",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S16/P03_test.py --junitxml=machine/evidence/S16/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S16/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S16/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S16-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"frozen_attack_count": 6, "cross_model_control_views": 2, "real_time_wait_performed": False},
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
        raise ModelRedteamAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S16/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise ModelRedteamAcceptanceError("S16/P03 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw + "\n").encode("utf-8")
        for raw, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ModelRedteamAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ModelRedteamAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S16/P04_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = acceptance_json_load(root / EVIDENCE_PATH)
    rollback = acceptance_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise ModelRedteamAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S16_P03_REDTEAM_AND_CROSS_MODEL_REVIEW_PASS_P04_REQUIRED"
        and evidence.get("next") == "S16/P04_READY_NOT_STARTED"
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
        and rollback.get("model_weight_changed") is False
        and rollback.get("model_promotion_allowed") is False
        and rollback.get("order_submission_enabled") is False
    )
    if not valid:
        raise ModelRedteamAcceptanceError("existing S16/P03 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S16/P04_READY_NOT_STARTED",
    }


__all__ = [
    "CONTRACT_ID",
    "CORE_PATH",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FEATURE_FLAG_ID",
    "FIXTURE_PATH",
    "ModelRedteamAcceptanceError",
    "ORACLE_PATH",
    "TEST_PATH",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
