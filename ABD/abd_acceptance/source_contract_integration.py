"""Fail-closed, fixture-only acceptance oracle for ABD S15/P02.

This phase verifies page, archived-mail, odds, and result source contracts
through frozen local fixtures.  A simulated unavailable-network input is
intentionally not a live network outage test: no network capability is used.
It proves deterministic fixture replay only, never a runtime, deployment,
market, account, order, or financial-return claim.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .software_correctness import verify_existing_phase_evidence as verify_s15_p01_evidence


CONTRACT_ID = "AC-S15-P02"
REQUIREMENT_ID = "REQ-S15-P02"
STAGE_ID = "S15"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_TESTS_PATH = Path("contract_tests.json")
INTEGRATION_TESTS_PATH = Path("integration_tests.json")
FIXTURES_MANIFEST_PATH = Path("fixtures_manifest.json")
ORACLE_PATH = Path("abd_acceptance/source_contract_integration.py")
TEST_PATH = Path("tests/S15/P02_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S15_P02.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S15/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S15/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
ROADMAP_PATH = Path("machine/facts/roadmap.json")
CANONICAL_FACTS_PATH = Path("machine/facts/canonical_facts.json")

P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S15-P01_rollback.json")
P01_EVIDENCE_SHA256 = "5ea76d98f26bb3225844a0e9ab62c58041647ca5e3337c4c722d7d842ddfc98a"
P01_ROLLBACK_SHA256 = "cd3b6d2d8e0934103e168c89758f24be727e996f65f86eead8e733ddb678854b"

FEATURE_FLAG_ID = "quality:s15-p02-local-source-contract-integration"
EXPECTED_TASK_IDS = ("T-S15-P02-01", "T-S15-P02-02", "T-S15-P02-03")
EXPECTED_TEST_IDS = ("TEST-S15-P02", "TEST-S15-P02-BOUNDARY", "TEST-S15-P02-REPLAY")
EXPECTED_ARTIFACTS = {
    "ART-S15-P02-01": CONTRACT_TESTS_PATH,
    "ART-S15-P02-02": INTEGRATION_TESTS_PATH,
    "ART-S15-P02-03": FIXTURES_MANIFEST_PATH,
}
SOURCE_SPECS = (
    {
        "id": "SRC-S15-P02-PAGE",
        "fixture_path": Path("machine/tests/fixtures/S15_P02/page_fixture.json"),
        "source_type": "FROZEN_VISIBLE_PAGE",
        "fixture_id": "FIX-S15-P02-PAGE-001",
        "payload_fields": ("event_id", "market_id", "selection_id", "ticket_id", "page_status", "locale", "visible_odds"),
    },
    {
        "id": "SRC-S15-P02-MAIL",
        "fixture_path": Path("machine/tests/fixtures/S15_P02/mail_fixture.json"),
        "source_type": "FROZEN_ARCHIVED_MAIL",
        "fixture_id": "FIX-S15-P02-MAIL-001",
        "payload_fields": ("event_id", "selection_id", "ticket_id", "archive_status", "evidence_status"),
    },
    {
        "id": "SRC-S15-P02-ODDS",
        "fixture_path": Path("machine/tests/fixtures/S15_P02/odds_fixture.json"),
        "source_type": "FROZEN_ODDS_SNAPSHOT",
        "fixture_id": "FIX-S15-P02-ODDS-001",
        "payload_fields": ("event_id", "market_id", "selection_id", "ticket_id", "quoted_odds", "minimum_odds", "odds_status"),
    },
    {
        "id": "SRC-S15-P02-RESULT",
        "fixture_path": Path("machine/tests/fixtures/S15_P02/result_fixture.json"),
        "source_type": "FROZEN_RESULT_RECORD",
        "fixture_id": "FIX-S15-P02-RESULT-001",
        "payload_fields": ("event_id", "selection_id", "ticket_id", "settlement_status", "actual_return_claimed"),
    },
)
SOURCE_CONTRACT_IDS = tuple(item["id"] for item in SOURCE_SPECS)
EXPECTED_CASE_IDS = (
    "S15-P02-BASELINE-LOCAL",
    "S15-P02-SIMULATED-NETWORK-UNAVAILABLE",
    "S15-P02-ODDS-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND",
    "S15-P02-ODDS-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND",
    "S15-P02-PAGE-EVENT-MISMATCH",
    "S15-P02-MAIL-NOT-ARCHIVED",
    "S15-P02-RESULT-TICKET-MISMATCH",
)
EXPECTED_CASES = (
    ("S15-P02-BASELINE-LOCAL", "LOCAL_FIXTURE_REPLAY", "NONE", "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION", ("ALL_SOURCE_CONTRACTS_MATCHED_LOCAL_FIXTURES",)),
    ("S15-P02-SIMULATED-NETWORK-UNAVAILABLE", "SIMULATED_NETWORK_UNAVAILABLE", "NONE", "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION", ("ALL_SOURCE_CONTRACTS_MATCHED_LOCAL_FIXTURES",)),
    ("S15-P02-ODDS-ADVERSE-MINUS-ONE-IN-TEN-THOUSAND", "SIMULATED_NETWORK_UNAVAILABLE", "ODDS_ADVERSE_MINUS_0_0001", "NO_ACTION_SOURCE_CONTRACT_FAILED", ("ODDS_BELOW_MINIMUM_AFTER_ADVERSE_DELTA",)),
    ("S15-P02-ODDS-FAVOURABLE-PLUS-ONE-IN-TEN-THOUSAND", "LOCAL_FIXTURE_REPLAY", "ODDS_FAVOURABLE_PLUS_0_0001", "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION", ("ALL_SOURCE_CONTRACTS_MATCHED_LOCAL_FIXTURES",)),
    ("S15-P02-PAGE-EVENT-MISMATCH", "LOCAL_FIXTURE_REPLAY", "PAGE_EVENT_MISMATCH", "NO_ACTION_SOURCE_CONTRACT_FAILED", ("PAGE_EVENT_ID_MISMATCH",)),
    ("S15-P02-MAIL-NOT-ARCHIVED", "LOCAL_FIXTURE_REPLAY", "MAIL_NOT_ARCHIVED", "NO_ACTION_SOURCE_CONTRACT_FAILED", ("MAIL_EVIDENCE_NOT_ARCHIVED",)),
    ("S15-P02-RESULT-TICKET-MISMATCH", "LOCAL_FIXTURE_REPLAY", "RESULT_TICKET_MISMATCH", "NO_ACTION_SOURCE_CONTRACT_FAILED", ("RESULT_TICKET_ID_MISMATCH",)),
)
NETWORK_MODES = ("LOCAL_FIXTURE_REPLAY", "SIMULATED_NETWORK_UNAVAILABLE")
FAULTS = tuple(item[2] for item in EXPECTED_CASES)
NEGATIVE_MUTATION_IDS = (
    "MUT-S15-P02-UNKNOWN-FIELD",
    "MUT-S15-P02-FLOAT-ODDS",
    "MUT-S15-P02-NONCANONICAL-ODDS",
    "MUT-S15-P02-NONSYNTHETIC-RESULT",
)
COMMON_FIXTURE_FIELDS = (
    "schema_version",
    "fixture_id",
    "source_contract_id",
    "source_type",
    "fixed_clock",
    "synthetic_test_only",
    "external_source_accessed",
    "payload",
)
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "gmail_account_or_api_accessed": False,
    "tab_or_provider_runtime_accessed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
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


class SourceContractIntegrationError(ValueError):
    """Raised when the local S15/P02 source-contract harness is invalid."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


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


def _closed_mapping(value: Any, fields: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields) or _contains_float(value):
        raise SourceContractIntegrationError("%s fields are not closed" % label)
    return value


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"[1-9]\d*\.\d{4}", value) is None:
        raise SourceContractIntegrationError("%s must be positive four-place decimal text" % field)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise SourceContractIntegrationError("%s is not decimal" % field) from exc


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise SourceContractIntegrationError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise SourceContractIntegrationError("JSONL row %d is not an object" % number)
        rows.append(value)
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise SourceContractIntegrationError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise SourceContractIntegrationError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _source_spec(source_contract_id: str) -> Mapping[str, Any]:
    matches = [item for item in SOURCE_SPECS if item["id"] == source_contract_id]
    if len(matches) != 1:
        raise SourceContractIntegrationError("unknown source contract")
    return matches[0]


def validate_source_fixture(source_contract_id: str, document: Any) -> Mapping[str, Any]:
    """Validate a closed local fixture; it never opens a remote source."""

    spec = _source_spec(source_contract_id)
    document = _closed_mapping(document, COMMON_FIXTURE_FIELDS, source_contract_id)
    payload = _closed_mapping(document.get("payload"), spec["payload_fields"], "%s payload" % source_contract_id)
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("fixture_id") == spec["fixture_id"]
        and document.get("source_contract_id") == source_contract_id
        and document.get("source_type") == spec["source_type"]
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("synthetic_test_only") is True
        and document.get("external_source_accessed") is False
        and isinstance(payload.get("event_id"), str)
        and isinstance(payload.get("selection_id"), str)
        and isinstance(payload.get("ticket_id"), str)
    )
    if source_contract_id in {"SRC-S15-P02-PAGE", "SRC-S15-P02-ODDS"}:
        valid = valid and isinstance(payload.get("market_id"), str)
    if source_contract_id == "SRC-S15-P02-PAGE":
        valid = valid and payload.get("page_status") == "VISIBLE_LOCAL_SNAPSHOT" and payload.get("locale") == "zh-AU" and _decimal(payload.get("visible_odds"), "visible_odds") > Decimal("1.0000")
    elif source_contract_id == "SRC-S15-P02-MAIL":
        valid = valid and payload.get("archive_status") == "ARCHIVED_LOCAL_EVIDENCE_ONLY" and payload.get("evidence_status") == "VERIFIED_SYNTHETIC_NOTIFICATION"
    elif source_contract_id == "SRC-S15-P02-ODDS":
        valid = valid and payload.get("odds_status") == "FROZEN_VISIBLE_QUOTE" and _decimal(payload.get("quoted_odds"), "quoted_odds") > Decimal("1.0000") and _decimal(payload.get("minimum_odds"), "minimum_odds") > Decimal("1.0000")
    elif source_contract_id == "SRC-S15-P02-RESULT":
        valid = valid and payload.get("settlement_status") == "SYNTHETIC_UNSETTLED_NO_RETURN_CLAIM" and payload.get("actual_return_claimed") is False
    if not valid:
        raise SourceContractIntegrationError("fixture violates %s" % source_contract_id)
    return document


def _validate_contract_tests(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "artifact_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock",
        "source_contracts", "required_linkage_fields", "odds_boundary_deltas", "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "contract_tests")
    expected_sources = [
        {
            "id": item["id"],
            "fixture_path": item["fixture_path"].as_posix(),
            "source_type": item["source_type"],
            "payload_fields": list(item["payload_fields"]),
        }
        for item in SOURCE_SPECS
    ]
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P02-01"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("source_contracts") == expected_sources
        and document.get("required_linkage_fields") == ["event_id", "selection_id", "ticket_id"]
        and document.get("odds_boundary_deltas") == ["-0.0001", "0.0000", "0.0001"]
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise SourceContractIntegrationError("contract_tests is not exact")
    return document


def _validate_integration_tests(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "artifact_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock",
        "network_modes", "outage_equivalence", "cases", "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "integration_tests")
    expected_cases = [
        {
            "case_id": case_id,
            "network_mode": network_mode,
            "fault": fault,
            "expected": {"status": status, "reason_codes": list(reasons)},
        }
        for case_id, network_mode, fault, status, reasons in EXPECTED_CASES
    ]
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P02-02"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("network_modes") == list(NETWORK_MODES)
        and document.get("outage_equivalence") == {
            "baseline_case_id": "S15-P02-BASELINE-LOCAL",
            "outage_case_id": "S15-P02-SIMULATED-NETWORK-UNAVAILABLE",
            "real_network_outage_exercised": False,
            "deterministic_projection_must_match": True,
        }
        and document.get("cases") == expected_cases
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise SourceContractIntegrationError("integration_tests is not exact")
    return document


def _validate_fixture_manifest(root: Path, document: Any) -> Tuple[Mapping[str, Any], Dict[str, Mapping[str, Any]]]:
    fields = {
        "schema_version", "artifact_id", "manifest_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version",
        "fixed_clock", "fixtures", "shared_identifiers", "external_effect_boundary",
    }
    document = _closed_mapping(document, fields, "fixtures_manifest")
    expected_rows = []
    bundle: Dict[str, Mapping[str, Any]] = {}
    for spec in SOURCE_SPECS:
        path = root / spec["fixture_path"]
        fixture = validate_source_fixture(spec["id"], strict_json_load(path))
        expected_rows.append(
            {
                "fixture_id": spec["fixture_id"],
                "path": spec["fixture_path"].as_posix(),
                "sha256": sha256_file(path),
                "source_contract_id": spec["id"],
            }
        )
        bundle[spec["id"]] = fixture
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("artifact_id") == "ART-S15-P02-03"
        and document.get("manifest_id") == "FIXTURES-S15-P02-LOCAL-SERVICE-BUNDLE"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("fixtures") == expected_rows
        and document.get("shared_identifiers") == {
            "event_id": "EVT-S15-P02-0001",
            "market_id": "MKT-S15-P02-WIN",
            "selection_id": "SEL-S15-P02-ALPHA",
            "ticket_id": "TICKET-S15-P02-0001",
        }
        and document.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not valid:
        raise SourceContractIntegrationError("fixtures_manifest is not exact")
    return document, bundle


def _validate_fixture(document: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "fixture_id", "contract_id", "requirement_id", "stage_id", "phase_id", "product_version", "fixed_clock",
        "parameters_sha256", "predecessor", "execution_policy", "minimum_targeted_pytest_cases", "expected_source_contract_ids",
        "expected_case_ids", "expected_outage_equivalence", "expected_negative_mutation_ids", "expected_decision", "expected_next",
    }
    document = _closed_mapping(document, fields, "S15 P02 fixture")
    expected_predecessor = {
        "contract_id": "AC-S15-P01",
        "evidence_path": P01_EVIDENCE_PATH.as_posix(),
        "evidence_sha256": P01_EVIDENCE_SHA256,
        "rollback_path": P01_ROLLBACK_PATH.as_posix(),
        "rollback_sha256": P01_ROLLBACK_SHA256,
        "next": "S15/P02_READY_NOT_STARTED",
    }
    valid = (
        document.get("schema_version") == "1.0.0"
        and document.get("fixture_id") == "FIX-S15-P02-LOCAL-SOURCE-CONTRACT-INTEGRATION"
        and document.get("contract_id") == CONTRACT_ID
        and document.get("requirement_id") == REQUIREMENT_ID
        and document.get("stage_id") == STAGE_ID
        and document.get("phase_id") == PHASE_ID
        and document.get("product_version") == VERSION
        and document.get("fixed_clock") == FIXED_CLOCK
        and document.get("parameters_sha256") == BASELINE_HASHES[PARAMETERS_PATH.as_posix()]
        and document.get("predecessor") == expected_predecessor
        and document.get("execution_policy") == EXECUTION_POLICY
        and isinstance(document.get("minimum_targeted_pytest_cases"), int)
        and document.get("minimum_targeted_pytest_cases") >= 18
        and document.get("expected_source_contract_ids") == list(SOURCE_CONTRACT_IDS)
        and document.get("expected_case_ids") == list(EXPECTED_CASE_IDS)
        and document.get("expected_outage_equivalence") == {
            "baseline_case_id": "S15-P02-BASELINE-LOCAL",
            "outage_case_id": "S15-P02-SIMULATED-NETWORK-UNAVAILABLE",
        }
        and document.get("expected_negative_mutation_ids") == list(NEGATIVE_MUTATION_IDS)
        and document.get("expected_decision") == "S15_P02_LOCAL_SOURCE_CONTRACT_INTEGRATION_READY_P03_REQUIRED"
        and document.get("expected_next") == "S15/P03_READY_NOT_STARTED"
    )
    if not valid:
        raise SourceContractIntegrationError("S15 P02 fixture is not exact")
    return document


def _bundle_sha256(manifest: Mapping[str, Any]) -> str:
    return _canonical_sha256({"fixtures": manifest.get("fixtures"), "shared_identifiers": manifest.get("shared_identifiers")})


def _faulted_bundle(bundle: Mapping[str, Mapping[str, Any]], fault: str) -> Dict[str, Dict[str, Any]]:
    result = {source_id: deepcopy(dict(value)) for source_id, value in bundle.items()}
    if fault == "NONE":
        return result
    if fault == "ODDS_ADVERSE_MINUS_0_0001":
        result["SRC-S15-P02-ODDS"]["payload"]["quoted_odds"] = "1.7999"
    elif fault == "ODDS_FAVOURABLE_PLUS_0_0001":
        result["SRC-S15-P02-ODDS"]["payload"]["quoted_odds"] = "1.8001"
    elif fault == "PAGE_EVENT_MISMATCH":
        result["SRC-S15-P02-PAGE"]["payload"]["event_id"] = "EVT-S15-P02-MISMATCH"
    elif fault == "MAIL_NOT_ARCHIVED":
        result["SRC-S15-P02-MAIL"]["payload"]["archive_status"] = "NOT_ARCHIVED"
    elif fault == "RESULT_TICKET_MISMATCH":
        result["SRC-S15-P02-RESULT"]["payload"]["ticket_id"] = "TICKET-S15-P02-MISMATCH"
    else:
        raise SourceContractIntegrationError("fault is not declared")
    return result


def evaluate_integration_case(manifest: Mapping[str, Any], bundle: Mapping[str, Mapping[str, Any]], case: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay one local multi-source integration case with no runtime network."""

    case = _closed_mapping(case, ("case_id", "network_mode", "fault", "expected"), "integration case")
    if not isinstance(case.get("case_id"), str) or case.get("case_id") not in EXPECTED_CASE_IDS:
        raise SourceContractIntegrationError("case_id is not declared")
    if case.get("network_mode") not in NETWORK_MODES or case.get("fault") not in FAULTS:
        raise SourceContractIntegrationError("case network mode or fault is not declared")
    faulted = _faulted_bundle(bundle, str(case["fault"]))
    page = faulted["SRC-S15-P02-PAGE"]["payload"]
    mail = faulted["SRC-S15-P02-MAIL"]["payload"]
    odds = faulted["SRC-S15-P02-ODDS"]["payload"]
    result = faulted["SRC-S15-P02-RESULT"]["payload"]
    if page.get("event_id") != odds.get("event_id") or page.get("event_id") != mail.get("event_id"):
        status, reasons = "NO_ACTION_SOURCE_CONTRACT_FAILED", ["PAGE_EVENT_ID_MISMATCH"]
    elif mail.get("archive_status") != "ARCHIVED_LOCAL_EVIDENCE_ONLY" or mail.get("evidence_status") != "VERIFIED_SYNTHETIC_NOTIFICATION":
        status, reasons = "NO_ACTION_SOURCE_CONTRACT_FAILED", ["MAIL_EVIDENCE_NOT_ARCHIVED"]
    elif _decimal(odds.get("quoted_odds"), "quoted_odds") < _decimal(odds.get("minimum_odds"), "minimum_odds"):
        status, reasons = "NO_ACTION_SOURCE_CONTRACT_FAILED", ["ODDS_BELOW_MINIMUM_AFTER_ADVERSE_DELTA"]
    elif result.get("ticket_id") != page.get("ticket_id") or result.get("ticket_id") != odds.get("ticket_id"):
        status, reasons = "NO_ACTION_SOURCE_CONTRACT_FAILED", ["RESULT_TICKET_ID_MISMATCH"]
    elif result.get("actual_return_claimed") is not False or result.get("settlement_status") != "SYNTHETIC_UNSETTLED_NO_RETURN_CLAIM":
        status, reasons = "NO_ACTION_SOURCE_CONTRACT_FAILED", ["RESULT_RETURN_CLAIM_NOT_ALLOWED"]
    else:
        status, reasons = "LOCAL_FIXTURE_INTEGRATION_PASS_NO_ACTION", ["ALL_SOURCE_CONTRACTS_MATCHED_LOCAL_FIXTURES"]
    projection = {
        "status": status,
        "reason_codes": reasons,
        "source_contract_ids": list(SOURCE_CONTRACT_IDS),
        "fixture_bundle_sha256": _bundle_sha256(manifest),
        "external_network_accessed": False,
        "gmail_account_or_api_accessed": False,
        "tab_or_provider_runtime_accessed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "actual_return_claimed": False,
        "external_state_changed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    return {
        "case_id": case["case_id"],
        "network_mode": case["network_mode"],
        "network_probe_performed": False,
        "real_network_outage_exercised": False,
        "decision_projection": projection,
        "decision_projection_sha256": _canonical_sha256(projection),
    }


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.as_posix())
    return value


def _safe_load_evidence_index(root: Path, checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S15P02-EVIDENCE-INDEX-STRICT-JSONL", True, EVIDENCE_INDEX_PATH.as_posix())
        return rows
    except Exception as exc:
        _add(checks, "S15P02-EVIDENCE-INDEX-STRICT-JSONL", False, "%s: %s" % (type(exc).__name__, exc))
        return []


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        _add(checks, "S15P02-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S15P02-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S15P02-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S15P02-TASKS-STRICT-JSON")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S15P02-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise SourceContractIntegrationError("task graph tasks are unavailable")
        p02_tasks = [item for item in tasks if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        task_outputs = {item.get("id"): item.get("outputs") for item in p02_tasks}
        valid = (
            requirement.get("scope") == ["contract_tests", "integration_tests", "fixtures_manifest.json"]
            and requirement.get("target") == "真实网络故障不影响测试确定性。"
            and requirement.get("non_goals") == ["不自动提交、确认或重试真实订单", "不以降低证据或风险门追赶30%月目标", "不引入付费数据或付费程序接口依赖"]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S15-P02 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in p02_tasks] == list(EXPECTED_TASK_IDS)
            and task_outputs == {
                "T-S15-P02-01": ["contract_tests", "integration_tests", "fixtures_manifest.json"],
                "T-S15-P02-02": ["tests/S15/P02_test.py", "machine/tests/fixtures/S15_P02.json"],
                "T-S15-P02-03": ["machine/evidence/EVD-S15-P02.json", "machine/evidence/EVD-S15-P02_rollback.json"],
            }
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S15-P02"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACTS)
        )
    except Exception as exc:
        valid = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S15P02-TASKPACK-SCOPE-TRACE-EXACT", valid, requirement if not valid else list(EXPECTED_TASK_IDS))
    index = _safe_load_evidence_index(root, checks)
    try:
        row = _row(index, "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("id") == "INDEX-%s" % CONTRACT_ID
            and row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "真实网络故障不影响测试确定性。"
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
            and row.get("next") == "S15/P03_READY_NOT_STARTED"
        )
        _add(checks, "S15P02-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S15P02-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence_hash = sha256_file(root / P01_EVIDENCE_PATH) if (root / P01_EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / P01_ROLLBACK_PATH) if (root / P01_ROLLBACK_PATH).is_file() else "MISSING"
    hashes[P01_EVIDENCE_PATH.as_posix()] = evidence_hash
    hashes[P01_ROLLBACK_PATH.as_posix()] = rollback_hash
    try:
        result = verify_s15_p01_evidence(root)
        valid = (
            result.get("contract_id") == "AC-S15-P01"
            and result.get("status") == "PASS"
            and result.get("evidence_sha256") == P01_EVIDENCE_SHA256 == evidence_hash
            and result.get("next") == "S15/P02_READY_NOT_STARTED"
            and rollback_hash == P01_ROLLBACK_SHA256
        )
    except Exception as exc:
        result = "%s: %s" % (type(exc).__name__, exc)
        valid = False
    _add(checks, "S15P02-P01-SIGNED-PREDECESSOR-EXACT", valid, result)


def _load_delivery_bundle(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> Tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None, Dict[str, Mapping[str, Any]]]:
    contract_tests = _safe_load(root, CONTRACT_TESTS_PATH, checks, "S15P02-CONTRACT-TESTS-STRICT-JSON")
    integration_tests = _safe_load(root, INTEGRATION_TESTS_PATH, checks, "S15P02-INTEGRATION-TESTS-STRICT-JSON")
    manifest = _safe_load(root, FIXTURES_MANIFEST_PATH, checks, "S15P02-FIXTURES-MANIFEST-STRICT-JSON")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S15P02-FIXTURE-STRICT-JSON")
    bundle: Dict[str, Mapping[str, Any]] = {}
    for path, document, validator, name in (
        (CONTRACT_TESTS_PATH, contract_tests, _validate_contract_tests, "CONTRACT-TESTS"),
        (INTEGRATION_TESTS_PATH, integration_tests, _validate_integration_tests, "INTEGRATION-TESTS"),
        (FIXTURE_PATH, fixture, _validate_fixture, "FIXTURE"),
    ):
        try:
            validator(document)
            hashes[path.as_posix()] = sha256_file(root / path)
            _add(checks, "S15P02-%s-EXACT" % name, True, path.as_posix())
        except Exception as exc:
            _add(checks, "S15P02-%s-EXACT" % name, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        manifest, bundle = _validate_fixture_manifest(root, manifest)
        hashes[FIXTURES_MANIFEST_PATH.as_posix()] = sha256_file(root / FIXTURES_MANIFEST_PATH)
        for spec in SOURCE_SPECS:
            hashes[spec["fixture_path"].as_posix()] = sha256_file(root / spec["fixture_path"])
        _add(checks, "S15P02-FIXTURES-MANIFEST-AND-HASHES-EXACT", True, list(SOURCE_CONTRACT_IDS))
    except Exception as exc:
        _add(checks, "S15P02-FIXTURES-MANIFEST-AND-HASHES-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    return contract_tests, integration_tests, manifest, fixture, bundle


def _check_integration_cases(integration_tests: Any, manifest: Any, fixture: Any, bundle: Mapping[str, Mapping[str, Any]], checks: List[Dict[str, Any]]) -> None:
    if not isinstance(integration_tests, Mapping) or not isinstance(manifest, Mapping) or not isinstance(fixture, Mapping) or set(bundle) != set(SOURCE_CONTRACT_IDS):
        _add(checks, "S15P02-INTEGRATION-CASES-AVAILABLE", False, "delivery bundle unavailable")
        return
    outputs: Dict[str, Dict[str, Any]] = {}
    for case in integration_tests["cases"]:
        try:
            result = evaluate_integration_case(manifest, bundle, case)
            expected = case["expected"]
            projection = result["decision_projection"]
            if projection.get("status") != expected.get("status") or projection.get("reason_codes") != expected.get("reason_codes"):
                raise SourceContractIntegrationError("integration projection differs from frozen case")
            if any(
                projection.get(key) is not False
                for key in (
                    "external_network_accessed", "gmail_account_or_api_accessed", "tab_or_provider_runtime_accessed",
                    "recommendation_generated", "order_submission_enabled", "actual_return_claimed", "external_state_changed", "real_time_soak_waited",
                )
            ) or projection.get("incremental_cash_spent_aud") != "0.00":
                raise SourceContractIntegrationError("external-effect boundary changed")
            outputs[str(case["case_id"])] = result
            _add(checks, "S15P02-CASE-%s" % case["case_id"], True, projection["status"])
        except Exception as exc:
            label = case.get("case_id") if isinstance(case, Mapping) else "INVALID"
            _add(checks, "S15P02-CASE-%s" % label, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        baseline_id = fixture["expected_outage_equivalence"]["baseline_case_id"]
        outage_id = fixture["expected_outage_equivalence"]["outage_case_id"]
        equivalent = (
            outputs[baseline_id]["decision_projection"] == outputs[outage_id]["decision_projection"]
            and outputs[baseline_id]["decision_projection_sha256"] == outputs[outage_id]["decision_projection_sha256"]
            and outputs[baseline_id]["network_probe_performed"] is False
            and outputs[outage_id]["network_probe_performed"] is False
            and outputs[outage_id]["real_network_outage_exercised"] is False
        )
        _add(checks, "S15P02-SIMULATED-NETWORK-UNAVAILABLE-DETERMINISTIC-PROJECTION", equivalent, {"baseline": baseline_id, "outage": outage_id})
    except Exception as exc:
        _add(checks, "S15P02-SIMULATED-NETWORK-UNAVAILABLE-DETERMINISTIC-PROJECTION", False, "%s: %s" % (type(exc).__name__, exc))


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
        passed = not imports.intersection(forbidden) and all(token not in source for token in forbidden_tokens)
        _add(checks, "S15P02-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", passed, {"imports": sorted(imports), "forbidden": sorted(imports.intersection(forbidden))})
    except Exception as exc:
        _add(checks, "S15P02-ORACLE-LOCAL-ONLY-STATIC-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
    if not suites:
        raise SourceContractIntegrationError("JUnit has no testsuite")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    normalized = True
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
        normalized = normalized and suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000"
        normalized = normalized and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
    return summary, normalized


def _check_reports(root: Path, fixture: Mapping[str, Any] | None, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        _add(checks, "S15P02-TARGETED-REPORTS-REQUIRED", True, "preflight mode")
        return
    try:
        summary, normalized = _junit_summary(root / JUNIT_PATH)
        minimum = fixture.get("minimum_targeted_pytest_cases") if isinstance(fixture, Mapping) else None
        passed = isinstance(minimum, int) and summary["tests"] >= minimum and not summary["failures"] and not summary["errors"] and not summary["skipped"] and normalized
        _add(checks, "S15P02-TARGETED-PYTEST-REPORT-PASS", passed, summary)
    except Exception as exc:
        _add(checks, "S15P02-TARGETED-PYTEST-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S15P02-PAID-DEPENDENCY-REPORT-PASS", all(item in report for item in required), SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S15P02-PAID-DEPENDENCY-REPORT-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S15P02-TASKPACK-REPORT-STRICT-JSON")
    _add(checks, "S15P02-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "S15_P02_LOCAL_SOURCE_CONTRACT_INTEGRATION_READY_P03_REQUIRED" if passed else "S15/P02_BLOCKED",
        "next": "S15/P03_READY_NOT_STARTED" if passed else "S15/P02_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": sum(item["passed"] for item in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "network_outage_claim_boundary": {
            "simulated_network_unavailable_tested": True,
            "real_network_outage_exercised": False,
            "external_network_accessed": False,
        },
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    _, integration_tests, manifest, fixture, bundle = _load_delivery_bundle(root, checks, hashes)
    _check_integration_cases(integration_tests, manifest, fixture, bundle, checks)
    _check_static_boundary(root, checks)
    _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = [CONTRACT_TESTS_PATH, INTEGRATION_TESTS_PATH, FIXTURES_MANIFEST_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH, *[spec["fixture_path"] for spec in SOURCE_SPECS]]
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING", "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(value["status"] == "PASS" for value in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S15_P02_LOCAL_SOURCE_CONTRACT_HARNESS_KEEP_SIGNED_S15_P01",
        "feature_flag_id": FEATURE_FLAG_ID,
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "actual_return_claimed": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        ORACLE_PATH, CONTRACT_TESTS_PATH, INTEGRATION_TESTS_PATH, FIXTURES_MANIFEST_PATH, TEST_PATH, FIXTURE_PATH,
        *[spec["fixture_path"] for spec in SOURCE_SPECS], *[Path(path) for path in BASELINE_HASHES], P01_EVIDENCE_PATH, P01_ROLLBACK_PATH,
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _canonical_sha256({"contract_id": evidence.get("contract_id"), "decision": evidence.get("decision"), "next": evidence.get("next"), "status": evidence.get("status"), "validation": evidence.get("validation")})


def build_evidence(root: Path, require_test_reports: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S15-P02",
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
        "execution_policy": dict(EXECUTION_POLICY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "network_outage_claim_boundary": dict(validation["network_outage_claim_boundary"]),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S15_P02_LOCAL_EVIDENCE_ONLY_P03_REQUIRED",
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S15/P02_test.py --junitxml=machine/evidence/S15/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S15/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S15/P02/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S15-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {
            "integration_case_count": len(EXPECTED_CASE_IDS),
            "outage_mode": "SIMULATED_NETWORK_UNAVAILABLE",
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
        raise SourceContractIntegrationError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S15/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    if sum(row.get("id") == replacement["id"] for row in rows) != 1:
        raise SourceContractIntegrationError("S15/P02 evidence-index row must exist exactly once")
    output = [_jsonl_bytes(replacement) if row.get("id") == replacement["id"] else (raw_line + "\n").encode("utf-8") for raw_line, row in zip(raw_lines, rows)]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise SourceContractIntegrationError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise SourceContractIntegrationError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S15/P03_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise SourceContractIntegrationError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S15_P02_LOCAL_SOURCE_CONTRACT_INTEGRATION_READY_P03_REQUIRED"
        and evidence.get("next") == "S15/P03_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("network_outage_claim_boundary") == {"simulated_network_unavailable_tested": True, "real_network_outage_exercised": False, "external_network_accessed": False}
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("feature_flag_id") == FEATURE_FLAG_ID
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("actual_return_claimed") is False
    )
    if not valid:
        raise SourceContractIntegrationError("existing S15/P02 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S15/P03_READY_NOT_STARTED"}


__all__ = [
    "CONTRACT_ID", "CONTRACT_TESTS_PATH", "EXECUTION_POLICY", "EXPECTED_CASE_IDS", "EXTERNAL_EFFECT_BOUNDARY", "FEATURE_FLAG_ID",
    "FIXTURE_PATH", "FIXTURES_MANIFEST_PATH", "INTEGRATION_TESTS_PATH", "NEGATIVE_MUTATION_IDS", "ORACLE_PATH", "SOURCE_CONTRACT_IDS",
    "SourceContractIntegrationError", "TEST_PATH", "evaluate_contract", "evaluate_integration_case", "perform_rollback_drill",
    "validate_candidate_preflight", "validate_source_fixture", "verify_existing_phase_evidence", "write_phase_evidence",
]
