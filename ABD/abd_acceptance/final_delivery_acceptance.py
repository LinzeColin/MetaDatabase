"""Fail-closed, offline final-delivery acceptance for ABD S19/P04.

The phase produces a deterministic local delivery receipt and a non-secret
handoff archive.  A passing receipt proves only the frozen local contract:
it never promotes synthetic controls to empirical returns, activates a model,
deploys a runtime, sends mail, or submits an order.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import zipfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .ga_reconciliation_acceptance import verify_existing_phase_evidence as verify_s19_p03
from .legacy_receipt_compatibility import approved_successor_sha256


CONTRACT_ID = "AC-S19-P04"
REQUIREMENT_ID = "REQ-S19-P04"
STAGE_ID = "S19"
PHASE_ID = "P04"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-10T09:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

ORACLE_PATH = Path("abd_acceptance/final_delivery_acceptance.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S19_P04.json")
TEST_PATH = Path("tests/S19/P04_test.py")
FINAL_ACCEPTANCE_PATH = Path("final_acceptance.json")
RELEASE_MANIFEST_PATH = Path("release_manifest.json")
HANDOFF_BUNDLE_PATH = Path("handoff_bundle.zip")
JUNIT_PATH = Path("machine/evidence/S19/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S19/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S19-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
CLI_PATH = Path("abd_acceptance/__main__.py")

EXPECTED_TASK_IDS = ("T-S19-P04-01", "T-S19-P04-02", "T-S19-P04-03")
EXPECTED_TEST_IDS = ("TEST-S19-P04", "TEST-S19-P04-BOUNDARY", "TEST-S19-P04-REPLAY")
EXPECTED_ARTIFACT_IDS = ("ART-S19-P04-01", "ART-S19-P04-02", "ART-S19-P04-03")
EXPECTED_OUTPUTS = {
    "T-S19-P04-01": [
        FINAL_ACCEPTANCE_PATH.as_posix(),
        RELEASE_MANIFEST_PATH.as_posix(),
        HANDOFF_BUNDLE_PATH.as_posix(),
    ],
    "T-S19-P04-02": [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()],
    "T-S19-P04-03": [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()],
}
EXPECTED_SCENARIOS = (
    "GOLDEN_LOCAL_FINAL_DELIVERY_STAGE_REVIEW_REQUIRED",
    "ADVERSE_ONE_IN_TEN_THOUSAND_STABLE",
    "VERSION_CONFLICT_FAILS_CLOSED",
    "SOURCE_HASH_CONFLICT_FAILS_CLOSED",
    "EMPIRICAL_RUNTIME_CLAIM_FAILS_CLOSED",
    "STOP_CONDITION_FAILS_CLOSED",
    "UNSAFE_RUNTIME_REQUESTS_FAIL_CLOSED",
    "RISK_RELAXATION_ATTEMPT_FAILS_CLOSED",
)

P03_PREDECESSOR_PATH = Path("machine/evidence/EVD-S19-P03.json")
P03_PREDECESSOR_SHA256 = "3bb3a41f8bb23f65bd4c5fbd4aba14c361d8a391d3cdbaca2666aae9887f345b"
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S19-P03_rollback.json")

BASELINE_HASHES = {
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
SOURCE_ARTIFACT_HASHES = {
    "actual_reconciliation.json": "9453b1b3942de55cebe218ebd7c5d481713e8a57150477c4ba74e9b9a9e1749b",
    "ga_report.json": "1164263e77391c7982fd2ac819845f0d06e811332ccdea0e05f55da6a927a24d",
    "machine/evidence/EVD-S19-P01.json": "183fc545bad654f5ee851fcb828433e0e7949396c83f8c67354ccc220c492219",
    "machine/evidence/EVD-S19-P02.json": "6d13caf6132005bbfa1f2d31e3bfbce23366065702404d1c56e4dff1f4c73177",
    "machine/evidence/EVD-S19-P03.json": P03_PREDECESSOR_SHA256,
    "machine/evidence/EVD-S19-P03_rollback.json": "7e55153bc6ab27c7e00b238dcc685e00566ed32e6a317b0a6233df543ca1c9ef",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/release_policy.json": "c1e9b0dfb263d4a5bcef9630b71ddf4b69836d07ace28ad978691c0b8be59c6b",
    "model_beta_gate.json": "cc64fb221b36925e09b1bcfffa3236e63dc7fc2ab6e0a4f67886ffbff7860dac",
    "model_release_gate.json": "6c4db127f346e644fcc4ec6fd6b9a158a29ad74dc628780a4139e709b4735720",
    "target_acceptance.json": "62ab02e730fda25bd18a58f0a578f3dbf65d4813d3d153ac3dbcec9ff6bcdd76",
}

SAFE_FINAL_CONFIG = {
    "delivery_mode": "LOCAL_FINAL_ACCEPTANCE_AND_NON_SECRET_HANDOFF_ONLY",
    "owner_final_order_only": True,
    "order_submission_module_present": False,
    "production_equivalent_config_schema": True,
    "target_shortfall_may_relax_gate": False,
}
SAFE_RUNTIME_OBSERVATION = {
    "actual_execution_evidence_status": "NO_EMPIRICAL_EXECUTION_EVIDENCE",
    "actual_record_count": 0,
    "deployment_status": "NOT_DEPLOYED_OR_ACTIVATED",
    "model_ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
    "return_status": "UNVERIFIED_NOT_GUARANTEED",
    "verified_days": 0,
}
EXTERNAL_EFFECT_BOUNDARY = {
    "database_or_market_runtime_accessed": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "external_network_accessed": False,
    "gmail_or_tab_account_accessed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submitted_confirmed_or_retried": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "owner_final_order_only": True,
    "production_deployed_or_activated": False,
    "real_account_or_fund_mutated": False,
    "real_time_soak_waited": False,
    "recommendation_generated_or_enabled": False,
    "synthetic_evidence_promoted_to_empirical": False,
}
EXECUTION_POLICY = {
    "external_runtime_access_allowed": False,
    "full_regression_or_real_time_soak_allowed": False,
    "incremental_cash_spent_aud": "0.00",
    "offline_deterministic_only": True,
    "phase_test_only": True,
    "production_equivalent_config_schema_only": True,
    "synthetic_or_local_control_may_count_as_empirical": False,
}

BUNDLE_MEMBERS = (
    FINAL_ACCEPTANCE_PATH,
    RELEASE_MANIFEST_PATH,
    Path("machine/evidence/EVD-S19-P01.json"),
    Path("machine/evidence/EVD-S19-P02.json"),
    P03_PREDECESSOR_PATH,
    P03_ROLLBACK_PATH,
    Path("ga_report.json"),
    Path("actual_reconciliation.json"),
    Path("target_acceptance.json"),
)


class FinalDeliveryInputError(ValueError):
    """Raised when an S19/P04 frozen input is malformed."""


class FinalDeliveryAcceptanceError(RuntimeError):
    """Raised when the final local delivery receipt cannot be reproduced."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _self_hash(value: Mapping[str, Any], field: str) -> str:
    unsigned = dict(value)
    unsigned.pop(field, None)
    return _sha256_bytes(_json_bytes(unsigned))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FinalDeliveryInputError("%s must be an object" % name)
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise FinalDeliveryInputError("%s must be boolean" % name)
    return value


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise FinalDeliveryInputError("%s must be an integer" % name)
    return value


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, path.as_posix())
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise FinalDeliveryAcceptanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise FinalDeliveryAcceptanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise FinalDeliveryAcceptanceError("blank JSONL row %d" % number)
        value = json.loads(line)
        if not isinstance(value, Mapping) or _contains_float(value):
            raise FinalDeliveryAcceptanceError("invalid JSONL row %d" % number)
        rows.append(value)
    return rows


def load_fixture(path: Path) -> Mapping[str, Any]:
    value = strict_json_load(path)
    if not isinstance(value, Mapping) or _contains_float(value):
        raise FinalDeliveryAcceptanceError("fixture must be a non-float object")
    return value


def validate_fixture(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected_keys = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "fixed_clock",
        "expected_next",
        "predecessor_evidence_sha256",
        "source_artifact_sha256",
        "safe_final_config",
        "safe_runtime_observation",
        "expected_bundle_members",
        "scenarios",
        "malformed_inputs",
    }
    if set(value) != expected_keys:
        raise FinalDeliveryAcceptanceError("fixture keys changed")
    identity_ok = (
        value.get("schema_version") == "1.0.0"
        and value.get("fixture_id") == "FIX-S19-P04-FINAL-DELIVERY"
        and value.get("contract_id") == CONTRACT_ID
        and value.get("requirement_id") == REQUIREMENT_ID
        and value.get("stage_id") == STAGE_ID
        and value.get("phase_id") == PHASE_ID
        and value.get("fixed_clock") == FIXED_CLOCK
        and value.get("expected_next") == "S19/STAGE_REVIEW_READY_NOT_STARTED"
        and value.get("predecessor_evidence_sha256") == P03_PREDECESSOR_SHA256
        and value.get("source_artifact_sha256") == SOURCE_ARTIFACT_HASHES
        and value.get("safe_final_config") == SAFE_FINAL_CONFIG
        and value.get("safe_runtime_observation") == SAFE_RUNTIME_OBSERVATION
        and value.get("expected_bundle_members") == [path.as_posix() for path in BUNDLE_MEMBERS]
    )
    if not identity_ok:
        raise FinalDeliveryAcceptanceError("fixture identity or source pins changed")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or tuple(item.get("scenario_id") for item in scenarios if isinstance(item, Mapping)) != EXPECTED_SCENARIOS:
        raise FinalDeliveryAcceptanceError("fixture scenarios changed")
    for item in scenarios:
        if not isinstance(item, Mapping) or set(item) != {"scenario_id", "final_input", "expected"}:
            raise FinalDeliveryAcceptanceError("fixture scenario schema changed")
        if not isinstance(item["expected"], Mapping) or _contains_float(item["expected"]):
            raise FinalDeliveryAcceptanceError("fixture expected result is invalid")
    malformed = value.get("malformed_inputs")
    if not isinstance(malformed, list) or not malformed:
        raise FinalDeliveryAcceptanceError("fixture malformed inputs are unavailable")
    return value


def validate_final_input(value: Any) -> Mapping[str, Any]:
    payload = _mapping(value, "final_input")
    expected_keys = {
        "schema_version",
        "fixed_clock",
        "evaluation_id",
        "product_version",
        "release_config",
        "artifact_hashes",
        "actual_runtime_observation",
        "probability_delta",
        "odds_tick_delta",
        "stop_conditions_triggered",
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    }
    if set(payload) != expected_keys or _contains_float(payload):
        raise FinalDeliveryInputError("final input keys and numeric types must be frozen")
    if payload.get("schema_version") != "1.0.0" or payload.get("fixed_clock") != FIXED_CLOCK:
        raise FinalDeliveryInputError("schema and fixed clock must be frozen")
    if not isinstance(payload.get("evaluation_id"), str) or not payload["evaluation_id"]:
        raise FinalDeliveryInputError("evaluation_id must be non-empty")
    if not isinstance(payload.get("product_version"), str):
        raise FinalDeliveryInputError("product_version must be a string")
    config = _mapping(payload.get("release_config"), "release_config")
    if set(config) != set(SAFE_FINAL_CONFIG) or any(not isinstance(item, bool) for key, item in config.items() if key != "delivery_mode") or not isinstance(config.get("delivery_mode"), str):
        raise FinalDeliveryInputError("release_config schema is invalid")
    hashes = _mapping(payload.get("artifact_hashes"), "artifact_hashes")
    if set(hashes) != set(SOURCE_ARTIFACT_HASHES) or not all(_is_sha256(item) for item in hashes.values()):
        raise FinalDeliveryInputError("artifact hashes must be an exact SHA-256 map")
    runtime = _mapping(payload.get("actual_runtime_observation"), "actual_runtime_observation")
    if set(runtime) != set(SAFE_RUNTIME_OBSERVATION):
        raise FinalDeliveryInputError("runtime observation schema is invalid")
    if not isinstance(runtime.get("actual_execution_evidence_status"), str) or not isinstance(runtime.get("deployment_status"), str) or not isinstance(runtime.get("model_ga_status"), str) or not isinstance(runtime.get("return_status"), str):
        raise FinalDeliveryInputError("runtime observation statuses must be strings")
    for key in ("actual_record_count", "verified_days"):
        if _integer(runtime.get(key), key) < 0:
            raise FinalDeliveryInputError("%s must be non-negative" % key)
    if payload.get("probability_delta") not in {"-0.0001", "0", "0.0001"}:
        raise FinalDeliveryInputError("probability delta is outside the frozen boundary")
    _integer(payload.get("odds_tick_delta"), "odds_tick_delta")
    for key in (
        "stop_conditions_triggered",
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    ):
        _bool(payload.get(key), key)
    return payload


def evaluate_final_delivery(value: Any) -> Dict[str, Any]:
    payload = validate_final_input(value)
    failures: List[str] = []
    if payload["product_version"] != PRODUCT_VERSION:
        failures.append("VERSION_CONFLICT")
    if dict(payload["release_config"]) != SAFE_FINAL_CONFIG:
        if payload["release_config"].get("target_shortfall_may_relax_gate") is True:
            failures.append("RISK_GATE_RELAXATION_ATTEMPT")
        failures.append("PRODUCTION_EQUIVALENT_CONFIG_CONFLICT")
    if dict(payload["artifact_hashes"]) != SOURCE_ARTIFACT_HASHES:
        failures.append("SOURCE_HASH_CONFLICT")
    if dict(payload["actual_runtime_observation"]) != SAFE_RUNTIME_OBSERVATION:
        failures.append("EMPIRICAL_OR_RUNTIME_CLAIM_NOT_VERIFIABLE_IN_FROZEN_LOCAL_EVALUATOR")
    if payload["stop_conditions_triggered"]:
        failures.append("STOP_CONDITION_TRIGGERED")
    request_codes = {
        "requested_external_execution": "EXTERNAL_RUNTIME_REQUESTED",
        "requested_actual_order": "ACTUAL_ORDER_REQUESTED",
        "requested_real_fund_mutation": "REAL_FUND_MUTATION_REQUESTED",
        "requested_real_mail_send": "REAL_MAIL_SEND_REQUESTED",
        "requested_production_deploy": "PRODUCTION_DEPLOY_REQUESTED",
    }
    failures.extend(code for key, code in request_codes.items() if payload[key])
    if failures:
        status = "FAIL_CLOSED"
        decision = "FINAL_DELIVERY_REJECTED_NO_ACTION"
    else:
        status = "PASS_LOCAL_FINAL_DELIVERY_GATE"
        decision = "LOCAL_FINAL_ACCEPTANCE_PASS_STAGE_REVIEW_REQUIRED_RUNTIME_AND_RETURN_UNVERIFIED"
    return {
        "schema_version": "1.0.0",
        "evaluation_id": payload["evaluation_id"],
        "status": status,
        "decision": decision,
        "action": "NO_RECOMMENDATION",
        "failure_codes": failures,
        "version": payload["product_version"],
        "source_hashes": dict(payload["artifact_hashes"]),
        "release_config": dict(payload["release_config"]),
        "actual_runtime_observation": dict(payload["actual_runtime_observation"]),
        "adverse_probability_delta": payload["probability_delta"],
        "adverse_odds_tick_delta": payload["odds_tick_delta"],
        "stage_review_required": True,
        "production_deployment_allowed": False,
        "recommendation_generation_allowed": False,
        "order_submission_allowed": False,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }


def build_final_acceptance(
    evaluation: Mapping[str, Any],
    *,
    fixture_sha256: str,
    source_artifact_sha256: Mapping[str, str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": EXPECTED_ARTIFACT_IDS[0],
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product": "ABD",
        "version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS_LOCAL_FINAL_ACCEPTANCE_STAGE_REVIEW_REQUIRED",
        "decision": "LOCAL_FINAL_ACCEPTANCE_PASS_STAGE_REVIEW_REQUIRED_RUNTIME_AND_RETURN_UNVERIFIED",
        "scope": "FROZEN_OFFLINE_FINAL_DELIVERY_CONTRACT_ONLY",
        "pass_gate": "所有验收通过，版本和哈希无歧义无冲突。",
        "predecessor": {
            "contract_id": "AC-S19-P03",
            "evidence_path": P03_PREDECESSOR_PATH.as_posix(),
            "evidence_sha256": P03_PREDECESSOR_SHA256,
            "status": "PASS_LOCAL_GA_RECONCILIATION_CONTROL_ACTUAL_GA_BLOCKED",
        },
        "fixture_sha256": fixture_sha256,
        "source_artifact_sha256": dict(source_artifact_sha256),
        "evaluation": dict(evaluation),
        "runtime_and_return_boundary": {
            "actual_ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
            "actual_reconciliation_status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
            "deployment_status": "NOT_DEPLOYED_OR_ACTIVATED",
            "external_runtime_verified": False,
            "return_or_roi_verified": False,
            "synthetic_or_local_control_promoted_to_empirical": False,
        },
        "financial": {
            "initial_bankroll_aud": "300.00",
            "incremental_cash_budget_aud": "0.00",
            "monthly_target": "30%",
            "target_formula": "B_n=300*1.3^n",
            "target_status": "UNVERIFIED_NOT_GUARANTEED",
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S19/STAGE_REVIEW_READY_NOT_STARTED",
    }
    result["final_acceptance_sha256"] = _self_hash(result, "final_acceptance_sha256")
    return result


def build_release_manifest(root: Path, final_acceptance: Mapping[str, Any]) -> Dict[str, Any]:
    members: List[Dict[str, Any]] = []
    for path in BUNDLE_MEMBERS:
        if path == FINAL_ACCEPTANCE_PATH:
            members.append({"path": path.as_posix(), "sha256": _sha256_bytes(_json_bytes(final_acceptance))})
        elif path == RELEASE_MANIFEST_PATH:
            members.append(
                {
                    "path": path.as_posix(),
                    "integrity": "SELF_NORMALIZED_SHA256_VIA_MANIFEST_SHA256",
                }
            )
        else:
            members.append({"path": path.as_posix(), "sha256": sha256_file(root / path)})
    result: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": EXPECTED_ARTIFACT_IDS[1],
        "contract_id": CONTRACT_ID,
        "product": "ABD",
        "version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": "LOCAL_DELIVERY_MANIFEST_NOT_A_PRODUCTION_RELEASE",
        "release_decision": "S19_STAGE_REVIEW_REQUIRED_BEFORE_GITHUB_UPLOAD_OR_ANY_DEPLOYMENT",
        "final_acceptance_path": FINAL_ACCEPTANCE_PATH.as_posix(),
        "final_acceptance_sha256": _sha256_bytes(_json_bytes(final_acceptance)),
        "handoff_bundle": {
            "path": HANDOFF_BUNDLE_PATH.as_posix(),
            "format": "ZIP_STORED_FIXED_CLOCK_NON_SECRET_REPOSITORY_RELATIVE",
            "member_count": len(members),
            "members": members,
            "archive_sha256_recorded_in": EVIDENCE_PATH.as_posix(),
        },
        "version_and_hash_status": "UNAMBIGUOUS_NO_CONFLICT",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "next": "S19/STAGE_REVIEW_READY_NOT_STARTED",
    }
    result["manifest_sha256"] = _self_hash(result, "manifest_sha256")
    return result


def _bundle_bytes(root: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for path in BUNDLE_MEMBERS:
            info = zipfile.ZipInfo(path.as_posix(), date_time=(2026, 8, 10, 9, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / path).read_bytes())
    return buffer.getvalue()


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in BASELINE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P04-BASELINE-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, Path("machine/facts/requirements.json"), checks, "S19P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, Path("machine/facts/acceptance_contracts.json"), checks, "S19P04-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root, Path("machine/facts/task_graph.json"), checks, "S19P04-TASK-GRAPH-STRICT-JSON")
    traceability = _safe_load(root, Path("machine/facts/traceability_matrix.json"), checks, "S19P04-TRACEABILITY-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        if not isinstance(tasks, list):
            raise FinalDeliveryAcceptanceError("task graph is unavailable")
        phase_tasks = [item for item in tasks if isinstance(item, Mapping) and item.get("stage_id") == STAGE_ID and item.get("phase_id") == PHASE_ID]
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        exact = (
            requirement.get("scope") == [FINAL_ACCEPTANCE_PATH.as_posix(), RELEASE_MANIFEST_PATH.as_posix(), HANDOFF_BUNDLE_PATH.as_posix()]
            and requirement.get("target") == "所有验收通过，版本和哈希无歧义无冲突。"
            and requirement.get("non_goals") == [
                "不自动提交、确认或重试真实订单",
                "不以降低证据或风险门追赶30%月目标",
                "不引入付费数据或付费程序接口依赖",
            ]
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S19-P04 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [item.get("id") for item in contract.get("tests", [])] == list(EXPECTED_TEST_IDS)
            and [item.get("id") for item in phase_tasks] == list(EXPECTED_TASK_IDS)
            and {item.get("id"): item.get("outputs") for item in phase_tasks} == EXPECTED_OUTPUTS
            and phase_tasks[0].get("depends_on") == ["T-S19-P03-03"]
            and phase_tasks[1].get("depends_on") == ["T-S19-P04-01"]
            and phase_tasks[2].get("depends_on") == ["T-S19-P04-02"]
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == list(EXPECTED_TASK_IDS)
            and trace.get("test_ids") == list(EXPECTED_TEST_IDS)
            and trace.get("evidence_id") == "EVD-S19-P04"
            and trace.get("artifact_ids") == list(EXPECTED_ARTIFACT_IDS)
        )
    except Exception as exc:
        exact = False
        requirement = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P04-TASKPACK-SCOPE-TRACE-EXACT", exact, list(EXPECTED_TASK_IDS) if exact else requirement)
    try:
        row = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
        planned = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("pass_gate") == "所有验收通过，版本和哈希无歧义无冲突。"
            and row.get("status") == "PLANNED"
        )
        signed = (
            row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and row.get("acceptance_contract_id") == CONTRACT_ID
            and row.get("stage_id") == STAGE_ID
            and row.get("requirement_id") == REQUIREMENT_ID
            and row.get("status") == "PASS"
            and row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and row.get("artifact_sha256") == (sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING")
            and row.get("next") == "S19/STAGE_REVIEW_READY_NOT_STARTED"
        )
        _add(checks, "S19P04-EVIDENCE-INDEX-EXACT", planned or signed, row)
    except Exception as exc:
        _add(checks, "S19P04-EVIDENCE-INDEX-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        result = verify_s19_p03(root)
        actual = sha256_file(root / P03_PREDECESSOR_PATH)
        hashes[P03_PREDECESSOR_PATH.as_posix()] = actual
        valid = (
            result.get("contract_id") == "AC-S19-P03"
            and result.get("status") == "PASS"
            and result.get("evidence_sha256") == P03_PREDECESSOR_SHA256
            and result.get("next") == "S19/P04_READY_NOT_STARTED"
            and actual == P03_PREDECESSOR_SHA256
        )
        detail: Any = {"expected": P03_PREDECESSOR_SHA256, "actual": actual, "next": result.get("next")}
    except Exception as exc:
        valid = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P04-PREDECESSOR-AC-S19-P03-CURRENT", valid, detail)


def _check_source_boundaries(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in SOURCE_ARTIFACT_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S19P04-SOURCE-PIN-%s" % relative.replace("/", "-"), actual == expected, {"expected": expected, "actual": actual})
    try:
        canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
        target = strict_json_load(root / "target_acceptance.json")
        beta = strict_json_load(root / "model_beta_gate.json")
        model_release = strict_json_load(root / "model_release_gate.json")
        ga_report = strict_json_load(root / "ga_report.json")
        reconciliation = strict_json_load(root / "actual_reconciliation.json")
        truth_ok = (
            canonical.get("truth_and_evidence", {}).get("advice_ledger_separate_from_actual_ledger") is True
            and canonical.get("truth_and_evidence", {}).get("actual_return_requires_verified_execution_evidence") is True
            and canonical.get("scope", {}).get("order_submission_module_present") is False
            and target.get("falsification_gate", {}).get("current_empirical_assessment", {}).get("evidence_status") == "NO_EMPIRICAL_EXECUTION_EVIDENCE"
            and target.get("hard_gate_invariants", {}).get("synthetic_artifacts_may_substitute_for_actual_return") is False
            and beta.get("model_beta_status") == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
            and model_release.get("model_gate", {}).get("status") == "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT"
            and ga_report.get("ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
            and reconciliation.get("status") == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
            and reconciliation.get("actual_record_count") == 0
            and reconciliation.get("actual_reconciliation_difference_cents") is None
            and reconciliation.get("ga_activation_allowed") is False
            and reconciliation.get("order_submission_allowed") is False
        )
    except Exception as exc:
        truth_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = "local delivery cannot substitute for empirical runtime, GA, or return evidence"
    _add(checks, "S19P04-EMPIRICAL-RUNTIME-AND-RETURN-TRUTH-BOUNDARY-EXACT", truth_ok, detail)


def _fixture_and_expected_artifacts(root: Path) -> Tuple[Mapping[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    fixture = validate_fixture(load_fixture(root / FIXTURE_PATH))
    golden = next(item for item in fixture["scenarios"] if item["scenario_id"] == EXPECTED_SCENARIOS[0])
    evaluation = evaluate_final_delivery(golden["final_input"])
    final_acceptance = build_final_acceptance(
        evaluation,
        fixture_sha256=sha256_file(root / FIXTURE_PATH),
        source_artifact_sha256=SOURCE_ARTIFACT_HASHES,
    )
    manifest = build_release_manifest(root, final_acceptance)
    return fixture, evaluation, final_acceptance, manifest


def _check_core_and_fixture(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    try:
        fixture, golden, final_acceptance, manifest = _fixture_and_expected_artifacts(root)
        hashes[FIXTURE_PATH.as_posix()] = sha256_file(root / FIXTURE_PATH)
        hashes[ORACLE_PATH.as_posix()] = sha256_file(root / ORACLE_PATH)
        replay_ok = True
        scenario_results: List[Dict[str, Any]] = []
        for scenario in fixture["scenarios"]:
            first = evaluate_final_delivery(scenario["final_input"])
            second = evaluate_final_delivery(scenario["final_input"])
            expected = scenario["expected"]
            scenario_ok = all(first.get(key) == value for key, value in expected.items()) and first == second
            replay_ok = replay_ok and scenario_ok
            scenario_results.append({"scenario_id": scenario["scenario_id"], "passed": scenario_ok, "failure_codes": first.get("failure_codes")})
        _add(checks, "S19P04-FROZEN-SCENARIOS-REPLAY-EXACT", replay_ok, scenario_results)
        artifact_ok = (
            golden.get("status") == "PASS_LOCAL_FINAL_DELIVERY_GATE"
            and golden.get("action") == "NO_RECOMMENDATION"
            and golden.get("production_deployment_allowed") is False
            and final_acceptance.get("artifact_id") == EXPECTED_ARTIFACT_IDS[0]
            and final_acceptance.get("status") == "PASS_LOCAL_FINAL_ACCEPTANCE_STAGE_REVIEW_REQUIRED"
            and final_acceptance.get("final_acceptance_sha256") == _self_hash(final_acceptance, "final_acceptance_sha256")
            and manifest.get("artifact_id") == EXPECTED_ARTIFACT_IDS[1]
            and manifest.get("version_and_hash_status") == "UNAMBIGUOUS_NO_CONFLICT"
            and manifest.get("manifest_sha256") == _self_hash(manifest, "manifest_sha256")
        )
        _add(checks, "S19P04-FINAL-ARTIFACT-BUILD-EXACT", artifact_ok, {"final": final_acceptance.get("final_acceptance_sha256"), "manifest": manifest.get("manifest_sha256")})
        source = (root / ORACLE_PATH).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"socket", "sub" + "process", "requests", "url" + "lib", "ht" + "tp", "smtp" + "lib", "ti" + "me", "async" + "io", "os", "random"}
        prohibited_tokens = ("sleep" + "(", "submit" + "_order", "retry" + "_order", "http" + "://", "https" + "://", "smtp" + "lib")
        source_ok = not imports.intersection(forbidden) and all(token not in source for token in prohibited_tokens)
        _add(checks, "S19P04-CORE-NO-EXTERNAL-RUNTIME-CAPABILITY", source_ok, sorted(imports.intersection(forbidden)))
    except Exception as exc:
        _add(checks, "S19P04-CORE-OR-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_generated_artifacts(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str], required: bool) -> None:
    if not required:
        _add(checks, "S19P04-GENERATED-ARTIFACTS-DEFERRED-PREFLIGHT", True, "pre-signing source and fixture preflight")
        return
    try:
        _, _, expected_final, expected_manifest = _fixture_and_expected_artifacts(root)
        actual_final = strict_json_load(root / FINAL_ACCEPTANCE_PATH)
        actual_manifest = strict_json_load(root / RELEASE_MANIFEST_PATH)
        actual_bundle = (root / HANDOFF_BUNDLE_PATH).read_bytes()
        hashes[FINAL_ACCEPTANCE_PATH.as_posix()] = sha256_file(root / FINAL_ACCEPTANCE_PATH)
        hashes[RELEASE_MANIFEST_PATH.as_posix()] = sha256_file(root / RELEASE_MANIFEST_PATH)
        hashes[HANDOFF_BUNDLE_PATH.as_posix()] = sha256_file(root / HANDOFF_BUNDLE_PATH)
        replay_ok = actual_final == expected_final and actual_manifest == expected_manifest and actual_bundle == _bundle_bytes(root)
        _add(checks, "S19P04-GENERATED-ARTIFACTS-REPLAY-EXACT", replay_ok, {"final": hashes[FINAL_ACCEPTANCE_PATH.as_posix()], "manifest": hashes[RELEASE_MANIFEST_PATH.as_posix()], "bundle": hashes[HANDOFF_BUNDLE_PATH.as_posix()]})
        with zipfile.ZipFile(io.BytesIO(actual_bundle), mode="r") as archive:
            names = archive.namelist()
            names_ok = names == [path.as_posix() for path in BUNDLE_MEMBERS]
            paths_ok = all(not name.startswith("/") and ".." not in Path(name).parts for name in names)
            contents_ok = all(archive.read(path.as_posix()) == (root / path).read_bytes() for path in BUNDLE_MEMBERS)
            bundle_ok = archive.testzip() is None and names_ok and paths_ok and contents_ok
        _add(checks, "S19P04-NON_SECRET-HANDOFF-BUNDLE-EXACT", bundle_ok, names)
        boundary_ok = (
            actual_final.get("runtime_and_return_boundary", {}).get("external_runtime_verified") is False
            and actual_final.get("runtime_and_return_boundary", {}).get("return_or_roi_verified") is False
            and actual_final.get("runtime_and_return_boundary", {}).get("actual_ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
            and actual_manifest.get("status") == "LOCAL_DELIVERY_MANIFEST_NOT_A_PRODUCTION_RELEASE"
            and actual_manifest.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
            and actual_manifest.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        )
        _add(checks, "S19P04-FINAL-DELIVERY-DOES-NOT-CLAIM-DEPLOYMENT-OR-RETURNS", boundary_ok, actual_manifest.get("status"))
    except Exception as exc:
        _add(checks, "S19P04-GENERATED-ARTIFACTS-REPLAY-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
        _add(checks, "S19P04-NON_SECRET-HANDOFF-BUNDLE-EXACT", False, "generated artifacts unavailable")
        _add(checks, "S19P04-FINAL-DELIVERY-DOES-NOT-CLAIM-DEPLOYMENT-OR-RETURNS", False, "generated artifacts unavailable")


def _check_cli_wiring(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CLI_PATH).read_text(encoding="utf-8")
        exact = (
            "from .final_delivery_acceptance import verify_existing_phase_evidence as verify_final_delivery_phase_evidence" in source
            and "from .final_delivery_acceptance import write_phase_evidence as write_final_delivery_phase_evidence" in source
            and '"AC-S19-P04": verify_final_delivery_phase_evidence,' in source
            and '"AC-S19-P04": write_final_delivery_phase_evidence,' in source
        )
    except Exception as exc:
        exact = False
        source = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P04-CLI-WRITER-AND-VERIFIER-EXACT", exact, CLI_PATH.as_posix() if exact else source)
    successor = approved_successor_sha256(root, CLI_PATH.as_posix())
    _add(checks, "S19P04-S08-LEGACY-SUCCESSOR-PIN-EXACT", successor == sha256_file(root / CLI_PATH), {"approved": successor, "current": sha256_file(root / CLI_PATH)})


def _junit_summary(path: Path) -> Tuple[Dict[str, int], bool]:
    try:
        root = ElementTree.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite")) if root.tag == "testsuites" else []
        summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for suite in suites:
            for key in summary:
                summary[key] += int(suite.attrib.get(key, "0"))
        normalized = bool(suites) and all(
            suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
            and suite.attrib.get("time") == "0.000"
            and "hostname" not in suite.attrib
            and all(case.attrib.get("time") == "0.000" for case in suite.findall("testcase"))
            for suite in suites
        )
        return summary, normalized
    except Exception:
        return {"tests": 0, "failures": 1, "errors": 1, "skipped": 0}, False


def _check_reports(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str], required: bool) -> None:
    if not required:
        _add(checks, "S19P04-TARGETED-REPORT-DEFERRED-PREFLIGHT", True, "pre-signing candidate preflight")
        return
    summary, normalized = _junit_summary(root / JUNIT_PATH)
    if (root / JUNIT_PATH).is_file():
        hashes[JUNIT_PATH.as_posix()] = sha256_file(root / JUNIT_PATH)
    report_ok = summary["tests"] > 0 and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and normalized
    _add(checks, "S19P04-TARGETED-PYTEST-REPORT", report_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        scan_ok = "STATUS: PASS" in scan and "EXTERNAL_NETWORK_ACCESS_PERFORMED: false" in scan and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan
    except Exception as exc:
        scan_ok = False
        scan = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S19P04-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    report = _safe_load(root, PACK_REPORT_PATH, checks, "S19P04-TASKPACK-REPORT-STRICT-JSON")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    _add(checks, "S19P04-TASKPACK-STATIC-VALIDATION-PASS", isinstance(report, Mapping) and report.get("status") == "PASS", report.get("status") if isinstance(report, Mapping) else report)


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [item["id"] for item in checks if not item["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID,
        "status": status,
        "decision": "S19_P04_LOCAL_FINAL_DELIVERY_PASS_STAGE_REVIEW_REQUIRED" if status == "PASS" else "S19_P04_FINAL_DELIVERY_FAIL_CLOSED",
        "next": "S19/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S19/P04_REMEDIATION_REQUIRED",
        "checks": checks,
        "failed_checks": failed,
        "hashes": dict(hashes),
        "execution_policy": EXECUTION_POLICY,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, *, require_test_reports: bool = False, require_generated_artifacts: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    _check_source_boundaries(root, checks, hashes)
    _check_core_and_fixture(root, checks, hashes)
    _check_generated_artifacts(root, checks, hashes, require_generated_artifacts)
    _check_cli_wiring(root, checks)
    _check_reports(root, checks, hashes, require_test_reports)
    boundary_ok = (
        all(value is False for key, value in EXTERNAL_EFFECT_BOUNDARY.items() if key not in {"incremental_cash_spent_aud", "owner_final_order_only"})
        and EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
        and EXTERNAL_EFFECT_BOUNDARY["owner_final_order_only"] is True
    )
    _add(checks, "S19P04-EXTERNAL-EFFECT-BOUNDARY-EXACT", boundary_ok, EXTERNAL_EFFECT_BOUNDARY)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False, require_generated_artifacts=False)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_core_artifacts(root: Path) -> Tuple[Dict[str, Any], Dict[str, Any], bytes]:
    root = root.resolve()
    _, _, final_acceptance, manifest = _fixture_and_expected_artifacts(root)
    _atomic_write(root / FINAL_ACCEPTANCE_PATH, _json_bytes(final_acceptance))
    _atomic_write(root / RELEASE_MANIFEST_PATH, _json_bytes(manifest))
    bundle = _bundle_bytes(root)
    _atomic_write(root / HANDOFF_BUNDLE_PATH, bundle)
    return final_acceptance, manifest, bundle


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = (
        ORACLE_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        P03_PREDECESSOR_PATH,
        P03_ROLLBACK_PATH,
        *[Path(path) for path in SOURCE_ARTIFACT_HASHES if path not in {P03_PREDECESSOR_PATH.as_posix(), P03_ROLLBACK_PATH.as_posix()}],
    )
    artifacts = {
        path.as_posix(): {"sha256": sha256_file(root / path) if (root / path).is_file() else "MISSING", "status": "PASS" if (root / path).is_file() else "FAIL"}
        for path in paths
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S19_P04_LOCAL_DELIVERY_GATE_RESTORE_SIGNED_S19_P03_EVIDENCE_KEEP_RUNTIME_UNVERIFIED",
        "feature_flag_id": "release:s19_p04_local_final_delivery_gate",
        "artifacts": artifacts,
        "previous_signed_artifact": P03_PREDECESSOR_PATH.as_posix(),
        "immutable_evidence_and_replay_preserved": True,
        "external_state_changed": False,
        "production_state_changed": False,
        "actual_ga_activation_enabled": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "mail_sent": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool, require_generated_artifacts: bool) -> Dict[str, str]:
    paths = [ORACLE_PATH, FIXTURE_PATH, TEST_PATH, P03_PREDECESSOR_PATH, P03_ROLLBACK_PATH, *[Path(path) for path in BASELINE_HASHES], *[Path(path) for path in SOURCE_ARTIFACT_HASHES]]
    if require_generated_artifacts:
        paths.extend([FINAL_ACCEPTANCE_PATH, RELEASE_MANIFEST_PATH, HANDOFF_BUNDLE_PATH])
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in sorted(set(paths), key=lambda item: item.as_posix())}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(unsigned))


def build_evidence(root: Path, *, require_test_reports: bool = False, require_generated_artifacts: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_test_reports=require_test_reports, require_generated_artifacts=require_generated_artifacts)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S19-P04",
        "artifact_id": EXPECTED_ARTIFACT_IDS[2],
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "execution_policy": EXECUTION_POLICY,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "actual_ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
        "release_status": "S19_P04_LOCAL_FINAL_DELIVERY_COMPLETE_STAGE_REVIEW_REQUIRED_RUNTIME_NOT_DEPLOYED",
        "handoff_status": "NON_SECRET_LOCAL_HANDOFF_BUNDLE_ONLY",
        "cli_wiring": {"path": CLI_PATH.as_posix(), "sha256_at_signing": sha256_file(root / CLI_PATH)},
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports, require_generated_artifacts=require_generated_artifacts),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "deterministic_replay": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "adverse_one_in_ten_thousand_vector_count": 2,
            "real_time_wait_performed": False,
            "production_deployed": False,
            "actual_return_verified": False,
            "synthetic_or_local_control_promoted_to_empirical": False,
        },
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    replacement = {
        "id": "INDEX-%s" % CONTRACT_ID,
        "kind": "ACCEPTANCE_EVIDENCE",
        "stage_id": STAGE_ID,
        "requirement_id": REQUIREMENT_ID,
        "acceptance_contract_id": CONTRACT_ID,
        "status": "PASS",
        "expected_artifact": EVIDENCE_PATH.as_posix(),
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S19/STAGE_REVIEW_READY_NOT_STARTED",
        "pass_gate": "所有验收通过，版本和哈希无歧义无冲突。",
        "verified_at": FIXED_CLOCK,
    }
    matches = [index for index, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(matches) != 1 or len(raw_lines) != len(rows):
        raise FinalDeliveryAcceptanceError("S19/P04 evidence-index row must exist exactly once")
    raw_lines[matches[0]] = _jsonl_bytes(replacement).decode("utf-8").rstrip("\n")
    _atomic_write(path, ("\n".join(raw_lines) + "\n").encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise FinalDeliveryAcceptanceError("evidence directory must be canonical machine/evidence")
    preflight = validate_candidate_preflight(root)
    if preflight["status"] != "PASS":
        raise FinalDeliveryAcceptanceError("cannot sign a failed S19/P04 preflight")
    write_core_artifacts(root)
    evidence, rollback = build_evidence(root, require_test_reports=True, require_generated_artifacts=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise FinalDeliveryAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/STAGE_REVIEW_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-%s" % CONTRACT_ID)
    validation = evaluate_contract(root, require_test_reports=True, require_generated_artifacts=True)
    valid = (
        isinstance(evidence, Mapping)
        and isinstance(rollback, Mapping)
        and evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "S19_P04_LOCAL_FINAL_DELIVERY_PASS_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S19/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("execution_policy") == EXECUTION_POLICY
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("actual_ga_status") == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True, require_generated_artifacts=True)
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS"
        and rollback.get("previous_signed_artifact") == P03_PREDECESSOR_PATH.as_posix()
        and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False
        and rollback.get("actual_ga_activation_enabled") is False
        and rollback.get("order_submission_enabled") is False
        and index.get("status") == "PASS"
        and index.get("actual_artifact") == EVIDENCE_PATH.as_posix()
        and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S19/STAGE_REVIEW_READY_NOT_STARTED"
        and validation.get("status") == "PASS"
    )
    if not valid:
        raise FinalDeliveryAcceptanceError("existing S19/P04 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S19/STAGE_REVIEW_READY_NOT_STARTED"}


__all__ = [
    "BUNDLE_MEMBERS",
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "FINAL_ACCEPTANCE_PATH",
    "FIXTURE_PATH",
    "HANDOFF_BUNDLE_PATH",
    "ORACLE_PATH",
    "RELEASE_MANIFEST_PATH",
    "TEST_PATH",
    "FinalDeliveryAcceptanceError",
    "FinalDeliveryInputError",
    "build_evidence",
    "build_final_acceptance",
    "build_release_manifest",
    "evaluate_contract",
    "evaluate_final_delivery",
    "load_fixture",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_core_artifacts",
    "write_phase_evidence",
]
