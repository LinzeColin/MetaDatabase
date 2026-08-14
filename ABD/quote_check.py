"""Deterministic, local-only quote validation for ABD S13/P02.

This module evaluates a frozen recommendation ticket against fields explicitly
visible to the owner in a browser companion.  It never opens a platform,
accesses a network or account, clicks a page element, or submits an order.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from typing import Any, Dict, Mapping, Sequence


PRODUCT_VERSION = "0.0.0.1"
SCHEMA_VERSION = "1.0.0"
INPUT_MODE = "FROZEN_SYNTHETIC_VISIBLE_PAGE_NO_NETWORK"
OPEN_MODE = "COPY_INSTRUCTION_ONLY_NO_AUTO_OPEN"
GREEN_STATUS = "GREEN_READY_FOR_OWNER_FINAL_ORDER"
RED_STATUS = "RED_REVOKE_DO_NOT_ORDER"
OWNER_ACTION = "OWNER_FINAL_ORDER_MANUAL_ONLY"
REVOKE_ACTION = "DO_NOT_ORDER"
DECIMAL_PRECISION = 50
ODDS_STEP = Decimal("0.000001")
ADVERSE_TIME_SECONDS = 2

CLAIM_BOUNDARY = {
    "actual_market_or_odds_observed": False,
    "automatic_platform_open_performed": False,
    "browser_extension_installed_or_executed": False,
    "external_network_accessed": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_account_accessed": False,
    "real_time_soak_waited": False,
}

_TICKET_FIELDS = {
    "schema_version",
    "ticket_id",
    "synthetic_test_only",
    "provider_id",
    "event_id",
    "market_id",
    "selection_id",
    "parameters_sha256",
    "provider_contracts_sha256",
    "minimum_odds",
    "advice_expires_at",
    "risk_feature_required",
    "open_mode",
    "copy_instruction_zh",
}
_SNAPSHOT_FIELDS = {
    "schema_version",
    "snapshot_id",
    "input_mode",
    "synthetic_test_only",
    "provider_id",
    "event_id",
    "market_id",
    "selection_id",
    "current_odds",
    "observed_at",
    "risk_feature_enabled",
    "visible_fields_complete",
}
_CASE_FIELDS = {
    "case_id",
    "snapshot",
    "expected_status",
    "expected_failed_gate_ids",
    "expected_action",
}
_ADVERSE_FIELDS = {
    "scenario_id",
    "base_case_id",
    "odds_down_ticks",
    "seconds_later",
    "expected_status",
    "expected_failed_gate_ids",
}
_FIXTURE_FIELDS = {
    "schema_version",
    "fixture_id",
    "product_version",
    "fixed_clock",
    "input_mode",
    "claim_boundary",
    "ticket",
    "cases",
    "adverse_scenarios",
}
_IDENTIFIER = re.compile(r"[A-Z0-9][A-Z0-9._:-]{2,127}")


class QuoteCheckError(ValueError):
    """Raised when a quote ticket or visible-page snapshot is unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _strict_object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise QuoteCheckError("%s has an unexpected shape" % label)
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise QuoteCheckError("%s is not a closed identifier" % label)
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise QuoteCheckError("%s must be a lowercase SHA-256" % label)
    return value


def _chinese_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or re.search(r"[\u3400-\u9fff]", value) is None:
        raise QuoteCheckError("%s must be non-empty Chinese text" % label)
    return value


def _decimal_odds(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise QuoteCheckError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise QuoteCheckError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or parsed <= Decimal("1"):
        raise QuoteCheckError("%s must be finite and greater than one" % label)
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            quantized = parsed.quantize(ODDS_STEP)
    except InvalidOperation as exc:
        raise QuoteCheckError("%s cannot use the fixed odds scale" % label) from exc
    if quantized != parsed:
        raise QuoteCheckError("%s is not aligned to odds scale 1e-6" % label)
    return parsed


def _format_odds(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return format(value.quantize(ODDS_STEP), "f")


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise QuoteCheckError("%s must be an ISO timestamp" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise QuoteCheckError("%s is not an ISO timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QuoteCheckError("%s must include a timezone offset" % label)
    return parsed


def _remaining_seconds(expires_at: datetime, observed_at: datetime) -> int:
    delta = expires_at - observed_at
    microseconds = ((delta.days * 86400) + delta.seconds) * 1_000_000 + delta.microseconds
    return max(0, microseconds // 1_000_000)


def validate_ticket(value: Any) -> Dict[str, Any]:
    ticket = _strict_object(value, _TICKET_FIELDS, "ticket")
    if _contains_float(ticket):
        raise QuoteCheckError("ticket must not contain binary floats")
    if ticket.get("schema_version") != SCHEMA_VERSION:
        raise QuoteCheckError("ticket schema version is not frozen")
    if ticket.get("synthetic_test_only") is not True:
        raise QuoteCheckError("ticket must be synthetic during this phase")
    if ticket.get("risk_feature_required") is not True:
        raise QuoteCheckError("ticket must require an enabled risk feature")
    if ticket.get("open_mode") != OPEN_MODE:
        raise QuoteCheckError("ticket must only provide a copy instruction")
    return {
        "schema_version": SCHEMA_VERSION,
        "ticket_id": _identifier(ticket.get("ticket_id"), "ticket.ticket_id"),
        "synthetic_test_only": True,
        "provider_id": _identifier(ticket.get("provider_id"), "ticket.provider_id"),
        "event_id": _identifier(ticket.get("event_id"), "ticket.event_id"),
        "market_id": _identifier(ticket.get("market_id"), "ticket.market_id"),
        "selection_id": _identifier(ticket.get("selection_id"), "ticket.selection_id"),
        "parameters_sha256": _sha256(ticket.get("parameters_sha256"), "ticket.parameters_sha256"),
        "provider_contracts_sha256": _sha256(ticket.get("provider_contracts_sha256"), "ticket.provider_contracts_sha256"),
        "minimum_odds": _format_odds(_decimal_odds(ticket.get("minimum_odds"), "ticket.minimum_odds")),
        "advice_expires_at": _timestamp(ticket.get("advice_expires_at"), "ticket.advice_expires_at").isoformat(),
        "risk_feature_required": True,
        "open_mode": OPEN_MODE,
        "copy_instruction_zh": _chinese_text(ticket.get("copy_instruction_zh"), "ticket.copy_instruction_zh"),
    }


def validate_visible_snapshot(value: Any) -> Dict[str, Any]:
    snapshot = _strict_object(value, _SNAPSHOT_FIELDS, "visible snapshot")
    if _contains_float(snapshot):
        raise QuoteCheckError("visible snapshot must not contain binary floats")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise QuoteCheckError("visible snapshot schema version is not frozen")
    if snapshot.get("input_mode") != INPUT_MODE:
        raise QuoteCheckError("visible snapshot input mode is unsafe")
    if snapshot.get("synthetic_test_only") is not True:
        raise QuoteCheckError("visible snapshot must stay synthetic in this phase")
    if type(snapshot.get("risk_feature_enabled")) is not bool or type(snapshot.get("visible_fields_complete")) is not bool:
        raise QuoteCheckError("visible snapshot flags must be booleans")
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": _identifier(snapshot.get("snapshot_id"), "snapshot.snapshot_id"),
        "input_mode": INPUT_MODE,
        "synthetic_test_only": True,
        "provider_id": _identifier(snapshot.get("provider_id"), "snapshot.provider_id"),
        "event_id": _identifier(snapshot.get("event_id"), "snapshot.event_id"),
        "market_id": _identifier(snapshot.get("market_id"), "snapshot.market_id"),
        "selection_id": _identifier(snapshot.get("selection_id"), "snapshot.selection_id"),
        "current_odds": _format_odds(_decimal_odds(snapshot.get("current_odds"), "snapshot.current_odds")),
        "observed_at": _timestamp(snapshot.get("observed_at"), "snapshot.observed_at").isoformat(),
        "risk_feature_enabled": snapshot["risk_feature_enabled"],
        "visible_fields_complete": snapshot["visible_fields_complete"],
    }


def build_copy_instruction(value: Any) -> Dict[str, Any]:
    ticket = validate_ticket(value)
    return {
        "schema_version": SCHEMA_VERSION,
        "ticket_id": ticket["ticket_id"],
        "provider_id": ticket["provider_id"],
        "open_mode": OPEN_MODE,
        "copy_instruction_zh": ticket["copy_instruction_zh"],
        "deep_link_status": "UNAVAILABLE_WITHOUT_VERIFIED_PROVIDER_CONTRACT",
        "automatic_platform_open_performed": False,
        "external_network_accessed": False,
        "order_submission_enabled": False,
        "synthetic_test_only": True,
    }


def _red_malformed(detail: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": RED_STATUS,
        "action": REVOKE_ACTION,
        "verdict_zh": "红色撤销：即时校验输入不完整或不可信，请勿下单。",
        "failed_gate_ids": ["MALFORMED_OR_UNTRUSTED_VISIBLE_INPUT"],
        "detail": detail,
        "automatic_platform_open_performed": False,
        "order_submission_enabled": False,
        "synthetic_test_only": True,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }


def evaluate_quote(ticket_value: Any, snapshot_value: Any) -> Dict[str, Any]:
    """Return a deterministic green or red owner-facing quote-check result."""

    try:
        ticket = validate_ticket(ticket_value)
        snapshot = validate_visible_snapshot(snapshot_value)
        minimum_odds = _decimal_odds(ticket["minimum_odds"], "ticket.minimum_odds")
        current_odds = _decimal_odds(snapshot["current_odds"], "snapshot.current_odds")
        expires_at = _timestamp(ticket["advice_expires_at"], "ticket.advice_expires_at")
        observed_at = _timestamp(snapshot["observed_at"], "snapshot.observed_at")
    except QuoteCheckError as exc:
        return _red_malformed(str(exc))

    failures: list[str] = []
    if snapshot["visible_fields_complete"] is not True:
        failures.append("VISIBLE_FIELDS_UNAVAILABLE")
    if snapshot["provider_id"] != ticket["provider_id"]:
        failures.append("PROVIDER_IDENTITY_MISMATCH")
    if snapshot["event_id"] != ticket["event_id"]:
        failures.append("EVENT_IDENTITY_MISMATCH")
    if snapshot["market_id"] != ticket["market_id"]:
        failures.append("MARKET_IDENTITY_MISMATCH")
    if snapshot["selection_id"] != ticket["selection_id"]:
        failures.append("SELECTION_IDENTITY_MISMATCH")
    if current_odds < minimum_odds:
        failures.append("CURRENT_ODDS_BELOW_MINIMUM")
    if observed_at >= expires_at:
        failures.append("ADVICE_EXPIRED")
    if snapshot["risk_feature_enabled"] is not True:
        failures.append("RISK_FEATURE_DISABLED")

    passed = not failures
    return {
        "schema_version": SCHEMA_VERSION,
        "ticket_id": ticket["ticket_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "status": GREEN_STATUS if passed else RED_STATUS,
        "action": OWNER_ACTION if passed else REVOKE_ACTION,
        "verdict_zh": "绿色：即时校验通过；仅由你自行完成最终下单。" if passed else "红色撤销：至少一项即时校验失败，请勿下单。",
        "checked_identity": {
            "provider_id": snapshot["provider_id"] == ticket["provider_id"],
            "event_id": snapshot["event_id"] == ticket["event_id"],
            "market_id": snapshot["market_id"] == ticket["market_id"],
            "selection_id": snapshot["selection_id"] == ticket["selection_id"],
        },
        "current_odds": _format_odds(current_odds),
        "minimum_odds": _format_odds(minimum_odds),
        "advice_remaining_seconds": _remaining_seconds(expires_at, observed_at),
        "risk_feature_enabled": snapshot["risk_feature_enabled"],
        "visible_fields_complete": snapshot["visible_fields_complete"],
        "failed_gate_ids": failures,
        "automatic_platform_open_performed": False,
        "order_submission_enabled": False,
        "synthetic_test_only": True,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }


def apply_adverse_perturbation(snapshot_value: Any, *, odds_down_ticks: int, seconds_later: int) -> Dict[str, Any]:
    """Create a deterministic adverse visible-page variant without a clock wait."""

    snapshot = validate_visible_snapshot(snapshot_value)
    if type(odds_down_ticks) is not int or odds_down_ticks < 0:
        raise QuoteCheckError("odds_down_ticks must be a non-negative integer")
    if type(seconds_later) is not int or seconds_later < 0:
        raise QuoteCheckError("seconds_later must be a non-negative integer")
    current_odds = _decimal_odds(snapshot["current_odds"], "snapshot.current_odds")
    perturbed_odds = current_odds - (ODDS_STEP * odds_down_ticks)
    if perturbed_odds <= Decimal("1"):
        raise QuoteCheckError("adverse odds perturbation leaves the valid odds domain")
    observed_at = _timestamp(snapshot["observed_at"], "snapshot.observed_at") + timedelta(seconds=seconds_later)
    output = dict(snapshot)
    output["current_odds"] = _format_odds(perturbed_odds)
    output["observed_at"] = observed_at.isoformat()
    output["snapshot_id"] = "%s-ADVERSE-%d-%d" % (snapshot["snapshot_id"], odds_down_ticks, seconds_later)
    return output


def validate_match_fixtures(value: Any) -> Dict[str, Any]:
    fixture = _strict_object(value, _FIXTURE_FIELDS, "match fixtures")
    if _contains_float(fixture):
        raise QuoteCheckError("match fixtures must not contain binary floats")
    if fixture.get("schema_version") != SCHEMA_VERSION or fixture.get("product_version") != PRODUCT_VERSION:
        raise QuoteCheckError("match fixture version is not frozen")
    if not isinstance(fixture.get("fixture_id"), str) or not fixture["fixture_id"].startswith("FIX-S13-P02-"):
        raise QuoteCheckError("match fixture id is invalid")
    if fixture.get("input_mode") != INPUT_MODE or fixture.get("claim_boundary") != CLAIM_BOUNDARY:
        raise QuoteCheckError("match fixture boundary is unsafe")
    _timestamp(fixture.get("fixed_clock"), "fixture.fixed_clock")
    ticket = validate_ticket(fixture.get("ticket"))
    cases = fixture.get("cases")
    adverse = fixture.get("adverse_scenarios")
    if not isinstance(cases, list) or len(cases) < 8 or not isinstance(adverse, list) or len(adverse) < 2:
        raise QuoteCheckError("match fixture does not cover required positive and adverse paths")
    normalized_cases: list[Dict[str, Any]] = []
    seen_cases: set[str] = set()
    for index, raw_case in enumerate(cases):
        case = _strict_object(raw_case, _CASE_FIELDS, "cases[%d]" % index)
        case_id = _identifier(case.get("case_id"), "cases[%d].case_id" % index)
        if case_id in seen_cases:
            raise QuoteCheckError("case ids must be unique")
        seen_cases.add(case_id)
        expected_status = case.get("expected_status")
        expected_action = case.get("expected_action")
        expected_failures = case.get("expected_failed_gate_ids")
        if expected_status not in {GREEN_STATUS, RED_STATUS} or expected_action not in {OWNER_ACTION, REVOKE_ACTION}:
            raise QuoteCheckError("case expected status or action is invalid")
        if not isinstance(expected_failures, list) or not all(isinstance(item, str) and item for item in expected_failures):
            raise QuoteCheckError("case expected failures are invalid")
        if (expected_status == GREEN_STATUS) != (not expected_failures) or (expected_action == OWNER_ACTION) != (expected_status == GREEN_STATUS):
            raise QuoteCheckError("case expected status, action and failures disagree")
        normalized_cases.append(
            {
                "case_id": case_id,
                "snapshot": validate_visible_snapshot(case.get("snapshot")),
                "expected_status": expected_status,
                "expected_failed_gate_ids": list(expected_failures),
                "expected_action": expected_action,
            }
        )
    normalized_adverse: list[Dict[str, Any]] = []
    seen_adverse: set[str] = set()
    for index, raw_scenario in enumerate(adverse):
        scenario = _strict_object(raw_scenario, _ADVERSE_FIELDS, "adverse_scenarios[%d]" % index)
        scenario_id = _identifier(scenario.get("scenario_id"), "adverse_scenarios[%d].scenario_id" % index)
        base_case_id = _identifier(scenario.get("base_case_id"), "adverse_scenarios[%d].base_case_id" % index)
        if scenario_id in seen_adverse or base_case_id not in seen_cases:
            raise QuoteCheckError("adverse scenario id or base case is invalid")
        seen_adverse.add(scenario_id)
        if type(scenario.get("odds_down_ticks")) is not int or scenario["odds_down_ticks"] < 0:
            raise QuoteCheckError("adverse odds ticks are invalid")
        if type(scenario.get("seconds_later")) is not int or scenario["seconds_later"] < 0:
            raise QuoteCheckError("adverse seconds are invalid")
        if scenario.get("expected_status") not in {GREEN_STATUS, RED_STATUS}:
            raise QuoteCheckError("adverse expected status is invalid")
        failures = scenario.get("expected_failed_gate_ids")
        if not isinstance(failures, list) or not all(isinstance(item, str) and item for item in failures):
            raise QuoteCheckError("adverse expected failures are invalid")
        normalized_adverse.append(
            {
                "scenario_id": scenario_id,
                "base_case_id": base_case_id,
                "odds_down_ticks": scenario["odds_down_ticks"],
                "seconds_later": scenario["seconds_later"],
                "expected_status": scenario["expected_status"],
                "expected_failed_gate_ids": list(failures),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture["fixture_id"],
        "product_version": PRODUCT_VERSION,
        "fixed_clock": _timestamp(fixture["fixed_clock"], "fixture.fixed_clock").isoformat(),
        "input_mode": INPUT_MODE,
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "ticket": ticket,
        "cases": normalized_cases,
        "adverse_scenarios": normalized_adverse,
    }


def replay_match_fixtures(value: Any) -> Dict[str, Any]:
    fixture = validate_match_fixtures(value)
    case_results = []
    by_id = {}
    for case in fixture["cases"]:
        result = evaluate_quote(fixture["ticket"], case["snapshot"])
        by_id[case["case_id"]] = case
        case_results.append(
            {
                "case_id": case["case_id"],
                "status": result["status"],
                "action": result["action"],
                "failed_gate_ids": result["failed_gate_ids"],
                "expected_status": case["expected_status"],
                "expected_action": case["expected_action"],
                "expected_failed_gate_ids": case["expected_failed_gate_ids"],
            }
        )
    adverse_results = []
    for scenario in fixture["adverse_scenarios"]:
        base_case = by_id[scenario["base_case_id"]]
        altered = apply_adverse_perturbation(
            base_case["snapshot"],
            odds_down_ticks=scenario["odds_down_ticks"],
            seconds_later=scenario["seconds_later"],
        )
        result = evaluate_quote(fixture["ticket"], altered)
        adverse_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "status": result["status"],
                "failed_gate_ids": result["failed_gate_ids"],
                "expected_status": scenario["expected_status"],
                "expected_failed_gate_ids": scenario["expected_failed_gate_ids"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture["fixture_id"],
        "copy_instruction": build_copy_instruction(fixture["ticket"]),
        "case_results": case_results,
        "adverse_results": adverse_results,
        "replay_sha256": canonical_sha256({"ticket": fixture["ticket"], "cases": case_results, "adverse": adverse_results}),
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
