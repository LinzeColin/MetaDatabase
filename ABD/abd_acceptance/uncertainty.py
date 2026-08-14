"""Independent, fail-closed acceptance oracle for ABD S10/P02.

Only frozen residual blocks are replayed.  The oracle never reaches a live
provider, reads an account, enables an advice route, submits an order, or waits
for real time.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from uncertainty import (
    CONTRACT_ID as RUNNER_CONTRACT_ID,
    build_manifest,
    manifest_sha256,
    validate_fixture,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S10-P02"
REQUIREMENT_ID = "REQ-S10-P02"
STAGE_ID = "S10"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
_ZERO = Decimal("0")

UNCERTAINTY_PATH = Path("uncertainty.py")
MANIFEST_PATH = Path("bootstrap_manifest.json")
ORACLE_PATH = Path("abd_acceptance/uncertainty.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
TEST_PATH = Path("tests/S10/P02_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S10_P02.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S10-P01.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S10-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S10-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S10/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S10/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "model:block_bootstrap_conservative_probability"
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH,)

_TASKPACK_HASHES = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
_PREDECESSOR_SHA256 = "851e86a0e1deb0166fc07a1b0c726e31cb68c12e0809df0237ca0a2b1225c6f2"
_ROLLBACK_ARTIFACTS = (UNCERTAINTY_PATH, MANIFEST_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "actual_market_or_odds_observed": False,
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


class UncertaintyAcceptanceError(ValueError):
    """Raised when S10/P02 evidence cannot be replayed or trusted."""


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
        raise UncertaintyAcceptanceError("rows are not a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise UncertaintyAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise UncertaintyAcceptanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise UncertaintyAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    return rows


def _check_taskpack_hashes(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _TASKPACK_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S10P02-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "S10P02-BASELINE-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        requirements = strict_json_load(root / "machine/facts/requirements.json")
        contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
        graph = strict_json_load(root / "machine/facts/task_graph.json")
        traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [task for task in graph.get("tasks", []) if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        expected_scope = ["uncertainty.py", "bootstrap_manifest.json"]
        outputs = {output for task in tasks for output in task.get("outputs", [])}
        scope_ok = (
            requirement.get("scope") == expected_scope
            and requirement.get("target") == "固定种子/输入可重放，保守概率单调。"
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle") == {"type": "EXECUTABLE", "command": "python -m abd_acceptance --contract AC-S10-P02 --evidence machine/evidence", "rule": requirement.get("target")}
            and contract.get("pass_gate") == requirement.get("target")
        )
        _add(checks, "S10P02-TASKPACK-EXACT", scope_ok, {"scope": requirement.get("scope"), "pass_gate": contract.get("pass_gate")})
        trace_ok = (
            [task.get("id") for task in tasks] == ["T-S10-P02-01", "T-S10-P02-02", "T-S10-P02-03"]
            and all(item in outputs for item in expected_scope)
            and TEST_PATH.as_posix() in outputs
            and FIXTURE_PATH.as_posix() in outputs
            and EVIDENCE_PATH.as_posix() in outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in outputs
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == ["T-S10-P02-01", "T-S10-P02-02", "T-S10-P02-03"]
            and trace.get("test_ids") == ["TEST-S10-P02", "TEST-S10-P02-BOUNDARY", "TEST-S10-P02-REPLAY"]
            and trace.get("evidence_id") == "EVD-S10-P02"
            and trace.get("artifact_ids") == ["ART-S10-P02-01", "ART-S10-P02-02"]
        )
        _add(checks, "S10P02-TRACE-CLOSED", trace_ok, {"tasks": [task.get("id") for task in tasks], "outputs": sorted(outputs)})
    except Exception as exc:
        _add(checks, "S10P02-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    value = _safe_load(root, PREDECESSOR_PATH, checks, "S10P02-P01-PREDECESSOR-STRICT-JSON")
    try:
        actual = sha256_file(root / PREDECESSOR_PATH)
    except Exception as exc:
        _add(checks, "S10P02-P01-PREDECESSOR-HASH", False, "%s: %s" % (type(exc).__name__, exc))
        return
    hashes[PREDECESSOR_PATH.as_posix()] = actual
    passed = (
        isinstance(value, Mapping)
        and actual == _PREDECESSOR_SHA256
        and value.get("contract_id") == "AC-S10-P01"
        and value.get("status") == "PASS"
        and value.get("next") == "S10/P02_READY_NOT_STARTED"
    )
    _add(checks, "S10P02-P01-PREDECESSOR-HASH", passed, {"expected": _PREDECESSOR_SHA256, "actual": actual})


def _check_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    parameters = _safe_load(root, Path("machine/facts/parameters.json"), checks, "S10P02-PARAMETERS-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S10P02-FIXTURE-STRICT-JSON")
    manifest = _safe_load(root, MANIFEST_PATH, checks, "S10P02-MANIFEST-STRICT-JSON")
    if not isinstance(parameters, Mapping) or not isinstance(fixture, Mapping) or not isinstance(manifest, Mapping):
        return
    try:
        validated = validate_fixture(fixture, parameters)
        rebuilt = build_manifest(fixture, parameters)
        digest = manifest_sha256(rebuilt)
        _add(
            checks,
            "S10P02-MANIFEST-REPLAY-EXACT",
            fixture.get("expected_manifest_sha256") == digest and manifest == rebuilt,
            {"expected": fixture.get("expected_manifest_sha256"), "actual": digest},
        )
        identity_ok = (
            rebuilt.get("manifest_id") == "MAN-S10-P02-BLOCK-BOOTSTRAP"
            and rebuilt.get("fixture_id") == "FIX-S10-P02-BLOCK-BOOTSTRAP"
            and rebuilt.get("contract_id") == CONTRACT_ID
            and rebuilt.get("requirement_id") == REQUIREMENT_ID
            and rebuilt.get("stage_id") == STAGE_ID
            and rebuilt.get("phase_id") == PHASE_ID
            and rebuilt.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
            and rebuilt.get("model") == "BLOCK_BOOTSTRAP_RESIDUAL_PERCENTILE"
        )
        _add(checks, "S10P02-MANIFEST-IDENTITY-EXACT", identity_ok, {"manifest_id": rebuilt.get("manifest_id"), "model": rebuilt.get("model")})
        parameter_ok = rebuilt.get("parameters") == {
            "runtime_block_bootstrap_iterations": 1000,
            "evaluation_block_bootstrap_iterations": 2000,
            "conservative_probability_percentile": 10,
        }
        _add(checks, "S10P02-BOOTSTRAP-COUNTS-AND-PERCENTILE-EXACT", parameter_ok, rebuilt.get("parameters"))
        runtime = rebuilt.get("runtime")
        evaluation = rebuilt.get("evaluation")
        run_ok = (
            isinstance(runtime, Mapping)
            and isinstance(evaluation, Mapping)
            and runtime.get("iterations") == 1000
            and evaluation.get("iterations") == 2000
            and runtime.get("percentile") == 10
            and evaluation.get("percentile") == 10
            and isinstance(runtime.get("sample_sha256"), str)
            and len(runtime.get("sample_sha256")) == 64
            and isinstance(evaluation.get("sample_sha256"), str)
            and len(evaluation.get("sample_sha256")) == 64
            and runtime.get("minimum_probability") != runtime.get("maximum_probability")
            and evaluation.get("minimum_probability") != evaluation.get("maximum_probability")
        )
        _add(checks, "S10P02-BLOCK-RESAMPLE-NONDEGENERATE", run_ok, {"runtime": runtime, "evaluation": evaluation})
        distinct_runs = (
            isinstance(runtime, Mapping)
            and isinstance(evaluation, Mapping)
            and runtime.get("seed") != evaluation.get("seed")
            and runtime.get("sample_sha256") != evaluation.get("sample_sha256")
        )
        _add(checks, "S10P02-RUNTIME-EVALUATION-SEEDS-AND-DIGESTS-DISTINCT", distinct_runs, {"runtime_seed": runtime.get("seed") if isinstance(runtime, Mapping) else None, "evaluation_seed": evaluation.get("seed") if isinstance(evaluation, Mapping) else None})
        base = Decimal(rebuilt["base_probability"])
        conservative = Decimal(rebuilt["conservative_probability"])
        conservative_ok = _ZERO <= conservative <= base
        _add(checks, "S10P02-CONSERVATIVE-PROBABILITY-NO-UPLIFT", conservative_ok, {"base": rebuilt["base_probability"], "conservative": rebuilt["conservative_probability"]})
        runtime_conservative = Decimal(runtime["conservative_probability"]) if isinstance(runtime, Mapping) else Decimal("-1")
        runtime_range_ok = (
            isinstance(runtime, Mapping)
            and Decimal(runtime["minimum_probability"]) <= runtime_conservative <= Decimal(runtime["maximum_probability"])
            and rebuilt.get("conservative_probability") == runtime.get("conservative_probability")
        )
        _add(checks, "S10P02-RUNTIME-PERCENTILE-RANGE-EXACT", runtime_range_ok, runtime)
        probes = rebuilt.get("monotonic_probe")
        monotonic_ok = (
            isinstance(probes, list)
            and len(probes) >= 3
            and rebuilt.get("conservative_probability_monotonic") is True
            and [Decimal(row["conservative_probability"]) for row in probes if isinstance(row, Mapping)] == sorted(Decimal(row["conservative_probability"]) for row in probes if isinstance(row, Mapping))
        )
        _add(checks, "S10P02-CONSERVATIVE-PROBABILITY-MONOTONIC", monotonic_ok, probes)
        predecessor_ok = rebuilt.get("predecessor") == fixture.get("predecessor") == {
            "contract_id": "AC-S10-P01",
            "evidence_path": PREDECESSOR_PATH.as_posix(),
            "sha256": _PREDECESSOR_SHA256,
        }
        _add(checks, "S10P02-PREDECESSOR-BINDING-EXACT", predecessor_ok, rebuilt.get("predecessor"))
        _add(checks, "S10P02-NO-EXTERNAL-RUNTIME-OR-ORDER-CLAIM", rebuilt.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY, rebuilt.get("external_effect_boundary"))
        _add(
            checks,
            "S10P02-FINANCIAL-AND-PRODUCTION-STATUS-EXACT",
            rebuilt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED" and rebuilt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED",
            {"financial_target_status": rebuilt.get("financial_target_status"), "production_status": rebuilt.get("production_status")},
        )
        _add(
            checks,
            "S10P02-READY-NEXT-STATE-EXACT",
            rebuilt.get("decision") == "CONSERVATIVE_PROBABILITY_READY_DOWNSTREAM_DECIMAL_GATE_REQUIRED" and rebuilt.get("next") == "S10/P03_READY_NOT_STARTED",
            {"decision": rebuilt.get("decision"), "next": rebuilt.get("next")},
        )
        for relative in (UNCERTAINTY_PATH, MANIFEST_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
        if validated["runtime_iterations"] != 1000 or validated["evaluation_iterations"] != 2000:
            _add(checks, "S10P02-FIXTURE-BOOTSTRAP-COUNTS", False, dict(validated))
    except Exception as exc:
        _add(checks, "S10P02-FIXTURE-AND-MANIFEST", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    try:
        source = (root / UNCERTAINTY_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        _add(checks, "S10P02-STATIC-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    imports = set()
    forbidden_calls: list[str] = []
    float_literals: list[Any] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen", "urlopen"}:
            forbidden_calls.append(node.func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            float_literals.append(node.value)
    passed = not (imports & prohibited_imports) and not forbidden_calls and not float_literals and "float(" not in source and "submit_order" not in source and "retry_order" not in source
    _add(
        checks,
        "S10P02-STATIC-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER",
        passed,
        {"imports": sorted(imports), "calls": sorted(forbidden_calls), "float_literals": float_literals},
    )


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S10P02-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _junit_summary(path: Path) -> dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise UncertaintyAcceptanceError("JUnit contains no suites")
    fields = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for field in fields:
            fields[field] += int(suite.attrib.get(field, "0"))
    return fields


def _junit_normalized(path: Path) -> bool:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
        for suite in suites
    )


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        passed = summary["tests"] >= 16 and not summary["failures"] and not summary["errors"] and not summary["skipped"] and _junit_normalized(root / JUNIT_PATH)
        _add(checks, "S10P02-TARGETED-PYTEST-REPORT", passed, summary)
    except Exception as exc:
        _add(checks, "S10P02-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S10P02-SCAN-REPORT", "STATUS: PASS" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S10P02-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S10P02-PACK-REPORT-STRICT-JSON")
    _add(checks, "S10P02-PACK-REPORT-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("summary") if isinstance(report, Mapping) else "unavailable")


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
        "decision": "CONSERVATIVE_PROBABILITY_READY_DOWNSTREAM_DECIMAL_GATE_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S10/P03_READY_NOT_STARTED" if status == "PASS" else "S10/P02_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "hashes": dict(hashes),
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _add(checks, "S10P02-CONTRACT-ID-BOUND", RUNNER_CONTRACT_ID == CONTRACT_ID, RUNNER_CONTRACT_ID)
    _check_taskpack_hashes(root, checks, hashes)
    _check_taskpack_trace(root, checks)
    _check_predecessor(root, checks, hashes)
    _check_runner(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in _ROLLBACK_ARTIFACTS
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S10-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_BLOCK_BOOTSTRAP_CONSERVATIVE_PROBABILITY_RESTORE_SIGNED_S10_P01_KEEP_ALL_EVIDENCE",
        "feature_flag_id": FEATURE_FLAG_ID,
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
        UNCERTAINTY_PATH,
        MANIFEST_PATH,
        ORACLE_PATH,
        TEST_PATH,
        FIXTURE_PATH,
        PREDECESSOR_PATH,
        *tuple(Path(path) for path in _TASKPACK_HASHES),
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "later dispatcher or bootstrap evolution must not invalidate phase-owned frozen evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        _json_bytes(
            {
                "contract_id": evidence.get("contract_id"),
                "decision": evidence.get("decision"),
                "next": evidence.get("next"),
                "validation": evidence.get("validation"),
            }
        )
    )


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S10-P02",
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
            "uv run --frozen --python 3.12 python uncertainty.py --fixture machine/tests/fixtures/S10_P02.json --parameters machine/facts/parameters.json --output bootstrap_manifest.json",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S10/P02/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S10/P02_test.py --junitxml=machine/evidence/S10/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S10/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S10-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"runtime_iterations": 1000, "evaluation_iterations": 2000, "real_time_wait_performed": False},
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S10_P02_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
    replacement = {
        "id": "INDEX-AC-S10-P02",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S10/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [replacement if row.get("id") == replacement["id"] else row for row in rows]
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise UncertaintyAcceptanceError("planned S10/P02 evidence-index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def _evidence_index_is_bound(root: Path, evidence_hash: str) -> bool:
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception:
        return False
    expected = {
        "id": "INDEX-AC-S10-P02",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S10/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = [row for row in rows if row.get("id") == expected["id"]]
    return len(matches) == 1 and matches[0] == expected


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise UncertaintyAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise UncertaintyAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S10/P03_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise UncertaintyAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    evidence_hash = sha256_file(root / EVIDENCE_PATH)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "CONSERVATIVE_PROBABILITY_READY_DOWNSTREAM_DECIMAL_GATE_REQUIRED"
        and evidence.get("next") == "S10/P03_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and _evidence_index_is_bound(root, evidence_hash)
    )
    if not valid:
        raise UncertaintyAcceptanceError("existing S10/P02 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "next": "S10/P03_READY_NOT_STARTED",
    }
