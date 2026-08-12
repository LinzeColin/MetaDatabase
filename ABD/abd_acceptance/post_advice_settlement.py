"""Independent fail-closed acceptance oracle for ABD S13/P03.

Only frozen synthetic advice, owner-confirmation, and settlement fixtures are
replayed.  The oracle cannot access an account, platform, mailbox, network, or
order endpoint, and it never treats an advice record as real funds evidence.
"""

from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ET

from performance_report import PerformanceReportError, build_performance_report
from post_advice_worker import CLAIM_BOUNDARY, PostAdviceError, canonical_json_bytes, canonical_sha256, make_advice_record
from result_settler import ResultSettlementError, settle_advice_record

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .platform_quote_check import verify_existing_phase_evidence as verify_platform_quote_check_phase_evidence


CONTRACT_ID = "AC-S13-P03"
REQUIREMENT_ID = "REQ-S13-P03"
STAGE_ID = "S13"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"

POST_ADVICE_PATH = Path("post_advice_worker.py")
SETTLER_PATH = Path("result_settler.py")
REPORT_PATH = Path("performance_report.py")
ORACLE_PATH = Path("abd_acceptance/post_advice_settlement.py")
TEST_PATH = Path("tests/S13/P03_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S13_P03.json")
PREDECESSOR_PATH = Path("machine/evidence/EVD-S13-P02.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S13-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S13/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S13/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAG_ID = "evidence:post_advice_settlement_fail_closed"
_FACT_PATHS = (
    Path("machine/facts/canonical_facts.json"),
    Path("machine/facts/parameters.json"),
    Path("machine/facts/requirements.json"),
    Path("machine/facts/acceptance_contracts.json"),
    Path("machine/facts/task_graph.json"),
    Path("machine/facts/traceability_matrix.json"),
    Path("machine/facts/roadmap.json"),
)


class PostAdviceSettlementAcceptanceError(ValueError):
    """Raised when the S13/P03 delivery cannot be replayed safely."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, relative.as_posix())
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise PostAdviceSettlementAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise PostAdviceSettlementAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise PostAdviceSettlementAcceptanceError("blank evidence-index row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise PostAdviceSettlementAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(value)
    return rows


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S13P03-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S13P03-CONTRACTS-PARSE")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S13P03-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S13P03-TRACEABILITY-PARSE")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [item for item in graph["tasks"] if item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        scope_ok = (
            requirement.get("scope") == ["post_advice_worker.py", "result_settler.py", "performance_report.py"]
            and requirement.get("target") == "没有确认时不伪造真实收益。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
        )
        _add(checks, "S13P03-TASKPACK-SCOPE-EXACT", scope_ok, {"scope": requirement.get("scope"), "target": requirement.get("target")})
        trace_ok = (
            [item.get("id") for item in tasks] == ["T-S13-P03-01", "T-S13-P03-02", "T-S13-P03-03"]
            and tasks[0].get("depends_on") == ["T-S13-P02-03"]
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == ["TEST-S13-P03", "TEST-S13-P03-BOUNDARY", "TEST-S13-P03-REPLAY"]
            and trace.get("evidence_id") == "EVD-S13-P03"
            and trace.get("artifact_ids") == ["ART-S13-P03-01", "ART-S13-P03-02", "ART-S13-P03-03"]
        )
        _add(checks, "S13P03-TASKPACK-TRACE-CLOSED", trace_ok, {"tasks": [item.get("id") for item in tasks], "trace": trace})
    except Exception as exc:
        _add(checks, "S13P03-TASKPACK-TRACE-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    try:
        predecessor = verify_platform_quote_check_phase_evidence(root)
        receipt = strict_json_load(root / PREDECESSOR_PATH)
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        index = _row(rows, "INDEX-AC-S13-P02")
        expected = fixture.get("predecessor") if isinstance(fixture, Mapping) else None
        actual_hash = sha256_file(root / PREDECESSOR_PATH)
        hashes[PREDECESSOR_PATH.as_posix()] = actual_hash
        passed = (
            isinstance(expected, Mapping)
            and predecessor.get("status") == "PASS"
            and predecessor.get("contract_id") == expected.get("contract_id") == "AC-S13-P02"
            and predecessor.get("next") == expected.get("next") == "S13/P03_READY_NOT_STARTED"
            and receipt.get("status") == "PASS"
            and receipt.get("next") == "S13/P03_READY_NOT_STARTED"
            and index.get("status") == "PASS"
            and index.get("artifact_sha256") == actual_hash
        )
        _add(checks, "S13P03-P02-PREDECESSOR-SIGNED-AND-INDEXED", passed, {"predecessor": predecessor, "index": index})
    except Exception as exc:
        _add(checks, "S13P03-P02-PREDECESSOR-SIGNED-AND-INDEXED", False, "%s: %s" % (type(exc).__name__, exc))


def _case_result(case_id: str, record: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "advice_status": record["advice_status"],
        "result_status": result["result_status"],
        "synthetic_pnl_cents": result["synthetic_pnl_cents"],
        "relative_closing_line_advantage": result["relative_closing_line_advantage"],
    }


def _check_fixture_and_runner(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S13P03-FIXTURE-PARSE")
    if not isinstance(fixture, Mapping):
        return None
    try:
        expected_fields = {
            "schema_version",
            "fixture_id",
            "fixed_clock",
            "parameters_sha256",
            "predecessor",
            "claim_boundary",
            "cases",
            "expected_case_count",
            "expected_synthetic_pnl_cents",
            "expected_mean_relative_closing_line_advantage",
            "expected_replay_sha256",
            "expected_preflight_minimum",
            "expected_next",
        }
        fixture_ok = (
            set(fixture) == expected_fields
            and fixture.get("schema_version") == "1.0.0"
            and fixture.get("fixture_id") == "FIX-S13-P03-POST-ADVICE-SETTLEMENT"
            and fixture.get("fixed_clock") == FIXED_CLOCK
            and fixture.get("claim_boundary") == CLAIM_BOUNDARY
            and fixture.get("expected_next") == "S13/P04_READY_NOT_STARTED"
            and isinstance(fixture.get("expected_preflight_minimum"), int)
            and not _contains_float(fixture)
        )
        _add(checks, "S13P03-FIXTURE-CONTRACT-EXACT", fixture_ok, {"fixture_id": fixture.get("fixture_id"), "fields": sorted(fixture)})
        parameter_hash = sha256_file(root / "machine/facts/parameters.json")
        _add(checks, "S13P03-PARAMETERS-HASH-EXACT", fixture.get("parameters_sha256") == parameter_hash, {"fixture": fixture.get("parameters_sha256"), "actual": parameter_hash})
        cases = fixture.get("cases")
        if not isinstance(cases, list) or len(cases) != fixture.get("expected_case_count"):
            raise PostAdviceSettlementAcceptanceError("fixture cases are invalid")
        seen_ids: set[str] = set()
        records: list[Mapping[str, Any]] = []
        results: list[Mapping[str, Any]] = []
        replay_cases: list[dict[str, Any]] = []
        cases_ok = True
        for item in cases:
            if not isinstance(item, Mapping) or set(item) != {"case_id", "advice", "confirmation", "settlement", "expected"}:
                raise PostAdviceSettlementAcceptanceError("case fields are not closed")
            case_id = item.get("case_id")
            if not isinstance(case_id, str) or case_id in seen_ids:
                raise PostAdviceSettlementAcceptanceError("case id is invalid or duplicated")
            seen_ids.add(case_id)
            record = make_advice_record(item.get("advice"), item.get("confirmation"))
            result = settle_advice_record(record, item.get("settlement"))
            expected = item.get("expected")
            expected_ok = (
                isinstance(expected, Mapping)
                and record.get("advice_status") == expected.get("advice_status")
                and result.get("result_status") == expected.get("result_status")
                and result.get("synthetic_pnl_cents") == expected.get("synthetic_pnl_cents")
                and result.get("relative_closing_line_advantage") == expected.get("relative_closing_line_advantage")
                and result.get("actual_return_claimed") is False
                and result.get("actual_return_cents") is None
                and result.get("claim_boundary") == CLAIM_BOUNDARY
            )
            cases_ok = cases_ok and expected_ok
            replay_cases.append(_case_result(case_id, record, result))
            records.append(record)
            results.append(result)
        _add(checks, "S13P03-FROZEN-CASE-RESULTS-EXACT", cases_ok, replay_cases)
        report = build_performance_report(records, results)
        report_ok = (
            report.get("synthetic_pnl_cents") == fixture.get("expected_synthetic_pnl_cents")
            and report.get("mean_relative_closing_line_advantage") == fixture.get("expected_mean_relative_closing_line_advantage")
            and report.get("actual_return_status") == "DO_NOT_CLAIM_ACTUAL_RETURN_UNCONFIRMED_ADVICE"
            and report.get("actual_return_claimed") is False
            and report.get("actual_return_cents") is None
            and report.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and report.get("claim_boundary") == CLAIM_BOUNDARY
        )
        _add(checks, "S13P03-REPORT-DOES-NOT-CLAIM-ACTUAL-RETURN", report_ok, report)
        replay = {"case_results": replay_cases, "report": report}
        replay_hash = canonical_sha256(replay)
        _add(checks, "S13P03-DETERMINISTIC-REPLAY-EXACT", replay_hash == fixture.get("expected_replay_sha256"), replay_hash)
        by_id = {item["case_id"]: item for item in replay_cases}
        adverse_boundary_ok = (
            Decimal(str(by_id["A03-CONFIRMED-SYNTHETIC-WIN"]["relative_closing_line_advantage"]))
            > Decimal(str(by_id["A05-CONFIRMED-FAVOURABLE-POINT-0001-VOID"]["relative_closing_line_advantage"]))
            > Decimal("0")
            > Decimal(str(by_id["A04-CONFIRMED-ADVERSE-POINT-0001-LOSS"]["relative_closing_line_advantage"]))
            and all(item.get("result_status") == "SYNTHETIC_SETTLED_NOT_ACTUAL_RETURN" for item in (by_id["A03-CONFIRMED-SYNTHETIC-WIN"], by_id["A04-CONFIRMED-ADVERSE-POINT-0001-LOSS"], by_id["A05-CONFIRMED-FAVOURABLE-POINT-0001-VOID"]))
        )
        _add(checks, "S13P03-POINT-0001-ADVERSE-ODDS-BOUNDARY-DOES-NOT-CREATE-ACTUAL-CLAIM", adverse_boundary_ok, {key: by_id[key] for key in ("A03-CONFIRMED-SYNTHETIC-WIN", "A04-CONFIRMED-ADVERSE-POINT-0001-LOSS", "A05-CONFIRMED-FAVOURABLE-POINT-0001-VOID")})
        no_confirmation = by_id["A01-UNCONFIRMED-ADVICE-ONLY"]
        _add(checks, "S13P03-NO-CONFIRMATION-NEVER-CLAIMS-ACTUAL-RETURN", no_confirmation["result_status"] == "UNCONFIRMED_DO_NOT_SETTLE_OR_CLAIM_ACTUAL_RETURN" and no_confirmation["synthetic_pnl_cents"] is None and no_confirmation["relative_closing_line_advantage"] is None, no_confirmation)
        for relative in (POST_ADVICE_PATH, SETTLER_PATH, REPORT_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
        return fixture
    except (PostAdviceError, ResultSettlementError, PerformanceReportError, PostAdviceSettlementAcceptanceError, ValueError, TypeError) as exc:
        _add(checks, "S13P03-FROZEN-RUNNER", False, "%s: %s" % (type(exc).__name__, exc))
        return fixture


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "asyncio", "time", "random", "os"}
    prohibited_literals = {"sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "web" + "hook", "smtp" + "lib"}
    failures: list[Any] = []
    for relative in (POST_ADVICE_PATH, SETTLER_PATH, REPORT_PATH):
        try:
            source = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            bad_imports = sorted(imports.intersection(prohibited_imports))
            bad_literals = sorted(item for item in prohibited_literals if item in source)
            if bad_imports or bad_literals:
                failures.append({"path": relative.as_posix(), "imports": bad_imports, "literals": bad_literals})
        except Exception as exc:
            failures.append({"path": relative.as_posix(), "error": "%s: %s" % (type(exc).__name__, exc)})
    _add(checks, "S13P03-STATIC-NO-NETWORK-SOAK-OR-ORDER", not failures, failures or "static boundary intact")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        scan = scan_dependency_budget(root)
        passed = scan.get("status") == "PASS" and scan.get("summary", {}).get("paid_or_unknown_dependencies") == 0
        _add(checks, "S13P03-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", passed, scan.get("summary"))
    except Exception as exc:
        _add(checks, "S13P03-ZERO-INCREMENTAL-CASH-AND-DEPENDENCY-GATE", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    }


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        cases = list(ET.parse(root / JUNIT_PATH).getroot().iter("testcase"))
        minimum = fixture.get("expected_preflight_minimum") if isinstance(fixture, Mapping) else None
        passed = (
            isinstance(minimum, int)
            and summary["tests"] >= minimum
            and not summary["failures"]
            and not summary["errors"]
            and not summary["skipped"]
            and all(case.attrib.get("time") == "0.000" for case in cases)
        )
        _add(checks, "S13P03-TARGETED-JUNIT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S13P03-TARGETED-JUNIT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S13P03-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S13P03-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S13P03-TASKPACK-REPORT-PARSE")
    _add(checks, "S13P03-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "POST_ADVICE_EVIDENCE_AND_SYNTHETIC_SETTLEMENT_READY_REAL_RETURN_REQUIRES_SEPARATE_EVIDENCE" if passed else "S13/P03_BLOCKED",
        "next": "S13/P04_READY_NOT_STARTED" if passed else "S13/P03_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "external_effect_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack_trace(root, checks)
    fixture = _check_fixture_and_runner(root, checks, hashes)
    _check_predecessor(root, fixture, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in (POST_ADVICE_PATH, SETTLER_PATH, REPORT_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_POST_ADVICE_SETTLEMENT_RESTORE_SIGNED_S13_P02_KEEP_ALL_EVIDENCE",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "actual_return_claimed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, POST_ADVICE_PATH, SETTLER_PATH, REPORT_PATH, TEST_PATH, FIXTURE_PATH, *_FACT_PATHS, PREDECESSOR_PATH]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "validation": evidence.get("validation")}))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S13-P03",
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
            "uv run --frozen --python 3.12 python -m pytest -q tests/S13/P03_test.py --junitxml=machine/evidence/S13/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S13/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S13/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S13-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"case_count": 5, "adverse_scenario_count": 2, "real_time_wait_performed": False},
        "external_effect_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S13_P03_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED",
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
    if len(raw_lines) != len(rows):
        raise PostAdviceSettlementAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-AC-S13-P03",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S13/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    matches = sum(row.get("id") == replacement["id"] for row in rows)
    if matches != 1:
        raise PostAdviceSettlementAcceptanceError("S13/P03 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise PostAdviceSettlementAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise PostAdviceSettlementAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/P04_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise PostAdviceSettlementAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "POST_ADVICE_EVIDENCE_AND_SYNTHETIC_SETTLEMENT_READY_REAL_RETURN_REQUIRES_SEPARATE_EVIDENCE"
        and evidence.get("next") == "S13/P04_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("actual_return_claimed") is False
    )
    if not valid:
        raise PostAdviceSettlementAcceptanceError("existing S13/P03 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S13/P04_READY_NOT_STARTED",
    }
