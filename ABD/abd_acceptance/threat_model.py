"""Fail-closed, local-only acceptance oracle for ABD S14/P01.

S14/P01 produces a frozen threat model, trust-boundary catalog, and abuse-case
catalog.  It deliberately does not contact a market, mailbox, account, OVH,
Cloudflare, or any deployment target, and it cannot enable an external action.
The artifacts are a local control contract, not proof of production security.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S14-P01"
REQUIREMENT_ID = "REQ-S14-P01"
STAGE_ID = "S14"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

THREAT_MODEL_PATH = Path("threat_model.json")
TRUST_BOUNDARIES_PATH = Path("trust_boundaries.json")
ABUSE_CASES_PATH = Path("abuse_cases.json")
ORACLE_PATH = Path("abd_acceptance/threat_model.py")
TEST_PATH = Path("tests/S14/P01_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S14_P01.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S14/P01/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S14/P01/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
ROADMAP_PATH = Path("machine/facts/roadmap.json")

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
EXECUTION_POLICY = {
    "offline_deterministic_only": True,
    "full_regression_or_real_time_soak_allowed": False,
    "external_runtime_access_allowed": False,
    "phase_test_only": True,
    "incremental_cash_spent_aud": "0.00",
}

THREAT_IDS = (
    "THR-PROMPT-INJECTION",
    "THR-MALICIOUS-ATTACHMENT",
    "THR-CREDENTIAL-EXPOSURE",
    "THR-DATA-POISONING",
    "THR-IDENTITY-MISMATCH",
    "THR-FALSE-EVIDENCE",
    "THR-UNAUTHORIZED-EXTERNAL-ACTION",
)
BOUNDARY_IDS = (
    "BND-UNTRUSTED-CONTENT",
    "BND-ATTACHMENT-QUARANTINE",
    "BND-CREDENTIAL-MATERIAL",
    "BND-SOURCE-INTEGRITY",
    "BND-IDENTITY-BINDING",
    "BND-EVIDENCE-CHAIN",
    "BND-OWNER-EXTERNAL-ACTION",
)
CASE_IDS = tuple("ABUSE-S14-P01-%02d" % number for number in range(1, 8))
CONTROL_GROUPS = ("prevention", "detection", "response", "recovery")
THREAT_FIELDS = {
    "threat_id",
    "category",
    "risk_level",
    "assets",
    "entry_points",
    "prevention_control_ids",
    "detection_control_ids",
    "response_control_ids",
    "recovery_control_ids",
    "local_contract_only",
}
BOUNDARY_FIELDS = {
    "boundary_id",
    "threat_id",
    "trusted_inputs",
    "untrusted_inputs",
    "allowed_actions",
    "prohibited_actions",
    "violation_action",
    "control_ids",
}
CASE_FIELDS = {
    "case_id",
    "threat_id",
    "boundary_id",
    "synthetic_input_id",
    "expected_outcome",
    "prevention_control_id",
    "detection_control_id",
    "response_control_id",
    "recovery_control_id",
}
THREAT_HEADER_FIELDS = {
    "schema_version",
    "threat_model_id",
    "contract_id",
    "requirement_id",
    "stage_id",
    "phase_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "high_risk_control_coverage_required",
    "scope_boundary",
    "external_effect_boundary",
    "threats",
}
BOUNDARY_HEADER_FIELDS = {
    "schema_version",
    "boundary_catalog_id",
    "contract_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "boundaries",
}
CASE_HEADER_FIELDS = {
    "schema_version",
    "abuse_case_catalog_id",
    "contract_id",
    "product_version",
    "fixed_clock",
    "execution_mode",
    "cases",
}
SCOPE_BOUNDARY = {
    "product_role": "ANALYSIS_AND_ADVICE_ONLY",
    "owner_final_order_only": True,
    "production_enforcement_verified": False,
    "real_account_or_market_accessed": False,
}
DEPENDENCY_SPECS = (
    {
        "label": "S04/P04",
        "evidence_path": "machine/evidence/EVD-S04-P04.json",
        "rollback_path": "machine/evidence/EVD-S04-P04_rollback.json",
        "evidence_sha256": "cc5c845238614bdb7c1fb3ad5706363453ec84880c6cf44430ffef3f9d23bb69",
        "rollback_sha256": "a60e512777101405ee60e21de0bce4c20eccd24035ec71995084802c68d7ebbf",
        "index_id": "INDEX-AC-S04-P04",
        "contract_id": "AC-S04-P04",
        "requirement_id": "REQ-S04-P04",
        "evidence_id": "EVD-S04-P04",
    },
    {
        "label": "S06/P04",
        "evidence_path": "machine/evidence/EVD-S06-P04.json",
        "rollback_path": "machine/evidence/EVD-S06-P04_rollback.json",
        "evidence_sha256": "2530864a43e7b4d2a2a55ccdbbe4a218a77a11b52438ab49ea9c2664f1f60aea",
        "rollback_sha256": "a54bfe27ffac5efad8fab4683a4a389239939e8fdbdf43fc75fef489c04fc579",
        "index_id": "INDEX-AC-S06-P04",
        "contract_id": "AC-S06-P04",
        "requirement_id": "REQ-S06-P04",
        "evidence_id": "EVD-S06-P04",
    },
    {
        "label": "S07/P04",
        "evidence_path": "machine/evidence/EVD-S07-P04.json",
        "rollback_path": "machine/evidence/EVD-S07-P04_rollback.json",
        "evidence_sha256": "a2fa2f72c069050ed7045f7e7c3cbe5928664bee4e91d1307169b19d466a6fa6",
        "rollback_sha256": "ad483c1e873985c14e5c70d67fb18c2801d9033bf8ed435ca9b149e8bb82054a",
        "index_id": "INDEX-AC-S07-P04",
        "contract_id": "AC-S07-P04",
        "requirement_id": "REQ-S07-P04",
        "evidence_id": "EVD-S07-P04",
    },
)
_SUM_LINE_RE = re.compile(r"^([a-f0-9]{64})  (.+)$")
_LOCAL_PATH_FRAGMENTS = ("/" + "Users/", "file" + "://")


class ThreatModelAcceptanceError(ValueError):
    """Raised when S14/P01 does not remain deterministic and fail-closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _portable(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_portable(item) for item in value)
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return not normalized.startswith("/") and not any(fragment in normalized for fragment in _LOCAL_PATH_FRAGMENTS)
    return True


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise ThreatModelAcceptanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise ThreatModelAcceptanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    if not rows:
        raise ThreatModelAcceptanceError("evidence index is empty")
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ThreatModelAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ThreatModelAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _nonempty_ids(value: Any, pattern: str, field: str) -> List[str]:
    if not isinstance(value, list) or not value or len(value) != len(set(value)):
        raise ThreatModelAcceptanceError("%s must be a non-empty unique list" % field)
    if not all(isinstance(item, str) and re.fullmatch(pattern, item) for item in value):
        raise ThreatModelAcceptanceError("%s contains an invalid identifier" % field)
    return list(value)


def _coverage_decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"[01]\.\d{4}", value) is None:
        raise ThreatModelAcceptanceError("coverage_score must be four-place decimal text")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ThreatModelAcceptanceError("coverage_score is not decimal") from exc


def _control_map(threat: Mapping[str, Any]) -> Dict[str, List[str]]:
    return {group: list(threat[group + "_control_ids"]) for group in CONTROL_GROUPS}


def validate_threat_model(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != THREAT_HEADER_FIELDS or _contains_float(value):
        raise ThreatModelAcceptanceError("threat model fields are not closed")
    header_ok = (
        value.get("schema_version") == "1.0.0"
        and value.get("threat_model_id") == "S14-P01-THREAT-MODEL"
        and value.get("contract_id") == CONTRACT_ID
        and value.get("requirement_id") == REQUIREMENT_ID
        and value.get("stage_id") == STAGE_ID
        and value.get("phase_id") == PHASE_ID
        and value.get("product_version") == VERSION
        and value.get("fixed_clock") == FIXED_CLOCK
        and value.get("execution_mode") == "FROZEN_SYNTHETIC_LOCAL_CONTRACT_ONLY"
        and value.get("high_risk_control_coverage_required") == "1.0000"
        and value.get("scope_boundary") == SCOPE_BOUNDARY
        and value.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
    )
    if not header_ok:
        raise ThreatModelAcceptanceError("threat model header is not frozen")
    rows = value.get("threats")
    if not isinstance(rows, list) or len(rows) != len(THREAT_IDS):
        raise ThreatModelAcceptanceError("threat model must contain exactly seven high threats")
    normalized: List[Dict[str, Any]] = []
    for expected_id, row in zip(THREAT_IDS, rows):
        if not isinstance(row, Mapping) or set(row) != THREAT_FIELDS:
            raise ThreatModelAcceptanceError("threat fields are not closed")
        if row.get("threat_id") != expected_id or row.get("risk_level") != "HIGH" or row.get("local_contract_only") is not True:
            raise ThreatModelAcceptanceError("threat identity or severity is not frozen")
        category = row.get("category")
        if not isinstance(category, str) or re.fullmatch(r"[A-Z_]{3,64}", category) is None:
            raise ThreatModelAcceptanceError("threat category is invalid")
        assets = _nonempty_ids(row.get("assets"), r"[a-z_]{3,96}", "assets")
        entry_points = _nonempty_ids(row.get("entry_points"), r"[a-z_]{3,96}", "entry_points")
        controls: Dict[str, List[str]] = {}
        for group in CONTROL_GROUPS:
            controls[group] = _nonempty_ids(row.get(group + "_control_ids"), r"CTRL-[A-Z0-9-]{3,96}", group + " controls")
        flattened = [item for values in controls.values() for item in values]
        if len(flattened) != len(set(flattened)):
            raise ThreatModelAcceptanceError("one threat may not reuse a control across control groups")
        normalized.append(
            {
                "threat_id": expected_id,
                "category": category,
                "risk_level": "HIGH",
                "assets": assets,
                "entry_points": entry_points,
                **{group + "_control_ids": controls[group] for group in CONTROL_GROUPS},
                "local_contract_only": True,
            }
        )
    return {
        "schema_version": "1.0.0",
        "threat_model_id": "S14-P01-THREAT-MODEL",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "FROZEN_SYNTHETIC_LOCAL_CONTRACT_ONLY",
        "high_risk_control_coverage_required": "1.0000",
        "scope_boundary": dict(SCOPE_BOUNDARY),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "threats": normalized,
    }


def validate_trust_boundaries(value: Any, threats: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != BOUNDARY_HEADER_FIELDS or _contains_float(value):
        raise ThreatModelAcceptanceError("trust-boundary fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("boundary_catalog_id") != "S14-P01-TRUST-BOUNDARIES"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("execution_mode") != "FROZEN_SYNTHETIC_LOCAL_CONTRACT_ONLY"
    ):
        raise ThreatModelAcceptanceError("trust-boundary header is not frozen")
    rows = value.get("boundaries")
    if not isinstance(rows, list) or len(rows) != len(BOUNDARY_IDS):
        raise ThreatModelAcceptanceError("trust-boundary catalog must contain exactly seven boundaries")
    threat_map = {item["threat_id"]: item for item in threats}
    normalized: List[Dict[str, Any]] = []
    for expected_boundary, expected_threat, row in zip(BOUNDARY_IDS, THREAT_IDS, rows):
        if not isinstance(row, Mapping) or set(row) != BOUNDARY_FIELDS:
            raise ThreatModelAcceptanceError("boundary fields are not closed")
        if row.get("boundary_id") != expected_boundary or row.get("threat_id") != expected_threat:
            raise ThreatModelAcceptanceError("boundary identity is not exact")
        lists = {
            name: _nonempty_ids(row.get(name), r"[A-Z_a-z]{3,128}", name)
            for name in ("trusted_inputs", "untrusted_inputs", "allowed_actions", "prohibited_actions")
        }
        violation = row.get("violation_action")
        if not isinstance(violation, str) or re.fullmatch(r"[A-Z_]{3,128}", violation) is None:
            raise ThreatModelAcceptanceError("boundary violation action is invalid")
        control_ids = _nonempty_ids(row.get("control_ids"), r"CTRL-[A-Z0-9-]{3,96}", "boundary controls")
        expected_controls = [item for values in _control_map(threat_map[expected_threat]).values() for item in values]
        if control_ids != expected_controls:
            raise ThreatModelAcceptanceError("boundary controls do not bind all threat controls")
        normalized.append(
            {
                "boundary_id": expected_boundary,
                "threat_id": expected_threat,
                **lists,
                "violation_action": violation,
                "control_ids": control_ids,
            }
        )
    return {
        "schema_version": "1.0.0",
        "boundary_catalog_id": "S14-P01-TRUST-BOUNDARIES",
        "contract_id": CONTRACT_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "FROZEN_SYNTHETIC_LOCAL_CONTRACT_ONLY",
        "boundaries": normalized,
    }


def validate_abuse_cases(value: Any, threats: Sequence[Mapping[str, Any]], boundaries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != CASE_HEADER_FIELDS or _contains_float(value):
        raise ThreatModelAcceptanceError("abuse-case fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("abuse_case_catalog_id") != "S14-P01-ABUSE-CASES"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("execution_mode") != "FROZEN_SYNTHETIC_LOCAL_CONTRACT_ONLY"
    ):
        raise ThreatModelAcceptanceError("abuse-case header is not frozen")
    rows = value.get("cases")
    if not isinstance(rows, list) or len(rows) != len(CASE_IDS):
        raise ThreatModelAcceptanceError("abuse-case catalog must contain exactly seven cases")
    threat_map = {item["threat_id"]: item for item in threats}
    boundary_map = {item["boundary_id"]: item for item in boundaries}
    normalized: List[Dict[str, Any]] = []
    for expected_case, expected_threat, expected_boundary, row in zip(CASE_IDS, THREAT_IDS, BOUNDARY_IDS, rows):
        if not isinstance(row, Mapping) or set(row) != CASE_FIELDS:
            raise ThreatModelAcceptanceError("abuse-case fields are not closed")
        if row.get("case_id") != expected_case or row.get("threat_id") != expected_threat or row.get("boundary_id") != expected_boundary:
            raise ThreatModelAcceptanceError("abuse-case linkage is not exact")
        synthetic_input = row.get("synthetic_input_id")
        outcome = row.get("expected_outcome")
        if not isinstance(synthetic_input, str) or re.fullmatch(r"FIX-[A-Z-]{3,96}", synthetic_input) is None:
            raise ThreatModelAcceptanceError("abuse-case input is not frozen synthetic data")
        expected_outcomes = {
            "REVOKE_AND_PRESERVE_EVIDENCE_NO_ACTION",
            "KEEP_AND_ALERT_NO_EXECUTION",
            "DISABLE_EXPOSED_CAPABILITY_NO_SECRET_READ",
            "REVOKE_UNVERIFIED_INPUT_NO_ACTION",
            "RED_REVOKE_NO_ACTION",
            "REJECT_CLAIM_AND_PRESERVE_RECORD",
            "DISABLE_AND_PRESERVE_EVIDENCE_NO_ACTION",
        }
        if (
            not isinstance(outcome, str)
            or re.fullmatch(r"[A-Z_]{3,128}", outcome) is None
            or outcome not in expected_outcomes
        ):
            raise ThreatModelAcceptanceError("abuse-case outcome is not fail-closed")
        threat_controls = _control_map(threat_map[expected_threat])
        boundary_controls = set(boundary_map[expected_boundary]["control_ids"])
        controls: Dict[str, str] = {}
        for group in CONTROL_GROUPS:
            control = row.get(group + "_control_id")
            if not isinstance(control, str) or control not in threat_controls[group] or control not in boundary_controls:
                raise ThreatModelAcceptanceError("abuse-case control does not bind its threat and boundary")
            controls[group] = control
        normalized.append(
            {
                "case_id": expected_case,
                "threat_id": expected_threat,
                "boundary_id": expected_boundary,
                "synthetic_input_id": synthetic_input,
                "expected_outcome": outcome,
                **{group + "_control_id": controls[group] for group in CONTROL_GROUPS},
            }
        )
    return {
        "schema_version": "1.0.0",
        "abuse_case_catalog_id": "S14-P01-ABUSE-CASES",
        "contract_id": CONTRACT_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "FROZEN_SYNTHETIC_LOCAL_CONTRACT_ONLY",
        "cases": normalized,
    }


def evaluate_threat_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate one frozen P14 security snapshot without enabling any action."""

    required = {
        "dependency_receipts_current",
        "all_high_threats_controlled",
        "trust_boundaries_closed",
        "abuse_cases_closed",
        "external_effect_boundary_preserved",
        "coverage_score",
        "findings_open",
        "foreign_odds_input_present",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != required:
        raise ThreatModelAcceptanceError("threat snapshot shape is invalid")
    for field in required - {"coverage_score", "findings_open"}:
        if type(snapshot.get(field)) is not bool:
            raise ThreatModelAcceptanceError("%s must be boolean" % field)
    if type(snapshot.get("findings_open")) is not int or snapshot["findings_open"] < 0:
        raise ThreatModelAcceptanceError("findings_open must be a nonnegative integer")
    coverage = _coverage_decimal(snapshot.get("coverage_score"))
    reason_map = (
        ("dependency_receipts_current", "DEPENDENCY_RECEIPTS_NOT_CURRENT"),
        ("all_high_threats_controlled", "HIGH_RISK_THREAT_CONTROL_GAP"),
        ("trust_boundaries_closed", "TRUST_BOUNDARY_NOT_CLOSED"),
        ("abuse_cases_closed", "ABUSE_CASE_COVERAGE_GAP"),
        ("external_effect_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if coverage != Decimal("1.0000"):
        reasons.append("CONTROL_COVERAGE_NOT_EXACT")
    if snapshot["findings_open"] != 0:
        reasons.append("OPEN_SECURITY_FINDINGS")
    if snapshot["foreign_odds_input_present"] is True:
        reasons.append("FOREIGN_ODDS_INPUT_REJECTED")
    result: Dict[str, Any] = {
        "status": "S14P01_THREAT_MODEL_VERIFIED_NO_ACTION" if not reasons else "S14P01_THREAT_MODEL_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    result = True
    for relative, expected in BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
            hashes[relative] = actual
            passed = actual == expected
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            passed = False
        _add(checks, "S14P01-BASELINE-%s" % Path(relative).name.upper().replace(".", "-"), passed, {"expected": expected, "actual": actual})
        result = result and passed
    return result


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S14P01-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S14P01-CONTRACTS-PARSE")
    graph_document = _safe_load(root, TASK_GRAPH_PATH, checks, "S14P01-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S14P01-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S14P01-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
    except Exception as exc:
        index = []
        _add(checks, "S14P01-EVIDENCE-INDEX-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
    tasks = graph_document.get("tasks") if isinstance(graph_document, Mapping) else None
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        task_rows = [row for row in tasks if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        task_map = {row.get("id"): row for row in task_rows}
        index_row = _row(index, "INDEX-" + CONTRACT_ID)
        non_goals = [
            "不自动提交、确认或重试真实订单",
            "不以降低证据或风险门追赶30%月目标",
            "不引入付费数据或付费程序接口依赖",
        ]
        expected_test_ids = ["TEST-S14-P01", "TEST-S14-P01-BOUNDARY", "TEST-S14-P01-REPLAY"]
        task_ids = ["T-S14-P01-01", "T-S14-P01-02", "T-S14-P01-03"]
        planned_index = {
            "acceptance_contract_id": CONTRACT_ID,
            "expected_artifact": EVIDENCE_PATH.as_posix(),
            "id": "INDEX-" + CONTRACT_ID,
            "kind": "ACCEPTANCE_EVIDENCE",
            "pass_gate": "高风险威胁均有预防、检测、响应和恢复控制。",
            "requirement_id": REQUIREMENT_ID,
            "status": "PLANNED",
        }
        signed_index_shape = (
            set(index_row) == {"id", "kind", "stage_id", "contract_id", "requirement_id", "status", "actual_artifact", "artifact_sha256", "next", "verified_at"}
            and index_row.get("id") == "INDEX-" + CONTRACT_ID
            and index_row.get("kind") == "PHASE_EVIDENCE"
            and index_row.get("stage_id") == STAGE_ID
            and index_row.get("contract_id") == CONTRACT_ID
            and index_row.get("requirement_id") == REQUIREMENT_ID
            and index_row.get("status") == "PASS"
            and index_row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and index_row.get("next") == "S14/P02_READY_NOT_STARTED"
            and index_row.get("verified_at") == FIXED_CLOCK
            and isinstance(index_row.get("artifact_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", index_row["artifact_sha256"]) is not None
        )
        exact = (
            requirement.get("stage_id") == STAGE_ID
            and requirement.get("phase_id") == PHASE_ID
            and requirement.get("scope") == [THREAT_MODEL_PATH.as_posix(), TRUST_BOUNDARIES_PATH.as_posix(), ABUSE_CASES_PATH.as_posix()]
            and requirement.get("target") == "高风险威胁均有预防、检测、响应和恢复控制。"
            and requirement.get("non_goals") == non_goals
            and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("pass_gate") == requirement.get("target")
            and contract.get("threshold") == requirement.get("target")
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract %s --evidence machine/evidence" % CONTRACT_ID
            and [item.get("id") for item in contract.get("tests", [])] == expected_test_ids
            and [row.get("id") for row in task_rows] == task_ids
            and task_map[task_ids[0]].get("outputs") == [THREAT_MODEL_PATH.as_posix(), TRUST_BOUNDARIES_PATH.as_posix(), ABUSE_CASES_PATH.as_posix()]
            and task_map[task_ids[0]].get("depends_on") == ["T-S04-P04-03", "T-S06-P04-03", "T-S07-P04-03"]
            and task_map[task_ids[1]].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and task_map[task_ids[1]].get("depends_on") == [task_ids[0]]
            and task_map[task_ids[2]].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and task_map[task_ids[2]].get("depends_on") == [task_ids[1]]
            and all(row.get("requirement_ids") == [REQUIREMENT_ID] and row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in task_rows)
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == task_ids
            and trace.get("test_ids") == expected_test_ids
            and trace.get("evidence_id") == "EVD-S14-P01"
            and trace.get("artifact_ids") == ["ART-S14-P01-01", "ART-S14-P01-02", "ART-S14-P01-03"]
            and (index_row == planned_index or signed_index_shape)
        )
        detail: Any = {"task_ids": task_ids, "index_status": index_row.get("status")}
    except Exception as exc:
        exact = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P01-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", exact, detail)
    return exact


def _check_predecessors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    except Exception:
        index = []
    results: Dict[str, bool] = {}
    for spec in DEPENDENCY_SPECS:
        receipt = _safe_load(root, Path(spec["evidence_path"]), checks, "S14P01-%s-EVIDENCE-PARSE" % spec["label"].replace("/", ""))
        rollback = _safe_load(root, Path(spec["rollback_path"]), checks, "S14P01-%s-ROLLBACK-PARSE" % spec["label"].replace("/", ""))
        try:
            index_row = _row(index, spec["index_id"])
            receipt_ok = (
                isinstance(receipt, Mapping)
                and receipt.get("evidence_id") == spec["evidence_id"]
                and receipt.get("contract_id") == spec["contract_id"]
                and receipt.get("requirement_id") == spec["requirement_id"]
                and receipt.get("status") == "PASS"
                and receipt.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
                and receipt.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
                and sha256_file(root / spec["evidence_path"]) == spec["evidence_sha256"]
                and index_row.get("id") == spec["index_id"]
                and index_row.get("status") == "PASS"
                and index_row.get("actual_artifact") == spec["evidence_path"]
                and index_row.get("artifact_sha256") == spec["evidence_sha256"]
            )
            rollback_ok = (
                isinstance(rollback, Mapping)
                and rollback.get("evidence_id") == spec["evidence_id"] + "-ROLLBACK"
                and rollback.get("contract_id") == spec["contract_id"]
                and rollback.get("status") == "PASS"
                and sha256_file(root / spec["rollback_path"]) == spec["rollback_sha256"]
            )
            boundary = receipt.get("external_effect_boundary") if isinstance(receipt, Mapping) else None
            local_only = isinstance(boundary, Mapping) and boundary.get("incremental_cash_spent_aud") == "0.00"
        except Exception as exc:
            receipt_ok = rollback_ok = local_only = False
            index_row = "%s: %s" % (type(exc).__name__, exc)
        passed = receipt_ok and rollback_ok and local_only
        _add(checks, "S14P01-%s-SIGNED-DEPENDENCY-EXACT" % spec["label"].replace("/", ""), passed, index_row)
        results[spec["label"]] = passed
        for key in ("evidence_path", "rollback_path"):
            candidate = root / spec[key]
            if candidate.is_file():
                hashes[spec[key]] = sha256_file(candidate)
    all_passed = all(results.values()) and len(results) == len(DEPENDENCY_SPECS)
    _add(checks, "S14P01-PREDECESSOR-RECEIPTS-CURRENT", all_passed, results)
    return all_passed


def _check_catalogs(
    threat_model: Any,
    boundaries: Any,
    abuse_cases: Any,
    checks: List[Dict[str, Any]],
) -> Dict[str, bool]:
    try:
        model = validate_threat_model(threat_model)
        _add(checks, "S14P01-HIGH-THREAT-MODEL-EXACT", True, [item["threat_id"] for item in model["threats"]])
    except Exception as exc:
        model = None
        _add(checks, "S14P01-HIGH-THREAT-MODEL-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        boundary_catalog = validate_trust_boundaries(boundaries, model["threats"] if isinstance(model, Mapping) else [])
        _add(checks, "S14P01-TRUST-BOUNDARIES-EXACT", True, [item["boundary_id"] for item in boundary_catalog["boundaries"]])
    except Exception as exc:
        boundary_catalog = None
        _add(checks, "S14P01-TRUST-BOUNDARIES-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        case_catalog = validate_abuse_cases(
            abuse_cases,
            model["threats"] if isinstance(model, Mapping) else [],
            boundary_catalog["boundaries"] if isinstance(boundary_catalog, Mapping) else [],
        )
        _add(checks, "S14P01-ABUSE-CASES-EXACT", True, [item["case_id"] for item in case_catalog["cases"]])
    except Exception as exc:
        case_catalog = None
        _add(checks, "S14P01-ABUSE-CASES-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    coverage = isinstance(model, Mapping) and isinstance(boundary_catalog, Mapping) and isinstance(case_catalog, Mapping)
    _add(checks, "S14P01-EVERY-HIGH-THREAT-HAS-PREVENT-DETECT-RESPOND-RECOVER", coverage, {"threat_count": len(model["threats"]) if isinstance(model, Mapping) else 0, "case_count": len(case_catalog["cases"]) if isinstance(case_catalog, Mapping) else 0})
    return {"model": isinstance(model, Mapping), "boundaries": isinstance(boundary_catalog, Mapping), "abuse": isinstance(case_catalog, Mapping), "coverage": coverage}


def _check_fixture(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    if not isinstance(fixture, Mapping) or _contains_float(fixture):
        _add(checks, "S14P01-FIXTURE-EXACT", False, "fixture malformed")
        return False
    header_ok = (
        fixture.get("schema_version") == "1.0.0"
        and fixture.get("fixture_id") == "FIX-S14-P01-THREAT-MODEL"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("requirement_id") == REQUIREMENT_ID
        and fixture.get("stage_id") == STAGE_ID
        and fixture.get("phase_id") == PHASE_ID
        and fixture.get("product_version") == VERSION
        and fixture.get("fixed_clock") == FIXED_CLOCK
        and fixture.get("minimum_targeted_pytest_cases") == 22
        and fixture.get("expected_threat_ids") == list(THREAT_IDS)
        and fixture.get("expected_boundary_ids") == list(BOUNDARY_IDS)
        and fixture.get("expected_case_ids") == list(CASE_IDS)
        and fixture.get("expected_next") == "S14/P02_READY_NOT_STARTED"
        and fixture.get("expected_decision") == "THREAT_MODEL_AND_TRUST_BOUNDARIES_READY_SECURITY_REMEDIATION_REQUIRED_BEFORE_PRODUCTION"
        and fixture.get("single_pass_case_count") == 10
    )
    cases = fixture.get("snapshot_cases")
    cases_ok = isinstance(cases, list) and len(cases) == fixture.get("single_pass_case_count") and len({row.get("case_id") for row in cases if isinstance(row, Mapping)}) == len(cases)
    result = header_ok and cases_ok
    _add(checks, "S14P01-FIXTURE-EXACT", result, {"header": header_ok, "cases": cases_ok})
    return result


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    rows = fixture.get("snapshot_cases") if isinstance(fixture, Mapping) else None
    if not isinstance(rows, list):
        _add(checks, "S14P01-SNAPSHOT-CASES", False, "cases unavailable")
        return False
    passed = True
    for row in rows:
        try:
            actual = evaluate_threat_snapshot(row["snapshot"])
            expected = row["expected"]
            case_ok = actual["status"] == expected["status"] and actual["reason_codes"] == expected["reason_codes"]
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            case_ok = False
        identifier = row.get("case_id") if isinstance(row, Mapping) else "MALFORMED"
        _add(checks, "S14P01-CASE-%s" % identifier, case_ok, actual)
        passed = passed and case_ok
    return passed


def _check_external_boundary(threat_model: Any, checks: List[Dict[str, Any]]) -> bool:
    passed = isinstance(threat_model, Mapping) and threat_model.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }
    _add(checks, "S14P01-NO-NETWORK-ACCOUNT-ORDER-DEPLOY-OR-SOAK-BOUNDARY", passed, EXECUTION_POLICY)
    return passed


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> bool:
    try:
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=ORACLE_PATH.as_posix())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "smtp" + "lib", "asyncio", "time", "random", "os"}
        prohibited_literals = {"sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "web" + "hook", "smtp" + "lib"}
        denied = sorted(imports.intersection(prohibited_imports))
        found = sorted(token for token in prohibited_literals if token in source)
        passed = not denied and not found
        detail: Any = {"imports": sorted(imports), "denied": denied, "tokens": found}
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P01-STATIC-NO-NETWORK-PROCESS-SOAK-OR-ORDER-CAPABILITY", passed, detail)
    return passed


def _junit_summary(path: Path) -> Dict[str, int]:
    document = ElementTree.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    if not suites:
        raise ThreatModelAcceptanceError("JUnit contains no suites")
    return {field: sum(int(suite.attrib.get(field, "0")) for suite in suites) for field in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    try:
        document = ElementTree.parse(path).getroot()
    except Exception:
        return False
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    return bool(suites) and all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK for suite in suites)


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    try:
        summary = _junit_summary(root / JUNIT_PATH)
        junit_ok = (
            summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and summary["failures"] == 0
            and summary["errors"] == 0
            and summary["skipped"] == 0
            and _junit_is_normalized(root / JUNIT_PATH)
        )
    except Exception as exc:
        summary = "%s: %s" % (type(exc).__name__, exc)
        junit_ok = False
    _add(checks, "S14P01-TARGETED-PYTEST-REPORT", junit_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(
            line in scan
            for line in (
                "STATUS: PASS",
                "MAX_INCREMENTAL_CASH_AUD: 0.00",
                "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
                "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
                "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
            )
        )
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P01-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        report_summary = report.get("summary") if isinstance(report, Mapping) else None
        pack_ok = (
            isinstance(report, Mapping)
            and report.get("status") == "PASS"
            and isinstance(report_summary, Mapping)
            and report_summary.get("failed") == 0
            and type(report_summary.get("checks")) is int
            and report_summary.get("passed") == report_summary.get("checks")
        )
    except Exception as exc:
        report_summary = None
        pack_ok = False
        report = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P01-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, report_summary if isinstance(report_summary, Mapping) else report)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    passed = not failed
    return {
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "status": "PASS" if passed else "FAIL",
        "decision": "THREAT_MODEL_AND_TRUST_BOUNDARIES_READY_SECURITY_REMEDIATION_REQUIRED_BEFORE_PRODUCTION" if passed else "THREAT_MODEL_OR_TRUST_BOUNDARY_REMEDIATION_REQUIRED",
        "next": "S14/P02_READY_NOT_STARTED" if passed else "S14/P01_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "snapshot": dict(snapshot),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    """Check the frozen S14/P01 delivery state without external effects."""

    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    threat_model = _safe_load(root, THREAT_MODEL_PATH, checks, "S14P01-THREAT-MODEL-PARSE")
    boundaries = _safe_load(root, TRUST_BOUNDARIES_PATH, checks, "S14P01-TRUST-BOUNDARIES-PARSE")
    abuse_cases = _safe_load(root, ABUSE_CASES_PATH, checks, "S14P01-ABUSE-CASES-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S14P01-FIXTURE-PARSE")
    _check_baseline(root, checks, hashes)
    taskpack_ok = _check_taskpack(root, checks)
    predecessors_ok = _check_predecessors(root, checks, hashes)
    catalogs = _check_catalogs(threat_model, boundaries, abuse_cases, checks)
    fixture_ok = _check_fixture(fixture, checks)
    boundary_ok = _check_external_boundary(threat_model, checks)
    portable = all(_portable(item) for item in (threat_model, boundaries, abuse_cases, fixture))
    _add(checks, "S14P01-ARTIFACTS-PORTABLE", portable, "portable" if portable else "local path detected")
    findings_open = 0 if catalogs["coverage"] else 1
    snapshot = {
        "dependency_receipts_current": predecessors_ok,
        "all_high_threats_controlled": catalogs["coverage"],
        "trust_boundaries_closed": catalogs["boundaries"],
        "abuse_cases_closed": catalogs["abuse"],
        "external_effect_boundary_preserved": boundary_ok,
        "coverage_score": "1.0000" if catalogs["coverage"] else "0.9999",
        "findings_open": findings_open,
        "foreign_odds_input_present": False,
    }
    snapshot_result = evaluate_threat_snapshot(snapshot)
    _add(checks, "S14P01-LIVE-SNAPSHOT-NO-ACTION", snapshot_result["status"] == "S14P01_THREAT_MODEL_VERIFIED_NO_ACTION", snapshot_result)
    cases_ok = _check_snapshot_cases(fixture, checks)
    static_ok = _check_static_boundary(root, checks)
    reports_ok = _check_reports(root, fixture if isinstance(fixture, Mapping) else {}, checks, require_test_reports=require_test_reports)
    _add(checks, "S14P01-REPORTS-REQUIRED-WHEN-SIGNING", reports_ok, "required" if require_test_reports else "candidate preflight")
    _add(checks, "S14P01-PHASE-ONLY-NO-FULL-REGRESSION", EXECUTION_POLICY["full_regression_or_real_time_soak_allowed"] is False, EXECUTION_POLICY)
    return _result(checks, hashes, snapshot)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"status": "PASS" if (root / relative).is_file() else "FAIL", "sha256": sha256_file(root / relative) if (root / relative).is_file() else "MISSING"}
        for relative in (THREAT_MODEL_PATH, TRUST_BOUNDARIES_PATH, ABUSE_CASES_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH)
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S14_P01_LOCAL_CONTROL_CONTRACT_PRESERVE_SIGNED_DEPENDENCIES_NO_EXTERNAL_MUTATION",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = set(BASELINE_HASHES)
    paths.update(
        {
            THREAT_MODEL_PATH.as_posix(),
            TRUST_BOUNDARIES_PATH.as_posix(),
            ABUSE_CASES_PATH.as_posix(),
            ORACLE_PATH.as_posix(),
            TEST_PATH.as_posix(),
            FIXTURE_PATH.as_posix(),
        }
    )
    for spec in DEPENDENCY_SPECS:
        paths.add(spec["evidence_path"])
        paths.add(spec["rollback_path"])
    if require_test_reports:
        paths.update({JUNIT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix(), PACK_REPORT_PATH.as_posix()})
    return {relative: sha256_file(root / relative) for relative in sorted(paths)}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = dict(evidence)
    payload.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    snapshot_result = evaluate_threat_snapshot(validation["snapshot"])
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S14-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "release_status": "S14_P01_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED" if validation["status"] == "PASS" else "S14_P01_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "execution_policy": dict(EXECUTION_POLICY),
        "commands": [
            "uv run --frozen --python 3.12 python -m pytest -q tests/S14/P01_test.py --junitxml=machine/evidence/S14/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S14/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S14/P01/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S14-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"threat_count": len(THREAT_IDS), "single_pass_snapshot_count": 10, "real_time_wait_performed": False},
        "stage_snapshot_summary": {"status": snapshot_result["status"], "reason_codes": snapshot_result["reason_codes"]},
        "hashes": {"code": sha256_file(root / ORACLE_PATH), "inputs": _input_hashes(root, require_test_reports=require_test_reports), "rollback_evidence": _sha256_bytes(_json_bytes(rollback))},
        "validation": validation,
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
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
        raise ThreatModelAcceptanceError("evidence index row count is inconsistent")
    replacement = {
        "id": "INDEX-" + CONTRACT_ID,
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S14/P02_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    positions = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) != 1:
        raise ThreatModelAcceptanceError("S14/P01 evidence-index row must exist exactly once")
    position = positions[0]
    expected_planned = {
        "acceptance_contract_id": CONTRACT_ID,
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "id": replacement["id"],
        "kind": "ACCEPTANCE_EVIDENCE",
        "pass_gate": "高风险威胁均有预防、检测、响应和恢复控制。",
        "requirement_id": REQUIREMENT_ID,
        "status": "PLANNED",
    }
    existing = rows[position]
    if existing != expected_planned and not (
        isinstance(existing, Mapping)
        and existing.get("kind") == "PHASE_EVIDENCE"
        and existing.get("contract_id") == CONTRACT_ID
        and existing.get("status") == "PASS"
    ):
        raise ThreatModelAcceptanceError("S14/P01 evidence-index row is not the planned or current phase record")
    output = [
        _jsonl_bytes(replacement) if number == position else (line + "\n").encode("utf-8")
        for number, line in enumerate(raw_lines)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ThreatModelAcceptanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ThreatModelAcceptanceError("cannot write evidence for a failed S14/P01 phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/P02_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-" + CONTRACT_ID)
    except Exception as exc:
        raise ThreatModelAcceptanceError("existing S14/P01 evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S14-P01"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("requirement_id") == REQUIREMENT_ID
        and evidence.get("stage_id") == STAGE_ID
        and evidence.get("phase_id") == PHASE_ID
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "THREAT_MODEL_AND_TRUST_BOUNDARIES_READY_SECURITY_REMEDIATION_REQUIRED_BEFORE_PRODUCTION"
        and evidence.get("next") == "S14/P02_READY_NOT_STARTED"
        and evidence.get("release_status") == "S14_P01_LOCAL_EVIDENCE_ONLY_REMAINING_PHASES_AND_STAGE_REVIEW_REQUIRED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("hashes", {}).get("code") == sha256_file(root / ORACLE_PATH)
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("order_submission_enabled") is False
        and rollback.get("real_time_soak_waited") is False
        and index == {
            "id": "INDEX-" + CONTRACT_ID,
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "status": "PASS",
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": sha256_file(root / EVIDENCE_PATH),
            "next": "S14/P02_READY_NOT_STARTED",
            "verified_at": FIXED_CLOCK,
        }
    )
    if not valid:
        raise ThreatModelAcceptanceError("existing S14/P01 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S14/P02_READY_NOT_STARTED",
    }


__all__ = [
    "ABUSE_CASES_PATH",
    "BASELINE_HASHES",
    "BOUNDARY_IDS",
    "CONTRACT_ID",
    "DEPENDENCY_SPECS",
    "EXECUTION_POLICY",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "ORACLE_PATH",
    "THREAT_IDS",
    "THREAT_MODEL_PATH",
    "ThreatModelAcceptanceError",
    "TRUST_BOUNDARIES_PATH",
    "evaluate_contract",
    "evaluate_threat_snapshot",
    "perform_rollback_drill",
    "validate_abuse_cases",
    "validate_candidate_preflight",
    "validate_threat_model",
    "validate_trust_boundaries",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
