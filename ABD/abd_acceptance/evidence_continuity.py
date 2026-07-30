"""Independent deterministic acceptance oracle for ABD S07/P04.

The module joins the frozen Task Pack facts, the evidence index and the
content-addressed artifact manifest into a queryable, fail-closed chain.  It
does not access a market, account, Gmail, OVH, Cloudflare, or any network
endpoint; it cannot generate a recommendation, submit an order, or wait for a
real-time soak period.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .budget import render_scan_report, scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .ledger_trace import verify_existing_phase_evidence as verify_s07_p03_evidence
from .legacy_receipt_compatibility import approved_successor_sha256


CONTRACT_ID = "AC-S07-P04"
REQUIREMENT_ID = "REQ-S07-P04"
STAGE_ID = "S07"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
ARTIFACT_MANIFEST_PATH = Path("machine/evidence/artifact_manifest.json")
SHA256SUMS_PATH = Path("machine/evidence/SHA256SUMS")
RELEASE_MANIFEST_PATH = Path("machine/evidence/release_manifest.json")
FINAL_ACCEPTANCE_PATH = Path("machine/evidence/final_acceptance.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S07_P04.json")
TEST_PATH = Path("tests/S07/P04_test.py")
ORACLE_PATH = Path("abd_acceptance/evidence_continuity.py")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S07-P03_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P04_rollback.json")
JUNIT_PATH = Path("machine/evidence/S07/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S07/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S07/P04/paid_dependency_scan.txt")

PHASE_ARTIFACT_PATHS = {
    "ART-S07-P04-01": EVIDENCE_INDEX_PATH,
    "ART-S07-P04-02": TRACEABILITY_PATH,
    "ART-S07-P04-03": ARTIFACT_MANIFEST_PATH,
}

PINNED_PHASE_HASHES: Dict[str, str] = {
    FIXTURE_PATH.as_posix(): "1867c3a9e8ea40b6322c3647f0405d415a4e79fe5f5ec4479299146d140be5a7",
    TEST_PATH.as_posix(): "3e658a3d13641f478c750603f12cf69e3db66240ddeb2f9445245e3bf8114fca",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    REQUIREMENTS_PATH.as_posix(): "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    CONTRACTS_PATH.as_posix(): "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    TASK_GRAPH_PATH.as_posix(): "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    TRACEABILITY_PATH.as_posix(): "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    RELEASE_MANIFEST_PATH.as_posix(): "42a1bda4cc7eb39b0d906d3f3aa5c58fd0c217384508e2602af746008f2be090",
    FINAL_ACCEPTANCE_PATH.as_posix(): "2e1b0125b764849fc075bc66c82fd992626444e35c61acf9f0e7ffa362027376",
    "machine/evidence/roadmap_stage_phase.md": "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de",
    P03_EVIDENCE_PATH.as_posix(): "ca87f049463efa377e18ada24ba7cdeb1cf2c1aff920b9d872794d4146728fa9",
    P03_ROLLBACK_PATH.as_posix(): "c51a5f368b3a2aacfce49207c090e84c4e3344c9beb4742923a2cdf0a93a2faf",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "864a0014bea5041e9532a3390654e9f6367f1f04832b2366ac86b50a0982e697"
LEGACY_EVIDENCE_CODE_HASH = "20a388d41762688b7336698a0069f5c2a6fa817fa7d78436f3ee7d86e460263f"
FULL_REGRESSION_TEST_MINIMUM = 5028
REQUIRED_COVERAGE = Decimal("1.0000")

ROLLBACK_ARTIFACTS = (
    EVIDENCE_INDEX_PATH,
    TRACEABILITY_PATH,
    ARTIFACT_MANIFEST_PATH,
    SHA256SUMS_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
)

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "financial_return_verified_or_guaranteed": False,
    "gmail_account_or_api_accessed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submitted_confirmed_or_retried": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "real_account_balance_read_or_written": False,
    "real_time_soak_waited": False,
    "recommendation_generated_or_enabled": False,
}

_EXCLUDED_MANIFEST_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__"}
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")


class EvidenceContinuityError(ValueError):
    """Raised when a continuity input is malformed or internally inconsistent."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _portable(path: Path) -> str:
    """Render evidence paths without leaking an operator-specific absolute path."""

    text = path.as_posix()
    for anchor in ("/machine/", "/tests/", "/abd_acceptance/"):
        if anchor in text:
            return anchor.lstrip("/") + text.split(anchor, 1)[1]
    return path.name


def _strict_pairs(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceContinuityError("duplicate JSON key: %s" % key)
        value[key] = item
    return value


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise EvidenceContinuityError("blank JSONL line: %d" % line_number)
        try:
            value = json.loads(line, object_pairs_hook=_strict_pairs)
        except Exception as exc:
            raise EvidenceContinuityError("invalid JSONL line %d: %s" % (line_number, exc)) from exc
        if not isinstance(value, dict):
            raise EvidenceContinuityError("JSONL line %d must be an object" % line_number)
        rows.append(value)
    if not rows:
        raise EvidenceContinuityError("evidence index must not be empty")
    return rows


def _safe_relative(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise EvidenceContinuityError("path must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise EvidenceContinuityError("unsafe path: %s" % value)
    return path


def _unique_mapping(rows: Sequence[Mapping[str, Any]], key: str, label: str) -> Dict[str, Mapping[str, Any]]:
    values: Dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise EvidenceContinuityError("%s has missing %s" % (label, key))
        if value in values:
            raise EvidenceContinuityError("%s has duplicate %s: %s" % (label, key, value))
        values[value] = row
    return values


def _row(rows: Sequence[Mapping[str, Any]], identifier: str, key: str = "id") -> Mapping[str, Any]:
    matches = [row for row in rows if row.get(key) == identifier]
    if len(matches) != 1:
        raise EvidenceContinuityError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _current_code_hash(root: Path) -> str:
    payload = ORACLE_PATH.as_posix().encode("utf-8") + b"\0" + (root / ORACLE_PATH).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8")) if normalized != text else "NORMALIZATION_FAILED"


def _junit_summary(path: Path) -> Dict[str, int]:
    tree = ElementTree.parse(path)
    root = tree.getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise EvidenceContinuityError("unexpected JUnit root")
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise EvidenceContinuityError("JUnit has no suites")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for field in totals:
            totals[field] += int(suite.attrib.get(field, "0"))
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


def _expected_project_files(root: Path) -> List[Path]:
    expected: List[Path] = []
    manifest = (root / ARTIFACT_MANIFEST_PATH).resolve()
    sums = (root / SHA256SUMS_PATH).resolve()
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        if any(part in _EXCLUDED_MANIFEST_PARTS for part in relative.parts):
            continue
        if candidate.suffix in {".pyc", ".pyo"} or candidate.name == ".DS_Store":
            continue
        if candidate.resolve() in {manifest, sums}:
            continue
        expected.append(candidate)
    return sorted(expected, key=lambda path: path.relative_to(root).as_posix())


def _parse_sums(path: Path) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise EvidenceContinuityError("invalid SHA256SUMS line %d" % line_number)
        digest, relative = match.groups()
        _safe_relative(relative)
        if relative in rows:
            raise EvidenceContinuityError("duplicate SHA256SUMS path: %s" % relative)
        rows[relative] = digest
    if not rows:
        raise EvidenceContinuityError("SHA256SUMS must not be empty")
    return rows


def _as_decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+\.\d{4}", value):
        raise EvidenceContinuityError("coverage must be an exact four-place decimal string")
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise EvidenceContinuityError("coverage is invalid") from exc
    if not decimal.is_finite():
        raise EvidenceContinuityError("coverage must be finite")
    return decimal


def evaluate_link_snapshot(snapshot: Mapping[str, Any], coverage: Any) -> Dict[str, Any]:
    """Evaluate a normalized in-memory link graph without reading external state."""

    if not isinstance(snapshot, Mapping):
        raise EvidenceContinuityError("link snapshot must be an object")
    raw_orphans = snapshot.get("orphans")
    if not isinstance(raw_orphans, Mapping):
        raise EvidenceContinuityError("link snapshot requires an orphan map")
    normalized_orphans: Dict[str, List[str]] = {}
    for category, values in raw_orphans.items():
        if not isinstance(category, str) or not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise EvidenceContinuityError("orphan map must contain string arrays")
        normalized_orphans[category] = sorted(set(values))
    decimal = _as_decimal(coverage)
    reason_codes: List[str] = []
    if decimal < REQUIRED_COVERAGE:
        reason_codes.append("LINK_COVERAGE_BELOW_ONE")
    elif decimal > REQUIRED_COVERAGE:
        reason_codes.append("LINK_COVERAGE_ABOVE_ONE")
    for category in sorted(normalized_orphans):
        if normalized_orphans[category]:
            reason_codes.append("ORPHAN_%s" % category.upper())
    status = "CONTINUITY_VERIFIED_NO_ACTION" if not reason_codes else "CONTINUITY_REJECTED_NO_ACTION"
    unsigned = {
        "status": status,
        "coverage": format(decimal, ".4f"),
        "required_coverage": format(REQUIRED_COVERAGE, ".4f"),
        "orphans": normalized_orphans,
        "reason_codes": reason_codes,
        "external_network_used": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "odds_treatment": "NOT_APPLICABLE_CONTINUITY_ONLY",
    }
    return dict(unsigned, output_sha256=_sha256_bytes(_json_bytes(unsigned)))


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S07P04-PIN-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P04-PIN-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))
    hashes[ORACLE_PATH.as_posix()] = sha256_file(root / ORACLE_PATH)
    actual_self = _structural_self_hash(root)
    _add(
        checks,
        "S07P04-ORACLE-STRUCTURAL-SELF-HASH",
        STRUCTURAL_SELF_NORMALIZED_SHA256 != "TO_BE_FILLED" and actual_self == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": actual_self},
    )
    for relative, expected in PINNED_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S07P04-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P04-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))


def _check_fixture(root: Path, checks: List[Dict[str, Any]]) -> Mapping[str, Any] | None:
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S07P04-FIXTURE-STRICT-JSON")
    if not isinstance(fixture, Mapping):
        return None
    expected_fields = {
        "adverse_odds_ticks",
        "adverse_replay_count",
        "cases",
        "contract_id",
        "expected_counts",
        "expected_next",
        "expected_oracle_check_minimum",
        "expected_positive_output_sha256",
        "expected_source_version_sha256",
        "external_effect_boundary",
        "fixed_clock",
        "parameter_version_sha256",
        "phase_id",
        "predecessor",
        "replay_count",
        "schema_version",
        "stage_id",
        "target_test_minimum",
    }
    cases = fixture.get("cases")
    case_ids = [item.get("case_id") for item in cases] if isinstance(cases, list) and all(isinstance(item, Mapping) for item in cases) else []
    shape_ok = (
        set(fixture) == expected_fields
        and fixture.get("schema_version") == "1.0.0"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("stage_id") == STAGE_ID
        and fixture.get("phase_id") == PHASE_ID
        and fixture.get("fixed_clock") == FIXED_CLOCK
        and fixture.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and isinstance(fixture.get("replay_count"), int)
        and fixture.get("replay_count") >= 100
        and isinstance(fixture.get("adverse_replay_count"), int)
        and fixture.get("adverse_replay_count") >= 10000
        and case_ids
        == [
            "POSITIVE_EXACT_CHAIN",
            "BOUNDARY_COVERAGE_MINUS_0001",
            "BOUNDARY_COVERAGE_EXACT",
            "BOUNDARY_COVERAGE_PLUS_0001",
            "NEGATIVE_ORPHAN_TASK",
            "FAULT_ORPHAN_EVIDENCE_INDEX",
        ]
        and fixture.get("adverse_odds_ticks") == ["-0.0001", "0.0001"]
        and fixture.get("parameter_version_sha256") == sha256_file(root / "machine/facts/parameters.json")
        and fixture.get("expected_source_version_sha256") == sha256_file(root / "machine/facts/canonical_facts.json")
    )
    _add(checks, "S07P04-PRODUCTION-EQUIVALENT-FIXTURE", shape_ok, {"case_ids": case_ids})
    return fixture


def _load_taskpack_inputs(root: Path, checks: List[Dict[str, Any]]) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]], List[Mapping[str, Any]], List[Mapping[str, Any]], List[Mapping[str, Any]]] | None:
    requirements = _safe_load(root / REQUIREMENTS_PATH, checks, "S07P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / CONTRACTS_PATH, checks, "S07P04-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root / TASK_GRAPH_PATH, checks, "S07P04-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / TRACEABILITY_PATH, checks, "S07P04-TRACEABILITY-STRICT-JSON")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S07P04-EVIDENCE-INDEX-STRICT-JSONL", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S07P04-EVIDENCE-INDEX-STRICT-JSONL", False, "%s: %s" % (type(exc).__name__, exc))
        index = []
    tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
    if not all(isinstance(value, list) for value in (requirements, contracts, tasks, traceability, index)):
        _add(checks, "S07P04-TASKPACK-LISTS-AVAILABLE", False, "one or more Task Pack collections are unavailable")
        return None
    if not all(all(isinstance(row, Mapping) for row in value) for value in (requirements, contracts, tasks, traceability, index)):
        _add(checks, "S07P04-TASKPACK-ROWS-OBJECTS", False, "all Task Pack rows must be objects")
        return None
    _add(checks, "S07P04-TASKPACK-LISTS-AVAILABLE", True, "all collections are available")
    return list(requirements), list(contracts), list(tasks), list(traceability), list(index)


def _index_contract_id(row: Mapping[str, Any]) -> str | None:
    identifier = row.get("id")
    if not isinstance(identifier, str) or not identifier.startswith("INDEX-AC-"):
        return None
    return identifier[len("INDEX-") :]


def _taskpack_orphans(
    requirements: Sequence[Mapping[str, Any]],
    contracts: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
    traceability: Sequence[Mapping[str, Any]],
    index: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, List[str]], Dict[str, Any]]:
    requirements_by_id = _unique_mapping(requirements, "id", "requirements")
    contracts_by_id = _unique_mapping(contracts, "id", "contracts")
    tasks_by_id = _unique_mapping(tasks, "id", "tasks")
    trace_by_requirement = _unique_mapping(traceability, "requirement_id", "traceability")
    index_by_id = _unique_mapping(index, "id", "evidence index")
    orphans: Dict[str, List[str]] = {
        "requirements": [],
        "contracts": [],
        "tasks": [],
        "traceability": [],
        "evidence": [],
        "artifacts": [],
        "release": [],
    }
    for requirement_id, requirement in requirements_by_id.items():
        contract_id = requirement.get("primary_acceptance_criteria_id")
        if not isinstance(contract_id, str) or contract_id not in contracts_by_id:
            orphans["requirements"].append(requirement_id)
            continue
        contract = contracts_by_id[contract_id]
        trace = trace_by_requirement.get(requirement_id)
        if trace is None:
            orphans["requirements"].append(requirement_id)
            continue
        if contract.get("requirement_id") != requirement_id or trace.get("acceptance_criteria_id") != contract_id:
            orphans["traceability"].append(requirement_id)
        task_ids = trace.get("task_ids")
        expected_test_ids = [item.get("id") for item in contract.get("tests", []) if isinstance(item, Mapping)]
        if (
            not isinstance(task_ids, list)
            or not task_ids
            or trace.get("test_ids") != expected_test_ids
            or not isinstance(trace.get("evidence_id"), str)
            or not isinstance(trace.get("artifact_ids"), list)
            or not trace.get("artifact_ids")
        ):
            orphans["traceability"].append(requirement_id)
        else:
            for task_id in task_ids:
                task = tasks_by_id.get(task_id)
                if task is None:
                    orphans["tasks"].append(str(task_id))
                    continue
                if requirement_id not in task.get("requirement_ids", []) or contract_id not in task.get("acceptance_criteria_ids", []):
                    orphans["tasks"].append(task_id)
        index_id = "INDEX-%s" % contract_id
        row = index_by_id.get(index_id)
        expected_artifact = "machine/evidence/%s.json" % trace.get("evidence_id")
        if row is None:
            orphans["evidence"].append(index_id)
        elif row.get("status") == "PLANNED":
            if (
                row.get("acceptance_contract_id") != contract_id
                or row.get("requirement_id") != requirement_id
                or row.get("expected_artifact") != expected_artifact
                or row.get("pass_gate") != contract.get("pass_gate")
            ):
                orphans["evidence"].append(index_id)
        elif row.get("status") == "PASS":
            actual = row.get("actual_artifact")
            digest = row.get("artifact_sha256")
            if row.get("contract_id") not in {contract_id, None} or actual != expected_artifact or not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                orphans["evidence"].append(index_id)
        else:
            orphans["evidence"].append(index_id)
    for contract_id, contract in contracts_by_id.items():
        requirement_id = contract.get("requirement_id")
        if requirement_id not in requirements_by_id or requirements_by_id[requirement_id].get("primary_acceptance_criteria_id") != contract_id:
            orphans["contracts"].append(contract_id)
    for task_id, task in tasks_by_id.items():
        requirement_ids = task.get("requirement_ids")
        contract_ids = task.get("acceptance_criteria_ids")
        if not isinstance(requirement_ids, list) or not isinstance(contract_ids, list) or len(requirement_ids) != 1 or len(contract_ids) != 1:
            orphans["tasks"].append(task_id)
            continue
        requirement_id, contract_id = requirement_ids[0], contract_ids[0]
        trace = trace_by_requirement.get(requirement_id)
        if (
            requirement_id not in requirements_by_id
            or contract_id not in contracts_by_id
            or trace is None
            or task_id not in trace.get("task_ids", [])
        ):
            orphans["tasks"].append(task_id)
    for requirement_id in trace_by_requirement:
        if requirement_id not in requirements_by_id:
            orphans["traceability"].append(requirement_id)
    expected_index_ids = {"INDEX-%s" % contract_id for contract_id in contracts_by_id}
    actual_index_ids = {identifier for identifier in index_by_id if identifier.startswith("INDEX-AC-")}
    for identifier in sorted(expected_index_ids - actual_index_ids):
        orphans["evidence"].append(identifier)
    for identifier in sorted(actual_index_ids - expected_index_ids):
        orphans["evidence"].append(identifier)
    for key in orphans:
        orphans[key] = sorted(set(orphans[key]))
    return orphans, {
        "requirements_by_id": requirements_by_id,
        "contracts_by_id": contracts_by_id,
        "tasks_by_id": tasks_by_id,
        "trace_by_requirement": trace_by_requirement,
        "index_by_id": index_by_id,
    }


def _check_taskpack_continuity(
    root: Path,
    fixture: Mapping[str, Any] | None,
    checks: List[Dict[str, Any]],
) -> Tuple[Dict[str, List[str]], Dict[str, Any]] | None:
    loaded = _load_taskpack_inputs(root, checks)
    if loaded is None:
        return None
    requirements, contracts, tasks, traceability, index = loaded
    try:
        orphans, lookup = _taskpack_orphans(requirements, contracts, tasks, traceability, index)
        expected_counts = fixture.get("expected_counts") if isinstance(fixture, Mapping) else {}
        counts_ok = (
            isinstance(expected_counts, Mapping)
            and len(requirements) == expected_counts.get("requirements")
            and len(contracts) == expected_counts.get("contracts")
            and len(tasks) == expected_counts.get("tasks")
            and len(traceability) == expected_counts.get("traceability")
            and len(index) == expected_counts.get("index")
        )
        _add(
            checks,
            "S07P04-ALL-LINK-COLLECTIONS-COVERED",
            counts_ok and not any(orphans.values()),
            {"counts": {"requirements": len(requirements), "contracts": len(contracts), "tasks": len(tasks), "traceability": len(traceability), "index": len(index)}, "orphans": orphans},
        )
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        p04_tasks = [row for row in tasks if row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        p04_index = _row(index, "INDEX-%s" % CONTRACT_ID)
        scope_ok = (
            requirement.get("scope") == ["evidence_index.jsonl", "traceability_matrix.json", "artifact_manifest.json"]
            and requirement.get("target") == "需求→任务→测试→证据→制品无孤儿。"
            and contract.get("pass_gate") == requirement.get("target")
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S07-P04 --evidence machine/evidence"
            and [item.get("id") for item in contract.get("tests", [])] == ["TEST-S07-P04", "TEST-S07-P04-BOUNDARY", "TEST-S07-P04-REPLAY"]
            and [item.get("id") for item in p04_tasks] == ["T-S07-P04-01", "T-S07-P04-02", "T-S07-P04-03"]
            and trace.get("evidence_id") == "EVD-S07-P04"
            and trace.get("artifact_ids") == list(PHASE_ARTIFACT_PATHS)
            and p04_index.get("status") in {"PLANNED", "PASS"}
        )
        _add(
            checks,
            "S07P04-TASKPACK-SCOPE-TRACE-EXACT",
            scope_ok,
            {"tasks": [item.get("id") for item in p04_tasks], "index_status": p04_index.get("status"), "trace": trace},
        )
        return orphans, {"lookup": lookup, "p04_index": p04_index, "p04_trace": trace}
    except Exception as exc:
        _add(checks, "S07P04-ALL-LINK-COLLECTIONS-COVERED", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_manifest(root: Path, checks: List[Dict[str, Any]], *, p04_index_status: str | None) -> Dict[str, Any] | None:
    manifest = _safe_load(root / ARTIFACT_MANIFEST_PATH, checks, "S07P04-ARTIFACT-MANIFEST-STRICT-JSON")
    try:
        sums = _parse_sums(root / SHA256SUMS_PATH)
        _add(checks, "S07P04-SHA256SUMS-STRICT", True, SHA256SUMS_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S07P04-SHA256SUMS-STRICT", False, "%s: %s" % (type(exc).__name__, exc))
        sums = {}
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("files"), list):
        _add(checks, "S07P04-ARTIFACT-MANIFEST-COVERAGE", False, "manifest files unavailable")
        return None
    try:
        rows = manifest["files"]
        paths: Dict[str, Mapping[str, Any]] = {}
        errors: List[Dict[str, str]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise EvidenceContinuityError("manifest row must be an object")
            relative = row.get("path")
            candidate = _safe_relative(relative)
            key = candidate.as_posix()
            if key in paths:
                raise EvidenceContinuityError("duplicate manifest path: %s" % key)
            paths[key] = row
            actual_path = root / candidate
            actual_hash = sha256_file(actual_path) if actual_path.is_file() else "MISSING"
            if (
                row.get("sha256") != actual_hash
                or row.get("bytes") != (actual_path.stat().st_size if actual_path.is_file() else None)
                or sums.get(key) != actual_hash
            ):
                errors.append({"path": key, "actual": actual_hash})
        expected_paths = {path.relative_to(root).as_posix() for path in _expected_project_files(root)}
        actual_paths = set(paths)
        checksum_expected = expected_paths | {ARTIFACT_MANIFEST_PATH.as_posix()}
        required_paths = {
            EVIDENCE_INDEX_PATH.as_posix(),
            TRACEABILITY_PATH.as_posix(),
            FIXTURE_PATH.as_posix(),
            TEST_PATH.as_posix(),
            ORACLE_PATH.as_posix(),
            P03_EVIDENCE_PATH.as_posix(),
        }
        if p04_index_status == "PASS":
            required_paths.update(
                {
                    EVIDENCE_PATH.as_posix(),
                    ROLLBACK_EVIDENCE_PATH.as_posix(),
                    JUNIT_PATH.as_posix(),
                    FULL_JUNIT_PATH.as_posix(),
                    SCAN_REPORT_PATH.as_posix(),
                }
            )
        coverage_ok = (
            manifest.get("schema_version") == "1.0.0"
            and manifest.get("version") == VERSION
            and manifest.get("file_count") == len(rows) == len(expected_paths)
            and [row.get("path") for row in rows] == sorted(actual_paths)
            and actual_paths == expected_paths
            and set(sums) == checksum_expected
            and sums.get(ARTIFACT_MANIFEST_PATH.as_posix()) == sha256_file(root / ARTIFACT_MANIFEST_PATH)
            and required_paths <= actual_paths
            and not errors
        )
        _add(
            checks,
            "S07P04-ARTIFACT-MANIFEST-COVERAGE",
            coverage_ok,
            {"manifest_files": len(rows), "expected_files": len(expected_paths), "errors": errors, "missing_required": sorted(required_paths - actual_paths)},
        )
        artifact_links = {
            artifact_id: {
                "path": path.as_posix(),
                "manifested": path.as_posix() in actual_paths if path != ARTIFACT_MANIFEST_PATH else True,
                "checksum_protected": path.as_posix() in sums,
            }
            for artifact_id, path in PHASE_ARTIFACT_PATHS.items()
        }
        _add(
            checks,
            "S07P04-PHASE-ARTIFACT-LINKS-EXACT",
            all(item["manifested"] and item["checksum_protected"] for item in artifact_links.values()),
            artifact_links,
        )
        return {"manifest": manifest, "paths": paths, "sums": sums, "artifact_links": artifact_links}
    except Exception as exc:
        _add(checks, "S07P04-ARTIFACT-MANIFEST-COVERAGE", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_pass_evidence_artifacts(
    root: Path,
    continuity: Tuple[Dict[str, List[str]], Dict[str, Any]] | None,
    manifest: Mapping[str, Any] | None,
    checks: List[Dict[str, Any]],
) -> None:
    if continuity is None or manifest is None:
        _add(checks, "S07P04-PASS-EVIDENCE-ARTIFACTS-RESOLVABLE", False, "continuity or manifest unavailable")
        return
    lookup = continuity[1]["lookup"]
    paths = manifest.get("paths", {})
    errors: List[Dict[str, str]] = []
    for contract_id in sorted(lookup["contracts_by_id"]):
        row = lookup["index_by_id"].get("INDEX-%s" % contract_id)
        if not isinstance(row, Mapping) or row.get("status") != "PASS":
            continue
        actual = row.get("actual_artifact")
        expected = "machine/evidence/%s.json" % lookup["trace_by_requirement"][lookup["contracts_by_id"][contract_id]["requirement_id"]]["evidence_id"]
        if not isinstance(actual, str) or actual != expected:
            errors.append({"contract": contract_id, "actual": str(actual)})
            continue
        artifact = root / _safe_relative(actual)
        digest = sha256_file(artifact) if artifact.is_file() else "MISSING"
        if row.get("artifact_sha256") != digest or actual not in paths:
            errors.append({"contract": contract_id, "actual": digest})
    _add(checks, "S07P04-PASS-EVIDENCE-ARTIFACTS-RESOLVABLE", not errors, errors or "all PASS evidence artifacts resolve")


def _check_release_link(root: Path, manifest: Mapping[str, Any] | None, checks: List[Dict[str, Any]]) -> None:
    release = _safe_load(root / RELEASE_MANIFEST_PATH, checks, "S07P04-RELEASE-MANIFEST-STRICT-JSON")
    final = _safe_load(root / FINAL_ACCEPTANCE_PATH, checks, "S07P04-FINAL-ACCEPTANCE-STRICT-JSON")
    if not isinstance(release, Mapping) or not isinstance(final, Mapping) or manifest is None:
        _add(checks, "S07P04-RELEASE-LINK-HONEST-AND-MANIFESTED", False, "release inputs unavailable")
        return
    paths = set(manifest.get("paths", {}))
    financial = release.get("financial")
    runtime = release.get("runtime")
    keys = release.get("key_artifacts")
    ok = (
        release.get("product") == "ABD"
        and release.get("status") == "FINAL_ACCEPTANCE_DELIVERY"
        and isinstance(financial, Mapping)
        and financial.get("incremental_cash_budget_aud") == "0.00"
        and financial.get("return_guaranteed") is False
        and isinstance(runtime, Mapping)
        and runtime.get("primary") == "OVH Singapore VPS-1"
        and isinstance(keys, list)
        and all(isinstance(path, str) and path in paths for path in keys)
        and final.get("decision") == "READY_FOR_FINAL_DEVELOPMENT_TASKPACK_HANDOFF"
        and "不能" in str(final.get("explicit_non_guarantee"))
    )
    _add(
        checks,
        "S07P04-RELEASE-LINK-HONEST-AND-MANIFESTED",
        ok,
        {"release_status": release.get("status"), "final_decision": final.get("decision"), "key_artifacts": keys},
    )


def _check_predecessor(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    try:
        result = verify_s07_p03_evidence(root, verify_git_history=verify_git_history)
        predecessor = fixture.get("predecessor") if isinstance(fixture, Mapping) else None
        ok = (
            isinstance(predecessor, Mapping)
            and predecessor.get("contract_id") == "AC-S07-P03"
            and predecessor.get("evidence_path") == P03_EVIDENCE_PATH.as_posix()
            and predecessor.get("rollback_path") == P03_ROLLBACK_PATH.as_posix()
            and predecessor.get("evidence_sha256") == sha256_file(root / P03_EVIDENCE_PATH)
            and predecessor.get("rollback_sha256") == sha256_file(root / P03_ROLLBACK_PATH)
            and predecessor.get("next") == "S07/P04_READY_NOT_STARTED"
            and result.get("status") == "PASS"
        )
        _add(checks, "S07P04-P03-PREDECESSOR-PASS", ok, {"p03": result.get("summary"), "evidence": sha256_file(root / P03_EVIDENCE_PATH)})
    except Exception as exc:
        _add(checks, "S07P04-P03-PREDECESSOR-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _check_snapshot_cases(fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    if not isinstance(fixture, Mapping) or not isinstance(fixture.get("cases"), list):
        _add(checks, "S07P04-SNAPSHOT-CASES-AVAILABLE", False, "fixture cases unavailable")
        return results
    try:
        for row in fixture["cases"]:
            if not isinstance(row, Mapping):
                raise EvidenceContinuityError("fixture case must be an object")
            case_id = row.get("case_id")
            snapshot = row.get("snapshot")
            expected = row.get("expected")
            if not isinstance(case_id, str) or not isinstance(snapshot, Mapping) or not isinstance(expected, Mapping):
                raise EvidenceContinuityError("fixture case is malformed")
            result = evaluate_link_snapshot(snapshot, row.get("coverage"))
            results[case_id] = result
            ok = (
                result.get("status") == expected.get("status")
                and result.get("reason_codes") == expected.get("reason_codes")
                and result.get("external_network_used") is False
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("real_time_soak_waited") is False
            )
            _add(checks, "S07P04-CASE-%s" % case_id, ok, result)
        positive = results.get("POSITIVE_EXACT_CHAIN")
        _add(
            checks,
            "S07P04-POSITIVE-OUTPUT-HASH-PIN",
            positive is not None and positive.get("output_sha256") == fixture.get("expected_positive_output_sha256"),
            positive.get("output_sha256") if positive else "MISSING",
        )
        replay_hashes = {
            evaluate_link_snapshot(next(row for row in fixture["cases"] if row["case_id"] == "POSITIVE_EXACT_CHAIN")["snapshot"], "1.0000")["output_sha256"]
            for _ in range(fixture["replay_count"])
        }
        _add(
            checks,
            "S07P04-100-REPLAY-DETERMINISTIC-NO-WAIT",
            len(replay_hashes) == 1 and replay_hashes == {fixture.get("expected_positive_output_sha256")},
            {"count": fixture["replay_count"], "hashes": sorted(replay_hashes)},
        )
        adverse_cases = [
            next(row for row in fixture["cases"] if row["case_id"] == case_id)
            for case_id in ("BOUNDARY_COVERAGE_MINUS_0001", "BOUNDARY_COVERAGE_PLUS_0001", "NEGATIVE_ORPHAN_TASK")
        ]
        failures: List[int] = []
        for index in range(fixture["adverse_replay_count"]):
            case = adverse_cases[index % len(adverse_cases)]
            result = evaluate_link_snapshot(case["snapshot"], case["coverage"])
            if (
                result["status"] != "CONTINUITY_REJECTED_NO_ACTION"
                or result["recommendation_generated"] is not False
                or result["order_submission_enabled"] is not False
                or result["external_network_used"] is not False
                or result["real_time_soak_waited"] is not False
            ):
                failures.append(index)
                break
        _add(
            checks,
            "S07P04-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ACTION",
            not failures,
            {"count": fixture["adverse_replay_count"], "failures": failures},
        )
    except Exception as exc:
        _add(checks, "S07P04-SNAPSHOT-CASES-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))
    return results


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=ORACLE_PATH.as_posix())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        denied = sorted(imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"})
        forbidden_tokens = [
            token
            for token in (
                "sleep" + "(",
                "requests" + ".",
                "urllib" + ".",
                "socket" + ".",
                "subprocess" + ".",
                "http" + "://",
                "https" + "://",
            )
            if token in source
        ]
        _add(
            checks,
            "S07P04-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY",
            not denied and not forbidden_tokens,
            {"imports": sorted(imports), "denied": denied, "tokens": forbidden_tokens},
        )
    except Exception as exc:
        _add(checks, "S07P04-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S07P04-REPORTS-DEFERRED-FOR-CANDIDATE", True, "candidate mode does not require generated reports")
        return
    target_minimum = fixture.get("target_test_minimum") if isinstance(fixture, Mapping) else 0
    for relative, minimum, check_id in (
        (JUNIT_PATH, target_minimum, "S07P04-TARGETED-PYTEST-REPORT"),
        (FULL_JUNIT_PATH, FULL_REGRESSION_TEST_MINIMUM, "S07P04-FULL-PYTEST-REPORT"),
    ):
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            ok = (
                isinstance(minimum, int)
                and minimum > 0
                and summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and summary["skipped"] == 0
                and normalized
            )
            _add(checks, check_id, ok, {"minimum": minimum, "summary": summary, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root / PACK_REPORT_PATH, checks, "S07P04-PACK-REPORT-STRICT-JSON")
    if isinstance(report, Mapping):
        summary = report.get("summary")
        _add(
            checks,
            "S07P04-TASKPACK-PASS",
            report.get("status") == "PASS"
            and isinstance(summary, Mapping)
            and summary.get("failed") == 0
            and summary.get("passed") == summary.get("checks"),
            summary if isinstance(summary, Mapping) else "missing summary",
        )
    try:
        expected = render_scan_report(scan_dependency_budget(root))
        actual = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(
            checks,
            "S07P04-PAID-DEPENDENCY-SCAN-PASS",
            actual == expected and "STATUS: PASS" in actual,
            {"exact_match": actual == expected, "path": SCAN_REPORT_PATH.as_posix()},
        )
    except Exception as exc:
        _add(checks, "S07P04-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _continuity_summary(
    continuity: Tuple[Dict[str, List[str]], Dict[str, Any]] | None,
    case_results: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    orphans = continuity[0] if continuity else {"unavailable": ["continuity"]}
    positive = case_results.get("POSITIVE_EXACT_CHAIN", {})
    return {
        "orphan_counts": {key: len(value) for key, value in sorted(orphans.items())},
        "positive_output_sha256": positive.get("output_sha256"),
        "positive_status": positive.get("status"),
        "case_reason_codes": {
            case_id: list(result.get("reason_codes", []))
            for case_id, result in sorted(case_results.items())
        },
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
    }


def evaluate_contract(
    root: Path,
    require_test_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_pins(root, checks, hashes)
    fixture = _check_fixture(root, checks)
    _check_predecessor(root, fixture, checks, verify_git_history=_verify_git_history)
    continuity = _check_taskpack_continuity(root, fixture, checks)
    p04_status = continuity[1]["p04_index"].get("status") if continuity is not None else None
    manifest = _check_manifest(root, checks, p04_index_status=p04_status)
    _check_pass_evidence_artifacts(root, continuity, manifest, checks)
    _check_release_link(root, manifest, checks)
    case_results = _check_snapshot_cases(fixture, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": status,
        "phase_status": "S07_P04_PASS" if status == "PASS" else "S07_P04_FAIL",
        "decision": "CONTINUOUS_EVIDENCE_CHAIN_VERIFIED_NO_ACTION" if status == "PASS" else "CONTINUITY_FAILURE_FAIL_CLOSED_NO_ACTION",
        "checks": checks,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "hashes": hashes,
        "continuity_summary": _continuity_summary(continuity, case_results),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "external_network_used_by_verifier": False,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "fixed_clock": fixture.get("fixed_clock") if isinstance(fixture, Mapping) else None,
        "next": "S07/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S07/P04_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_test_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S07_P04_CANDIDATE_VALID" if result["status"] == "PASS" else "S07_P04_CANDIDATE_INVALID",
        "summary": result["summary"],
        "next": result["next"],
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, str]] = {}
    for relative in ROLLBACK_ARTIFACTS:
        path = root / relative
        artifacts[relative.as_posix()] = {
            "status": "PASS" if path.is_file() else "FAIL",
            "sha256": sha256_file(path) if path.is_file() else "MISSING",
        }
    status = "PASS" if artifacts and all(row["status"] == "PASS" for row in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "RESTORE_PRIOR_SIGNED_ARTIFACTS_REPLAY_CONTINUITY_NO_EXTERNAL_MUTATION",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = list(PINNED_PHASE_HASHES) + list(PINNED_BASELINE_HASHES) + [ORACLE_PATH.as_posix(), "abd_acceptance/__main__.py"]
    return {relative: sha256_file(root / relative) for relative in sorted(set(paths))}


def build_evidence(
    root: Path,
    require_test_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": validation.get("fixed_clock"),
        "status": validation["status"],
        "phase_status": validation["phase_status"],
        "decision": validation["decision"],
        "validation": validation,
        "predecessor_evidence": {
            "p03_evidence": P03_EVIDENCE_PATH.as_posix(),
            "p03_evidence_sha256": sha256_file(root / P03_EVIDENCE_PATH),
            "p03_rollback_sha256": sha256_file(root / P03_ROLLBACK_PATH),
        },
        "continuity_summary": validation["continuity_summary"],
        "deterministic_replay": {
            "replay_count": strict_json_load(root / FIXTURE_PATH).get("replay_count"),
            "adverse_replay_count": strict_json_load(root / FIXTURE_PATH).get("adverse_replay_count"),
            "real_time_wait_performed": False,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S07_STAGE_REVIEW_REQUIRED_BEFORE_ANY_UPLOAD_OR_DEPLOYMENT",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "structured_failure_log": {
            "failed_check_ids": validation["summary"]["failed_check_ids"],
            "case_reason_codes": validation["continuity_summary"].get("case_reason_codes", {}),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S07/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S07/P04_test.py --junitxml=machine/evidence/S07/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S07/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S07/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S07/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S07-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": _input_hashes(root),
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S07/P04 validates offline evidence continuity only.",
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


def _update_evidence_index(root: Path, status: str, evidence_hash: str, fixed_clock: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = _strict_jsonl(path)
    rows = [row for row in rows if row.get("id") != "INDEX-%s" % CONTRACT_ID]
    rows.append(
        {
            "id": "INDEX-%s" % CONTRACT_ID,
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S07/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S07/P04_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise EvidenceContinuityError("S07/P04 evidence must be written to machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, str(evidence["status"]), evidence_hash, str(evidence["fixed_clock"]))
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


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S07P04-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S07P04-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        integrity = (
            evidence.get("evidence_id") == "EVD-S07-P04"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S07/STAGE_REVIEW_READY_NOT_STARTED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S07P04-EXISTING-EVIDENCE-INTEGRITY", integrity, evidence.get("status"))
        errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            try:
                candidate = _safe_relative(relative)
                actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
                if actual != expected and approved_successor_sha256(root, relative) != actual:
                    errors.append({"path": relative, "actual": actual})
            except Exception:
                errors.append({"path": str(relative), "actual": "UNSAFE_PATH"})
        _add(checks, "S07P04-EXISTING-INPUT-HASHES", not errors, errors or "all inputs match")
        expected_code = evidence.get("hashes", {}).get("code")
        current_code = _current_code_hash(root)
        compatible_code = (
            expected_code == LEGACY_EVIDENCE_CODE_HASH
            and _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        )
        _add(
            checks,
            "S07P04-EXISTING-CODE-HASH",
            expected_code == current_code or compatible_code,
            {"expected": expected_code, "current": current_code, "compatible_structural_hash": compatible_code},
        )
    else:
        _add(checks, "S07P04-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S07-P04-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_account_balance_read_or_written") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S07P04-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S07P04-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_test_reports=True, _verify_git_history=verify_git_history)
    _add(checks, "S07P04-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S07/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S07/P04_REMEDIATION_REQUIRED",
    }


__all__ = [
    "ARTIFACT_MANIFEST_PATH",
    "CONTRACT_ID",
    "EVIDENCE_INDEX_PATH",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FINAL_ACCEPTANCE_PATH",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_FIXED_CLOCK",
    "JUNIT_PATH",
    "ORACLE_PATH",
    "P03_EVIDENCE_PATH",
    "PHASE_ARTIFACT_PATHS",
    "PINNED_BASELINE_HASHES",
    "PINNED_PHASE_HASHES",
    "RELEASE_MANIFEST_PATH",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "SHA256SUMS_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "TEST_PATH",
    "TRACEABILITY_PATH",
    "EvidenceContinuityError",
    "_check_manifest",
    "_check_pins",
    "_check_reports",
    "_junit_is_normalized",
    "_junit_summary",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "evaluate_link_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
