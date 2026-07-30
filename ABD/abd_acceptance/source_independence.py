"""Independent fail-closed acceptance oracle for ABD S08/P02.

The oracle verifies frozen synthetic source metadata only. It never reads a
live price, opens a network connection, accesses an account, creates advice,
or submits an order.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from source_independence import SourceIndependenceError, build_report, canonical_json_bytes, cluster_sources

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S08-P02"
REQUIREMENT_ID = "REQ-S08-P02"
STAGE_ID = "S08"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

CORE_PATH = Path("source_independence.py")
CLUSTERS_PATH = Path("source_clusters.json")
ORACLE_PATH = Path("abd_acceptance/source_independence.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
INIT_PATH = Path("abd_acceptance/__init__.py")
TEST_PATH = Path("tests/S08/P02_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S08_P02.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S08/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S08/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, INIT_PATH)

_PREDECESSORS = {
    "machine/evidence/EVD-S08-P01.json": {
        "sha256": "aa29bfd32067cf53727399f2f9f521ba08e43600b4597b358f994507c5010e13",
        "contract_id": "AC-S08-P01",
        "status": "PASS",
        "next": "S08/P02_READY_NOT_STARTED",
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
    CLUSTERS_PATH,
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


class SourceIndependenceAcceptanceError(ValueError):
    """Raised for malformed phase evidence or an unreplayable source cluster."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _portable(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise SourceIndependenceAcceptanceError("path is outside the ABD root") from exc


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
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise SourceIndependenceAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SourceIndependenceAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise SourceIndependenceAcceptanceError("expected exactly one id=%s" % identifier)
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise SourceIndependenceAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise SourceIndependenceAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise SourceIndependenceAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise SourceIndependenceAcceptanceError("%s must be finite" % label)
    return parsed


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _IMMUTABLE_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S08P02-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S08P02-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S08P02-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S08P02-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S08P02-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S08P02-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise SourceIndependenceAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        outputs = set(requirement.get("scope", []))
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        exact = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "同源复制不得被错误计为多条独立证据。"
            and outputs == {"source_independence.py", "source_clusters.json"}
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S08-P02 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S08-P02-01", "T-S08-P02-02", "T-S08-P02-03"]
            and {"source_independence.py", "source_clusters.json"}.issubset(task_outputs)
        )
        _add(checks, "S08P02-TASKPACK-EXACT", exact, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S08P02-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _PREDECESSORS.items():
        path = root / relative
        value = _safe_load(root, path, checks, "S08P02-PREDECESSOR-PARSE-%s" % Path(relative).stem)
        try:
            actual = sha256_file(path)
        except Exception as exc:
            _add(checks, "S08P02-PREDECESSOR-HASH-%s" % Path(relative).stem, False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        passed = isinstance(value, Mapping) and actual == expected["sha256"] and all(value.get(key) == item for key, item in expected.items() if key != "sha256")
        _add(checks, "S08P02-PREDECESSOR-HASH-%s" % Path(relative).stem, passed, {"expected": expected["sha256"], "actual": actual})


def _check_clusters(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S08P02-FIXTURE-STRICT-JSON")
    clusters = _safe_load(root, root / CLUSTERS_PATH, checks, "S08P02-CLUSTERS-STRICT-JSON")
    if not isinstance(fixture, Mapping) or not isinstance(clusters, Mapping):
        return
    try:
        expected_report = build_report(fixture)
        _add(checks, "S08P02-CLUSTERS-REPLAY-EXACT", clusters == expected_report, "recomputed from frozen source fixture")
        required_fixture_values = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S08-P02-SOURCE-INDEPENDENCE",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "expected_next": "S08/P03_READY_NOT_STARTED",
            "replay_count": 100,
            "adverse_replay_count": 10000,
            "predecessor_evidence_sha256": _PREDECESSORS["machine/evidence/EVD-S08-P01.json"]["sha256"],
        }
        _add(checks, "S08P02-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in required_fixture_values.items()), sorted(required_fixture_values))
        claim = fixture.get("claim_boundary")
        safe_claim = isinstance(claim, Mapping) and all(
            claim.get(key) is value
            for key, value in {
                "network_accessed": False,
                "actual_market_or_odds_observed": False,
                "recommendation_generated": False,
                "order_submission_enabled": False,
                "real_time_soak_required": False,
            }.items()
        ) and claim.get("incremental_cash_spent_aud") == "0.00"
        _add(checks, "S08P02-FIXTURE-NO-EXTERNAL-CLAIM", safe_claim, claim)
        fixture_cases = fixture.get("cases")
        report_cases = {case.get("id"): case for case in clusters.get("cases", []) if isinstance(case, Mapping)}
        if not isinstance(fixture_cases, list) or len(fixture_cases) != 4:
            raise SourceIndependenceAcceptanceError("exactly four frozen source cases required")
        unique_ids: set[str] = set()
        balances_ok = True
        for fixture_case in fixture_cases:
            if not isinstance(fixture_case, Mapping):
                raise SourceIndependenceAcceptanceError("fixture case must be an object")
            identifier = fixture_case.get("id")
            expected = fixture_case.get("expected")
            report_case = report_cases.get(identifier)
            if not isinstance(identifier, str) or not isinstance(expected, Mapping) or not isinstance(report_case, Mapping):
                _add(checks, "S08P02-CASE-%s" % identifier, False, "missing expected or report case")
                continue
            member_counts = [cluster.get("member_count") for cluster in report_case.get("clusters", []) if isinstance(cluster, Mapping)]
            passed = (
                report_case.get("cluster_count") == expected.get("cluster_count")
                and report_case.get("eligible_independent_source_count") == expected.get("eligible_independent_source_count")
                and report_case.get("effective_independent_weight") == expected.get("effective_independent_weight")
                and member_counts == expected.get("cluster_member_counts")
            )
            _add(checks, "S08P02-CASE-%s" % identifier, passed, {"expected": expected, "actual": {"cluster_count": report_case.get("cluster_count"), "eligible_independent_source_count": report_case.get("eligible_independent_source_count"), "effective_independent_weight": report_case.get("effective_independent_weight"), "cluster_member_counts": member_counts}})
            for cluster in report_case.get("clusters", []):
                if not isinstance(cluster, Mapping):
                    balances_ok = False
                    continue
                members = cluster.get("members", [])
                if not isinstance(members, list):
                    balances_ok = False
                    continue
                weights = []
                for member in members:
                    if not isinstance(member, Mapping) or not isinstance(member.get("source_id"), str):
                        balances_ok = False
                        continue
                    if member["source_id"] in unique_ids:
                        balances_ok = False
                    unique_ids.add(member["source_id"])
                    weights.append(_decimal(member.get("weight"), label="member.weight"))
                if sum(weights, Decimal("0")) != _decimal(cluster.get("independent_weight"), label="cluster.independent_weight"):
                    balances_ok = False
        _add(checks, "S08P02-CLUSTER-WEIGHTS-DO-NOT-MULTIPLY-COPIES", balances_ok, "member weights sum to one cluster weight and source ids do not repeat")
        invalid_cases = fixture.get("invalid_cases")
        invalid_ok = isinstance(invalid_cases, list) and bool(invalid_cases)
        if isinstance(invalid_cases, list):
            for invalid_case in invalid_cases:
                try:
                    cluster_sources(invalid_case)
                except SourceIndependenceError:
                    continue
                invalid_ok = False
        _add(checks, "S08P02-INVALID-PROVENANCE-FAILS-CLOSED", invalid_ok, "copy graph, content conflict, timestamp and status negatives")
        for relative in (CORE_PATH, CLUSTERS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (SourceIndependenceError, SourceIndependenceAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S08P02-CLUSTERS-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        tree = ast.parse((root / CORE_PATH).read_text(encoding="utf-8"))
    except Exception as exc:
        _add(checks, "S08P02-CORE-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
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
    _add(checks, "S08P02-CORE-NO-NETWORK-PROCESS-OR-SOAK", not (imports & prohibited_imports) and not forbidden_calls, {"imports": sorted(imports), "calls": sorted(forbidden_calls)})
    source = (root / CORE_PATH).read_text(encoding="utf-8")
    float_literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]
    _add(checks, "S08P02-CORE-NO-FLOAT-LITERALS", "float(" not in source and not float_literals, "decimal-only source weights")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S08P02-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        junit_ok = junit["tests"] >= 20 and not junit["failures"] and not junit["errors"] and not junit["skipped"]
        _add(checks, "S08P02-TARGETED-PYTEST-REPORT", junit_ok, junit)
    except Exception as exc:
        _add(checks, "S08P02-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
        _add(checks, "S08P02-SCAN-REPORT", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S08P02-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S08P02-PACK-REPORT-STRICT-JSON")
    _add(checks, "S08P02-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


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
        "decision": "SOURCE_INDEPENDENCE_WEIGHTING_READY_DOWNSTREAM_GATES_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S08/P03_READY_NOT_STARTED" if status == "PASS" else "S08/P02_BLOCKED",
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
    _check_clusters(root, checks, hashes)
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
        "evidence_id": "EVD-S08-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S08_P02_SOURCE_INDEPENDENCE_DERIVATION_KEEP_PREDECESSOR_EVIDENCE",
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
        CORE_PATH, CLUSTERS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH,
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"), Path("machine/facts/traceability_matrix.json"), Path("machine/facts/roadmap.json"),
        Path("machine/evidence/EVD-S08-P01.json"),
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "downstream dispatcher or bootstrap evolution must not invalidate phase-owned evidence",
    }


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
        "evidence_id": "EVD-S08-P02",
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
        "shared_runtime_contract": _shared_runtime_contract(),
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S08/P02/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S08/P02_test.py --junitxml=machine/evidence/S08/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S08/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S08-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S08_P02_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S08-P02",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S08/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise SourceIndependenceAcceptanceError("planned S08/P02 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise SourceIndependenceAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise SourceIndependenceAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S08/P03_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise SourceIndependenceAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    index_rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    index = _row(index_rows, "INDEX-AC-S08-P02")
    current_hash = sha256_file(root / EVIDENCE_PATH)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "SOURCE_INDEPENDENCE_WEIGHTING_READY_DOWNSTREAM_GATES_REQUIRED"
        and evidence.get("next") == "S08/P03_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == current_hash
    )
    if not valid:
        raise SourceIndependenceAcceptanceError("existing S08/P02 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": current_hash, "next": "S08/P03_READY_NOT_STARTED"}
