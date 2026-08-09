"""Fail-closed, local-only whole-stage review oracle for ABD S18.

The S18 review is a local addendum, not a replacement for frozen Task Pack
facts.  It replays signed phase receipts and static control artifacts only.
It does not access a runtime, provider, database, account, market, mail, or
network, and it never deploys, waits for a real-time soak, recommends, or
submits an order.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .limited_self_heal_acceptance import verify_existing_phase_evidence as verify_p03
from .observability_alerts import verify_existing_phase_evidence as verify_p02
from .operations_automation_acceptance import verify_existing_phase_evidence as verify_p04
from .safe_release import verify_existing_phase_evidence as verify_p01


CONTRACT_ID = "STAGE-REVIEW-S18"
REVIEW_ID = "ABD-S18-WHOLE-STAGE-REVIEW"
STAGE_ID = "S18"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T05:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
ADDENDUM_STATUS = "LOCAL_STAGE_REVIEW_CONTRACT_NOT_A_FROZEN_TASK_PACK_FACT"

CONTRACT_PATH = Path("machine/facts/stage18_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S18/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S18_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S18/stage_review_test.py")
ORACLE_PATH = Path("abd_acceptance/stage18_review.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S18-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S18-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S18/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S18/STAGE_REVIEW/paid_dependency_scan.txt")
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
        "requirement_id": "REQ-S18-P01",
        "contract_id": "AC-S18-P01",
        "target": "新版本探针失败自动回旧版。",
        "outputs": ["release_pipeline.yml", "canary_policy.json", "post_release_probe.py"],
        "task_outputs": {
            "T-S18-P01-01": ["release_pipeline.yml", "canary_policy.json", "post_release_probe.py"],
            "T-S18-P01-02": ["tests/S18/P01_test.py", "machine/tests/fixtures/S18_P01.json"],
            "T-S18-P01-03": ["machine/evidence/EVD-S18-P01.json", "machine/evidence/EVD-S18-P01_rollback.json"],
        },
        "test_ids": ("TEST-S18-P01", "TEST-S18-P01-BOUNDARY", "TEST-S18-P01-REPLAY"),
        "artifact_ids": ("ART-S18-P01-01", "ART-S18-P01-02", "ART-S18-P01-03"),
        "evidence_path": "machine/evidence/EVD-S18-P01.json",
        "evidence_sha256": "7934fdcc8998467883ab993fee312892311e5a45d26add37e4e00b04a5f8d9e5",
        "rollback_path": "machine/evidence/EVD-S18-P01_rollback.json",
        "rollback_sha256": "4d5d36930f8fe654bda2c0697140c1f3cabfa75f9e20ca17c444e0a9ef1e0b66",
        "decision": "S18_P01_SAFE_RELEASE_CONTROL_PASS_P02_REQUIRED",
        "next": "S18/P02_READY_NOT_STARTED",
        "required_checks": (
            "S18P01-PIPELINE-FAIL-CLOSED-EXACT",
            "S18P01-CANARY-POLICY-FAIL-CLOSED-EXACT",
            "S18P01-PROBE-REPLAY-AND-FAIL-CLOSED-EXACT",
            "S18P01-ADVERSE-ONE-IN-TEN-THOUSAND-STABLE",
        ),
        "verifier": verify_p01,
    },
    "P02": {
        "requirement_id": "REQ-S18-P02",
        "contract_id": "AC-S18-P02",
        "target": "每个高优先级告警有唯一自动或人工动作。",
        "outputs": ["dashboards.json", "alerts.json", "diagnostic_bundle.py"],
        "task_outputs": {
            "T-S18-P02-01": ["dashboards.json", "alerts.json", "diagnostic_bundle.py"],
            "T-S18-P02-02": ["tests/S18/P02_test.py", "machine/tests/fixtures/S18_P02.json"],
            "T-S18-P02-03": ["machine/evidence/EVD-S18-P02.json", "machine/evidence/EVD-S18-P02_rollback.json"],
        },
        "test_ids": ("TEST-S18-P02", "TEST-S18-P02-BOUNDARY", "TEST-S18-P02-REPLAY"),
        "artifact_ids": ("ART-S18-P02-01", "ART-S18-P02-02", "ART-S18-P02-03"),
        "evidence_path": "machine/evidence/EVD-S18-P02.json",
        "evidence_sha256": "ce54a29f06d7dae07c1e559eebf360c7e41221851290d78496fdf51dd3b957c2",
        "rollback_path": "machine/evidence/EVD-S18-P02_rollback.json",
        "rollback_sha256": "74d475e7dddcfab4b1331fe068190e4137cc9f99c050f6f3454bb3afc112f02c",
        "decision": "S18_P02_OBSERVABILITY_CONTROL_PASS_P03_REQUIRED",
        "next": "S18/P03_READY_NOT_STARTED",
        "required_checks": (
            "S18P02-DASHBOARD-ALERT-UNIQUE-ACTION-EXACT",
            "S18P02-ALL-HIGH-PRIORITY-ALERTS-HAVE-ONE-UNIQUE-ACTION",
            "S18P02-ADVERSE-ONE-IN-TEN-THOUSAND-STABLE",
        ),
        "verifier": verify_p02,
    },
    "P03": {
        "requirement_id": "REQ-S18-P03",
        "contract_id": "AC-S18-P03",
        "target": "自愈不能修改资金事实或放宽风险门。",
        "outputs": ["self_heal_policy.json", "watchdog.py", "outbox_worker.py"],
        "task_outputs": {
            "T-S18-P03-01": ["self_heal_policy.json", "watchdog.py", "outbox_worker.py"],
            "T-S18-P03-02": ["tests/S18/P03_test.py", "machine/tests/fixtures/S18_P03.json"],
            "T-S18-P03-03": ["machine/evidence/EVD-S18-P03.json", "machine/evidence/EVD-S18-P03_rollback.json"],
        },
        "test_ids": ("TEST-S18-P03", "TEST-S18-P03-BOUNDARY", "TEST-S18-P03-REPLAY"),
        "artifact_ids": ("ART-S18-P03-01", "ART-S18-P03-02", "ART-S18-P03-03"),
        "evidence_path": "machine/evidence/EVD-S18-P03.json",
        "evidence_sha256": "99ade2e845cd72af99713e4c0d5d07e2aea3a1e49e6895f5b9bcdeca2a9afe1f",
        "rollback_path": "machine/evidence/EVD-S18-P03_rollback.json",
        "rollback_sha256": "43922654ea06dc674986a9502da55daf1f128b5df42eb1a69fc103ec0ab4949f",
        "decision": "S18_P03_LIMITED_SELF_HEAL_CONTROL_PASS_P04_REQUIRED",
        "next": "S18/P04_READY_NOT_STARTED",
        "required_checks": (
            "S18P03-IMMUTABLE-FUND-AND-RISK-POLICY-EXACT",
            "S18P03-SELF-HEAL-PRESERVES-FUND-FACTS-AND-RISK-GATES",
            "S18P03-OUTBOX-LOCAL-ONLY-NOT-SENT",
            "S18P03-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-RISK-GATE",
        ),
        "verifier": verify_p03,
    },
    "P04": {
        "requirement_id": "REQ-S18-P04",
        "contract_id": "AC-S18-P04",
        "target": "正常运行无需用户维护；异常仅按暂停合同升级。",
        "outputs": ["operations_runbook.md", "scheduled_jobs.json", "maintenance_calendar.json"],
        "task_outputs": {
            "T-S18-P04-01": ["operations_runbook.md", "scheduled_jobs.json", "maintenance_calendar.json"],
            "T-S18-P04-02": ["tests/S18/P04_test.py", "machine/tests/fixtures/S18_P04.json"],
            "T-S18-P04-03": ["machine/evidence/EVD-S18-P04.json", "machine/evidence/EVD-S18-P04_rollback.json"],
        },
        "test_ids": ("TEST-S18-P04", "TEST-S18-P04-BOUNDARY", "TEST-S18-P04-REPLAY"),
        "artifact_ids": ("ART-S18-P04-01", "ART-S18-P04-02", "ART-S18-P04-03"),
        "evidence_path": "machine/evidence/EVD-S18-P04.json",
        "evidence_sha256": "b196f207508350f8dbdb51efcd880f1fe616880e490af344bd3b2d238c142931",
        "rollback_path": "machine/evidence/EVD-S18-P04_rollback.json",
        "rollback_sha256": "16549e9bc30e27ec7dac585efd43cf6310b91cbfe44271a1db5d61b13ad2cd12",
        "decision": "S18_P04_OPERATIONS_AUTOMATION_PASS_STAGE_REVIEW_REQUIRED",
        "next": "S18/STAGE_REVIEW_READY_NOT_STARTED",
        "required_checks": (
            "S18P04-RUNBOOK-PAUSE-CONTRACT-EXACT",
            "S18P04-NORMAL-CYCLE-NO-OWNER-MAINTENANCE",
            "S18P04-ALL-SCHEDULED-JOB-FAILURES-PAUSE-EXACT",
            "S18P04-ADVERSE-ONE-IN-TEN-THOUSAND-PRESERVES-GATES",
        ),
        "verifier": verify_p04,
    },
}

CONTROL_CODE_PATHS = {
    "P01": (Path("post_release_probe.py"),),
    "P02": (Path("diagnostic_bundle.py"),),
    "P03": (Path("watchdog.py"), Path("outbox_worker.py")),
    "P04": (Path("abd_acceptance/operations_automation.py"),),
}
CONTROL_ARTIFACTS = (
    Path("release_pipeline.yml"),
    Path("canary_policy.json"),
    Path("post_release_probe.py"),
    Path("dashboards.json"),
    Path("alerts.json"),
    Path("diagnostic_bundle.py"),
    Path("self_heal_policy.json"),
    Path("watchdog.py"),
    Path("outbox_worker.py"),
    Path("operations_runbook.md"),
    Path("scheduled_jobs.json"),
    Path("maintenance_calendar.json"),
)
REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "SAFE_RELEASE_PROBE_CANARY_FAIL_CLOSED_PRESERVED",
    "HIGH_PRIORITY_ALERTS_UNIQUE_ACTION_PRESERVED",
    "LIMITED_SELF_HEAL_FUND_RISK_AND_OUTBOX_BOUNDARY_PRESERVED",
    "OPERATIONS_NORMAL_NO_MAINTENANCE_AND_PAUSE_CONTRACT_PRESERVED",
    "NO_NETWORK_RUNTIME_ACCOUNT_DATABASE_ORDER_DEPLOY_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_S18_REVIEW_FINDINGS_RESOLVED",
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
    "S18 只复核冻结的本地发布、告警、自愈和值守控制及其已签名证据。",
    "S18 复审通过不构成真实 OVH、Cloudflare、数据库、TAB/Gmail、调度器、备份、容灾、市场、账户、部署或实际收益证明。",
    "本复审不覆盖既有阶段的独立连续性限制，且不通过引用覆盖或消除它们。",
    "A$300×1.3^n 的30%月度目标仍为 UNVERIFIED_NOT_GUARANTEED。",
]
RESOLVED_FINDINGS = [
    {
        "id": "S18-REVIEW-001",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "蓝绿、canary 与探针制品可能被误读为已在 OVH 或 Cloudflare 上切流和运行。",
        "resolution": "P01 将发布流程限定为离线确定性控制面；任何探针失败、未知或格式错误都回到上一签名槽位并保持建议禁用。",
        "resolution_evidence": ["release_pipeline.yml", "canary_policy.json", "machine/evidence/EVD-S18-P01.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S18-REVIEW-002",
        "severity": "CRITICAL",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "高优先级告警与有限自愈若没有唯一动作、资金/风险不变量或本地 outbox 边界，可能被误解为可对账户或订单产生动作。",
        "resolution": "P02 为每个高优先级告警固定唯一逻辑动作；P03 保持资金事实与风险门不可变，并将所有升级限制为未发送的本地结构化 outbox。",
        "resolution_evidence": ["alerts.json", "self_heal_policy.json", "machine/evidence/EVD-S18-P02.json", "machine/evidence/EVD-S18-P03.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S18-REVIEW-003",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "日周月值守、补丁、备份和容灾逻辑可能被误读为已安装调度器、执行真实备份或进行真实灾难恢复。",
        "resolution": "P04 将正常周期固定为无需用户维护的离线控制面；任何任务失败或不安全输入仅触发暂停合同和本地 owner outbox 升级。",
        "resolution_evidence": ["operations_runbook.md", "scheduled_jobs.json", "maintenance_calendar.json", "machine/evidence/EVD-S18-P04.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
]
SNAPSHOT_CASE_IDS = (
    "POSITIVE_EXACT_STAGE",
    "PHASE_RECEIPT_FAIL",
    "TASKPACK_TRACE_FAIL",
    "SAFE_RELEASE_GATE_FAIL",
    "OBSERVABILITY_GATE_FAIL",
    "SELF_HEAL_GATE_FAIL",
    "OPERATIONS_PAUSE_GATE_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PORTABILITY_FAIL",
    "OPEN_FINDING_FAIL",
)


class Stage18ReviewError(ValueError):
    """Raised when the local S18 stage-review contract is not reproducible."""


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
            raise Stage18ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage18ReviewError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage18ReviewError("rows are unavailable")
    matching = [value for value in rows if isinstance(value, Mapping) and value.get(key) == identifier]
    if len(matching) != 1:
        raise Stage18ReviewError("expected exactly one %s=%s" % (key, identifier))
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
        ("safe_release_gate_preserved", "SAFE_RELEASE_GATE_RELAXED"),
        ("observability_gate_preserved", "OBSERVABILITY_UNIQUE_ACTION_GATE_RELAXED"),
        ("self_heal_gate_preserved", "SELF_HEAL_FUND_OR_RISK_GATE_RELAXED"),
        ("operations_pause_gate_preserved", "OPERATIONS_PAUSE_CONTRACT_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    required = {key for key, _ in bool_keys} | {"findings_open"}
    if set(snapshot) != required or any(type(snapshot[key]) is not bool for key, _ in bool_keys):
        raise Stage18ReviewError("stage snapshot is malformed")
    findings_open = snapshot["findings_open"]
    if type(findings_open) is not int or findings_open < 0:
        raise Stage18ReviewError("findings_open must be a nonnegative integer")
    reasons = [reason for key, reason in bool_keys if snapshot[key] is not True]
    if findings_open != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    status = "S18_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S18_STAGE_REVIEW_REJECTED_NO_ACTION"
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
        _add(checks, "S18REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "stage_review_addendum": ADDENDUM_STATUS,
        "targeted_test_command": "pytest -q tests/S18/stage_review_test.py",
        "release_status_on_pass": "S18_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S18/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S18/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S18REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S18REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S18REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S18REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S18REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S18REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S18-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": len(SNAPSHOT_CASE_IDS),
        "minimum_targeted_pytest_cases": 28,
        "expected_phase_ids": list(PHASE_SPECS),
        "expected_phase_evidence_sha256": {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_phase_rollback_sha256": {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_next": "S18/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S18_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 3, "open": 0, "resolved": 3, "blocked": 0},
    }
    _add(checks, "S18REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S18REVIEW-SINGLE-PASS-CASES-EXACT",
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
    _add(checks, "S18REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    passed = True
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        ok = actual == expected
        _add(checks, "S18REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), ok, {"expected": expected, "actual": actual})
        passed = passed and ok
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S18REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S18REVIEW-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S18REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S18REVIEW-TRACEABILITY-PARSE")
    try:
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise Stage18ReviewError("task graph unavailable")
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
                and trace.get("evidence_id") == "EVD-S18-%s" % phase
                and trace.get("artifact_ids") == list(spec["artifact_ids"])
            )
            _add(checks, "S18REVIEW-%s-TASKPACK-TRACE-EXACT" % phase, phase_ok, {"tasks": task_ids})
            valid = valid and phase_ok
    except Exception as exc:
        valid = False
        _add(checks, "S18REVIEW-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return valid


def _all_validation_checks_pass(receipt: Mapping[str, Any]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, Mapping) and row.get("passed") is True for row in rows)


def _receipt_boundary(boundary: Any) -> bool:
    required_false = (
        "external_network_accessed",
        "recommendation_generated_or_enabled",
        "order_submission_enabled",
        "production_deployed_or_activated",
        "real_time_soak_waited",
    )
    return isinstance(boundary, Mapping) and all(boundary.get(key) is False for key in required_false) and boundary.get("incremental_cash_spent_aud") == "0.00"


def _control_boundary(boundary: Any) -> bool:
    """Check the shared local-only fields present in every S18 control file."""

    required_false = (
        "external_network_accessed",
        "recommendation_generated_or_enabled",
        "order_submission_enabled",
        "production_deployed_or_activated",
    )
    return isinstance(boundary, Mapping) and all(boundary.get(key) is False for key in required_false) and boundary.get("incremental_cash_spent_aud") == "0.00"


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    all_ok = True
    receipts: Dict[str, Mapping[str, Any]] = {}
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        index_rows = []
        _add(checks, "S18REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        all_ok = False
    for phase, spec in PHASE_SPECS.items():
        try:
            receipt = strict_json_load(root / spec["evidence_path"])
            rollback = strict_json_load(root / spec["rollback_path"])
            index = _row(index_rows, "INDEX-%s" % spec["contract_id"])
            verifier_result = spec["verifier"](root)
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
                and verifier_result.get("status") == "PASS"
                and verifier_result.get("evidence_sha256") == spec["evidence_sha256"]
            )
            detail: Any = {"verifier": verifier_result, "receipt_sha256": receipt_hash}
            receipts[phase] = receipt
            hashes[spec["evidence_path"]] = receipt_hash
            hashes[spec["rollback_path"]] = rollback_hash
        except Exception as exc:
            valid = False
            detail = "%s: %s" % (type(exc).__name__, exc)
            receipts[phase] = {}
        _add(checks, "S18REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, valid, detail)
        all_ok = all_ok and valid
    return all_ok, receipts


def _load_control(root: Path, path: str) -> Mapping[str, Any]:
    value = strict_json_load(root / path)
    if not isinstance(value, Mapping):
        raise Stage18ReviewError("control document is not an object: %s" % path)
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


def _check_stage_controls(root: Path, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Dict[str, bool]:
    controls = {"p01": False, "p02": False, "p03": False, "p04": False}
    try:
        pipeline = _load_control(root, "release_pipeline.yml")
        canary = _load_control(root, "canary_policy.json")
        p01_boundary = pipeline.get("external_effect_boundary")
        canary_boundary = canary.get("external_effect_boundary")
        profiles = canary.get("canary_profiles")
        controls["p01"] = (
            pipeline.get("contract_id") == "AC-S18-P01"
            and pipeline.get("execution_mode") == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
            and pipeline.get("entry_conditions", {}).get("live_recommendation_enabled") is False
            and pipeline.get("entry_conditions", {}).get("order_submission_enabled") is False
            and pipeline.get("rollback_policy", {}).get("on_any_probe_failure") is True
            and pipeline.get("rollback_policy", {}).get("advice_remains_disabled") is True
            and canary.get("contract_id") == "AC-S18-P01"
            and canary.get("failure_action") == "AUTO_ROLL_BACK_TO_PREVIOUS_SLOT_KEEP_ADVICE_DISABLED"
            and isinstance(profiles, list)
            and bool(profiles)
            and all(isinstance(item, Mapping) and item.get("live_recommendation") is False and item.get("order_submission_enabled") is False for item in profiles)
            and _control_boundary(p01_boundary)
            and _control_boundary(canary_boundary)
            and _local_control_code(root, "P01", hashes)
        )
        hashes["release_pipeline.yml"] = sha256_file(root / "release_pipeline.yml")
        hashes["canary_policy.json"] = sha256_file(root / "canary_policy.json")
        detail: Any = {"profiles": len(profiles) if isinstance(profiles, list) else None, "failure_action": canary.get("failure_action")}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18REVIEW-SAFE-RELEASE-PROBE-CANARY-FAIL-CLOSED-GATE", controls["p01"], detail)
    try:
        dashboards = _load_control(root, "dashboards.json")
        alerts = _load_control(root, "alerts.json")
        rows = alerts.get("high_priority_alerts")
        action_ids = [item.get("action", {}).get("action_id") for item in rows if isinstance(item, Mapping)] if isinstance(rows, list) else []
        controls["p02"] = (
            dashboards.get("contract_id") == "AC-S18-P02"
            and dashboards.get("execution_mode") == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
            and alerts.get("contract_id") == "AC-S18-P02"
            and alerts.get("safe_action") == "NO_RECOMMENDATION_NO_ORDER"
            and isinstance(rows, list)
            and bool(rows)
            and len(action_ids) == len(rows) == len(set(action_ids))
            and all(isinstance(item, Mapping) and item.get("action", {}).get("logical_effect") == "NO_RECOMMENDATION_NO_ORDER" for item in rows)
            and _control_boundary(dashboards.get("external_effect_boundary"))
            and _control_boundary(alerts.get("external_effect_boundary"))
            and _local_control_code(root, "P02", hashes)
        )
        hashes["dashboards.json"] = sha256_file(root / "dashboards.json")
        hashes["alerts.json"] = sha256_file(root / "alerts.json")
        detail = {"high_priority_alerts": len(rows) if isinstance(rows, list) else None, "unique_actions": len(set(action_ids))}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18REVIEW-HIGH-PRIORITY-ALERTS-UNIQUE-ACTION-GATE", controls["p02"], detail)
    try:
        policy = _load_control(root, "self_heal_policy.json")
        operations = policy.get("allowed_operations")
        immutable_fund = policy.get("immutable_fund_facts", {})
        immutable_risk = policy.get("immutable_risk_gate", {})
        outbox = policy.get("outbox_policy", {})
        controls["p03"] = (
            policy.get("contract_id") == "AC-S18-P03"
            and policy.get("execution_mode") == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
            and immutable_fund.get("actual_fund_fact_mutation_allowed") is False
            and immutable_fund.get("actual_ledger_mutation_allowed") is False
            and immutable_risk.get("target_shortfall_may_relax_gate") is False
            and isinstance(operations, list)
            and bool(operations)
            and all(isinstance(item, Mapping) and item.get("derived_state_only") is True and item.get("writes_shared_ledger") is False for item in operations)
            and outbox.get("external_delivery_enabled") is False
            and outbox.get("retry_external_delivery") is False
            and _control_boundary(policy.get("external_effect_boundary"))
            and _local_control_code(root, "P03", hashes)
        )
        hashes["self_heal_policy.json"] = sha256_file(root / "self_heal_policy.json")
        detail = {"operations": len(operations) if isinstance(operations, list) else None, "outbox": outbox.get("delivery_mode")}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18REVIEW-LIMITED-SELF-HEAL-FUND-RISK-OUTBOX-GATE", controls["p03"], detail)
    try:
        schedule = _load_control(root, "scheduled_jobs.json")
        calendar = _load_control(root, "maintenance_calendar.json")
        jobs = schedule.get("jobs")
        windows = calendar.get("maintenance_windows")
        controls["p04"] = (
            schedule.get("contract_id") == "AC-S18-P04"
            and schedule.get("execution_mode") == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
            and schedule.get("normal_operation", {}).get("owner_maintenance_required") is False
            and schedule.get("exception_policy", {}).get("pause_contract") is True
            and schedule.get("exception_policy", {}).get("external_delivery_enabled") is False
            and isinstance(jobs, list)
            and len(jobs) == 6
            and all(isinstance(item, Mapping) and item.get("failure_action") == "PAUSE_CONTRACT_AND_ESCALATE_OWNER_OUTBOX_ONLY" and item.get("external_effects_permitted") is False for item in jobs)
            and calendar.get("normal_owner_maintenance_required") is False
            and calendar.get("exception_escalation", {}).get("pause_contract") is True
            and calendar.get("exception_escalation", {}).get("external_delivery_enabled") is False
            and isinstance(windows, list)
            and len(windows) == 6
            and all(isinstance(item, Mapping) and item.get("requires_owner_maintenance_normal") is False for item in windows)
            and _control_boundary(schedule.get("external_effect_boundary"))
            and _control_boundary(calendar.get("external_effect_boundary"))
            and _local_control_code(root, "P04", hashes)
        )
        hashes["scheduled_jobs.json"] = sha256_file(root / "scheduled_jobs.json")
        hashes["maintenance_calendar.json"] = sha256_file(root / "maintenance_calendar.json")
        hashes["operations_runbook.md"] = sha256_file(root / "operations_runbook.md")
        detail = {"jobs": len(jobs) if isinstance(jobs, list) else None, "windows": len(windows) if isinstance(windows, list) else None}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18REVIEW-OPERATIONS-NORMAL-AND-PAUSE-CONTRACT-GATE", controls["p04"], detail)
    return controls


def _check_external_boundary(contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    receipt_boundaries = all(_receipt_boundary(receipt.get("external_effect_boundary")) for receipt in receipts.values() if isinstance(receipt, Mapping)) and len(receipts) == len(PHASE_SPECS)
    exact = isinstance(contract, Mapping) and contract.get("execution_policy") == EXECUTION_POLICY and isinstance(findings, Mapping) and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
    valid = exact and receipt_boundaries
    _add(checks, "S18REVIEW-NO-NETWORK-RUNTIME-ACCOUNT-DATABASE-ORDER-DEPLOY-OR-SOAK-BOUNDARY", valid, {"review": EXTERNAL_EFFECT_BOUNDARY, "receipts_current": receipt_boundaries})
    return valid


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> None:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S18REVIEW-SNAPSHOT-CASES-FAIL-CLOSED", False, "cases unavailable")
        return
    passed = True
    details = []
    for case in cases:
        try:
            if not isinstance(case, Mapping):
                raise Stage18ReviewError("case is malformed")
            result = evaluate_stage_snapshot(case["snapshot"])
            expected = case["expected"]
            ok = result.get("status") == expected.get("status") and result.get("reason_codes") == expected.get("reason_codes")
        except Exception as exc:
            ok = False
            result = "%s: %s" % (type(exc).__name__, exc)
        passed = passed and ok
        details.append({"case_id": case.get("case_id") if isinstance(case, Mapping) else None, "passed": ok, "result": result})
    _add(checks, "S18REVIEW-SNAPSHOT-CASES-FAIL-CLOSED", passed, details)


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
    _add(checks, "S18REVIEW-ORACLE-STATIC-NO-NETWORK-PROCESS-WAIT-OR-ORDER", valid, "parsed" if valid else source)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .stage18_review import verify_existing_stage_review_evidence as verify_existing_stage18_review_evidence" in source
            and "from .stage18_review import write_stage_review_evidence as write_stage18_review_evidence" in source
            and '"STAGE-REVIEW-S18": verify_existing_stage18_review_evidence,' in source
            and '"STAGE-REVIEW-S18": write_stage18_review_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18REVIEW-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)


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
    _add(checks, "S18REVIEW-TARGETED-PYTEST-REPORT", pytest_ok, {"summary": summary, "normalized": normalized})
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
    _add(checks, "S18REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, "present" if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        pack_ok = report.get("status") == "PASS" and report.get("summary", {}).get("failed") == 0 and report.get("summary", {}).get("passed") == report.get("summary", {}).get("checks")
    except Exception as exc:
        pack_ok = False
        report = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S18REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report.get("summary") if isinstance(report, Mapping) else report)
    return pytest_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": status,
        "stage_status": "S18_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S18_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S18_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S18_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S18/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S18/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the local S18 review without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, CONTRACT_PATH, checks, "S18REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S18REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, FINDINGS_PATH, checks, "S18REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, receipts, checks, hashes)
    boundary_ok = _check_external_boundary(contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = _portable(contract) and _portable(fixture) and _portable(findings) and all(_portable(receipt) for receipt in receipts.values())
    _add(checks, "S18REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "absolute path found")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) and isinstance(findings.get("summary"), Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "safe_release_gate_preserved": controls["p01"],
        "observability_gate_preserved": controls["p02"],
        "self_heal_gate_preserved": controls["p03"],
        "operations_pause_gate_preserved": controls["p04"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S18REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S18_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_cli_wiring(root, checks)
    _add(checks, "S18REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
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
        "evidence_id": "EVD-S18-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S18_STAGE_REVIEW_CANDIDATE_KEEP_RUNTIME_AND_RELEASE_BLOCKED",
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
        "evidence_id": "EVD-S18-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S18_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S18_STAGE_REVIEW_REMEDIATION_REQUIRED",
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
            "uv run --frozen --python 3.12 python -m pytest -q tests/S18/stage_review_test.py --junitxml=machine/evidence/S18/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S18/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S18/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S18 --evidence machine/evidence",
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
        raise Stage18ReviewError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-S18-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S18/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    matching = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) > 1:
        raise Stage18ReviewError("S18 stage-review evidence-index row is duplicated")
    if not matching:
        raw_lines.append(json.dumps(replacement, ensure_ascii=False, sort_keys=True))
    else:
        raw_lines[matching[0]] = json.dumps(replacement, ensure_ascii=False, sort_keys=True)
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage18ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage18ReviewError("cannot write a failed S18 stage review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/GITHUB_STAGE_UPLOAD_READY",
    }


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-S18-STAGE-REVIEW")
    except Exception as exc:
        raise Stage18ReviewError("existing S18 stage-review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S18-STAGE-REVIEW"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("stage_status") == "S18_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("decision") == "S18_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S18/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S18_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
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
        and index.get("next") == "S18/GITHUB_STAGE_UPLOAD_READY"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise Stage18ReviewError("existing S18 stage-review evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S18/GITHUB_STAGE_UPLOAD_READY",
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
    "Stage18ReviewError",
    "evaluate_contract",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
