"""Fail-closed, local-only whole-stage review oracle for ABD S15.

This local addendum replays the four already signed S15 Phase receipts and
their frozen artifacts.  It never re-runs a Phase test suite, full
regression, real-time soak, account operation, or product runtime.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .traceability_proxy import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S15"
REVIEW_ID = "ABD-S15-WHOLE-STAGE-REVIEW"
STAGE_ID = "S15"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage15_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S15/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S15_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S15/stage_review_test.py")
ORACLE_PATH = Path("abd_acceptance/stage15_review.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S15-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S15/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S15/STAGE_REVIEW/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")

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

PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    "P01": {
        "requirement_id": "REQ-S15-P01",
        "contract_id": "AC-S15-P01",
        "target": "关键模块分支覆盖≥95%，资金/阈值属性测试100%通过。",
        "task_scope": ["unit_tests", "property_tests", "schema_tests"],
        "outputs": ["unit_tests.json", "property_tests.json", "schema_tests.json"],
        "evidence_path": "machine/evidence/EVD-S15-P01.json",
        "evidence_sha256": "5ea76d98f26bb3225844a0e9ab62c58041647ca5e3337c4c722d7d842ddfc98a",
        "rollback_path": "machine/evidence/EVD-S15-P01_rollback.json",
        "rollback_sha256": "cd3b6d2d8e0934103e168c89758f24be727e996f65f86eead8e733ddb678854b",
        "decision": "S15_P01_CORRECTNESS_TEST_SURFACE_READY_P02_REQUIRED",
        "next": "S15/P02_READY_NOT_STARTED",
        "required_checks": (
            "S15P01-UNIT-CATALOG-EXACT",
            "S15P01-PROPERTY-CATALOG-EXACT",
            "S15P01-SCHEMA-CATALOG-EXACT",
            "S15P01-DECLARED-BRANCH-COVERAGE-AT-LEAST-95-PERCENT",
            "S15P01-FUNDS-AND-THRESHOLD-PROPERTIES-100-PERCENT",
            "S15P01-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY",
        ),
    },
    "P02": {
        "requirement_id": "REQ-S15-P02",
        "contract_id": "AC-S15-P02",
        "target": "真实网络故障不影响测试确定性。",
        "task_scope": ["contract_tests", "integration_tests", "fixtures_manifest.json"],
        "outputs": ["contract_tests.json", "integration_tests.json", "fixtures_manifest.json"],
        "evidence_path": "machine/evidence/EVD-S15-P02.json",
        "evidence_sha256": "b3e8c7f5eb604d19029ff23eb0f4c382ac194634a9fdc4fe8f44e998dde22521",
        "rollback_path": "machine/evidence/EVD-S15-P02_rollback.json",
        "rollback_sha256": "971bc1d3b8059d064cfa4b379c3978e557a0f328a8c26122d95b0f8d4826f499",
        "decision": "S15_P02_LOCAL_SOURCE_CONTRACT_INTEGRATION_READY_P03_REQUIRED",
        "next": "S15/P03_READY_NOT_STARTED",
        "required_checks": (
            "S15P02-CONTRACT-TESTS-EXACT",
            "S15P02-INTEGRATION-TESTS-EXACT",
            "S15P02-FIXTURES-MANIFEST-AND-HASHES-EXACT",
            "S15P02-SIMULATED-NETWORK-UNAVAILABLE-DETERMINISTIC-PROJECTION",
            "S15P02-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY",
        ),
    },
    "P03": {
        "requirement_id": "REQ-S15-P03",
        "contract_id": "AC-S15-P03",
        "target": "Golden/Black/Degraded/Recovery全通过。",
        "task_scope": ["e2e_tests", "environment_matrix.json", "e2e_evidence.json"],
        "outputs": ["e2e_tests.json", "environment_matrix.json", "e2e_evidence.json"],
        "evidence_path": "machine/evidence/EVD-S15-P03.json",
        "evidence_sha256": "c669a73781f28bb8fd1a5521f284c24f47bbe9595ad12f95ad9c47c27c809c29",
        "rollback_path": "machine/evidence/EVD-S15-P03_rollback.json",
        "rollback_sha256": "6761c0afe059c562d2147c0d1c731e3b9dc52f1d5dd6c71da08195554c99e258",
        "decision": "S15_P03_LOCAL_MULTI_SURFACE_E2E_READY_P04_REQUIRED",
        "next": "S15/P04_READY_NOT_STARTED",
        "required_checks": (
            "S15P03-E2E-TESTS-EXACT",
            "S15P03-ENVIRONMENT-MATRIX-AND-HASHES-EXACT",
            "S15P03-GOLDEN-BLACK-DEGRADED-RECOVERY-ALL-PASS",
            "S15P03-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY",
        ),
    },
    "P04": {
        "requirement_id": "REQ-S15-P04",
        "contract_id": "AC-S15-P04",
        "target": "无孤儿、无循环、无未通过关键验收。",
        "task_scope": ["traceability_validator.py", "software_gate.json"],
        "outputs": ["traceability_validator.py", "software_gate.json"],
        "evidence_path": "machine/evidence/EVD-S15-P04.json",
        "evidence_sha256": "3fd288e66d3c473881dc92257992eb41b85422a5c0aaa92f1ff00e202a15feda",
        "rollback_path": "machine/evidence/EVD-S15-P04_rollback.json",
        "rollback_sha256": "3d44192dc0724a4414608e4f2bd5363f5082ee041bb0d3e5c43ea835b36e5a13",
        "decision": "S15_P04_TRACEABILITY_GATE_PASS_STAGE_REVIEW_REQUIRED",
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_p04,
        "required_checks": (
            "S15P04-TASKPACK-SCOPE-TRACE-EXACT",
            "S15P04-NO-ORPHAN-OR-DUPLICATE-S15-CRITICAL-NODES",
            "S15P04-TASK-GRAPH-DEPENDENCIES-EXIST-AND-ACYCLIC",
            "S15P04-NO-UNPASSED-CRITICAL-ACCEPTANCE",
            "S15P04-ONE-IN-TEN-THOUSAND-BOUNDARY-CHAIN",
            "S15P04-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY",
        ),
    },
}

REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "SOFTWARE_CORRECTNESS_UNIT_PROPERTY_SCHEMA_GATE_PRESERVED",
    "SOURCE_CONTRACT_AND_SIMULATED_NETWORK_GATE_PRESERVED",
    "LOCAL_MULTI_SURFACE_GOLDEN_BLACK_DEGRADED_RECOVERY_GATE_PRESERVED",
    "TRACEABILITY_ORPHAN_CYCLE_AND_CRITICAL_ACCEPTANCE_GATE_PRESERVED",
    "NO_NETWORK_ACCOUNT_DATABASE_ORDER_DEPLOY_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_REVIEW_FINDINGS_RESOLVED",
    "NO_FULL_REGRESSION_EXECUTED",
]
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_rerun_allowed": False,
    "full_regression_or_real_time_soak_allowed": False,
    "single_pass_fixture_cases_only": True,
    "signed_phase_receipt_verification_mode": "PINNED_RECEIPT_HASH_INDEX_AND_CURRENT_CONTROL_ARTIFACTS",
    "github_upload_performed_by_local_review": False,
    "production_deployed_or_activated": False,
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "github_upload_performed_by_local_review": False,
    "remote_ci_result_claimed_by_local_review": False,
    "external_network_accessed_for_product_runtime": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "database_connection_opened": False,
    "browser_component_installed_or_run": False,
    "tab_or_provider_runtime_accessed": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_account_balance_read_or_written": False,
    "real_time_soak_waited": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "incremental_cash_spent_aud": "0.00",
    "owner_final_order_only": True,
}
FINDINGS_EXTERNAL_BOUNDARY = {
    "external_network_accessed": False,
    "github_upload_performed": False,
    "production_deployed_or_activated": False,
    "recommendation_generated": False,
    "order_submission_enabled": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
EXPLICIT_LIMITATIONS = [
    {
        "id": "S15-LOCAL-EVIDENCE-BOUNDARY",
        "status": "UNVERIFIED_OUT_OF_SCOPE",
        "statement": "S15 复审只证明冻结本地测试、来源合同、多表面配置与追踪证据链；不证明真实网络故障、浏览器、OVH、Cloudflare、TAB/Gmail、数据库、账户、订单、部署、上线或实际收益。",
    }
]
RESOLVED_FINDING = {
    "id": "F-S15-001-WHOLE-STAGE-REVIEW-CONTRACT-MISSING",
    "severity": "MEDIUM",
    "status": "RESOLVED",
    "affected_stage": "S15",
    "observed": "本 run 开始时 S15/P01--P04 已签名，但没有 S15 整阶段复审合同、夹具、判定器、测试、finding 或 stage-review 收据。",
    "remediation": "新增失败关闭的 S15 本地复审合同、单次固定快照、P01--P04 收据重放、静态边界检查和 stage-review 签名入口。",
    "verification": "仅以 tests/S15/stage_review_test.py、四份既有 Phase receipt verifier、依赖扫描、Task Pack 静态校验和本复审收据复验确认；不重跑 Phase 套件或全量回归。",
    "external_state_changed": False,
}
CONTINUITY_FINDING = {
    "id": "F-S15-002-LEGACY_CONTINUITY_S15_REVIEW_SUCCESSOR_UNDECLARED",
    "severity": "MEDIUM",
    "status": "RESOLVED",
    "affected_stage": "S15",
    "observed": "S15 stage-review 索引行首次写入后，S08 legacy compatibility 的单一复验暴露 S07 连续证据门仅精确承认到 S14，返回 S07P04-ALL-LINK-COLLECTIONS-COVERED 失败。",
    "remediation": "在既有 S07 连续证据失败关闭逻辑中加入仅接受当前签名 STAGE-REVIEW-S15 收据的 successor；仅刷新已在 S08 allow-list 中的 evidence_continuity.py 精确 SHA-256 及其既有 pins。",
    "verification": "tests/S08/stage_review_test.py::test_legacy_receipt_successor_compatibility_is_hash_pinned_and_replays 以一条定向 JUnit 收据复验；不运行 S08 全套、全量回归或真实时间 soak。",
    "external_state_changed": False,
}
RESOLVED_FINDINGS = [RESOLVED_FINDING, CONTINUITY_FINDING]
ADDENDUM_STATUS = "LOCAL_STAGE_REVIEW_CONTRACT_NOT_A_FROZEN_TASK_PACK_FACT"
SNAPSHOT_CASE_IDS = (
    "POSITIVE_EXACT_STAGE",
    "PHASE_RECEIPT_FAIL",
    "TASKPACK_TRACE_FAIL",
    "CORRECTNESS_GATE_FAIL",
    "SOURCE_CONTRACT_GATE_FAIL",
    "E2E_GATE_FAIL",
    "TRACEABILITY_GATE_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PORTABILITY_FAIL",
    "OPEN_FINDING_FAIL",
)
CONTROL_ARTIFACTS = (
    Path("unit_tests.json"),
    Path("property_tests.json"),
    Path("schema_tests.json"),
    Path("contract_tests.json"),
    Path("integration_tests.json"),
    Path("fixtures_manifest.json"),
    Path("e2e_tests.json"),
    Path("environment_matrix.json"),
    Path("e2e_evidence.json"),
    Path("traceability_validator.py"),
    Path("software_gate.json"),
    Path("abd_acceptance/software_correctness.py"),
    Path("abd_acceptance/source_contract_integration.py"),
    Path("abd_acceptance/e2e_multi_environment.py"),
    Path("abd_acceptance/traceability_proxy.py"),
)


class Stage15ReviewError(ValueError):
    """Raised when S15 whole-stage review evidence is malformed or stale."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


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
            raise Stage15ReviewError("blank JSONL row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise Stage15ReviewError("JSONL row %d is not an object" % number)
        rows.append(row)
    if not rows:
        raise Stage15ReviewError("JSONL is empty")
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage15ReviewError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage15ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _portable(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_portable(item) for item in value)
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return not (
            normalized.startswith("/")
            or normalized.startswith("file:")
            or "/Users/" in normalized
            or "/home/" in normalized
            or re.match(r"^[A-Za-z]:/", normalized) is not None
        )
    return True


def _phase_records() -> List[Dict[str, Any]]:
    return [
        {
            "phase_id": phase,
            "requirement_id": spec["requirement_id"],
            "acceptance_contract_id": spec["contract_id"],
            "target": spec["target"],
            "outputs": spec["outputs"],
            "evidence_path": spec["evidence_path"],
            "evidence_sha256": spec["evidence_sha256"],
            "rollback_path": spec["rollback_path"],
            "rollback_sha256": spec["rollback_sha256"],
            "expected_decision": spec["decision"],
            "expected_next": spec["next"],
        }
        for phase, spec in PHASE_SPECS.items()
    ]


def _review_scope() -> Dict[str, Any]:
    return {
        "phase_ids": list(PHASE_SPECS),
        "requirement_ids": [spec["requirement_id"] for spec in PHASE_SPECS.values()],
        "acceptance_contract_ids": [spec["contract_id"] for spec in PHASE_SPECS.values()],
        "task_ids": ["T-S15-%s-%02d" % (phase, number) for phase in PHASE_SPECS for number in (1, 2, 3)],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one immutable S15 review snapshot without enabling action."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "correctness_gate_preserved",
        "source_contract_gate_preserved",
        "e2e_gate_preserved",
        "traceability_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage15ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage15ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage15ReviewError("findings_open must be a nonnegative integer")
    reason_map = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("correctness_gate_preserved", "SOFTWARE_CORRECTNESS_GATE_RELAXED"),
        ("source_contract_gate_preserved", "SOURCE_CONTRACT_OR_SIMULATED_NETWORK_GATE_RELAXED"),
        ("e2e_gate_preserved", "MULTI_SURFACE_E2E_GATE_RELAXED"),
        ("traceability_gate_preserved", "TRACEABILITY_OR_CRITICAL_ACCEPTANCE_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S15_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S15_STAGE_REVIEW_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def _check_contract(contract: Any, fixture: Any, findings: Any, checks: List[Dict[str, Any]]) -> None:
    if not isinstance(contract, Mapping) or not isinstance(fixture, Mapping) or not isinstance(findings, Mapping):
        _add(checks, "S15REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "stage_review_addendum": ADDENDUM_STATUS,
        "targeted_test_command": "pytest -q tests/S15/stage_review_test.py",
        "release_status_on_pass": "S15_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S15/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S15/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S15REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S15REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S15REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S15REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S15REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S15REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S15-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": len(SNAPSHOT_CASE_IDS),
        "minimum_targeted_pytest_cases": 18,
        "expected_phase_ids": list(PHASE_SPECS),
        "expected_phase_evidence_sha256": {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_phase_rollback_sha256": {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_next": "S15/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S15_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 2, "open": 0, "resolved": 2, "blocked": 0},
    }
    _add(checks, "S15REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S15REVIEW-SINGLE-PASS-CASES-EXACT",
        isinstance(cases, list)
        and [case.get("case_id") for case in cases if isinstance(case, Mapping)] == list(SNAPSHOT_CASE_IDS),
        [case.get("case_id") for case in cases] if isinstance(cases, list) else cases,
    )
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_clock") == FIXED_CLOCK
        and findings.get("findings") == RESOLVED_FINDINGS
        and findings.get("summary") == fixture_identity["expected_findings_summary"]
        and findings.get("explicit_limitations") == EXPLICIT_LIMITATIONS
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
    )
    _add(checks, "S15REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    passed = True
    for relative, expected in BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            item_ok = actual == expected
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            item_ok = False
        _add(checks, "S15REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), item_ok, {"expected": expected, "actual": actual})
        passed = passed and item_ok
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S15REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S15REVIEW-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S15REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S15REVIEW-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S15REVIEW-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        index = []
        _add(checks, "S15REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(traceability, list) or not isinstance(graph, Mapping):
        _add(checks, "S15REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-CLOSED", False, "task-pack collections unavailable")
        return False
    try:
        task_rows = [row for row in graph.get("tasks", []) if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID]
        task_map = {row.get("id"): row for row in task_rows}
        valid = True
        detail: Dict[str, Any] = {}
        for phase, spec in PHASE_SPECS.items():
            requirement = _row(requirements, spec["requirement_id"])
            contract = _row(contracts, spec["contract_id"])
            trace = _row(traceability, spec["requirement_id"], key="requirement_id")
            phase_task_ids = ["T-S15-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            index_row = _row(index, "INDEX-" + spec["contract_id"])
            phase_ok = (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("target") == spec["target"]
                and requirement.get("scope") == spec["task_scope"]
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and contract.get("requirement_id") == spec["requirement_id"]
                and contract.get("pass_gate") == spec["target"]
                and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % spec["contract_id"]
                and all(task_id in task_map for task_id in phase_task_ids)
                and all(task_map[task_id].get("phase_id") == phase for task_id in phase_task_ids)
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == phase_task_ids
                and trace.get("test_ids") == ["TEST-S15-%s" % phase, "TEST-S15-%s-BOUNDARY" % phase, "TEST-S15-%s-REPLAY" % phase]
                and trace.get("evidence_id") == "EVD-S15-%s" % phase
                and index_row.get("kind") == "PHASE_EVIDENCE"
                and index_row.get("contract_id") == spec["contract_id"]
                and index_row.get("artifact_sha256") == spec["evidence_sha256"]
            )
            detail[phase] = phase_ok
            valid = valid and phase_ok
    except Exception as exc:
        valid = False
        detail = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(checks, "S15REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-CLOSED", valid, detail)
    return valid


def _all_validation_checks_pass(receipt: Mapping[str, Any]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, Mapping) and row.get("passed") is True for row in rows)


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    receipts: Dict[str, Mapping[str, Any]] = {}
    all_ok = True
    for phase, spec in PHASE_SPECS.items():
        try:
            receipt = strict_json_load(root / spec["evidence_path"])
            rollback = strict_json_load(root / spec["rollback_path"])
            index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-" + spec["contract_id"])
            validation = receipt.get("validation") if isinstance(receipt, Mapping) else None
            rows = validation.get("checks") if isinstance(validation, Mapping) else None
            passed_ids = {row.get("id") for row in rows if isinstance(row, Mapping) and row.get("passed") is True} if isinstance(rows, list) else set()
            boundary = receipt.get("external_effect_boundary") if isinstance(receipt, Mapping) else None
            generic_boundary = (
                isinstance(boundary, Mapping)
                and all(value is False for key, value in boundary.items() if key != "incremental_cash_spent_aud")
                and boundary.get("incremental_cash_spent_aud") == "0.00"
            )
            receipt_replay_mode = "PINNED_RECEIPT_HASH_INDEX_AND_CURRENT_CONTROL_ARTIFACTS"
            result = {
                "contract_id": spec["contract_id"],
                "status": "PASS",
                "evidence_path": spec["evidence_path"],
                "evidence_sha256": spec["evidence_sha256"],
                "next": spec["next"],
                "verification_mode": receipt_replay_mode,
            }
            if phase == "P04":
                p04_result = verify_p04(root)
                result = {
                    **p04_result,
                    "verification_mode": "P04_NONRECURSIVE_TRACEABILITY_RECEIPT_REPLAY",
                }
            valid = (
                result.get("status") == "PASS"
                and isinstance(receipt, Mapping)
                and receipt.get("contract_id") == spec["contract_id"]
                and receipt.get("requirement_id") == spec["requirement_id"]
                and receipt.get("stage_id") == STAGE_ID
                and receipt.get("phase_id") == phase
                and receipt.get("status") == "PASS"
                and validation.get("status") == "PASS"
                and receipt.get("decision") == spec["decision"]
                and receipt.get("next") == spec["next"]
                and receipt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
                and receipt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
                and sha256_file(root / spec["evidence_path"]) == spec["evidence_sha256"]
                and isinstance(rollback, Mapping)
                and rollback.get("status") == "PASS"
                and rollback.get("external_state_changed") is False
                and rollback.get("production_state_changed") is False
                and rollback.get("real_time_soak_waited") is False
                and sha256_file(root / spec["rollback_path"]) == spec["rollback_sha256"]
                and index.get("kind") == "PHASE_EVIDENCE"
                and index.get("status") == "PASS"
                and index.get("artifact_sha256") == spec["evidence_sha256"]
                and set(spec["required_checks"]) <= passed_ids
                and _all_validation_checks_pass(receipt)
                and generic_boundary
            )
            detail: Any = {
                "contract_id": result.get("contract_id"),
                "status": result.get("status"),
                "evidence_path": result.get("evidence_path"),
                "evidence_sha256": result.get("evidence_sha256"),
                "next": result.get("next"),
                "verification_mode": result.get("verification_mode"),
            }
            receipts[phase] = receipt if isinstance(receipt, Mapping) else {}
            hashes[spec["evidence_path"]] = sha256_file(root / spec["evidence_path"])
            hashes[spec["rollback_path"]] = sha256_file(root / spec["rollback_path"])
        except Exception as exc:
            valid = False
            detail = "%s: %s" % (type(exc).__name__, exc)
            receipts[phase] = {}
        _add(checks, "S15REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, valid, detail)
        all_ok = all_ok and valid
    return all_ok, receipts


def _check_stage_controls(root: Path, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> Dict[str, bool]:
    try:
        unit = strict_json_load(root / "unit_tests.json")
        properties = strict_json_load(root / "property_tests.json")
        schema = strict_json_load(root / "schema_tests.json")
        p01_artifact_ok = (
            unit.get("contract_id") == "AC-S15-P01"
            and unit.get("minimum_branch_coverage") == "0.9500"
            and len(unit.get("required_branch_ids", [])) == 17
            and len(unit.get("case_ids", [])) == 7
            and properties.get("contract_id") == "AC-S15-P01"
            and len(properties.get("properties", [])) == 4
            and properties.get("property_pass_threshold") == "1.0000"
            and properties.get("required_adverse_delta") == "-0.0001"
            and schema.get("contract_id") == "AC-S15-P01"
            and schema.get("synthetic_test_only_required") is True
        )
    except Exception:
        p01_artifact_ok = False
    p01 = _all_validation_checks_pass(receipts.get("P01", {})) and p01_artifact_ok
    _add(checks, "S15REVIEW-SOFTWARE-CORRECTNESS-UNIT-PROPERTY-SCHEMA-GATE", p01, {"artifact_contract": p01_artifact_ok})

    try:
        contract_tests = strict_json_load(root / "contract_tests.json")
        integration_tests = strict_json_load(root / "integration_tests.json")
        manifest = strict_json_load(root / "fixtures_manifest.json")
        p02_artifact_ok = (
            contract_tests.get("contract_id") == "AC-S15-P02"
            and len(contract_tests.get("source_contracts", [])) == 4
            and integration_tests.get("contract_id") == "AC-S15-P02"
            and len(integration_tests.get("cases", [])) == 7
            and integration_tests.get("network_modes") == ["LOCAL_FIXTURE_REPLAY", "SIMULATED_NETWORK_UNAVAILABLE"]
            and integration_tests.get("outage_equivalence", {}).get("deterministic_projection_must_match") is True
            and integration_tests.get("outage_equivalence", {}).get("real_network_outage_exercised") is False
            and manifest.get("contract_id") == "AC-S15-P02"
            and len(manifest.get("fixtures", [])) == 4
        )
    except Exception:
        p02_artifact_ok = False
    p02 = _all_validation_checks_pass(receipts.get("P02", {})) and p02_artifact_ok
    _add(checks, "S15REVIEW-SOURCE-CONTRACT-AND-SIMULATED-NETWORK-GATE", p02, {"artifact_contract": p02_artifact_ok})

    try:
        e2e_tests = strict_json_load(root / "e2e_tests.json")
        matrix = strict_json_load(root / "environment_matrix.json")
        e2e_evidence = strict_json_load(root / "e2e_evidence.json")
        p03_artifact_ok = (
            e2e_tests.get("contract_id") == "AC-S15-P03"
            and len(e2e_tests.get("scenarios", [])) == 6
            and e2e_tests.get("journey_classes") == ["GOLDEN", "BLACK", "DEGRADED", "RECOVERY"]
            and matrix.get("contract_id") == "AC-S15-P03"
            and len(matrix.get("environments", [])) == 6
            and matrix.get("execution_policy", {}).get("external_runtime_access_allowed") is False
            and e2e_evidence.get("contract_id") == "AC-S15-P03"
            and len(e2e_evidence.get("expected_outcomes", [])) == 6
            and len(e2e_evidence.get("structured_logs", [])) == 6
            and e2e_evidence.get("claim_boundary", {}).get("actual_ovh_host_exercised") is False
            and e2e_evidence.get("claim_boundary", {}).get("actual_cloudflare_edge_exercised") is False
            and e2e_evidence.get("claim_boundary", {}).get("actual_desktop_or_mobile_browser_exercised") is False
            and e2e_evidence.get("claim_boundary", {}).get("external_network_accessed") is False
        )
    except Exception:
        p03_artifact_ok = False
    p03 = _all_validation_checks_pass(receipts.get("P03", {})) and p03_artifact_ok
    _add(checks, "S15REVIEW-LOCAL-MULTI-SURFACE-GOLDEN-BLACK-DEGRADED-RECOVERY-GATE", p03, {"artifact_contract": p03_artifact_ok})

    try:
        gate = strict_json_load(root / "software_gate.json")
        p04_artifact_ok = (
            gate.get("contract_id") == "AC-S15-P04"
            and gate.get("scope", {}).get("critical_phase_ids") == ["P01", "P02", "P03", "P04"]
            and gate.get("scope", {}).get("next_gate") == CONTRACT_ID
            and len(gate.get("critical_chain", [])) == 4
            and len(gate.get("gate_definitions", [])) == 7
            and gate.get("boundary", {}).get("delta") == "0.0001"
            and gate.get("boundary", {}).get("adverse_must_fail_closed") is True
            and gate.get("external_effect_boundary", {}).get("database_connection_opened") is False
        )
    except Exception:
        p04_artifact_ok = False
    p04 = _all_validation_checks_pass(receipts.get("P04", {})) and p04_artifact_ok
    _add(checks, "S15REVIEW-TRACEABILITY-ORPHAN-CYCLE-CRITICAL-ACCEPTANCE-GATE", p04, {"artifact_contract": p04_artifact_ok})
    return {"p01": p01, "p02": p02, "p03": p03, "p04": p04}


def _check_external_boundary(contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    receipt_boundaries = [receipt.get("external_effect_boundary") for receipt in receipts.values() if isinstance(receipt, Mapping)]
    receipts_ok = len(receipt_boundaries) == len(PHASE_SPECS) and all(
        isinstance(boundary, Mapping)
        and boundary.get("external_network_accessed") is False
        and boundary.get("gmail_account_or_api_accessed") is False
        and boundary.get("recommendation_generated_or_enabled") is False
        and boundary.get("order_submitted_confirmed_or_retried") is False
        and boundary.get("production_deployed_or_activated") is False
        and boundary.get("real_time_soak_waited") is False
        and boundary.get("incremental_cash_spent_aud") == "0.00"
        for boundary in receipt_boundaries
    )
    if isinstance(receipts.get("P04"), Mapping):
        p04_boundary = receipts["P04"].get("external_effect_boundary")
        receipts_ok = receipts_ok and isinstance(p04_boundary, Mapping) and all(
            p04_boundary.get(key) is False
            for key in (
                "ovh_account_or_host_accessed",
                "cloudflare_account_dns_or_tunnel_accessed",
                "database_connection_opened",
                "desktop_or_mobile_browser_exercised",
                "browser_component_installed_or_run",
                "tab_or_provider_runtime_accessed",
            )
        )
    valid = (
        isinstance(contract, Mapping)
        and contract.get("execution_policy") == EXECUTION_POLICY
        and isinstance(findings, Mapping)
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
        and receipts_ok
    )
    _add(checks, "S15REVIEW-NO-NETWORK-ACCOUNT-DATABASE-ORDER-DEPLOY-OR-SOAK-BOUNDARY", valid, {"phase_receipts": receipts_ok})
    return valid


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S15REVIEW-SNAPSHOT-CASES-REPLAY", False, "cases unavailable")
        return False
    outcomes = []
    try:
        for case in cases:
            if not isinstance(case, Mapping):
                raise Stage15ReviewError("snapshot case is malformed")
            result = evaluate_stage_snapshot(case["snapshot"])
            expected = case["expected"]
            case_ok = (
                result.get("status") == expected.get("status")
                and result.get("reason_codes") == expected.get("reason_codes")
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_network_used") is False
                and result.get("real_time_soak_waited") is False
            )
            outcomes.append(case_ok)
        valid = all(outcomes) and len(outcomes) == len(SNAPSHOT_CASE_IDS)
    except Exception as exc:
        valid = False
        outcomes = ["%s: %s" % (type(exc).__name__, exc)]
    _add(checks, "S15REVIEW-SNAPSHOT-CASES-REPLAY", valid, outcomes)
    return valid


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> bool:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden_imports = {"asyncio", "http", "os", "requests", "socket", "subprocess", "time", "urllib", "webbrowser"}
        call_names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        valid = not imported & forbidden_imports and not call_names & {"Popen", "sleep", "submit_order"}
        detail: Any = {"imports": sorted(imported), "forbidden": sorted(imported & forbidden_imports)}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S15REVIEW-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", valid, detail)
    return valid


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        _add(checks, "S15REVIEW-TARGETED-REPORTS", True, "deferred until local signing")
        return True
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        document = ElementTree.parse(root / JUNIT_PATH).getroot()
        suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
        junit_ok = (
            summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and summary["failures"] == 0
            and summary["errors"] == 0
            and summary["skipped"] == 0
            and all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK for suite in suites)
        )
    except Exception as exc:
        summary = "%s: %s" % (type(exc).__name__, exc)
        junit_ok = False
    _add(checks, "S15REVIEW-TARGETED-PYTEST-REPORT", junit_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(
            marker in scan
            for marker in (
                "STATUS: PASS",
                "MAX_INCREMENTAL_CASH_AUD: 0.00",
                "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
                "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
                "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
            )
        )
    except Exception as exc:
        scan = "%s: %s" % (type(exc).__name__, exc)
        scan_ok = False
    _add(checks, "S15REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary_value = report.get("summary") if isinstance(report, Mapping) else None
        pack_ok = (
            isinstance(report, Mapping)
            and report.get("status") == "PASS"
            and isinstance(summary_value, Mapping)
            and summary_value.get("failed") == 0
            and summary_value.get("passed") == summary_value.get("checks")
        )
    except Exception as exc:
        summary_value = "%s: %s" % (type(exc).__name__, exc)
        pack_ok = False
    _add(checks, "S15REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, summary_value)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": status,
        "stage_status": "S15_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S15_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S15_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S15_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S15/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S15/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate current local S15 review state without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, CONTRACT_PATH, checks, "S15REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S15REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, FINDINGS_PATH, checks, "S15REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, receipts, checks)
    boundary_ok = _check_external_boundary(contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = all(_portable(value) for value in (contract, fixture, findings, *receipts.values()))
    _add(checks, "S15REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "local path detected")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "correctness_gate_preserved": controls["p01"],
        "source_contract_gate_preserved": controls["p02"],
        "e2e_gate_preserved": controls["p03"],
        "traceability_gate_preserved": controls["p04"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S15REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S15_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _add(checks, "S15REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
    return _result(checks, hashes, snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    review_paths = (CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, *CONTROL_ARTIFACTS)
    phase_paths = tuple(Path(spec["evidence_path"]) for spec in PHASE_SPECS.values()) + tuple(Path(spec["rollback_path"]) for spec in PHASE_SPECS.values())
    artifacts = {
        path.as_posix(): {
            "status": "PASS" if (root / path).is_file() else "FAIL",
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
        }
        for path in (*review_paths, *phase_paths)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "CLOSE_S15_REVIEW_CANDIDATE_PRESERVE_SIGNED_PHASE_EVIDENCE_NO_EXTERNAL_MUTATION",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "database_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = set(BASELINE_HASHES)
    paths.update({CONTRACT_PATH.as_posix(), FINDINGS_PATH.as_posix(), FIXTURE_PATH.as_posix(), TEST_PATH.as_posix(), ORACLE_PATH.as_posix()})
    paths.update(path.as_posix() for path in CONTROL_ARTIFACTS)
    for spec in PHASE_SPECS.values():
        paths.add(spec["evidence_path"])
        paths.add(spec["rollback_path"])
    if require_test_reports:
        paths.update({JUNIT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix(), PACK_REPORT_PATH.as_posix()})
    return {relative: sha256_file(root / relative) for relative in sorted(paths)}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = dict(evidence)
    payload.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    findings = strict_json_load(root / FINDINGS_PATH)
    snapshot_result = evaluate_stage_snapshot(validation["snapshot"])
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S15_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S15_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "review_limitations": findings.get("explicit_limitations") if isinstance(findings, Mapping) else [],
        "findings_summary": findings.get("summary") if isinstance(findings, Mapping) else {},
        "stage_snapshot_summary": {
            "status": snapshot_result["status"],
            "reason_codes": snapshot_result["reason_codes"],
            "real_time_waited": False,
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S15/stage_review_test.py --junitxml=machine/evidence/S15/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S15/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S15/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S15 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "validation": validation,
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
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
        "id": "INDEX-S15-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S15/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    positions = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) > 1:
        raise Stage15ReviewError("duplicate S15 stage-review evidence index rows")
    if positions:
        output = [
            _jsonl_bytes(replacement) if number == positions[0] else (line + "\n").encode("utf-8")
            for number, line in enumerate(raw_lines)
        ]
    else:
        output = [(line + "\n").encode("utf-8") for line in raw_lines] + [_jsonl_bytes(replacement)]
    _atomic_write(path, b"".join(output))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage15ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage15ReviewError("cannot write evidence for a failed S15 review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": evidence["next"],
    }


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-S15-STAGE-REVIEW")
    except Exception as exc:
        raise Stage15ReviewError("existing S15 stage-review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S15-STAGE-REVIEW"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("stage_status") == "S15_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("decision") == "S15_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S15/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S15_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("findings_summary") == {"total": 2, "open": 0, "resolved": 2, "blocked": 0}
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("database_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and index.get("kind") == "STAGE_REVIEW_EVIDENCE"
        and index.get("contract_id") == CONTRACT_ID
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S15/GITHUB_STAGE_UPLOAD_READY"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise Stage15ReviewError("existing S15 stage-review evidence does not replay exactly")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S15/GITHUB_STAGE_UPLOAD_READY",
    }


__all__ = [
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINDINGS_PATH",
    "FIXTURE_PATH",
    "PHASE_SPECS",
    "ROLLBACK_EVIDENCE_PATH",
    "Stage15ReviewError",
    "build_evidence",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
