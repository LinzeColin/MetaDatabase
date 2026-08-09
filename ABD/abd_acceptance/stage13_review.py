"""Fail-closed, offline whole-stage review for ABD S13.

The frozen Task Pack defines S13/P01--P04 but not a stage-review node.  This
local addendum reviews the four already-signed receipts without changing their
baseline.  It deliberately performs no network activity, account operation,
order action, deployment, GitHub upload, full regression, or real-time wait.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .chinese_workbench import verify_existing_phase_evidence as verify_p01
from .journey_paths import verify_existing_phase_evidence as verify_p04
from .platform_quote_check import verify_existing_phase_evidence as verify_p02
from .post_advice_settlement import verify_existing_phase_evidence as verify_p03


CONTRACT_ID = "STAGE-REVIEW-S13"
REVIEW_ID = "ABD-S13-WHOLE-STAGE-REVIEW"
STAGE_ID = "S13"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage13_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S13/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S13_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S13/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S13/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S13/STAGE_REVIEW/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S13-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S13-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
ORACLE_PATH = Path("abd_acceptance/stage13_review.py")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")

PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    "P01": {
        "requirement_id": "REQ-S13-P01",
        "contract_id": "AC-S13-P01",
        "target": "手机/电脑任意地点可访问，界面中文。",
        "outputs": ["webapp", "push_service.py", "ui_fixtures.json"],
        "evidence_path": "machine/evidence/EVD-S13-P01.json",
        "evidence_sha256": "161a75ad86f1f0f745eae393b27b3a7f7a07c034d4342381f88b95892ad0199d",
        "rollback_path": "machine/evidence/EVD-S13-P01_rollback.json",
        "rollback_sha256": "504ef71bbaba64179ba54b7e8a6be64b9aecca64c2e9db0db27fd65569c175c1",
        "decision": "CHINESE_WORKBENCH_AND_LOCAL_PUSH_CONTRACT_READY_PLATFORM_VALIDATION_AND_POST_ADVICE_EVIDENCE_REQUIRED",
        "next": "S13/P02_READY_NOT_STARTED",
        "release_status": "S13_P01_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED",
        "boundary": {
            "external_network_accessed": False,
            "external_push_sent": False,
            "financial_return_verified_or_guaranteed": False,
            "incremental_cash_spent_aud": "0.00",
            "order_submission_enabled": False,
            "production_deployed_or_activated": False,
            "real_account_accessed": False,
            "real_time_soak_waited": False,
        },
        "control_ids": [
            "S13P01-ALL-VISIBLE-FIXTURE-TEXT-PASSES-CHINESE-GATE",
            "S13P01-STATIC-CHINESE-WORKBENCH-SEMANTICS",
            "S13P01-LOCAL-PUSH-PAYLOAD-ONLY-NO-EXTERNAL-DELIVERY",
            "S13P01-STATIC-NO-NETWORK-SOAK-ORDER-OR-EXTERNAL-PUSH",
        ],
    },
    "P02": {
        "requirement_id": "REQ-S13-P02",
        "contract_id": "AC-S13-P02",
        "target": "低于最低赔率、身份不符或过期立即红色撤销。",
        "outputs": ["browser_companion", "quote_check.py", "match_fixtures.json"],
        "evidence_path": "machine/evidence/EVD-S13-P02.json",
        "evidence_sha256": "42be48209052f1056d16dd002322ca710cafbe1023be7c9a20a16d158abbbe89",
        "rollback_path": "machine/evidence/EVD-S13-P02_rollback.json",
        "rollback_sha256": "37216196b19640aba63181e9a5211c5ec31048e33495f4b8da11d5f1391fd236",
        "decision": "BROWSER_COMPANION_AND_LOCAL_VISIBLE_QUOTE_CHECK_READY_POST_ADVICE_EVIDENCE_REQUIRED",
        "next": "S13/P03_READY_NOT_STARTED",
        "release_status": "S13_P02_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED",
        "boundary": {
            "actual_market_or_odds_observed": False,
            "automatic_platform_open_performed": False,
            "browser_extension_installed_or_executed": False,
            "external_network_accessed": False,
            "financial_return_verified_or_guaranteed": False,
            "incremental_cash_spent_aud": "0.00",
            "order_submission_enabled": False,
            "production_deployed_or_activated": False,
            "real_account_accessed": False,
            "real_time_soak_waited": False,
        },
        "control_ids": [
            "S13P02-ONE_IN_TEN_THOUSAND_BOUNDARY-REVOKES",
            "S13P02-COPY-INSTRUCTION-ONLY-NO-AUTO-OPEN",
            "S13P02-BROWSER-COMPANION-LEAST-PRIVILEGE",
            "S13P02-BROWSER-COMPANION-NO-NETWORK-CLICK-OR-ORDER",
        ],
    },
    "P03": {
        "requirement_id": "REQ-S13-P03",
        "contract_id": "AC-S13-P03",
        "target": "没有确认时不伪造真实收益。",
        "outputs": ["post_advice_worker.py", "result_settler.py", "performance_report.py"],
        "evidence_path": "machine/evidence/EVD-S13-P03.json",
        "evidence_sha256": "7ebe8b2b59bce33b34e1c7bab01bf96a7d2225414725bddebada481443fc197a",
        "rollback_path": "machine/evidence/EVD-S13-P03_rollback.json",
        "rollback_sha256": "38da833ecfc4199cc842f6725f77b9d4c740f117734e546f8b31f9de37b7b9a6",
        "decision": "POST_ADVICE_EVIDENCE_AND_SYNTHETIC_SETTLEMENT_READY_REAL_RETURN_REQUIRES_SEPARATE_EVIDENCE",
        "next": "S13/P04_READY_NOT_STARTED",
        "release_status": "S13_P03_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED",
        "boundary": {
            "actual_market_or_odds_observed": False,
            "actual_order_execution_claimed": False,
            "external_network_accessed": False,
            "financial_return_verified_or_guaranteed": False,
            "incremental_cash_spent_aud": "0.00",
            "order_submission_enabled": False,
            "production_deployed_or_activated": False,
            "real_account_accessed": False,
            "real_time_soak_waited": False,
            "system_order_confirmation_enabled": False,
        },
        "control_ids": [
            "S13P03-REPORT-DOES-NOT-CLAIM-ACTUAL-RETURN",
            "S13P03-POINT-0001-ADVERSE-ODDS-BOUNDARY-DOES-NOT-CREATE-ACTUAL-CLAIM",
            "S13P03-NO-CONFIRMATION-NEVER-CLAIMS-ACTUAL-RETURN",
            "S13P03-STATIC-NO-NETWORK-SOAK-OR-ORDER",
        ],
    },
    "P04": {
        "requirement_id": "REQ-S13-P04",
        "contract_id": "AC-S13-P04",
        "target": "每类路径有输入、状态、输出、证据和恢复。",
        "outputs": ["journey_tests.json", "recovery_actions.json"],
        "evidence_path": "machine/evidence/EVD-S13-P04.json",
        "evidence_sha256": "1c4d9febd44b30dddfa780daa0aad56a70ab8d477ab9cdafc905107760d7c81e",
        "rollback_path": "machine/evidence/EVD-S13-P04_rollback.json",
        "rollback_sha256": "8cea40846c7d60b5ee8adaecee741e97be17a46e6045728e71cfb08131dc0856",
        "decision": "SIX_COMPLETE_SYNTHETIC_JOURNEYS_AND_LOCAL_RECOVERY_READY_STAGE_REVIEW_REQUIRED",
        "next": "S13/STAGE_REVIEW_READY_NOT_STARTED",
        "release_status": "S13_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED",
        "boundary": {
            "actual_market_or_odds_observed": False,
            "actual_order_execution_claimed": False,
            "external_network_accessed": False,
            "financial_return_verified_or_guaranteed": False,
            "incremental_cash_spent_aud": "0.00",
            "order_submission_enabled": False,
            "production_deployed_or_activated": False,
            "real_account_accessed": False,
            "real_time_soak_waited": False,
            "system_order_confirmation_enabled": False,
        },
        "control_ids": [
            "S13P04-SIX-PATHS-INPUT-STATE-OUTPUT-EVIDENCE-RECOVERY-EXACT",
            "S13P04-POINT-0001-ADVERSE-ODDS-REVOKES-WITHOUT-ACTUAL-CLAIM",
            "S13P04-ALL-RECOVERIES-PRESERVE-EVIDENCE-AND-LOCAL-ONLY",
            "S13P04-STATIC-NO-NETWORK-SOAK-OR-ORDER",
        ],
    },
}

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

REQUIRED_GATES = [
    "PHASE_RECEIPTS_CURRENT_AND_PORTABLE",
    "REQUIREMENT_ACCEPTANCE_TASK_TRACE_CLOSED",
    "CHINESE_WORKBENCH_ACTIONS_DISABLED_AND_LOCAL_PUSH_ONLY_GATE_PRESERVED",
    "VISIBLE_QUOTE_IDENTITY_MINIMUM_ODDS_EXPIRY_AND_RISK_REVOKE_GATE_PRESERVED",
    "POST_ADVICE_SYNTHETIC_SETTLEMENT_NOT_ACTUAL_RETURN_GATE_PRESERVED",
    "SIX_COMPLETE_PATHS_AND_LOCAL_RECOVERY_GATE_PRESERVED",
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
        "id": "S13-LOCAL-EVIDENCE-BOUNDARY",
        "status": "UNVERIFIED_OUT_OF_SCOPE",
        "statement": "S13 复审只证明冻结合成制品与本地证据链；不证明真实浏览器、移动设备、市场、账户、TAB/Gmail、OVH、Cloudflare、部署、上线、订单或实际收益。",
    }
]
CONTROL_ARTIFACTS = (
    Path("webapp/index.html"),
    Path("push_service.py"),
    Path("browser_companion/manifest.json"),
    Path("browser_companion/background.js"),
    Path("machine/tests/fixtures/S13_P03.json"),
    Path("journey_tests.json"),
    Path("recovery_actions.json"),
)
ROLLBACK_ARTIFACTS = (
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
    *tuple(Path(spec["evidence_path"]) for spec in PHASE_SPECS.values()),
    *tuple(Path(spec["rollback_path"]) for spec in PHASE_SPECS.values()),
)
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")
_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}


class Stage13ReviewError(ValueError):
    """Raised when S13 whole-stage review evidence is malformed or stale."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise Stage13ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage13ReviewError("JSONL row %d is not an object" % number)
        rows.append(value)
    if not rows:
        raise Stage13ReviewError("JSONL is empty")
    return rows


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative)
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage13ReviewError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage13ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


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
            or "/" + "Users/" in normalized
            or "/" + "home/" in normalized
            or re.match(r"^[A-Za-z]:/", normalized) is not None
        )
    return True


def _parse_sums(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise Stage13ReviewError("invalid SHA256SUMS line %d" % number)
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in parsed:
            raise Stage13ReviewError("unsafe or duplicate checksum path")
        parsed[relative] = digest
    if not parsed:
        raise Stage13ReviewError("SHA256SUMS is empty")
    return parsed


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise Stage13ReviewError("JUnit contains no suites")
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for field in result:
            result[field] += int(suite.attrib.get(field, "0"))
    return result


def _junit_is_normalized(path: Path) -> bool:
    try:
        document = ElementTree.parse(path).getroot()
    except Exception:
        return False
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    return bool(suites) and all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK for suite in suites)


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
        "task_ids": ["T-S13-%s-%02d" % (phase, number) for phase in PHASE_SPECS for number in (1, 2, 3)],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one immutable S13 review snapshot without enabling action."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "chinese_workbench_gate_preserved",
        "visible_quote_gate_preserved",
        "post_advice_gate_preserved",
        "six_paths_recovery_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage13ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage13ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage13ReviewError("findings_open must be a nonnegative integer")
    reason_map = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("chinese_workbench_gate_preserved", "CHINESE_WORKBENCH_OR_LOCAL_PUSH_GATE_RELAXED"),
        ("visible_quote_gate_preserved", "VISIBLE_QUOTE_REVOKE_GATE_RELAXED"),
        ("post_advice_gate_preserved", "POST_ADVICE_OR_SYNTHETIC_RETURN_BOUNDARY_RELAXED"),
        ("six_paths_recovery_gate_preserved", "SIX_PATH_OR_RECOVERY_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S13_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S13_STAGE_REVIEW_REJECTED_NO_ACTION",
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
        _add(checks, "S13REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "targeted_test_command": "pytest -q tests/S13/stage_review_test.py",
        "release_status_on_pass": "S13_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S13/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S13/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S13REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S13REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S13REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S13REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    _add(checks, "S13REVIEW-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    _add(checks, "S13REVIEW-NO-FULL-REGRESSION-POLICY", contract.get("execution_policy") == EXECUTION_POLICY, contract.get("execution_policy"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S13-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": 9,
        "minimum_targeted_pytest_cases": 24,
        "expected_phase_ids": list(PHASE_SPECS),
        "expected_phase_evidence_sha256": {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_phase_rollback_sha256": {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        "expected_next": "S13/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S13_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "expected_findings_summary": {"total": 0, "open": 0, "resolved": 0, "blocked": 0},
    }
    _add(checks, "S13REVIEW-FIXTURE-IDENTITY", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    cases = fixture.get("cases")
    _add(
        checks,
        "S13REVIEW-SINGLE-PASS-CASES-EXACT",
        isinstance(cases, list)
        and len(cases) == fixture.get("single_pass_case_count")
        and len({case.get("case_id") for case in cases if isinstance(case, Mapping)}) == len(cases),
        [case.get("case_id") for case in cases] if isinstance(cases, list) else cases,
    )
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_clock") == FIXED_CLOCK
        and findings.get("findings") == []
        and findings.get("summary") == fixture_identity["expected_findings_summary"]
        and findings.get("explicit_limitations") == EXPLICIT_LIMITATIONS
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
    )
    _add(checks, "S13REVIEW-FINDINGS-AND-LIMITATIONS-EXACT", findings_ok, findings.get("summary"))


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
        _add(checks, "S13REVIEW-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), item_ok, {"expected": expected, "actual": actual})
        passed = passed and item_ok
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, root / REQUIREMENTS_PATH, checks, "S13REVIEW-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, root / CONTRACTS_PATH, checks, "S13REVIEW-CONTRACTS-PARSE")
    graph_document = _safe_load(root, root / TASK_GRAPH_PATH, checks, "S13REVIEW-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, root / TRACEABILITY_PATH, checks, "S13REVIEW-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S13REVIEW-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S13REVIEW-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        index = []
    tasks = graph_document.get("tasks") if isinstance(graph_document, Mapping) else None
    if not all(isinstance(value, list) for value in (requirements, contracts, tasks, traceability, index)):
        _add(checks, "S13REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-CLOSED", False, "task-pack collections are unavailable")
        return False
    phase_results: Dict[str, bool] = {}
    common_non_goals = [
        "不自动提交、确认或重试真实订单",
        "不以降低证据或风险门追赶30%月目标",
        "不引入付费数据或付费程序接口依赖",
    ]
    for phase, spec in PHASE_SPECS.items():
        try:
            requirement = _row(requirements, spec["requirement_id"])
            contract = _row(contracts, spec["contract_id"])
            trace = _row(traceability, spec["requirement_id"], key="requirement_id")
            phase_tasks = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == phase]
            index_row = _row(index, "INDEX-%s" % spec["contract_id"])
            task_ids = ["T-S13-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            expected_test_ids = ["TEST-S13-%s" % phase, "TEST-S13-%s-BOUNDARY" % phase, "TEST-S13-%s-REPLAY" % phase]
            exact = (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("scope") == spec["outputs"]
                and requirement.get("target") == spec["target"]
                and requirement.get("non_goals") == common_non_goals
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and contract.get("requirement_id") == spec["requirement_id"]
                and contract.get("pass_gate") == spec["target"]
                and contract.get("threshold") == spec["target"]
                and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % spec["contract_id"]
                and [item.get("id") for item in contract.get("tests", [])] == expected_test_ids
                and [item.get("id") for item in phase_tasks] == task_ids
                and all(item.get("requirement_ids") == [spec["requirement_id"]] and item.get("acceptance_criteria_ids") == [spec["contract_id"]] for item in phase_tasks)
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == task_ids
                and trace.get("test_ids") == expected_test_ids
                and trace.get("evidence_id") == "EVD-S13-%s" % phase
                and index_row.get("id") == "INDEX-%s" % spec["contract_id"]
                and index_row.get("status") == "PASS"
                and index_row.get("actual_artifact") == spec["evidence_path"]
                and index_row.get("artifact_sha256") == spec["evidence_sha256"]
            )
        except Exception as exc:
            exact = False
            trace = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S13REVIEW-%s-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT" % phase, exact, trace)
        phase_results[phase] = exact
    result = all(phase_results.values())
    _add(checks, "S13REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-CLOSED", result, phase_results)
    return result


def _validation_ids_pass(receipt: Mapping[str, Any], required: Sequence[str]) -> bool:
    validation = receipt.get("validation")
    rows = validation.get("checks") if isinstance(validation, Mapping) else None
    if not isinstance(rows, list):
        return False
    by_id = {row.get("id"): row.get("passed") for row in rows if isinstance(row, Mapping)}
    return all(by_id.get(identifier) is True for identifier in required)


def _check_phase_receipts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> tuple[bool, Dict[str, Mapping[str, Any]]]:
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception:
        index = []
    documents: Dict[str, Mapping[str, Any]] = {}
    phase_ok: Dict[str, bool] = {}
    for phase, spec in PHASE_SPECS.items():
        receipt_path = root / spec["evidence_path"]
        rollback_path = root / spec["rollback_path"]
        receipt = _safe_load(root, receipt_path, checks, "S13REVIEW-%s-EVIDENCE-STRICT-JSON" % phase)
        rollback = _safe_load(root, rollback_path, checks, "S13REVIEW-%s-ROLLBACK-STRICT-JSON" % phase)
        try:
            verifier = PHASE_VERIFIERS[phase](root)
            expected_verifier = {
                "contract_id": spec["contract_id"],
                "status": "PASS",
                "evidence_path": spec["evidence_path"],
                "evidence_sha256": spec["evidence_sha256"],
                "next": spec["next"],
            }
            verifier_ok = verifier == expected_verifier
        except Exception as exc:
            verifier = "%s: %s" % (type(exc).__name__, exc)
            verifier_ok = False
        _add(checks, "S13REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, verifier_ok, verifier)
        try:
            index_row = _row(index, "INDEX-%s" % spec["contract_id"])
            evidence_ok = (
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
                and receipt.get("external_effect_boundary") == spec["boundary"]
                and receipt.get("validation", {}).get("summary", {}).get("failed") == 0
                and receipt.get("validation", {}).get("summary", {}).get("passed") == receipt.get("validation", {}).get("summary", {}).get("checks")
                and sha256_file(receipt_path) == spec["evidence_sha256"]
                and sha256_file(rollback_path) == spec["rollback_sha256"]
                and index_row.get("kind") == "PHASE_EVIDENCE"
                and index_row.get("stage_id") == STAGE_ID
                and index_row.get("contract_id") == spec["contract_id"]
                and index_row.get("status") == "PASS"
                and index_row.get("actual_artifact") == spec["evidence_path"]
                and index_row.get("artifact_sha256") == spec["evidence_sha256"]
                and index_row.get("next") == spec["next"]
            )
            rollback_ok = (
                isinstance(rollback, Mapping)
                and rollback.get("contract_id") == spec["contract_id"]
                and rollback.get("status") == "PASS"
                and rollback.get("external_state_changed") is False
                and rollback.get("production_state_changed") is False
                and rollback.get("order_submission_enabled") is False
                and rollback.get("real_time_soak_waited") is False
                and rollback.get("incremental_cash_spent_aud") == "0.00"
            )
            portable = _portable(receipt) and _portable(rollback)
        except Exception as exc:
            evidence_ok = rollback_ok = portable = False
            index_row = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S13REVIEW-%s-EVIDENCE-INDEX-BOUNDARY-EXACT" % phase, evidence_ok, index_row)
        _add(checks, "S13REVIEW-%s-ROLLBACK-LOCAL-ONLY" % phase, rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else rollback)
        _add(checks, "S13REVIEW-%s-EVIDENCE-PORTABLE" % phase, portable, spec["evidence_path"])
        phase_ok[phase] = verifier_ok and evidence_ok and rollback_ok and portable
        if isinstance(receipt, Mapping):
            documents[phase] = receipt
        if receipt_path.is_file():
            hashes[spec["evidence_path"]] = sha256_file(receipt_path)
        if rollback_path.is_file():
            hashes[spec["rollback_path"]] = sha256_file(rollback_path)
    result = all(phase_ok.values()) and len(documents) == len(PHASE_SPECS)
    _add(checks, "S13REVIEW-PHASE-RECEIPTS-CURRENT-AND-PORTABLE", result, phase_ok)
    return result, documents


def _check_stage_controls(root: Path, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> Dict[str, bool]:
    control_rows = {phase: _validation_ids_pass(receipts.get(phase, {}), spec["control_ids"]) for phase, spec in PHASE_SPECS.items()}
    p01_page = (root / "webapp/index.html").read_text(encoding="utf-8") if (root / "webapp/index.html").is_file() else ""
    p01_push = (root / "push_service.py").read_text(encoding="utf-8") if (root / "push_service.py").is_file() else ""
    p01_artifacts = (
        '<html lang="zh-CN">' in p01_page
        and "不连接真实账户" in p01_page
        and "不提交订单" in p01_page
        and "def build_push_payload" in p01_push
        and "build_local_push_payload" in p01_push
    )
    p01 = control_rows["P01"] and p01_artifacts
    _add(checks, "S13REVIEW-CHINESE-WORKBENCH-AND-LOCAL-PUSH-GATE", p01, {"receipt_controls": control_rows["P01"], "artifact_contract": p01_artifacts})

    try:
        extension = strict_json_load(root / "browser_companion/manifest.json")
        background = (root / "browser_companion/background.js").read_text(encoding="utf-8")
        p02_artifacts = (
            isinstance(extension, Mapping)
            and extension.get("manifest_version") == 3
            and extension.get("permissions") == ["activeTab", "scripting"]
            and extension.get("host_permissions") is None
            and "COPY_INSTRUCTION_ONLY_NO_AUTO_OPEN" in background
            and "OWNER_FINAL_ORDER_MANUAL_ONLY" in background
            and "tabs.create" not in background
            and "order_submission_enabled: false" in background
        )
    except Exception:
        p02_artifacts = False
    p02 = control_rows["P02"] and p02_artifacts
    _add(checks, "S13REVIEW-VISIBLE-QUOTE-REVOKE-AND-OWNER-ONLY-GATE", p02, {"receipt_controls": control_rows["P02"], "artifact_contract": p02_artifacts})

    try:
        post_fixture = strict_json_load(root / "machine/tests/fixtures/S13_P03.json")
        cases = post_fixture.get("cases") if isinstance(post_fixture, Mapping) else None
        unconfirmed = next((case for case in cases if isinstance(case, Mapping) and case.get("case_id") == "A01-UNCONFIRMED-ADVICE-ONLY"), None) if isinstance(cases, list) else None
        synthetic = isinstance(cases, list) and all(
            isinstance(case, Mapping)
            and isinstance(case.get("advice"), Mapping)
            and case["advice"].get("synthetic_test_only") is True
            and (case.get("confirmation") is None or isinstance(case.get("confirmation"), Mapping) and case["confirmation"].get("synthetic_test_only") is True)
            and (case.get("settlement") is None or isinstance(case.get("settlement"), Mapping) and case["settlement"].get("synthetic_test_only") is True)
            for case in cases
        )
        p03_artifacts = (
            isinstance(unconfirmed, Mapping)
            and unconfirmed.get("expected", {}).get("result_status") == "UNCONFIRMED_DO_NOT_SETTLE_OR_CLAIM_ACTUAL_RETURN"
            and synthetic
            and post_fixture.get("expected_case_count") == 5
        )
    except Exception:
        p03_artifacts = False
    p03 = control_rows["P03"] and p03_artifacts
    _add(checks, "S13REVIEW-POST-ADVICE-SYNTHETIC-NO-ACTUAL-RETURN-GATE", p03, {"receipt_controls": control_rows["P03"], "artifact_contract": p03_artifacts})

    try:
        journeys = strict_json_load(root / "journey_tests.json")
        recovery = strict_json_load(root / "recovery_actions.json")
        journey_rows = journeys.get("journeys") if isinstance(journeys, Mapping) else None
        recovery_rows = recovery.get("actions") if isinstance(recovery, Mapping) else None
        expected_types = ["WALKING_SKELETON", "GOLDEN", "BLACK", "ABUSE", "DEGRADED", "RECOVERY"]
        complete = isinstance(journey_rows, list) and [row.get("journey_type") for row in journey_rows if isinstance(row, Mapping)] == expected_types and all(
            isinstance(row, Mapping)
            and isinstance(row.get("input"), Mapping)
            and isinstance(row.get("state_transitions"), list)
            and bool(row.get("state_transitions"))
            and isinstance(row.get("output"), Mapping)
            and isinstance(row.get("evidence_refs"), list)
            and bool(row.get("evidence_refs"))
            and isinstance(row.get("user_action_zh"), str)
            and bool(row.get("user_action_zh"))
            and isinstance(row.get("recovery_action_id"), str)
            and row.get("synthetic_test_only") is True
            and row["output"].get("automatic_order_submitted") is False
            and row["output"].get("actual_return_claimed") is False
            and row["output"].get("external_state_changed") is False
            for row in journey_rows
        )
        black = next((row for row in journey_rows if isinstance(row, Mapping) and row.get("journey_type") == "BLACK"), None) if isinstance(journey_rows, list) else None
        adverse = (
            isinstance(black, Mapping)
            and black.get("input", {}).get("visible_odds") == "2.199900"
            and black.get("input", {}).get("minimum_odds") == "2.200000"
            and black.get("output", {}).get("terminal_status") == "RED_REVOKE_DO_NOT_ORDER"
        )
        action_ids = {row.get("action_id") for row in recovery_rows if isinstance(row, Mapping)} if isinstance(recovery_rows, list) else set()
        recovery_ok = isinstance(recovery_rows, list) and len(recovery_rows) == 6 and all(
            isinstance(row, Mapping)
            and row.get("evidence_preserved") is True
            and row.get("external_state_changed") is False
            and row.get("production_state_changed") is False
            and row.get("actual_return_claimed") is False
            and row.get("order_submission_enabled") is False
            and row.get("synthetic_test_only") is True
            for row in recovery_rows
        ) and isinstance(journey_rows, list) and all(row.get("recovery_action_id") in action_ids for row in journey_rows if isinstance(row, Mapping))
        p04_artifacts = complete and adverse and recovery_ok and journeys.get("claim_boundary") == PHASE_SPECS["P04"]["boundary"] and recovery.get("claim_boundary") == PHASE_SPECS["P04"]["boundary"]
    except Exception:
        p04_artifacts = False
    p04 = control_rows["P04"] and p04_artifacts
    _add(checks, "S13REVIEW-SIX-COMPLETE-PATHS-AND-LOCAL-RECOVERY-GATE", p04, {"receipt_controls": control_rows["P04"], "artifact_contract": p04_artifacts})
    return {"p01": p01, "p02": p02, "p03": p03, "p04": p04}


def _check_external_boundary(contract: Any, findings: Any, receipts: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> bool:
    phase_boundaries = all(receipts.get(phase, {}).get("external_effect_boundary") == spec["boundary"] for phase, spec in PHASE_SPECS.items())
    exact = (
        isinstance(contract, Mapping)
        and contract.get("execution_policy") == EXECUTION_POLICY
        and isinstance(findings, Mapping)
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
        and phase_boundaries
    )
    _add(checks, "S13REVIEW-NO-NETWORK-ACCOUNT-ORDER-DEPLOY-OR-SOAK-BOUNDARY", exact, {"phase_boundaries": phase_boundaries})
    return exact


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S13REVIEW-SNAPSHOT-CASES", False, "cases unavailable")
        return False
    result = True
    for case in cases:
        try:
            actual = evaluate_stage_snapshot(case["snapshot"])
            expected = case["expected"]
            passed = actual["status"] == expected["status"] and actual["reason_codes"] == expected["reason_codes"]
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            passed = False
        identifier = case.get("case_id") if isinstance(case, Mapping) else "MALFORMED"
        _add(checks, "S13REVIEW-CASE-%s" % identifier, passed, actual)
        result = result and passed
    return result


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
        prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtp" + "lib", "asyncio", "time", "random", "os"}
        prohibited_literals = {"sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "web" + "hook", "smtp" + "lib"}
        denied = sorted(imports.intersection(prohibited_imports))
        tokens = sorted(token for token in prohibited_literals if token in source)
        passed = not denied and not tokens
        detail: Any = {"imports": sorted(imports), "denied": denied, "tokens": tokens}
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S13REVIEW-STATIC-NO-NETWORK-PROCESS-SOAK-OR-ORDER-CAPABILITY", passed, detail)
    return passed


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        junit_ok = (
            summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and summary["failures"] == 0
            and summary["errors"] == 0
            and summary["skipped"] == 0
            and _junit_is_normalized(root / JUNIT_PATH)
        )
    except Exception as exc:
        summary = "%s: %s" % (type(exc).__name__, exc)
        junit_ok = False
    _add(checks, "S13REVIEW-TARGETED-PYTEST-REPORT", junit_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(
            line in scan
            for line in (
                "STATUS: PASS",
                "MAX_INCREMENTAL_CASH_AUD: 0.00",
                "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
                "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
                "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
            )
        )
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S13REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary") if isinstance(report, Mapping) else None
        pack_ok = (
            isinstance(report, Mapping)
            and report.get("status") == "PASS"
            and isinstance(summary, Mapping)
            and summary.get("failed") == 0
            and type(summary.get("checks")) is int
            and summary.get("passed") == summary.get("checks")
        )
    except Exception as exc:
        pack_ok = False
        report = "%s: %s" % (type(exc).__name__, exc)
        summary = None
    _add(checks, "S13REVIEW-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, summary if isinstance(summary, Mapping) else report)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "status": "PASS" if passed else "FAIL",
        "stage_status": "S13_WHOLE_STAGE_REVIEW_PASS" if passed else "S13_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S13_WHOLE_STAGE_REVIEW_PASS" if passed else "S13_WHOLE_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "next": "S13/GITHUB_STAGE_UPLOAD_READY" if passed else "S13/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the current local S13 review state with fail-closed checks."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, root / CONTRACT_PATH, checks, "S13REVIEW-CONTRACT-PARSE")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S13REVIEW-FIXTURE-PARSE")
    findings = _safe_load(root, root / FINDINGS_PATH, checks, "S13REVIEW-FINDINGS-PARSE")
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, checks, hashes)
    trace_ok = _check_taskpack(root, checks)
    receipts_ok, receipts = _check_phase_receipts(root, checks, hashes)
    controls = _check_stage_controls(root, receipts, checks)
    boundary_ok = _check_external_boundary(contract, findings, receipts, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    portable = all(_portable(value) for value in (contract, fixture, findings, *receipts.values()))
    _add(checks, "S13REVIEW-REVIEW-EVIDENCE-PORTABLE", portable, "portable" if portable else "local path detected")
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings, Mapping) else 1
    snapshot = {
        "phase_receipts_current": receipts_ok,
        "taskpack_trace_closed": trace_ok,
        "chinese_workbench_gate_preserved": controls["p01"],
        "visible_quote_gate_preserved": controls["p02"],
        "post_advice_gate_preserved": controls["p03"],
        "six_paths_recovery_gate_preserved": controls["p04"],
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable,
        "findings_open": findings_open if type(findings_open) is int and findings_open >= 0 else 1,
    }
    snapshot_result = evaluate_stage_snapshot(snapshot)
    _add(checks, "S13REVIEW-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S13_STAGE_REVIEW_VERIFIED_NO_ACTION", snapshot_result)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _add(checks, "S13REVIEW-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
    return _result(checks, hashes, snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, Any]] = {}
    for relative in ROLLBACK_ARTIFACTS:
        candidate = root / relative
        artifacts[relative.as_posix()] = {
            "status": "PASS" if candidate.is_file() else "FAIL",
            "sha256": sha256_file(candidate) if candidate.is_file() else "MISSING",
        }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "CLOSE_S13_REVIEW_CANDIDATE_PRESERVE_SIGNED_PHASE_EVIDENCE_NO_EXTERNAL_MUTATION",
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
    paths.update(
        {
            CONTRACT_PATH.as_posix(),
            FINDINGS_PATH.as_posix(),
            FIXTURE_PATH.as_posix(),
            TEST_PATH.as_posix(),
            ORACLE_PATH.as_posix(),
            *(path.as_posix() for path in CONTROL_ARTIFACTS),
        }
    )
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
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S13_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if validation["status"] == "PASS" else "S13_STAGE_REVIEW_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "review_limitations": findings.get("explicit_limitations") if isinstance(findings, Mapping) else [],
        "stage_snapshot_summary": {
            "status": validation["snapshot_result"]["status"] if "snapshot_result" in validation else evaluate_stage_snapshot(validation["snapshot"])["status"],
            "reason_codes": evaluate_stage_snapshot(validation["snapshot"])["reason_codes"],
            "real_time_waited": False,
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S13/stage_review_test.py --junitxml=machine/evidence/S13/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S13/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S13/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S13 --evidence machine/evidence",
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
    rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    replacement = {
        "id": "INDEX-S13-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S13/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    positions = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) > 1:
        raise Stage13ReviewError("duplicate S13 stage-review evidence index rows")
    if positions:
        rows[positions[0]] = replacement
    else:
        rows.append(replacement)
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in rows))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage13ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage13ReviewError("cannot write evidence for a failed S13 review")
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


def _manifest_current(root: Path) -> bool:
    try:
        manifest = strict_json_load(root / ARTIFACT_MANIFEST_PATH)
        sums = _parse_sums(root / SHA256SUMS_PATH)
    except Exception:
        return False
    rows = manifest.get("files") if isinstance(manifest, Mapping) else None
    if not isinstance(rows, list):
        return False
    entries: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            return False
        relative = row["path"]
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in entries:
            return False
        entries[relative] = row
    excluded = {(root / ARTIFACT_MANIFEST_PATH).resolve(), (root / SHA256SUMS_PATH).resolve()}
    expected: List[Path] = []
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate.resolve() in excluded:
            continue
        relative = candidate.relative_to(root)
        if any(part in _EXCLUDED_MANIFEST_PARTS for part in relative.parts) or candidate.suffix in {".pyc", ".pyo"} or candidate.name == ".DS_Store":
            continue
        expected.append(candidate)
    expected_paths = {path.relative_to(root).as_posix() for path in expected}
    manifest_key = ARTIFACT_MANIFEST_PATH.as_posix()
    if (
        manifest.get("schema_version") != "1.0.0"
        or manifest.get("version") != VERSION
        or manifest.get("file_count") != len(rows)
        or [row.get("path") for row in rows] != sorted(entries)
        or set(entries) != expected_paths
        or set(sums) != expected_paths | {manifest_key}
        or sums.get(manifest_key) != sha256_file(root / ARTIFACT_MANIFEST_PATH)
    ):
        return False
    return all(
        entries[path.relative_to(root).as_posix()].get("sha256") == sums[path.relative_to(root).as_posix()] == sha256_file(path)
        and entries[path.relative_to(root).as_posix()].get("bytes") == path.stat().st_size
        for path in expected
    )


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        raise Stage13ReviewError("S13 review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    index = [row for row in index_rows if row.get("id") == "INDEX-S13-STAGE-REVIEW"]
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S13-STAGE-REVIEW"
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("decision") == "S13_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S13/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S13_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("recommendation_generated") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and len(index) == 1
        and index[0].get("kind") == "STAGE_REVIEW_EVIDENCE"
        and index[0].get("stage_id") == STAGE_ID
        and index[0].get("contract_id") == CONTRACT_ID
        and index[0].get("status") == "PASS"
        and index[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index[0].get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index[0].get("next") == "S13/GITHUB_STAGE_UPLOAD_READY"
        and _manifest_current(root)
    )
    if not valid:
        raise Stage13ReviewError("existing S13 review evidence is not reproducible or its manifest is stale")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/GITHUB_STAGE_UPLOAD_READY",
    }


__all__ = [
    "BASELINE_HASHES",
    "CONTRACT_ID",
    "CONTRACT_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINDINGS_PATH",
    "FIXTURE_PATH",
    "ORACLE_PATH",
    "PHASE_SPECS",
    "PHASE_VERIFIERS",
    "REQUIRED_GATES",
    "ROLLBACK_ARTIFACTS",
    "Stage13ReviewError",
    "evaluate_contract",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
