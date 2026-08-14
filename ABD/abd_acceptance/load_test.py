"""Fail-closed acceptance oracle for ABD S17/P01 local load controls.

S17/P01 validates only a frozen local count-conserving replay.  It does not
turn a planned OVH VPS-1 into an observed host-capacity or deployment claim.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load as acceptance_json_load
from .load_test_engine import (
    CAPACITY_EVIDENCE_PATH,
    CLAIM_BOUNDARY,
    CONTRACT_ID,
    COSTS_PATH,
    EXECUTION_POLICY,
    FIXED_CLOCK,
    FIXTURE_PATH,
    INPUT_MODE,
    LOAD_PROFILE_PATH,
    LOAD_TEST_PATH,
    PRODUCT_VERSION,
    RESOURCE_CONTRACT,
    LoadTestInputError,
    artifact_sha256,
    build_artifacts,
    canonical_json_bytes,
    load_fixture,
    sha256_file as engine_sha256_file,
    strict_json_load,
    validate_artifacts,
)
from .model_release_gate import verify_existing_phase_evidence as verify_s16_p04
from .traceability_proxy import verify_existing_phase_evidence as verify_s15_p04


REQUIREMENT_ID = "REQ-S17-P01"
STAGE_ID = "S17"
PHASE_ID = "P01"
ORACLE_PATH = Path("abd_acceptance/load_test.py")
CORE_PATH = Path("abd_acceptance/load_test_engine.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
GENERATOR_PATH = LOAD_TEST_PATH
TEST_PATH = Path("tests/S17/P01_test.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S17-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S17/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S17/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"
FEATURE_FLAG_ID = "load:s17_frozen_full_history_10x"
SIGNED_ORACLE_SHA256 = "922ccd92b9c473169c6e6c6b00dcf767f8bc8c0bd551e8851cc4cc3014be0392"
SIGNED_DISPATCHER_SHA256 = "c346e9ccf167f3b400df7fe91eb9410dfd1779ba7babda6249d05a264ec36804"
P01_SHARED_DISPATCHER_SUCCESSOR_STRUCTURAL_SHA256 = "ce0a2c5f3c5f4d3aa6ad70bf777f26b1fa31b597dde691e09f9fb52a9459275e"

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

PREDECESSORS = {
    "AC-S15-P04": {
        "evidence_path": Path("machine/evidence/EVD-S15-P04.json"),
        "evidence_sha256": "3fd288e66d3c473881dc92257992eb41b85422a5c0aaa92f1ff00e202a15feda",
        "next": "S15/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_s15_p04,
    },
    "AC-S16-P04": {
        "evidence_path": Path("machine/evidence/EVD-S16-P04.json"),
        "evidence_sha256": "5543c7963bb6d8de97cd1e5c1872e2576fddde3dc98805fce48d763633f6ae45",
        "next": "S16/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_s16_p04,
    },
}

EXPECTED_TEST_IDS = ("TEST-S17-P01", "TEST-S17-P01-BOUNDARY", "TEST-S17-P01-REPLAY")
EXPECTED_TASK_IDS = ("T-S17-P01-01", "T-S17-P01-02", "T-S17-P01-03")
EXPECTED_ARTIFACT_IDS = ("ART-S17-P01-01", "ART-S17-P01-02", "ART-S17-P01-03")
EXPECTED_OUTPUTS = {
    "T-S17-P01-01": ["load_test.py", "load_profile.json", "capacity_evidence.json"],
    "T-S17-P01-02": ["tests/S17/P01_test.py", "machine/tests/fixtures/S17_P01.json"],
    "T-S17-P01-03": ["machine/evidence/EVD-S17-P01.json", "machine/evidence/EVD-S17-P01_rollback.json"],
}
EXTERNAL_EFFECT_BOUNDARY = {
    **CLAIM_BOUNDARY,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "owner_final_order_only": True,
}


class LoadTestAcceptanceError(ValueError):
    """Raised when S17/P01 evidence cannot be reproduced safely."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


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
            raise LoadTestAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise LoadTestAcceptanceError("JSONL row %d must be an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise LoadTestAcceptanceError("rows are unavailable")
    matching = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matching) != 1:
        raise LoadTestAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matching[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = acceptance_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S17P01-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S17P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S17P01-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S17P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S17P01-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise LoadTestAcceptanceError("task graph is unavailable")
        phase_tasks = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == ["load_test.py", "load_profile.json", "capacity_evidence.json"]
            and requirement.get("target") == "VPS-1资源门内且无静默丢数据。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S17-P01 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S17-P01"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P01-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "VPS-1资源门内且无静默丢数据。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("kind") == "PHASE_EVIDENCE"
            and row.get("stage_id") == STAGE_ID
            and row.get("contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("artifact_sha256") == (sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING")
            and row.get("next") == "S17/P02_READY_NOT_STARTED"
        )
        _add(checks, "S17P01-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S17P01-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for contract_id, spec in PREDECESSORS.items():
        try:
            result = spec["verifier"](root)
            path = root / spec["evidence_path"]
            actual = sha256_file(path)
            valid = (
                result.get("status") == "PASS"
                and result.get("contract_id") == contract_id
                and result.get("evidence_sha256") == spec["evidence_sha256"]
                and result.get("next") == spec["next"]
                and actual == spec["evidence_sha256"]
            )
            detail: Any = result
            hashes[spec["evidence_path"].as_posix()] = actual
        except Exception as exc:
            valid = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S17P01-PREDECESSOR-%s-CURRENT" % contract_id, valid, detail)


def _check_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    try:
        fixture = load_fixture(root / FIXTURE_PATH)
        expected = build_artifacts(root, fixture)
        actual = validate_artifacts(root, fixture)
        profile = actual[LOAD_PROFILE_PATH.as_posix()]
        capacity = actual[CAPACITY_EVIDENCE_PATH.as_posix()]
        profile_ok = (
            profile.get("artifact_id") == "ART-S17-P01-02"
            and profile.get("input_mode") == INPUT_MODE
            and profile.get("resource_contract") == RESOURCE_CONTRACT
            and profile.get("load_definition", {}).get("load_multiplier") == 10
            and profile.get("load_definition", {}).get("ten_x_event_count") == 12000
            and profile.get("source_generator", {}).get("artifact_id") == "ART-S17-P01-01"
            and profile.get("source_generator", {}).get("path") == GENERATOR_PATH.as_posix()
            and profile.get("source_generator", {}).get("sha256") == engine_sha256_file(root / GENERATOR_PATH)
        )
        capacity_ok = (
            capacity.get("artifact_id") == "ART-S17-P01-03"
            and capacity.get("profile_sha256") == artifact_sha256(profile)
            and capacity.get("resource_gate", {}).get("local_envelope_passed") is True
            and capacity.get("resource_gate", {}).get("actual_vps_capacity_measured") is False
            and capacity.get("resource_gate", {}).get("runtime_deployment_allowed") is False
            and capacity.get("no_silent_data_loss", {}).get("passed") is True
            and capacity.get("no_silent_data_loss", {}).get("silent_drop_count") == 0
            and capacity.get("no_silent_data_loss", {}).get("missing_disposition_count") == 0
            and capacity.get("decision") == fixture["expected_decision"]
            and capacity.get("next") == fixture["expected_next"]
        )
        deterministic = expected == actual
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        hashes[COSTS_PATH.as_posix()] = sha256_file(root / COSTS_PATH)
        hashes[GENERATOR_PATH.as_posix()] = sha256_file(root / GENERATOR_PATH)
        hashes[LOAD_PROFILE_PATH.as_posix()] = sha256_file(root / LOAD_PROFILE_PATH)
        hashes[CAPACITY_EVIDENCE_PATH.as_posix()] = sha256_file(root / CAPACITY_EVIDENCE_PATH)
        _add(checks, "S17P01-ARTIFACT-REPLAY-EXACT", deterministic, {path: artifact_sha256(value) for path, value in actual.items()})
        _add(checks, "S17P01-FROZEN-10X-LOAD-PROFILE-EXACT", profile_ok, profile.get("load_definition"))
        _add(checks, "S17P01-VPS-ENVELOPE-AND-NO-SILENT-DROP-EXACT", capacity_ok, capacity.get("resource_gate"))
        return fixture
    except Exception as exc:
        _add(checks, "S17P01-ARTIFACT-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        imports: set[str] = set()
        call_names: set[str] = set()
        source = ""
        for relative in (CORE_PATH, ORACLE_PATH, GENERATOR_PATH):
            content = (root / relative).read_text(encoding="utf-8")
            source += content
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
                    call_names.add(node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
        forbidden = {"asyncio", "http", "os", "requests", "socket", "smtplib", "subprocess", "time", "urllib", "webbrowser"}
        url_prefixes = ("http:" + "//", "https:" + "//")
        url_literals = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(url_prefixes)
        ]
        valid = not imports.intersection(forbidden) and not call_names.intersection({"Popen", "sleep", "submit_order", "retry_order"}) and not url_literals
        detail: Any = {"imports": sorted(imports), "forbidden": sorted(imports.intersection(forbidden)), "url_literals": url_literals}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P01-LOCAL-ONLY-STATIC-BOUNDARY", valid, detail)


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        required_fragments = (
            "from .load_test import verify_existing_phase_evidence as verify_load_test_phase_evidence",
            "from .load_test import write_phase_evidence as write_load_test_phase_evidence",
            '"AC-S17-P01": verify_load_test_phase_evidence,',
            '"AC-S17-P01": write_load_test_phase_evidence,',
        )
        valid = all(fragment in source for fragment in required_fragments)
        hashes[CLI_PATH.as_posix()] = sha256_file(root / CLI_PATH)
        detail: Any = {"required_fragments": len(required_fragments), "matched": sum(fragment in source for fragment in required_fragments)}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P01-CLI-WRITER-AND-VERIFIER-EXACT", valid, detail)


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    if not suites:
        raise LoadTestAcceptanceError("JUnit has no suite")
    summary = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    normalized = all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S17P01-TARGETED-REPORTS", True, "deferred until local signing")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        expected_minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        junit_ok = summary["tests"] >= expected_minimum and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
        detail: Any = summary
    except Exception as exc:
        junit_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P01-TARGETED-PYTEST-REPORT", junit_ok, detail)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(marker in scan for marker in ("STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"))
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = acceptance_json_load(root / PACK_REPORT_PATH)
        pack_ok = isinstance(report, Mapping) and report.get("status") == "PASS"
    except Exception as exc:
        pack_ok = False
        report = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S17P01-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": status,
        "decision": "S17_P01_FROZEN_FULL_HISTORY_10X_LOAD_PASS_P02_REQUIRED" if status == "PASS" else "S17_P01_REMEDIATION_REQUIRED",
        "next": "S17/P02_READY_NOT_STARTED" if status == "PASS" else "S17/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(sorted(hashes.items())),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack(root, checks)
    _check_predecessors(root, checks, hashes)
    fixture = _check_artifacts(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_cli_wiring(root, checks, hashes)
    _check_reports(root, fixture, checks, require_test_reports)
    _add(checks, "S17P01-EXTERNAL-EFFECT-BOUNDARY-EXACT", EXTERNAL_EFFECT_BOUNDARY["external_network_accessed"] is False and EXTERNAL_EFFECT_BOUNDARY["real_vps_resource_observed_or_measured"] is False and EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False and EXTERNAL_EFFECT_BOUNDARY["order_submission_enabled"] is False and EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False, EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (CORE_PATH, ORACLE_PATH, CLI_PATH, GENERATOR_PATH, FIXTURE_PATH, LOAD_PROFILE_PATH, CAPACITY_EVIDENCE_PATH, COSTS_PATH, *[spec["evidence_path"] for spec in PREDECESSORS.values()])
    artifacts = {
        path.as_posix(): {"status": "PASS" if (root / path).is_file() else "FAIL", "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S17-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "feature_flag_id": FEATURE_FLAG_ID,
        "mode": "DISABLE_LOCAL_LOAD_REPLAY_KEEP_RUNTIME_DEPLOYMENT_BLOCKED",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_vps_resource_observed_or_measured": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, require_test_reports: bool) -> Dict[str, str]:
    paths = [CORE_PATH, ORACLE_PATH, CLI_PATH, GENERATOR_PATH, FIXTURE_PATH, LOAD_PROFILE_PATH, CAPACITY_EVIDENCE_PATH, COSTS_PATH, *PREDECESSORS.values()]
    normalized: list[Path] = []
    for path in paths:
        normalized.append(path["evidence_path"] if isinstance(path, Mapping) else path)
    normalized.extend(Path(path) for path in BASELINE_HASHES)
    if require_test_reports:
        normalized.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(normalized), key=lambda item: item.as_posix())}


def _successor_oracle_is_exact(root: Path) -> bool:
    """Pin the small verifier evolution needed for shared-dispatcher growth.

    S17/P01 was signed before later S17 handlers existed.  Only this verifier's
    explicitly normalized successor source may interpret the shared dispatcher
    and regenerated static-pack report as mutable shared infrastructure.
    """

    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        normalized = re.sub(
            r'(?m)^(P01_SHARED_DISPATCHER_SUCCESSOR_STRUCTURAL_SHA256 = ")[^"]+("\s*)$',
            r'\1TO_BE_FILLED\2',
            source,
        )
        return (
            P01_SHARED_DISPATCHER_SUCCESSOR_STRUCTURAL_SHA256 != "TO_BE_FILLED"
            and hashlib.sha256(normalized.encode("utf-8")).hexdigest() == P01_SHARED_DISPATCHER_SUCCESSOR_STRUCTURAL_SHA256
        )
    except OSError:
        return False


def _shared_dispatcher_retains_p01_wiring(root: Path) -> bool:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        fragments = (
            "from .load_test import verify_existing_phase_evidence as verify_load_test_phase_evidence",
            "from .load_test import write_phase_evidence as write_load_test_phase_evidence",
            '"AC-S17-P01": verify_load_test_phase_evidence,',
            '"AC-S17-P01": write_load_test_phase_evidence,',
        )
        return all(source.count(fragment) == 1 for fragment in fragments)
    except OSError:
        return False


def _regenerated_pack_report_is_pass(root: Path) -> bool:
    try:
        report = acceptance_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary") if isinstance(report, Mapping) else None
        return (
            isinstance(summary, Mapping)
            and report.get("status") == "PASS"
            and summary.get("failed") == 0
            and summary.get("passed") == summary.get("checks")
        )
    except Exception:
        return False


def _signed_inputs_match(root: Path, evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("hashes", {}).get("inputs")
    if not isinstance(expected, Mapping) or not all(isinstance(path, str) and isinstance(digest, str) for path, digest in expected.items()):
        return False
    actual = _input_hashes(root, True)
    if dict(expected) == actual:
        return True
    if set(expected) != set(actual):
        return False
    changed = {path for path, digest in expected.items() if actual.get(path) != digest}
    allowed = {ORACLE_PATH.as_posix(), CLI_PATH.as_posix(), PACK_REPORT_PATH.as_posix()}
    if not changed or not changed.issubset(allowed):
        return False
    if (
        expected.get(ORACLE_PATH.as_posix()) != SIGNED_ORACLE_SHA256
        or expected.get(CLI_PATH.as_posix()) != SIGNED_DISPATCHER_SHA256
        or not _successor_oracle_is_exact(root)
    ):
        return False
    if CLI_PATH.as_posix() in changed and not _shared_dispatcher_retains_p01_wiring(root):
        return False
    if PACK_REPORT_PATH.as_posix() in changed and not _regenerated_pack_report_is_pass(root):
        return False
    return True


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S17-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S17_P01_LOCAL_LOAD_EVIDENCE_ONLY_P02_REQUIRED" if validation["status"] == "PASS" else "S17_P01_REMEDIATION_REQUIRED",
        "validation": validation,
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python load_test.py --root .",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S17/P01_test.py --junitxml=machine/evidence/S17/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S17/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S17/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S17-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"synthetic_full_history_events": 1200, "ten_x_events": 12000, "scenario_count": 4, "adverse_delta": "0.0001", "real_time_wait_performed": False},
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
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S17/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matching = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matching) != 1 or len(raw_lines) != len(rows):
        raise LoadTestAcceptanceError("S17/P01 evidence-index row must exist exactly once")
    raw_lines[matching[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise LoadTestAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise LoadTestAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S17/P02_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = acceptance_json_load(root / EVIDENCE_PATH)
    rollback = acceptance_json_load(root / ROLLBACK_EVIDENCE_PATH)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S17_P01_FROZEN_FULL_HISTORY_10X_LOAD_PASS_P02_REQUIRED"
        and evidence.get("next") == "S17/P02_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and _signed_inputs_match(root, evidence)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and index.get("kind") == "PHASE_EVIDENCE"
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S17/P02_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise LoadTestAcceptanceError("existing S17/P01 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S17/P02_READY_NOT_STARTED",
    }


__all__ = [
    "CORE_PATH",
    "CLI_PATH",
    "EVIDENCE_PATH",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FEATURE_FLAG_ID",
    "FIXTURE_PATH",
    "LoadTestAcceptanceError",
    "ORACLE_PATH",
    "TEST_PATH",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
