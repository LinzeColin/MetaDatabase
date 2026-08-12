"""Fail-closed, offline whole-stage review for ABD S12.

The frozen Task Pack defines S12/P01--P04 but no stage-review task.  This
independent local addendum verifies those signed receipts without changing the
frozen phase baseline.  It is intentionally a small, targeted review: it does
not rerun phase test suites, run a full regression, wait in real time, access
the network, or enable a recommendation, account, deployment, or order path.
"""

from __future__ import annotations

import argparse
import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .capacity_correlation import verify_existing_phase_evidence as verify_p02
from .economics_sensitivity import verify_existing_phase_evidence as verify_p03
from .target_curve import verify_existing_phase_evidence as verify_p01
from .target_falsification_gate import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S12"
REVIEW_ID = "ABD-S12-WHOLE-STAGE-REVIEW"
STAGE_ID = "S12"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage12_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S12/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S12_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S12/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S12/STAGE_REVIEW/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S12/STAGE_REVIEW/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S12-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S12-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
ORACLE_PATH = Path("abd_acceptance/stage12_review.py")
INTEGRATION_PATHS = (Path("abd_acceptance/__main__.py"), Path("abd_acceptance/evidence_continuity.py"))

PHASE_EXTERNAL_BOUNDARY_BASE = {
    "external_network_accessed": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_account_balance_read_or_written": False,
    "real_time_soak_waited": False,
    "recommendation_generated_or_enabled": False,
}
PHASE_EXTERNAL_BOUNDARY_WITH_MARKET = dict(
    PHASE_EXTERNAL_BOUNDARY_BASE,
    real_market_or_provider_capacity_observed=False,
)
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

PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    "P01": {
        "requirement_id": "REQ-S12-P01",
        "contract_id": "AC-S12-P01",
        "target": "固定时钟下目标曲线与高精度参考一致。",
        "outputs": ["target_engine.py", "cashflow_adjustment.py", "target_vectors.json"],
        "module_path": "abd_acceptance/target_curve.py",
        "test_path": "tests/S12/P01_test.py",
        "fixture_path": "machine/tests/fixtures/S12_P01.json",
        "evidence_path": "machine/evidence/EVD-S12-P01.json",
        "evidence_sha256": "9462cfab12b28218bf84419d45bf0c4d512aa406d5547de108f0dfbb09d4214a",
        "rollback_path": "machine/evidence/EVD-S12-P01_rollback.json",
        "rollback_sha256": "47601c6b52ad0fb04eae4bc2231bcf24ecb4a023d4e301f6a5a00fc3c4c2c69f",
        "decision": "TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED",
        "next": "S12/P02_READY_NOT_STARTED",
        "release_status": "S12_P01_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
        "external_boundary": PHASE_EXTERNAL_BOUNDARY_BASE,
    },
    "P02": {
        "requirement_id": "REQ-S12-P02",
        "contract_id": "AC-S12-P02",
        "target": "不把高度相关机会重复计入30%覆盖。",
        "outputs": ["capacity_model.py", "equivalent_signal.py", "capacity_report.json"],
        "module_path": "abd_acceptance/capacity_correlation.py",
        "test_path": "tests/S12/P02_test.py",
        "fixture_path": "machine/tests/fixtures/S12_P02.json",
        "evidence_path": "machine/evidence/EVD-S12-P02.json",
        "evidence_sha256": "dba62cb8d87a6a33fb7e4ea90615a7a892233e908fd48973000afc43576395f0",
        "rollback_path": "machine/evidence/EVD-S12-P02_rollback.json",
        "rollback_sha256": "1aeb15bd630c8f4dc9eaba24f8c344db3047d363c12bcba909d46f6bb0a2f4ca",
        "decision": "CAPACITY_CORRELATION_READY_DOWNSTREAM_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED",
        "next": "S12/P03_READY_NOT_STARTED",
        "release_status": "S12_P02_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
        "external_boundary": PHASE_EXTERNAL_BOUNDARY_WITH_MARKET,
    },
    "P03": {
        "requirement_id": "REQ-S12-P03",
        "contract_id": "AC-S12-P03",
        "target": "所有收益带区间、置信度和失败概率，不输出保证。",
        "outputs": ["economics.py", "sensitivity_grid.json", "opportunity_cost.json"],
        "module_path": "abd_acceptance/economics_sensitivity.py",
        "test_path": "tests/S12/P03_test.py",
        "fixture_path": "machine/tests/fixtures/S12_P03.json",
        "evidence_path": "machine/evidence/EVD-S12-P03.json",
        "evidence_sha256": "10ece6229575dc17dfed64e802d734d1ad199df592393b9525552d9f26c04a58",
        "rollback_path": "machine/evidence/EVD-S12-P03_rollback.json",
        "rollback_sha256": "04cb344aeafb66c96ec4efa20360c200c1bba7887b9bb2f1c249032d03c1ad8e",
        "decision": "ECONOMICS_SENSITIVITY_READY_DOWNSTREAM_FALSIFICATION_GATE_REQUIRED",
        "next": "S12/P04_READY_NOT_STARTED",
        "release_status": "S12_P03_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
        "external_boundary": PHASE_EXTERNAL_BOUNDARY_WITH_MARKET,
    },
    "P04": {
        "requirement_id": "REQ-S12-P04",
        "contract_id": "AC-S12-P04",
        "target": "目标短缺只报告，不降低阈值、仓位或证据门。",
        "outputs": ["target_falsification.py", "target_acceptance.json", "kill_report.schema.json"],
        "module_path": "abd_acceptance/target_falsification_gate.py",
        "test_path": "tests/S12/P04_test.py",
        "fixture_path": "machine/tests/fixtures/S12_P04.json",
        "evidence_path": "machine/evidence/EVD-S12-P04.json",
        "evidence_sha256": "73d7574576fbc86fae29e0de7f9e671204c934e078f847037115a50c9c50441b",
        "rollback_path": "machine/evidence/EVD-S12-P04_rollback.json",
        "rollback_sha256": "9545a7065a616293af8fdd06ba13af266048f1fee4864692987e6423296520c0",
        "decision": "TARGET_FALSIFICATION_AND_VERIFICATION_CONTRACT_READY_STAGE_REVIEW_REQUIRED",
        "next": "S12/STAGE_REVIEW_READY_NOT_STARTED",
        "release_status": "S12_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
        "external_boundary": PHASE_EXTERNAL_BOUNDARY_WITH_MARKET,
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
    "TARGET_CURVE_AND_AUDITED_CASHFLOW_GATE_PRESERVED",
    "CORRELATION_CAPACITY_NOT_TARGET_COVERAGE_GATE_PRESERVED",
    "SYNTHETIC_SENSITIVITY_NOT_RETURN_OR_GUARANTEE_GATE_PRESERVED",
    "FALSIFICATION_VERIFICATION_SHORTFALL_REPORT_ONLY_GATE_PRESERVED",
    "NO_NETWORK_ORDER_OR_REAL_TIME_SOAK_EXECUTED",
    "ALL_REVIEW_FINDINGS_RESOLVED",
    "NO_FULL_REGRESSION_EXECUTED",
]
ROLLBACK_ARTIFACTS = (
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
    *(Path(spec["evidence_path"]) for spec in PHASE_SPECS.values()),
    *(Path(spec["rollback_path"]) for spec in PHASE_SPECS.values()),
)
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")
_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}


class Stage12ReviewError(ValueError):
    """Raised when S12 whole-stage review evidence is not reproducible."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage12ReviewError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage12ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative)
    return value


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise Stage12ReviewError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise Stage12ReviewError("JSONL row %d is not an object" % number)
        rows.append(value)
    if not rows:
        raise Stage12ReviewError("JSONL is empty")
    return rows


def _parse_sums(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise Stage12ReviewError("invalid SHA256SUMS line %d" % number)
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in parsed:
            raise Stage12ReviewError("unsafe or duplicate checksum path")
        parsed[relative] = digest
    if not parsed:
        raise Stage12ReviewError("SHA256SUMS is empty")
    return parsed


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise Stage12ReviewError("JUnit contains no suites")
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


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise Stage12ReviewError("expected decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise Stage12ReviewError("invalid decimal") from exc
    if not parsed.is_finite():
        raise Stage12ReviewError("decimal must be finite")
    return parsed


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
        "task_ids": ["T-S12-%s-%02d" % (phase, number) for phase in PHASE_SPECS for number in (1, 2, 3)],
    }


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one immutable S12 review snapshot without enabling action."""

    keys = {
        "phase_receipts_current",
        "taskpack_trace_closed",
        "target_curve_and_cashflow_gate_preserved",
        "correlation_capacity_gate_preserved",
        "synthetic_sensitivity_gate_preserved",
        "falsification_verification_shortfall_gate_preserved",
        "external_action_boundary_preserved",
        "portable_evidence",
        "findings_open",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != keys:
        raise Stage12ReviewError("stage snapshot shape is invalid")
    for key in keys - {"findings_open"}:
        if type(snapshot.get(key)) is not bool:
            raise Stage12ReviewError("%s must be boolean" % key)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise Stage12ReviewError("findings_open must be a nonnegative integer")
    reason_map = (
        ("phase_receipts_current", "PHASE_RECEIPTS_NOT_CURRENT"),
        ("taskpack_trace_closed", "TASKPACK_TRACE_NOT_CLOSED"),
        ("target_curve_and_cashflow_gate_preserved", "TARGET_CURVE_OR_AUDITED_CASHFLOW_GATE_RELAXED"),
        ("correlation_capacity_gate_preserved", "CORRELATION_CAPACITY_OR_TARGET_COVERAGE_GATE_RELAXED"),
        ("synthetic_sensitivity_gate_preserved", "SYNTHETIC_SENSITIVITY_OR_NO_GUARANTEE_GATE_RELAXED"),
        ("falsification_verification_shortfall_gate_preserved", "FALSIFICATION_VERIFICATION_OR_SHORTFALL_GATE_RELAXED"),
        ("external_action_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    result: Dict[str, Any] = {
        "status": "S12_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S12_STAGE_REVIEW_REJECTED_NO_ACTION",
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
        _add(checks, "S12REVIEW-CONTRACT-FIXTURE-FINDINGS-SHAPE", False, "one or more review inputs are malformed")
        return
    identity = {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "targeted_test_command": "pytest -q tests/S12/stage_review_test.py",
        "release_status_on_pass": "S12_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "next_on_pass": "S12/GITHUB_STAGE_UPLOAD_READY",
        "next_on_fail": "S12/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }
    _add(checks, "S12REVIEW-CONTRACT-IDENTITY", all(contract.get(key) == value for key, value in identity.items()), identity)
    _add(checks, "S12REVIEW-SCOPE-EXACT", contract.get("review_scope") == _review_scope(), contract.get("review_scope"))
    _add(checks, "S12REVIEW-PHASE-RECORDS-EXACT", contract.get("phase_records") == _phase_records(), contract.get("phase_records"))
    _add(checks, "S12REVIEW-FROZEN-BASELINE-PINS-EXACT", contract.get("baseline_hashes") == BASELINE_HASHES, contract.get("baseline_hashes"))
    policy = {
        "offline_deterministic_only": True,
        "phase_test_rerun_allowed": False,
        "full_regression_or_real_time_soak_allowed": False,
        "single_pass_fixture_cases_only": True,
        "github_upload_performed_by_local_review": False,
        "production_deployed_or_activated": False,
        "incremental_cash_spent_aud": "0.00",
    }
    _add(checks, "S12REVIEW-NO-FULL-REGRESSION-OR-REALTIME-POLICY", contract.get("execution_policy") == policy, contract.get("execution_policy"))
    _add(checks, "S12REVIEW-REQUIRED-GATES-EXACT", contract.get("review_gates") == REQUIRED_GATES, contract.get("review_gates"))
    fixture_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S12-WHOLE-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "single_pass_case_count": 9,
        "minimum_targeted_pytest_cases": 24,
        "expected_next": "S12/GITHUB_STAGE_UPLOAD_READY",
        "expected_release_status": "S12_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
    }
    _add(checks, "S12REVIEW-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in fixture_identity.items()), fixture_identity)
    _add(
        checks,
        "S12REVIEW-FIXTURE-PHASE-RECEIPT-PINS-EXACT",
        fixture.get("expected_phase_evidence_sha256") == {phase: spec["evidence_sha256"] for phase, spec in PHASE_SPECS.items()}
        and fixture.get("expected_phase_rollback_sha256") == {phase: spec["rollback_sha256"] for phase, spec in PHASE_SPECS.items()},
        {"evidence": fixture.get("expected_phase_evidence_sha256"), "rollback": fixture.get("expected_phase_rollback_sha256")},
    )
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_clock") == FIXED_CLOCK
        and findings.get("summary") == {"total": 0, "open": 0, "resolved": 0, "blocked": 0}
        and findings.get("findings") == []
        and findings.get("external_effect_boundary") == FINDINGS_EXTERNAL_BOUNDARY
    )
    _add(checks, "S12REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, findings.get("summary"))


def _check_baseline(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected = contract.get("baseline_hashes")
    if expected != BASELINE_HASHES:
        _add(checks, "S12REVIEW-BASELINE-CONTRACT-PINS-EXACT", False, expected)
        return
    _add(checks, "S12REVIEW-BASELINE-CONTRACT-PINS-EXACT", True, sorted(BASELINE_HASHES))
    all_match = True
    for relative, digest in sorted(BASELINE_HASHES.items()):
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            passed = actual == digest
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            passed = False
        all_match = all_match and passed
        _add(checks, "S12REVIEW-BASELINE-%s" % Path(relative).stem.upper(), passed, {"expected": digest, "actual": actual})
    _add(checks, "S12REVIEW-BASELINE-CRITICAL-HASHES", all_match, "all frozen baseline hashes match" if all_match else "frozen baseline drift")


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S12REVIEW-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S12REVIEW-CONTRACTS-STRICT-JSON")
    roadmap = _safe_load(root, root / "machine/facts/roadmap.json", checks, "S12REVIEW-ROADMAP-STRICT-JSON")
    graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S12REVIEW-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, root / "machine/facts/traceability_matrix.json", checks, "S12REVIEW-TRACE-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(roadmap, Mapping) or not isinstance(graph, Mapping) or not isinstance(traceability, list):
        _add(checks, "S12REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "task pack inputs malformed")
        return False
    tasks = graph.get("tasks")
    stages = roadmap.get("stages")
    if not isinstance(tasks, list) or not isinstance(stages, list):
        _add(checks, "S12REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "task graph or roadmap unavailable")
        return False
    valid = True
    detail: Dict[str, Any] = {}
    for phase, spec in PHASE_SPECS.items():
        try:
            requirement = _row(requirements, spec["requirement_id"])
            acceptance = _row(contracts, spec["contract_id"])
            trace = _row(traceability, spec["requirement_id"], key="requirement_id")
            stage = _row(stages, STAGE_ID)
            phases = stage.get("phases") if isinstance(stage, Mapping) else None
            roadmap_phase = _row(phases, phase)
            phase_tasks = [task for task in tasks if isinstance(task, Mapping) and task.get("stage_id") == STAGE_ID and task.get("phase_id") == phase]
            expected_task_ids = ["T-S12-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            task_ids = [task.get("id") for task in phase_tasks]
            task_outputs = {output for task in phase_tasks for output in task.get("outputs", [])}
            required_outputs = set(spec["outputs"]) | {spec["test_path"], spec["fixture_path"], spec["evidence_path"], spec["rollback_path"]}
            expected_oracle = {
                "type": "EXECUTABLE",
                "command": "python -m abd_acceptance --contract %s --evidence machine/evidence" % spec["contract_id"],
                "rule": spec["target"],
            }
            current = (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("scope") == spec["outputs"]
                and requirement.get("target") == spec["target"]
                and requirement.get("primary_acceptance_criteria_id") == spec["contract_id"]
                and acceptance.get("requirement_id") == spec["requirement_id"]
                and acceptance.get("oracle") == expected_oracle
                and acceptance.get("pass_gate") == spec["target"]
                and roadmap_phase.get("outputs") == spec["outputs"]
                and roadmap_phase.get("pass_gate") == spec["target"]
                and task_ids == expected_task_ids
                and required_outputs.issubset(task_outputs)
                and all((root / path).is_file() for path in (*spec["outputs"], spec["module_path"], spec["test_path"], spec["fixture_path"], spec["evidence_path"], spec["rollback_path"]))
                and trace.get("acceptance_criteria_id") == spec["contract_id"]
                and trace.get("task_ids") == expected_task_ids
                and trace.get("test_ids") == ["TEST-S12-%s" % phase, "TEST-S12-%s-BOUNDARY" % phase, "TEST-S12-%s-REPLAY" % phase]
                and trace.get("evidence_id") == "EVD-S12-%s" % phase
                and trace.get("artifact_ids") == ["ART-S12-%s-%02d" % (phase, number) for number in (1, 2, 3)]
            )
        except Exception as exc:
            current = False
            task_ids = "%s: %s" % (type(exc).__name__, exc)
        valid = valid and current
        detail[phase] = {"passed": current, "task_ids": task_ids}
    _add(checks, "S12REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", valid, detail)
    return valid


def _check_phase_receipts(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> Tuple[bool, bool, bool]:
    if contract.get("phase_records") != _phase_records():
        _add(checks, "S12REVIEW-PHASE-RECORDS-AVAILABLE", False, contract.get("phase_records"))
        return False, False, False
    _add(checks, "S12REVIEW-PHASE-RECORDS-AVAILABLE", True, list(PHASE_SPECS))
    phase_ok = True
    portable_ok = True
    boundary_ok = True
    for phase, spec in PHASE_SPECS.items():
        evidence_path = root / spec["evidence_path"]
        rollback_path = root / spec["rollback_path"]
        evidence = _safe_load(root, evidence_path, checks, "S12REVIEW-%s-EVIDENCE-STRICT-JSON" % phase)
        rollback = _safe_load(root, rollback_path, checks, "S12REVIEW-%s-ROLLBACK-STRICT-JSON" % phase)
        try:
            evidence_hash = sha256_file(evidence_path)
            rollback_hash = sha256_file(rollback_path)
            hashes[spec["evidence_path"]] = evidence_hash
            hashes[spec["rollback_path"]] = rollback_hash
            pin_ok = (
                evidence_hash == spec["evidence_sha256"]
                and rollback_hash == spec["rollback_sha256"]
                and fixture.get("expected_phase_evidence_sha256", {}).get(phase) == evidence_hash
                and fixture.get("expected_phase_rollback_sha256", {}).get(phase) == rollback_hash
            )
            _add(checks, "S12REVIEW-%s-RECEIPT-HASHES" % phase, pin_ok, {"evidence": evidence_hash, "rollback": rollback_hash})
        except Exception as exc:
            pin_ok = False
            _add(checks, "S12REVIEW-%s-RECEIPT-HASHES" % phase, False, "%s: %s" % (type(exc).__name__, exc))
        try:
            verified = PHASE_VERIFIERS[phase](root)
            verifier_ok = (
                verified.get("status") == "PASS"
                and verified.get("contract_id") == spec["contract_id"]
                and verified.get("evidence_path") == spec["evidence_path"]
                and verified.get("evidence_sha256") == spec["evidence_sha256"]
                and verified.get("next") == spec["next"]
            )
        except Exception as exc:
            verified = "%s: %s" % (type(exc).__name__, exc)
            verifier_ok = False
        _add(checks, "S12REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, verifier_ok, verified)
        receipt_ok = (
            isinstance(evidence, Mapping)
            and evidence.get("status") == "PASS"
            and evidence.get("contract_id") == spec["contract_id"]
            and evidence.get("requirement_id") == spec["requirement_id"]
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == phase
            and evidence.get("decision") == spec["decision"]
            and evidence.get("next") == spec["next"]
            and evidence.get("release_status") == spec["release_status"]
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("external_effect_boundary") == spec["external_boundary"]
            and isinstance(rollback, Mapping)
            and rollback.get("contract_id") == spec["contract_id"]
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and rollback.get("production_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_time_soak_waited") is False
            and rollback.get("incremental_cash_spent_aud") == "0.00"
        )
        _add(checks, "S12REVIEW-%s-RECEIPT-AND-BOUNDARY-EXACT" % phase, receipt_ok, {"decision": evidence.get("decision") if isinstance(evidence, Mapping) else None, "next": evidence.get("next") if isinstance(evidence, Mapping) else None})
        try:
            index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % spec["contract_id"])
            index_ok = (
                index.get("kind") == "PHASE_EVIDENCE"
                and index.get("stage_id") == STAGE_ID
                and index.get("contract_id") == spec["contract_id"]
                and index.get("requirement_id") == spec["requirement_id"]
                and index.get("status") == "PASS"
                and index.get("actual_artifact") == spec["evidence_path"]
                and index.get("artifact_sha256") == spec["evidence_sha256"]
                and index.get("next") == spec["next"]
                and index.get("verified_at") == FIXED_CLOCK
            )
        except Exception as exc:
            index = "%s: %s" % (type(exc).__name__, exc)
            index_ok = False
        _add(checks, "S12REVIEW-%s-EVIDENCE-INDEX-EXACT" % phase, index_ok, index)
        current_portable = _portable(evidence) and _portable(rollback) and _portable(index)
        _add(checks, "S12REVIEW-%s-EVIDENCE-PORTABLE" % phase, current_portable, "portable" if current_portable else "local path detected")
        phase_ok = phase_ok and pin_ok and verifier_ok and receipt_ok and index_ok
        portable_ok = portable_ok and current_portable
        boundary_ok = boundary_ok and receipt_ok
    _add(checks, "S12REVIEW-PHASE-RECEIPTS-CURRENT", phase_ok, "all signed P01--P04 receipts current" if phase_ok else "one or more phase receipts are stale")
    _add(checks, "S12REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS", portable_ok, "portable" if portable_ok else "local path detected")
    _add(checks, "S12REVIEW-PHASE-EXTERNAL-BOUNDARY-EXACT", boundary_ok, "all phase boundaries checked" if boundary_ok else "boundary mismatch")
    return phase_ok, portable_ok, boundary_ok


def _artifact_identity(document: Any, phase: str) -> bool:
    spec = PHASE_SPECS[phase]
    return (
        isinstance(document, Mapping)
        and document.get("schema_version") == "1.0.0"
        and document.get("contract_id") == spec["contract_id"]
        and document.get("requirement_id") == spec["requirement_id"]
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == phase
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    )


def _check_stage_controls(root: Path, checks: List[Dict[str, Any]]) -> Tuple[bool, bool, bool, bool]:
    vectors = _safe_load(root, root / "target_vectors.json", checks, "S12REVIEW-TARGET-VECTORS-STRICT-JSON")
    capacity = _safe_load(root, root / "capacity_report.json", checks, "S12REVIEW-CAPACITY-REPORT-STRICT-JSON")
    grid = _safe_load(root, root / "sensitivity_grid.json", checks, "S12REVIEW-SENSITIVITY-GRID-STRICT-JSON")
    opportunity = _safe_load(root, root / "opportunity_cost.json", checks, "S12REVIEW-OPPORTUNITY-COST-STRICT-JSON")
    target = _safe_load(root, root / "target_acceptance.json", checks, "S12REVIEW-TARGET-ACCEPTANCE-STRICT-JSON")
    kill_schema = _safe_load(root, root / "kill_report.schema.json", checks, "S12REVIEW-KILL-SCHEMA-STRICT-JSON")

    target_curve_ok = False
    try:
        rows = vectors.get("monthly_rows") if isinstance(vectors, Mapping) else None
        flows = [flow for row in rows for flow in row.get("cashflows", [])] if isinstance(rows, list) and all(isinstance(row, Mapping) for row in rows) else []
        target_curve_ok = (
            isinstance(vectors, Mapping)
            and vectors.get("schema_version") == "1.0.0"
            and vectors.get("contract_id") == "AC-S12-P01"
            and vectors.get("artifact_id") == "ART-S12-P01-03"
            and vectors.get("product_version") == VERSION
            and vectors.get("fixed_clock") == FIXED_CLOCK
            and vectors.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
            and vectors.get("decision") == "TARGET_CURVE_REPLAY_READY_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"
            and vectors.get("next") == "S12/P02_READY_NOT_STARTED"
            and vectors.get("target_curve") == {
                "formula": "B_n = 300 * 1.3^n",
                "initial_bankroll_cents": 30000,
                "monthly_log_growth": "0.26236426446749106",
                "monthly_return": "0.30",
                "target_rounding": "UP_TO_INTEGER_CENT_FOR_CONSERVATIVE_TARGET",
            }
            and vectors.get("summary") == {
                "actual_execution_or_account_evidence_claimed": False,
                "chase_loss_prohibited": True,
                "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
                "months": 4,
                "target_on_track_count": 3,
                "target_shortfall_count": 1,
                "target_shortfall_may_relax_gate": False,
            }
            and vectors.get("claim_boundary") == PHASE_EXTERNAL_BOUNDARY_BASE
            and isinstance(rows, list)
            and [row.get("month_index") for row in rows] == [0, 1, 2, 3]
            and all(row.get("shortfall_action") == "REPORT_ONLY_NO_GATE_RELAXATION" for row in rows)
            and rows[3].get("target_status") == "TARGET_SHORTFALL_REPORT_ONLY"
            and rows[3].get("target_gap_cents") == -6083
            and all(
                flow.get("evidence_status") == "SYNTHETIC_VERIFIED_FOR_TEST_ONLY"
                and flow.get("timing") in {"MONTH_START", "MONTH_END"}
                for flow in flows
            )
        )
    except (IndexError, KeyError, TypeError, ValueError):
        target_curve_ok = False
    _add(checks, "S12REVIEW-TARGET-CURVE-AND-AUDITED-CASHFLOW-GATE-PRESERVED", target_curve_ok, {"row_count": len(vectors.get("monthly_rows", [])) if isinstance(vectors, Mapping) else None})

    capacity_ok = False
    try:
        clusters = capacity.get("clusters") if isinstance(capacity, Mapping) else None
        allocations = capacity.get("platform_allocations") if isinstance(capacity, Mapping) else None
        capacity_ok = (
            _artifact_identity(capacity, "P02")
            and capacity.get("artifact_id") == "ART-S12-P02-03"
            and capacity.get("decision") == "CAPACITY_CORRECTED_SYNTHETIC_ONLY_NOT_TARGET_COVERAGE"
            and capacity.get("next") == "S12/P03_READY_NOT_STARTED"
            and capacity.get("external_effect_boundary") == PHASE_EXTERNAL_BOUNDARY_WITH_MARKET
            and capacity.get("policy") == {
                "chase_loss_prohibited": True,
                "correlation_rule": "ONE_REPRESENTATIVE_PER_PREDECLARED_HIGH_CORRELATION_CLUSTER",
                "executable_fraction_rule": "FLOOR_RISK_LIMITED_CAPACITY_TIMES_DECLARED_EXECUTABLE_FRACTION",
                "platform_rule": "DETERMINISTIC_DECLARED_REMAINING_CAPACITY_NO_OVERALLOCATION",
                "target_shortfall_may_relax_gate": False,
            }
            and capacity.get("target_plausibility") == {
                "capacity_is_not_return_or_30_PERCENT_COVERAGE": True,
                "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
                "independent_equivalent_signals_observed": 5,
                "independent_equivalent_signals_required": 1000,
                "status": "INSUFFICIENT_INDEPENDENT_EQUIVALENT_SIGNALS_TARGET_UNVERIFIED",
            }
            and capacity.get("summary") == {
                "correlation_adjusted_capacity_cents": 5090,
                "distinct_correlation_cluster_count": 6,
                "duplicate_capacity_not_counted_cents": 2200,
                "final_platform_and_executable_capacity_cents": 4000,
                "independent_equivalent_signals": 5,
                "platform_limited_capacity_not_counted_cents": 1090,
                "platform_remaining_capacity_cents": {"SYNTHETIC-OTHER-C": 100, "SYNTHETIC-SPORTSBET-B": 0, "SYNTHETIC-TAB-A": 0},
                "raw_candidate_count": 8,
                "raw_naive_executable_capacity_cents": 7290,
                "remaining_opportunity_count": 5,
            }
            and isinstance(clusters, list)
            and len(clusters) == 6
            and all(
                row.get("counting_rule") == "ONE_REPRESENTATIVE_PER_PREDECLARED_HIGH_CORRELATION_CLUSTER"
                and row.get("correlation_adjusted_capacity_cents") <= row.get("naive_member_executable_capacity_cents")
                for row in clusters
            )
            and {row.get("cluster_id"): row.get("not_counted_as_additional_coverage_ids") for row in clusters}.get("C01-SAME-EVENT-MARKETS") == ["S12-P02-C01-B"]
            and {row.get("cluster_id"): row.get("not_counted_as_additional_coverage_ids") for row in clusters}.get("C03-LEAGUE-WEATHER-LINEUP") == ["S12-P02-C03-B"]
            and isinstance(allocations, list)
            and sum(row.get("final_executable_capacity_cents", -1) for row in allocations) == 4000
            and all(row.get("representative_selected") is True for row in allocations)
        )
    except (KeyError, TypeError, ValueError):
        capacity_ok = False
    _add(checks, "S12REVIEW-CORRELATION-CAPACITY-NOT-TARGET-COVERAGE-GATE-PRESERVED", capacity_ok, {"cluster_count": len(capacity.get("clusters", [])) if isinstance(capacity, Mapping) else None})

    sensitivity_ok = False
    try:
        bands = grid.get("return_bands") if isinstance(grid, Mapping) else None
        sensitivity_ok = (
            _artifact_identity(grid, "P03")
            and _artifact_identity(opportunity, "P03")
            and grid.get("artifact_id") == "ART-S12-P03-02"
            and opportunity.get("artifact_id") == "ART-S12-P03-03"
            and grid.get("decision") == "SYNTHETIC_ECONOMICS_SENSITIVITY_TARGET_UNVERIFIED_NO_RECOMMENDATION"
            and opportunity.get("decision") == "SYNTHETIC_COST_DISCLOSURE_ONLY_DO_NOT_REPORT_ROI_OR_TARGET_SUCCESS"
            and grid.get("external_effect_boundary") == PHASE_EXTERNAL_BOUNDARY_WITH_MARKET
            and opportunity.get("external_effect_boundary") == PHASE_EXTERNAL_BOUNDARY_WITH_MARKET
            and grid.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and opportunity.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and grid.get("summary") == {
                "all_scenarios_leave_target_unverified": True,
                "available_capacity_cents_from_signed_p02": 4000,
                "highest_upper_band_cents": 800,
                "independent_equivalent_signals_from_signed_p02": 5,
                "lowest_upper_band_target_shortfall_cents": 8200,
                "return_bands_are_synthetic_sensitivity_not_revenue": True,
                "target_increment_cents": 9000,
            }
            and isinstance(bands, list)
            and len(bands) == 3
            and all(
                row.get("action") == "SYNTHETIC_SENSITIVITY_NOT_ACTIONABLE"
                and row.get("evidence_status") == "SYNTHETIC_VERIFIED_FOR_TEST_ONLY"
                and row.get("target_covered") is False
                and _decimal(row.get("confidence")) + _decimal(row.get("failure_probability")) == Decimal("1.0000")
                for row in bands
            )
            and [(row.get("scenario_id"), row.get("return_band_cents")) for row in bands]
            == [
                ("S12-P03-BASELINE-SYNTHETIC", {"low": -400, "central": 100, "high": 800}),
                ("S12-P03-ADVERSE-ONE-IN-TEN-THOUSAND", {"low": -401, "central": 99, "high": 799}),
                ("S12-P03-NO-EXECUTION-SYNTHETIC", {"low": 0, "central": 0, "high": 0}),
            ]
            and opportunity.get("operating_cost") == {
                "bankroll_principal_cents": 30000,
                "existing_recurring_cost_status": "UNKNOWN_ACCOUNT_SPECIFIC_NO_BILLING_ACCESS",
                "existing_resources_are_not_relabelled_zero": True,
                "incremental_cash_budget_cents": 0,
                "incremental_cash_spent_cents": 0,
                "incremental_cash_status": "ZERO_NEW_CASH_ONLY_NOT_TOTAL_SYSTEM_COST",
            }
            and opportunity.get("return_cost_boundary", {}).get("actual_return_requires_verified_execution_and_reconciliation") is True
            and opportunity.get("return_cost_boundary", {}).get("return_bands_are_not_realized_revenue") is True
            and opportunity.get("return_cost_boundary", {}).get("roi_reported") is False
            and opportunity.get("return_cost_boundary", {}).get("target_curve_or_sensitivity_may_substitute_for_actual_return") is False
            and all(row.get("classification") == "SENSITIVITY_ONLY_NOT_OWNER_TIME_VALUATION" for row in opportunity.get("opportunity_cost_bands", []))
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        sensitivity_ok = False
    _add(checks, "S12REVIEW-SYNTHETIC-SENSITIVITY-NOT-RETURN-OR-GUARANTEE-GATE-PRESERVED", sensitivity_ok, {"band_count": len(grid.get("return_bands", [])) if isinstance(grid, Mapping) else None})

    falsification_ok = False
    try:
        plausibility = target.get("plausibility_gate", {}) if isinstance(target, Mapping) else {}
        falsification = target.get("falsification_gate", {}) if isinstance(target, Mapping) else {}
        verification = target.get("verification_gate", {}) if isinstance(target, Mapping) else {}
        reason_codes = [row.get("code") for row in kill_schema.get("reason_codes", [])] if isinstance(kill_schema, Mapping) else []
        falsification_ok = (
            _artifact_identity(target, "P04")
            and _artifact_identity(kill_schema, "P04")
            and target.get("artifact_id") == "ART-S12-P04-02"
            and kill_schema.get("artifact_id") == "ART-S12-P04-03"
            and target.get("decision") == "TARGET_FALSIFICATION_CONTRACT_READY_NO_EMPIRICAL_TARGET_VERIFICATION"
            and target.get("external_effect_boundary") == PHASE_EXTERNAL_BOUNDARY_WITH_MARKET
            and kill_schema.get("external_effect_boundary") == PHASE_EXTERNAL_BOUNDARY_WITH_MARKET
            and target.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and kill_schema.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and plausibility.get("required_shadow_days") == 90
            and plausibility.get("observed_shadow_days") == 0
            and plausibility.get("required_independent_equivalent_signals") == 1000
            and plausibility.get("observed_independent_equivalent_signals") == 5
            and plausibility.get("status") == "NOT_PLAUSIBLE_INSUFFICIENT_90D_OR_1000_SIGNALS"
            and falsification.get("current_empirical_assessment", {}).get("status") == "NOT_EVALUABLE_NO_EMPIRICAL_6_MONTH_DATA"
            and falsification.get("synthetic_case_assessment", {}).get("status") == "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL"
            and falsification.get("synthetic_case_assessment", {}).get("complete_calendar_months") == 6
            and falsification.get("synthetic_case_assessment", {}).get("independent_equivalent_signals") == 1000
            and falsification.get("synthetic_case_assessment", {}).get("monthly_return_95_upper_bound") == "0.2999"
            and falsification.get("synthetic_case_is_not_empirical") is True
            and verification.get("current_empirical_assessment", {}).get("status") == "NOT_VERIFIABLE_NO_ACTUAL_EXECUTION_AND_RECONCILIATION_EVIDENCE"
            and verification.get("current_empirical_assessment", {}).get("complete_calendar_months") == 0
            and verification.get("current_empirical_assessment", {}).get("unresolved_reconciliation_differences") == 0
            and target.get("target_shortfall_report") == {
                "bankroll_principal_cents": 30000,
                "best_synthetic_upper_band_cents": 800,
                "incremental_cash_budget_cents": 0,
                "status": "TARGET_SHORTFALL_REPORT_ONLY",
                "synthetic_upper_band_shortfall_cents": 8200,
                "target_increment_cents": 9000,
            }
            and target.get("hard_gate_invariants") == {
                "financial_return_verified_or_guaranteed": False,
                "order_submission_enabled": False,
                "recommendation_generated_or_enabled": False,
                "risk_target_shortfall_may_relax_gate": False,
                "shortfall_behavior": "REPORT_ONLY_NO_GATE_RELAXATION",
                "synthetic_artifacts_may_substitute_for_actual_return": False,
                "threshold_or_position_or_evidence_may_be_relaxed": False,
            }
            and kill_schema.get("hard_invariants") == {
                "actual_return_required_for_verification": True,
                "order_submission_enabled": False,
                "risk_target_shortfall_may_relax_gate": False,
                "synthetic_fixture_may_be_marked_empirical": False,
                "target_shortfall_behavior": "REPORT_ONLY_NO_GATE_RELAXATION",
            }
            and reason_codes
            == [
                "TARGET_SHORTFALL_REPORT_ONLY",
                "PLAUSIBILITY_INSUFFICIENT_90D_OR_1000_SIGNALS",
                "FALSIFICATION_REQUIRES_6_COMPLETE_MONTHS_AND_1000_SIGNALS",
                "VERIFICATION_REQUIRES_12_MONTHS_EXECUTION_EVIDENCE_AND_ZERO_RECONCILIATION_DIFFERENCE",
                "NO_GATE_RELAXATION_FOR_TARGET_SHORTFALL",
            ]
        )
    except (KeyError, TypeError, ValueError):
        falsification_ok = False
    _add(checks, "S12REVIEW-FALSIFICATION-VERIFICATION-SHORTFALL-REPORT-ONLY-GATE-PRESERVED", falsification_ok, {"plausibility": plausibility.get("status") if isinstance(plausibility, Mapping) else None, "verification": verification.get("current_empirical_assessment", {}).get("status") if isinstance(verification, Mapping) else None})
    return target_curve_ok, capacity_ok, sensitivity_ok, falsification_ok


def _check_snapshot_cases(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S12REVIEW-SINGLE-PASS-FIXTURE-CASES", False, "cases unavailable")
        return {}
    case_ids = [row.get("case_id") for row in cases if isinstance(row, Mapping)]
    shape_ok = len(cases) == 9 and len(case_ids) == len(cases) and len(set(case_ids)) == len(cases)
    _add(checks, "S12REVIEW-SINGLE-PASS-FIXTURE-CASES", shape_ok, {"case_count": len(cases), "case_ids": case_ids})
    results: Dict[str, Dict[str, Any]] = {}
    for row in cases:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("expected"), Mapping):
            _add(checks, "S12REVIEW-SINGLE-PASS-CASE-SHAPE", False, row)
            continue
        try:
            actual = evaluate_stage_snapshot(row["snapshot"])
            expected = row["expected"]
            passed = (
                actual.get("status") == expected.get("status")
                and actual.get("reason_codes") == expected.get("reason_codes")
                and actual.get("recommendation_generated") is False
                and actual.get("order_submission_enabled") is False
                and actual.get("external_network_used") is False
                and actual.get("real_time_soak_waited") is False
            )
            _add(checks, "S12REVIEW-CASE-%s" % row["case_id"], passed, {"actual": actual, "expected": expected})
            results[row["case_id"]] = actual
        except Exception as exc:
            _add(checks, "S12REVIEW-CASE-%s" % row["case_id"], False, "%s: %s" % (type(exc).__name__, exc))
    positive = results.get("POSITIVE_EXACT_STAGE")
    positive_ok = positive is not None and positive.get("status") == "S12_STAGE_REVIEW_VERIFIED_NO_ACTION"
    _add(checks, "S12REVIEW-CURRENT-FIXED-SNAPSHOT-NO-ACTION", positive_ok, positive)
    _add(checks, "S12REVIEW-NO-REPEATED-REPLAY-OR-SOAK", fixture.get("single_pass_case_count") == 9, "each frozen snapshot is evaluated once")
    return results


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        calls: list[str] = []
        forbidden_calls = {"sleep", "run", "Popen", "float", "submit_order"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else None
                if name in forbidden_calls:
                    calls.append(name)
        prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
        passed = not (imports & prohibited_imports) and not calls and ("float" + "(") not in source
        _add(checks, "S12REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", passed, {"imports": sorted(imports), "calls": sorted(calls)})
    except Exception as exc:
        _add(checks, "S12REVIEW-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        junit_ok = (
            summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and not summary["failures"]
            and not summary["errors"]
            and not summary["skipped"]
            and _junit_is_normalized(root / JUNIT_PATH)
        )
        _add(checks, "S12REVIEW-TARGETED-PYTEST-REPORT", junit_ok, {"summary": summary, "normalized": _junit_is_normalized(root / JUNIT_PATH)})
    except Exception as exc:
        _add(checks, "S12REVIEW-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S12REVIEW-PAID-DEPENDENCY-SCAN-PASS", "STATUS: PASS" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S12REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, root / PACK_REPORT_PATH, checks, "S12REVIEW-PACK-REPORT-STRICT-JSON")
    _add(checks, "S12REVIEW-PACK-REPORT-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("summary") if isinstance(report, Mapping) else "unavailable")


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any] | None) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "stage_status": "S12_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S12_WHOLE_STAGE_REVIEW_BLOCKED",
        "decision": "S12_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S12/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S12/STAGE_REVIEW_REMEDIATION_REQUIRED",
        "release_status": "S12_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT" if status == "PASS" else "S12_RELEASE_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "stage_snapshot": dict(snapshot) if snapshot is not None else None,
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root, root / CONTRACT_PATH, checks, "S12REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root, root / FINDINGS_PATH, checks, "S12REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S12REVIEW-FIXTURE-STRICT-JSON")
    if not isinstance(contract, Mapping) or not isinstance(findings, Mapping) or not isinstance(fixture, Mapping):
        return _result(checks, hashes, None)
    _check_contract(contract, fixture, findings, checks)
    _check_baseline(root, contract, checks, hashes)
    taskpack_ok = _check_taskpack(root, checks)
    phase_ok, portable_ok, boundary_ok = _check_phase_receipts(root, contract, fixture, checks, hashes)
    curve_ok, capacity_ok, sensitivity_ok, falsification_ok = _check_stage_controls(root, checks)
    _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    findings_open = findings.get("summary", {}).get("open") if isinstance(findings.get("summary"), Mapping) else -1
    snapshot = {
        "phase_receipts_current": phase_ok,
        "taskpack_trace_closed": taskpack_ok,
        "target_curve_and_cashflow_gate_preserved": curve_ok,
        "correlation_capacity_gate_preserved": capacity_ok,
        "synthetic_sensitivity_gate_preserved": sensitivity_ok,
        "falsification_verification_shortfall_gate_preserved": falsification_ok,
        "external_action_boundary_preserved": boundary_ok,
        "portable_evidence": portable_ok,
        "findings_open": findings_open,
    }
    stage_snapshot = evaluate_stage_snapshot(snapshot)
    _add(checks, "S12REVIEW-CURRENT-STAGE-SNAPSHOT-NO-ACTION", stage_snapshot["status"] == "S12_STAGE_REVIEW_VERIFIED_NO_ACTION", stage_snapshot)
    return _result(checks, hashes, stage_snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path), "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in ROLLBACK_ARTIFACTS
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S12-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S12_STAGE_REVIEW_CANDIDATE_KEEP_SIGNED_PHASE_RECEIPTS_AND_REPLAY_OFFLINE",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    phase_paths = [
        Path(path)
        for spec in PHASE_SPECS.values()
        for path in (*spec["outputs"], spec["module_path"], spec["test_path"], spec["fixture_path"], spec["evidence_path"], spec["rollback_path"])
    ]
    paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, *INTEGRATION_PATHS, *(Path(path) for path in BASELINE_HASHES), *phase_paths]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S12-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": validation["release_status"],
        "validation": validation,
        "phase_receipts": {
            phase: {
                "evidence_path": spec["evidence_path"],
                "evidence_sha256": sha256_file(root / spec["evidence_path"]),
                "rollback_path": spec["rollback_path"],
                "rollback_sha256": sha256_file(root / spec["rollback_path"]),
            }
            for phase, spec in PHASE_SPECS.items()
        },
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S12-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S12-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S12-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python -m abd_acceptance --verify-existing AC-S12-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S12/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S12/stage_review_test.py --junitxml=machine/evidence/S12/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S12/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S12 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_review": {"single_pass_fixture_cases": 9, "phase_test_suites_rerun": False, "full_regression_executed": False, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    updated = {
        "id": "INDEX-S12-STAGE-REVIEW",
        "kind": "STAGE_REVIEW_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S12/GITHUB_STAGE_UPLOAD_READY",
        "verified_at": FIXED_CLOCK,
    }
    positions = [index for index, row in enumerate(rows) if row.get("id") == updated["id"]]
    if len(positions) > 1:
        raise Stage12ReviewError("duplicate S12 stage-review evidence index rows")
    if positions:
        rows[positions[0]] = updated
    else:
        rows.append(updated)
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in rows))


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage12ReviewError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage12ReviewError("cannot write evidence for a failed S12 review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S12/GITHUB_STAGE_UPLOAD_READY",
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
        raise Stage12ReviewError("S12 review evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    index = [row for row in index_rows if row.get("id") == "INDEX-S12-STAGE-REVIEW"]
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S12_WHOLE_STAGE_REVIEW_PASS"
        and evidence.get("next") == "S12/GITHUB_STAGE_UPLOAD_READY"
        and evidence.get("release_status") == "S12_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and len(index) == 1
        and index[0].get("kind") == "STAGE_REVIEW_EVIDENCE"
        and index[0].get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and _manifest_current(root)
    )
    if not valid:
        raise Stage12ReviewError("existing S12 review evidence is not reproducible or its manifest is stale")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S12/GITHUB_STAGE_UPLOAD_READY",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABD S12 offline whole-stage review")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract")
    mode.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence", default="machine/evidence")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    evidence_dir = Path(args.evidence)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir
    if args.verify_existing:
        result = verify_existing_stage_review_evidence(root)
    else:
        if args.contract != CONTRACT_ID:
            parser.error("unsupported contract: %s" % args.contract)
        result = write_stage_review_evidence(root, evidence_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
