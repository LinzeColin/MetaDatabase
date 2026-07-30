"""Fail-closed, offline whole-stage review oracle for ABD S07.

The review binds the four signed S07 phase receipts to the supplied Task Pack
baseline.  It is an evidence review only: it neither accesses an external
service nor enables a recommendation, order, account balance mutation,
deployment, or wall-clock soak.  A PASS makes S07 eligible for the separate
GitHub-delivery run; it does not claim that delivery has happened.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .evidence_continuity import verify_existing_phase_evidence as verify_p04
from .identity_resolution import verify_existing_phase_evidence as verify_p01
from .ledger_trace import verify_existing_phase_evidence as verify_p03
from .temporal_lineage import verify_existing_phase_evidence as verify_p02


CONTRACT_ID = "STAGE-REVIEW-S07"
REVIEW_ID = "ABD-S07-WHOLE-STAGE-REVIEW"
STAGE_ID = "S07"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage7_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S07/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S07_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S07/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S07/STAGE_REVIEW/pytest.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S07/STAGE_REVIEW/signed_state_regression.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S07/STAGE_REVIEW/full_regression.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S07/STAGE_REVIEW/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S07-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-STAGE-REVIEW_rollback.json")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
ORACLE_PATH = Path("abd_acceptance/stage7_review.py")

PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_DECISIONS = {
    "P01": "IDENTITY_GATE_PASSED_DOWNSTREAM_GATES_REQUIRED",
    "P02": "ZERO_FUTURE_INFORMATION_LINEAGE_GATE_PASSED_NO_ADVICE",
    "P03": "IMMUTABLE_ADVICE_AND_DUAL_LEDGER_GATE_PASSED_NO_ADVICE",
    "P04": "CONTINUOUS_EVIDENCE_CHAIN_VERIFIED_NO_ACTION",
}
PHASE_NEXT = {
    "P01": "S07/P02_READY_NOT_STARTED",
    "P02": "S07/P03_READY_NOT_STARTED",
    "P03": "S07/P04_READY_NOT_STARTED",
    "P04": "S07/STAGE_REVIEW_READY_NOT_STARTED",
}
PHASE_TARGETS = {
    "P01": "身份置信度<99.5%时不建议。",
    "P02": "未来信息容忍度=0。",
    "P03": "无成交证据时真实资金账本不变化。",
    "P04": "需求→任务→测试→证据→制品无孤儿。",
}
PHASE_OUTPUTS = {
    "P01": ["identity_resolver.py", "identity_fixtures.json", "identity_registry.json"],
    "P02": ["temporal_lineage.schema.json", "leakage_oracle.py"],
    "P03": ["ledger.py", "ledger.schema.json", "reconciliation_oracle.py"],
    "P04": ["evidence_index.jsonl", "traceability_matrix.json", "artifact_manifest.json"],
}
PHASE_EVIDENCE = {phase: Path("machine/evidence/EVD-S07-%s.json" % phase) for phase in PHASE_VERIFIERS}
PHASE_ROLLBACK = {phase: Path("machine/evidence/EVD-S07-%s_rollback.json" % phase) for phase in PHASE_VERIFIERS}

PINNED_REVIEW_ARTIFACT_HASHES: Dict[str, str] = {
    CONTRACT_PATH.as_posix(): "ee37bd765d9d415e7e3128a14105140d8aaa3fd7c78da5359639cea56f6ff48f",
    FINDINGS_PATH.as_posix(): "1fd1430885e85ab2396cd9ce67c4152b466fbc4c7b9fe5f214503e17b18e5387",
    FIXTURE_PATH.as_posix(): "999d421e07c825b7fdfb9eb0e6415c8b9a475eece763cdea6dfd4ea4384c5b0d",
    TEST_PATH.as_posix(): "24de0726ada5384c60d1f814388c5e49c0c358ebefd93fb7994260b1f022a644",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "a19333941101f5ffbeedebd3282b26035e2a65ee40651a6c5602a48b3770d15d"
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/evidence/roadmap_stage_phase.md": "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "github_upload_performed_by_local_review": False,
    "remote_ci_result_claimed_by_local_review": False,
    "external_network_accessed_for_product_runtime": False,
    "gmail_account_or_api_accessed": False,
    "gmail_mutation_performed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "model_or_strategy_executed": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "secret_provisioned_or_read": False,
    "production_deployed_or_activated": False,
    "real_account_balance_read_or_written": False,
    "real_time_soak_waited": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "incremental_cash_spent_aud": "0.00",
    "owner_final_order_only": True,
}
ROLLBACK_ARTIFACTS = (
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
    *tuple(PHASE_EVIDENCE.values()),
    *tuple(PHASE_ROLLBACK.values()),
)
_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")
_LOCAL_PATH_FRAGMENTS = ("/" + "Users/", "file" + "://")


class Stage7ReviewContractError(ValueError):
    """Raised when the S07 review evidence cannot be trusted."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _portable(path: Path) -> str:
    """Keep serialized evidence independent of the local checkout location."""

    text = path.as_posix()
    for anchor in ("/machine/", "/tests/", "/abd_acceptance/"):
        if anchor in text:
            return anchor.lstrip("/") + text.split(anchor, 1)[1]
    return path.name


def _safe_load(path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, _portable(path))
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage7ReviewContractError("rows are unavailable")
    matched = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matched) != 1:
        raise Stage7ReviewContractError("expected exactly one %s=%s" % (key, identifier))
    return matched[0]


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8")) if normalized != text else "NORMALIZATION_FAILED"


def _current_code_hash(root: Path) -> str:
    return _sha256_bytes(ORACLE_PATH.as_posix().encode("utf-8") + b"\0" + (root / ORACLE_PATH).read_bytes() + b"\0")


def _parse_sums(path: Path) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise Stage7ReviewContractError("invalid SHA256SUMS line %d" % number)
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in rows:
            raise Stage7ReviewContractError("unsafe or duplicate checksum path")
        rows[relative] = digest
    if not rows:
        raise Stage7ReviewContractError("SHA256SUMS is empty")
    return rows


def _expected_project_files(root: Path) -> List[Path]:
    manifest = (root / ARTIFACT_MANIFEST_PATH).resolve()
    sums = (root / SHA256SUMS_PATH).resolve()
    files = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        if any(part in _EXCLUDED_MANIFEST_PARTS for part in relative.parts):
            continue
        if candidate.suffix in {".pyc", ".pyo"} or candidate.name == ".DS_Store":
            continue
        if candidate.resolve() not in {manifest, sums}:
            files.append(candidate)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ElementTree.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise Stage7ReviewContractError("unexpected JUnit root")
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise Stage7ReviewContractError("JUnit has no suites")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.attrib.get(key, "0"))
    return totals


def _junit_is_normalized(path: Path) -> bool:
    try:
        root = ElementTree.parse(path).getroot()
    except Exception:
        return False
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
        for suite in suites
    )


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate the four S07 outcome gates using frozen in-memory data only."""

    if not isinstance(snapshot, Mapping):
        raise Stage7ReviewContractError("review snapshot must be an object")
    confidence = snapshot.get("identity_confidence")
    if not isinstance(confidence, str) or not re.fullmatch(r"\d\.\d{4}", confidence):
        raise Stage7ReviewContractError("identity confidence must be a four-place decimal string")
    try:
        confidence_decimal = Decimal(confidence)
    except InvalidOperation as exc:
        raise Stage7ReviewContractError("identity confidence is invalid") from exc
    tolerance = snapshot.get("future_information_tolerance")
    actual_changed = snapshot.get("actual_funds_changed_without_execution")
    signed = snapshot.get("phase_receipts_signed")
    raw_orphans = snapshot.get("orphans")
    if not isinstance(tolerance, int) or isinstance(tolerance, bool):
        raise Stage7ReviewContractError("future information tolerance must be an integer")
    if not isinstance(actual_changed, bool) or not isinstance(signed, bool) or not isinstance(raw_orphans, Mapping):
        raise Stage7ReviewContractError("review snapshot fields are malformed")
    orphans: Dict[str, List[str]] = {}
    for category, values in raw_orphans.items():
        if not isinstance(category, str) or not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise Stage7ReviewContractError("orphan map must contain string arrays")
        orphans[category] = sorted(set(values))
    reasons: List[str] = []
    if confidence_decimal < Decimal("0.9950"):
        reasons.append("IDENTITY_CONFIDENCE_BELOW_995")
    if tolerance != 0:
        reasons.append("FUTURE_INFORMATION_TOLERANCE_NONZERO")
    if actual_changed:
        reasons.append("ACTUAL_FUNDS_CHANGED_WITHOUT_EXECUTION")
    if not signed:
        reasons.append("UNSIGNED_PHASE_RECEIPT")
    for category in sorted(orphans):
        if orphans[category]:
            reasons.append("CONTINUITY_ORPHANS_PRESENT")
            break
    unsigned = {
        "status": "S07_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S07_STAGE_REVIEW_REJECTED_NO_ACTION",
        "identity_confidence": confidence,
        "future_information_tolerance": tolerance,
        "actual_funds_changed_without_execution": actual_changed,
        "phase_receipts_signed": signed,
        "orphans": orphans,
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
    }
    return dict(unsigned, output_sha256=_sha256_bytes(_json_bytes(unsigned)))


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected_paths = {CONTRACT_PATH.as_posix(), FINDINGS_PATH.as_posix(), FIXTURE_PATH.as_posix(), TEST_PATH.as_posix()}
    _add(checks, "S07REVIEW-PIN-SET-EXACT", set(PINNED_REVIEW_ARTIFACT_HASHES) == expected_paths, sorted(PINNED_REVIEW_ARTIFACT_HASHES))
    for relative in sorted(expected_paths):
        expected = PINNED_REVIEW_ARTIFACT_HASHES.get(relative, "")
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S07REVIEW-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"), expected != "TO_BE_FILLED" and actual == expected, {"expected": expected, "actual": actual})
    actual_self = _structural_self_hash(root)
    _add(checks, "S07REVIEW-ORACLE-STRUCTURAL-HASH", STRUCTURAL_SELF_NORMALIZED_SHA256 != "TO_BE_FILLED" and actual_self == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": actual_self})


def _check_contract_and_findings(contract: Any, findings: Any, fixture: Any, checks: List[Dict[str, Any]]) -> None:
    phases = ["P01", "P02", "P03", "P04"]
    scope = contract.get("review_scope", {}) if isinstance(contract, Mapping) else {}
    identity_ok = (
        isinstance(contract, Mapping)
        and isinstance(findings, Mapping)
        and isinstance(fixture, Mapping)
        and contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and contract.get("fixed_at") == FIXED_CLOCK
        and fixture.get("fixture_id") == "FIX-S07-STAGE-REVIEW"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("review_id") == REVIEW_ID
        and fixture.get("fixed_clock") == FIXED_CLOCK
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_at") == FIXED_CLOCK
    )
    _add(checks, "S07REVIEW-CONTRACT-IDENTITY", identity_ok, {"review": contract.get("review_id") if isinstance(contract, Mapping) else None})
    scope_ok = (
        scope.get("phase_ids") == phases
        and scope.get("requirement_ids") == ["REQ-S07-%s" % phase for phase in phases]
        and scope.get("acceptance_contract_ids") == ["AC-S07-%s" % phase for phase in phases]
        and scope.get("task_ids") == ["T-S07-%s-%02d" % (phase, task) for phase in phases for task in (1, 2, 3)]
    )
    _add(checks, "S07REVIEW-SCOPE-EXACT", scope_ok, scope)
    records = contract.get("phase_records") if isinstance(contract, Mapping) else None
    records_ok = isinstance(records, list) and [row.get("phase_id") for row in records if isinstance(row, Mapping)] == phases
    if records_ok:
        records_ok = all(
            row.get("requirement_id") == "REQ-S07-%s" % phase
            and row.get("acceptance_contract_id") == "AC-S07-%s" % phase
            and row.get("task_ids") == ["T-S07-%s-%02d" % (phase, task) for task in (1, 2, 3)]
            and row.get("required_outputs") == PHASE_OUTPUTS[phase]
            and row.get("expected_next") == PHASE_NEXT[phase]
            and row.get("evidence_path") == PHASE_EVIDENCE[phase].as_posix()
            and row.get("rollback_path") == PHASE_ROLLBACK[phase].as_posix()
            for phase, row in zip(phases, records)
        )
    _add(checks, "S07REVIEW-PHASE-RECORDS-EXACT", records_ok, [row.get("phase_id") for row in records] if isinstance(records, list) else records)
    source_receipts = contract.get("supplied_source_receipts") if isinstance(contract, Mapping) else None
    source_ok = (
        isinstance(source_receipts, list)
        and len(source_receipts) == 2
        and source_receipts[0].get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and source_receipts[1].get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and source_receipts[1].get("original_file_count") == 53
    )
    _add(checks, "S07REVIEW-SUPPLIED-SOURCE-RECEIPTS-EXACT", source_ok, source_receipts)
    finding_rows = findings.get("findings") if isinstance(findings, Mapping) else None
    expected_ids = fixture.get("expected_finding_ids") if isinstance(fixture, Mapping) else None
    findings_ok = (
        isinstance(finding_rows, list)
        and [row.get("id") for row in finding_rows if isinstance(row, Mapping)] == expected_ids
        and all(row.get("status") == "RESOLVED_IN_REVIEW_CANDIDATE" for row in finding_rows if isinstance(row, Mapping))
        and findings.get("summary") == {"total": len(finding_rows), "resolved_in_review_candidate": len(finding_rows), "open": 0, "github_upload_pending_is_not_an_open_code_finding": True}
    )
    _add(checks, "S07REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, findings.get("summary") if isinstance(findings, Mapping) else findings)
    boundary_ok = (
        isinstance(contract, Mapping)
        and contract.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and contract.get("claim_boundary") == {
            "financial_target_verified_or_guaranteed": False,
            "production_deployed_or_activated": False,
            "github_upload_or_remote_ci_verified": False,
            "ovh_7x24_runtime_verified": False,
            "cloudflare_global_chinese_access_verified": False,
            "market_or_account_runtime_access_verified": False,
        }
        and contract.get("release_status_on_pass") == "S07_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and contract.get("next_on_pass") == "S07/GITHUB_STAGE_UPLOAD_READY"
    )
    _add(checks, "S07REVIEW-CLAIM-AND-TERMINAL-BOUNDARY", boundary_ok, contract.get("claim_boundary") if isinstance(contract, Mapping) else None)


def _check_baseline(root: Path, contract: Any, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected = contract.get("baseline_critical_artifacts") if isinstance(contract, Mapping) else None
    if expected != PINNED_BASELINE_HASHES:
        _add(checks, "S07REVIEW-BASELINE-CONTRACT-PINS-EXACT", False, "review contract baseline pins differ")
        return
    _add(checks, "S07REVIEW-BASELINE-CONTRACT-PINS-EXACT", True, len(expected))
    mismatches = []
    for relative, required in sorted(PINNED_BASELINE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        if actual != required:
            mismatches.append({"path": relative, "expected": required, "actual": actual})
    _add(checks, "S07REVIEW-BASELINE-CRITICAL-HASHES", not mismatches, mismatches or "all baseline hashes match")


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S07REVIEW-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S07REVIEW-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S07REVIEW-TASK-GRAPH-STRICT-JSON")
    trace = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S07REVIEW-TRACE-STRICT-JSON")
    phases = ["P01", "P02", "P03", "P04"]
    try:
        task_rows = graph.get("tasks") if isinstance(graph, Mapping) else None
        requirement_rows = [_row(requirements, "REQ-S07-%s" % phase) for phase in phases]
        contract_rows = [_row(contracts, "AC-S07-%s" % phase) for phase in phases]
        selected_tasks = [_row(task_rows, "T-S07-%s-%02d" % (phase, task)) for phase in phases for task in (1, 2, 3)]
        trace_rows = [_row(trace, "REQ-S07-%s" % phase, key="requirement_id") for phase in phases]
        requirements_ok = all(
            row.get("stage_id") == STAGE_ID
            and row.get("phase_id") == phase
            and row.get("scope") == PHASE_OUTPUTS[phase]
            and row.get("target") == PHASE_TARGETS[phase]
            and row.get("primary_acceptance_criteria_id") == "AC-S07-%s" % phase
            for phase, row in zip(phases, requirement_rows)
        )
        contracts_ok = all(
            row.get("requirement_id") == "REQ-S07-%s" % phase
            and row.get("pass_gate") == PHASE_TARGETS[phase]
            and row.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S07-%s --evidence machine/evidence" % phase
            for phase, row in zip(phases, contract_rows)
        )
        task_ok = all(
            row.get("stage_id") == STAGE_ID
            and row.get("requirement_ids") == ["REQ-S07-%s" % row.get("phase_id")]
            and row.get("acceptance_criteria_ids") == ["AC-S07-%s" % row.get("phase_id")]
            for row in selected_tasks
        )
        trace_ok = all(
            row.get("stage_id") == STAGE_ID
            and row.get("phase_id") == phase
            and row.get("acceptance_criteria_id") == "AC-S07-%s" % phase
            and row.get("task_ids") == ["T-S07-%s-%02d" % (phase, task) for task in (1, 2, 3)]
            and row.get("evidence_id") == "EVD-S07-%s" % phase
            for phase, row in zip(phases, trace_rows)
        )
        _add(checks, "S07REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", requirements_ok and contracts_ok and task_ok and trace_ok, {"requirements": requirements_ok, "contracts": contracts_ok, "tasks": task_ok, "traceability": trace_ok})
    except Exception as exc:
        _add(checks, "S07REVIEW-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_phase_receipts(root: Path, contract: Any, fixture: Any, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    records = contract.get("phase_records") if isinstance(contract, Mapping) else None
    if not isinstance(records, list) or not isinstance(fixture, Mapping):
        _add(checks, "S07REVIEW-PHASE-RECEIPTS-AVAILABLE", False, "phase records or fixture unavailable")
        return
    expected_hashes = fixture.get("expected_phase_evidence_sha256", {})
    expected_rollbacks = fixture.get("expected_phase_rollback_sha256", {})
    local_path_leaks = []
    for record in records:
        phase = record.get("phase_id")
        if phase not in PHASE_VERIFIERS:
            _add(checks, "S07REVIEW-PHASE-UNKNOWN", False, record)
            continue
        evidence_path = root / PHASE_EVIDENCE[phase]
        rollback_path = root / PHASE_ROLLBACK[phase]
        evidence_hash = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_hash = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        hash_ok = (
            evidence_hash == record.get("evidence_sha256") == expected_hashes.get(phase)
            and rollback_hash == record.get("rollback_sha256") == expected_rollbacks.get(phase)
        )
        _add(checks, "S07REVIEW-%s-RECEIPT-HASHES" % phase, hash_ok, {"evidence": evidence_hash, "rollback": rollback_hash})
        try:
            signed = strict_json_load(evidence_path)
            result = PHASE_VERIFIERS[phase](root, verify_git_history=verify_git_history)
            receipt_ok = (
                result.get("status") == "PASS"
                and result.get("next") == PHASE_NEXT[phase]
                and signed.get("status") == "PASS"
                and signed.get("decision") == PHASE_DECISIONS[phase]
                and signed.get("next") == PHASE_NEXT[phase]
                and signed.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
                and signed.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            )
            detail: Any = {"verifier_status": result.get("status"), "decision": signed.get("decision"), "next": result.get("next")}
        except Exception as exc:
            receipt_ok = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S07REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, receipt_ok, detail)
        for label, path in (("evidence", evidence_path), ("rollback", rollback_path)):
            try:
                raw = path.read_text(encoding="utf-8")
                if any(fragment in raw for fragment in _LOCAL_PATH_FRAGMENTS):
                    local_path_leaks.append({"phase": phase, "artifact": label})
            except Exception as exc:
                local_path_leaks.append({"phase": phase, "artifact": label, "error": type(exc).__name__})
    _add(checks, "S07REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS", not local_path_leaks, local_path_leaks or "none")


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    cases = fixture.get("cases") if isinstance(fixture, Mapping) else None
    if not isinstance(cases, list):
        _add(checks, "S07REVIEW-SNAPSHOT-CASES-AVAILABLE", False, "cases unavailable")
        return results
    try:
        for row in cases:
            if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("snapshot"), Mapping) or not isinstance(row.get("expected"), Mapping):
                raise Stage7ReviewContractError("malformed review case")
            result = evaluate_stage_snapshot(row["snapshot"])
            results[row["case_id"]] = result
            expected = row["expected"]
            case_ok = (
                result.get("status") == expected.get("status")
                and result.get("reason_codes") == expected.get("reason_codes")
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_network_used") is False
                and result.get("real_time_soak_waited") is False
            )
            _add(checks, "S07REVIEW-CASE-%s" % row["case_id"], case_ok, result)
        positive = results.get("POSITIVE_EXACT_STAGE")
        _add(checks, "S07REVIEW-POSITIVE-OUTPUT-HASH-PIN", positive is not None and positive.get("output_sha256") == fixture.get("expected_positive_output_sha256"), positive.get("output_sha256") if positive else "MISSING")
        positive_snapshot = next(row["snapshot"] for row in cases if row["case_id"] == "POSITIVE_EXACT_STAGE")
        replay_hashes = {evaluate_stage_snapshot(positive_snapshot)["output_sha256"] for _ in range(fixture["replay_iterations"])}
        _add(checks, "S07REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", replay_hashes == {fixture.get("expected_positive_output_sha256")}, {"count": fixture["replay_iterations"], "hashes": sorted(replay_hashes)})
        adverse_reasons = set()
        no_action = True
        for index in range(fixture["adverse_perturbation_iterations"]):
            snapshot = dict(positive_snapshot)
            snapshot["orphans"] = {key: list(value) for key, value in positive_snapshot["orphans"].items()}
            selector = index % 5
            if selector == 0:
                snapshot["identity_confidence"] = "0.9949"
            elif selector == 1:
                snapshot["future_information_tolerance"] = 1
            elif selector == 2:
                snapshot["actual_funds_changed_without_execution"] = True
            elif selector == 3:
                snapshot["orphans"]["evidence"].append("ADVERSE-%05d" % index)
            else:
                snapshot["phase_receipts_signed"] = False
            result = evaluate_stage_snapshot(snapshot)
            adverse_reasons.update(result["reason_codes"])
            no_action = no_action and result["status"] == "S07_STAGE_REVIEW_REJECTED_NO_ACTION" and result["recommendation_generated"] is False and result["order_submission_enabled"] is False and result["real_time_soak_waited"] is False
        _add(checks, "S07REVIEW-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ACTION", no_action and adverse_reasons == {"IDENTITY_CONFIDENCE_BELOW_995", "FUTURE_INFORMATION_TOLERANCE_NONZERO", "ACTUAL_FUNDS_CHANGED_WITHOUT_EXECUTION", "CONTINUITY_ORPHANS_PRESENT", "UNSIGNED_PHASE_RECEIPT"}, {"count": fixture["adverse_perturbation_iterations"], "reason_codes": sorted(adverse_reasons)})
    except Exception as exc:
        _add(checks, "S07REVIEW-SNAPSHOT-CASES-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))
    return results


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=ORACLE_PATH.as_posix())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        denied = sorted(imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"})
        forbidden = [token for token in ("sleep" + "(", "requests" + ".", "urllib" + ".", "socket" + ".", "subprocess" + ".", "http" + "://", "https" + "://") if token in source]
        _add(checks, "S07REVIEW-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY", not denied and not forbidden, {"imports": sorted(imports), "denied": denied, "tokens": forbidden})
    except Exception as exc:
        _add(checks, "S07REVIEW-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_manifest(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    manifest = _safe_load(root / ARTIFACT_MANIFEST_PATH, checks, "S07REVIEW-ARTIFACT-MANIFEST-STRICT-JSON")
    try:
        sums = _parse_sums(root / SHA256SUMS_PATH)
        _add(checks, "S07REVIEW-SHA256SUMS-STRICT", True, SHA256SUMS_PATH.as_posix())
    except Exception as exc:
        sums = {}
        _add(checks, "S07REVIEW-SHA256SUMS-STRICT", False, "%s: %s" % (type(exc).__name__, exc))
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("files"), list):
        _add(checks, "S07REVIEW-ARTIFACT-MANIFEST-COVERAGE", False, "manifest files unavailable")
        return
    try:
        rows = manifest["files"]
        paths: Dict[str, Mapping[str, Any]] = {}
        errors = []
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
                raise Stage7ReviewContractError("manifest row is malformed")
            relative = row["path"]
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts or relative in paths:
                raise Stage7ReviewContractError("manifest path is unsafe or duplicate")
            paths[relative] = row
            file_path = root / candidate
            actual = sha256_file(file_path) if file_path.is_file() else "MISSING"
            if row.get("sha256") != actual or row.get("bytes") != (file_path.stat().st_size if file_path.is_file() else None) or sums.get(relative) != actual:
                errors.append({"path": relative, "actual": actual})
        expected_paths = {path.relative_to(root).as_posix() for path in _expected_project_files(root)}
        required = {CONTRACT_PATH.as_posix(), FINDINGS_PATH.as_posix(), FIXTURE_PATH.as_posix(), TEST_PATH.as_posix(), ORACLE_PATH.as_posix()}
        if require_test_reports:
            required.update({JUNIT_PATH.as_posix(), SIGNED_STATE_JUNIT_PATH.as_posix(), FULL_JUNIT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()})
        coverage_ok = (
            manifest.get("schema_version") == "1.0.0"
            and manifest.get("version") == VERSION
            and manifest.get("file_count") == len(rows) == len(expected_paths)
            and [row.get("path") for row in rows] == sorted(paths)
            and set(paths) == expected_paths
            and set(sums) == expected_paths | {ARTIFACT_MANIFEST_PATH.as_posix()}
            and sums.get(ARTIFACT_MANIFEST_PATH.as_posix()) == sha256_file(root / ARTIFACT_MANIFEST_PATH)
            and required <= set(paths)
            and not errors
        )
        _add(checks, "S07REVIEW-ARTIFACT-MANIFEST-COVERAGE", coverage_ok, {"manifest_files": len(rows), "expected_files": len(expected_paths), "missing_required": sorted(required - set(paths)), "errors": errors})
    except Exception as exc:
        _add(checks, "S07REVIEW-ARTIFACT-MANIFEST-COVERAGE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Any, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S07REVIEW-REPORTS-DEFERRED-FOR-CANDIDATE", True, "candidate mode does not require generated reports")
        return
    for relative, minimum, identifier in (
        (JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else 0, "S07REVIEW-TARGETED-PYTEST-REPORT"),
        (SIGNED_STATE_JUNIT_PATH, fixture.get("minimum_signed_state_pytest_cases") if isinstance(fixture, Mapping) else 0, "S07REVIEW-SIGNED-STATE-PYTEST-REPORT"),
        (FULL_JUNIT_PATH, fixture.get("minimum_full_pytest_cases") if isinstance(fixture, Mapping) else 0, "S07REVIEW-FULL-PYTEST-REPORT"),
    ):
        try:
            summary = _junit_summary(root / relative)
            ok = isinstance(minimum, int) and minimum > 0 and summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, identifier, ok, {"summary": summary, "minimum": minimum})
        except Exception as exc:
            _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in report and "MAX_INCREMENTAL_CASH_AUD: 0.00" in report and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in report and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in report
        _add(checks, "S07REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S07REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(root: Path, require_test_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_pins(root, checks, hashes)
    contract = _safe_load(root / CONTRACT_PATH, checks, "S07REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root / FINDINGS_PATH, checks, "S07REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S07REVIEW-FIXTURE-STRICT-JSON")
    _check_contract_and_findings(contract, findings, fixture, checks)
    _check_baseline(root, contract, checks, hashes)
    _check_taskpack(root, checks)
    _check_phase_receipts(root, contract, fixture, checks, verify_git_history=_verify_git_history)
    case_results = _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_manifest(root, checks, require_test_reports=require_test_reports)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    positive = case_results.get("POSITIVE_EXACT_STAGE", {})
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "stage_status": "S07_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S07_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S07_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S07_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED",
        "release_status": "S07_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "stage_snapshot_summary": {"positive_status": positive.get("status"), "positive_output_sha256": positive.get("output_sha256"), "real_time_waited": False},
        "external_network_used_by_verifier": False,
        "next": "S07/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S07/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_test_reports=False, _verify_git_history=verify_git_history)
    return {"status": result["status"], "decision": "S07_STAGE_REVIEW_CANDIDATE_VALID" if result["status"] == "PASS" else "S07_STAGE_REVIEW_CANDIDATE_INVALID", "summary": result["summary"], "next": result["next"]}


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {}
    for relative in ROLLBACK_ARTIFACTS:
        path = root / relative
        artifacts[relative.as_posix()] = {"status": "PASS" if path.is_file() else "FAIL", "sha256": sha256_file(path) if path.is_file() else "MISSING"}
    status = "PASS" if artifacts and all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_STAGE_REVIEW_RELEASE_CANDIDATE_KEEP_SIGNED_PHASE_RECEIPTS_AND_REPLAY_OFFLINE",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH, *PHASE_EVIDENCE.values(), *PHASE_ROLLBACK.values(), *[Path(key) for key in PINNED_BASELINE_HASHES]]
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def build_evidence(root: Path, require_test_reports: bool = False, *, _verify_git_history: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    fixture = strict_json_load(root / FIXTURE_PATH)
    positive = next(row for row in fixture["cases"] if row["case_id"] == "POSITIVE_EXACT_STAGE")
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "validation": validation,
        "phase_receipts": {phase: {"evidence_path": PHASE_EVIDENCE[phase].as_posix(), "evidence_sha256": sha256_file(root / PHASE_EVIDENCE[phase]), "rollback_path": PHASE_ROLLBACK[phase].as_posix(), "rollback_sha256": sha256_file(root / PHASE_ROLLBACK[phase])} for phase in PHASE_VERIFIERS},
        "stage_snapshot": evaluate_stage_snapshot(positive["snapshot"]),
        "deterministic_replay": {"replay_iterations": fixture["replay_iterations"], "adverse_perturbation_iterations": fixture["adverse_perturbation_iterations"], "real_time_wait_performed": False},
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S07_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S07/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S07/stage_review_test.py --junitxml=machine/evidence/S07/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S07/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S07/P01_test.py tests/S07/P02_test.py tests/S07/P03_test.py tests/S07/P04_test.py tests/S07/stage_review_test.py --junitxml=machine/evidence/S07/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S07/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S07/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S07/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance.stage7_review --contract STAGE-REVIEW-S07 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {"inputs": _input_hashes(root), "code": _current_code_hash(root), "parameters": sha256_file(root / "machine/facts/parameters.json"), "model": sha256_file(root / "machine/facts/model_system_card.json"), "model_not_executed_reason": "S07 stage review validates frozen evidence gates only.", "rollback_evidence": _sha256_bytes(_json_bytes(rollback))},
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    expected = (root / "machine/evidence").resolve()
    if evidence_dir.resolve() != expected:
        raise Stage7ReviewContractError("S07 review evidence must be written to machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    return {"contract_id": CONTRACT_ID, "status": evidence["status"], "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": evidence["next"]}


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = dict(evidence)
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_stage_review_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S07REVIEW-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S07REVIEW-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S07-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S07/GITHUB_STAGE_UPLOAD_READY"
            and evidence.get("release_status") == "S07_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S07REVIEW-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        errors = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            actual = sha256_file(root / candidate) if not candidate.is_absolute() and ".." not in candidate.parts and (root / candidate).is_file() else "MISSING_OR_UNSAFE"
            if actual != expected:
                errors.append({"path": relative, "actual": actual})
        _add(checks, "S07REVIEW-EXISTING-INPUT-HASHES", not errors, errors or "all inputs match")
        _add(checks, "S07REVIEW-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S07REVIEW-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S07-STAGE-REVIEW-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_account_balance_read_or_written") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S07REVIEW-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S07REVIEW-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_test_reports=True, _verify_git_history=verify_git_history)
    _add(checks, "S07REVIEW-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    return {"contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING", "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed}, "next": "S07/GITHUB_STAGE_UPLOAD_READY" if not failed else "S07/STAGE_REVIEW_REMEDIATION_REQUIRED"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write or verify ABD S07 whole-stage review evidence")
    parser.add_argument("--contract", default=CONTRACT_ID)
    parser.add_argument("--evidence", type=Path, default=Path("machine/evidence"))
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args(argv)
    if args.contract != CONTRACT_ID:
        parser.error("only %s is supported" % CONTRACT_ID)
    root = Path(__file__).resolve().parents[1]
    result = verify_existing_stage_review_evidence(root) if args.verify_existing else write_stage_review_evidence(root, root / args.evidence)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_PATH",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINDINGS_PATH",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_PATH",
    "ORACLE_PATH",
    "PHASE_NEXT",
    "PHASE_VERIFIERS",
    "PINNED_BASELINE_HASHES",
    "PINNED_REVIEW_ARTIFACT_HASHES",
    "REVIEW_ID",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "SIGNED_STATE_JUNIT_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "TEST_PATH",
    "Stage7ReviewContractError",
    "_current_code_hash",
    "_junit_is_normalized",
    "_junit_summary",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "evaluate_stage_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage_review_evidence",
]
