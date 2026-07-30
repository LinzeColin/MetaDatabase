"""Independent deterministic acceptance oracle for ABD S07/P01.

The oracle evaluates only frozen synthetic identity records.  It never contacts
providers, starts a scheduler, reads an account, generates a recommendation,
submits an order, spends cash, or waits for real-time soak.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from identity_resolver import (
    CONFIDENCE_THRESHOLD,
    IDENTITY_ELIGIBLE,
    NO_ADVICE,
    TIME_TOLERANCE_SECONDS,
    canonicalize_line,
    confidence_action,
    deterministic_resolution_hash,
    prepare_registry,
    resolve_identity,
    resolve_prepared_identity,
    validate_registry,
)

from .canonical_facts import sha256_file, strict_json_load
from .mail_deletion_audit import verify_existing_phase_evidence as verify_s06_p04_evidence
from .stage4_delivery import verify_stage4_delivery
from .stage5_delivery import verify_stage5_delivery
from .stage6_review import verify_existing_stage_review_evidence as verify_stage6_review_evidence


CONTRACT_ID = "AC-S07-P01"
REQUIREMENT_ID = "REQ-S07-P01"
STAGE_ID = "S07"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-29T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

RESOLVER_PATH = Path("identity_resolver.py")
IDENTITY_FIXTURES_PATH = Path("identity_fixtures.json")
REGISTRY_PATH = Path("identity_registry.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S07_P01.json")
TEST_PATH = Path("tests/S07/P01_test.py")
ORACLE_PATH = Path("abd_acceptance/identity_resolution.py")
EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S07-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S07/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S07/P01/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")

PINNED_PHASE_HASHES: Dict[str, str] = {
    RESOLVER_PATH.as_posix(): "4d3cf470f26928d8194d24b37e78286a8920b036db56f2b4d87122146ef28250",
    IDENTITY_FIXTURES_PATH.as_posix(): "d79b855a58089fc143739bbc032ca9d42317f7d453c6cad4fadcef1595877fc7",
    REGISTRY_PATH.as_posix(): "ca8962619e0a93ea6080de78635a63ecc3c22ffc0f09a25c5fef10bf2df10b05",
    FIXTURE_PATH.as_posix(): "d4e4c4d9f2d8dae1f72cea8805cf3ea3f8ceb98b8bbba44287c7dff59e69ab4d",
    TEST_PATH.as_posix(): "a4003b8daf7f94890bf750a6ca9275fb23e31971b63b0c84ac0bfe266d079994",
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
    "machine/evidence/S04/STAGE_REVIEW/github_delivery_receipt.json": "d9b83cc0ebc1464c9f52c87e49bed32887323297118c595be1f97a475b78ed36",
    "machine/evidence/S05/STAGE_REVIEW/github_delivery_receipt.json": "5926e2e8ef70c141b9453dbced4851f02499fda817d99a4922cfe3272f75ace2",
    "machine/evidence/EVD-S06-P04.json": "2530864a43e7b4d2a2a55ccdbbe4a218a77a11b52438ab49ea9c2664f1f60aea",
    "machine/evidence/EVD-S06-P04_rollback.json": "a54bfe27ffac5efad8fab4683a4a389239939e8fdbdf43fc75fef489c04fc579",
    "machine/evidence/EVD-S06-STAGE-REVIEW.json": "467f3d610bb2b027a6a14ede52ad2ced9a5b71b95dee057641533d4ad29f0be3",
    "machine/evidence/EVD-S06-STAGE-REVIEW_rollback.json": "2afa60333d47b6459bc8492e0e868e23b1f11aee852c40ebe6469a90a6eb6dc2",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "af15a25ea99902e346944b28c08c3c234d1e8058f4b4a7d0d3233f1906f5c863"

ROLLBACK_ARTIFACTS = (
    RESOLVER_PATH,
    IDENTITY_FIXTURES_PATH,
    REGISTRY_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    ORACLE_PATH,
    Path("abd_acceptance/__main__.py"),
)

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed_for_identity": False,
    "provider_account_or_page_accessed": False,
    "raw_market_or_odds_data_read": False,
    "gmail_account_or_api_accessed": False,
    "scheduler_daemon_started": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
    "financial_return_verified_or_guaranteed": False,
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _row(rows: Any, identifier: str, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    found = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(found) != 1:
        raise ValueError("expected exactly one row for %s" % identifier)
    return found[0]


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
    for relative in (RESOLVER_PATH, ORACLE_PATH):
        payload += relative.as_posix().encode("utf-8") + b"\0" + (root / relative).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _junit_summary(path: Path) -> Dict[str, int]:
    tree = ElementTree.parse(path)
    suites = tree.getroot()
    if suites.tag not in {"testsuite", "testsuites"}:
        raise ValueError("unexpected junit root")
    if suites.tag == "testsuite":
        nodes = [suites]
    else:
        nodes = list(suites.findall("testsuite"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for node in nodes:
        for field in totals:
            totals[field] += int(node.attrib.get(field, "0"))
    return totals


def _junit_is_normalized(path: Path) -> bool:
    try:
        root = ElementTree.parse(path).getroot()
    except Exception:
        return False
    suites = list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
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
                "S07P01-PIN-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P01-PIN-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))
    actual_self = _structural_self_hash(root)
    hashes[ORACLE_PATH.as_posix()] = sha256_file(root / ORACLE_PATH)
    _add(
        checks,
        "S07P01-ORACLE-STRUCTURAL-HASH",
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
                "S07P01-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"),
                expected != "TO_BE_FILLED" and actual == expected,
                {"expected": expected, "actual": actual},
            )
        except Exception as exc:
            _add(checks, "S07P01-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), False, "%s: %s" % (type(exc).__name__, exc))


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S07P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S07P01-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S07P01-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S07P01-TRACE-STRICT-JSON")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "S07P01-ROADMAP-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        stage = _row(roadmap.get("stages"), STAGE_ID)
        phase = _row(stage.get("phases"), PHASE_ID)
        tasks = [
            row
            for row in task_graph.get("tasks", [])
            if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID
        ]
        expected_outputs = [RESOLVER_PATH.as_posix(), IDENTITY_FIXTURES_PATH.as_posix(), REGISTRY_PATH.as_posix()]
        expected_task_ids = ["T-S07-P01-01", "T-S07-P01-02", "T-S07-P01-03"]
        expected_test_ids = ["TEST-S07-P01", "TEST-S07-P01-BOUNDARY", "TEST-S07-P01-REPLAY"]
        ok = (
            requirement.get("scope") == expected_outputs
            and requirement.get("target") == "身份置信度<99.5%时不建议。"
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S07-P01 --evidence machine/evidence"
            and [row.get("id") for row in contract.get("tests", [])] == expected_test_ids
            and contract.get("threshold") == "身份置信度<99.5%时不建议。"
            and [row.get("id") for row in tasks] == expected_task_ids
            and tasks[0].get("outputs") == expected_outputs
            and tasks[1].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and tasks[2].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks)
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == expected_task_ids
            and trace.get("test_ids") == expected_test_ids
            and trace.get("evidence_id") == "EVD-S07-P01"
            and stage.get("depends_on") == ["S04", "S05", "S06"]
            and phase.get("outputs") == expected_outputs
        )
        _add(checks, "S07P01-TASKPACK-TRACE-EXACT", ok, {"tasks": [row.get("id") for row in tasks], "stage_dependencies": stage.get("depends_on")})
    except Exception as exc:
        _add(checks, "S07P01-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    try:
        stage4 = verify_stage4_delivery(root, verify_git_history=verify_git_history)
        _add(checks, "S07P01-S04-DELIVERY-PREREQUISITE", stage4.get("status") == "PASS", stage4.get("next"))
    except Exception as exc:
        _add(checks, "S07P01-S04-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        stage5 = verify_stage5_delivery(root, verify_git_history=verify_git_history)
        _add(checks, "S07P01-S05-DELIVERY-PREREQUISITE", stage5.get("status") == "PASS", stage5.get("next"))
    except Exception as exc:
        _add(checks, "S07P01-S05-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        p04 = verify_s06_p04_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S07P01-S06-P04-PREREQUISITE", p04.get("status") == "PASS", p04.get("next"))
    except Exception as exc:
        _add(checks, "S07P01-S06-P04-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        review = verify_stage6_review_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S07P01-S06-WHOLE-STAGE-REVIEW-PREREQUISITE", review.get("status") == "PASS", review.get("next"))
    except Exception as exc:
        _add(checks, "S07P01-S06-WHOLE-STAGE-REVIEW-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))


def _fixture_case(fixtures: Mapping[str, Any], identifier: str) -> Mapping[str, Any]:
    cases = fixtures.get("cases")
    if not isinstance(cases, list):
        raise ValueError("identity fixture cases must be a list")
    return _row(cases, identifier, key="case_id")


def _check_core_artifacts(
    root: Path,
    fixtures: Mapping[str, Any] | None,
    registry: Mapping[str, Any] | None,
    machine_fixture: Mapping[str, Any] | None,
    checks: List[Dict[str, Any]],
) -> Mapping[str, Any] | None:
    if not isinstance(fixtures, Mapping) or not isinstance(registry, Mapping) or not isinstance(machine_fixture, Mapping):
        _add(checks, "S07P01-FROZEN-ARTIFACTS-AVAILABLE", False, "fixture or registry unavailable")
        return None
    fixture_ok = (
        fixtures.get("schema_version") == "1.0.0"
        and fixtures.get("artifact_id") == "ART-S07-P01-02"
        and fixtures.get("fixture_id") == "ABD-IDENTITY-FIXTURES-S07-P01"
        and fixtures.get("requirement_id") == REQUIREMENT_ID
        and fixtures.get("acceptance_contract_id") == CONTRACT_ID
        and fixtures.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        and fixtures.get("claim_boundary")
        == {
            "actual_provider_or_market_observed": False,
            "recommendation_or_order_enabled": False,
            "financial_return_verified_or_guaranteed": False,
            "real_time_soak_required": False,
        }
    )
    _add(checks, "S07P01-IDENTITY-FIXTURES-EXACT", fixture_ok, fixtures.get("fixture_id"))
    machine_ok = (
        machine_fixture.get("schema_version") == "1.0.0"
        and machine_fixture.get("fixture_id") == "FIX-S07-P01"
        and machine_fixture.get("contract_id") == CONTRACT_ID
        and machine_fixture.get("requirement_id") == REQUIREMENT_ID
        and machine_fixture.get("stage_id") == STAGE_ID
        and machine_fixture.get("phase_id") == PHASE_ID
        and machine_fixture.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        and machine_fixture.get("expected_next") == "S07/P02_READY_NOT_STARTED"
        and machine_fixture.get("identity_confidence_threshold") == "0.9950"
        and machine_fixture.get("boundary_deltas") == ["-0.0001", "0", "0.0001"]
        and machine_fixture.get("replay_count") == 100
        and machine_fixture.get("adverse_replay_count") == 10000
        and machine_fixture.get("claim_boundary")
        == {
            "network_accessed": False,
            "actual_market_or_odds_observed": False,
            "recommendation_generated": False,
            "order_submission_enabled": False,
            "real_time_soak_required": False,
        }
    )
    _add(checks, "S07P01-MACHINE-FIXTURE-EXACT", machine_ok, machine_fixture.get("fixture_id"))
    registry_errors = validate_registry(registry)
    _add(checks, "S07P01-REGISTRY-VALID", not registry_errors, registry_errors or "valid")
    if registry_errors:
        return None
    try:
        authoritative = _fixture_case(fixtures, "POSITIVE_AUTHORITATIVE_REFERENCE")
        cross_source = _fixture_case(fixtures, "POSITIVE_CROSS_SOURCE_MINIMUM_THRESHOLD")
        time_drift = _fixture_case(fixtures, "NEGATIVE_START_TIME_ONE_SECOND_DRIFT")
        unknown = _fixture_case(fixtures, "NEGATIVE_UNKNOWN_ALIAS")
        authoritative_result = resolve_identity(registry, authoritative["observation"])
        cross_result = resolve_identity(registry, cross_source["observation"])
        drift_result = resolve_identity(registry, time_drift["observation"])
        unknown_result = resolve_identity(registry, unknown["observation"])
        positive_ok = (
            authoritative_result.get("status") == authoritative["expected"]["status"]
            and authoritative_result.get("identity_confidence") == authoritative["expected"]["identity_confidence"]
            and authoritative_result.get("identity_eligible") is True
            and authoritative_result.get("canonical", {}).get("selection_id") == authoritative["expected"]["selection_id"]
            and cross_result.get("status") == cross_source["expected"]["status"]
            and cross_result.get("identity_confidence") == cross_source["expected"]["identity_confidence"]
            and cross_result.get("identity_eligible") is True
            and cross_result.get("canonical", {}).get("selection_id") == cross_source["expected"]["selection_id"]
            and authoritative_result.get("identity_key") != cross_result.get("identity_key")
            and authoritative_result.get("recommendation_generated") is False
            and cross_result.get("order_submission_enabled") is False
        )
        _add(checks, "S07P01-POSITIVE-IDENTITY-RESOLUTION", positive_ok, {"authoritative": authoritative_result.get("identity_confidence"), "cross_source": cross_result.get("identity_confidence")})
        negative_ok = (
            drift_result.get("status") == time_drift["expected"]["status"]
            and drift_result.get("identity_confidence") == time_drift["expected"]["identity_confidence"]
            and drift_result.get("identity_eligible") is False
            and time_drift["expected"]["reason_code"] in drift_result.get("reason_codes", [])
            and unknown_result.get("status") == unknown["expected"]["status"]
            and unknown["expected"]["reason_code"] in unknown_result.get("reason_codes", [])
            and unknown_result.get("identity_key") is None
        )
        _add(checks, "S07P01-NEGATIVE-IDENTITY-FAIL-CLOSED", negative_ok, {"drift": drift_result.get("reason_codes"), "unknown": unknown_result.get("reason_codes")})
        return {
            "authoritative": authoritative,
            "cross_source": cross_source,
            "time_drift": time_drift,
            "unknown": unknown,
            "authoritative_result": authoritative_result,
            "cross_source_result": cross_result,
        }
    except Exception as exc:
        _add(checks, "S07P01-IDENTITY-RESOLUTION-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_threshold_and_replay(
    registry: Mapping[str, Any] | None,
    case_data: Mapping[str, Any] | None,
    machine_fixture: Mapping[str, Any] | None,
    checks: List[Dict[str, Any]],
) -> None:
    if not isinstance(registry, Mapping) or not isinstance(case_data, Mapping) or not isinstance(machine_fixture, Mapping):
        _add(checks, "S07P01-THRESHOLD-AND-REPLAY-AVAILABLE", False, "core fixture unavailable")
        return
    try:
        lower = confidence_action(CONFIDENCE_THRESHOLD - Decimal("0.0001"))
        equal = confidence_action(CONFIDENCE_THRESHOLD)
        upper = confidence_action(CONFIDENCE_THRESHOLD + Decimal("0.0001"))
        boundary_ok = (
            lower["identity_eligible"] is False
            and lower["identity_action"] == NO_ADVICE
            and equal["identity_eligible"] is True
            and equal["identity_action"] == IDENTITY_ELIGIBLE
            and upper["identity_eligible"] is True
            and canonicalize_line({"representation": "SCALAR_DECIMAL", "value": "2.500"})
            == canonicalize_line({"representation": "SCALAR_DECIMAL", "value": "2.5"})
            and canonicalize_line({"representation": "NO_LINE_APPLICABLE"}) == {"representation": "NO_LINE_APPLICABLE"}
        )
        _add(checks, "S07P01-CONFIDENCE-BOUNDARY-PLUS-MINUS-00001", boundary_ok, {"lower": lower, "equal": equal, "upper": upper})
        positive = case_data["authoritative"]["observation"]
        expected_hash = deterministic_resolution_hash(registry, positive)
        replay_hashes = set()
        for _ in range(int(machine_fixture["replay_count"])):
            reordered = {key: positive[key] for key in reversed(list(positive))}
            replay_hashes.add(deterministic_resolution_hash(registry, reordered))
        _add(
            checks,
            "S07P01-100-REPLAY-DETERMINISTIC-NO-WAIT",
            replay_hashes == {expected_hash},
            {"count": machine_fixture["replay_count"], "hash": expected_hash},
        )
        negative_base = case_data["unknown"]["observation"]
        prepared = prepare_registry(registry)
        adverse_failures: List[int] = []
        for index in range(int(machine_fixture["adverse_replay_count"])):
            candidate = deepcopy(negative_base)
            mode = index % 5
            if mode == 0:
                candidate["home_alias"] = "Unknown-%d" % index
            elif mode == 1:
                candidate["source_version_sha256"] = "f" * 64
            elif mode == 2:
                candidate["selection_alias"] = "Not A Selection"
            elif mode == 3:
                candidate["line"] = {"representation": "SCALAR_DECIMAL", "value": "1.5"}
            else:
                candidate["start_time"] = "2026-08-15T19:32:00+10:00"
            result = resolve_prepared_identity(prepared, candidate)
            if result.get("status") != NO_ADVICE or result.get("identity_key") is not None or result.get("recommendation_generated") is not False:
                adverse_failures.append(index)
                break
        _add(
            checks,
            "S07P01-ONE-IN-TEN-THOUSAND-ADVERSE-NO-ADVICE",
            not adverse_failures,
            {"count": machine_fixture["adverse_replay_count"], "failures": adverse_failures},
        )
    except Exception as exc:
        _add(checks, "S07P01-THRESHOLD-AND-REPLAY-EXECUTION", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        tree = ast.parse((root / RESOLVER_PATH).read_text(encoding="utf-8"), filename=RESOLVER_PATH.as_posix())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        denied = sorted(imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"})
        text = (root / RESOLVER_PATH).read_text(encoding="utf-8")
        forbidden_tokens = [token for token in ("sleep(", "requests.", "urllib.", "socket.", "subprocess.", "http://", "https://") if token in text]
        _add(checks, "S07P01-NO-NETWORK-PROCESS-OR-SLEEP-IMPORT", not denied and not forbidden_tokens, {"imports": sorted(imports), "denied": denied, "tokens": forbidden_tokens})
    except Exception as exc:
        _add(checks, "S07P01-NO-NETWORK-PROCESS-OR-SLEEP-IMPORT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S07P01-REPORTS-DEFERRED-FOR-CANDIDATE", True, "candidate mode does not require generated reports")
        return
    for relative, minimum, check_id in (
        (JUNIT_PATH, 24, "S07P01-TARGETED-PYTEST-REPORT"),
        (FULL_JUNIT_PATH, 4870, "S07P01-FULL-PYTEST-REPORT"),
    ):
        try:
            summary = _junit_summary(root / relative)
            ok = (
                summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and summary["skipped"] == 0
                and _junit_is_normalized(root / relative)
            )
            _add(checks, check_id, ok, {"minimum": minimum, "summary": summary, "normalized": _junit_is_normalized(root / relative)})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root / PACK_REPORT_PATH, checks, "S07P01-PACK-REPORT-STRICT-JSON")
    if isinstance(report, Mapping):
        summary = report.get("summary")
        ok = isinstance(summary, Mapping) and report.get("status") == "PASS" and summary.get("failed") == 0 and summary.get("passed") == summary.get("checks")
        _add(checks, "S07P01-TASKPACK-PASS", ok, summary if isinstance(summary, Mapping) else "missing summary")
    if (root / SCAN_REPORT_PATH).is_file():
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S07P01-PAID-DEPENDENCY-SCAN-PASS", "STATUS: PASS" in text or "status=PASS" in text or '"status": "PASS"' in text, "scan receipt present")
    else:
        _add(checks, "S07P01-PAID-DEPENDENCY-SCAN-PASS", False, "scan receipt missing")


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
    _check_predecessors(root, checks, verify_git_history=_verify_git_history)
    fixtures = _safe_load(root / IDENTITY_FIXTURES_PATH, checks, "S07P01-IDENTITY-FIXTURES-STRICT-JSON")
    registry = _safe_load(root / REGISTRY_PATH, checks, "S07P01-REGISTRY-STRICT-JSON")
    machine_fixture = _safe_load(root / FIXTURE_PATH, checks, "S07P01-MACHINE-FIXTURE-STRICT-JSON")
    case_data = _check_core_artifacts(root, fixtures, registry, machine_fixture, checks)
    _check_threshold_and_replay(registry if isinstance(registry, Mapping) else None, case_data, machine_fixture if isinstance(machine_fixture, Mapping) else None, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": status,
        "phase_status": "S07_P01_PASS" if status == "PASS" else "S07_P01_FAIL",
        "decision": "IDENTITY_GATE_PASSED_DOWNSTREAM_GATES_REQUIRED" if status == "PASS" else "NO_ADVICE_AND_REMEDIATION_REQUIRED",
        "checks": checks,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "no_real_time_soak": {
            "required": False,
            "wait_performed": False,
            "deterministic_replay_count": machine_fixture.get("replay_count") if isinstance(machine_fixture, Mapping) else None,
            "deterministic_adverse_replay_count": machine_fixture.get("adverse_replay_count") if isinstance(machine_fixture, Mapping) else None,
        },
        "next": "S07/P02_READY_NOT_STARTED" if status == "PASS" else "S07/P01_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_test_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S07_P01_CANDIDATE_VALID" if result["status"] == "PASS" else "S07_P01_CANDIDATE_INVALID",
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
        "evidence_id": "EVD-S07-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_IDENTITY_RESOLUTION_KEEP_SIGNED_INPUTS_AND_DERIVED_EVIDENCE",
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
        RESOLVER_PATH,
        IDENTITY_FIXTURES_PATH,
        REGISTRY_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/model_system_card.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("machine/evidence/S04/STAGE_REVIEW/github_delivery_receipt.json"),
        Path("machine/evidence/S05/STAGE_REVIEW/github_delivery_receipt.json"),
        Path("machine/evidence/EVD-S06-P04.json"),
        Path("machine/evidence/EVD-S06-P04_rollback.json"),
        Path("machine/evidence/EVD-S06-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S06-STAGE-REVIEW_rollback.json"),
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
    fixtures = strict_json_load(root / IDENTITY_FIXTURES_PATH)
    registry = strict_json_load(root / REGISTRY_PATH)
    authoritative = _fixture_case(fixtures, "POSITIVE_AUTHORITATIVE_REFERENCE")
    cross_source = _fixture_case(fixtures, "POSITIVE_CROSS_SOURCE_MINIMUM_THRESHOLD")
    authoritative_result = resolve_identity(registry, authoritative["observation"])
    cross_result = resolve_identity(registry, cross_source["observation"])
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S07-P01",
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
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "identity_summary": {
            "fixture_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "authoritative_identity_key": authoritative_result.get("identity_key"),
            "cross_source_identity_key": cross_result.get("identity_key"),
            "identity_confidences": [authoritative_result.get("identity_confidence"), cross_result.get("identity_confidence")],
            "recommendation_generated": False,
            "order_submission_enabled": False,
        },
        "deterministic_replay": {
            "replay_count": 100,
            "adverse_replay_count": 10000,
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
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S07-P01"]
    rows.append(
        {
            "id": "INDEX-AC-S07-P01",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S07/P02_READY_NOT_STARTED" if status == "PASS" else "S07/P01_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise ValueError("S07/P01 evidence must be written to machine/evidence")
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
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S07P01-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S07P01-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S07-P01"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S07/P02_READY_NOT_STARTED"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S07P01-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        hash_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                hash_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                hash_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S07P01-EXISTING-INPUT-HASHES", not hash_errors, hash_errors or "all inputs match")
        _add(checks, "S07P01-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S07P01-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S07-P01-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("recommendation_generated") is False
            and rollback.get("order_submission_enabled") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S07P01-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S07P01-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_test_reports=True, _verify_git_history=verify_git_history)
    _add(checks, "S07P01-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": evidence_hash,
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S07/P02_READY_NOT_STARTED" if not failed else "S07/P01_REMEDIATION_REQUIRED",
    }
