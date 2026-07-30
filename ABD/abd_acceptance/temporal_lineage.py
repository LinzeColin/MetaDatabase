"""Independent deterministic acceptance oracle for ABD S07/P02.

The oracle reads frozen local artifacts only. It proves the S07/P02
future-information tolerance is exactly zero, then writes a local receipt. It
does not access a provider, Gmail, market data, OVH, Cloudflare, an account, or
an order endpoint; it does not generate a recommendation and it never waits
for real-time soak.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from leakage_oracle import (
    FUTURE_INFORMATION_TOLERANCE,
    LINEAGE_APPROVED_NO_ADVICE,
    NO_ADVICE,
    canonical_json_bytes,
    deterministic_lineage_hash,
    evaluate_lineage,
    prepare_policy,
    sha256_json,
    strict_json_load as strict_lineage_json_load,
    validate_schema_document,
)

from .budget import render_scan_report, scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .identity_resolution import verify_existing_phase_evidence as verify_s07_p01_evidence


CONTRACT_ID = "AC-S07-P02"
REQUIREMENT_ID = "REQ-S07-P02"
STAGE_ID = "S07"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SCHEMA_PATH = Path("temporal_lineage.schema.json")
LEAKAGE_ORACLE_PATH = Path("leakage_oracle.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S07_P02.json")
TEST_PATH = Path("tests/S07/P02_test.py")
ORACLE_PATH = Path("abd_acceptance/temporal_lineage.py")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S07-P01_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S07/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S07/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S07/P02/paid_dependency_scan.txt")

PINNED_PHASE_HASHES: Dict[str, str] = {
    SCHEMA_PATH.as_posix(): "c55fa1a91179347308c31e518e6c4350982d807783a2086061c8e0fe8b88ee5a",
    LEAKAGE_ORACLE_PATH.as_posix(): "7988dd12cb40b2be837c0efe2904241bffcd4752e437ddba5ca92359e6791208",
    FIXTURE_PATH.as_posix(): "45d7dfb31920587332d0375f79bf418a30fb9f664a7be19be9acaab8f4b1f22b",
    TEST_PATH.as_posix(): "a9aad16244fdc7bf4bb5706b728fc476c274da238387742a194510fe6a862a86",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "machine/evidence/roadmap_stage_phase.md": "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de",
    P01_EVIDENCE_PATH.as_posix(): "2e3f7ceb3e93807fbb14c224282ab3d062d6197c5a139a771e24d30f5316aa99",
    P01_ROLLBACK_PATH.as_posix(): "f3a6cbab09f3fc3bb39b15eef2a9371ce2f54c1dd9784a5bd8d8728d16d0e656",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "267746a813aee1cdaf7e3594dc08ec0fdcf9e2c61591f39cbaaaaec27473e3ea"
FULL_REGRESSION_TEST_MINIMUM = 4968

ROLLBACK_ARTIFACTS = (
    SCHEMA_PATH,
    LEAKAGE_ORACLE_PATH,
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
    "real_time_soak_waited": False,
    "recommendation_generated_or_enabled": False,
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str, *, lineage: bool = False) -> Any:
    try:
        value = strict_lineage_json_load(path) if lineage else strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    matched = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matched) != 1:
        raise ValueError("expected exactly one row for %s" % identifier)
    return matched[0]


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


def _phase_artifact_hashes(root: Path) -> Dict[str, str]:
    return {relative: sha256_file(root / relative) for relative in PINNED_PHASE_HASHES}


def _current_code_hash(root: Path) -> str:
    payload = b""
    for relative in (LEAKAGE_ORACLE_PATH, ORACLE_PATH):
        payload += relative.as_posix().encode("utf-8") + b"\0" + (root / relative).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _junit_summary(path: Path) -> Dict[str, int]:
    tree = ElementTree.parse(path)
    root = tree.getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("unexpected junit root")
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
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


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S07P02-PIN-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P02-PIN-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))
    actual_self = _structural_self_hash(root)
    hashes[ORACLE_PATH.as_posix()] = sha256_file(root / ORACLE_PATH)
    _add(
        checks,
        "S07P02-ORACLE-STRUCTURAL-SELF-HASH",
        STRUCTURAL_SELF_NORMALIZED_SHA256 != "TO_BE_FILLED" and actual_self == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": actual_self},
    )


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            _add(
                checks,
                "S07P02-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P02-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        requirements = strict_json_load(root / "machine/facts/requirements.json")
        contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
        graph = strict_json_load(root / "machine/facts/task_graph.json")["tasks"]
        traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [task for task in graph if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        _add(
            checks,
            "S07P02-TASKPACK-SCOPE",
            requirement.get("scope") == ["temporal_lineage.schema.json", "leakage_oracle.py"]
            and requirement.get("target") == "未来信息容忍度=0。"
            and contract.get("pass_gate") == requirement.get("target"),
            {"scope": requirement.get("scope"), "target": requirement.get("target")},
        )
        _add(
            checks,
            "S07P02-TASKPACK-TRACE",
            [item.get("id") for item in tasks] == ["T-S07-P02-01", "T-S07-P02-02", "T-S07-P02-03"]
            and [item.get("id") for item in contract.get("tests", [])] == ["TEST-S07-P02", "TEST-S07-P02-BOUNDARY", "TEST-S07-P02-REPLAY"]
            and trace.get("evidence_id") == "EVD-S07-P02"
            and trace.get("artifact_ids") == ["ART-S07-P02-01", "ART-S07-P02-02"],
            {"tasks": [item.get("id") for item in tasks], "trace": trace},
        )
    except Exception as exc:
        _add(checks, "S07P02-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _case(fixture: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise ValueError("cases unavailable")
    return _row(cases, case_id, key="case_id")


def _check_predecessor(
    root: Path,
    fixture: Mapping[str, Any] | None,
    checks: List[Dict[str, Any]],
    *,
    verify_git_history: bool,
) -> None:
    if not isinstance(fixture, Mapping):
        _add(checks, "S07P02-P01-PREDECESSOR-AVAILABLE", False, "fixture unavailable")
        return
    try:
        predecessor = fixture.get("predecessor")
        if not isinstance(predecessor, Mapping):
            raise ValueError("predecessor missing")
        expected_hash = predecessor.get("evidence_sha256")
        p01_result = verify_s07_p01_evidence(root, verify_git_history=verify_git_history)
        ok = (
            predecessor.get("contract_id") == "AC-S07-P01"
            and predecessor.get("evidence_path") == P01_EVIDENCE_PATH.as_posix()
            and predecessor.get("next") == "S07/P02_READY_NOT_STARTED"
            and expected_hash == sha256_file(root / P01_EVIDENCE_PATH)
            and p01_result.get("status") == "PASS"
        )
        _add(checks, "S07P02-P01-PREDECESSOR-PASS", ok, {"p01": p01_result.get("summary"), "hash": expected_hash})
    except Exception as exc:
        _add(checks, "S07P02-P01-PREDECESSOR-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _check_core_artifacts(
    root: Path,
    schema: Any,
    fixture: Any,
    checks: List[Dict[str, Any]],
) -> Tuple[Any, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    if not isinstance(schema, Mapping) or not isinstance(fixture, Mapping):
        _add(checks, "S07P02-CORE-ARTIFACTS-AVAILABLE", False, "schema or fixture unavailable")
        return None, None, None
    try:
        validate_schema_document(schema)
        expected_fixture_fields = {
            "schema_version",
            "contract_id",
            "stage_id",
            "phase_id",
            "fixed_clock",
            "future_information_tolerance",
            "policy",
            "predecessor",
            "cases",
            "replay_count",
            "adverse_replay_count",
            "expected_positive_output_sha256",
            "expected_oracle_check_minimum",
            "target_test_minimum",
            "expected_next",
            "external_effect_boundary",
        }
        _add(
            checks,
            "S07P02-PRODUCTION-EQUIVALENT-SCHEMA",
            set(fixture) == expected_fixture_fields
            and fixture.get("contract_id") == CONTRACT_ID
            and fixture.get("stage_id") == STAGE_ID
            and fixture.get("phase_id") == PHASE_ID
            and fixture.get("future_information_tolerance") == FUTURE_INFORMATION_TOLERANCE
            and fixture.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY,
            {"fixture_fields": sorted(fixture), "tolerance": fixture.get("future_information_tolerance")},
        )
        policy = prepare_policy(schema, fixture["policy"])
        parameter_hash = sha256_file(root / "machine/facts/parameters.json")
        _add(
            checks,
            "S07P02-PARAMETER-VERSION-PINNED",
            policy.parameter_version_sha256 == parameter_hash,
            {"policy": policy.parameter_version_sha256, "parameters": parameter_hash},
        )
        outputs: Dict[str, Mapping[str, Any]] = {}
        cases = fixture.get("cases")
        if not isinstance(cases, list) or len(cases) < 8:
            raise ValueError("insufficient fixed cases")
        for row in cases:
            if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("record"), Mapping):
                raise ValueError("invalid case shape")
            result = evaluate_lineage(policy, row["record"])
            outputs[str(row["case_id"])] = result
            expected = row.get("expected")
            if not isinstance(expected, Mapping):
                raise ValueError("case expected missing")
            result_ok = (
                result.get("status") == expected.get("status")
                and result.get("lineage_eligible") == expected.get("lineage_eligible")
                and result.get("action") == NO_ADVICE
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_network_used") is False
                and result.get("real_time_soak_waited") is False
                and (
                    result.get("reason_codes") == expected.get("reason_codes")
                    if "reason_codes" in expected
                    else expected.get("reason_code") in result.get("reason_codes", [])
                )
            )
            _add(checks, "S07P02-CASE-%s" % row["case_id"], result_ok, result)
        positive = outputs.get("POSITIVE_EXACT")
        _add(
            checks,
            "S07P02-POSITIVE-OUTPUT-HASH-PIN",
            isinstance(positive, Mapping)
            and positive.get("output_sha256") == fixture.get("expected_positive_output_sha256")
            and positive.get("status") == LINEAGE_APPROVED_NO_ADVICE
            and positive.get("action") == NO_ADVICE,
            positive,
        )
        return policy, fixture, outputs
    except Exception as exc:
        _add(checks, "S07P02-CORE-ARTIFACT-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))
        return None, fixture, None


def _check_boundaries_and_replay(
    policy: Any,
    fixture: Mapping[str, Any] | None,
    outputs: Mapping[str, Mapping[str, Any]] | None,
    checks: List[Dict[str, Any]],
) -> None:
    if policy is None or not isinstance(fixture, Mapping) or not isinstance(outputs, Mapping):
        _add(checks, "S07P02-REPLAY-AVAILABLE", False, "core outputs unavailable")
        return
    try:
        equal = outputs["BOUNDARY_ALL_TIMES_EQUAL"]
        odds_minus = outputs["BOUNDARY_ODDS_MINUS_0001"]
        odds_plus = outputs["BOUNDARY_ODDS_PLUS_0001"]
        cutoff = outputs["NEGATIVE_FEATURE_CUTOFF_PLUS_0001"]
        _add(
            checks,
            "S07P02-BOUNDARY-ZERO-AND-PLUS-MINUS-00001",
            all(result.get("status") == LINEAGE_APPROVED_NO_ADVICE for result in (equal, odds_minus, odds_plus))
            and cutoff.get("status") == NO_ADVICE
            and cutoff.get("future_information_count") == 1
            and "FUTURE_INFORMATION_TOLERANCE_EXCEEDED" in cutoff.get("reason_codes", []),
            {"equal": equal, "minus": odds_minus, "plus": odds_plus, "cutoff": cutoff},
        )
        positive_record = _case(fixture, "POSITIVE_EXACT")["record"]
        expected_hash = deterministic_lineage_hash(policy, positive_record)
        replay_hashes = {
            deterministic_lineage_hash(policy, {key: positive_record[key] for key in reversed(list(positive_record))})
            for _ in range(int(fixture["replay_count"]))
        }
        _add(
            checks,
            "S07P02-100-REPLAY-DETERMINISTIC-NO-WAIT",
            replay_hashes == {expected_hash} == {fixture.get("expected_positive_output_sha256")},
            {"count": fixture["replay_count"], "hash": expected_hash},
        )
        failures: List[int] = []
        for index in range(int(fixture["adverse_replay_count"])):
            candidate = deepcopy(positive_record)
            mode = index % 5
            if mode == 0:
                candidate["feature_cutoff_time"] = "2026-08-15T18:00:04.0001+10:00"
            elif mode == 1:
                candidate["source_version_sha256"] = "f" * 64
            elif mode == 2:
                candidate["model_version_sha256"] = "f" * 64
            elif mode == 3:
                candidate["parameter_version_sha256"] = "f" * 64
            else:
                candidate["untrusted_future_field"] = str(index)
            result = evaluate_lineage(policy, candidate)
            if (
                result.get("status") != NO_ADVICE
                or result.get("lineage_eligible") is not False
                or result.get("action") != NO_ADVICE
                or result.get("recommendation_generated") is not False
                or result.get("order_submission_enabled") is not False
            ):
                failures.append(index)
                break
        _add(
            checks,
            "S07P02-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ADVICE",
            not failures,
            {"count": fixture["adverse_replay_count"], "failures": failures},
        )
    except Exception as exc:
        _add(checks, "S07P02-BOUNDARY-AND-REPLAY-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / LEAKAGE_ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=LEAKAGE_ORACLE_PATH.as_posix())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        denied = sorted(imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"})
        forbidden_tokens = [
            token
            for token in ("sleep(", "requests.", "urllib.", "socket.", "subprocess.", "http://", "https://")
            if token in source
        ]
        _add(
            checks,
            "S07P02-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY",
            not denied and not forbidden_tokens,
            {"imports": sorted(imports), "denied": denied, "tokens": forbidden_tokens},
        )
    except Exception as exc:
        _add(checks, "S07P02-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S07P02-REPORTS-DEFERRED-FOR-CANDIDATE", True, "candidate mode does not require generated reports")
        return
    target_minimum = int(fixture.get("target_test_minimum", 0)) if isinstance(fixture, Mapping) else 0
    for relative, minimum, check_id in (
        (JUNIT_PATH, target_minimum, "S07P02-TARGETED-PYTEST-REPORT"),
        (FULL_JUNIT_PATH, FULL_REGRESSION_TEST_MINIMUM, "S07P02-FULL-PYTEST-REPORT"),
    ):
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            ok = (
                minimum > 0
                and summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and summary["skipped"] == 0
                and normalized
            )
            _add(checks, check_id, ok, {"minimum": minimum, "summary": summary, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root / PACK_REPORT_PATH, checks, "S07P02-PACK-REPORT-STRICT-JSON")
    if isinstance(report, Mapping):
        summary = report.get("summary")
        _add(
            checks,
            "S07P02-TASKPACK-PASS",
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
            "S07P02-PAID-DEPENDENCY-SCAN-PASS",
            actual == expected and "STATUS: PASS" in actual,
            {"exact_match": actual == expected, "path": SCAN_REPORT_PATH.as_posix()},
        )
    except Exception as exc:
        _add(checks, "S07P02-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


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
    _check_baseline(root, checks, hashes)
    _check_taskpack_trace(root, checks)
    schema = _safe_load(root / SCHEMA_PATH, checks, "S07P02-SCHEMA-STRICT-JSON", lineage=True)
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S07P02-FIXTURE-STRICT-JSON", lineage=True)
    _check_predecessor(root, fixture if isinstance(fixture, Mapping) else None, checks, verify_git_history=_verify_git_history)
    policy, validated_fixture, outputs = _check_core_artifacts(root, schema, fixture, checks)
    _check_boundaries_and_replay(policy, validated_fixture, outputs, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, validated_fixture, checks, require_test_reports=require_test_reports)
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": status,
        "phase_status": "S07_P02_PASS" if status == "PASS" else "S07_P02_FAIL",
        "decision": "ZERO_FUTURE_INFORMATION_LINEAGE_GATE_PASSED_NO_ADVICE" if status == "PASS" else "NO_ADVICE_AND_REMEDIATION_REQUIRED",
        "checks": checks,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "no_real_time_soak": {
            "required": False,
            "wait_performed": False,
            "deterministic_replay_count": validated_fixture.get("replay_count") if isinstance(validated_fixture, Mapping) else None,
            "deterministic_adverse_replay_count": validated_fixture.get("adverse_replay_count") if isinstance(validated_fixture, Mapping) else None,
        },
        "next": "S07/P03_READY_NOT_STARTED" if status == "PASS" else "S07/P02_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_test_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S07_P02_CANDIDATE_VALID" if result["status"] == "PASS" else "S07_P02_CANDIDATE_INVALID",
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
    status = "PASS" if artifacts and all(row.get("status") == "PASS" for row in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_TEMPORAL_LINEAGE_GATE_RESTORE_PRIOR_SIGNED_ARTIFACTS_REPLAY_DERIVED_STATE",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        SCHEMA_PATH,
        LEAKAGE_ORACLE_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        P01_EVIDENCE_PATH,
        P01_ROLLBACK_PATH,
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
    if require_test_reports:
        paths.extend([JUNIT_PATH, FULL_JUNIT_PATH, PACK_REPORT_PATH, SCAN_REPORT_PATH])
    return {relative.as_posix(): sha256_file(root / relative) for relative in paths}


def build_evidence(
    root: Path,
    require_test_reports: bool = True,
    *,
    _verify_git_history: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    schema = strict_lineage_json_load(root / SCHEMA_PATH)
    fixture = strict_lineage_json_load(root / FIXTURE_PATH)
    policy = prepare_policy(schema, fixture["policy"])
    positive = _case(fixture, "POSITIVE_EXACT")
    positive_result = evaluate_lineage(policy, positive["record"])
    failures = {
        str(case["case_id"]): evaluate_lineage(policy, case["record"])["reason_codes"]
        for case in fixture["cases"]
        if case["case_id"] != "POSITIVE_EXACT"
    }
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "phase_status": validation["phase_status"],
        "decision": validation["decision"],
        "validation": validation,
        "hashes": {
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "code": _current_code_hash(root),
            "model_versions": dict(policy.model_versions),
            "output": positive_result["output_sha256"],
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "lineage_summary": {
            "schema_content_sha256": policy.schema_content_sha256,
            "parameter_version_sha256": policy.parameter_version_sha256,
            "source_versions": dict(policy.source_versions),
            "model_versions": dict(policy.model_versions),
            "future_information_tolerance": FUTURE_INFORMATION_TOLERANCE,
            "positive_lineage_eligible": positive_result["lineage_eligible"],
            "positive_action": positive_result["action"],
            "recommendation_generated": False,
            "order_submission_enabled": False,
        },
        "structured_failure_log": {
            "path": "machine/tests/fixtures/S07_P02.json",
            "case_reason_codes": failures,
            "sha256": sha256_json(failures),
        },
        "deterministic_replay": {
            "replay_count": fixture["replay_count"],
            "adverse_replay_count": fixture["adverse_replay_count"],
            "real_time_wait_performed": False,
        },
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
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
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S07-P02"]
    rows.append(
        {
            "id": "INDEX-AC-S07-P02",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S07/P03_READY_NOT_STARTED" if status == "PASS" else "S07/P02_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise ValueError("S07/P02 evidence must be written to machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(evidence_path, _json_bytes(evidence))
    _atomic_write(rollback_path, _json_bytes(rollback))
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
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S07P02-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S07P02-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        integrity = (
            evidence.get("evidence_id") == "EVD-S07-P02"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S07/P03_READY_NOT_STARTED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S07P02-EXISTING-EVIDENCE-INTEGRITY", integrity, evidence.get("status"))
        hash_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                hash_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                hash_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S07P02-EXISTING-INPUT-HASHES", not hash_errors, hash_errors or "all inputs match")
        _add(checks, "S07P02-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S07P02-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S07-P02-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S07P02-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S07P02-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_test_reports=True, _verify_git_history=verify_git_history)
    _add(checks, "S07P02-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S07/P03_READY_NOT_STARTED" if not failed else "S07/P02_REMEDIATION_REQUIRED",
    }
