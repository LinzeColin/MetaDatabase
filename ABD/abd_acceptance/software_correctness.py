"""Fail-closed, offline acceptance oracle for ABD S15/P01.

S15/P01 establishes a deliberately bounded correctness test surface for
money/threshold arithmetic, local state transitions, and closed JSON
serialization.  The coverage number is limited to the declared frozen
decision-branch inventory below; it is not a repository-wide coverage,
production-runtime, market, account, or return claim.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from .artifact_provenance import verify_existing_phase_evidence as verify_s14_p04_evidence
from .canonical_facts import sha256_file, strict_json_load
from .coverage_observability import verify_existing_phase_evidence as verify_s05_p04_evidence
from .evidence_continuity import verify_existing_phase_evidence as verify_s07_p04_evidence
from .journey_paths import verify_existing_phase_evidence as verify_s13_p04_evidence


CONTRACT_ID = "AC-S15-P01"
REQUIREMENT_ID = "REQ-S15-P01"
STAGE_ID = "S15"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

UNIT_TESTS_PATH = Path("unit_tests.json")
PROPERTY_TESTS_PATH = Path("property_tests.json")
SCHEMA_TESTS_PATH = Path("schema_tests.json")
ORACLE_PATH = Path("abd_acceptance/software_correctness.py")
TEST_PATH = Path("tests/S15/P01_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S15_P01.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S15/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S15/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
ROADMAP_PATH = Path("machine/facts/roadmap.json")
CANONICAL_FACTS_PATH = Path("machine/facts/canonical_facts.json")

FEATURE_FLAG_ID = "quality:s15-p01-offline-correctness-contract"
EXPECTED_TASK_IDS = ("T-S15-P01-01", "T-S15-P01-02", "T-S15-P01-03")
EXPECTED_TEST_IDS = ("TEST-S15-P01", "TEST-S15-P01-BOUNDARY", "TEST-S15-P01-REPLAY")
EXPECTED_ARTIFACTS = {
    "ART-S15-P01-01": UNIT_TESTS_PATH,
    "ART-S15-P01-02": PROPERTY_TESTS_PATH,
    "ART-S15-P01-03": SCHEMA_TESTS_PATH,
}
EXPECTED_CASE_IDS = (
    "S15-P01-EXACT-THRESHOLD",
    "S15-P01-BELOW-THRESHOLD",
    "S15-P01-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
    "S15-P01-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
    "S15-P01-ZERO-FUNDS",
    "S15-P01-BLOCKED-STATE",
    "S15-P01-NEGATIVE-FUNDS-REJECTED",
)
REQUIRED_BRANCH_IDS = (
    "SCHEMA-CLOSED",
    "SERIALIZATION-CANONICAL",
    "FUNDS-POSITIVE",
    "FUNDS-ZERO",
    "FUNDS-NEGATIVE-REJECT",
    "ADVERSE-DELTA-NEUTRAL",
    "ADVERSE-DELTA-NEGATIVE-ONE-IN-TEN-THOUSAND",
    "ADVERSE-DELTA-POSITIVE-ONE-IN-TEN-THOUSAND",
    "THRESHOLD-BELOW",
    "THRESHOLD-EXACT",
    "THRESHOLD-ABOVE",
    "STATE-LOCAL-TEST-ONLY",
    "STATE-BLOCKED",
    "NO-ACTION-THRESHOLD",
    "NO-ACTION-ZERO-FUNDS",
    "NO-ACTION-STATE-BLOCKED",
    "LOCAL-TEST-PASS-NO-ACTION",
)
PROPERTY_SPECS = (
    {
        "id": "PROP-S15-P01-NO-INCREMENTAL-CASH",
        "case_ids": list(EXPECTED_CASE_IDS),
        "rule": "Every frozen case records A$0 incremental cash and no external action.",
    },
    {
        "id": "PROP-S15-P01-THRESHOLD-FAILS-CLOSED",
        "case_ids": [
            "S15-P01-BELOW-THRESHOLD",
            "S15-P01-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
        ],
        "rule": "A below-threshold result, including a -0.0001 adverse delta, cannot enable an action.",
    },
    {
        "id": "PROP-S15-P01-ZERO-AND-NEGATIVE-FUNDS-SAFE",
        "case_ids": ["S15-P01-ZERO-FUNDS", "S15-P01-NEGATIVE-FUNDS-REJECTED"],
        "rule": "Zero funds remains no-action and negative funds is rejected without an external effect.",
    },
    {
        "id": "PROP-S15-P01-LOCAL-STATE-NEVER-ORDERS",
        "case_ids": [
            "S15-P01-EXACT-THRESHOLD",
            "S15-P01-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
            "S15-P01-BLOCKED-STATE",
        ],
        "rule": "Even a local test pass remains evidence-only and never submits an order.",
    },
)
NEGATIVE_MUTATION_IDS = (
    "MUT-S15-P01-UNKNOWN-FIELD",
    "MUT-S15-P01-FLOAT-NUMERIC",
    "MUT-S15-P01-NONCANONICAL-DECIMAL",
    "MUT-S15-P01-NONSYNTHETIC-INPUT",
)
SNAPSHOT_FIELDS = (
    "case_id",
    "funds_aud",
    "incremental_cash_spent_aud",
    "score",
    "threshold",
    "adverse_delta",
    "state",
    "serialization",
    "synthetic_test_only",
)
RESULT_FIELDS = (
    "case_id",
    "status",
    "effective_score",
    "threshold_pass",
    "branch_ids",
    "recommendation_generated",
    "order_submission_enabled",
    "external_state_changed",
    "real_time_soak_waited",
    "incremental_cash_spent_aud",
)
COVERAGE_SCOPE = {
    "declared_critical_modules": [
        "money_threshold_gate",
        "local_test_state_gate",
        "closed_schema_validator",
    ],
    "method": "FROZEN_DECISION_BRANCH_INVENTORY",
    "repository_wide_coverage_claimed": False,
    "production_runtime_coverage_claimed": False,
    "full_regression_or_real_time_soak_performed": False,
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
    "incremental_cash_spent_aud": "0.00",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    CANONICAL_FACTS_PATH.as_posix(): "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    PARAMETERS_PATH.as_posix(): "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    ROADMAP_PATH.as_posix(): "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    REQUIREMENTS_PATH.as_posix(): "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    CONTRACTS_PATH.as_posix(): "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    TASK_GRAPH_PATH.as_posix(): "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    TRACEABILITY_PATH.as_posix(): "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
PREDECESSORS: Dict[str, Dict[str, Any]] = {
    "AC-S05-P04": {
        "evidence_path": Path("machine/evidence/EVD-S05-P04.json"),
        "evidence_sha256": "986d52d8ca695b99f5dbbbea7e273cc5dafdfc7e81892ebd0b272be848ea9249",
        "rollback_path": Path("machine/evidence/EVD-S05-P04_rollback.json"),
        "rollback_sha256": "3a8825f0c7b8b9daf2c7d95646db79ad5e224c637eed31f5736e683a67a41c28",
        "next": "S05/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_s05_p04_evidence,
    },
    "AC-S07-P04": {
        "evidence_path": Path("machine/evidence/EVD-S07-P04.json"),
        "evidence_sha256": "a2fa2f72c069050ed7045f7e7c3cbe5928664bee4e91d1307169b19d466a6fa6",
        "rollback_path": Path("machine/evidence/EVD-S07-P04_rollback.json"),
        "rollback_sha256": "ad483c1e873985c14e5c70d67fb18c2801d9033bf8ed435ca9b149e8bb82054a",
        "next": "S07/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_s07_p04_evidence,
    },
    "AC-S13-P04": {
        "evidence_path": Path("machine/evidence/EVD-S13-P04.json"),
        "evidence_sha256": "1c4d9febd44b30dddfa780daa0aad56a70ab8d477ab9cdafc905107760d7c81e",
        "rollback_path": Path("machine/evidence/EVD-S13-P04_rollback.json"),
        "rollback_sha256": "8cea40846c7d60b5ee8adaecee741e97be17a46e6045728e71cfb08131dc0856",
        "next": "S13/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_s13_p04_evidence,
    },
    "AC-S14-P04": {
        "evidence_path": Path("machine/evidence/EVD-S14-P04.json"),
        "evidence_sha256": "820f5a1c13f788386c54af8d18551bd6bd40d7816d659c6ffd43a657c25ddf4b",
        "rollback_path": Path("machine/evidence/EVD-S14-P04_rollback.json"),
        "rollback_sha256": "0b3bfaa1bccf0dccb77afea4f6c44b3eab670d5e0af5d07bc5a1ff73aaef68b5",
        "next": "S14/STAGE_REVIEW_READY_NOT_STARTED",
        "verifier": verify_s14_p04_evidence,
    },
}


class SoftwareCorrectnessAcceptanceError(ValueError):
    """Raised when the S15/P01 local correctness contract is not satisfied."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise SoftwareCorrectnessAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SoftwareCorrectnessAcceptanceError("JSONL row %d is not an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise SoftwareCorrectnessAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise SoftwareCorrectnessAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"-?\d+\.\d{4}", value) is None:
        raise SoftwareCorrectnessAcceptanceError("%s must be four-place decimal text" % field)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise SoftwareCorrectnessAcceptanceError("%s is not decimal" % field) from exc


def _closed_mapping(value: Any, fields: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields) or _contains_float(value):
        raise SoftwareCorrectnessAcceptanceError("%s fields are not closed" % label)
    return value


def evaluate_quality_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay one frozen correctness vector without enabling a real action."""

    snapshot = _closed_mapping(snapshot, SNAPSHOT_FIELDS, "snapshot")
    case_id = snapshot.get("case_id")
    if not isinstance(case_id, str) or case_id not in EXPECTED_CASE_IDS:
        raise SoftwareCorrectnessAcceptanceError("snapshot case_id is not declared")
    if snapshot.get("incremental_cash_spent_aud") != "0.00":
        raise SoftwareCorrectnessAcceptanceError("incremental cash must remain A$0")
    if snapshot.get("serialization") != "CANONICAL_JSON_V1":
        raise SoftwareCorrectnessAcceptanceError("serialization must be canonical JSON v1")
    if snapshot.get("synthetic_test_only") is not True:
        raise SoftwareCorrectnessAcceptanceError("snapshot must be frozen synthetic input")
    if snapshot.get("state") not in {"LOCAL_TEST_ONLY", "BLOCKED"}:
        raise SoftwareCorrectnessAcceptanceError("snapshot state is not allowed")
    funds = _decimal(snapshot.get("funds_aud"), "funds_aud")
    score = _decimal(snapshot.get("score"), "score")
    threshold = _decimal(snapshot.get("threshold"), "threshold")
    adverse_delta = _decimal(snapshot.get("adverse_delta"), "adverse_delta")
    if threshold != Decimal("0.9500") or adverse_delta not in {Decimal("-0.0001"), Decimal("0.0000"), Decimal("0.0001")}:
        raise SoftwareCorrectnessAcceptanceError("threshold or adverse delta is not frozen")

    branch_ids = ["SCHEMA-CLOSED", "SERIALIZATION-CANONICAL"]
    if funds < Decimal("0.0000"):
        branch_ids.append("FUNDS-NEGATIVE-REJECT")
        return {
            "case_id": case_id,
            "status": "INVALID_FUNDS_REJECTED_NO_ACTION",
            "effective_score": None,
            "threshold_pass": False,
            "branch_ids": branch_ids,
            "recommendation_generated": False,
            "order_submission_enabled": False,
            "external_state_changed": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        }
    if funds == Decimal("0.0000"):
        branch_ids.append("FUNDS-ZERO")
    else:
        branch_ids.append("FUNDS-POSITIVE")
    if adverse_delta == Decimal("-0.0001"):
        branch_ids.append("ADVERSE-DELTA-NEGATIVE-ONE-IN-TEN-THOUSAND")
    elif adverse_delta == Decimal("0.0001"):
        branch_ids.append("ADVERSE-DELTA-POSITIVE-ONE-IN-TEN-THOUSAND")
    else:
        branch_ids.append("ADVERSE-DELTA-NEUTRAL")
    effective_score = score + adverse_delta
    if effective_score < threshold:
        branch_ids.append("THRESHOLD-BELOW")
        threshold_pass = False
    elif effective_score == threshold:
        branch_ids.append("THRESHOLD-EXACT")
        threshold_pass = True
    else:
        branch_ids.append("THRESHOLD-ABOVE")
        threshold_pass = True
    if snapshot.get("state") == "BLOCKED":
        branch_ids.append("STATE-BLOCKED")
    else:
        branch_ids.append("STATE-LOCAL-TEST-ONLY")

    if funds == Decimal("0.0000"):
        status = "NO_ACTION_ZERO_FUNDS"
        branch_ids.append("NO-ACTION-ZERO-FUNDS")
    elif not threshold_pass:
        status = "NO_ACTION_THRESHOLD_NOT_MET"
        branch_ids.append("NO-ACTION-THRESHOLD")
    elif snapshot.get("state") == "BLOCKED":
        status = "NO_ACTION_STATE_BLOCKED"
        branch_ids.append("NO-ACTION-STATE-BLOCKED")
    else:
        status = "LOCAL_TEST_PASS_NO_ACTION"
        branch_ids.append("LOCAL-TEST-PASS-NO-ACTION")
    return {
        "case_id": case_id,
        "status": status,
        "effective_score": format(effective_score, ".4f"),
        "threshold_pass": threshold_pass,
        "branch_ids": branch_ids,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_state_changed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def calculate_branch_coverage(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Calculate only the declared S15/P01 decision-branch coverage surface."""

    covered = {
        branch
        for result in results
        if isinstance(result, Mapping)
        for branch in result.get("branch_ids", [])
        if isinstance(branch, str) and branch in REQUIRED_BRANCH_IDS
    }
    ratio = (Decimal(len(covered)) / Decimal(len(REQUIRED_BRANCH_IDS))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return {
        "coverage_scope": dict(COVERAGE_SCOPE),
        "covered_branch_ids": [branch for branch in REQUIRED_BRANCH_IDS if branch in covered],
        "missing_branch_ids": [branch for branch in REQUIRED_BRANCH_IDS if branch not in covered],
        "branch_coverage": format(ratio, ".4f"),
        "minimum_branch_coverage": "0.9500",
        "passes": ratio >= Decimal("0.9500"),
    }


def evaluate_property_suite(results_by_case: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluate the frozen money and threshold properties from replay results."""

    missing = [case_id for case_id in EXPECTED_CASE_IDS if case_id not in results_by_case]
    if missing:
        raise SoftwareCorrectnessAcceptanceError("property suite is missing cases: %s" % ",".join(missing))
    all_results = [results_by_case[case_id] for case_id in EXPECTED_CASE_IDS]
    properties = [
        {
            "id": "PROP-S15-P01-NO-INCREMENTAL-CASH",
            "passed": all(
                result.get("incremental_cash_spent_aud") == "0.00"
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_state_changed") is False
                for result in all_results
            ),
        },
        {
            "id": "PROP-S15-P01-THRESHOLD-FAILS-CLOSED",
            "passed": all(
                results_by_case[case_id].get("status") == "NO_ACTION_THRESHOLD_NOT_MET"
                and results_by_case[case_id].get("threshold_pass") is False
                for case_id in (
                    "S15-P01-BELOW-THRESHOLD",
                    "S15-P01-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
                )
            ),
        },
        {
            "id": "PROP-S15-P01-ZERO-AND-NEGATIVE-FUNDS-SAFE",
            "passed": (
                results_by_case["S15-P01-ZERO-FUNDS"].get("status") == "NO_ACTION_ZERO_FUNDS"
                and results_by_case["S15-P01-NEGATIVE-FUNDS-REJECTED"].get("status") == "INVALID_FUNDS_REJECTED_NO_ACTION"
            ),
        },
        {
            "id": "PROP-S15-P01-LOCAL-STATE-NEVER-ORDERS",
            "passed": all(
                results_by_case[case_id].get("order_submission_enabled") is False
                and results_by_case[case_id].get("recommendation_generated") is False
                for case_id in (
                    "S15-P01-EXACT-THRESHOLD",
                    "S15-P01-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
                    "S15-P01-BLOCKED-STATE",
                )
            ),
        },
    ]
    return properties


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.as_posix())
    return value


def _validate_unit_tests(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "artifact_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "coverage_scope",
        "required_branch_ids",
        "minimum_branch_coverage",
        "case_ids",
        "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "unit_tests")
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P01-01"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("coverage_scope") == COVERAGE_SCOPE
        and document.get("required_branch_ids") == list(REQUIRED_BRANCH_IDS)
        and document.get("minimum_branch_coverage") == "0.9500"
        and document.get("case_ids") == list(EXPECTED_CASE_IDS)
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise SoftwareCorrectnessAcceptanceError("unit test catalog is not exact")
    return document


def _validate_property_tests(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "artifact_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "properties",
        "property_pass_threshold",
        "required_adverse_delta",
        "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "property_tests")
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P01-02"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("properties") == list(PROPERTY_SPECS)
        and document.get("property_pass_threshold") == "1.0000"
        and document.get("required_adverse_delta") == "-0.0001"
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise SoftwareCorrectnessAcceptanceError("property test catalog is not exact")
    return document


def _validate_schema_tests(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "artifact_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "closed_snapshot_fields",
        "decimal_text_fields",
        "allowed_adverse_deltas",
        "negative_mutation_ids",
        "serialization",
        "synthetic_test_only_required",
        "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "schema_tests")
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P01-03"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("closed_snapshot_fields") == list(SNAPSHOT_FIELDS)
        and document.get("decimal_text_fields") == ["funds_aud", "score", "threshold", "adverse_delta"]
        and document.get("allowed_adverse_deltas") == ["-0.0001", "0.0000", "0.0001"]
        and document.get("negative_mutation_ids") == list(NEGATIVE_MUTATION_IDS)
        and document.get("serialization") == "CANONICAL_JSON_V1"
        and document.get("synthetic_test_only_required") is True
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise SoftwareCorrectnessAcceptanceError("schema test catalog is not exact")
    return document


def _validate_fixture(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "parameters_sha256",
        "predecessors",
        "execution_policy",
        "minimum_targeted_pytest_cases",
        "expected_case_ids",
        "expected_branch_ids",
        "expected_branch_coverage",
        "expected_property_ids",
        "expected_negative_mutation_ids",
        "expected_decision",
        "expected_next",
        "snapshot_cases",
    }
    document = _closed_mapping(document, fields, "S15 fixture")
    predecessor_shape = {
        contract_id: {
            "evidence_path": metadata["evidence_path"].as_posix(),
            "evidence_sha256": metadata["evidence_sha256"],
            "rollback_path": metadata["rollback_path"].as_posix(),
            "rollback_sha256": metadata["rollback_sha256"],
            "next": metadata["next"],
        }
        for contract_id, metadata in PREDECESSORS.items()
    }
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("fixture_id") == "FIX-S15-P01-OFFLINE-CORRECTNESS"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("parameters_sha256") == BASELINE_HASHES[PARAMETERS_PATH.as_posix()]
        and document.get("predecessors") == predecessor_shape
        and document.get("execution_policy") == EXECUTION_POLICY
        and isinstance(document.get("minimum_targeted_pytest_cases"), int)
        and document.get("minimum_targeted_pytest_cases") >= 18
        and document.get("expected_case_ids") == list(EXPECTED_CASE_IDS)
        and document.get("expected_branch_ids") == list(REQUIRED_BRANCH_IDS)
        and document.get("expected_branch_coverage") == "1.0000"
        and document.get("expected_property_ids") == [item["id"] for item in PROPERTY_SPECS]
        and document.get("expected_negative_mutation_ids") == list(NEGATIVE_MUTATION_IDS)
        and document.get("expected_decision") == "S15_P01_CORRECTNESS_TEST_SURFACE_READY_P02_REQUIRED"
        and document.get("expected_next") == "S15/P02_READY_NOT_STARTED"
        and isinstance(document.get("snapshot_cases"), list)
    )
    if not valid:
        raise SoftwareCorrectnessAcceptanceError("S15 fixture is not exact")
    return document


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S15P01-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S15P01-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S15P01-CONTRACTS-STRICT-JSON")
    tasks = _safe_load(root, TASK_GRAPH_PATH, checks, "S15P01-TASKS-STRICT-JSON")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S15P01-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        task_rows = tasks.get("tasks") if isinstance(tasks, Mapping) else tasks
        if not isinstance(task_rows, list):
            raise SoftwareCorrectnessAcceptanceError("task graph tasks are unavailable")
        p01_tasks = [item for item in task_rows if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        task_outputs = {item.get("id"): item.get("outputs") for item in p01_tasks}
        valid = (
            requirement.get("scope") == ["unit_tests", "property_tests", "schema_tests"]
            and requirement.get("target") == "关键模块分支覆盖≥95%，资金/阈值属性测试100%通过。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S15-P01 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in p01_tasks] == list(EXPECTED_TASK_IDS)
            and task_outputs == {
                "T-S15-P01-01": ["unit_tests", "property_tests", "schema_tests"],
                "T-S15-P01-02": ["tests/S15/P01_test.py", "machine/tests/fixtures/S15_P01.json"],
                "T-S15-P01-03": ["machine/evidence/EVD-S15-P01.json", "machine/evidence/EVD-S15-P01_rollback.json"],
            }
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S15-P01"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACTS)
        )
    except Exception as exc:
        valid = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S15P01-TASKPACK-SCOPE-TRACE-EXACT", valid, requirement if not valid else list(EXPECTED_TASK_IDS))
    index = _safe_load_evidence_index(root, checks)
    try:
        row = _row(index, "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "关键模块分支覆盖≥95%，资金/阈值属性测试100%通过。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "PHASE_EVIDENCE"
            and row.get("stage_id") == STAGE_ID
            and row.get("contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("artifact_sha256") == (sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING")
            and row.get("next") == "S15/P02_READY_NOT_STARTED"
        )
        _add(checks, "S15P01-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S15P01-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _safe_load_evidence_index(root: Path, checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S15P01-EVIDENCE-INDEX-STRICT-JSONL", True, EVIDENCE_INDEX_PATH.as_posix())
        return rows
    except Exception as exc:
        _add(checks, "S15P01-EVIDENCE-INDEX-STRICT-JSONL", False, "%s: %s" % (type(exc).__name__, exc))
        return []


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for contract_id, metadata in PREDECESSORS.items():
        evidence_path = metadata["evidence_path"]
        rollback_path = metadata["rollback_path"]
        evidence_hash = sha256_file(root / evidence_path) if (root / evidence_path).is_file() else "MISSING"
        rollback_hash = sha256_file(root / rollback_path) if (root / rollback_path).is_file() else "MISSING"
        hashes[evidence_path.as_posix()] = evidence_hash
        hashes[rollback_path.as_posix()] = rollback_hash
        try:
            result = metadata["verifier"](root)
            valid = (
                result.get("contract_id") == contract_id
                and result.get("status") == "PASS"
                and result.get("evidence_sha256") == metadata["evidence_sha256"] == evidence_hash
                and result.get("next") == metadata["next"]
                and rollback_hash == metadata["rollback_sha256"]
            )
        except Exception as exc:
            valid = False
            result = "%s: %s" % (type(exc).__name__, exc)
        _add(checks, "S15P01-PREDECESSOR-%s" % contract_id, valid, result)


def _check_delivery_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    loaded: List[Mapping[str, Any] | None] = []
    validators: Tuple[Callable[[Any], Mapping[str, Any]], ...] = (_validate_unit_tests, _validate_property_tests, _validate_schema_tests)
    for path, validator, label in zip((UNIT_TESTS_PATH, PROPERTY_TESTS_PATH, SCHEMA_TESTS_PATH), validators, ("UNIT", "PROPERTY", "SCHEMA")):
        document = _safe_load(root, path, checks, "S15P01-%s-CATALOG-STRICT-JSON" % label)
        try:
            validated = validator(document)
            hashes[path.as_posix()] = sha256_file(root / path)
            _add(checks, "S15P01-%s-CATALOG-EXACT" % label, True, path.as_posix())
        except Exception as exc:
            validated = None
            _add(checks, "S15P01-%s-CATALOG-EXACT" % label, False, "%s: %s" % (type(exc).__name__, exc))
        loaded.append(validated)
    return loaded[0], loaded[1], loaded[2]


def _check_fixture_cases(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Mapping[str, Any] | None:
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S15P01-FIXTURE-STRICT-JSON")
    try:
        fixture = _validate_fixture(fixture)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        _add(checks, "S15P01-FIXTURE-EXACT", True, FIXTURE_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P01-FIXTURE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        return None
    cases = fixture["snapshot_cases"]
    if [item.get("case_id") for item in cases if isinstance(item, Mapping)] != list(EXPECTED_CASE_IDS) or len(cases) != len(EXPECTED_CASE_IDS):
        _add(checks, "S15P01-FROZEN-CASE-ORDER-EXACT", False, cases)
        return fixture
    _add(checks, "S15P01-FROZEN-CASE-ORDER-EXACT", True, list(EXPECTED_CASE_IDS))
    results: Dict[str, Dict[str, Any]] = {}
    for item in cases:
        try:
            if not isinstance(item, Mapping) or set(item) != {"case_id", "snapshot", "expected"}:
                raise SoftwareCorrectnessAcceptanceError("fixture case fields are not closed")
            result = evaluate_quality_snapshot(item["snapshot"])
            expected = item["expected"]
            if not isinstance(expected, Mapping) or result != expected:
                raise SoftwareCorrectnessAcceptanceError("fixture case replay differs")
            results[str(item["case_id"])] = result
            _add(checks, "S15P01-CASE-%s" % item["case_id"], True, result["status"])
        except Exception as exc:
            _add(checks, "S15P01-CASE-%s" % (item.get("case_id") if isinstance(item, Mapping) else "INVALID"), False, "%s: %s" % (type(exc).__name__, exc))
    try:
        coverage = calculate_branch_coverage(list(results.values()))
        _add(
            checks,
            "S15P01-DECLARED-BRANCH-COVERAGE-AT-LEAST-95-PERCENT",
            coverage["passes"] and coverage["branch_coverage"] == fixture["expected_branch_coverage"],
            coverage,
        )
        properties = evaluate_property_suite(results)
        properties_ok = [item["id"] for item in properties] == fixture["expected_property_ids"] and all(item["passed"] for item in properties)
        _add(checks, "S15P01-FUNDS-AND-THRESHOLD-PROPERTIES-100-PERCENT", properties_ok, properties)
    except Exception as exc:
        _add(checks, "S15P01-DECLARED-BRANCH-COVERAGE-AT-LEAST-95-PERCENT", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S15P01-FUNDS-AND-THRESHOLD-PROPERTIES-100-PERCENT", False, "%s: %s" % (type(exc).__name__, exc))
    return fixture


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"}
        forbidden_tokens = ("slee" "p(", "submit" "_order", "retry" "_order", "http" "://", "https" "://")
        no_capability = not imports.intersection(forbidden) and all(token not in source for token in forbidden_tokens)
        _add(checks, "S15P01-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", no_capability, {"imports": sorted(imports), "forbidden": sorted(imports.intersection(forbidden))})
    except Exception as exc:
        _add(checks, "S15P01-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
    if not suites:
        raise SoftwareCorrectnessAcceptanceError("JUnit has no testsuite")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    normalized = True
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
        normalized = normalized and suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        normalized = normalized and suite.attrib.get("time") == "0.000"
        normalized = normalized and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S15P01-TARGETED-REPORTS-REQUIRED", True, "preflight mode")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        passed = (
            isinstance(minimum, int)
            and summary["tests"] >= minimum
            and not summary["failures"]
            and not summary["errors"]
            and not summary["skipped"]
            and normalized
        )
        _add(checks, "S15P01-TARGETED-PYTEST-REPORT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S15P01-TARGETED-PYTEST-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S15P01-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P01-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S15P01-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S15P01-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S15_P01_CORRECTNESS_TEST_SURFACE_READY_P02_REQUIRED" if passed else "S15/P01_BLOCKED",
        "next": "S15/P02_READY_NOT_STARTED" if passed else "S15/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "coverage_claim_boundary": dict(COVERAGE_SCOPE),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Evaluate the frozen S15/P01 contract, with reports only when requested."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack(root, checks)
    _check_predecessors(root, checks, hashes)
    _check_delivery_artifacts(root, checks, hashes)
    fixture = _check_fixture_cases(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    """Record a local-only disable operation without changing external state."""

    root = root.resolve()
    artifacts = {
        path.as_posix(): {
            "sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING",
            "status": "PASS" if (root / path).is_file() else "FAIL",
        }
        for path in (UNIT_TESTS_PATH, PROPERTY_TESTS_PATH, SCHEMA_TESTS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S15_P01_LOCAL_CORRECTNESS_TEST_SURFACE_KEEP_SIGNED_PREDECESSORS",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        ORACLE_PATH,
        UNIT_TESTS_PATH,
        PROPERTY_TESTS_PATH,
        SCHEMA_TESTS_PATH,
        TEST_PATH,
        FIXTURE_PATH,
        *[Path(relative) for relative in BASELINE_HASHES],
        *[metadata["evidence_path"] for metadata in PREDECESSORS.values()],
        *[metadata["rollback_path"] for metadata in PREDECESSORS.values()],
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = {
        "contract_id": evidence.get("contract_id"),
        "decision": evidence.get("decision"),
        "next": evidence.get("next"),
        "status": evidence.get("status"),
        "validation": evidence.get("validation"),
    }
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P01",
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
        "coverage_claim_boundary": dict(COVERAGE_SCOPE),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S15_P01_LOCAL_EVIDENCE_ONLY_P02_REQUIRED",
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S15/P01_test.py --junitxml=machine/evidence/S15/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S15/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S15/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S15-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {
            "snapshot_case_count": len(EXPECTED_CASE_IDS),
            "declared_branch_count": len(REQUIRED_BRANCH_IDS),
            "adverse_delta": "-0.0001",
            "real_time_wait_performed": False,
        },
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
        raise SoftwareCorrectnessAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S15/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise SoftwareCorrectnessAcceptanceError("S15/P01 evidence-index row must exist exactly once")
    output = [
        _jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8")
        for raw_line, row in zip(raw_lines, rows)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise SoftwareCorrectnessAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise SoftwareCorrectnessAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S15/P02_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise SoftwareCorrectnessAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S15_P01_CORRECTNESS_TEST_SURFACE_READY_P02_REQUIRED"
        and evidence.get("next") == "S15/P02_READY_NOT_STARTED"
        and evidence.get("coverage_claim_boundary") == COVERAGE_SCOPE
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
    )
    if not valid:
        raise SoftwareCorrectnessAcceptanceError("existing S15/P01 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S15/P02_READY_NOT_STARTED",
    }


__all__ = [
    "CONTRACT_ID",
    "COVERAGE_SCOPE",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FEATURE_FLAG_ID",
    "FIXTURE_PATH",
    "NEGATIVE_MUTATION_IDS",
    "ORACLE_PATH",
    "PROPERTY_SPECS",
    "REQUIRED_BRANCH_IDS",
    "SCHEMA_TESTS_PATH",
    "SNAPSHOT_FIELDS",
    "SoftwareCorrectnessAcceptanceError",
    "TEST_PATH",
    "UNIT_TESTS_PATH",
    "calculate_branch_coverage",
    "evaluate_contract",
    "evaluate_property_suite",
    "evaluate_quality_snapshot",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
