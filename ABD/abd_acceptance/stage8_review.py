"""Fail-closed, offline whole-stage review for ABD S08.

The review validates frozen evidence and deterministic gates only.  It does
not access live markets, accounts, mail, infrastructure, or the network.
"""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .devig import verify_existing_phase_evidence as verify_p01
from .legacy_receipt_compatibility import COMPATIBILITY_ID, MANIFEST_PATH as LEGACY_COMPATIBILITY_PATH
from .legacy_receipt_compatibility import PINNED_MANIFEST_SHA256, approved_successor_sha256
from .source_independence import verify_existing_phase_evidence as verify_p02
from .market_consensus import verify_existing_phase_evidence as verify_p03
from .outlier_line_movement import verify_existing_phase_evidence as verify_p04


CONTRACT_ID = "STAGE-REVIEW-S08"
REVIEW_ID = "ABD-S08-WHOLE-STAGE-REVIEW"
STAGE_ID = "S08"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage8_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S08/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S08_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S08/stage_review_test.py")
LEGACY_COMPATIBILITY_HELPER_PATH = Path("abd_acceptance/legacy_receipt_compatibility.py")
JUNIT_PATH = Path("machine/evidence/S08/STAGE_REVIEW/pytest.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S08/STAGE_REVIEW/signed_state_regression.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S08/STAGE_REVIEW/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S08-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-STAGE-REVIEW_rollback.json")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
ORACLE_PATH = Path("abd_acceptance/stage8_review.py")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
REPOSITORY_FAST_WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}
PHASE_DECISIONS = {
    "P01": "MARKET_PRIOR_DEVIG_READY_DOWNSTREAM_GATES_REQUIRED",
    "P02": "SOURCE_INDEPENDENCE_WEIGHTING_READY_DOWNSTREAM_GATES_REQUIRED",
    "P03": "MARKET_CONSENSUS_READY_OUTLIER_GATE_REQUIRED",
    "P04": "OUTLIER_AND_LINE_MOVEMENT_GATES_READY_STAGE_REVIEW_REQUIRED",
}
PHASE_NEXT = {
    "P01": "S08/P02_READY_NOT_STARTED",
    "P02": "S08/P03_READY_NOT_STARTED",
    "P03": "S08/P04_READY_NOT_STARTED",
    "P04": "S08/STAGE_REVIEW_READY_NOT_STARTED",
}
PHASE_TARGETS = {
    "P01": "完整盘口概率和=1±1e-9，四种方法可重放。",
    "P02": "同源复制不得被错误计为多条独立证据。",
    "P03": "增加复制来源不改变共识；结果跨实现一致。",
    "P04": "单一异常长赔率不能制造建议。",
}
PHASE_OUTPUTS = {
    "P01": ["devig.py", "devig_vectors.json", "devig_report.json"],
    "P02": ["source_independence.py", "source_clusters.json"],
    "P03": ["market_consensus.py", "consensus_vectors.json"],
    "P04": ["outlier_detector.py", "line_movement.py", "outlier_fixtures.json"],
}
PHASE_EVIDENCE = {phase: Path("machine/evidence/EVD-S08-%s.json" % phase) for phase in PHASE_VERIFIERS}
PHASE_ROLLBACK = {phase: Path("machine/evidence/EVD-S08-%s_rollback.json" % phase) for phase in PHASE_VERIFIERS}
PHASE_SHARED_RUNTIME_EXCLUSIONS = {
    "P01": ["abd_acceptance/__main__.py", "abd_acceptance/__init__.py"],
    "P02": ["abd_acceptance/__main__.py", "abd_acceptance/__init__.py"],
    "P03": ["abd_acceptance/__main__.py", "abd_acceptance/budget.py"],
    "P04": ["abd_acceptance/__main__.py", "abd_acceptance/budget.py"],
}

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
PINNED_REVIEW_ARTIFACT_HASHES: Dict[str, str] = {
    CONTRACT_PATH.as_posix(): "25f814d65418295a8eee9024c8b41f4f023e13c517c370e8172bacbdea907966",
    FINDINGS_PATH.as_posix(): "f97754d251cdeb41df3cf901dae519e8a5af000ab8f55802c3a9f6cfaf7c6811",
    FIXTURE_PATH.as_posix(): "fb0ad14b7a3c266dc30e2e0964fc72b69bbe3c6c3dc814d517a8e07a9ac2f9db",
    TEST_PATH.as_posix(): "a343f5cdb4ceb015292f8f8d55ef5c816dcec7aaf37937b7b2d8f17bbe511f51",
    LEGACY_COMPATIBILITY_PATH.as_posix(): "3b422243e4b85987abcb8a8bc04dbfdb5b8bc7484ac38423e3948e775c9c461e",
    LEGACY_COMPATIBILITY_HELPER_PATH.as_posix(): "978b7ac7f6f4047ba073f3217c332ce44cbf078ff0ca2d0d8bf5ae03f043878b",
}
REPOSITORY_CI_CONTRACT = {
    "fast_workflow_path": REPOSITORY_FAST_WORKFLOW_PATH.as_posix(),
    "fast_workflow_sha256": "2a71e5df499247259e8c8b86a3de55b6aa3b810207d37972bfa1a554723c7e72",
    "fast_gate_timeout_minutes": 15,
    "targeted_test_nodes": [
        "tests/S00/stage_review_test.py::test_baseline_whole_stage_review_passes_without_generated_stage_reports",
        "tests/S00/stage_review_test.py::test_abd_ci_workflow_mutations_fail_closed",
        "tests/S00/stage_review_test.py::test_abd_fast_targeted_workflow_mutations_fail_closed",
        "tests/S08/stage_review_test.py",
    ],
    "full_regression_or_real_time_soak_allowed": False,
    "real_time_soak_waited": False,
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
    LEGACY_COMPATIBILITY_PATH,
    LEGACY_COMPATIBILITY_HELPER_PATH,
    ORACLE_PATH,
    *tuple(PHASE_EVIDENCE.values()),
    *tuple(PHASE_ROLLBACK.values()),
)
_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")


class Stage8ReviewError(ValueError):
    """Raised when the S08 review contract cannot be trusted."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _portable(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise Stage8ReviewError("path is outside the ABD root") from exc


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        portable = _portable(root, path)
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, portable)
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise Stage8ReviewError("blank JSONL row %d" % number)
        row = json.loads(line)
        if not isinstance(row, dict):
            raise Stage8ReviewError("JSONL row %d is not an object" % number)
        rows.append(row)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage8ReviewError("rows are unavailable")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matching) != 1:
        raise Stage8ReviewError("expected exactly one %s=%s" % (key, identifier))
    return matching[0]


def _parse_sums(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise Stage8ReviewError("invalid SHA256SUMS line %d" % number)
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in parsed:
            raise Stage8ReviewError("unsafe or duplicate checksum path")
        parsed[relative] = digest
    if not parsed:
        raise Stage8ReviewError("SHA256SUMS is empty")
    return parsed


def _expected_project_files(root: Path) -> List[Path]:
    excluded = {(root / ARTIFACT_MANIFEST_PATH).resolve(), (root / SHA256SUMS_PATH).resolve()}
    files = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        if any(part in _EXCLUDED_MANIFEST_PARTS for part in relative.parts):
            continue
        if candidate.suffix in {".pyc", ".pyo"} or candidate.name == ".DS_Store" or candidate.resolve() in excluded:
            continue
        files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    if document.tag not in {"testsuite", "testsuites"}:
        raise Stage8ReviewError("unexpected JUnit root")
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise Stage8ReviewError("JUnit has no suites")
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in result:
            result[key] += int(suite.attrib.get(key, "0"))
    return result


def _junit_is_normalized(path: Path) -> bool:
    try:
        document = ElementTree.parse(path).getroot()
    except Exception:
        return False
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
        for suite in suites
    )


def evaluate_stage_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate the whole-stage gates using frozen in-memory booleans only."""

    if not isinstance(snapshot, Mapping):
        raise Stage8ReviewError("stage snapshot must be an object")
    bool_keys = (
        "probability_sum_within_tolerance",
        "replicated_sources_do_not_change_consensus",
        "single_long_odds_blocked",
        "fresh_confirmed_line_only",
        "stale_or_desynchronized_blocks",
        "signed_receipts_current",
        "portable_evidence",
    )
    for key in bool_keys:
        if not isinstance(snapshot.get(key), bool):
            raise Stage8ReviewError("%s must be a boolean" % key)
    open_findings = snapshot.get("findings_open")
    if not isinstance(open_findings, int) or isinstance(open_findings, bool) or open_findings < 0:
        raise Stage8ReviewError("findings_open must be a non-negative integer")
    reasons = []
    rules = (
        ("probability_sum_within_tolerance", "PROBABILITY_SUM_GATE_FAILED"),
        ("replicated_sources_do_not_change_consensus", "SOURCE_INDEPENDENCE_GATE_FAILED"),
        ("single_long_odds_blocked", "SINGLE_LONG_ODDS_NOT_BLOCKED"),
        ("fresh_confirmed_line_only", "UNCONFIRMED_OR_UNFRESH_LINE_ALLOWED"),
        ("stale_or_desynchronized_blocks", "STALE_OR_DESYNCHRONIZED_QUOTE_ALLOWED"),
        ("signed_receipts_current", "SIGNED_RECEIPT_NOT_CURRENT"),
        ("portable_evidence", "EVIDENCE_NOT_PORTABLE"),
    )
    for key, reason in rules:
        if snapshot[key] is not True:
            reasons.append(reason)
    if open_findings != 0:
        reasons.append("OPEN_REVIEW_FINDINGS")
    status = "S08_STAGE_REVIEW_VERIFIED_NO_ACTION" if not reasons else "S08_STAGE_REVIEW_REJECTED_NO_ACTION"
    payload = {key: snapshot[key] for key in (*bool_keys, "findings_open")}
    return {
        "status": status,
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "output_sha256": _sha256_bytes(_json_bytes(payload)),
    }


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_REVIEW_ARTIFACT_HASHES.items():
        identifier = "S08REVIEW-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-")
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(checks, identifier, actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))


def _check_contract_and_findings(contract: Any, findings: Any, fixture: Any, checks: List[Dict[str, Any]]) -> None:
    identity_ok = (
        isinstance(contract, Mapping)
        and contract.get("review_id") == REVIEW_ID
        and contract.get("stage_id") == STAGE_ID
        and contract.get("product_version") == VERSION
        and contract.get("fixed_at") == FIXED_CLOCK
        and isinstance(fixture, Mapping)
        and fixture.get("fixture_id") == "FIX-S08-STAGE-REVIEW"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("review_id") == REVIEW_ID
        and fixture.get("fixed_clock") == FIXED_CLOCK
        and isinstance(findings, Mapping)
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_at") == FIXED_CLOCK
    )
    _add(checks, "S08REVIEW-CONTRACT-IDENTITY", identity_ok, REVIEW_ID)
    records = contract.get("phase_records") if isinstance(contract, Mapping) else None
    phase_records_ok = isinstance(records, list) and isinstance(fixture, Mapping) and [row.get("phase_id") for row in records if isinstance(row, Mapping)] == fixture.get("expected_phase_ids")
    if phase_records_ok:
        for record in records:
            phase = record["phase_id"]
            phase_records_ok = phase_records_ok and (
                record.get("requirement_id") == "REQ-S08-%s" % phase
                and record.get("acceptance_contract_id") == "AC-S08-%s" % phase
                and record.get("required_outputs") == PHASE_OUTPUTS[phase]
                and record.get("expected_next") == PHASE_NEXT[phase]
                and record.get("evidence_path") == PHASE_EVIDENCE[phase].as_posix()
                and record.get("rollback_path") == PHASE_ROLLBACK[phase].as_posix()
                and record.get("evidence_sha256") == fixture["expected_phase_evidence_sha256"][phase]
                and record.get("rollback_sha256") == fixture["expected_phase_rollback_sha256"][phase]
                and record.get("pre_review_evidence_sha256") == fixture["pre_review_receipt_sha256"][phase]
                and isinstance(record.get("implementation_commit"), str)
                and len(record["implementation_commit"]) == 40
            )
    _add(checks, "S08REVIEW-PHASE-RECORDS-EXACT", phase_records_ok, [row.get("phase_id") for row in records] if isinstance(records, list) else records)
    finding_rows = findings.get("findings") if isinstance(findings, Mapping) else None
    findings_ok = (
        isinstance(finding_rows, list)
        and len(finding_rows) == 3
        and findings.get("summary") == fixture.get("expected_findings_summary") if isinstance(fixture, Mapping) else False
    )
    if findings_ok:
        finding = _row(finding_rows, "S08-REVIEW-001")
        compatibility_finding = _row(finding_rows, "S08-REVIEW-002")
        ci_finding = _row(finding_rows, "S08-REVIEW-003")
        findings_ok = (
            isinstance(finding, Mapping)
            and finding.get("id") == "S08-REVIEW-001"
            and finding.get("status") == "RESOLVED_IN_STAGE_REVIEW"
            and finding.get("affected_phases") == ["P01", "P02", "P03", "P04"]
            and finding.get("old_to_new_receipt_sha256") == {
                phase: {"old": fixture["pre_review_receipt_sha256"][phase], "new": fixture["expected_phase_evidence_sha256"][phase]}
                for phase in fixture["expected_phase_ids"]
            }
            and finding.get("external_state_changed") is False
            and finding.get("incremental_cash_spent_aud") == "0.00"
            and finding.get("real_time_soak_waited") is False
            and isinstance(compatibility_finding, Mapping)
            and compatibility_finding.get("status") == "RESOLVED_IN_STAGE_REVIEW"
            and compatibility_finding.get("affected_contract_ids") == fixture.get("legacy_receipt_compatibility", {}).get("contract_ids")
            and compatibility_finding.get("external_state_changed") is False
            and compatibility_finding.get("incremental_cash_spent_aud") == "0.00"
            and compatibility_finding.get("real_time_soak_waited") is False
            and isinstance(ci_finding, Mapping)
            and ci_finding.get("status") == "RESOLVED_IN_STAGE_REVIEW"
            and ci_finding.get("affected_paths") == [REPOSITORY_FAST_WORKFLOW_PATH.as_posix()]
            and ci_finding.get("fast_gate_timeout_minutes") == 15
            and ci_finding.get("full_regression_or_real_time_soak_allowed") is False
            and ci_finding.get("external_state_changed") is False
            and ci_finding.get("incremental_cash_spent_aud") == "0.00"
            and ci_finding.get("real_time_soak_waited") is False
        )
    _add(checks, "S08REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, findings.get("summary") if isinstance(findings, Mapping) else findings)
    terminal_ok = (
        isinstance(contract, Mapping)
        and contract.get("review_findings_path") == FINDINGS_PATH.as_posix()
        and contract.get("next_on_pass") == "S08/GITHUB_STAGE_UPLOAD_READY"
        and contract.get("release_status_on_pass") == "S08_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
        and contract.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and contract.get("repository_ci_contract") == REPOSITORY_CI_CONTRACT
        and "REPOSITORY_CI_FAST_TARGETED_GATE_CONTRACT_EXACT" in contract.get("review_gates", [])
    )
    _add(checks, "S08REVIEW-TERMINAL-STATE-EXACT", terminal_ok, contract.get("next_on_pass") if isinstance(contract, Mapping) else contract)


def _check_baseline(root: Path, contract: Any, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    if not isinstance(contract, Mapping) or contract.get("baseline_critical_artifacts") != PINNED_BASELINE_HASHES:
        _add(checks, "S08REVIEW-BASELINE-CONTRACT-PINS-EXACT", False, "review contract baseline pins differ")
        return
    _add(checks, "S08REVIEW-BASELINE-CONTRACT-PINS-EXACT", True, len(PINNED_BASELINE_HASHES))
    for relative, expected in PINNED_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(checks, "S08REVIEW-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})
        except Exception as exc:
            _add(checks, "S08REVIEW-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))


def _repository_ci_hashes(root: Path) -> Dict[str, str]:
    repo_root = root.parent
    return {
        relative.as_posix(): sha256_file(repo_root / relative)
        for relative in (REPOSITORY_FAST_WORKFLOW_PATH,)
    }


def _check_repository_ci_contract(root: Path, contract: Any, checks: List[Dict[str, Any]]) -> None:
    contract_ok = isinstance(contract, Mapping) and contract.get("repository_ci_contract") == REPOSITORY_CI_CONTRACT
    _add(checks, "S08REVIEW-REPOSITORY-CI-CONTRACT-EXACT", contract_ok, contract.get("repository_ci_contract") if isinstance(contract, Mapping) else contract)
    try:
        hashes = _repository_ci_hashes(root)
    except Exception as exc:
        _add(checks, "S08REVIEW-REPOSITORY-CI-HASHES", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S08REVIEW-REPOSITORY-CI-FAST-TARGETED-GATE", False, "workflow unavailable")
        return
    hash_ok = hashes.get(REPOSITORY_FAST_WORKFLOW_PATH.as_posix()) == REPOSITORY_CI_CONTRACT["fast_workflow_sha256"]
    _add(checks, "S08REVIEW-REPOSITORY-CI-HASHES", hash_ok, hashes)
    try:
        fast_text = (root.parent / REPOSITORY_FAST_WORKFLOW_PATH).read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S08REVIEW-REPOSITORY-CI-FAST-TARGETED-GATE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    targeted_nodes = REPOSITORY_CI_CONTRACT["targeted_test_nodes"]
    targeted_command = re.search(
        r"python -m pytest -q\s+tests/S00/stage_review_test\.py::test_baseline_whole_stage_review_passes_without_generated_stage_reports\s+tests/S00/stage_review_test\.py::test_abd_ci_workflow_mutations_fail_closed\s+tests/S00/stage_review_test\.py::test_abd_fast_targeted_workflow_mutations_fail_closed\s+tests/S08/stage_review_test\.py",
        fast_text,
    )
    semantic_ok = (
        "timeout-minutes: 15" in fast_text
        and "pull_request:" in fast_text
        and "workflow_dispatch:" in fast_text
        and "branches: [main, \"codex/abd-**\"]" in fast_text
        and all(node in fast_text for node in targeted_nodes)
        and fast_text.count("python -m pytest -q") == 1
        and targeted_command is not None
        and "abd-full-regression" not in fast_text
        and "if: ${{ false }}" not in fast_text
        and "continue-on-error: true" not in fast_text
        and ("$" + "{{ secrets.") not in fast_text
        and "sleep " not in fast_text
    )
    _add(
        checks,
        "S08REVIEW-REPOSITORY-CI-FAST-TARGETED-GATE",
        semantic_ok,
        {"targeted_nodes": targeted_nodes, "targeted_command": bool(targeted_command)},
    )


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S08REVIEW-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S08REVIEW-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S08REVIEW-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(graph, Mapping) or not isinstance(graph.get("tasks"), list):
        _add(checks, "S08REVIEW-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    phase_ok = True
    task_ids = []
    for phase in PHASE_VERIFIERS:
        try:
            requirement = _row(requirements, "REQ-S08-%s" % phase)
            acceptance = _row(contracts, "AC-S08-%s" % phase)
            tasks = [row for row in graph["tasks"] if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == phase]
            phase_task_ids = [row.get("id") for row in tasks]
            task_ids.extend(phase_task_ids)
            phase_ok = phase_ok and (
                requirement.get("stage_id") == STAGE_ID
                and requirement.get("phase_id") == phase
                and requirement.get("scope") == PHASE_OUTPUTS[phase]
                and requirement.get("target") == PHASE_TARGETS[phase]
                and requirement.get("primary_acceptance_criteria_id") == "AC-S08-%s" % phase
                and acceptance.get("requirement_id") == "REQ-S08-%s" % phase
                and acceptance.get("pass_gate") == PHASE_TARGETS[phase]
                and acceptance.get("oracle", {}).get("rule") == PHASE_TARGETS[phase]
                and len(tasks) == 3
                and all(
                    task.get("requirement_ids") == ["REQ-S08-%s" % phase]
                    and task.get("acceptance_criteria_ids") == ["AC-S08-%s" % phase]
                    and task.get("oracle", {}).get("expected") == PHASE_TARGETS[phase]
                    and task.get("pass_gate") == PHASE_TARGETS[phase]
                    for task in tasks
                )
            )
        except Exception:
            phase_ok = False
    _add(checks, "S08REVIEW-TASKPACK-EXACT", phase_ok and task_ids == ["T-S08-P01-01", "T-S08-P01-02", "T-S08-P01-03", "T-S08-P02-01", "T-S08-P02-02", "T-S08-P02-03", "T-S08-P03-01", "T-S08-P03-02", "T-S08-P03-03", "T-S08-P04-01", "T-S08-P04-02", "T-S08-P04-03"], task_ids)


def _is_portable(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "/" + "Users/" not in serialized and "file" + "://" not in serialized


def _check_phase_receipts(root: Path, contract: Any, fixture: Any, checks: List[Dict[str, Any]]) -> None:
    records = contract.get("phase_records") if isinstance(contract, Mapping) else None
    if not isinstance(records, list) or not isinstance(fixture, Mapping):
        _add(checks, "S08REVIEW-PHASE-RECEIPTS-AVAILABLE", False, "phase records unavailable")
        return
    record_by_phase = {row.get("phase_id"): row for row in records if isinstance(row, Mapping)}
    _add(checks, "S08REVIEW-PHASE-RECEIPTS-AVAILABLE", set(record_by_phase) == set(PHASE_VERIFIERS), sorted(record_by_phase))
    try:
        index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception as exc:
        index_rows = []
        _add(checks, "S08REVIEW-EVIDENCE-INDEX-STRICT-JSON", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S08REVIEW-EVIDENCE-INDEX-STRICT-JSON", True, EVIDENCE_INDEX_PATH.as_posix())
    no_local_paths = True
    external_boundary_ok = True
    shared_runtime_ok = True
    for phase, verifier in PHASE_VERIFIERS.items():
        record = record_by_phase.get(phase, {})
        evidence_path = root / PHASE_EVIDENCE[phase]
        rollback_path = root / PHASE_ROLLBACK[phase]
        evidence = _safe_load(root, evidence_path, checks, "S08REVIEW-%s-EVIDENCE-STRICT-JSON" % phase)
        rollback = _safe_load(root, rollback_path, checks, "S08REVIEW-%s-ROLLBACK-STRICT-JSON" % phase)
        try:
            result = verifier(root)
            verifier_ok = result.get("status") == "PASS" and result.get("next") == PHASE_NEXT[phase]
        except Exception as exc:
            verifier_ok = False
            result = "%s: %s" % (type(exc).__name__, exc)
        evidence_hash = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_hash = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        expected_evidence = fixture["expected_phase_evidence_sha256"].get(phase)
        expected_rollback = fixture["expected_phase_rollback_sha256"].get(phase)
        try:
            index = _row(index_rows, "INDEX-AC-S08-%s" % phase)
        except Exception:
            index = {}
        receipt_ok = (
            verifier_ok
            and isinstance(evidence, Mapping)
            and isinstance(rollback, Mapping)
            and evidence_hash == expected_evidence == record.get("evidence_sha256")
            and rollback_hash == expected_rollback == record.get("rollback_sha256")
            and evidence.get("contract_id") == "AC-S08-%s" % phase
            and evidence.get("decision") == PHASE_DECISIONS[phase]
            and evidence.get("next") == PHASE_NEXT[phase]
            and evidence.get("status") == "PASS"
            and rollback.get("status") == "PASS"
            and rollback.get("external_state_changed") is False
            and rollback.get("production_state_changed") is False
            and rollback.get("real_time_soak_waited") is False
            and index.get("status") == "PASS"
            and index.get("artifact_sha256") == evidence_hash
        )
        _add(checks, "S08REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, receipt_ok, {"verifier": result, "evidence_sha256": evidence_hash})
        portable = _is_portable(evidence) and _is_portable(rollback)
        no_local_paths = no_local_paths and portable
        shared = evidence.get("shared_runtime_contract") if isinstance(evidence, Mapping) else None
        shared_expected = {
            "paths_excluded_from_receipt_input_hashes": PHASE_SHARED_RUNTIME_EXCLUSIONS[phase],
            "current_validation": "evaluate_contract",
        }
        shared_runtime_ok = shared_runtime_ok and isinstance(shared, Mapping) and all(shared.get(key) == value for key, value in shared_expected.items()) and isinstance(shared.get("reason"), str)
        boundary = evidence.get("external_effect_boundary") if isinstance(evidence, Mapping) else None
        boundary_expected = (
            isinstance(boundary, Mapping)
            and boundary.get("external_network_accessed") is False
            and boundary.get("real_market_or_odds_observed") is False
            and boundary.get("recommendation_generated_or_enabled") is False
            and boundary.get("order_submission_enabled") is False
            and boundary.get("production_deployed_or_activated") is False
            and boundary.get("real_time_soak_waited") is False
            and boundary.get("incremental_cash_spent_aud") == "0.00"
        )
        external_boundary_ok = external_boundary_ok and boundary_expected
    _add(checks, "S08REVIEW-PHASE-EVIDENCE-NO-LOCAL-PATHS", no_local_paths, "portable" if no_local_paths else "local-path-or-URI-leak")
    _add(checks, "S08REVIEW-SHARED-RUNTIME-CONTRACT-EXACT", shared_runtime_ok, PHASE_SHARED_RUNTIME_EXCLUSIONS)
    _add(checks, "S08REVIEW-PHASE-EXTERNAL-BOUNDARY-EXACT", external_boundary_ok, "all phase boundaries checked")


def _check_legacy_receipt_compatibility(root: Path, contract: Any, fixture: Any, checks: List[Dict[str, Any]]) -> None:
    expected = fixture.get("legacy_receipt_compatibility") if isinstance(fixture, Mapping) else None
    declared = contract.get("legacy_receipt_compatibility") if isinstance(contract, Mapping) else None
    manifest = _safe_load(root, root / LEGACY_COMPATIBILITY_PATH, checks, "S08REVIEW-LEGACY-COMPATIBILITY-STRICT-JSON")
    expected_paths = {
        "manifest_path": LEGACY_COMPATIBILITY_PATH.as_posix(),
        "manifest_sha256": PINNED_MANIFEST_SHA256,
        "helper_path": LEGACY_COMPATIBILITY_HELPER_PATH.as_posix(),
    }
    helper_hash = sha256_file(root / LEGACY_COMPATIBILITY_HELPER_PATH) if (root / LEGACY_COMPATIBILITY_HELPER_PATH).is_file() else "MISSING"
    contract_ok = (
        isinstance(expected, Mapping)
        and isinstance(declared, Mapping)
        and all(declared.get(key) == value for key, value in expected_paths.items())
        and declared.get("helper_sha256") == expected.get("helper_sha256") == helper_hash
        and declared.get("legacy_receipt_contract_ids") == expected.get("contract_ids")
        and isinstance(declared.get("constraint"), str)
        and "SUCCESSOR_EVOLVABLE_SIGNED_INPUTS" in declared["constraint"]
        and "LEGACY_SIGNED_RECEIPT_SUCCESSOR_COMPATIBILITY_IS_EXACT_AND_ALLOW_LISTED" in contract.get("review_gates", [])
    )
    _add(checks, "S08REVIEW-LEGACY-COMPATIBILITY-CONTRACT-EXACT", contract_ok, declared)
    hashes = manifest.get("approved_successor_hashes") if isinstance(manifest, Mapping) else None
    manifest_ok = (
        isinstance(expected, Mapping)
        and sha256_file(root / LEGACY_COMPATIBILITY_PATH) == expected.get("manifest_sha256") == PINNED_MANIFEST_SHA256
        and isinstance(manifest, Mapping)
        and manifest.get("schema_version") == "1.0.0"
        and manifest.get("compatibility_id") == COMPATIBILITY_ID
        and manifest.get("stage_id") == STAGE_ID
        and isinstance(hashes, Mapping)
        and bool(hashes)
        and all(isinstance(path, str) and approved_successor_sha256(root, path) == digest for path, digest in hashes.items())
    )
    _add(checks, "S08REVIEW-LEGACY-COMPATIBILITY-MANIFEST-EXACT", manifest_ok, {"paths": sorted(hashes) if isinstance(hashes, Mapping) else hashes, "helper_sha256": helper_hash})


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(fixture, Mapping) or not isinstance(fixture.get("cases"), list):
        _add(checks, "S08REVIEW-FROZEN-STAGE-CASES", False, "cases unavailable")
        return {}
    results: Dict[str, Dict[str, Any]] = {}
    for row in fixture["cases"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("expected"), Mapping):
            _add(checks, "S08REVIEW-FROZEN-STAGE-CASE-SHAPE", False, row)
            continue
        try:
            actual = evaluate_stage_snapshot(row["snapshot"])
            expected = row["expected"]
            ok = actual["status"] == expected.get("status") and actual["reason_codes"] == expected.get("reason_codes") and actual["recommendation_generated"] is False and actual["order_submission_enabled"] is False and actual["real_time_soak_waited"] is False
            _add(checks, "S08REVIEW-CASE-%s" % row["case_id"], ok, {"actual": actual, "expected": expected})
            results[row["case_id"]] = actual
        except Exception as exc:
            _add(checks, "S08REVIEW-CASE-%s" % row["case_id"], False, "%s: %s" % (type(exc).__name__, exc))
    positive = results.get("POSITIVE_EXACT_STAGE")
    replay_ok = False
    if positive is not None:
        source = next(row for row in fixture["cases"] if row.get("case_id") == "POSITIVE_EXACT_STAGE")
        replay_ok = all(evaluate_stage_snapshot(source["snapshot"]) == positive for _ in range(fixture.get("replay_count", 0)))
    _add(checks, "S08REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", replay_ok, fixture.get("replay_count") if isinstance(fixture, Mapping) else None)
    adverse_cases = [row for row in fixture["cases"] if isinstance(row, Mapping) and row.get("case_id") != "POSITIVE_EXACT_STAGE"]
    adverse_ok = isinstance(fixture.get("adverse_replay_count"), int) and fixture.get("adverse_replay_count") == 10000 and bool(adverse_cases)
    adverse_reason_codes = set()
    if adverse_ok:
        for number in range(fixture["adverse_replay_count"]):
            result = evaluate_stage_snapshot(adverse_cases[number % len(adverse_cases)]["snapshot"])
            adverse_ok = adverse_ok and result["status"] == "S08_STAGE_REVIEW_REJECTED_NO_ACTION" and result["recommendation_generated"] is False and result["order_submission_enabled"] is False and result["real_time_soak_waited"] is False
            adverse_reason_codes.update(result["reason_codes"])
    expected_reasons = {
        "PROBABILITY_SUM_GATE_FAILED",
        "SOURCE_INDEPENDENCE_GATE_FAILED",
        "SINGLE_LONG_ODDS_NOT_BLOCKED",
        "UNCONFIRMED_OR_UNFRESH_LINE_ALLOWED",
        "STALE_OR_DESYNCHRONIZED_QUOTE_ALLOWED",
        "SIGNED_RECEIPT_NOT_CURRENT",
        "EVIDENCE_NOT_PORTABLE",
        "OPEN_REVIEW_FINDINGS",
    }
    _add(checks, "S08REVIEW-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ACTION", adverse_ok and adverse_reason_codes == expected_reasons, {"count": fixture.get("adverse_replay_count"), "reason_codes": sorted(adverse_reason_codes)})
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
        _add(checks, "S08REVIEW-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY", not denied and not forbidden, {"imports": sorted(imports), "denied": denied, "tokens": forbidden})
    except Exception as exc:
        _add(checks, "S08REVIEW-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_manifest(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    manifest = _safe_load(root, root / ARTIFACT_MANIFEST_PATH, checks, "S08REVIEW-ARTIFACT-MANIFEST-STRICT-JSON")
    try:
        sums = _parse_sums(root / SHA256SUMS_PATH)
        _add(checks, "S08REVIEW-SHA256SUMS-STRICT", True, SHA256SUMS_PATH.as_posix())
    except Exception as exc:
        sums = {}
        _add(checks, "S08REVIEW-SHA256SUMS-STRICT", False, "%s: %s" % (type(exc).__name__, exc))
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("files"), list):
        _add(checks, "S08REVIEW-ARTIFACT-MANIFEST-COVERAGE", False, "manifest files unavailable")
        return
    try:
        rows = manifest["files"]
        entries: Dict[str, Mapping[str, Any]] = {}
        errors = []
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
                raise Stage8ReviewError("manifest row is malformed")
            relative = row["path"]
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts or relative in entries:
                raise Stage8ReviewError("manifest path is unsafe or duplicate")
            entries[relative] = row
            path = root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if row.get("sha256") != actual or row.get("bytes") != (path.stat().st_size if path.is_file() else None) or sums.get(relative) != actual:
                errors.append({"path": relative, "actual": actual})
        expected_paths = {path.relative_to(root).as_posix() for path in _expected_project_files(root)}
        report_paths = {JUNIT_PATH.as_posix(), SIGNED_STATE_JUNIT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix()}
        required = {CONTRACT_PATH.as_posix(), FINDINGS_PATH.as_posix(), FIXTURE_PATH.as_posix(), TEST_PATH.as_posix(), ORACLE_PATH.as_posix()}
        if require_test_reports:
            required.update(report_paths)
        considered_entries = set(entries) if require_test_reports else set(entries) - report_paths
        considered_expected = expected_paths if require_test_reports else expected_paths - report_paths
        considered_sums = set(sums) if require_test_reports else set(sums) - report_paths
        considered_errors = errors if require_test_reports else [row for row in errors if row["path"] not in report_paths]
        coverage_ok = (
            manifest.get("schema_version") == "1.0.0"
            and manifest.get("version") == VERSION
            and manifest.get("file_count") == len(rows)
            and [row.get("path") for row in rows] == sorted(entries)
            and considered_entries == considered_expected
            and considered_sums == considered_expected | {ARTIFACT_MANIFEST_PATH.as_posix()}
            and sums.get(ARTIFACT_MANIFEST_PATH.as_posix()) == sha256_file(root / ARTIFACT_MANIFEST_PATH)
            and required <= considered_entries
            and not considered_errors
        )
        _add(checks, "S08REVIEW-ARTIFACT-MANIFEST-COVERAGE", coverage_ok, {"manifest_files": len(rows), "expected_files": len(considered_expected), "missing_required": sorted(required - considered_entries), "errors": considered_errors})
    except Exception as exc:
        _add(checks, "S08REVIEW-ARTIFACT-MANIFEST-COVERAGE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Any, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S08REVIEW-REPORTS-DEFERRED-FOR-CANDIDATE", True, "candidate mode does not require generated reports")
        return
    report_specs = (
        (JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else 0, "S08REVIEW-TARGETED-PYTEST-REPORT"),
        (SIGNED_STATE_JUNIT_PATH, fixture.get("minimum_signed_state_pytest_cases") if isinstance(fixture, Mapping) else 0, "S08REVIEW-SIGNED-STATE-PYTEST-REPORT"),
    )
    for relative, minimum, identifier in report_specs:
        try:
            summary = _junit_summary(root / relative)
            ok = isinstance(minimum, int) and minimum > 0 and summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, identifier, ok, {"summary": summary, "minimum": minimum})
        except Exception as exc:
            _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in report and "MAX_INCREMENTAL_CASH_AUD: 0.00" in report and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in report and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in report
        _add(checks, "S08REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S08REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_pins(root, checks, hashes)
    contract = _safe_load(root, root / CONTRACT_PATH, checks, "S08REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root, root / FINDINGS_PATH, checks, "S08REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S08REVIEW-FIXTURE-STRICT-JSON")
    _check_contract_and_findings(contract, findings, fixture, checks)
    _check_repository_ci_contract(root, contract, checks)
    _check_baseline(root, contract, checks, hashes)
    _check_taskpack(root, checks)
    _check_phase_receipts(root, contract, fixture, checks)
    _check_legacy_receipt_compatibility(root, contract, fixture, checks)
    cases = _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_manifest(root, checks, require_test_reports=require_test_reports)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    positive = cases.get("POSITIVE_EXACT_STAGE", {})
    return {
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "stage_status": "S08_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S08_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S08_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S08_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED",
        "release_status": "S08_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "stage_snapshot_summary": {"positive_status": positive.get("status"), "positive_output_sha256": positive.get("output_sha256"), "real_time_waited": False},
        "external_network_used_by_verifier": False,
        "next": "S08/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S08/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    result = evaluate_contract(root, require_test_reports=False)
    return {
        "status": result["status"],
        "decision": "S08_STAGE_REVIEW_CANDIDATE_VALID" if result["status"] == "PASS" else "S08_STAGE_REVIEW_CANDIDATE_INVALID",
        "summary": result["summary"],
        "next": result["next"],
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {}
    for relative in ROLLBACK_ARTIFACTS:
        path = root / relative
        artifacts[relative.as_posix()] = {"status": "PASS" if path.is_file() else "FAIL", "sha256": sha256_file(path) if path.is_file() else "MISSING"}
    status = "PASS" if artifacts and all(row["status"] == "PASS" for row in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-STAGE-REVIEW-ROLLBACK",
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
    paths = [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, LEGACY_COMPATIBILITY_PATH, LEGACY_COMPATIBILITY_HELPER_PATH, ORACLE_PATH, *PHASE_EVIDENCE.values(), *PHASE_ROLLBACK.values(), *[Path(key) for key in PINNED_BASELINE_HASHES]]
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def _current_code_hash(root: Path) -> str:
    return _sha256_bytes(ORACLE_PATH.as_posix().encode("utf-8") + b"\0" + (root / ORACLE_PATH).read_bytes() + b"\0")


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    fixture = strict_json_load(root / FIXTURE_PATH)
    positive = next(row for row in fixture["cases"] if row["case_id"] == "POSITIVE_EXACT_STAGE")
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "validation": validation,
        "phase_receipts": {
            phase: {
                "evidence_path": PHASE_EVIDENCE[phase].as_posix(),
                "evidence_sha256": sha256_file(root / PHASE_EVIDENCE[phase]),
                "rollback_path": PHASE_ROLLBACK[phase].as_posix(),
                "rollback_sha256": sha256_file(root / PHASE_ROLLBACK[phase]),
            }
            for phase in PHASE_VERIFIERS
        },
        "stage_snapshot": evaluate_stage_snapshot(positive["snapshot"]),
        "deterministic_replay": {"replay_iterations": fixture["replay_count"], "adverse_perturbation_iterations": fixture["adverse_replay_count"], "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S08_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S08/STAGE_REVIEW/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S00/stage_review_test.py::test_baseline_whole_stage_review_passes_without_generated_stage_reports tests/S00/stage_review_test.py::test_abd_ci_workflow_mutations_fail_closed tests/S00/stage_review_test.py::test_abd_fast_targeted_workflow_mutations_fail_closed tests/S08/stage_review_test.py --junitxml=machine/evidence/S08/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S08/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S08/P01_test.py tests/S08/P02_test.py tests/S08/P03_test.py tests/S08/P04_test.py tests/S08/stage_review_test.py --junitxml=machine/evidence/S08/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S08/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance.stage8_review --root . --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {"inputs": _input_hashes(root), "repository_ci": _repository_ci_hashes(root), "code": _current_code_hash(root), "parameters": sha256_file(root / "machine/facts/parameters.json"), "model": sha256_file(root / "machine/facts/model_system_card.json"), "model_not_executed_reason": "S08 review validates frozen evidence gates only.", "rollback_evidence": _sha256_bytes(_json_bytes(rollback))},
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
        "next": validation["next"],
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise Stage8ReviewError("S08 review evidence must be written to machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise Stage8ReviewError("cannot write a failed S08 stage review")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    return {"contract_id": CONTRACT_ID, "status": evidence["status"], "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": evidence["next"]}


def verify_existing_stage_review_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root, root / EVIDENCE_PATH, checks, "S08REVIEW-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root, root / ROLLBACK_EVIDENCE_PATH, checks, "S08REVIEW-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S08-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S08/GITHUB_STAGE_UPLOAD_READY"
            and evidence.get("release_status") == "S08_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and evidence.get("decision_sha256") == _decision_hash(evidence)
        )
        _add(checks, "S08REVIEW-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        errors = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            actual = sha256_file(root / candidate) if not candidate.is_absolute() and ".." not in candidate.parts and (root / candidate).is_file() else "MISSING_OR_UNSAFE"
            if actual != expected:
                errors.append({"path": relative, "actual": actual})
        _add(checks, "S08REVIEW-EXISTING-INPUT-HASHES", not errors, errors or "all inputs match")
        repository_ci = evidence.get("hashes", {}).get("repository_ci", {})
        repository_ci_errors = []
        expected_repository_ci_paths = {
            REPOSITORY_FAST_WORKFLOW_PATH.as_posix(),
        }
        if not isinstance(repository_ci, Mapping) or set(repository_ci) != expected_repository_ci_paths:
            repository_ci_errors.append({"reason": "repository_ci hash set is invalid"})
        else:
            for relative, expected in repository_ci.items():
                candidate = Path(relative)
                actual = sha256_file(root.parent / candidate) if not candidate.is_absolute() and ".." not in candidate.parts and (root.parent / candidate).is_file() else "MISSING_OR_UNSAFE"
                if actual != expected:
                    repository_ci_errors.append({"path": relative, "actual": actual})
        _add(checks, "S08REVIEW-EXISTING-REPOSITORY-CI-HASHES", not repository_ci_errors, repository_ci_errors or "all repository CI inputs match")
        _add(checks, "S08REVIEW-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S08REVIEW-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S08-STAGE-REVIEW-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and rollback.get("recommendation_generated") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_account_balance_read_or_written") is False
        and rollback.get("real_time_soak_waited") is False
        and rollback.get("incremental_cash_spent_aud") == "0.00"
    )
    _add(checks, "S08REVIEW-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else rollback)
    current = evaluate_contract(root, require_test_reports=True)
    _add(checks, "S08REVIEW-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING",
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S08/GITHUB_STAGE_UPLOAD_READY" if not failed else "S08/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def main(argv: List[str] | None = None) -> int:
    """Provide a stage-local CLI without changing the shared phase dispatcher."""

    parser = argparse.ArgumentParser(description="ABD S08 fail-closed whole-stage review")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-existing", action="store_true", help="verify an existing signed S08 stage-review receipt")
    parser.add_argument("--root", default=".", help="ABD project root")
    parser.add_argument("--evidence", default="machine/evidence", help="evidence directory, relative to --root unless absolute")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.verify_existing:
        result = verify_existing_stage_review_evidence(root)
    else:
        evidence_dir = Path(args.evidence)
        if not evidence_dir.is_absolute():
            evidence_dir = root / evidence_dir
        result = write_stage_review_evidence(root, evidence_dir)
    print(
        json.dumps(
            {
                "contract_id": result["contract_id"],
                "status": result["status"],
                "evidence": result["evidence_path"],
                "evidence_sha256": result["evidence_sha256"],
                "next": result["next"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
