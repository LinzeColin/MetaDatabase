"""Independent deterministic acceptance oracle for ABD S07/P03.

The oracle reads frozen local artifacts and verifies append-only advice and
actual-funds ledgers.  It never contacts a provider, Gmail, a market, OVH,
Cloudflare, a financial account, or an order endpoint; it never waits for
real-time soak and it cannot create a recommendation or submit an order.
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

from ledger import (
    ACTUAL_FUNDS_LEDGER,
    ADVICE_LEDGER,
    GENESIS,
    LEDGER_VALID_NO_ADVICE,
    NO_ADVICE,
    LedgerValidationError,
    PreparedLedgerPolicy,
    canonical_json_bytes,
    deterministic_ledger_hash,
    evaluate_ledgers,
    make_event,
    prepare_policy,
    sha256_json,
    strict_json_load as strict_ledger_json_load,
    validate_schema_document,
)
from reconciliation_oracle import (
    deterministic_reconciliation_hash,
    reconcile_ledgers,
)

from .budget import render_scan_report, scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load
from .temporal_lineage import verify_existing_phase_evidence as verify_s07_p02_evidence


CONTRACT_ID = "AC-S07-P03"
REQUIREMENT_ID = "REQ-S07-P03"
STAGE_ID = "S07"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SCHEMA_PATH = Path("ledger.schema.json")
LEDGER_PATH = Path("ledger.py")
RECONCILIATION_ORACLE_PATH = Path("reconciliation_oracle.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S07_P03.json")
TEST_PATH = Path("tests/S07/P03_test.py")
ORACLE_PATH = Path("abd_acceptance/ledger_trace.py")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P02.json")
P02_ROLLBACK_PATH = Path("machine/evidence/EVD-S07-P02_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S07/P03/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S07/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S07/P03/paid_dependency_scan.txt")

PINNED_PHASE_HASHES: Dict[str, str] = {
    SCHEMA_PATH.as_posix(): "781df3d1e19b1571037ba440daf05fc85fda1cae7d6af528b1f046bfd03ef5ae",
    LEDGER_PATH.as_posix(): "3a316ea7c6ec347dc6bfa165037d11e0a022d1ca5185fae791bede9f62823cfd",
    RECONCILIATION_ORACLE_PATH.as_posix(): "aac95af984a4999aab2b8b3a3cbdbeb158e2766d9d1d66a33aec7249de004e8b",
    FIXTURE_PATH.as_posix(): "063a080e95c5d8583510cabaaa9a2fcfd77c46a4cf4d95c9415858073091eb8e",
    TEST_PATH.as_posix(): "e7120bf943f20c042291df957ee114bc13b52da1434cf8301d5f34a8c96e5090",
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
    P02_EVIDENCE_PATH.as_posix(): "05b99ca4038dfff43c1c4ae7591a708fe2e58aefc3f86e7ee38444072647b602",
    P02_ROLLBACK_PATH.as_posix(): "89f7a7ec50228ac49494d52c28c2f468e962414478ff86c64a420fbbdafb68d9",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "e4de999d04322f269e254fd3dc0f6ef9641f26af3d95e0d27999d1096eabb211"
FULL_REGRESSION_TEST_MINIMUM = 4968

ROLLBACK_ARTIFACTS = (
    SCHEMA_PATH,
    LEDGER_PATH,
    RECONCILIATION_ORACLE_PATH,
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


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str, *, ledger: bool = False) -> Any:
    try:
        value = strict_ledger_json_load(path) if ledger else strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ValueError("expected exactly one row for %s" % identifier)
    return matches[0]


def _case(fixture: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    return _row(fixture.get("cases"), case_id, key="case_id")


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
    for relative in (LEDGER_PATH, RECONCILIATION_ORACLE_PATH, ORACLE_PATH):
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
                "S07P03-PIN-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P03-PIN-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))
    hashes[ORACLE_PATH.as_posix()] = sha256_file(root / ORACLE_PATH)
    actual_self = _structural_self_hash(root)
    _add(
        checks,
        "S07P03-ORACLE-STRUCTURAL-SELF-HASH",
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
                "S07P03-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"),
                actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P03-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))


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
            "S07P03-TASKPACK-SCOPE",
            requirement.get("scope") == ["ledger.py", "ledger.schema.json", "reconciliation_oracle.py"]
            and requirement.get("target") == "无成交证据时真实资金账本不变化。"
            and contract.get("pass_gate") == requirement.get("target"),
            {"scope": requirement.get("scope"), "target": requirement.get("target")},
        )
        _add(
            checks,
            "S07P03-TASKPACK-TRACE",
            [item.get("id") for item in tasks] == ["T-S07-P03-01", "T-S07-P03-02", "T-S07-P03-03"]
            and [item.get("id") for item in contract.get("tests", [])] == ["TEST-S07-P03", "TEST-S07-P03-BOUNDARY", "TEST-S07-P03-REPLAY"]
            and trace.get("evidence_id") == "EVD-S07-P03"
            and trace.get("artifact_ids") == ["ART-S07-P03-01", "ART-S07-P03-02", "ART-S07-P03-03"],
            {"tasks": [item.get("id") for item in tasks], "trace": trace},
        )
    except Exception as exc:
        _add(checks, "S07P03-TASKPACK-TRACE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(
    root: Path,
    fixture: Mapping[str, Any] | None,
    checks: List[Dict[str, Any]],
    *,
    verify_git_history: bool,
) -> None:
    if not isinstance(fixture, Mapping):
        _add(checks, "S07P03-P02-PREDECESSOR-AVAILABLE", False, "fixture unavailable")
        return
    try:
        predecessor = fixture.get("predecessor")
        if not isinstance(predecessor, Mapping):
            raise ValueError("predecessor missing")
        p02_result = verify_s07_p02_evidence(root, verify_git_history=verify_git_history)
        ok = (
            predecessor.get("contract_id") == "AC-S07-P02"
            and predecessor.get("evidence_path") == P02_EVIDENCE_PATH.as_posix()
            and predecessor.get("rollback_path") == P02_ROLLBACK_PATH.as_posix()
            and predecessor.get("next") == "S07/P03_READY_NOT_STARTED"
            and predecessor.get("evidence_sha256") == sha256_file(root / P02_EVIDENCE_PATH)
            and predecessor.get("rollback_sha256") == sha256_file(root / P02_ROLLBACK_PATH)
            and p02_result.get("status") == "PASS"
        )
        _add(checks, "S07P03-P02-PREDECESSOR-PASS", ok, {"p02": p02_result.get("summary"), "evidence": predecessor.get("evidence_sha256")})
    except Exception as exc:
        _add(checks, "S07P03-P02-PREDECESSOR-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _check_core_artifacts(
    root: Path,
    schema: Any,
    fixture: Any,
    checks: List[Dict[str, Any]],
) -> Tuple[PreparedLedgerPolicy | None, Mapping[str, Any] | None, Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]]]:
    if not isinstance(schema, Mapping) or not isinstance(fixture, Mapping):
        _add(checks, "S07P03-CORE-ARTIFACTS-AVAILABLE", False, "schema or fixture unavailable")
        return None, None, {}
    try:
        validate_schema_document(schema)
        expected_fixture_fields = {
            "schema_version",
            "contract_id",
            "stage_id",
            "phase_id",
            "fixed_clock",
            "policy",
            "predecessor",
            "cases",
            "replay_count",
            "adverse_replay_count",
            "expected_no_execution_output_sha256",
            "expected_verified_execution_output_sha256",
            "expected_oracle_check_minimum",
            "target_test_minimum",
            "expected_next",
            "external_effect_boundary",
        }
        _add(
            checks,
            "S07P03-PRODUCTION-EQUIVALENT-SCHEMA",
            set(fixture) == expected_fixture_fields
            and fixture.get("contract_id") == CONTRACT_ID
            and fixture.get("stage_id") == STAGE_ID
            and fixture.get("phase_id") == PHASE_ID
            and fixture.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY,
            {"fixture_fields": sorted(fixture), "contract": fixture.get("contract_id")},
        )
        policy = prepare_policy(schema, fixture["policy"])
        parameter_hash = sha256_file(root / "machine/facts/parameters.json")
        _add(
            checks,
            "S07P03-PARAMETER-VERSION-PINNED",
            policy.parameter_version_sha256 == parameter_hash,
            {"policy": policy.parameter_version_sha256, "parameters": parameter_hash},
        )
        cases = fixture.get("cases")
        if not isinstance(cases, list) or len(cases) < 8:
            raise ValueError("insufficient fixed cases")
        outputs: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
        for row in cases:
            if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str):
                raise ValueError("invalid case")
            advice_events = row.get("advice_events")
            actual_events = row.get("actual_funds_events")
            expected = row.get("expected")
            if not isinstance(expected, Mapping):
                raise ValueError("case expected missing")
            ledger_result = evaluate_ledgers(policy, advice_events, actual_events)
            reconciliation = reconcile_ledgers(fixture["policy"], advice_events, actual_events)
            outputs[str(row["case_id"])] = (ledger_result, reconciliation)
            result_ok = (
                ledger_result.get("status") == expected.get("ledger_status")
                and reconciliation.get("status") == expected.get("reconciliation_status")
                and ledger_result.get("recommendation_generated") is False
                and ledger_result.get("order_submission_enabled") is False
                and ledger_result.get("external_network_used") is False
                and ledger_result.get("real_time_soak_waited") is False
                and reconciliation.get("external_network_used") is False
                and reconciliation.get("real_time_soak_waited") is False
            )
            if "ledger_reason_code" in expected:
                result_ok = result_ok and expected["ledger_reason_code"] in ledger_result.get("reason_codes", [])
            if "reconciliation_reason_code" in expected:
                result_ok = result_ok and expected["reconciliation_reason_code"] in reconciliation.get("reason_codes", [])
            for field in ("actual_funds_balance_cents", "actual_funds_unchanged_without_execution_evidence", "execution_evidence_count"):
                if field in expected:
                    result_ok = result_ok and ledger_result.get(field) == expected[field] and reconciliation.get(field) == expected[field]
            _add(
                checks,
                "S07P03-CASE-%s" % row["case_id"],
                result_ok,
                {"ledger": ledger_result, "reconciliation": reconciliation},
            )
        no_execution = outputs.get("NO_EXECUTION_EVIDENCE")
        verified = outputs.get("VERIFIED_FROZEN_EXECUTION_EVIDENCE")
        _add(
            checks,
            "S07P03-NO-EXECUTION-OUTPUT-HASH-PIN",
            no_execution is not None
            and no_execution[0].get("output_sha256") == fixture.get("expected_no_execution_output_sha256")
            and no_execution[0].get("actual_funds_unchanged_without_execution_evidence") is True
            and no_execution[0].get("actual_funds_balance_cents") == policy.opening_balance_cents,
            no_execution[0] if no_execution else "missing",
        )
        _add(
            checks,
            "S07P03-VERIFIED-FIXTURE-OUTPUT-HASH-PIN",
            verified is not None
            and verified[0].get("output_sha256") == fixture.get("expected_verified_execution_output_sha256")
            and verified[0].get("execution_evidence_count") == 1
            and verified[1].get("reconciliation_difference_cents") == 0,
            {"ledger": verified[0], "reconciliation": verified[1]} if verified else "missing",
        )
        return policy, fixture, outputs
    except Exception as exc:
        _add(checks, "S07P03-CORE-ARTIFACT-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))
        return None, fixture, {}


def _rehash(event: Mapping[str, Any]) -> Dict[str, Any]:
    body = {key: value for key, value in event.items() if key != "event_sha256"}
    return make_event(body)


def _check_boundaries_and_replay(
    policy: PreparedLedgerPolicy | None,
    fixture: Mapping[str, Any] | None,
    outputs: Mapping[str, Tuple[Dict[str, Any], Dict[str, Any]]],
    checks: List[Dict[str, Any]],
) -> None:
    if policy is None or not isinstance(fixture, Mapping) or not outputs:
        _add(checks, "S07P03-REPLAY-AVAILABLE", False, "core outputs unavailable")
        return
    try:
        no_execution, no_execution_reconciliation = outputs["NO_EXECUTION_EVIDENCE"]
        boundary, boundary_reconciliation = outputs["BOUNDARY_ADVERSE_EXACT_0001"]
        verified, verified_reconciliation = outputs["VERIFIED_FROZEN_EXECUTION_EVIDENCE"]
        _add(
            checks,
            "S07P03-NO-EXECUTION-REAL-FUNDS-UNCHANGED",
            no_execution.get("status") == LEDGER_VALID_NO_ADVICE
            and no_execution.get("actual_funds_unchanged_without_execution_evidence") is True
            and no_execution.get("actual_funds_balance_cents") == policy.opening_balance_cents
            and no_execution_reconciliation.get("actual_funds_unchanged_without_execution_evidence") is True
            and no_execution_reconciliation.get("reconciliation_difference_cents") == 0,
            {"ledger": no_execution, "reconciliation": no_execution_reconciliation},
        )
        _add(
            checks,
            "S07P03-BOUNDARY-PLUS-MINUS-0001-FAIL-CLOSED",
            boundary.get("status") == LEDGER_VALID_NO_ADVICE
            and boundary_reconciliation.get("status") == "RECONCILED"
            and verified.get("execution_evidence_count") == 1
            and verified_reconciliation.get("reconciliation_difference_cents") == 0,
            {"boundary": boundary, "verified": verified},
        )
        base = _case(fixture, "NO_EXECUTION_EVIDENCE")
        base_advice = base["advice_events"]
        expected_hash = deterministic_ledger_hash(policy, base_advice, [])
        replay_hashes = {
            deterministic_ledger_hash(
                policy,
                [{key: event[key] for key in reversed(list(event))} for event in base_advice],
                [],
            )
            for _ in range(int(fixture["replay_count"]))
        }
        reconciliation_hashes = {
            deterministic_reconciliation_hash(
                fixture["policy"],
                [{key: event[key] for key in reversed(list(event))} for event in base_advice],
                [],
            )
            for _ in range(int(fixture["replay_count"]))
        }
        _add(
            checks,
            "S07P03-100-REPLAY-DETERMINISTIC-NO-WAIT",
            replay_hashes == {expected_hash} == {fixture.get("expected_no_execution_output_sha256")}
            and len(reconciliation_hashes) == 1,
            {"count": fixture["replay_count"], "ledger_hash": expected_hash, "reconciliation_hash": next(iter(reconciliation_hashes))},
        )
        verified_case = _case(fixture, "VERIFIED_FROZEN_EXECUTION_EVIDENCE")
        advice = deepcopy(verified_case["advice_events"])
        actual = deepcopy(verified_case["actual_funds_events"])
        failures: List[int] = []
        for index in range(int(fixture["adverse_replay_count"])):
            candidate_advice = deepcopy(advice)
            candidate_actual = deepcopy(actual)
            mode = index % 5
            if mode == 0:
                candidate_advice[0]["payload"]["adverse_probability_delta"] = "-0.0001"
                candidate_advice[0] = _rehash(candidate_advice[0])
            elif mode == 1:
                candidate_advice[0]["payload"]["adverse_odds_tick"] = "0.0002"
                candidate_advice[0] = _rehash(candidate_advice[0])
            elif mode == 2:
                candidate_actual[0]["payload"]["execution_evidence_verified"] = False
                candidate_actual[0] = _rehash(candidate_actual[0])
            elif mode == 3:
                candidate_actual[0]["payload"]["advice_event_sha256"] = "f" * 64
                candidate_actual[0] = _rehash(candidate_actual[0])
            else:
                candidate_actual[0]["previous_event_sha256"] = "f" * 64
                candidate_actual[0] = _rehash(candidate_actual[0])
            ledger_result = evaluate_ledgers(policy, candidate_advice, candidate_actual)
            reconciliation = reconcile_ledgers(fixture["policy"], candidate_advice, candidate_actual)
            if (
                ledger_result.get("status") != NO_ADVICE
                or ledger_result.get("actual_funds_changed") is not False
                or ledger_result.get("recommendation_generated") is not False
                or ledger_result.get("order_submission_enabled") is not False
                or reconciliation.get("status") != "RECONCILIATION_REJECTED"
            ):
                failures.append(index)
                break
        _add(
            checks,
            "S07P03-ONE-IN-TEN-THOUSAND-ADVERSE-NO-FUNDS-MUTATION",
            not failures,
            {"count": fixture["adverse_replay_count"], "failures": failures},
        )
    except Exception as exc:
        _add(checks, "S07P03-BOUNDARY-AND-REPLAY-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    for path, name in ((LEDGER_PATH, "LEDGER"), (RECONCILIATION_ORACLE_PATH, "RECONCILIATION")):
        try:
            source = (root / path).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path.as_posix())
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
                "S07P03-%s-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY" % name,
                not denied and not forbidden_tokens,
                {"imports": sorted(imports), "denied": denied, "tokens": forbidden_tokens},
            )
        except Exception as exc:
            _add(checks, "S07P03-%s-NO-NETWORK-PROCESS-OR-SLEEP-CAPABILITY" % name, False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S07P03-REPORTS-DEFERRED-FOR-CANDIDATE", True, "candidate mode does not require generated reports")
        return
    target_minimum = int(fixture.get("target_test_minimum", 0)) if isinstance(fixture, Mapping) else 0
    for relative, minimum, check_id in (
        (JUNIT_PATH, target_minimum, "S07P03-TARGETED-PYTEST-REPORT"),
        (FULL_JUNIT_PATH, FULL_REGRESSION_TEST_MINIMUM, "S07P03-FULL-PYTEST-REPORT"),
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
    report = _safe_load(root / PACK_REPORT_PATH, checks, "S07P03-PACK-REPORT-STRICT-JSON")
    if isinstance(report, Mapping):
        summary = report.get("summary")
        _add(
            checks,
            "S07P03-TASKPACK-PASS",
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
            "S07P03-PAID-DEPENDENCY-SCAN-PASS",
            actual == expected and "STATUS: PASS" in actual,
            {"exact_match": actual == expected, "path": SCAN_REPORT_PATH.as_posix()},
        )
    except Exception as exc:
        _add(checks, "S07P03-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


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
    schema = _safe_load(root / SCHEMA_PATH, checks, "S07P03-SCHEMA-STRICT-JSON", ledger=True)
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S07P03-FIXTURE-STRICT-JSON", ledger=True)
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
        "phase_status": "S07_P03_PASS" if status == "PASS" else "S07_P03_FAIL",
        "decision": "IMMUTABLE_ADVICE_AND_DUAL_LEDGER_GATE_PASSED_NO_ADVICE" if status == "PASS" else "NO_ADVICE_AND_REMEDIATION_REQUIRED",
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
        "next": "S07/P04_READY_NOT_STARTED" if status == "PASS" else "S07/P03_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_test_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S07_P03_CANDIDATE_VALID" if result["status"] == "PASS" else "S07_P03_CANDIDATE_INVALID",
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
        "evidence_id": "EVD-S07-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_LEDGER_GATE_RESTORE_PRIOR_SIGNED_ARTIFACTS_REPLAY_DERIVED_STATE",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        SCHEMA_PATH,
        LEDGER_PATH,
        RECONCILIATION_ORACLE_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        P02_EVIDENCE_PATH,
        P02_ROLLBACK_PATH,
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
    schema = strict_ledger_json_load(root / SCHEMA_PATH)
    fixture = strict_ledger_json_load(root / FIXTURE_PATH)
    policy = prepare_policy(schema, fixture["policy"])
    no_execution_case = _case(fixture, "NO_EXECUTION_EVIDENCE")
    verified_case = _case(fixture, "VERIFIED_FROZEN_EXECUTION_EVIDENCE")
    no_execution = evaluate_ledgers(policy, no_execution_case["advice_events"], no_execution_case["actual_funds_events"])
    verified = evaluate_ledgers(policy, verified_case["advice_events"], verified_case["actual_funds_events"])
    reconciliation = reconcile_ledgers(fixture["policy"], no_execution_case["advice_events"], no_execution_case["actual_funds_events"])
    failures = {
        str(case["case_id"]): {
            "ledger_reason_codes": evaluate_ledgers(policy, case["advice_events"], case["actual_funds_events"])["reason_codes"],
            "reconciliation_reason_codes": reconcile_ledgers(fixture["policy"], case["advice_events"], case["actual_funds_events"])["reason_codes"],
        }
        for case in fixture["cases"]
        if str(case["case_id"]).startswith("NEGATIVE_")
    }
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-P03",
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
            "model_versions": {},
            "no_execution_output": no_execution["output_sha256"],
            "verified_fixture_output": verified["output_sha256"],
            "reconciliation_output": reconciliation["output_sha256"],
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "ledger_summary": {
            "currency": policy.currency,
            "opening_balance_cents": policy.opening_balance_cents,
            "no_execution_balance_cents": no_execution["actual_funds_balance_cents"],
            "no_execution_unchanged": no_execution["actual_funds_unchanged_without_execution_evidence"],
            "verified_fixture_balance_cents": verified["actual_funds_balance_cents"],
            "verified_fixture_only": True,
            "recommendation_generated": False,
            "order_submission_enabled": False,
        },
        "reconciliation_summary": {
            "no_execution_status": reconciliation["status"],
            "no_execution_difference_cents": reconciliation["reconciliation_difference_cents"],
            "no_execution_unchanged": reconciliation["actual_funds_unchanged_without_execution_evidence"],
        },
        "structured_failure_log": {
            "path": FIXTURE_PATH.as_posix(),
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
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S07-P03"]
    rows.append(
        {
            "id": "INDEX-AC-S07-P03",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S07/P04_READY_NOT_STARTED" if status == "PASS" else "S07/P03_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise ValueError("S07/P03 evidence must be written to machine/evidence")
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
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S07P03-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S07P03-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        integrity = (
            evidence.get("evidence_id") == "EVD-S07-P03"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S07/P04_READY_NOT_STARTED"
            and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
            and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S07P03-EXISTING-EVIDENCE-INTEGRITY", integrity, evidence.get("status"))
        hash_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                hash_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                hash_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S07P03-EXISTING-INPUT-HASHES", not hash_errors, hash_errors or "all inputs match")
        _add(checks, "S07P03-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S07P03-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S07-P03-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_account_balance_read_or_written") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S07P03-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S07P03-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_test_reports=True, _verify_git_history=verify_git_history)
    _add(checks, "S07P03-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S07/P04_READY_NOT_STARTED" if not failed else "S07/P03_REMEDIATION_REQUIRED",
    }
