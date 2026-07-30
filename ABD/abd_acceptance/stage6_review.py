"""Independent whole-stage review oracle for ABD S06.

This review joins the four already-signed S06 phase receipts with one frozen,
synthetic mail flow.  It is deliberately not a Gmail runtime: it never reads a
token, opens a network connection, starts a scheduler, invokes a trash
adapter, persists raw mail in the repository, or waits for wall-clock time.
Passing means that the local, fail-closed stage contract is internally
consistent; it does not claim a deployed archive, account mutation, malware
clearance, OVH/Cloudflare runtime, order, or financial return.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from attachment_sandbox import scan_attachment
from mail_collector import ARCHIVE_DIRECTORY_NAME, preserve_mail
from mail_trash_worker import (
    PERMANENT_DELETE_CAPABILITY,
    REAL_TIME_SOAK_REQUIRED,
    SCHEDULED_AUDIT_LOCAL_TIME,
    assess_trash_candidate,
    audit_daily_mail_state,
    dispatch_trash_request,
    prepare_restore_request,
    validate_no_real_time_soak,
)

from .attachment_security import verify_existing_phase_evidence as verify_p03
from .canonical_facts import sha256_file, strict_json_load
from .gmail_authorization import verify_existing_phase_evidence as verify_p01
from .gmail_oauth_core import ALLOWED_GMAIL_METHODS, DENIED_GMAIL_METHODS, GMAIL_SCOPE
from .mail_deletion_audit import _fixture_mail_record
from .mail_deletion_audit import verify_existing_phase_evidence as verify_p04
from .mail_preservation import verify_existing_phase_evidence as verify_p02
from .stage4_delivery import verify_stage4_delivery


CONTRACT_ID = "STAGE-REVIEW-S06"
REVIEW_ID = "ABD-S06-WHOLE-STAGE-REVIEW"
STAGE_ID = "S06"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-29T00:00:00+10:00"
STAGE_REVIEW_COMMIT = "313c71f46ad66f81e1ff15295c3ad688ecb8473c"

CONTRACT_PATH = Path("machine/facts/stage6_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S06/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S06_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S06/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S06/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S06/STAGE_REVIEW/full_regression.xml")
SIGNED_STATE_JUNIT_PATH = Path("machine/evidence/S06/STAGE_REVIEW/signed_state_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S06-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
ORACLE_PATH = Path("abd_acceptance/stage6_review.py")

# Filled after the review artifacts exist.  Keeping these pins in the oracle
# makes an unreviewed edit fail closed rather than silently changing the scope.
PINNED_REVIEW_ARTIFACT_HASHES: Dict[str, str] = {
    CONTRACT_PATH.as_posix(): "19ee85cda12926c416b0e2a3fcc94f37a15aaade57d9e1d767e81b51e35a4dfa",
    FINDINGS_PATH.as_posix(): "5699527cee51fd72a554922069bd128cc55b062cc300687b2098b70c4a553da2",
    FIXTURE_PATH.as_posix(): "6962b50badba2c241be6c70aeb2ce76c3ed90bf4aea88e7783a665327776fb03",
    TEST_PATH.as_posix(): "2bf736caedda9990e3344d7552849ad52d0ac8e75a1ad42a783426e0e9a23275",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "cb2d83555feab21b55d97b1d5e043d6a143a798bb9dc8039d23666188cf92c28"

PHASE_VERIFIERS = {
    "P01": verify_p01,
    "P02": verify_p02,
    "P03": verify_p03,
    "P04": verify_p04,
}
PHASE_DECISIONS = {
    "P01": "GMAIL_AUTHORIZATION_QUERY_AND_CURSOR_FROZEN",
    "P02": "MAIL_BYTES_PRESERVED_READBACK_VERIFIED_KEEP_ONLY",
    "P03": "ATTACHMENTS_PARSED_OR_QUARANTINED_KEEP_ONLY",
    "P04": "TRASH_REQUEST_ONLY_AFTER_ALL_GATES_NO_PERMANENT_DELETE",
}
PHASE_NEXT = {
    "P01": "S06/P02_READY_NOT_STARTED",
    "P02": "S06/P03_READY_NOT_STARTED",
    "P03": "S06/P04_READY_NOT_STARTED",
    "P04": "S06/STAGE_REVIEW_READY_NOT_STARTED",
}
PHASE_OUTPUTS = {
    "P01": ["gmail_oauth.py", "mail_query_rules.json", "token_storage.md"],
    "P02": ["mail_collector.py", "mail_manifest.schema.json", "archive_layout.md"],
    "P03": ["attachment_sandbox.py", "parser_registry.json", "quarantine_rules.json"],
    "P04": ["mail_trash_worker.py", "codex_daily_audit.md", "mail_restore_runbook.md"],
}
ROLLBACK_ARTIFACTS = (
    Path("gmail_oauth.py"),
    Path("mail_query_rules.json"),
    Path("token_storage.md"),
    Path("mail_collector.py"),
    Path("mail_manifest.schema.json"),
    Path("archive_layout.md"),
    Path("attachment_sandbox.py"),
    Path("parser_registry.json"),
    Path("quarantine_rules.json"),
    Path("mail_trash_worker.py"),
    Path("codex_daily_audit.md"),
    Path("mail_restore_runbook.md"),
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
)
EXTERNAL_EFFECT_BOUNDARY = {
    "github_upload_performed_by_local_review": False,
    "remote_ci_result_claimed_by_local_review": False,
    "external_network_accessed_for_product_runtime": False,
    "gmail_account_or_api_accessed": False,
    "gmail_mutation_performed": False,
    "gmail_runtime_adapter_invoked": False,
    "permanent_delete_capability": False,
    "private_database_client_executed": False,
    "private_database_or_raw_data_written": False,
    "scheduler_daemon_started": False,
    "real_time_soak_waited": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "model_or_strategy_executed": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "secret_provisioned_or_read": False,
    "production_deployed_or_activated": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "incremental_cash_spent_aud": "0.00",
    "owner_final_order_only": True,
}
SECRET_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])ya29\.[A-Za-z0-9._-]+", re.I),
    re.compile(r"(?:^|[^a-z0-9])1//[A-Za-z0-9._-]+", re.I),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}", re.I),
)
LOCAL_PATH_FRAGMENTS = ("/" + "Users/", "file" + "://")


class Stage6ReviewContractError(ValueError):
    """Raised when the S06 whole-stage review cannot pass safely."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _portable(path: Path) -> str:
    text = path.as_posix()
    for anchor in ("/machine/", "/tests/", "/abd_acceptance/"):
        if anchor in text:
            return anchor.lstrip("/") + text.split(anchor, 1)[1]
    return path.name


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise Stage6ReviewContractError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise Stage6ReviewContractError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]*("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8")) if normalized != text else "NORMALIZATION_FAILED"


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@lru_cache(maxsize=None)
def _historical_code_hash(root: Path, commit: str, *, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", commit, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_IMPLEMENTATION_TREE"
    digest = hashlib.sha256()
    paths = sorted(
        item for item in listing.stdout.splitlines() if item.startswith("ABD/abd_acceptance/") and item.endswith(".py")
    )
    if not paths:
        return "EMPTY_IMPLEMENTATION_TREE"
    for repo_path in paths:
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (commit, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_IMPLEMENTATION_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


@lru_cache(maxsize=None)
def _receipt_commit_is_ancestor(root: Path, *, verify_git_history: bool) -> bool:
    if not verify_git_history:
        return False
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", STAGE_REVIEW_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@lru_cache(maxsize=None)
def _historical_receipt_input_hash(root: Path, relative: str, *, verify_git_history: bool) -> str:
    if not verify_git_history or not _receipt_commit_is_ancestor(root, verify_git_history=verify_git_history):
        return "UNVERIFIED_RECEIPT_HISTORY"
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return "UNSAFE_RECEIPT_INPUT"
    result = subprocess.run(
        ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (STAGE_REVIEW_COMMIT, candidate.as_posix())],
        check=False,
        capture_output=True,
    )
    return _sha256_bytes(result.stdout) if result.returncode == 0 else "MISSING_RECEIPT_INPUT"


def _review_pin_checks(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected_paths = {CONTRACT_PATH.as_posix(), FINDINGS_PATH.as_posix(), FIXTURE_PATH.as_posix(), TEST_PATH.as_posix()}
    pins_ok = set(PINNED_REVIEW_ARTIFACT_HASHES) == expected_paths
    _add(checks, "S06REVIEW-PIN-SET-EXACT", pins_ok, sorted(PINNED_REVIEW_ARTIFACT_HASHES))
    for relative in sorted(expected_paths):
        expected = PINNED_REVIEW_ARTIFACT_HASHES.get(relative, "")
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(
            checks,
            "S06REVIEW-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"),
            bool(expected) and actual == expected,
            {"expected": expected or "UNSET", "actual": actual},
        )
    actual_structural = _structural_self_hash(root)
    _add(
        checks,
        "S06REVIEW-ORACLE-STRUCTURAL-HASH",
        bool(STRUCTURAL_SELF_NORMALIZED_SHA256) and actual_structural == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256 or "UNSET", "actual": actual_structural},
    )


def _check_contract_and_findings(
    contract: Mapping[str, Any], findings: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]
) -> None:
    scope = contract.get("review_scope", {})
    expected_phases = ["P01", "P02", "P03", "P04"]
    identity_ok = (
        contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and contract.get("fixed_at") == FIXED_CLOCK
        and fixture.get("fixture_id") == "FIX-S06-STAGE-REVIEW"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("review_id") == REVIEW_ID
        and fixture.get("fixed_clock") == FIXED_CLOCK
    )
    _add(checks, "S06REVIEW-CONTRACT-IDENTITY", identity_ok, {"review": contract.get("review_id"), "fixture": fixture.get("fixture_id")})
    scope_ok = (
        scope.get("phase_ids") == fixture.get("expected_phase_ids") == expected_phases
        and scope.get("requirement_ids") == ["REQ-S06-%s" % phase for phase in expected_phases]
        and scope.get("acceptance_contract_ids") == ["AC-S06-%s" % phase for phase in expected_phases]
        and scope.get("task_ids") == ["T-S06-%s-%02d" % (phase, task) for phase in expected_phases for task in [1, 2, 3]]
    )
    _add(checks, "S06REVIEW-SCOPE-EXACT", scope_ok, scope)
    source_receipts = contract.get("supplied_source_receipts")
    receipts_ok = (
        isinstance(source_receipts, list)
        and len(source_receipts) == 2
        and source_receipts[0].get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and source_receipts[1].get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and source_receipts[1].get("original_file_count") == 53
    )
    _add(checks, "S06REVIEW-SOURCE-RECEIPTS-EXACT", receipts_ok, source_receipts)
    records = contract.get("phase_records")
    records_ok = (
        isinstance(records, list)
        and [row.get("phase_id") for row in records] == expected_phases
        and all(
            row.get("requirement_id") == "REQ-S06-%s" % row.get("phase_id")
            and row.get("acceptance_contract_id") == "AC-S06-%s" % row.get("phase_id")
            and row.get("task_ids") == ["T-S06-%s-%02d" % (row.get("phase_id"), task) for task in [1, 2, 3]]
            and row.get("required_outputs") == PHASE_OUTPUTS.get(row.get("phase_id"))
            and row.get("expected_next") == PHASE_NEXT.get(row.get("phase_id"))
            for row in records
        )
    )
    _add(checks, "S06REVIEW-PHASE-RECORDS-EXACT", records_ok, [row.get("phase_id") for row in records] if isinstance(records, list) else records)
    finding_rows = findings.get("findings")
    expected_findings = fixture.get("expected_finding_ids")
    findings_ok = (
        findings.get("schema_version") == "1.0.0"
        and findings.get("review_id") == REVIEW_ID
        and findings.get("stage_id") == STAGE_ID
        and findings.get("fixed_at") == FIXED_CLOCK
        and isinstance(finding_rows, list)
        and [row.get("id") for row in finding_rows] == expected_findings
        and len({row.get("verification_gate") for row in finding_rows}) == len(finding_rows)
        and all(row.get("status") == "RESOLVED_IN_REVIEW_CANDIDATE" for row in finding_rows)
        and findings.get("summary") == {
            "total": 6,
            "resolved_in_review_candidate": 6,
            "open": 0,
            "github_upload_pending_is_not_an_open_code_finding": True,
        }
    )
    _add(checks, "S06REVIEW-ALL-FINDINGS-RESOLVED", findings_ok, findings.get("summary"))
    effects = contract.get("external_effect_boundary")
    effects_ok = effects == EXTERNAL_EFFECT_BOUNDARY
    _add(checks, "S06REVIEW-EXTERNAL-EFFECT-BOUNDARY", effects_ok, effects)
    boundary_ok = (
        contract.get("claim_boundary") == {
            "gmail_evidence_archival_verified": False,
            "gmail_permission_or_runtime_access_verified": False,
            "live_malware_clearance_verified": False,
            "production_collection_enabled": False,
            "runtime_freshness_verified": False,
            "ovh_7x24_runtime_verified": False,
            "cloudflare_global_chinese_access_verified": False,
            "financial_target_verified_or_guaranteed": False,
        }
        and contract.get("release_status_on_pass") == fixture.get("expected_release_status")
        and contract.get("next_on_pass") == fixture.get("expected_next")
    )
    _add(checks, "S06REVIEW-CLAIM-AND-TERMINAL-BOUNDARY", boundary_ok, contract.get("claim_boundary"))


def _check_baseline(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    expected = contract.get("baseline_critical_artifacts")
    if not isinstance(expected, Mapping):
        _add(checks, "S06REVIEW-BASELINE-CRITICAL-HASHES", False, "baseline hashes unavailable")
        return
    mismatches: list[dict[str, str]] = []
    for relative, expected_hash in sorted(expected.items()):
        path = root / str(relative)
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[str(relative)] = actual
        if actual != expected_hash:
            mismatches.append({"path": str(relative), "expected": str(expected_hash), "actual": actual})
    _add(checks, "S06REVIEW-BASELINE-CRITICAL-HASHES", not mismatches, mismatches or "all baseline hashes match")


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S06REVIEW-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S06REVIEW-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S06REVIEW-TASK-GRAPH-STRICT-JSON")
    trace = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S06REVIEW-TRACE-STRICT-JSON")
    expected_phases = ["P01", "P02", "P03", "P04"]
    try:
        requirement_rows = [_row(requirements, "REQ-S06-%s" % phase) for phase in expected_phases]
        contract_rows = [_row(contracts, "AC-S06-%s" % phase) for phase in expected_phases]
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        task_rows = [_row(tasks, "T-S06-%s-%02d" % (phase, step)) for phase in expected_phases for step in [1, 2, 3]]
        trace_rows = [_row(trace, "REQ-S06-%s" % phase, key="requirement_id") for phase in expected_phases]
        requirements_ok = all(
            row.get("stage_id") == STAGE_ID
            and row.get("phase_id") == phase
            and row.get("scope") == PHASE_OUTPUTS[phase]
            and row.get("primary_acceptance_criteria_id") == "AC-S06-%s" % phase
            for phase, row in zip(expected_phases, requirement_rows)
        )
        contracts_ok = all(
            row.get("requirement_id") == "REQ-S06-%s" % phase
            and row.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S06-%s --evidence machine/evidence" % phase
            for phase, row in zip(expected_phases, contract_rows)
        )
        task_graph_ok = all(
            row.get("requirement_ids") == ["REQ-S06-%s" % row.get("phase_id")]
            and row.get("acceptance_criteria_ids") == ["AC-S06-%s" % row.get("phase_id")]
            for row in task_rows
        ) and [row.get("id") for row in task_rows] == [
            "T-S06-%s-%02d" % (phase, step) for phase in expected_phases for step in [1, 2, 3]
        ]
        trace_ok = all(
            row.get("acceptance_criteria_id") == "AC-S06-%s" % phase
            and row.get("task_ids") == ["T-S06-%s-%02d" % (phase, step) for step in [1, 2, 3]]
            and row.get("evidence_id") == "EVD-S06-%s" % phase
            for phase, row in zip(expected_phases, trace_rows)
        )
    except Exception as exc:
        requirements_ok = contracts_ok = task_graph_ok = trace_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = "exact S06 task-pack rows"
    _add(checks, "S06REVIEW-TASKPACK-REQUIREMENTS-EXACT", requirements_ok, detail)
    _add(checks, "S06REVIEW-TASKPACK-CONTRACTS-EXACT", contracts_ok, detail)
    _add(checks, "S06REVIEW-TASKPACK-GRAPH-EXACT", task_graph_ok, detail)
    _add(checks, "S06REVIEW-TASKPACK-TRACE-EXACT", trace_ok, detail)


def _check_phase_receipts_and_oracles(
    root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    *,
    verify_git_history: bool,
) -> None:
    try:
        s04 = verify_stage4_delivery(root, verify_git_history=verify_git_history)
        s04_ok = (
            s04.get("status") == "PASS"
            and s04.get("decision") == "S04_DELIVERED_S05_MAY_START"
            and s04.get("next") == "S05/P01_READY_NOT_STARTED"
        )
        s04_detail: Any = {"status": s04.get("status"), "decision": s04.get("decision"), "next": s04.get("next")}
    except Exception as exc:
        s04_ok = False
        s04_detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06REVIEW-S04-DELIVERY-PREREQUISITE", s04_ok, s04_detail)
    records = contract.get("phase_records")
    if not isinstance(records, list):
        _add(checks, "S06REVIEW-PHASE-RECEIPT-RECORDS", False, "phase records unavailable")
        return
    for record in records:
        phase = record.get("phase_id")
        if phase not in PHASE_VERIFIERS:
            _add(checks, "S06REVIEW-PHASE-UNKNOWN", False, record)
            continue
        evidence_path = root / str(record.get("evidence_path", ""))
        rollback_path = root / str(record.get("rollback_path", ""))
        evidence_actual = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_actual = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        receipt_ok = (
            evidence_actual == record.get("evidence_sha256") == fixture.get("expected_phase_evidence_sha256", {}).get(phase)
            and rollback_actual == record.get("rollback_sha256") == fixture.get("expected_phase_rollback_sha256", {}).get(phase)
        )
        _add(
            checks,
            "S06REVIEW-%s-RECEIPT-HASHES" % phase,
            receipt_ok,
            {"evidence": evidence_actual, "rollback": rollback_actual},
        )
        try:
            signed_evidence = strict_json_load(evidence_path)
            result = PHASE_VERIFIERS[phase](root, verify_git_history=verify_git_history)
            phase_ok = (
                result.get("status") == "PASS"
                and result.get("next") == PHASE_NEXT[phase]
                and isinstance(signed_evidence, Mapping)
                and signed_evidence.get("status") == "PASS"
                and signed_evidence.get("decision") == PHASE_DECISIONS[phase]
                and signed_evidence.get("next") == PHASE_NEXT[phase]
            )
            detail: Any = {
                "verifier_status": result.get("status"),
                "signed_decision": signed_evidence.get("decision") if isinstance(signed_evidence, Mapping) else None,
                "next": result.get("next"),
            }
        except Exception as exc:
            phase_ok = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S06REVIEW-%s-CURRENT-PHASE-ORACLE" % phase, phase_ok, detail)
        historical = _historical_code_hash(root, str(record.get("implementation_commit", "")), verify_git_history=verify_git_history)
        history_ok = (not verify_git_history) or historical == record.get("implementation_code_sha256")
        _add(
            checks,
            "S06REVIEW-%s-HISTORICAL-ACCEPTANCE-CODE" % phase,
            history_ok,
            {"expected": record.get("implementation_code_sha256"), "actual": historical},
        )


def _private_roots(directory: Path) -> tuple[Path, Path]:
    return directory / "private" / "Private-MetaDatabase" / "ABD", directory / "repository"


def _security_rows(root: Path, record: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    attestations: list[dict[str, str]] = []
    for attachment in record["attachments"]:
        result = scan_attachment(
            attachment,
            parser_registry_path=root / "parser_registry.json",
            quarantine_rules_path=root / "quarantine_rules.json",
        )
        results.append(
            {
                "attachment_id": result.get("attachment_id"),
                "content_sha256": result.get("content_sha256"),
                "status": result.get("status"),
                "quarantined": result.get("quarantined"),
                "parser_result_recorded": result.get("parser_result_recorded"),
                "trash_eligible": result.get("trash_eligible"),
                "gmail_mutation_performed": result.get("gmail_mutation_performed"),
                "permanent_delete_performed": result.get("permanent_delete_performed"),
            }
        )
        attestations.append(
            {
                "attachment_id": result.get("attachment_id"),
                "content_sha256": result.get("content_sha256"),
                "status": "PASS",
            }
        )
    return results, attestations


def _integrated_flow(root: Path, fixture: Mapping[str, Any]) -> dict[str, Any]:
    p04_fixture = strict_json_load(root / fixture["p04_fixture_path"])
    record = _fixture_mail_record(root, p04_fixture)
    with tempfile.TemporaryDirectory(prefix="abd-s06-stage-review-") as directory_name:
        directory = Path(directory_name)
        archive_root, repository_root = _private_roots(directory)
        preservation = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
        security, attestations = _security_rows(root, record)
        decision = assess_trash_candidate(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=record["gmail_message_id"],
            sender_state=p04_fixture["sender_state"],
            authentication_state=p04_fixture["authentication_state"],
            attachment_security_results=security,
            malware_attestations=attestations,
        )
        dispatch = dispatch_trash_request(decision)
        synthetic_receipt = {
            "status": "TRASHED",
            "gmail_message_id": decision.get("gmail_message_id"),
            "trash_request_key": decision.get("trash_request_key"),
        }
        restore = prepare_restore_request(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=record["gmail_message_id"],
            trash_request_key=decision.get("trash_request_key"),
            trash_receipt=synthetic_receipt,
        )
        audit = audit_daily_mail_state([decision], observed_local_time=SCHEDULED_AUDIT_LOCAL_TIME)
    return {
        "record": record,
        "preservation": preservation,
        "security": security,
        "attestations": attestations,
        "decision": decision,
        "dispatch": dispatch,
        "restore": restore,
        "audit": audit,
    }


def _negative_flow(root: Path, fixture: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    p04_fixture = strict_json_load(root / fixture["p04_fixture_path"])
    record = _fixture_mail_record(root, p04_fixture)
    outcomes: Dict[str, Mapping[str, Any]] = {}
    for label, sender, auth, mutate_attestation, tamper in [
        ("unknown_sender", "UNKNOWN", "PASS", False, False),
        ("failed_authentication", "KNOWN_ALLOWLISTED", "FAIL", False, False),
        ("failed_malware_attestation", "KNOWN_ALLOWLISTED", "PASS", True, False),
        ("tampered_archive", "KNOWN_ALLOWLISTED", "PASS", False, True),
    ]:
        with tempfile.TemporaryDirectory(prefix="abd-s06-stage-negative-") as directory_name:
            directory = Path(directory_name)
            archive_root, repository_root = _private_roots(directory)
            preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            security, attestations = _security_rows(root, record)
            if mutate_attestation:
                attestations = deepcopy(attestations)
                attestations[0]["status"] = "FAIL"
            if tamper:
                target = archive_root / ARCHIVE_DIRECTORY_NAME / "records" / record["gmail_message_id"] / "raw.eml"
                target.unlink()
            outcomes[label] = assess_trash_candidate(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=record["gmail_message_id"],
                sender_state=sender,
                authentication_state=auth,
                attachment_security_results=security,
                malware_attestations=attestations,
            )
    return outcomes


def _check_integrated_flow(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        flow = _integrated_flow(root, fixture)
        security_ok = all(
            row.get("status") == "PARSED_SAFE"
            and row.get("quarantined") is False
            and row.get("parser_result_recorded") is True
            and row.get("trash_eligible") is False
            for row in flow["security"]
        )
        positive_ok = (
            flow["preservation"].get("status") == "PRESERVED_READBACK_VERIFIED"
            and security_ok
            and flow["decision"].get("status") == "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"
            and flow["decision"].get("gmail_method") == "users.messages.trash"
            and flow["decision"].get("gmail_mutation_performed") is False
            and flow["decision"].get("permanent_delete_capability") is False
            and flow["dispatch"].get("status") == "TRASH_REQUEST_READY_NO_MUTATION"
            and flow["dispatch"].get("gmail_mutation_performed") is False
            and flow["restore"].get("status") == "RESTORE_REQUEST_READY_NO_MUTATION"
            and flow["restore"].get("gmail_mutation_performed") is False
            and flow["audit"].get("status") == "AUDIT_PASS"
            and flow["audit"].get("scheduler_started") is False
        )
        no_raw_summary = all(
            "raw_eml" not in json.dumps(value, ensure_ascii=False, sort_keys=True)
            and "content_base64" not in json.dumps(value, ensure_ascii=False, sort_keys=True)
            for value in (flow["decision"], flow["dispatch"], flow["restore"], flow["audit"])
        )
        detail: Any = {
            "preservation": flow["preservation"].get("status"),
            "parser_statuses": [row.get("status") for row in flow["security"]],
            "decision": flow["decision"].get("status"),
            "dispatch": flow["dispatch"].get("status"),
            "restore": flow["restore"].get("status"),
            "audit": flow["audit"].get("status"),
        }
    except Exception as exc:
        positive_ok = no_raw_summary = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06REVIEW-FROZEN-MESSAGE-CROSS-PHASE-REQUEST-ONLY", positive_ok, detail)
    _add(checks, "S06REVIEW-NO-RAW-MAIL-IN-DECISION-SUMMARY", no_raw_summary, detail)


def _check_negative_and_replay(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        negative = _negative_flow(root, fixture)
        negative_ok = all(
            value.get("status") == "KEEP_AND_QUARANTINE"
            and value.get("trash_eligible") is False
            and value.get("gmail_mutation_performed") is False
            and value.get("permanent_delete_performed") is False
            for value in negative.values()
        )
        p04_fixture = strict_json_load(root / fixture["p04_fixture_path"])
        record = _fixture_mail_record(root, p04_fixture)
        with tempfile.TemporaryDirectory(prefix="abd-s06-stage-replay-") as directory_name:
            archive_root, repository_root = _private_roots(Path(directory_name))
            preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            security, attestations = _security_rows(root, record)
            first = assess_trash_candidate(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=record["gmail_message_id"],
                sender_state="KNOWN_ALLOWLISTED",
                authentication_state="PASS",
                attachment_security_results=security,
                malware_attestations=attestations,
            )
            replay = [
                assess_trash_candidate(
                    archive_root=archive_root,
                    repository_root=repository_root,
                    gmail_message_id=record["gmail_message_id"],
                    sender_state="KNOWN_ALLOWLISTED",
                    authentication_state="PASS",
                    attachment_security_results=security,
                    malware_attestations=attestations,
                )
                for _ in range(int(fixture["replay_iterations"]))
            ]
            adverse = [
                assess_trash_candidate(
                    archive_root=archive_root,
                    repository_root=repository_root,
                    gmail_message_id=record["gmail_message_id"],
                    sender_state="UNKNOWN",
                    authentication_state="PASS",
                    attachment_security_results=security,
                    malware_attestations=attestations,
                )
                for _ in range(int(fixture["adverse_perturbation_iterations"]))
            ]
            on_schedule = audit_daily_mail_state([first], observed_local_time="06:00")
            off_schedule = [audit_daily_mail_state([first], observed_local_time=value) for value in ("05:59", "06:01")]
        replay_ok = all(item == first for item in replay)
        adverse_ok = all(
            item == adverse[0]
            and item.get("status") == "KEEP_AND_QUARANTINE"
            and item.get("gmail_mutation_performed") is False
            and item.get("real_time_soak_waited") is False
            for item in adverse
        )
        audit_ok = (
            on_schedule.get("status") == "AUDIT_PASS"
            and on_schedule.get("scheduler_started") is False
            and all(item.get("status") == "AUDIT_OFF_SCHEDULE" and item.get("action") == "ESCALATE" for item in off_schedule)
        )
        detail: Any = {"negative": {key: value.get("status") for key, value in negative.items()}, "replay": len(replay), "adverse": len(adverse)}
    except Exception as exc:
        negative_ok = replay_ok = adverse_ok = audit_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06REVIEW-UNKNOWN-AUTH-MALWARE-TAMPER-KEEP", negative_ok, detail)
    _add(checks, "S06REVIEW-100-REPLAY-DETERMINISTIC-NO-WAIT", replay_ok, detail)
    _add(checks, "S06REVIEW-ONE-IN-TEN-THOUSAND-UNKNOWN-KEEPS", adverse_ok, detail)
    _add(checks, "S06REVIEW-0600-DATA-ONLY-NO-SCHEDULER", audit_ok, detail)


def _check_static_safety(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        worker = (root / "mail_trash_worker.py").read_text(encoding="utf-8")
        tree = ast.parse(worker, filename="mail_trash_worker.py")
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".", 1)[0])
        denied_imports = {"socket", "subprocess", "requests", "urllib", "http", "os", "shutil", "time", "asyncio"}
        no_network_or_process = not (imports & denied_imports)
        banned = (
            "time.sleep(",
            "subprocess.",
            "socket.",
            "requests.",
            "urllib.",
            "os.system(",
            "users.messages.delete",
            "users.messages.batchDelete",
            "users.threads.delete",
        )
        worker_ok = (
            not any(value in worker for value in banned)
            and "PERMANENT_DELETE_CAPABILITY = False" in worker
            and "REAL_TIME_SOAK_REQUIRED = False" in worker
            and "allow_external_mutation: bool = False" in worker
            and "schedule." not in worker
        )
        scope_and_methods_ok = (
            GMAIL_SCOPE == "https://www.googleapis.com/auth/gmail.modify"
            and "users.messages.trash" in ALLOWED_GMAIL_METHODS
            and "users.messages.untrash" in ALLOWED_GMAIL_METHODS
            and "users.messages." + "delete" in DENIED_GMAIL_METHODS
            and "users.messages." + "batchDelete" in DENIED_GMAIL_METHODS
        )
        no_soak = validate_no_real_time_soak() == {
            "real_time_soak_required": False,
            "p02_real_time_soak_required": False,
            "scheduled_audit_local_time": "06:00",
            "audit_evaluated_as_data": True,
            "real_time_wait_performed": False,
            "scheduler_started": False,
        } and PERMANENT_DELETE_CAPABILITY is False and REAL_TIME_SOAK_REQUIRED is False
        detail: Any = {"imports": sorted(imports), "denied": sorted(imports & denied_imports), "scope": GMAIL_SCOPE}
    except Exception as exc:
        no_network_or_process = worker_ok = scope_and_methods_ok = no_soak = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06REVIEW-NO-NETWORK-OR-PROCESS-IMPORT", no_network_or_process, detail)
    _add(checks, "S06REVIEW-NO-SLEEP-OR-PERMANENT-DELETE-CALL", worker_ok, detail)
    _add(checks, "S06REVIEW-GMAIL-SCOPE-AND-METHODS-EXACT", scope_and_methods_ok, detail)
    _add(checks, "S06REVIEW-NO-REAL-TIME-SOAK-BOUNDARY", no_soak, detail)


def _check_no_sensitive_material(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = (CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH)
    problems: list[dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            problems.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            problems.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            problems.append({"path": relative.as_posix(), "kind": "local-path"})
    _add(checks, "S06REVIEW-NO-SECRET-OR-LOCAL-PATH", not problems, problems or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    nodes = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    return {
        "tests": sum(int(node.attrib.get("tests", "0")) for node in nodes),
        "failures": sum(int(node.attrib.get("failures", "0")) for node in nodes),
        "errors": sum(int(node.attrib.get("errors", "0")) for node in nodes),
        "skipped": sum(int(node.attrib.get("skipped", "0")) for node in nodes),
    }


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(path).getroot()
    nodes = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not nodes:
        return False
    for node in nodes:
        if node.attrib.get("timestamp") != "2026-07-19T00:00:00+10:00" or node.attrib.get("time") != "0.000" or "hostname" in node.attrib:
            return False
    return all(testcase.attrib.get("time") == "0.000" and "hostname" not in testcase.attrib for testcase in root.findall(".//testcase"))


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    report_specs = (
        (JUNIT_PATH, "TARGETED", fixture.get("minimum_targeted_pytest_cases")),
        (FULL_JUNIT_PATH, "FULL", fixture.get("minimum_full_pytest_cases")),
        (SIGNED_STATE_JUNIT_PATH, "SIGNED-STATE", fixture.get("minimum_signed_state_pytest_cases")),
    )
    for relative, label, minimum in report_specs:
        path = root / relative
        try:
            summary = _junit_summary(path)
            normalized = _junit_is_normalized(path)
            hashes[relative.as_posix()] = sha256_file(path)
            passed = type(minimum) is int and summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and normalized
            detail: Any = {"minimum": minimum, "summary": summary, "normalized": normalized}
        except Exception as exc:
            passed = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S06REVIEW-%s-PYTEST-REPORT" % label, passed, detail)
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S06REVIEW-PACK-REPORT-STRICT-JSON")
    pack_summary = pack.get("summary") if isinstance(pack, Mapping) else None
    pack_ok = (
        isinstance(pack, Mapping)
        and pack.get("status") == "PASS"
        and isinstance(pack_summary, Mapping)
        and pack_summary.get("failed") == 0
        and pack_summary.get("passed") == pack_summary.get("checks")
    )
    _add(checks, "S06REVIEW-TASKPACK-PASS", pack_ok, pack_summary if isinstance(pack_summary, Mapping) else "unavailable")
    scan_path = root / SCAN_REPORT_PATH
    try:
        scan_text = scan_path.read_text(encoding="utf-8")
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(scan_path)
        scan_ok = "PASS" in scan_text and "FAIL" not in scan_text
        detail = "scan receipt present"
    except Exception as exc:
        scan_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, detail)


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root / CONTRACT_PATH, checks, "S06REVIEW-CONTRACT-STRICT-JSON")
    findings = _safe_load(root / FINDINGS_PATH, checks, "S06REVIEW-FINDINGS-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S06REVIEW-FIXTURE-STRICT-JSON")
    _review_pin_checks(root, checks, hashes)
    if isinstance(contract, Mapping) and isinstance(findings, Mapping) and isinstance(fixture, Mapping):
        _check_contract_and_findings(contract, findings, fixture, checks)
        _check_baseline(root, contract, checks, hashes)
        _check_taskpack(root, checks)
        _check_phase_receipts_and_oracles(root, contract, fixture, checks, verify_git_history=_verify_git_history)
        _check_integrated_flow(root, fixture, checks)
        _check_negative_and_replay(root, fixture, checks)
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S06REVIEW-REQUIRED-INPUTS-AVAILABLE", False, "review contract, findings, or fixture unavailable")
    _check_static_safety(root, checks)
    _check_no_sensitive_material(root, checks)
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS" if not failed else "FAIL",
        "stage_status": "S06_WHOLE_STAGE_REVIEW_PASS" if not failed else "S06_WHOLE_STAGE_REVIEW_FAIL",
        "decision": "S06_WHOLE_STAGE_REVIEW_PASS" if not failed else "S06_WHOLE_STAGE_REVIEW_BLOCKED_FAIL_CLOSED",
        "release_status": "NOT_READY_S07_TO_S19_AND_GMAIL_RUNTIME_ACTIVATION_REQUIRED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S06/GITHUB_STAGE_UPLOAD_READY" if not failed else "S06/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S06_STAGE_REVIEW_CANDIDATE_VALID" if result["status"] == "PASS" else "S06_STAGE_REVIEW_CANDIDATE_INVALID",
        "summary": result["summary"],
        "next": result["next"],
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, str]] = {}
    for relative in ROLLBACK_ARTIFACTS:
        try:
            before = sha256_file(root / relative)
            after = sha256_file(root / relative)
            artifacts[relative.as_posix()] = {"status": "PASS" if before == after else "FAIL", "before": before, "after": after}
        except Exception as exc:
            artifacts[relative.as_posix()] = {"status": "FAIL", "detail": "%s: %s" % (type(exc).__name__, exc)}
    status = "PASS" if len(artifacts) == len(ROLLBACK_ARTIFACTS) and all(row.get("status") == "PASS" for row in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_GMAIL_RUNTIME_ADAPTER_KEEP_ARCHIVE_AND_SIGNED_PHASE_EVIDENCE",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "gmail_account_or_api_accessed": False,
        "gmail_mutation_performed": False,
        "permanent_delete_performed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        Path("machine/tests/fixtures/S06_P04.json"),
        Path("machine/evidence/S04/STAGE_REVIEW/github_delivery_receipt.json"),
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/model_system_card.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
    ]
    for phase in ["P01", "P02", "P03", "P04"]:
        paths.extend([Path("machine/evidence/EVD-S06-%s.json" % phase), Path("machine/evidence/EVD-S06-%s_rollback.json" % phase)])
    return {relative.as_posix(): sha256_file(root / relative) for relative in paths}


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
    *,
    _verify_git_history: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    flow_summary: Mapping[str, Any]
    replay_summary: Mapping[str, Any]
    try:
        fixture = strict_json_load(root / FIXTURE_PATH)
        flow = _integrated_flow(root, fixture)
        negative = _negative_flow(root, fixture)
        flow_summary = {
            "preservation_status": flow["preservation"].get("status"),
            "attachment_security_statuses": [row.get("status") for row in flow["security"]],
            "malware_attestation_mode": "FROZEN_SYNTHETIC_ATTESTATION_NOT_A_LIVE_AV_CLEARANCE",
            "trash_decision": flow["decision"].get("status"),
            "dispatch_status": flow["dispatch"].get("status"),
            "restore_status": flow["restore"].get("status"),
            "audit_status": flow["audit"].get("status"),
            "negative_statuses": {key: value.get("status") for key, value in negative.items()},
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
        }
        replay_summary = {
            "iterations": fixture["adverse_perturbation_iterations"],
            "action": "UNKNOWN_SENDER_KEEP_AND_QUARANTINE",
            "deterministic": True,
            "real_time_waited": False,
            "result_sha256": _sha256_bytes(_json_bytes(negative["unknown_sender"])),
        }
    except Exception as exc:
        flow_summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
        replay_summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "stage_status": validation["stage_status"],
        "decision": validation["decision"],
        "validation": validation,
        "cross_phase_flow_summary": flow_summary,
        "deterministic_replay": replay_summary,
        "no_real_time_soak": validate_no_real_time_soak(),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "NOT_READY_S07_TO_S19_AND_GMAIL_RUNTIME_ACTIVATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S06/stage_review_test.py --junitxml=machine/evidence/S06/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S04/stage_review_test.py tests/S06/P01_test.py tests/S06/P02_test.py tests/S06/P03_test.py tests/S06/P04_test.py tests/S06/stage_review_test.py --junitxml=machine/evidence/S06/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/STAGE_REVIEW/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S06/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S06 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": _input_hashes(root),
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S06 stage review validates frozen synthetic mail flow and fail-closed boundaries only.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
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


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    rows = [row for row in rows if row.get("id") != "INDEX-S06-STAGE-REVIEW"]
    rows.append(
        {
            "id": "INDEX-S06-STAGE-REVIEW",
            "kind": "STAGE_REVIEW_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S06/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S06/STAGE_REVIEW_REMEDIATION_REQUIRED",
            "verified_at": FIXED_CLOCK,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_stage6_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_directory = (root / "machine/evidence").resolve()
    if evidence_dir != expected_directory:
        raise Stage6ReviewContractError("S06 review evidence must be written to the project machine/evidence directory")
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = root / EVIDENCE_PATH
    rollback_path = root / ROLLBACK_EVIDENCE_PATH
    _atomic_write(evidence_path, _json_bytes(evidence))
    _atomic_write(rollback_path, _json_bytes(rollback))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = dict(evidence)
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_stage_review_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S06REVIEW-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S06REVIEW-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S06-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S06/GITHUB_STAGE_UPLOAD_READY"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S06REVIEW-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        mismatches: list[dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                mismatches.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                historical = _historical_receipt_input_hash(root, relative, verify_git_history=verify_git_history)
                if historical != expected:
                    mismatches.append({"path": relative, "expected": str(expected), "actual": actual, "historical": historical})
        _add(checks, "S06REVIEW-EXISTING-INPUT-HASHES", not mismatches, mismatches or "all inputs match")
        expected_code_hash = evidence.get("hashes", {}).get("code")
        current_code_hash = _current_code_hash(root)
        historical_code_hash = _historical_code_hash(root, STAGE_REVIEW_COMMIT, verify_git_history=verify_git_history)
        code_hash_ok = current_code_hash == expected_code_hash or (
            _receipt_commit_is_ancestor(root, verify_git_history=verify_git_history) and historical_code_hash == expected_code_hash
        )
        _add(
            checks,
            "S06REVIEW-EXISTING-CODE-HASH",
            code_hash_ok,
            {"expected": expected_code_hash, "current": current_code_hash, "historical": historical_code_hash},
        )
    else:
        _add(checks, "S06REVIEW-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S06-STAGE-REVIEW-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("gmail_mutation_performed") is False
            and rollback.get("permanent_delete_performed") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S06REVIEW-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S06REVIEW-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    _add(checks, "S06REVIEW-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "",
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S06/GITHUB_STAGE_UPLOAD_READY" if not failed else "S06/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_PATH",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINDINGS_PATH",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_PATH",
    "PINNED_REVIEW_ARTIFACT_HASHES",
    "REVIEW_ID",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "SIGNED_STATE_JUNIT_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "TEST_PATH",
    "Stage6ReviewContractError",
    "_current_code_hash",
    "_junit_is_normalized",
    "_junit_summary",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_stage_review_evidence",
    "write_stage6_review_evidence",
]
