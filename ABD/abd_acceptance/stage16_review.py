"""Fail-closed, local-only whole-stage review oracle for ABD S16.

The S16 review is a local addendum, not a replacement for frozen Task Pack
facts.  It only replays the four signed Phase receipts and their current
control artifacts.  It never re-runs Phase suites, touches an account or
runtime, activates a model, performs a deployment, or waits in real time.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .model_challenge import verify_existing_phase_evidence as verify_p01
from .model_eval import verify_existing_phase_evidence as verify_p02
from .model_redteam import verify_existing_phase_evidence as verify_p03
from .model_release_gate import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S16"
REVIEW_ID = "ABD-S16-WHOLE-STAGE-REVIEW"
STAGE_ID = "S16"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
ADDENDUM_STATUS = "LOCAL_STAGE_REVIEW_CONTRACT_NOT_A_FROZEN_TASK_PACK_FACT"

CONTRACT_PATH = Path("machine/facts/stage16_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S16/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S16_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S16/stage_review_test.py")
ORACLE_PATH = Path("abd_acceptance/stage16_review.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S16-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S16-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S16/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S16/STAGE_REVIEW/paid_dependency_scan.txt")
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
        "requirement_id": "REQ-S16-P01",
        "contract_id": "AC-S16-P01",
        "target": "模型没有显著增量时权重归零。",
        "outputs": ["model_registry.json", "baseline_report.json", "challenger_report.json"],
        "evidence_path": "machine/evidence/EVD-S16-P01.json",
        "evidence_sha256": "9d0081fd92199eb4fb60800b81aa078d18e69219a49d5c2bcf03f7c0fcdb865c",
        "rollback_path": "machine/evidence/EVD-S16-P01_rollback.json",
        "rollback_sha256": "775a2f51de6d563fd1a610db70ccb4594c9fb5a94447192696a1b3ea6151853b",
        "decision": "S16_P01_MARKET_CHAMPION_RETAINED_CHALLENGERS_ZERO_WEIGHT_P02_REQUIRED",
        "next": "S16/P02_READY_NOT_STARTED",
        "required_checks": (
            "S16P01-NO-SIGNIFICANT-INCREMENT-ZERO-WEIGHT",
            "S16P01-FROZEN-TIME-WINDOWS-NONEMPIRICAL",
            "S16P01-ARTIFACT-EXTERNAL-BOUNDARY-EXACT",
        ),
        "verifier": verify_p01,
    },
    "P02": {
        "requirement_id": "REQ-S16-P02",
        "contract_id": "AC-S16-P02",
        "target": "所有95%置信下界门通过才晋级。",
        "outputs": ["model_eval.py", "eval_catalog.json", "eval_report.json"],
        "evidence_path": "machine/evidence/EVD-S16-P02.json",
        "evidence_sha256": "f9769b776bca121d1a048f312b107d91028550f640826023ac0d32db702aef6a",
        "rollback_path": "machine/evidence/EVD-S16-P02_rollback.json",
        "rollback_sha256": "7552faac77079c952200fad309ed2c856a0dde6107fdd77854c9cadefd19b81f",
        "decision": "S16_P02_SYNTHETIC_EVALUATION_LCB_GATES_PASS_P03_REDTEAM_REQUIRED",
        "next": "S16/P03_READY_NOT_STARTED",
        "required_checks": (
            "S16P02-ALL-SYNTHETIC-LCB-AND-CALIBRATION-GATES-PASS",
            "S16P02-NO-EMPIRICAL-ACTIVATION-OR-RETURN-CLAIM",
        ),
        "verifier": verify_p02,
    },
    "P03": {
        "requirement_id": "REQ-S16-P03",
        "contract_id": "AC-S16-P03",
        "target": "任何可绕过门的攻击为阻断缺陷。",
        "outputs": ["model_redteam.json", "cross_model_review.json"],
        "evidence_path": "machine/evidence/EVD-S16-P03.json",
        "evidence_sha256": "d86c3a811022a14afa76457051dcf575e91c330bd7171c052d7cf1b849b5739d",
        "rollback_path": "machine/evidence/EVD-S16-P03_rollback.json",
        "rollback_sha256": "4f96650d428197bd5821e163acf064bcc8afafb5f3de88780efb6a120187a50e",
        "decision": "S16_P03_REDTEAM_AND_CROSS_MODEL_REVIEW_PASS_P04_REQUIRED",
        "next": "S16/P04_READY_NOT_STARTED",
        "required_checks": (
            "S16P03-ALL-SIX-FROZEN-ATTACKS-BLOCKED",
            "S16P03-CROSS-MODEL-REVIEW-UNANIMOUS-AND-NO-PROMOTION",
            "S16P03-NO-EMPIRICAL-ACTIVATION-OR-RETURN-CLAIM",
        ),
        "verifier": verify_p03,
    },
    "P04": {
        "requirement_id": "REQ-S16-P04",
        "contract_id": "AC-S16-P04",
        "target": "软件通过不能替代模型通过，两条门独立。",
        "outputs": ["model_system_card.json", "model_release_gate.json"],
        "evidence_path": "machine/evidence/EVD-S16-P04.json",
        "evidence_sha256": "5543c7963bb6d8de97cd1e5c1872e2576fddde3dc98805fce48d763633f6ae45",
        "rollback_path": "machine/evidence/EVD-S16-P04_rollback.json",
        "rollback_sha256": "8a3e06c36d72dd43d553a6c5ec0e79d4a5a965c4fa62c28ec84d5e588e71ad5b",
        "decision": "S16_P04_DUAL_GATE_CONTROL_PASS_STAGE_REVIEW_REQUIRED_NOT_DEPLOYMENT",
        "next": "S16/STAGE_REVIEW_READY_NOT_STARTED",
        "required_checks": (
            "S16P04-SYSTEM-CARD-BOUNDARY-EXACT",
            "S16P04-SOFTWARE-AND-MODEL-GATES-INDEPENDENT",
            "S16P04-BOUNDARY-AND-ADVERSE-DELTA-FAIL-CLOSED",
        ),
        "verifier": verify_p04,
    },
}

REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "MARKET_CHAMPION_AND_ZERO_WEIGHT_CHALLENGERS_PRESERVED",
    "SYNTHETIC_EVALUATION_NOT_EMPIRICAL_AND_NO_PROMOTION_PRESERVED",
    "REDTEAM_BLOCKING_AND_CROSS_MODEL_NO_PROMOTION_PRESERVED",
    "SOFTWARE_AND_MODEL_GATES_INDEPENDENT_AND_RELEASE_BLOCKED",
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
    "S16 只验证冻结本地控制和已签名证据，不验证独立经验模型增量。",
    "S16 复审通过不构成模型激活、部署、真实市场、真实账户、TAB/Gmail、OVH、Cloudflare 或实际收益证明。",
    "A$300×1.3^n 的30%月度目标仍为 UNVERIFIED_NOT_GUARANTEED。",
]
RESOLVED_FINDINGS = [
    {
        "id": "S16-REVIEW-001",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "冻结合成评测的通过状态可能被误读为独立经验模型增量。",
        "resolution": "P02 的范围固定为合成评测，P04 模型门明确为 BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT，模型权重和激活保持为零/禁用。",
        "resolution_evidence": ["eval_report.json", "model_release_gate.json", "machine/evidence/EVD-S16-P04.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S16-REVIEW-002",
        "severity": "CRITICAL",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "软件控制通过不得代替模型通过或部署许可。",
        "resolution": "P04 发布门明确软件门与模型门互不替代；当前软件门仅为本地证据 PASS，模型门保持阻断，所有冻结案例均禁止 release。",
        "resolution_evidence": ["model_system_card.json", "model_release_gate.json", "machine/evidence/EVD-S16-P04.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
    {
        "id": "S16-REVIEW-003",
        "severity": "HIGH",
        "status": "RESOLVED_IN_STAGE_REVIEW",
        "observation": "红队攻击阻断与跨模型控制审查不能被误当作模型推理、市场验证或收益保证。",
        "resolution": "P03 仅重放六类冻结攻击且禁止 promotion；系统说明卡保留非经验、非部署与不保证收益边界。",
        "resolution_evidence": ["model_redteam.json", "cross_model_review.json", "model_system_card.json"],
        "external_state_changed": False,
        "real_time_soak_waited": False,
    },
]
SNAPSHOT_CASE_IDS = (
    "POSITIVE_EXACT_STAGE",
    "PHASE_RECEIPT_FAIL",
    "TASKPACK_TRACE_FAIL",
    "MARKET_REGISTRY_GATE_FAIL",
    "SYNTHETIC_EVAL_GATE_FAIL",
    "REDTEAM_GATE_FAIL",
    "DUAL_GATE_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "PORTABILITY_FAIL",
    "OPEN_FINDING_FAIL",
)
CONTROL_ARTIFACTS = (
    Path("model_registry.json"),
    Path("baseline_report.json"),
    Path("challenger_report.json"),
    Path("eval_catalog.json"),
    Path("eval_report.json"),
    Path("model_redteam.json"),
    Path("cross_model_review.json"),
    Path("model_system_card.json"),
    Path("model_release_gate.json"),
)


class Stage16ReviewError(ValueError):
    """Raised when the S16 local review cannot reproduce its evidence."""


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
            raise Stage16ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage16ReviewError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage16ReviewError("rows are unavailable")
    matching = [value for value in rows if isinstance(value, Mapping) and value.get(key) == identifier]
    if len(matching) != 1:
        raise Stage16ReviewError("expected exactly one %s=%s" % (key, identifier))
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
        "task_ids": ["T-S16-%s-%02d" % (phase, number) for phase in PHASE_SPECS for number in (1, 2, 3)],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay one review state as a no-action decision."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "market_registry_gate_preserved",
        "synthetic_eval_gate_preserved",
        "redteam_gate_preserved",
        "dual_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage16ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage16ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage16ReviewError("findings_open must be a nonnegative integer")
    reasons = [
        reason
        for key, reason in (
            ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
            ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
            ("market_registry_gate_preserved", "MARKET_REGISTRY_OR_ZERO_WEIGHT_GATE_RELAXED"),
            ("synthetic_eval_gate_preserved", "SYNTHETIC_EVALUATION_OR_NO_PROMOTION_GATE_RELAXED"),
            ("redteam_gate_preserved", "REDTEAM_OR_CROSS_MODEL_GATE_RELAXED"),
            ("dual_gate_preserved", "SOFTWARE_MODEL_DUAL_GATE_RELAXED"),
            ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
            ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
        )
        if snapshot[key] is not True
    ]
    if snapshot["findings_open"]:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S16_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S16_STAGE_REVIEW_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "model_activation_enabled": False,
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
        _add(checks, "S16REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "stage_review_addendum": ADDENDUM_STATUS,
        "targeted_test_command": "pytest -q tests/S16/stage_review_test.py",
        "release_status_on_pass": "S16_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S16/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S16/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S16REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S16REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S16REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S16REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S16REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S16REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S16-WHOLE-STAGE-REVIEW",
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
        "expected_next": "S16/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S16_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 3, "open": 0, "resolved": 3, "blocked": 0},
    }
    _add(checks, "S16REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S16REVIEW-SINGLE-PASS-CASES-EXACT",
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
    _add(checks, "S16REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    passed = True
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        ok = actual == expected
        _add(checks, "S16REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), ok, {"expected": expected, "actual": actual})
        passed = passed and ok
    return passed


def _task_rows(value: Any) -> Any:
    return value if isinstance(value, list) else value.get("tasks") if isinstance(value, Mapping) else None


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S16REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S16REVIEW-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S16REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S16REVIEW-TRACEABILITY-PARSE")
    try:
        tasks = _task_rows(graph)
        if not isinstance(tasks, list):
            raise Stage16ReviewError("task graph unavailable")
        valid = True
        for phase, spec in PHASE_SPECS.items():
            requirement = _row(requirements, spec["requirement_id"])
            contract = _row(contracts, spec["contract_id"])
            trace = _row(traceability, spec["requirement_id"], key="requirement_id")
            phase_tasks = [item for item in tasks if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == phase]
            task_ids = ["T-S16-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            phase_ok = (
                requirement.get("scope") == spec["outputs"]
                and requirement.get("target") == spec["target"]
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and contract.get("requirement_id") == spec["requirement_id"]
                and contract.get("pass_gate") == spec["target"]
                and [item.get("id") for item in phase_tasks] == task_ids
                and phase_tasks[0].get("outputs") == spec["outputs"]
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == task_ids
                and trace.get("evidence_id") == "EVD-S16-%s" % phase
            )
            _add(checks, "S16REVIEW-%s-TASKPACK-TRACE-EXACT" % phase, phase_ok, {"tasks": task_ids})
            valid = valid and phase_ok
    except Exception as exc:
        valid = False
        _add(checks, "S16REVIEW-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return valid


def _all_validation_checks_pass(receipt: Mapping[str, Any]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, Mapping) and row.get("passed") is True for row in rows)


def _generic_phase_boundary(boundary: Any) -> bool:
    return (
        isinstance(boundary, Mapping)
        and boundary.get("external_network_accessed") is False
        and boundary.get("real_market_or_odds_observed") is False
        and boundary.get("order_submission_enabled") is False
        and boundary.get("production_deployed_or_activated") is False
        and boundary.get("real_time_soak_waited") is False
        and boundary.get("incremental_cash_spent_aud") == "0.00"
    )


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    all_ok = True
    receipts: Dict[str, Mapping[str, Any]] = {}
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        index_rows = []
        _add(checks, "S16REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        all_ok = False
    for phase, spec in PHASE_SPECS.items():
        try:
            receipt = strict_json_load(root / spec["evidence_path"])
            rollback = strict_json_load(root / spec["rollback_path"])
            index = _row(index_rows, "INDEX-%s" % spec["contract_id"])
            verifier_result = spec["verifier"](root)
            passed_ids = {row.get("id") for row in receipt.get("validation", {}).get("checks", []) if isinstance(row, Mapping) and row.get("passed") is True}
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
                and _generic_phase_boundary(receipt.get("external_effect_boundary"))
                and set(spec["required_checks"]) <= passed_ids
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
                and verifier_result.get("status") == "PASS"
                and verifier_result.get("evidence_sha256") == spec["evidence_sha256"]
            )
            detail: Any = {"verifier": verifier_result, "receipt_sha256": sha256_file(root / spec["evidence_path"])}
            receipts[phase] = receipt
            hashes[spec["evidence_path"]] = sha256_file(root / spec["evidence_path"])
            hashes[spec["rollback_path"]] = sha256_file(root / spec["rollback_path"])
        except Exception as exc:
            valid = False
            detail = "%s: %s" % (type(exc).__name__, exc)
            receipts[phase] = {}
        _add(checks, "S16REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, valid, detail)
        all_ok = all_ok and valid
    return all_ok, receipts


def _check_stage_controls(root: Path, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> Dict[str, bool]:
    try:
        registry = strict_json_load(root / "model_registry.json")
        baseline = strict_json_load(root / "baseline_report.json")
        challenger = strict_json_load(root / "challenger_report.json")
        challengers = registry.get("challengers") if isinstance(registry, Mapping) else None
        p01_artifacts = (
            isinstance(registry, Mapping)
            and registry.get("contract_id") == "AC-S16-P01"
            and registry.get("champion", {}).get("model_id") == "MARKET_CONSENSUS_CHAMPION"
            and registry.get("champion", {}).get("active_weight") == "1.00"
            and isinstance(challengers, list)
            and len(challengers) == 6
            and all(
                isinstance(item, Mapping)
                and item.get("active_weight") == "0.00"
                and item.get("significant_increment") is False
                for item in challengers
            )
            and isinstance(baseline, Mapping)
            and baseline.get("contract_id") == "AC-S16-P01"
            and isinstance(challenger, Mapping)
            and challenger.get("contract_id") == "AC-S16-P01"
        )
    except Exception:
        p01_artifacts = False
    p01 = _all_validation_checks_pass(receipts.get("P01", {})) and p01_artifacts
    _add(checks, "S16REVIEW-MARKET-CHAMPION-AND-ZERO-WEIGHT-CHALLENGERS-GATE", p01, {"artifact_contract": p01_artifacts})

    try:
        catalog = strict_json_load(root / "eval_catalog.json")
        report = strict_json_load(root / "eval_report.json")
        promotion = report.get("model_promotion") if isinstance(report, Mapping) else None
        p02_artifacts = (
            isinstance(catalog, Mapping)
            and catalog.get("contract_id") == "AC-S16-P02"
            and isinstance(report, Mapping)
            and report.get("contract_id") == "AC-S16-P02"
            and report.get("evaluation_scope", {}).get("classification") == "FROZEN_SYNTHETIC_EVALUATION_NOT_EMPIRICAL"
            and report.get("gate_summary", {}).get("all_s16_p02_gates_pass") is True
            and isinstance(promotion, Mapping)
            and promotion.get("weight_after") == "0.00"
            and promotion.get("weight_change_allowed") is False
            and promotion.get("activation_status") == "NOT_ACTIVATED_PENDING_S16_P03_AND_S16_P04"
        )
    except Exception:
        p02_artifacts = False
    p02 = _all_validation_checks_pass(receipts.get("P02", {})) and p02_artifacts
    _add(checks, "S16REVIEW-SYNTHETIC-EVALUATION-NOT-EMPIRICAL-AND-NO-PROMOTION-GATE", p02, {"artifact_contract": p02_artifacts})

    try:
        redteam = strict_json_load(root / "model_redteam.json")
        review = strict_json_load(root / "cross_model_review.json")
        consensus = review.get("review_consensus") if isinstance(review, Mapping) else None
        p03_artifacts = (
            isinstance(redteam, Mapping)
            and redteam.get("contract_id") == "AC-S16-P03"
            and redteam.get("summary") == {
                "attack_count": 6,
                "blocked_count": 6,
                "bypass_count": 0,
                "all_attack_paths_blocked": True,
                "any_bypass_is_blocking_defect": True,
            }
            and isinstance(review, Mapping)
            and review.get("contract_id") == "AC-S16-P03"
            and isinstance(consensus, Mapping)
            and consensus.get("all_required_attacks_blocked") is True
            and consensus.get("model_promotion_allowed") is False
            and consensus.get("activation_status") == "NOT_ACTIVATED_PENDING_S16_P04"
        )
    except Exception:
        p03_artifacts = False
    p03 = _all_validation_checks_pass(receipts.get("P03", {})) and p03_artifacts
    _add(checks, "S16REVIEW-REDTEAM-BLOCKING-AND-CROSS-MODEL-NO-PROMOTION-GATE", p03, {"artifact_contract": p03_artifacts})

    try:
        card = strict_json_load(root / "model_system_card.json")
        gate = strict_json_load(root / "model_release_gate.json")
        software = gate.get("software_gate") if isinstance(gate, Mapping) else None
        model = gate.get("model_gate") if isinstance(gate, Mapping) else None
        independence = gate.get("gate_independence") if isinstance(gate, Mapping) else None
        summary = gate.get("summary") if isinstance(gate, Mapping) else None
        p04_artifacts = (
            isinstance(card, Mapping)
            and card.get("contract_id") == "AC-S16-P04"
            and card.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and isinstance(gate, Mapping)
            and gate.get("contract_id") == "AC-S16-P04"
            and isinstance(software, Mapping)
            and software.get("passed") is True
            and isinstance(model, Mapping)
            and model.get("passed") is False
            and model.get("activation_allowed") is False
            and isinstance(independence, Mapping)
            and independence.get("software_pass_can_replace_model_pass") is False
            and independence.get("model_pass_can_replace_software_pass") is False
            and isinstance(summary, Mapping)
            and summary.get("all_cases_release_blocked") is True
            and summary.get("deployment_allowed") is False
            and summary.get("model_activation_allowed") is False
        )
    except Exception:
        p04_artifacts = False
    p04 = _all_validation_checks_pass(receipts.get("P04", {})) and p04_artifacts
    _add(checks, "S16REVIEW-SOFTWARE-AND-MODEL-GATES-INDEPENDENT-AND-RELEASE-BLOCKED", p04, {"artifact_contract": p04_artifacts})
    return {"p01": p01, "p02": p02, "p03": p03, "p04": p04}


def _check_external_boundary(contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    receipt_boundaries = [receipt.get("external_effect_boundary") for receipt in receipts.values() if isinstance(receipt, Mapping)]
    receipts_ok = len(receipt_boundaries) == len(PHASE_SPECS) and all(_generic_phase_boundary(item) for item in receipt_boundaries)
    valid = (
        isinstance(contract, Mapping)
        and contract.get("execution_policy") == EXECUTION_POLICY
        and isinstance(findings, Mapping)
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
        and receipts_ok
    )
    _add(checks, "S16REVIEW-NO-NETWORK-ACCOUNT-DATABASE-ORDER-DEPLOY-OR-SOAK-BOUNDARY", valid, {"phase_receipts": receipts_ok})
    return valid


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S16REVIEW-SNAPSHOT-CASES-REPLAY", False, "cases unavailable")
        return False
    outcomes = []
    try:
        for case in cases:
            if not isinstance(case, Mapping):
                raise Stage16ReviewError("snapshot case is malformed")
            result = evaluate_stage_snapshot(case["snapshot"])
            expected = case["expected"]
            outcomes.append(
                result.get("status") == expected.get("status")
                and result.get("reason_codes") == expected.get("reason_codes")
                and result.get("model_activation_enabled") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_network_used") is False
                and result.get("real_time_soak_waited") is False
            )
        valid = all(outcomes) and len(outcomes) == len(SNAPSHOT_CASE_IDS)
    except Exception as exc:
        valid = False
        outcomes = ["%s: %s" % (type(exc).__name__, exc)]
    _add(checks, "S16REVIEW-SNAPSHOT-CASES-REPLAY", valid, outcomes)
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
        forbidden = {"asyncio", "http", "os", "requests", "socket", "subprocess", "time", "urllib", "webbrowser"}
        call_names = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        valid = not imported & forbidden and not call_names & {"Popen", "sleep", "submit_order"}
        detail: Any = {"imports": sorted(imported), "forbidden": sorted(imported & forbidden)}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S16REVIEW-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", valid, detail)
    return valid


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> bool:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        valid = (
            '"STAGE-REVIEW-S16": write_stage16_review_evidence' in source
            and '"STAGE-REVIEW-S16": verify_existing_stage16_review_evidence' in source
        )
        detail: Any = CLI_PATH.as_posix()
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S16REVIEW-ACCEPTANCE-CLI-WIRING-EXACT", valid, detail)
    return valid


def _junit_summary(path: Path) -> tuple[Dict[str, int], bool]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    if not suites:
        raise Stage16ReviewError("JUnit has no suite")
    summary = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    normalized = all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        _add(checks, "S16REVIEW-TARGETED-REPORTS", True, "deferred until local signing")
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
    _add(checks, "S16REVIEW-TARGETED-PYTEST-REPORT", junit_ok, summary)
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
    _add(checks, "S16REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        pack_ok = isinstance(report, Mapping) and report.get("status") == "PASS"
    except Exception as exc:
        report = "%s: %s" % (type(exc).__name__, exc)
        pack_ok = False
    _add(checks, "S16REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report.get("status") if isinstance(report, Mapping) else report)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": status,
        "stage_status": "S16_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S16_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S16_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S16_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S16/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S16/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the local S16 review without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, CONTRACT_PATH, checks, "S16REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S16REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, FINDINGS_PATH, checks, "S16REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, receipts, checks)
    boundary_ok = _check_external_boundary(contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = all(_portable(value) for value in (contract, fixture, findings, *receipts.values()))
    _add(checks, "S16REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "absolute path detected")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "market_registry_gate_preserved": controls["p01"],
        "synthetic_eval_gate_preserved": controls["p02"],
        "redteam_gate_preserved": controls["p03"],
        "dual_gate_preserved": controls["p04"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S16REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S16_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_cli_wiring(root, checks)
    _add(checks, "S16REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
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
        "evidence_id": "EVD-S16-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S16_STAGE_REVIEW_CANDIDATE_KEEP_MODEL_AND_RELEASE_BLOCKED",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "model_activation_enabled": False,
        "model_promotion_allowed": False,
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
        "evidence_id": "EVD-S16-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S16_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S16_STAGE_REVIEW_REMEDIATION_REQUIRED",
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
            "uv run --frozen --python 3.12 python -m pytest -q tests/S16/stage_review_test.py --junitxml=machine/evidence/S16/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S16/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S16/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S16 --evidence machine/evidence",
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
        raise Stage16ReviewError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-S16-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S16/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    matching = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) > 1:
        raise Stage16ReviewError("S16 stage-review evidence-index row is duplicated")
    if not matching:
        raw_lines.append(json.dumps(replacement, ensure_ascii=False, sort_keys=True))
    else:
        raw_lines[matching[0]] = json.dumps(replacement, ensure_ascii=False, sort_keys=True)
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage16ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage16ReviewError("cannot write a failed S16 stage review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S16/GITHUB_STAGE_UPLOAD_READY",
    }


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-S16-STAGE-REVIEW")
    except Exception as exc:
        raise Stage16ReviewError("existing S16 stage-review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S16-STAGE-REVIEW"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("stage_status") == "S16_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("decision") == "S16_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S16/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S16_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("model_activation_enabled") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and index.get("kind") == "STAGE_REVIEW_EVIDENCE"
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S16/GITHUB_STAGE_UPLOAD_READY"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise Stage16ReviewError("existing S16 stage-review evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S16/GITHUB_STAGE_UPLOAD_READY",
    }


__all__ = [
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINDINGS_PATH",
    "FIXTURE_PATH",
    "Stage16ReviewError",
    "evaluate_contract",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
