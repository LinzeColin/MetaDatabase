"""Fail-closed, local-only whole-stage review oracle for ABD S14.

The review consumes the four already signed S14 Phase receipts and their
frozen artifacts. It records one resolved provenance-boundary finding, never
claims production release, and does not re-run any Phase test suite, full
regression, real-time soak, account operation, or external runtime.
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
from .component_governance import verify_existing_phase_evidence as verify_p03
from .security_analysis import verify_existing_phase_evidence as verify_p02
from .threat_model import verify_existing_phase_evidence as verify_p01
from .artifact_provenance import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S14"
REVIEW_ID = "ABD-S14-WHOLE-STAGE-REVIEW"
STAGE_ID = "S14"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage14_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S14/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S14_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S14/stage_review_test.py")
ORACLE_PATH = Path("abd_acceptance/stage14_review.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S14-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S14/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S14/STAGE_REVIEW/paid_dependency_scan.txt")
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
        "requirement_id": "REQ-S14-P01",
        "contract_id": "AC-S14-P01",
        "target": "高风险威胁均有预防、检测、响应和恢复控制。",
        "outputs": ["threat_model.json", "trust_boundaries.json", "abuse_cases.json"],
        "evidence_path": "machine/evidence/EVD-S14-P01.json",
        "evidence_sha256": "91d353c7e3f850119cbc755936c4023537c6870ec3f1a384346bc1875aa90a8c",
        "rollback_path": "machine/evidence/EVD-S14-P01_rollback.json",
        "rollback_sha256": "feba53995af01741678c252fb0f2a2d58af4a3a37f5b558f70a94549354463c0",
        "decision": "THREAT_MODEL_AND_TRUST_BOUNDARIES_READY_SECURITY_REMEDIATION_REQUIRED_BEFORE_PRODUCTION",
        "next": "S14/P02_READY_NOT_STARTED",
        "verifier": verify_p01,
        "required_checks": (
            "S14P01-HIGH-THREAT-MODEL-EXACT",
            "S14P01-EVERY-HIGH-THREAT-HAS-PREVENT-DETECT-RESPOND-RECOVER",
            "S14P01-NO-NETWORK-ACCOUNT-ORDER-DEPLOY-OR-SOAK-BOUNDARY",
        ),
    },
    "P02": {
        "requirement_id": "REQ-S14-P02",
        "contract_id": "AC-S14-P02",
        "target": "未处置严重/高危为0。",
        "outputs": ["security_pipeline.yml", "sast_policy.json", "secret_policy.json"],
        "evidence_path": "machine/evidence/EVD-S14-P02.json",
        "evidence_sha256": "ef081da80f4b8d690dcc396cf762d5998d761136a95bd04dd5ece0c942d4fee9",
        "rollback_path": "machine/evidence/EVD-S14-P02_rollback.json",
        "rollback_sha256": "1000e28224fb747657065d500cc903560ed0bcc97ee7a8ebd8665b251c0f0d70",
        "decision": "SECURITY_PIPELINE_READY_UNRESOLVED_CRITICAL_OR_HIGH_FINDINGS_ZERO_LOCAL_ONLY",
        "next": "S14/P03_READY_NOT_STARTED",
        "verifier": verify_p02,
        "required_checks": (
            "S14P02-SECURITY-PIPELINE-EXACT",
            "S14P02-SAST-POLICY-EXACT",
            "S14P02-SECRET-POLICY-EXACT",
            "S14P02-STATIC-ANALYSIS-UNRESOLVED-CRITICAL-HIGH-ZERO",
        ),
    },
    "P03": {
        "requirement_id": "REQ-S14-P03",
        "contract_id": "AC-S14-P03",
        "target": "每个生产组件有来源、版本、许可证和负责人。",
        "outputs": ["sbom.json", "component_governance.json", "patch_sla.json"],
        "evidence_path": "machine/evidence/EVD-S14-P03.json",
        "evidence_sha256": "5d0644b143115c6cdd99eb8774b8f8cbc68a618ba86b82772ff6797e7293708c",
        "rollback_path": "machine/evidence/EVD-S14-P03_rollback.json",
        "rollback_sha256": "39437e5a68e6cb86bc6a4122bcda763b501be4196d2973a64c0d2a2b2c8d64b2",
        "decision": "COMPONENT_METADATA_COMPLETE_LOCAL_ONLY_P04_PROVENANCE_REQUIRED",
        "next": "S14/P04_READY_NOT_STARTED",
        "verifier": verify_p03,
        "required_checks": (
            "S14P03-SBOM-EXACT",
            "S14P03-COMPONENT-GOVERNANCE-EXACT",
            "S14P03-PATCH-SLA-EXACT",
        ),
    },
    "P04": {
        "requirement_id": "REQ-S14-P04",
        "contract_id": "AC-S14-P04",
        "target": "发布制品可追溯到源代码、依赖和构建环境。",
        "outputs": ["provenance.json", "artifact_signing.md", "security_rollback.md"],
        "evidence_path": "machine/evidence/EVD-S14-P04.json",
        "evidence_sha256": "820f5a1c13f788386c54af8d18551bd6bd40d7816d659c6ffd43a657c25ddf4b",
        "rollback_path": "machine/evidence/EVD-S14-P04_rollback.json",
        "rollback_sha256": "0b3bfaa1bccf0dccb77afea4f6c44b3eab670d5e0af5d07bc5a1ff73aaef68b5",
        "decision": "LOCAL_PRE_RELEASE_PROVENANCE_COMPLETE_STAGE_REVIEW_REQUIRED",
        "next": "S14/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_p04,
        "required_checks": (
            "S14P04-PROVENANCE-EXACT",
            "S14P04-SIGNING-POLICY-EXACT",
            "S14P04-ROLLBACK-POLICY-EXACT",
        ),
    },
}

REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "THREAT_TRUST_ABUSE_SECURITY_REMEDIATION_GATE_PRESERVED",
    "OFFLINE_SECURITY_PIPELINE_AND_ZERO_HIGH_CRITICAL_GATE_PRESERVED",
    "COMPONENT_METADATA_UNADMITTED_RUNTIME_AND_PATCH_GATE_PRESERVED",
    "PROVENANCE_LOCAL_ATTESTATION_NOT_RELEASE_SIGNATURE_GATE_PRESERVED",
    "NO_NETWORK_ACCOUNT_ORDER_DEPLOY_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_REVIEW_FINDINGS_RESOLVED",
    "NO_FULL_REGRESSION_EXECUTED",
]
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "phase_test_rerun_allowed": False,
    "full_regression_or_real_time_soak_allowed": False,
    "single_pass_fixture_cases_only": True,
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
    "model_or_strategy_executed": False,
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
        "id": "S14-LOCAL-EVIDENCE-BOUNDARY",
        "status": "UNVERIFIED_OUT_OF_SCOPE",
        "statement": "S14 复审只证明冻结本地安全、组件和制品来源证据链；不证明真实渗透测试、实时漏洞、签名密钥、制品注册表、OVH、Cloudflare、TAB/Gmail、账户、订单、部署、上线或实际收益。",
    }
]
RESOLVED_FINDING = {
    "id": "F-S14-001-SHARED-DISPATCHER-PROVENANCE",
    "severity": "MEDIUM",
    "status": "RESOLVED",
    "affected_phase": "P04",
    "impact": "共享 CLI 编排入口若被计入 P04 phase-owned 哈希，后续复审入口变更会错误地使已签名 P04 收据失效。",
    "root_cause": "P04 初始来源闭包把 abd_acceptance/__main__.py 误归属为 phase-owned 输入。",
    "remediation": "从 P04 phase-owned source_inputs 与 receipt input hashes 中剥离共享 dispatcher；保留 P04 自身判定器、夹具、测试、依赖和制品哈希，并重签 P04。",
    "verification": "P04 定向测试 42 passed；AC-S14-P04 重签后 receipt 与本复审均重新验证。",
    "external_state_changed": False,
}
SNAPSHOT_CASE_IDS = (
    "POSITIVE_EXACT_STAGE",
    "PHASE_RECEIPT_FAIL",
    "TASKPACK_TRACE_FAIL",
    "THREAT_GATE_FAIL",
    "SECURITY_PIPELINE_GATE_FAIL",
    "COMPONENT_GOVERNANCE_GATE_FAIL",
    "PROVENANCE_GATE_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PORTABILITY_FAIL",
    "OPEN_FINDING_FAIL",
)
CONTROL_ARTIFACTS = (
    Path("threat_model.json"),
    Path("trust_boundaries.json"),
    Path("abuse_cases.json"),
    Path("security_pipeline.yml"),
    Path("sast_policy.json"),
    Path("secret_policy.json"),
    Path("sbom.json"),
    Path("component_governance.json"),
    Path("patch_sla.json"),
    Path("provenance.json"),
    Path("artifact_signing.md"),
    Path("security_rollback.md"),
)


class Stage14ReviewError(ValueError):
    """Raised when S14 whole-stage review evidence is malformed or stale."""


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
            raise Stage14ReviewError("blank JSONL row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise Stage14ReviewError("JSONL row %d is not an object" % number)
        rows.append(row)
    if not rows:
        raise Stage14ReviewError("JSONL is empty")
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage14ReviewError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage14ReviewError("expected exactly one %s=%s" % (key, identifier))
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
        "task_ids": ["T-S14-%s-%02d" % (phase, number) for phase in PHASE_SPECS for number in (1, 2, 3)],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one immutable S14 review snapshot without enabling action."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "threat_gate_preserved",
        "security_pipeline_gate_preserved",
        "component_governance_gate_preserved",
        "provenance_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage14ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage14ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage14ReviewError("findings_open must be a nonnegative integer")
    reason_map = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("threat_gate_preserved", "THREAT_TRUST_ABUSE_GATE_RELAXED"),
        ("security_pipeline_gate_preserved", "SECURITY_PIPELINE_OR_FINDING_GATE_RELAXED"),
        ("component_governance_gate_preserved", "COMPONENT_GOVERNANCE_OR_RUNTIME_ADMISSION_GATE_RELAXED"),
        ("provenance_gate_preserved", "PROVENANCE_OR_LOCAL_ATTESTATION_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S14_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S14_STAGE_REVIEW_REJECTED_NO_ACTION",
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
        _add(checks, "S14REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "targeted_test_command": "pytest -q tests/S14/stage_review_test.py",
        "release_status_on_pass": "S14_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S14/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S14/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S14REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S14REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S14REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S14REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S14REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S14REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S14-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": len(SNAPSHOT_CASE_IDS),
        "minimum_targeted_pytest_cases": 30,
        "expected_phase_ids": list(PHASE_SPECS),
        "expected_phase_evidence_sha256": {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_phase_rollback_sha256": {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_next": "S14/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S14_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 1, "open": 0, "resolved": 1, "blocked": 0},
    }
    _add(checks, "S14REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S14REVIEW-SINGLE-PASS-CASES-EXACT",
        isinstance(cases, list)
        and [case.get("case_id") for case in cases if isinstance(case, Mapping)] == list(SNAPSHOT_CASE_IDS),
        [case.get("case_id") for case in cases] if isinstance(cases, list) else cases,
    )
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_clock") == FIXED_CLOCK
        and findings.get("findings") == [RESOLVED_FINDING]
        and findings.get("summary") == fixture_identity["expected_findings_summary"]
        and findings.get("explicit_limitations") == EXPLICIT_LIMITATIONS
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
    )
    _add(checks, "S14REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


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
        _add(checks, "S14REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), item_ok, {"expected": expected, "actual": actual})
        passed = passed and item_ok
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S14REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S14REVIEW-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S14REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S14REVIEW-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S14REVIEW-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        index = []
        _add(checks, "S14REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(traceability, list) or not isinstance(graph, Mapping):
        _add(checks, "S14REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-CLOSED", False, "task-pack collections unavailable")
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
            phase_task_ids = ["T-S14-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            index_row = _row(index, "INDEX-" + spec["contract_id"])
            phase_ok = (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("target") == spec["target"]
                and requirement.get("scope") == spec["outputs"]
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and contract.get("requirement_id") == spec["requirement_id"]
                and contract.get("pass_gate") == spec["target"]
                and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % spec["contract_id"]
                and all(task_id in task_map for task_id in phase_task_ids)
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == phase_task_ids
                and trace.get("evidence_id") == "EVD-S14-%s" % phase
                and index_row.get("kind") == "PHASE_EVIDENCE"
                and index_row.get("contract_id") == spec["contract_id"]
                and index_row.get("artifact_sha256") == spec["evidence_sha256"]
            )
            detail[phase] = phase_ok
            valid = valid and phase_ok
    except Exception as exc:
        valid = False
        detail = {"error": "%s: %s" % (type(exc).__name__, exc)}
    _add(checks, "S14REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-CLOSED", valid, detail)
    return valid


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    receipts: Dict[str, Mapping[str, Any]] = {}
    all_ok = True
    for phase, spec in PHASE_SPECS.items():
        try:
            result = spec["verifier"](root)
            receipt = strict_json_load(root / spec["evidence_path"])
            rollback = strict_json_load(root / spec["rollback_path"])
            index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-" + spec["contract_id"])
            validation = receipt.get("validation") if isinstance(receipt, Mapping) else None
            rows = validation.get("checks") if isinstance(validation, Mapping) else None
            passed_ids = {row.get("id") for row in rows if isinstance(row, Mapping) and row.get("passed") is True} if isinstance(rows, list) else set()
            generic_boundary = (
                isinstance(receipt, Mapping)
                and isinstance(receipt.get("external_effect_boundary"), Mapping)
                and receipt["external_effect_boundary"].get("external_network_accessed") is False
                and receipt["external_effect_boundary"].get("order_submitted_confirmed_or_retried") is False
                and receipt["external_effect_boundary"].get("production_deployed_or_activated") is False
                and receipt["external_effect_boundary"].get("real_time_soak_waited") is False
                and receipt["external_effect_boundary"].get("incremental_cash_spent_aud") == "0.00"
            )
            valid = (
                result.get("status") == "PASS"
                and isinstance(receipt, Mapping)
                and receipt.get("contract_id") == spec["contract_id"]
                and receipt.get("requirement_id") == spec["requirement_id"]
                and receipt.get("status") == "PASS"
                and receipt.get("decision") == spec["decision"]
                and receipt.get("next") == spec["next"]
                and receipt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
                and receipt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
                and sha256_file(root / spec["evidence_path"]) == spec["evidence_sha256"]
                and isinstance(rollback, Mapping)
                and rollback.get("status") == "PASS"
                and rollback.get("external_state_changed") is False
                and rollback.get("production_state_changed") is False
                and rollback.get("real_time_soak_waited") is False
                and sha256_file(root / spec["rollback_path"]) == spec["rollback_sha256"]
                and index.get("artifact_sha256") == spec["evidence_sha256"]
                and set(spec["required_checks"]) <= passed_ids
                and generic_boundary
            )
            detail: Any = {
                "contract_id": result.get("contract_id"),
                "status": result.get("status"),
                "evidence_path": result.get("evidence_path"),
                "evidence_sha256": result.get("evidence_sha256"),
                "next": result.get("next"),
            }
            receipts[phase] = receipt if isinstance(receipt, Mapping) else {}
            hashes[spec["evidence_path"]] = sha256_file(root / spec["evidence_path"])
            hashes[spec["rollback_path"]] = sha256_file(root / spec["rollback_path"])
        except Exception as exc:
            valid = False
            detail = "%s: %s" % (type(exc).__name__, exc)
            receipts[phase] = {}
        _add(checks, "S14REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, valid, detail)
        all_ok = all_ok and valid
    return all_ok, receipts


def _all_validation_checks_pass(receipt: Mapping[str, Any]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, Mapping) and row.get("passed") is True for row in rows)


def _check_stage_controls(root: Path, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> Dict[str, bool]:
    try:
        threat_model = strict_json_load(root / "threat_model.json")
        trust_boundaries = strict_json_load(root / "trust_boundaries.json")
        abuse_cases = strict_json_load(root / "abuse_cases.json")
        p01_artifact_ok = (
            isinstance(threat_model, Mapping)
            and threat_model.get("contract_id") == "AC-S14-P01"
            and threat_model.get("high_risk_control_coverage_required") == "1.0000"
            and isinstance(threat_model.get("threats"), list)
            and len(threat_model["threats"]) == 7
            and isinstance(trust_boundaries.get("boundaries"), list)
            and len(trust_boundaries["boundaries"]) == 7
            and isinstance(abuse_cases.get("cases"), list)
            and len(abuse_cases["cases"]) == 7
        )
    except Exception:
        p01_artifact_ok = False
    p01 = _all_validation_checks_pass(receipts.get("P01", {})) and p01_artifact_ok
    _add(checks, "S14REVIEW-THREAT-TRUST-ABUSE-AND-SECURITY-REMEDIATION-GATE", p01, {"artifact_contract": p01_artifact_ok})

    try:
        sast = strict_json_load(root / "sast_policy.json")
        secret = strict_json_load(root / "secret_policy.json")
        p02_analysis = receipts.get("P02", {}).get("validation", {}).get("analysis", {})
        p02_artifact_ok = (
            isinstance(sast, Mapping)
            and isinstance(secret, Mapping)
            and len(sast.get("analysis_rules", [])) == 5
            and len(sast.get("source_targets", [])) == 5
            and len(secret.get("detection_rules", [])) == 4
            and len(secret.get("scan_targets", [])) == 13
            and sast.get("finding_gate") == {"unresolved_critical": 0, "unresolved_high": 0, "automatic_waiver_allowed": False}
            and secret.get("finding_gate") == {"unresolved_critical": 0, "unresolved_high": 0, "automatic_waiver_allowed": False}
            and p02_analysis.get("unresolved_critical_count") == 0
            and p02_analysis.get("unresolved_high_count") == 0
            and p02_analysis.get("live_vulnerability_database_queried") is False
        )
    except Exception:
        p02_artifact_ok = False
    p02 = _all_validation_checks_pass(receipts.get("P02", {})) and p02_artifact_ok
    _add(checks, "S14REVIEW-OFFLINE-SECURITY-PIPELINE-AND-ZERO-HIGH-CRITICAL-GATE", p02, {"artifact_contract": p02_artifact_ok})

    try:
        sbom = strict_json_load(root / "sbom.json")
        governance = strict_json_load(root / "component_governance.json")
        patch_sla = strict_json_load(root / "patch_sla.json")
        p03_analysis = receipts.get("P03", {}).get("validation", {}).get("analysis", {})
        prerequisites = sbom.get("declared_unadmitted_runtime_prerequisites") if isinstance(sbom, Mapping) else None
        p03_artifact_ok = (
            isinstance(sbom, Mapping)
            and len(sbom.get("production_components", [])) == 1
            and len(sbom.get("development_components", [])) == 12
            and isinstance(prerequisites, list)
            and len(prerequisites) == 3
            and all(item.get("release_admission") == "BLOCKED" for item in prerequisites if isinstance(item, Mapping))
            and isinstance(governance, Mapping)
            and governance.get("admission_rules", {}).get("missing_license") == "BLOCK_RELEASE"
            and isinstance(patch_sla, Mapping)
            and [item.get("maximum_elapsed_hours") for item in patch_sla.get("severity_slas", [])] == ["24", "168", "720"]
            and p03_analysis.get("production_component_count") == 1
            and p03_analysis.get("unadmitted_runtime_prerequisite_count") == 3
            and p03_analysis.get("runtime_direct_dependency_count") == 0
        )
    except Exception:
        p03_artifact_ok = False
    p03 = _all_validation_checks_pass(receipts.get("P03", {})) and p03_artifact_ok
    _add(checks, "S14REVIEW-COMPONENT-METADATA-UNADMITTED-RUNTIME-AND-PATCH-GATE", p03, {"artifact_contract": p03_artifact_ok})

    try:
        provenance = strict_json_load(root / "provenance.json")
        signing = (root / "artifact_signing.md").read_text(encoding="utf-8")
        rollback_policy = (root / "security_rollback.md").read_text(encoding="utf-8")
        p04_analysis = receipts.get("P04", {}).get("validation", {}).get("analysis", {})
        p04_artifact_ok = (
            isinstance(provenance, Mapping)
            and len(provenance.get("source_inputs", {})) == 15
            and len(provenance.get("dependency_provenance", {}).get("locked_files", {})) == 3
            and provenance.get("local_attestation", {}).get("keyed_or_identity_signature") is False
            and provenance.get("release_boundary", {}).get("actual_release_signed") is False
            and provenance.get("release_boundary", {}).get("deployment_or_activation_performed") is False
            and "not a GPG, Sigstore, key-backed, identity-backed, or production release signature" in signing
            and "No shell, host, Cloudflare, OVH, account, order, or deployment mutation is performed by this Phase." in rollback_policy
            and p04_analysis.get("source_trace_current") is True
            and p04_analysis.get("dependency_trace_current") is True
            and p04_analysis.get("build_environment_trace_current") is True
            and p04_analysis.get("local_attestation_is_keyed_signature") is False
            and p04_analysis.get("production_artifact_or_host_verified") is False
        )
    except Exception:
        p04_artifact_ok = False
    p04 = _all_validation_checks_pass(receipts.get("P04", {})) and p04_artifact_ok
    _add(checks, "S14REVIEW-PROVENANCE-LOCAL-ATTESTATION-NOT-RELEASE-SIGNATURE-GATE", p04, {"artifact_contract": p04_artifact_ok})
    return {"p01": p01, "p02": p02, "p03": p03, "p04": p04}


def _check_external_boundary(contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    phase_boundaries = all(
        isinstance(receipt.get("external_effect_boundary"), Mapping)
        and receipt["external_effect_boundary"].get("external_network_accessed") is False
        and receipt["external_effect_boundary"].get("order_submitted_confirmed_or_retried") is False
        and receipt["external_effect_boundary"].get("production_deployed_or_activated") is False
        and receipt["external_effect_boundary"].get("real_time_soak_waited") is False
        and receipt["external_effect_boundary"].get("incremental_cash_spent_aud") == "0.00"
        for receipt in receipts.values()
    )
    exact = (
        isinstance(contract, Mapping)
        and contract.get("execution_policy") == EXECUTION_POLICY
        and isinstance(findings, Mapping)
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
        and phase_boundaries
    )
    _add(checks, "S14REVIEW-NO-NETWORK-ACCOUNT-ORDER-DEPLOY-OR-SOAK-BOUNDARY", exact, {"phase_boundaries": phase_boundaries})
    return exact


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S14REVIEW-SNAPSHOT-CASES", False, "cases unavailable")
        return False
    passed = True
    for case in cases:
        try:
            actual = evaluate_stage_snapshot(case["snapshot"])
            current = actual["status"] == case["expected"]["status"] and actual["reason_codes"] == case["expected"]["reason_codes"]
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            current = False
        identifier = case.get("case_id") if isinstance(case, Mapping) else "MALFORMED"
        _add(checks, "S14REVIEW-CASE-%s" % identifier, current, actual)
        passed = passed and current
    return passed


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> bool:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=ORACLE_PATH.as_posix())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        # Build denied spellings without embedding them verbatim in this
        # self-inspecting source file.  Otherwise the literal scan would flag
        # its own deny-list instead of a real capability.
        prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtp" + "lib", "asyncio", "time", "random", "os"}
        prohibited_literals = {"sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "web" + "hook", "smtp" + "lib"}
        denied = sorted(imports.intersection(prohibited_imports))
        tokens = sorted(token for token in prohibited_literals if token in source)
        passed = not denied and not tokens
        detail: Any = {"imports": sorted(imports), "denied": denied, "tokens": tokens}
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14REVIEW-STATIC-NO-NETWORK-PROCESS-SOAK-OR-ORDER-CAPABILITY", passed, detail)
    return passed


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise Stage14ReviewError("JUnit contains no suites")
    return {field: sum(int(suite.attrib.get(field, "0")) for suite in suites) for field in ("tests", "failures", "errors", "skipped")}


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        document = ElementTree.parse(root / JUNIT_PATH).getroot()
        suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
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
    _add(checks, "S14REVIEW-TARGETED-PYTEST-REPORT", junit_ok, summary)
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
    _add(checks, "S14REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
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
    _add(checks, "S14REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, summary_value)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": status,
        "stage_status": "S14_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S14_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S14_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S14_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S14/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S14/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate current local S14 review state without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, CONTRACT_PATH, checks, "S14REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S14REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, FINDINGS_PATH, checks, "S14REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, receipts, checks)
    boundary_ok = _check_external_boundary(contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = all(_portable(value) for value in (contract, fixture, findings, *receipts.values()))
    _add(checks, "S14REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "local path detected")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "threat_gate_preserved": controls["p01"],
        "security_pipeline_gate_preserved": controls["p02"],
        "component_governance_gate_preserved": controls["p03"],
        "provenance_gate_preserved": controls["p04"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S14REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S14_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _add(checks, "S14REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
    return _result(checks, hashes, snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, *CONTROL_ARTIFACTS)
    phase_paths = tuple(Path(spec["evidence_path"]) for spec in PHASE_SPECS.values()) + tuple(Path(spec["rollback_path"]) for spec in PHASE_SPECS.values())
    artifacts = {
        path.as_posix(): {
            "status": "PASS" if (root / path).is_file() else "FAIL",
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
        }
        for path in (*paths, *phase_paths)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "CLOSE_S14_REVIEW_CANDIDATE_PRESERVE_SIGNED_PHASE_EVIDENCE_NO_EXTERNAL_MUTATION",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
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
        "evidence_id": "EVD-S14-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S14_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S14_STAGE_REVIEW_REMEDIATION_REQUIRED",
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
            "uv run --frozen --python 3.12 python -m pytest -q tests/S14/stage_review_test.py --junitxml=machine/evidence/S14/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S14/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S14/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S14 --evidence machine/evidence",
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
        "id": "INDEX-S14-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S14/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    positions = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) > 1:
        raise Stage14ReviewError("duplicate S14 stage-review evidence index rows")
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
        raise Stage14ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage14ReviewError("cannot write evidence for a failed S14 review")
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
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-S14-STAGE-REVIEW")
    except Exception as exc:
        raise Stage14ReviewError("existing S14 stage-review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S14-STAGE-REVIEW"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("stage_status") == "S14_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("decision") == "S14_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S14/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S14_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("findings_summary") == {"total": 1, "open": 0, "resolved": 1, "blocked": 0}
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and index.get("kind") == "STAGE_REVIEW_EVIDENCE"
        and index.get("contract_id") == CONTRACT_ID
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S14/GITHUB_STAGE_UPLOAD_READY"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise Stage14ReviewError("existing S14 stage-review evidence does not replay exactly")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/GITHUB_STAGE_UPLOAD_READY",
    }
