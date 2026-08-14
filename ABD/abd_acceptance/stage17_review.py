"""Fail-closed, local-only whole-stage review oracle for ABD S17.

The S17 review is a local addendum, not a replacement for frozen Task Pack
facts. It replays only signed Phase receipts and their deterministic control
artifacts. It does not access a runtime, account, database, provider, or
network, and it never performs a real-time soak, deployment, recommendation,
or order action.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .chaos import verify_existing_phase_evidence as verify_p03
from .concurrency_idempotency import verify_existing_phase_evidence as verify_p02
from .load_test import verify_existing_phase_evidence as verify_p01
from .recovery import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S17"
REVIEW_ID = "ABD-S17-WHOLE-STAGE-REVIEW"
STAGE_ID = "S17"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
ADDENDUM_STATUS = "LOCAL_STAGE_REVIEW_CONTRACT_NOT_A_FROZEN_TASK_PACK_FACT"

CONTRACT_PATH = Path("machine/facts/stage17_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S17/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S17_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S17/stage_review_test.py")
ORACLE_PATH = Path("abd_acceptance/stage17_review.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S17-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S17-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S17/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S17/STAGE_REVIEW/paid_dependency_scan.txt")
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
        "requirement_id": "REQ-S17-P01",
        "contract_id": "AC-S17-P01",
        "target": "VPS-1资源门内且无静默丢数据。",
        "outputs": ["load_test.py", "load_profile.json", "capacity_evidence.json"],
        "task_outputs": {
            "T-S17-P01-01": ["load_test.py", "load_profile.json", "capacity_evidence.json"],
            "T-S17-P01-02": ["tests/S17/P01_test.py", "machine/tests/fixtures/S17_P01.json"],
            "T-S17-P01-03": ["machine/evidence/EVD-S17-P01.json", "machine/evidence/EVD-S17-P01_rollback.json"],
        },
        "test_ids": ("TEST-S17-P01", "TEST-S17-P01-BOUNDARY", "TEST-S17-P01-REPLAY"),
        "artifact_ids": ("ART-S17-P01-01", "ART-S17-P01-02", "ART-S17-P01-03"),
        "evidence_path": "machine/evidence/EVD-S17-P01.json",
        "evidence_sha256": "2f8cc9265cea7eec0e28d6ae0608ba6548a75378d28b850e639509465bff2fa9",
        "rollback_path": "machine/evidence/EVD-S17-P01_rollback.json",
        "rollback_sha256": "daaf5ca4b5f3b4c5089aa9a75d7ec0837bda8447943a32842ac502a11d401b88",
        "decision": "S17_P01_FROZEN_FULL_HISTORY_10X_LOAD_PASS_P02_REQUIRED",
        "next": "S17/P02_READY_NOT_STARTED",
        "required_checks": (
            "S17P01-FROZEN-10X-LOAD-PROFILE-EXACT",
            "S17P01-VPS-ENVELOPE-AND-NO-SILENT-DROP-EXACT",
            "S17P01-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
        "verifier": verify_p01,
    },
    "P02": {
        "requirement_id": "REQ-S17-P02",
        "contract_id": "AC-S17-P02",
        "target": "重复建议/账本事件为0。",
        "outputs": ["concurrency_test.py", "idempotency_report.json"],
        "task_outputs": {
            "T-S17-P02-01": ["concurrency_test.py", "idempotency_report.json"],
            "T-S17-P02-02": ["tests/S17/P02_test.py", "machine/tests/fixtures/S17_P02.json"],
            "T-S17-P02-03": ["machine/evidence/EVD-S17-P02.json", "machine/evidence/EVD-S17-P02_rollback.json"],
        },
        "test_ids": ("TEST-S17-P02", "TEST-S17-P02-BOUNDARY", "TEST-S17-P02-REPLAY"),
        "artifact_ids": ("ART-S17-P02-01", "ART-S17-P02-02"),
        "evidence_path": "machine/evidence/EVD-S17-P02.json",
        "evidence_sha256": "c417d9eb732c24969d11db52bd501438572a57e2b3eeef8791085e746aae2711",
        "rollback_path": "machine/evidence/EVD-S17-P02_rollback.json",
        "rollback_sha256": "8d496ff9548c7b71dd1777c4067e91b7c8148d3337efde160a14b57150fa5a3c",
        "decision": "S17_P02_IDEMPOTENCY_PASS_P03_REQUIRED",
        "next": "S17/P03_READY_NOT_STARTED",
        "required_checks": (
            "S17P02-IDEMPOTENCY-ARTIFACT-REPLAY-EXACT",
            "S17P02-ZERO-DUPLICATE-SUGGESTION-AND-LEDGER-EXACT",
            "S17P02-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
        "verifier": verify_p02,
    },
    "P03": {
        "requirement_id": "REQ-S17-P03",
        "contract_id": "AC-S17-P03",
        "target": "错误时不使用陈旧数据且自动降级。",
        "outputs": ["chaos_scenarios.json", "chaos_runner.py"],
        "task_outputs": {
            "T-S17-P03-01": ["chaos_scenarios.json", "chaos_runner.py"],
            "T-S17-P03-02": ["tests/S17/P03_test.py", "machine/tests/fixtures/S17_P03.json"],
            "T-S17-P03-03": ["machine/evidence/EVD-S17-P03.json", "machine/evidence/EVD-S17-P03_rollback.json"],
        },
        "test_ids": ("TEST-S17-P03", "TEST-S17-P03-BOUNDARY", "TEST-S17-P03-REPLAY"),
        "artifact_ids": ("ART-S17-P03-01", "ART-S17-P03-02"),
        "evidence_path": "machine/evidence/EVD-S17-P03.json",
        "evidence_sha256": "2f40bd1eed62a0b1ed14347507d497fa54cc63db56c4f31112c631fe48beef97",
        "rollback_path": "machine/evidence/EVD-S17-P03_rollback.json",
        "rollback_sha256": "73de0722f20bf34a76c461e87a36bd6b8748168d1bd8dbfb8b60d9df8d7364b4",
        "decision": "S17_P03_CHAOS_STALE_DATA_GATE_PASS_P04_REQUIRED",
        "next": "S17/P04_READY_NOT_STARTED",
        "required_checks": (
            "S17P03-CHAOS-ARTIFACT-REPLAY-EXACT",
            "S17P03-STALE-DATA-REJECTED-AND-DEGRADED-EXACT",
            "S17P03-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
        "verifier": verify_p03,
    },
    "P04": {
        "requirement_id": "REQ-S17-P04",
        "contract_id": "AC-S17-P04",
        "target": "账本恢复点≤60秒，建议服务恢复≤15分钟。",
        "outputs": ["recovery_test.py", "disaster_drill.md", "recovery_report.json"],
        "task_outputs": {
            "T-S17-P04-01": ["recovery_test.py", "disaster_drill.md", "recovery_report.json"],
            "T-S17-P04-02": ["tests/S17/P04_test.py", "machine/tests/fixtures/S17_P04.json"],
            "T-S17-P04-03": ["machine/evidence/EVD-S17-P04.json", "machine/evidence/EVD-S17-P04_rollback.json"],
        },
        "test_ids": ("TEST-S17-P04", "TEST-S17-P04-BOUNDARY", "TEST-S17-P04-REPLAY"),
        "artifact_ids": ("ART-S17-P04-01", "ART-S17-P04-02", "ART-S17-P04-03"),
        "evidence_path": "machine/evidence/EVD-S17-P04.json",
        "evidence_sha256": "08e1d389d3b0d80d6c729d9835dc27343018985cd8cc1796a9528b5ed7d6e708",
        "rollback_path": "machine/evidence/EVD-S17-P04_rollback.json",
        "rollback_sha256": "6d268bbbec86958f790f78da7ef4194b2a542c4231d8b0ebc8fb5143f25c0622",
        "decision": "S17_P04_RECOVERY_DRILL_PASS_STAGE_REVIEW_REQUIRED",
        "next": "S17/STAGE_REVIEW_READY_NOT_STARTED",
        "required_checks": (
            "S17P04-RECOVERY-ARTIFACT-REPLAY-EXACT",
            "S17P04-RPO_RTO_GATE_AND_FAIL_CLOSED-EXACT",
            "S17P04-EXTERNAL-EFFECT-BOUNDARY-EXACT",
        ),
        "verifier": verify_p04,
    },
}

REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "FROZEN_LOAD_ENVELOPE_COUNT_CONSERVING_NO_SILENT_DROP_PRESERVED",
    "IDEMPOTENCY_NO_DUPLICATE_SUGGESTION_OR_LEDGER_PRESERVED",
    "CHAOS_STALE_DATA_REJECTED_AND_AUTO_DEGRADED_PRESERVED",
    "RECOVERY_RPO_RTO_FAIL_CLOSED_LOGICAL_GATE_PRESERVED",
    "NO_NETWORK_RUNTIME_ACCOUNT_DATABASE_ORDER_DEPLOY_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_S17_REVIEW_FINDINGS_RESOLVED",
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
    "S17 只验证冻结本地负载、逻辑并发、逻辑故障与逻辑恢复控制及其已签名证据。",
    "S17 复审通过不构成真实 OVH/VPS 容量、数据库恢复、Cloudflare、TAB/Gmail、市场、账户、部署或实际收益证明。",
    "既有 S07/S08 连续性回放的已知独立限制不在本次 S17 复审范围内，且未被本次结果覆盖或消除。",
    "A$300×1.3^n 的30%月度目标仍为 UNVERIFIED_NOT_GUARANTEED。",
]
RESOLVED_FINDINGS = [
    {
        "id": "S17-REVIEW-001",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "冻结 10× 全历史重放可能被误读为真实 VPS 容量、吞吐或 soak 证明。",
        "resolution": "P01 将资源门固定为本地计数守恒制品，明确未观察真实 VPS，并在资源不可用或超限时保持运行时部署阻断。",
        "resolution_evidence": ["load_profile.json", "capacity_evidence.json", "machine/evidence/EVD-S17-P01.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S17-REVIEW-002",
        "severity": "CRITICAL",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "逻辑并发和逻辑故障控制不得产生重复建议、真实账本事件、陈旧数据使用或订单动作。",
        "resolution": "P02 将重复建议和账本事件门固定为零；P03 对八类错误拒绝陈旧数据并自动降级；两者均保持 NO_RECOMMENDATION_NO_ORDER。",
        "resolution_evidence": ["idempotency_report.json", "chaos_scenarios.json", "machine/evidence/EVD-S17-P02.json", "machine/evidence/EVD-S17-P03.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S17-REVIEW-003",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "逻辑 RPO/RTO 门可能被误读为已执行的备份恢复或建议服务恢复。",
        "resolution": "P04 固定 60 秒/900 秒逻辑门及 61 秒/901 秒失败关闭向量，演练文档明确不重启、不读写账本、不恢复备份、不删除票据。",
        "resolution_evidence": ["disaster_drill.md", "recovery_report.json", "machine/evidence/EVD-S17-P04.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
]
SNAPSHOT_CASE_IDS = (
    "POSITIVE_EXACT_STAGE",
    "PHASE_RECEIPT_FAIL",
    "TASKPACK_TRACE_FAIL",
    "LOAD_GATE_FAIL",
    "IDEMPOTENCY_GATE_FAIL",
    "CHAOS_GATE_FAIL",
    "RECOVERY_GATE_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PORTABILITY_FAIL",
    "OPEN_FINDING_FAIL",
)
CONTROL_ARTIFACTS = (
    Path("load_profile.json"),
    Path("capacity_evidence.json"),
    Path("idempotency_report.json"),
    Path("chaos_scenarios.json"),
    Path("disaster_drill.md"),
    Path("recovery_report.json"),
)


class Stage17ReviewError(ValueError):
    """Raised when the S17 local review cannot reproduce its evidence."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


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
            raise Stage17ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage17ReviewError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage17ReviewError("rows are unavailable")
    matching = [value for value in rows if isinstance(value, Mapping) and value.get(key) == identifier]
    if len(matching) != 1:
        raise Stage17ReviewError("expected exactly one %s=%s" % (key, identifier))
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
        ("load_gate_preserved", "LOAD_ENVELOPE_OR_NO_SILENT_DROP_GATE_RELAXED"),
        ("idempotency_gate_preserved", "IDEMPOTENCY_GATE_RELAXED"),
        ("chaos_gate_preserved", "CHAOS_STALE_DATA_GATE_RELAXED"),
        ("recovery_gate_preserved", "RECOVERY_RPO_RTO_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    required = {key for key, _ in bool_keys} | {"findings_open"}
    if set(snapshot) != required or any(type(snapshot[key]) is not bool for key, _ in bool_keys):
        raise Stage17ReviewError("stage snapshot is malformed")
    findings_open = snapshot["findings_open"]
    if type(findings_open) is not int or findings_open < 0:
        raise Stage17ReviewError("findings_open must be a nonnegative integer")
    reasons = [reason for key, reason in bool_keys if snapshot[key] is not True]
    if findings_open != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    status = "S17_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S17_STAGE_REVIEW_REJECTED_NO_ACTION"
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
        _add(checks, "S17REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "stage_review_addendum": ADDENDUM_STATUS,
        "targeted_test_command": "pytest -q tests/S17/stage_review_test.py",
        "release_status_on_pass": "S17_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S17/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S17/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S17REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S17REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S17REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S17REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S17REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S17REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S17-WHOLE-STAGE-REVIEW",
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
        "expected_next": "S17/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S17_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 3, "open": 0, "resolved": 3, "blocked": 0},
    }
    _add(checks, "S17REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S17REVIEW-SINGLE-PASS-CASES-EXACT",
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
    _add(checks, "S17REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    passed = True
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        ok = actual == expected
        _add(checks, "S17REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), ok, {"expected": expected, "actual": actual})
        passed = passed and ok
    return passed


def _task_rows(value: Any) -> Any:
    return value.get("tasks") if isinstance(value, Mapping) else None


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S17REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S17REVIEW-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S17REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S17REVIEW-TRACEABILITY-PARSE")
    try:
        tasks = _task_rows(graph)
        if not isinstance(tasks, list):
            raise Stage17ReviewError("task graph unavailable")
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
                and trace.get("evidence_id") == "EVD-S17-%s" % phase
                and trace.get("artifact_ids") == list(spec["artifact_ids"])
            )
            _add(checks, "S17REVIEW-%s-TASKPACK-TRACE-EXACT" % phase, phase_ok, {"tasks": task_ids})
            valid = valid and phase_ok
    except Exception as exc:
        valid = False
        _add(checks, "S17REVIEW-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return valid


def _all_validation_checks_pass(receipt: Mapping[str, Any]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, Mapping) and row.get("passed") is True for row in rows)


def _artifact_boundary(boundary: Any) -> bool:
    required_false = (
        "external_network_accessed",
        "financial_return_verified_or_guaranteed",
        "gmail_account_or_api_accessed",
        "order_submission_enabled",
        "ovh_or_cloudflare_runtime_accessed",
        "production_deployed_or_activated",
        "real_account_balance_read_or_written",
        "real_market_or_odds_observed",
        "real_time_soak_waited",
        "real_vps_resource_observed_or_measured",
        "recommendation_generated_or_enabled",
    )
    return (
        isinstance(boundary, Mapping)
        and all(boundary.get(key) is False for key in required_false)
        and boundary.get("incremental_cash_spent_aud") == "0.00"
    )


def _receipt_boundary(boundary: Any) -> bool:
    return (
        _artifact_boundary(boundary)
        and isinstance(boundary, Mapping)
        and boundary.get("evidence_numeric_risk_safety_or_source_gate_relaxed") is False
        and boundary.get("owner_final_order_only") is True
    )


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    all_ok = True
    receipts: Dict[str, Mapping[str, Any]] = {}
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        index_rows = []
        _add(checks, "S17REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
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
                and rollback_hash == spec["rollback_sha256"]
                and index.get("kind") == "PHASE_EVIDENCE"
                and index.get("stage_id") == STAGE_ID
                and index.get("contract_id") == spec["contract_id"]
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
        _add(checks, "S17REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, valid, detail)
        all_ok = all_ok and valid
    return all_ok, receipts


def _all_no_action(rows: Any, *, runtime_field: str | None = None) -> bool:
    return (
        isinstance(rows, list)
        and bool(rows)
        and all(
            isinstance(row, Mapping)
            and row.get("action") == "NO_RECOMMENDATION_NO_ORDER"
            and (runtime_field is None or row.get(runtime_field) is False)
            for row in rows
        )
    )


def _check_stage_controls(root: Path, checks: List[Dict[str, Any]]) -> Dict[str, bool]:
    controls = {"p01": False, "p02": False, "p03": False, "p04": False}
    try:
        capacity = strict_json_load(root / "capacity_evidence.json")
        gate = capacity.get("resource_gate") if isinstance(capacity, Mapping) else None
        loss = capacity.get("no_silent_data_loss") if isinstance(capacity, Mapping) else None
        expected_gate = {
            "actual_vps_capacity_claimed": False,
            "actual_vps_capacity_measured": False,
            "declared_resource_id": "RES-OVH-EXISTING-VPS1",
            "effective_resource_unit_cap": 9999,
            "local_envelope_passed": True,
            "maximum_observed_queue_high_water": 12000,
            "maximum_observed_resource_units": 9999,
            "on_resource_unavailable_or_limit": "BLOCK_RUNTIME_DEPLOYMENT_KEEP_LOCAL_DEVELOPMENT_AND_EVIDENCE",
            "queue_cap": 12000,
            "runtime_deployment_allowed": False,
        }
        expected_loss = {
            "all_inputs_accounted": True,
            "missing_disposition_count": 0,
            "passed": True,
            "silent_drop_count": 0,
            "silent_drop_max": 0,
            "tracked_quarantine_count": 1,
        }
        scenarios = capacity.get("scenario_results") if isinstance(capacity, Mapping) else None
        controls["p01"] = (
            capacity.get("contract_id") == "AC-S17-P01"
            and gate == expected_gate
            and loss == expected_loss
            and isinstance(scenarios, list)
            and [row.get("scenario_id") for row in scenarios if isinstance(row, Mapping)]
            == ["BASELINE_FULL_HISTORY", "TEN_X_FULL_HISTORY", "TEN_X_BOUNDARY_0_9999", "TEN_X_TRACKED_FAULT"]
            and _all_no_action(scenarios)
            and all(
                isinstance(row, Mapping)
                and row.get("accounted_count") == row.get("ingress_count")
                and row.get("dropped_count") == 0
                and row.get("missing_disposition_count") == 0
                for row in scenarios
            )
            and _artifact_boundary(capacity.get("claim_boundary"))
        )
        _add(checks, "S17REVIEW-FROZEN-LOAD-ENVELOPE-NO-SILENT-DROP-GATE", controls["p01"], {"resource_gate": gate, "no_silent_data_loss": loss})
    except Exception as exc:
        _add(checks, "S17REVIEW-FROZEN-LOAD-ENVELOPE-NO-SILENT-DROP-GATE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / "idempotency_report.json")
        aggregate = report.get("aggregate") if isinstance(report, Mapping) else None
        gate = report.get("idempotency_gate") if isinstance(report, Mapping) else None
        policy = report.get("idempotency_policy") if isinstance(report, Mapping) else None
        expected_aggregate = {
            "accepted_local_projection_count": 8,
            "input_attempt_count": 19,
            "quarantined_key_conflict_count": 1,
            "suppressed_duplicate_attempt_count": 9,
            "timeout_no_state_change_count": 1,
        }
        expected_gate = {
            "duplicate_ledger_event_count": 0,
            "duplicate_suggestion_count": 0,
            "input_attempts_accounted": True,
            "local_projection_count": 8,
            "passed": True,
            "projection_identity_unique": True,
            "suppressed_duplicate_attempt_count": 9,
        }
        scenarios = report.get("scenarios") if isinstance(report, Mapping) else None
        controls["p02"] = (
            report.get("contract_id") == "AC-S17-P02"
            and report.get("concurrency_model") == "FROZEN_LOGICAL_LANES_DETERMINISTIC_ORDER_NOT_RUNTIME_CONCURRENCY"
            and aggregate == expected_aggregate
            and gate == expected_gate
            and isinstance(policy, Mapping)
            and policy.get("order_submission_enabled") is False
            and policy.get("recommendation_enabled") is False
            and policy.get("scheduler") == "FROZEN_LOGICAL_LANE_SCHEDULER_NOT_RUNTIME_CONCURRENCY"
            and _all_no_action(scenarios, runtime_field="real_runtime_concurrency_used")
            and _all_no_action(report.get("structured_fault_log"))
            and _artifact_boundary(report.get("claim_boundary"))
        )
        _add(checks, "S17REVIEW-IDEMPOTENCY-ZERO-DUPLICATE-GATE", controls["p02"], {"aggregate": aggregate, "idempotency_gate": gate})
    except Exception as exc:
        _add(checks, "S17REVIEW-IDEMPOTENCY-ZERO-DUPLICATE-GATE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / "chaos_scenarios.json")
        aggregate = report.get("aggregate") if isinstance(report, Mapping) else None
        gate = report.get("stale_data_gate") if isinstance(report, Mapping) else None
        policy = report.get("chaos_policy") if isinstance(report, Mapping) else None
        expected_aggregate = {
            "degraded_count": 8,
            "error_scenario_count": 8,
            "no_recommendation_no_order_count": 9,
            "rejected_stale_data_count": 8,
            "scenario_count": 9,
            "stale_data_used_count": 0,
        }
        expected_gate = {
            "auto_degraded_count": 8,
            "error_scenario_count": 8,
            "passed": True,
            "rejected_stale_data_count": 8,
            "stale_data_used_count": 0,
        }
        scenarios = report.get("scenarios") if isinstance(report, Mapping) else None
        errors = [row for row in scenarios if isinstance(row, Mapping) and row.get("fault") != "NONE"] if isinstance(scenarios, list) else []
        controls["p03"] = (
            report.get("contract_id") == "AC-S17-P03"
            and aggregate == expected_aggregate
            and gate == expected_gate
            and isinstance(policy, Mapping)
            and policy.get("injection_mode") == "FROZEN_LOGICAL_FAULT_PROJECTION_NOT_ACTUAL_SYSTEM_FAULT"
            and policy.get("order_submission_enabled") is False
            and policy.get("recommendation_enabled") is False
            and _all_no_action(scenarios)
            and len(errors) == 8
            and all(
                row.get("degraded") is True
                and row.get("stale_data_used") is False
                and row.get("stale_data_disposition") == "REJECTED_STALE_DATA"
                and row.get("real_fault_injected") is False
                for row in errors
            )
            and _artifact_boundary(report.get("claim_boundary"))
        )
        _add(checks, "S17REVIEW-CHAOS-STALE-DATA-AUTO-DEGRADE-GATE", controls["p03"], {"aggregate": aggregate, "stale_data_gate": gate})
    except Exception as exc:
        _add(checks, "S17REVIEW-CHAOS-STALE-DATA-AUTO-DEGRADE-GATE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / "recovery_report.json")
        aggregate = report.get("aggregate") if isinstance(report, Mapping) else None
        gate = report.get("recovery_gate") if isinstance(report, Mapping) else None
        policy = report.get("recovery_policy") if isinstance(report, Mapping) else None
        expected_aggregate = {
            "eligible_restore_count": 5,
            "frozen_expired_ticket_projection_count": 3,
            "recommendation_or_order_enabled_count": 0,
            "rpo_exceeded_fail_closed_count": 1,
            "rpo_within_gate_count": 5,
            "rto_exceeded_fail_closed_count": 1,
            "rto_within_gate_count": 5,
            "scenario_count": 7,
        }
        expected_gate = {
            "advice_service_recovery_seconds_max": 900,
            "eligible_max_logical_rpo_seconds": 60,
            "eligible_max_logical_rto_seconds": 900,
            "eligible_rpo_gate_passed": True,
            "eligible_rto_gate_passed": True,
            "ledger_recovery_point_seconds_max": 60,
            "over_limit_vectors_fail_closed": True,
            "passed": True,
        }
        scenarios = report.get("scenarios") if isinstance(report, Mapping) else None
        controls["p04"] = (
            report.get("contract_id") == "AC-S17-P04"
            and aggregate == expected_aggregate
            and gate == expected_gate
            and isinstance(policy, Mapping)
            and policy.get("drill_mode") == "FROZEN_LOGICAL_RECOVERY_DRILL_NOT_RUNTIME_RESTART_OR_RESTORE"
            and policy.get("order_submission_enabled") is False
            and policy.get("recommendation_enabled") is False
            and _all_no_action(scenarios, runtime_field="real_runtime_state_changed")
            and isinstance(scenarios, list)
            and len([row for row in scenarios if isinstance(row, Mapping) and row.get("restoration_eligible") is True]) == 5
            and {row.get("reason_code") for row in scenarios if isinstance(row, Mapping) and row.get("restoration_eligible") is False}
            == {"RPO_EXCEEDED_FAIL_CLOSED", "RTO_EXCEEDED_FAIL_CLOSED"}
            and _artifact_boundary(report.get("claim_boundary"))
        )
        _add(checks, "S17REVIEW-RECOVERY-RPO-RTO-FAIL-CLOSED-GATE", controls["p04"], {"aggregate": aggregate, "recovery_gate": gate})
    except Exception as exc:
        _add(checks, "S17REVIEW-RECOVERY-RPO-RTO-FAIL-CLOSED-GATE", False, "%s: %s" % (type(exc).__name__, exc))
    return controls


def _check_external_boundary(root: Path, contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    artifact_paths = ("capacity_evidence.json", "idempotency_report.json", "chaos_scenarios.json", "recovery_report.json")
    try:
        artifact_boundaries = [strict_json_load(root / path).get("claim_boundary") for path in artifact_paths]
    except Exception:
        artifact_boundaries = []
    valid = (
        isinstance(contract, Mapping)
        and contract.get("execution_policy") == EXECUTION_POLICY
        and isinstance(findings, Mapping)
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
        and all(_receipt_boundary(receipt.get("external_effect_boundary")) for receipt in receipts.values())
        and all(_artifact_boundary(boundary) for boundary in artifact_boundaries)
    )
    _add(checks, "S17REVIEW-NO-NETWORK-RUNTIME-ACCOUNT-DATABASE-ORDER-DEPLOY-OR-SOAK-BOUNDARY", valid, dict(EXTERNAL_EFFECT_BOUNDARY))
    return valid


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    try:
        cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
        if not isinstance(cases, list):
            raise Stage17ReviewError("review cases unavailable")
        result = [
            evaluate_stage_snapshot(case["snapshot"]).get("status") == case["expected"]["status"]
            and evaluate_stage_snapshot(case["snapshot"]).get("reason_codes") == case["expected"]["reason_codes"]
            for case in cases
            if isinstance(case, Mapping)
        ]
        valid = len(result) == len(SNAPSHOT_CASE_IDS) and all(result)
    except Exception as exc:
        valid = False
        result = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17REVIEW-SNAPSHOT-CASES-REPLAY", valid, result)
    return valid


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> bool:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=ORACLE_PATH.as_posix())
        imports = set()
        url_literals: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(("http:" + "//", "https:" + "//")):
                url_literals.append(node.value)
        forbidden = {"asyncio", "http", "os", "requests", "socket", "subprocess", "time", "urllib", "webbrowser"}
        call_names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        valid = not imports & forbidden and not call_names & {"Popen", "sleep", "submit_order"} and not url_literals
        detail: Any = {"imports": sorted(imports), "forbidden": sorted(imports & forbidden)}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17REVIEW-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", valid, detail)
    return valid


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> bool:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        fragments = (
            "from .stage17_review import verify_existing_stage_review_evidence as verify_existing_stage17_review_evidence",
            "from .stage17_review import write_stage_review_evidence as write_stage17_review_evidence",
            '"STAGE-REVIEW-S17": verify_existing_stage17_review_evidence,',
            '"STAGE-REVIEW-S17": write_stage17_review_evidence,',
        )
        valid = all(source.count(fragment) == 1 for fragment in fragments)
        detail: Any = CLI_PATH.as_posix()
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17REVIEW-ACCEPTANCE-CLI-WIRING-EXACT", valid, detail)
    return valid


def _junit_summary(path: Path) -> tuple[Dict[str, int], bool]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    if not suites:
        raise Stage17ReviewError("JUnit has no suite")
    summary = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    normalized = all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        _add(checks, "S17REVIEW-TARGETED-REPORTS", True, "deferred until local signing")
        return True
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        junit_ok = (
            summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and summary["failures"] == 0
            and summary["errors"] == 0
            and summary["skipped"] == 0
            and normalized
        )
    except Exception as exc:
        summary = "%s: %s" % (type(exc).__name__, exc)
        junit_ok = False
    _add(checks, "S17REVIEW-TARGETED-PYTEST-REPORT", junit_ok, summary)
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
    _add(checks, "S17REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        pack_ok = isinstance(report, Mapping) and report.get("status") == "PASS" and report.get("summary", {}).get("failed") == 0
    except Exception as exc:
        report = "%s: %s" % (type(exc).__name__, exc)
        pack_ok = False
    _add(checks, "S17REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report.get("status") if isinstance(report, Mapping) else report)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": status,
        "stage_status": "S17_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S17_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S17_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S17_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S17/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S17/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the local S17 review without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, CONTRACT_PATH, checks, "S17REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S17REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, FINDINGS_PATH, checks, "S17REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, checks)
    boundary_ok = _check_external_boundary(root, contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = _portable(contract) and _portable(fixture) and _portable(findings) and all(_portable(receipt) for receipt in receipts.values())
    _add(checks, "S17REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "absolute path found")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) and isinstance(findings.get("summary"), Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "load_gate_preserved": controls["p01"],
        "idempotency_gate_preserved": controls["p02"],
        "chaos_gate_preserved": controls["p03"],
        "recovery_gate_preserved": controls["p04"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S17REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S17_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_cli_wiring(root, checks)
    _add(checks, "S17REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
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
        "evidence_id": "EVD-S17-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S17_STAGE_REVIEW_CANDIDATE_KEEP_RUNTIME_AND_RELEASE_BLOCKED",
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
        "evidence_id": "EVD-S17-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S17_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S17_STAGE_REVIEW_REMEDIATION_REQUIRED",
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
            "uv run --frozen --python 3.12 python -m pytest -q tests/S17/stage_review_test.py --junitxml=machine/evidence/S17/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S17/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S17/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S17 --evidence machine/evidence",
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
        raise Stage17ReviewError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-S17-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S17/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    matching = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) > 1:
        raise Stage17ReviewError("S17 stage-review evidence-index row is duplicated")
    if not matching:
        raw_lines.append(json.dumps(replacement, ensure_ascii=False, sort_keys=True))
    else:
        raw_lines[matching[0]] = json.dumps(replacement, ensure_ascii=False, sort_keys=True)
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage17ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage17ReviewError("cannot write a failed S17 stage review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S17/GITHUB_STAGE_UPLOAD_READY",
    }


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-S17-STAGE-REVIEW")
    except Exception as exc:
        raise Stage17ReviewError("existing S17 stage-review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S17-STAGE-REVIEW"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("stage_status") == "S17_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("decision") == "S17_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S17/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S17_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
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
        and index.get("next") == "S17/GITHUB_STAGE_UPLOAD_READY"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise Stage17ReviewError("existing S17 stage-review evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S17/GITHUB_STAGE_UPLOAD_READY",
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
    "Stage17ReviewError",
    "evaluate_contract",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
