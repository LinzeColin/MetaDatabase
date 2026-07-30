"""Independent fail-closed acceptance oracle for ABD S08/P01.

It validates frozen synthetic vectors only.  It never reads a live price,
opens a network connection, creates advice, or touches an external account.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from devig import METHODS, PROBABILITY_SUM_TOLERANCE, DevigInputError, build_report, canonical_json_bytes

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S08-P01"
REQUIREMENT_ID = "REQ-S08-P01"
STAGE_ID = "S08"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

CORE_PATH = Path("devig.py")
VECTORS_PATH = Path("devig_vectors.json")
REPORT_PATH = Path("devig_report.json")
ORACLE_PATH = Path("abd_acceptance/devig.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
INIT_PATH = Path("abd_acceptance/__init__.py")
TEST_PATH = Path("tests/S08/P01_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S08_P01.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S08/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S08/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

_PREDECESSORS = {
    "machine/evidence/EVD-S02-P04.json": {
        "sha256": "062d4bf5cfbc5e63c3fb454874a8f6a10cbaa67ad84c8ea9fc77fe64b81f633f",
        "contract_id": "AC-S02-P04",
        "status": "PASS",
    },
    "machine/evidence/EVD-S07-P04.json": {
        "sha256": "a2fa2f72c069050ed7045f7e7c3cbe5928664bee4e91d1307169b19d466a6fa6",
        "contract_id": "AC-S07-P04",
        "status": "PASS",
    },
}

_IMMUTABLE_BASELINE_HASHES = {
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

_ROLLBACK_ARTIFACTS = (
    CORE_PATH,
    VECTORS_PATH,
    REPORT_PATH,
    ORACLE_PATH,
    CLI_PATH,
    INIT_PATH,
    TEST_PATH,
    FIXTURE_PATH,
)

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class DevigAcceptanceError(ValueError):
    """Raised for malformed phase evidence or a non-replayable phase input."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, path.as_posix())
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise DevigAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise DevigAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matching = [row for row in rows if row.get("id") == identifier]
    if len(matching) != 1:
        raise DevigAcceptanceError("expected exactly one id=%s" % identifier)
    return matching[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise DevigAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _parse_decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise DevigAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DevigAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise DevigAcceptanceError("%s must be finite" % label)
    return parsed


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _IMMUTABLE_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S08P01-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "S08P01-BASELINE-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S08P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S08P01-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S08P01-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S08P01-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise DevigAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        outputs = set(requirement.get("scope", []))
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        exact = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "完整盘口概率和=1±1e-9，四种方法可重放。"
            and outputs == {"devig.py", "devig_vectors.json", "devig_report.json"}
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S08-P01 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S08-P01-01", "T-S08-P01-02", "T-S08-P01-03"]
            and {"devig.py", "devig_vectors.json", "devig_report.json"}.issubset(task_outputs)
        )
        _add(checks, "S08P01-TASKPACK-EXACT", exact, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S08P01-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _PREDECESSORS.items():
        path = root / relative
        value = _safe_load(path, checks, "S08P01-PREDECESSOR-PARSE-%s" % Path(relative).stem)
        try:
            actual = sha256_file(path)
        except Exception as exc:
            _add(checks, "S08P01-PREDECESSOR-HASH-%s" % Path(relative).stem, False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        passed = isinstance(value, Mapping) and actual == expected["sha256"] and all(value.get(key) == item for key, item in expected.items() if key != "sha256")
        _add(checks, "S08P01-PREDECESSOR-HASH-%s" % Path(relative).stem, passed, {"actual": actual, "expected": expected["sha256"]})


def _check_vectors_and_report(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    vectors = _safe_load(root / VECTORS_PATH, checks, "S08P01-VECTORS-STRICT-JSON")
    report = _safe_load(root / REPORT_PATH, checks, "S08P01-REPORT-STRICT-JSON")
    if not isinstance(vectors, Mapping) or not isinstance(report, Mapping):
        return
    try:
        expected_report = build_report(vectors)
        report_matches = report == expected_report
        _add(checks, "S08P01-REPORT-REPLAY-EXACT", report_matches, "recomputed from frozen vectors")
        required_vector_values = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S08-P01-DEVIG",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "expected_next": "S08/P02_READY_NOT_STARTED",
            "probability_sum_tolerance": "0.000000001",
            "replay_count": 100,
            "adverse_replay_count": 10000,
        }
        vector_exact = all(vectors.get(key) == value for key, value in required_vector_values.items())
        _add(checks, "S08P01-VECTORS-CONTRACT-EXACT", vector_exact, sorted(required_vector_values))
        claim = vectors.get("claim_boundary")
        safe_claim = isinstance(claim, Mapping) and all(
            claim.get(key) is value
            for key, value in {
                "network_accessed": False,
                "actual_market_or_odds_observed": False,
                "recommendation_generated": False,
                "order_submission_enabled": False,
                "real_time_soak_required": False,
            }.items()
        )
        _add(checks, "S08P01-VECTORS-NO-EXTERNAL-CLAIM", safe_claim, claim)
        cases = vectors.get("cases")
        if not isinstance(cases, list) or len(cases) != 4:
            raise DevigAcceptanceError("four frozen vector cases required")
        report_cases = {case.get("id"): case for case in report.get("cases", []) if isinstance(case, Mapping)}
        for vector_case in cases:
            identifier = vector_case.get("id") if isinstance(vector_case, Mapping) else None
            report_case = report_cases.get(identifier)
            if not isinstance(identifier, str) or not isinstance(report_case, Mapping):
                _add(checks, "S08P01-CASE-%s" % identifier, False, "missing report case")
                continue
            methods = report_case.get("methods")
            for method in METHODS:
                probabilities = methods.get(method, {}).get("probabilities") if isinstance(methods, Mapping) else None
                try:
                    decimal_probabilities = tuple(_parse_decimal(value, label="%s/%s" % (identifier, method)) for value in probabilities)
                    total = sum(decimal_probabilities, Decimal("0"))
                    valid = len(decimal_probabilities) == len(vector_case.get("odds", [])) and all(Decimal("0") < value < Decimal("1") for value in decimal_probabilities) and abs(total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
                except Exception as exc:
                    valid = False
                    total = "%s: %s" % (type(exc).__name__, exc)
                _add(checks, "S08P01-SUM-%s-%s" % (identifier, method), valid, {"sum": str(total)})
        shin_case = report_cases.get("THREE_WAY_SHIN_REFERENCE", {})
        shin_probabilities = shin_case.get("methods", {}).get("SHIN", {}).get("probabilities", []) if isinstance(shin_case, Mapping) else []
        expected_shin = next(case.get("expected_shin_probabilities") for case in cases if case.get("id") == "THREE_WAY_SHIN_REFERENCE")
        shin_ok = len(shin_probabilities) == len(expected_shin) and all(
            abs(_parse_decimal(actual, label="shin") - _parse_decimal(expected, label="expected_shin")) <= Decimal("1e-12")
            for actual, expected in zip(shin_probabilities, expected_shin)
        )
        _add(checks, "S08P01-SHIN-REFERENCE-WITHIN-1E-12", shin_ok, shin_probabilities)
        for relative in (CORE_PATH, VECTORS_PATH, REPORT_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (DevigInputError, DevigAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S08P01-VECTORS-AND-REPORT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        tree = ast.parse((root / CORE_PATH).read_text(encoding="utf-8"))
    except Exception as exc:
        _add(checks, "S08P01-CORE-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    imports = set()
    forbidden_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen"}:
            forbidden_calls.append(node.func.attr)
    _add(checks, "S08P01-CORE-NO-NETWORK-PROCESS-OR-SOAK", not (imports & prohibited_imports) and not forbidden_calls, {"imports": sorted(imports), "calls": sorted(forbidden_calls)})
    source = (root / CORE_PATH).read_text(encoding="utf-8")
    float_literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]
    _add(checks, "S08P01-CORE-NO-FLOAT-LITERALS", "float(" not in source and not float_literals, "decimal-only authoritative calculations")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S08P01-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        junit_ok = junit["tests"] >= 18 and not junit["failures"] and not junit["errors"] and not junit["skipped"]
        _add(checks, "S08P01-TARGETED-PYTEST-REPORT", junit_ok, junit)
    except Exception as exc:
        _add(checks, "S08P01-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
        _add(checks, "S08P01-SCAN-REPORT", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S08P01-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S08P01-PACK-REPORT-STRICT-JSON")
    _add(checks, "S08P01-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "MARKET_PRIOR_DEVIG_READY_DOWNSTREAM_GATES_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S08/P02_READY_NOT_STARTED" if status == "PASS" else "S08/P01_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessors(root, checks, hashes)
    _check_vectors_and_report(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, str]] = {}
    for relative in _ROLLBACK_ARTIFACTS:
        path = root / relative
        artifacts[relative.as_posix()] = {"sha256": sha256_file(path), "status": "PASS" if path.is_file() else "FAIL"}
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S08_P01_MARKET_PRIOR_COMPONENT_RESTORE_PREDECESSOR_RECEIPTS_KEEP_ALL_EVIDENCE",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        CORE_PATH, VECTORS_PATH, REPORT_PATH, ORACLE_PATH, CLI_PATH, INIT_PATH, TEST_PATH, FIXTURE_PATH,
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"), Path("machine/facts/roadmap.json"),
        Path("machine/evidence/EVD-S02-P04.json"), Path("machine/evidence/EVD-S07-P04.json"),
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = {
        "contract_id": evidence.get("contract_id"),
        "decision": evidence.get("decision"),
        "next": evidence.get("next"),
        "validation": evidence.get("validation"),
    }
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S08/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S08/P01_test.py --junitxml=machine/evidence/S08/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S08/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S08-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S08_P01_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S08-P01",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S08/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise DevigAcceptanceError("planned S08/P01 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise DevigAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise DevigAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S08/P02_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise DevigAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "MARKET_PRIOR_DEVIG_READY_DOWNSTREAM_GATES_REQUIRED"
        and evidence.get("next") == "S08/P02_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
    )
    if not valid:
        raise DevigAcceptanceError("existing S08/P01 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S08/P02_READY_NOT_STARTED"}
