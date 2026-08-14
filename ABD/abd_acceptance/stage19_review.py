"""Fail-closed, local-only whole-stage review oracle for ABD S19.

This review is a local addendum over the frozen Task Pack.  It verifies the
four signed S19 phase receipts, their pinned control artifacts, and the
explicit truth boundaries around Alpha, Model Beta, actual GA, delivery, and
deployment.  It does not open a network, provider, database, market, Gmail,
TAB, or account session; it never waits for real time, recommends, submits an
order, or deploys a runtime.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "STAGE-REVIEW-S19"
REVIEW_ID = "ABD-S19-WHOLE-STAGE-REVIEW"
STAGE_ID = "S19"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T10:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
ADDENDUM_STATUS = "LOCAL_STAGE_REVIEW_CONTRACT_NOT_A_FROZEN_TASK_PACK_FACT"

CONTRACT_PATH = Path("machine/facts/stage19_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S19/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S19_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S19/stage_review_test.py")
ORACLE_PATH = Path("abd_acceptance/stage19_review.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S19-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S19-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S19/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S19/STAGE_REVIEW/paid_dependency_scan.txt")
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
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}

PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    "P01": {
        "requirement_id": "REQ-S19-P01",
        "contract_id": "AC-S19-P01",
        "target": "不使用真实资金即可确定性闭环。",
        "outputs": ["walking_skeleton_evidence.json", "software_alpha_gate.json"],
        "task_outputs": {
            "T-S19-P01-01": ["walking_skeleton_evidence.json", "software_alpha_gate.json"],
            "T-S19-P01-02": ["tests/S19/P01_test.py", "machine/tests/fixtures/S19_P01.json"],
            "T-S19-P01-03": ["machine/evidence/EVD-S19-P01.json", "machine/evidence/EVD-S19-P01_rollback.json"],
        },
        "test_ids": ("TEST-S19-P01", "TEST-S19-P01-BOUNDARY", "TEST-S19-P01-REPLAY"),
        "artifact_ids": ("ART-S19-P01-01", "ART-S19-P01-02"),
        "evidence_path": "machine/evidence/EVD-S19-P01.json",
        "evidence_sha256": "183fc545bad654f5ee851fcb828433e0e7949396c83f8c67354ccc220c492219",
        "rollback_path": "machine/evidence/EVD-S19-P01_rollback.json",
        "rollback_sha256": "6297ba555889762ce6eba2a615ddd4087c162f7905a3f19cb7716dad185eccdc",
        "decision": "S19_P01_WALKING_SKELETON_AND_SOFTWARE_ALPHA_PASS_P02_REQUIRED",
        "next": "S19/P02_READY_NOT_STARTED",
        "release_status": "S19_P01_LOCAL_SOFTWARE_ALPHA_ONLY_P02_REQUIRED",
        "required_checks": (
            "S19P01-GOLDEN-CLOSED-LOOP-NO-FUNDS",
            "S19P01-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY",
            "S19P01-SOFTWARE-ALPHA-LOCAL-ONLY",
            "S19P01-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
    },
    "P02": {
        "requirement_id": "REQ-S19-P02",
        "contract_id": "AC-S19-P02",
        "target": "校准、净增长、时效、容量和漂移门通过。",
        "outputs": ["shadow_report.json", "model_beta_gate.json"],
        "task_outputs": {
            "T-S19-P02-01": ["shadow_report.json", "model_beta_gate.json"],
            "T-S19-P02-02": ["tests/S19/P02_test.py", "machine/tests/fixtures/S19_P02.json"],
            "T-S19-P02-03": ["machine/evidence/EVD-S19-P02.json", "machine/evidence/EVD-S19-P02_rollback.json"],
        },
        "test_ids": ("TEST-S19-P02", "TEST-S19-P02-BOUNDARY", "TEST-S19-P02-REPLAY"),
        "artifact_ids": ("ART-S19-P02-01", "ART-S19-P02-02"),
        "evidence_path": "machine/evidence/EVD-S19-P02.json",
        "evidence_sha256": "6d13caf6132005bbfa1f2d31e3bfbce23366065702404d1c56e4dff1f4c73177",
        "rollback_path": "machine/evidence/EVD-S19-P02_rollback.json",
        "rollback_sha256": "90db8f84ec6a6e5a06b280f9f969ee3e4c5a21a9deecd754965f381d5f2af655",
        "decision": "S19_P02_SHADOW_BETA_CONTROL_PASS_P03_REQUIRED_NOT_MODEL_BETA",
        "next": "S19/P03_READY_NOT_STARTED",
        "release_status": "S19_P02_LOCAL_SHADOW_GATE_CONTROL_ONLY_EMPIRICAL_RUNTIME_REQUIRED",
        "required_checks": (
            "S19P02-ALL-FIVE-LOCAL-QUALITY-GATES-PASS-BETA-BLOCKED",
            "S19P02-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY",
            "S19P02-MODEL-BETA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-EVIDENCE",
            "S19P02-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
    },
    "P03": {
        "requirement_id": "REQ-S19-P03",
        "contract_id": "AC-S19-P03",
        "target": "证据完整、对账差异0、终止条件未触发。",
        "outputs": ["ga_report.json", "actual_reconciliation.json"],
        "task_outputs": {
            "T-S19-P03-01": ["ga_report.json", "actual_reconciliation.json"],
            "T-S19-P03-02": ["tests/S19/P03_test.py", "machine/tests/fixtures/S19_P03.json"],
            "T-S19-P03-03": ["machine/evidence/EVD-S19-P03.json", "machine/evidence/EVD-S19-P03_rollback.json"],
        },
        "test_ids": ("TEST-S19-P03", "TEST-S19-P03-BOUNDARY", "TEST-S19-P03-REPLAY"),
        "artifact_ids": ("ART-S19-P03-01", "ART-S19-P03-02"),
        "evidence_path": "machine/evidence/EVD-S19-P03.json",
        "evidence_sha256": "3bb3a41f8bb23f65bd4c5fbd4aba14c361d8a391d3cdbaca2666aae9887f345b",
        "rollback_path": "machine/evidence/EVD-S19-P03_rollback.json",
        "rollback_sha256": "7e55153bc6ab27c7e00b238dcc685e00566ed32e6a317b0a6233df543ca1c9ef",
        "decision": "S19_P03_LOCAL_GA_RECONCILIATION_CONTROL_PASS_P04_REQUIRED_ACTUAL_GA_BLOCKED",
        "next": "S19/P04_READY_NOT_STARTED",
        "release_status": "S19_P03_LOCAL_GA_RECONCILIATION_CONTROL_ONLY_SEPARATE_EMPIRICAL_RUNTIME_REQUIRED",
        "required_checks": (
            "S19P03-LOCAL-ZERO-DIFFERENCE-NOT-AN-ACTUAL-RECONCILIATION-CLAIM",
            "S19P03-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY",
            "S19P03-ACTUAL-GA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-EVIDENCE",
            "S19P03-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
    },
    "P04": {
        "requirement_id": "REQ-S19-P04",
        "contract_id": "AC-S19-P04",
        "target": "所有验收通过，版本和哈希无歧义无冲突。",
        "outputs": ["final_acceptance.json", "release_manifest.json", "handoff_bundle.zip"],
        "task_outputs": {
            "T-S19-P04-01": ["final_acceptance.json", "release_manifest.json", "handoff_bundle.zip"],
            "T-S19-P04-02": ["tests/S19/P04_test.py", "machine/tests/fixtures/S19_P04.json"],
            "T-S19-P04-03": ["machine/evidence/EVD-S19-P04.json", "machine/evidence/EVD-S19-P04_rollback.json"],
        },
        "test_ids": ("TEST-S19-P04", "TEST-S19-P04-BOUNDARY", "TEST-S19-P04-REPLAY"),
        "artifact_ids": ("ART-S19-P04-01", "ART-S19-P04-02", "ART-S19-P04-03"),
        "evidence_path": "machine/evidence/EVD-S19-P04.json",
        "evidence_sha256": "b1de99378bbb12fbe4d49819bd4d71301330cad661c038b452ba368a0872f0ad",
        "rollback_path": "machine/evidence/EVD-S19-P04_rollback.json",
        "rollback_sha256": "6e036dbe4a35fae1cdffdeaf98b0aa232b2a84d1a0d1ab1bfaeef51322d4bb96",
        "decision": "S19_P04_LOCAL_FINAL_DELIVERY_PASS_STAGE_REVIEW_REQUIRED",
        "next": "S19/STAGE_REVIEW_READY_NOT_STARTED",
        "release_status": "S19_P04_LOCAL_FINAL_DELIVERY_COMPLETE_STAGE_REVIEW_REQUIRED_RUNTIME_NOT_DEPLOYED",
        "required_checks": (
            "S19P04-FINAL-DELIVERY-DOES-NOT-CLAIM-DEPLOYMENT-OR-RETURNS",
            "S19P04-NON_SECRET-HANDOFF-BUNDLE-EXACT",
            "S19P04-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY",
            "S19P04-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
    },
}

CONTROL_CODE_PATHS = {
    "P01": (Path("abd_acceptance/walking_skeleton.py"),),
    "P02": (Path("abd_acceptance/shadow_beta.py"),),
    "P03": (Path("abd_acceptance/ga_reconciliation.py"),),
    "P04": (Path("abd_acceptance/final_delivery_acceptance.py"),),
}
CONTROL_ARTIFACTS = (
    Path("walking_skeleton_evidence.json"),
    Path("software_alpha_gate.json"),
    Path("shadow_report.json"),
    Path("model_beta_gate.json"),
    Path("ga_report.json"),
    Path("actual_reconciliation.json"),
    Path("final_acceptance.json"),
    Path("release_manifest.json"),
    Path("handoff_bundle.zip"),
)
REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "SOFTWARE_ALPHA_REMAINS_LOCAL_NO_REAL_FUNDS_OR_ORDER",
    "MODEL_BETA_REMAINS_BLOCKED_WITHOUT_EMPIRICAL_REALTIME_EVIDENCE",
    "ACTUAL_GA_AND_RETURN_REMAIN_BLOCKED_OR_UNVERIFIED_WITH_ZERO_ACTUAL_RECORDS",
    "FINAL_DELIVERY_REMAINS_NON_SECRET_LOCAL_AND_NON_PRODUCTION",
    "NO_NETWORK_RUNTIME_ACCOUNT_DATABASE_ORDER_DEPLOY_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_S19_REVIEW_FINDINGS_RESOLVED",
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
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
EXPLICIT_LIMITATIONS = [
    "S19 只复核冻结的本地 Walking Skeleton、影子门、零行 GA 对账控制和最终交付制品及其已签名证据。",
    "S19 复审通过不构成真实 OVH、Cloudflare、数据库、TAB/Gmail、市场、账户、模型运行、部署、实际 GA 或实际收益证明。",
    "真实时间影子、实际执行、对账、模型晋级、GitHub 上传、远端 CI 与部署均不由本地复审执行或证明。",
    "A$300×1.3^n 的30%月度目标仍为 UNVERIFIED_NOT_GUARANTEED。",
]
RESOLVED_FINDINGS = [
    {
        "id": "S19-REVIEW-001",
        "severity": "CRITICAL",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "Walking Skeleton 和 Software Alpha 制品可能被误读为已连接市场、资金、Gmail/TAB 或可以提交订单。",
        "resolution": "P01 固定为无真实资金的本地闭环；Alpha 仅为本地状态，推荐、订单、外部运行时、部署和风险门放宽均保持禁用。",
        "resolution_evidence": ["walking_skeleton_evidence.json", "software_alpha_gate.json", "machine/evidence/EVD-S19-P01.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S19-REVIEW-002",
        "severity": "CRITICAL",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "本地合成指标和零行对账控制可能被误读为 Model Beta、实际 GA、实际对账或收益已获得经验性验证。",
        "resolution": "P02 明确 Model Beta 在缺少真实时间影子证据时保持阻断；P03 明确 actual records 和 verified days 均为零，实际对账不可评估，GA 与收益均不升级。",
        "resolution_evidence": ["shadow_report.json", "model_beta_gate.json", "ga_report.json", "actual_reconciliation.json", "machine/evidence/EVD-S19-P02.json", "machine/evidence/EVD-S19-P03.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S19-REVIEW-003",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "最终验收、发布清单与交接包可能被误读为 GitHub 已上传、远端 CI 已通过、运行时已部署或目标回报已保证。",
        "resolution": "P04 的最终交付严格标为本地、非秘密、非生产制品；本复审仅在通过后打开 GitHub Stage upload，任何部署仍须独立真实证据。",
        "resolution_evidence": ["final_acceptance.json", "release_manifest.json", "handoff_bundle.zip", "machine/evidence/EVD-S19-P04.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
]
SNAPSHOT_CASE_IDS = (
    "POSITIVE_EXACT_STAGE",
    "PHASE_RECEIPT_FAIL",
    "TASKPACK_TRACE_FAIL",
    "ALPHA_GATE_FAIL",
    "MODEL_AND_GA_BOUNDARY_FAIL",
    "FINAL_DELIVERY_BOUNDARY_FAIL",
    "RELEASE_CHAIN_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PORTABILITY_FAIL",
    "OPEN_FINDING_FAIL",
)


class Stage19ReviewError(ValueError):
    """Raised when the local S19 stage-review contract is not reproducible."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise Stage19ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage19ReviewError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage19ReviewError("rows are unavailable")
    matching = [value for value in rows if isinstance(value, Mapping) and value.get(key) == identifier]
    if len(matching) != 1:
        raise Stage19ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matching[0]


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, path.as_posix())
    return value


def _portable(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_portable(key) and _portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_portable(item) for item in value)
    return not isinstance(value, str) or not value.startswith("/")


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
            "expected_release_status": spec["release_status"],
            "required_checks": list(spec["required_checks"]),
        }
        for phase, spec in PHASE_SPECS.items()
    ]


def _review_scope() -> Dict[str, Any]:
    return {
        "phase_ids": list(PHASE_SPECS),
        "requirement_ids": [spec["requirement_id"] for spec in PHASE_SPECS.values()],
        "acceptance_contract_ids": [spec["contract_id"] for spec in PHASE_SPECS.values()],
        "task_ids": [task_id for spec in PHASE_SPECS.values() for task_id in spec["task_outputs"]],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    bool_keys = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("alpha_local_only_preserved", "ALPHA_LOCAL_ONLY_GATE_RELAXED"),
        ("beta_and_ga_truth_boundary_preserved", "BETA_OR_GA_TRUTH_BOUNDARY_RELAXED"),
        ("final_delivery_boundary_preserved", "FINAL_DELIVERY_BOUNDARY_RELAXED"),
        ("release_chain_preserved", "RELEASE_CHAIN_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    required = {key for key, _ in bool_keys} | {"findings_open"}
    if set(snapshot) != required or any(type(snapshot[key]) is not bool for key, _ in bool_keys):
        raise Stage19ReviewError("stage snapshot is malformed")
    findings_open = snapshot["findings_open"]
    if type(findings_open) is not int or findings_open < 0:
        raise Stage19ReviewError("findings_open must be a nonnegative integer")
    reasons = [reason for key, reason in bool_keys if snapshot[key] is not True]
    if findings_open != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    status = "S19_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S19_STAGE_REVIEW_REJECTED_NO_ACTION"
    payload = {key: snapshot[key] for key in (*[key for key, _ in bool_keys], "findings_open")}
    return {
        "status": status,
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "production_deployed_or_activated": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
        "output_sha256": _sha256_bytes(_json_bytes(payload)),
    }


def _check_contract(contract: Any, fixture: Any, findings: Any, checks: List[Dict[str, Any]]) -> None:
    if not isinstance(contract, Mapping) or not isinstance(fixture, Mapping) or not isinstance(findings, Mapping):
        _add(checks, "S19REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "stage_review_addendum": ADDENDUM_STATUS,
        "targeted_test_command": "pytest -q tests/S19/stage_review_test.py",
        "release_status_on_pass": "S19_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S19/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S19/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S19REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S19REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S19REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S19REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S19REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S19REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S19-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": len(SNAPSHOT_CASE_IDS),
        "minimum_targeted_pytest_cases": 27,
        "expected_phase_ids": list(PHASE_SPECS),
        "expected_phase_evidence_sha256": {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_phase_rollback_sha256": {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_next": "S19/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S19_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 3, "open": 0, "resolved": 3, "blocked": 0},
    }
    _add(checks, "S19REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S19REVIEW-SINGLE-PASS-CASES-EXACT",
        isinstance(cases, list) and [case.get("case_id") for case in cases if isinstance(case, Mapping)] == list(SNAPSHOT_CASE_IDS),
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
    _add(checks, "S19REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    passed = True
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        ok = actual == expected
        _add(checks, "S19REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), ok, {"expected": expected, "actual": actual})
        passed = passed and ok
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S19REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S19REVIEW-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S19REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S19REVIEW-TRACEABILITY-PARSE")
    try:
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise Stage19ReviewError("task graph unavailable")
        valid = True
        for phase, spec in PHASE_SPECS.items():
            requirement = _row(requirements, spec["requirement_id"])
            contract = _row(contracts, spec["contract_id"])
            trace = _row(traceability, spec["requirement_id"], key="requirement_id")
            phase_tasks = [item for item in tasks if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == phase]
            task_ids = list(spec["task_outputs"])
            phase_ok = (
                requirement.get("scope") == spec["outputs"]
                and requirement.get("target") == spec["target"]
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and contract.get("requirement_id") == spec["requirement_id"]
                and contract.get("pass_gate") == spec["target"]
                and [item.get("id") for item in contract.get("tests", [])] == list(spec["test_ids"])
                and [item.get("id") for item in phase_tasks] == task_ids
                and {item.get("id"): item.get("outputs") for item in phase_tasks} == spec["task_outputs"]
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == task_ids
                and trace.get("test_ids") == list(spec["test_ids"])
                and trace.get("evidence_id") == "EVD-S19-%s" % phase
                and trace.get("artifact_ids") == list(spec["artifact_ids"])
            )
            _add(checks, "S19REVIEW-%s-TASKPACK-TRACE-EXACT" % phase, phase_ok, {"tasks": task_ids})
            valid = valid and phase_ok
    except Exception as exc:
        valid = False
        _add(checks, "S19REVIEW-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return valid


def _all_validation_checks_pass(receipt: Mapping[str, Any]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, Mapping) and row.get("passed") is True for row in rows)


def _receipt_boundary(boundary: Any) -> bool:
    required_false = (
        "external_network_accessed",
        "recommendation_generated_or_enabled",
        "order_submitted_confirmed_or_retried",
        "production_deployed_or_activated",
        "real_time_soak_waited",
    )
    return isinstance(boundary, Mapping) and all(boundary.get(key) is False for key in required_false) and boundary.get("incremental_cash_spent_aud") == "0.00"


def _control_boundary(boundary: Any) -> bool:
    return _receipt_boundary(boundary) and isinstance(boundary, Mapping) and boundary.get("evidence_numeric_risk_safety_or_source_gate_relaxed") is False


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    all_ok = True
    receipts: Dict[str, Mapping[str, Any]] = {}
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        index_rows = []
        _add(checks, "S19REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        all_ok = False
    for phase, spec in PHASE_SPECS.items():
        try:
            receipt = strict_json_load(root / spec["evidence_path"])
            rollback = strict_json_load(root / spec["rollback_path"])
            index = _row(index_rows, "INDEX-%s" % spec["contract_id"])
            passed_ids = {row.get("id") for row in receipt.get("validation", {}).get("checks", []) if isinstance(row, Mapping) and row.get("passed") is True}
            receipt_hash = sha256_file(root / spec["evidence_path"])
            rollback_hash = sha256_file(root / spec["rollback_path"])
            valid = (
                isinstance(receipt, Mapping)
                and receipt.get("contract_id") == spec["contract_id"]
                and receipt.get("requirement_id") == spec["requirement_id"]
                and receipt.get("stage_id") == STAGE_ID
                and receipt.get("phase_id") == phase
                and receipt.get("status") == "PASS"
                and receipt.get("decision") == spec["decision"]
                and receipt.get("next") == spec["next"]
                and receipt.get("release_status") == spec["release_status"]
                and receipt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
                and receipt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
                and _all_validation_checks_pass(receipt)
                and _receipt_boundary(receipt.get("external_effect_boundary"))
                and set(spec["required_checks"]) <= passed_ids
                and receipt_hash == spec["evidence_sha256"]
                and isinstance(rollback, Mapping)
                and rollback.get("status") == "PASS"
                and rollback.get("external_state_changed") is False
                and rollback.get("production_state_changed") is False
                and rollback.get("real_time_soak_waited") is False
                and rollback.get("incremental_cash_spent_aud") == "0.00"
                and rollback_hash == spec["rollback_sha256"]
                and index.get("kind") == "ACCEPTANCE_EVIDENCE"
                and index.get("stage_id") == STAGE_ID
                and index.get("acceptance_contract_id") == spec["contract_id"]
                and index.get("requirement_id") == spec["requirement_id"]
                and index.get("status") == "PASS"
                and index.get("actual_artifact") == spec["evidence_path"]
                and index.get("artifact_sha256") == spec["evidence_sha256"]
                and index.get("next") == spec["next"]
            )
            detail: Any = {"receipt_sha256": receipt_hash, "rollback_sha256": rollback_hash, "verification_mode": EXECUTION_POLICY["signed_phase_receipt_verification_mode"]}
            receipts[phase] = receipt
            hashes[spec["evidence_path"]] = receipt_hash
            hashes[spec["rollback_path"]] = rollback_hash
        except Exception as exc:
            valid = False
            detail = "%s: %s" % (type(exc).__name__, exc)
            receipts[phase] = {}
        _add(checks, "S19REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, valid, detail)
        all_ok = all_ok and valid
    return all_ok, receipts


def _load_control(root: Path, path: str) -> Mapping[str, Any]:
    value = strict_json_load(root / path)
    if not isinstance(value, Mapping):
        raise Stage19ReviewError("control document is not an object: %s" % path)
    return value


def _local_control_code(root: Path, phase: str, hashes: MutableMapping[str, str]) -> bool:
    forbidden = {"socket", "urllib", "requests", "httpx", "subprocess", "os", "shutil", "time", "asyncio", "smtplib"}
    try:
        source = "\n".join((root / path).read_text(encoding="utf-8") for path in CONTROL_CODE_PATHS[phase])
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        for path in CONTROL_CODE_PATHS[phase]:
            hashes[path.as_posix()] = sha256_file(root / path)
        return not (imports & forbidden) and "http://" not in source and "https://" not in source
    except Exception:
        return False


def _check_stage_controls(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Dict[str, bool]:
    controls = {"p01": False, "p02": False, "p03": False, "p04": False, "release_chain": False}
    try:
        walking = _load_control(root, "walking_skeleton_evidence.json")
        alpha = _load_control(root, "software_alpha_gate.json")
        activation = alpha.get("activation_conditions")
        controls["p01"] = (
            walking.get("contract_id") == "AC-S19-P01"
            and walking.get("status") == "PASS"
            and walking.get("decision") == "LOCAL_ALPHA_CLOSED_LOOP_NO_ORDER"
            and alpha.get("contract_id") == "AC-S19-P01"
            and alpha.get("status") == "PASS"
            and alpha.get("alpha_status") == "SOFTWARE_ALPHA_LOCAL_ONLY_NOT_DEPLOYED"
            and isinstance(activation, Mapping)
            and activation.get("real_funds_used") is False
            and activation.get("actual_order_submission_enabled") is False
            and activation.get("external_runtime_accessed") is False
            and _control_boundary(walking.get("external_effect_boundary"))
            and _control_boundary(alpha.get("external_effect_boundary"))
            and _local_control_code(root, "P01", hashes)
        )
        hashes["walking_skeleton_evidence.json"] = sha256_file(root / "walking_skeleton_evidence.json")
        hashes["software_alpha_gate.json"] = sha256_file(root / "software_alpha_gate.json")
        detail: Any = {"alpha_status": alpha.get("alpha_status"), "decision": walking.get("decision")}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-SOFTWARE-ALPHA-LOCAL-NO-FUNDS-OR-ORDER-GATE", controls["p01"], detail)
    try:
        shadow = _load_control(root, "shadow_report.json")
        beta = _load_control(root, "model_beta_gate.json")
        controls["p02"] = (
            shadow.get("contract_id") == "AC-S19-P02"
            and shadow.get("status") == "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT"
            and shadow.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
            and beta.get("contract_id") == "AC-S19-P02"
            and beta.get("status") == "PASS_LOCAL_CONTRACT_MODEL_BETA_BLOCKED"
            and beta.get("local_contract_validation_status") == "PASS_ALL_SYNTHETIC_QUALITY_GATES"
            and beta.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
            and beta.get("model_beta_eligible") is False
            and beta.get("model_activation_allowed") is False
            and beta.get("recommendation_generation_allowed") is False
            and beta.get("order_submission_allowed") is False
            and _control_boundary(shadow.get("external_effect_boundary"))
            and _control_boundary(beta.get("external_effect_boundary"))
            and _local_control_code(root, "P02", hashes)
        )
        hashes["shadow_report.json"] = sha256_file(root / "shadow_report.json")
        hashes["model_beta_gate.json"] = sha256_file(root / "model_beta_gate.json")
        detail = {"model_beta_status": beta.get("model_beta_status"), "eligible": beta.get("model_beta_eligible")}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-MODEL-BETA-REMAINS-BLOCKED-WITHOUT-EMPIRICAL-GATE", controls["p02"], detail)
    try:
        ga = _load_control(root, "ga_report.json")
        reconciliation = _load_control(root, "actual_reconciliation.json")
        observed = ga.get("actual_execution_observation")
        controls["p03"] = (
            ga.get("contract_id") == "AC-S19-P03"
            and ga.get("status") == "PASS_LOCAL_GA_RECONCILIATION_CONTROL_ACTUAL_GA_BLOCKED"
            and ga.get("ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
            and isinstance(observed, Mapping)
            and observed.get("actual_execution_evidence_complete") is False
            and observed.get("actual_record_count") == 0
            and observed.get("verified_days") == 0
            and observed.get("actual_reconciliation_status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
            and reconciliation.get("contract_id") == "AC-S19-P03"
            and reconciliation.get("status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
            and reconciliation.get("actual_execution_evidence_complete") is False
            and reconciliation.get("actual_record_count") == 0
            and reconciliation.get("verified_days") == 0
            and reconciliation.get("actual_reconciliation_difference_is_known") is False
            and reconciliation.get("ga_activation_allowed") is False
            and reconciliation.get("recommendation_generation_allowed") is False
            and reconciliation.get("order_submission_allowed") is False
            and _control_boundary(ga.get("external_effect_boundary"))
            and _control_boundary(reconciliation.get("external_effect_boundary"))
            and _local_control_code(root, "P03", hashes)
        )
        hashes["ga_report.json"] = sha256_file(root / "ga_report.json")
        hashes["actual_reconciliation.json"] = sha256_file(root / "actual_reconciliation.json")
        detail = {"ga_status": ga.get("ga_status"), "actual_records": reconciliation.get("actual_record_count")}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-ACTUAL-GA-AND-RETURN-TRUTH-BOUNDARY-GATE", controls["p03"], detail)
    try:
        final = _load_control(root, "final_acceptance.json")
        manifest = _load_control(root, "release_manifest.json")
        runtime_boundary = final.get("runtime_and_return_boundary")
        evaluation = final.get("evaluation")
        bundle = manifest.get("handoff_bundle")
        controls["p04"] = (
            final.get("contract_id") == "AC-S19-P04"
            and final.get("status") == "PASS_LOCAL_FINAL_ACCEPTANCE_STAGE_REVIEW_REQUIRED"
            and final.get("decision") == "LOCAL_FINAL_ACCEPTANCE_PASS_STAGE_REVIEW_REQUIRED_RUNTIME_AND_RETURN_UNVERIFIED"
            and isinstance(runtime_boundary, Mapping)
            and runtime_boundary.get("external_runtime_verified") is False
            and runtime_boundary.get("return_or_roi_verified") is False
            and runtime_boundary.get("deployment_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and isinstance(evaluation, Mapping)
            and evaluation.get("recommendation_generation_allowed") is False
            and evaluation.get("order_submission_allowed") is False
            and evaluation.get("production_deployment_allowed") is False
            and manifest.get("contract_id") == "AC-S19-P04"
            and manifest.get("status") == "LOCAL_DELIVERY_MANIFEST_NOT_A_PRODUCTION_RELEASE"
            and manifest.get("release_decision") == "S19_STAGE_REVIEW_REQUIRED_BEFORE_GITHUB_UPLOAD_OR_ANY_DEPLOYMENT"
            and manifest.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and isinstance(bundle, Mapping)
            and bundle.get("format") == "ZIP_STORED_FIXED_CLOCK_NON_SECRET_REPOSITORY_RELATIVE"
            and (root / "handoff_bundle.zip").is_file()
            and _control_boundary(final.get("external_effect_boundary"))
            and _control_boundary(manifest.get("external_effect_boundary"))
            and _local_control_code(root, "P04", hashes)
        )
        controls["release_chain"] = (
            final.get("next") == "S19/STAGE_REVIEW_READY_NOT_STARTED"
            and manifest.get("next") == "S19/STAGE_REVIEW_READY_NOT_STARTED"
            and final.get("financial", {}).get("target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and manifest.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        )
        hashes["final_acceptance.json"] = sha256_file(root / "final_acceptance.json")
        hashes["release_manifest.json"] = sha256_file(root / "release_manifest.json")
        hashes["handoff_bundle.zip"] = sha256_file(root / "handoff_bundle.zip")
        detail = {"manifest_status": manifest.get("status"), "release_chain": controls["release_chain"]}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-FINAL-DELIVERY-NONSECRET-LOCAL-NONPRODUCTION-GATE", controls["p04"], detail)
    _add(checks, "S19REVIEW-FINAL-DELIVERY-RELEASE-CHAIN-GATE", controls["release_chain"], detail)
    return controls


def _check_external_boundary(contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    receipt_boundaries = all(_receipt_boundary(receipt.get("external_effect_boundary")) for receipt in receipts.values() if isinstance(receipt, Mapping)) and len(receipts) == len(PHASE_SPECS)
    exact = isinstance(contract, Mapping) and contract.get("execution_policy") == EXECUTION_POLICY and isinstance(findings, Mapping) and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
    valid = exact and receipt_boundaries
    _add(checks, "S19REVIEW-NO-NETWORK-RUNTIME-ACCOUNT-DATABASE-ORDER-DEPLOY-OR-SOAK-BOUNDARY", valid, {"review": EXTERNAL_EFFECT_BOUNDARY, "receipts_current": receipt_boundaries})
    return valid


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> None:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S19REVIEW-SNAPSHOT-CASES-FAIL-CLOSED", False, "cases unavailable")
        return
    passed = True
    details = []
    for case in cases:
        try:
            if not isinstance(case, Mapping):
                raise Stage19ReviewError("case is malformed")
            result = evaluate_stage_snapshot(case["snapshot"])
            expected = case["expected"]
            ok = result.get("status") == expected.get("status") and result.get("reason_codes") == expected.get("reason_codes")
        except Exception as exc:
            ok = False
            result = "%s: %s" % (type(exc).__name__, exc)
        passed = passed and ok
        details.append({"case_id": case.get("case_id") if isinstance(case, Mapping) else None, "passed": ok, "result": result})
    _add(checks, "S19REVIEW-SNAPSHOT-CASES-FAIL-CLOSED", passed, details)


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "smtplib"}
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        valid = not (imports & forbidden) and not (calls & {"sleep", "Popen", "submit_order"})
    except Exception as exc:
        valid = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-ORACLE-STATIC-NO-NETWORK-PROCESS-WAIT-OR-ORDER", valid, "parsed" if valid else source)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .stage19_review import verify_existing_stage_review_evidence as verify_existing_stage19_review_evidence" in source
            and "from .stage19_review import write_stage_review_evidence as write_stage19_review_evidence" in source
            and '"STAGE-REVIEW-S19": verify_existing_stage19_review_evidence,' in source
            and '"STAGE-REVIEW-S19": write_stage19_review_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)


def _junit_summary(path: Path) -> tuple[Dict[str, int], bool]:
    try:
        document = ElementTree.parse(path).getroot()
        suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite")) if document.tag == "testsuites" else []
        summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for suite in suites:
            for key in summary:
                summary[key] += int(suite.attrib.get(key, "0"))
        normalized = bool(suites) and all(
            suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
            and suite.attrib.get("time") == "0.000"
            and "hostname" not in suite.attrib
            and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
            for suite in suites
        )
        return summary, normalized
    except Exception:
        return {"tests": 0, "failures": 1, "errors": 1, "skipped": 0}, False


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    pytest_ok = normalized and summary["tests"] >= fixture.get("minimum_targeted_pytest_cases", 1) and summary["failures"] == summary["errors"] == summary["skipped"] == 0
    _add(checks, "S19REVIEW-TARGETED-PYTEST-REPORT", pytest_ok, {"summary": summary, "normalized": normalized})
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = (
            "STATUS: PASS" in scan
            and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan
            and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in scan
            and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in scan
        )
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, "present" if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        pack_ok = report.get("status") == "PASS" and report.get("summary", {}).get("failed") == 0 and report.get("summary", {}).get("passed") == report.get("summary", {}).get("checks")
    except Exception as exc:
        pack_ok = False
        report = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report.get("summary") if isinstance(report, Mapping) else report)
    return pytest_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": status,
        "stage_status": "S19_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S19_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S19_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S19_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S19/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S19/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the local S19 review without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, CONTRACT_PATH, checks, "S19REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S19REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, FINDINGS_PATH, checks, "S19REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, checks, hashes)
    boundary_ok = _check_external_boundary(contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = _portable(contract) and _portable(fixture) and _portable(findings) and all(_portable(receipt) for receipt in receipts.values())
    _add(checks, "S19REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "absolute path found")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) and isinstance(findings.get("summary"), Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "alpha_local_only_preserved": controls["p01"],
        "beta_and_ga_truth_boundary_preserved": controls["p02"] and controls["p03"],
        "final_delivery_boundary_preserved": controls["p04"],
        "release_chain_preserved": controls["release_chain"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S19REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S19_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_cli_wiring(root, checks)
    _add(checks, "S19REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
    return _result(checks, hashes, snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    review_paths = (CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, CLI_PATH, *CONTROL_ARTIFACTS)
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
        "evidence_id": "EVD-S19-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S19_STAGE_REVIEW_CANDIDATE_KEEP_RUNTIME_AND_RELEASE_BLOCKED",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, CLI_PATH, *CONTROL_ARTIFACTS]
    paths.extend(Path(spec["evidence_path"]) for spec in PHASE_SPECS.values())
    paths.extend(Path(spec["rollback_path"]) for spec in PHASE_SPECS.values())
    paths.extend(Path(path) for path in BASELINE_HASHES)
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S19_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S19_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "validation": validation,
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "findings": {"path": FINDINGS_PATH.as_posix(), "summary": strict_json_load(root / FINDINGS_PATH).get("summary")},
        "hashes": {
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "code": sha256_file(root / ORACLE_PATH),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S19/stage_review_test.py --junitxml=machine/evidence/S19/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S19/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S19/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S19 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"single_pass_fixture_cases": len(SNAPSHOT_CASE_IDS), "phase_test_suites_rerun": False, "real_time_wait_performed": False},
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
        raise Stage19ReviewError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-S19-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S19/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    matching = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) > 1:
        raise Stage19ReviewError("S19 stage-review evidence-index row is duplicated")
    if not matching:
        raw_lines.append(json.dumps(replacement, ensure_ascii=False, sort_keys=True))
    else:
        raw_lines[matching[0]] = json.dumps(replacement, ensure_ascii=False, sort_keys=True)
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage19ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage19ReviewError("cannot write a failed S19 stage review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S19/GITHUB_STAGE_UPLOAD_READY",
    }


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-S19-STAGE-REVIEW")
    except Exception as exc:
        raise Stage19ReviewError("existing S19 stage-review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S19-STAGE-REVIEW"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("stage_status") == "S19_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("decision") == "S19_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S19/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S19_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("findings", {}).get("summary") == {"total": 3, "open": 0, "resolved": 3, "blocked": 0}
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("recommendation_generated") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and index.get("kind") == "STAGE_REVIEW_EVIDENCE"
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S19/GITHUB_STAGE_UPLOAD_READY"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise Stage19ReviewError("existing S19 stage-review evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S19/GITHUB_STAGE_UPLOAD_READY",
    }


__all__ = [
    "BASELINE_HASHES",
    "CONTRACT_ID",
    "CONTRACT_PATH",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINDINGS_PATH",
    "FIXTURE_PATH",
    "ORACLE_PATH",
    "PHASE_SPECS",
    "REQUIRED_GATES",
    "RESOLVED_FINDINGS",
    "Stage19ReviewError",
    "evaluate_contract",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
