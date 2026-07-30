"""Deterministic, fail-closed identity resolution for ABD S07/P01.

This module works only with caller-supplied frozen records and a versioned
registry.  It deliberately has no network, account, scheduler, pricing,
recommendation, or order-submission capability.  A match is useful only as an
identity precondition: downstream recommendation gates remain required.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = "1.0.0"
REGISTRY_ID = "ABD-IDENTITY-REGISTRY"
REGISTRY_VERSION = "0.0.0.1-S07P01"
CONFIDENCE_THRESHOLD = Decimal("0.9950")
TIME_TOLERANCE_SECONDS = 60
NO_ADVICE = "NO_ADVICE"
IDENTITY_ELIGIBLE = "IDENTITY_ELIGIBLE_DOWNSTREAM_GATES_REQUIRED"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{2,63}$")
REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*:[a-z0-9][a-z0-9._~-]{0,127}$")
MARKET_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
PERIOD_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
CATEGORY_RE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,63}$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
LINE_REPRESENTATIONS = {
    "NO_LINE_APPLICABLE",
    "SCALAR_DECIMAL",
    "RANGE_DECIMAL",
    "CATEGORICAL",
}


class IdentityResolutionError(ValueError):
    """Raised for malformed records that cannot safely be resolved."""


@dataclass(frozen=True)
class PreparedRegistry:
    """An immutable, validated JSON snapshot for deterministic bulk replay."""

    registry_json: bytes
    registry_sha256: str


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _require_string(value: Any, field: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise IdentityResolutionError("%s must be a non-empty string" % field)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise IdentityResolutionError("%s contains a control character" % field)
    if pattern is not None and pattern.fullmatch(value) is None:
        raise IdentityResolutionError("%s has an invalid shape" % field)
    return value


def _require_sha256(value: Any, field: str) -> str:
    value = _require_string(value, field, pattern=SHA256_RE)
    return value


def normalize_alias(value: Any) -> str:
    """Normalize only display-equivalent aliases; never perform fuzzy matching."""

    raw = _require_string(value, "alias")
    normalized = " ".join(unicodedata.normalize("NFKC", raw).casefold().split())
    if not normalized or len(normalized) > 160:
        raise IdentityResolutionError("alias normalizes to an invalid length")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise IdentityResolutionError("alias contains a control character after normalization")
    return normalized


def _canonical_decimal(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or DECIMAL_RE.fullmatch(value) is None:
        raise IdentityResolutionError("%s must be a base-10 decimal string" % field)
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:
        raise IdentityResolutionError("%s is not a valid decimal" % field) from exc
    if not decimal_value.is_finite():
        raise IdentityResolutionError("%s must be finite" % field)
    if decimal_value == 0:
        return "0"
    rendered = format(decimal_value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def canonicalize_line(value: Any) -> Dict[str, str]:
    """Return a canonical, JSON-safe line representation without binary floats."""

    if not isinstance(value, Mapping) or _contains_float(value):
        raise IdentityResolutionError("line must be an object without binary floats")
    representation = _require_string(value.get("representation"), "line.representation")
    if representation not in LINE_REPRESENTATIONS:
        raise IdentityResolutionError("line.representation is unsupported")
    keys = set(value)
    if representation == "NO_LINE_APPLICABLE":
        if keys != {"representation"}:
            raise IdentityResolutionError("NO_LINE_APPLICABLE has no value fields")
        return {"representation": representation}
    if representation == "SCALAR_DECIMAL":
        if keys != {"representation", "value"}:
            raise IdentityResolutionError("SCALAR_DECIMAL needs exactly one value")
        return {"representation": representation, "value": _canonical_decimal(value.get("value"), "line.value")}
    if representation == "RANGE_DECIMAL":
        if keys != {"representation", "lower", "upper"}:
            raise IdentityResolutionError("RANGE_DECIMAL needs lower and upper")
        lower = _canonical_decimal(value.get("lower"), "line.lower")
        upper = _canonical_decimal(value.get("upper"), "line.upper")
        if Decimal(lower) >= Decimal(upper):
            raise IdentityResolutionError("line.lower must be less than line.upper")
        return {"representation": representation, "lower": lower, "upper": upper}
    if keys != {"representation", "value"}:
        raise IdentityResolutionError("CATEGORICAL needs exactly one value")
    category = _require_string(value.get("value"), "line.value", pattern=CATEGORY_RE)
    return {"representation": representation, "value": category}


def canonicalize_start_time(value: Any, source_timezone: Any) -> str:
    """Validate an explicit local offset against the declared IANA timezone."""

    raw = _require_string(value, "start_time")
    zone_name = _require_string(source_timezone, "source_timezone")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise IdentityResolutionError("start_time must be ISO-8601 with an explicit offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.microsecond:
        raise IdentityResolutionError("start_time must have an explicit offset and whole-second precision")
    try:
        declared_zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as exc:
        raise IdentityResolutionError("source_timezone is not an installed IANA timezone") from exc
    local = parsed.astimezone(declared_zone)
    if local.replace(tzinfo=None) != parsed.replace(tzinfo=None) or local.utcoffset() != parsed.utcoffset():
        raise IdentityResolutionError("start_time offset conflicts with source_timezone")
    return local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_identifier(value: Any, field: str) -> str:
    return _require_string(value, field, pattern=IDENTIFIER_RE)


def _canonical_market_code(value: Any, field: str) -> str:
    return _require_string(value, field, pattern=MARKET_CODE_RE)


def _canonical_period(value: Any, field: str) -> str:
    return _require_string(value, field, pattern=PERIOD_ID_RE)


def _source_map(registry: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {str(row["source_id"]): row for row in registry.get("sources", []) if isinstance(row, Mapping) and isinstance(row.get("source_id"), str)}


def _alias_values(value: Any, *, source_id: str, field: str) -> List[str]:
    if not isinstance(value, Mapping):
        raise IdentityResolutionError("%s must be a source-to-alias mapping" % field)
    aliases = value.get(source_id)
    if not isinstance(aliases, list) or not aliases:
        return []
    normalized = [normalize_alias(item) for item in aliases]
    if len(normalized) != len(set(normalized)):
        raise IdentityResolutionError("%s contains duplicate aliases" % field)
    return normalized


def validate_registry(registry: Any) -> List[Dict[str, str]]:
    """Return all deterministic registry violations without making a resolution."""

    errors: List[Dict[str, str]] = []
    if not isinstance(registry, Mapping):
        return [{"path": "$", "message": "registry must be an object"}]
    if _contains_float(registry):
        errors.append({"path": "$", "message": "binary floats are forbidden"})
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append({"path": "schema_version", "message": "unexpected schema version"})
    if registry.get("registry_id") != REGISTRY_ID:
        errors.append({"path": "registry_id", "message": "unexpected registry id"})
    if registry.get("registry_version") != REGISTRY_VERSION:
        errors.append({"path": "registry_version", "message": "unexpected registry version"})
    confidence = registry.get("confidence_contract")
    expected_confidence = {
        "threshold": "0.9950",
        "below_threshold_action": NO_ADVICE,
        "at_or_above_threshold_action": IDENTITY_ELIGIBLE,
        "fuzzy_matching_allowed": False,
        "binary_float_allowed": False,
    }
    if confidence != expected_confidence:
        errors.append({"path": "confidence_contract", "message": "confidence contract must be exact"})
    boundary = registry.get("claim_boundary")
    expected_boundary = {
        "frozen_synthetic_registry_only": True,
        "network_or_provider_accessed": False,
        "actual_market_or_odds_observed": False,
        "cross_source_identity_runtime_verified": False,
        "recommendation_enabled": False,
        "order_submission_enabled": False,
        "financial_return_verified_or_guaranteed": False,
    }
    if boundary != expected_boundary:
        errors.append({"path": "claim_boundary", "message": "claim boundary must be exact"})

    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append({"path": "sources", "message": "sources must be a non-empty list"})
        sources = []
    source_ids: List[str] = []
    for index, source in enumerate(sources):
        path = "sources[%d]" % index
        if not isinstance(source, Mapping):
            errors.append({"path": path, "message": "source must be an object"})
            continue
        try:
            source_id = _require_string(source.get("source_id"), path + ".source_id", pattern=SOURCE_ID_RE)
            source_ids.append(source_id)
            _require_sha256(source.get("source_version_sha256"), path + ".source_version_sha256")
            if source.get("mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT":
                raise IdentityResolutionError("source mode must stay frozen and offline")
            if not isinstance(source.get("source_reference_binding_required"), bool):
                raise IdentityResolutionError("source_reference_binding_required must be boolean")
        except IdentityResolutionError as exc:
            errors.append({"path": path, "message": str(exc)})
    if len(source_ids) != len(set(source_ids)):
        errors.append({"path": "sources", "message": "source_id values must be unique"})

    events = registry.get("events")
    if not isinstance(events, list) or not events:
        errors.append({"path": "events", "message": "events must be a non-empty list"})
        events = []
    event_ids: List[str] = []
    source_refs: set[Tuple[str, str]] = set()
    for event_index, event in enumerate(events):
        path = "events[%d]" % event_index
        if not isinstance(event, Mapping):
            errors.append({"path": path, "message": "event must be an object"})
            continue
        try:
            event_id = _canonical_identifier(event.get("event_id"), path + ".event_id")
            event_ids.append(event_id)
            _canonical_identifier(event.get("sport_id"), path + ".sport_id")
            _canonical_identifier(event.get("competition_id"), path + ".competition_id")
            canonical_start = canonicalize_start_time(event.get("scheduled_start_local"), event.get("scheduled_start_timezone"))
            if event.get("scheduled_start_utc") != canonical_start:
                raise IdentityResolutionError("scheduled_start_utc conflicts with scheduled_start_local/timezone")
            participants = event.get("participants")
            if not isinstance(participants, Mapping) or set(participants) != {"HOME", "AWAY"}:
                raise IdentityResolutionError("participants must contain exactly HOME and AWAY")
            for role, participant in participants.items():
                if not isinstance(participant, Mapping):
                    raise IdentityResolutionError("participant %s must be an object" % role)
                _canonical_identifier(participant.get("participant_id"), "participant_id")
                aliases = participant.get("aliases")
                if not isinstance(aliases, Mapping):
                    raise IdentityResolutionError("participant aliases must be an object")
                for source_id, values in aliases.items():
                    _require_string(source_id, "alias source_id", pattern=SOURCE_ID_RE)
                    if source_id not in source_ids:
                        raise IdentityResolutionError("participant alias references an unknown source")
                    if not isinstance(values, list) or not values:
                        raise IdentityResolutionError("participant alias values must be non-empty")
                    normalized = [normalize_alias(item) for item in values]
                    if len(normalized) != len(set(normalized)):
                        raise IdentityResolutionError("participant aliases must be unique per source")
            references = event.get("source_references")
            if not isinstance(references, list):
                raise IdentityResolutionError("source_references must be a list")
            for reference in references:
                if not isinstance(reference, Mapping):
                    raise IdentityResolutionError("source reference must be an object")
                source_id = _require_string(reference.get("source_id"), "source_reference.source_id", pattern=SOURCE_ID_RE)
                value = _require_string(reference.get("source_event_ref"), "source_reference.source_event_ref", pattern=REFERENCE_RE)
                if source_id not in source_ids:
                    raise IdentityResolutionError("source reference uses unknown source")
                key = (source_id, value)
                if key in source_refs:
                    raise IdentityResolutionError("source reference must be globally unique")
                source_refs.add(key)
            markets = event.get("markets")
            if not isinstance(markets, list) or not markets:
                raise IdentityResolutionError("markets must be a non-empty list")
            market_keys: set[Tuple[str, str, str]] = set()
            for market in markets:
                if not isinstance(market, Mapping):
                    raise IdentityResolutionError("market must be an object")
                _canonical_identifier(market.get("market_id"), "market_id")
                market_code = _canonical_market_code(market.get("market_code"), "market_code")
                period_id = _canonical_period(market.get("period_id"), "period_id")
                line = canonicalize_line(market.get("line"))
                market_key = (market_code, period_id, json.dumps(line, sort_keys=True))
                if market_key in market_keys:
                    raise IdentityResolutionError("market semantic key must be unique within an event")
                market_keys.add(market_key)
                selections = market.get("selections")
                if not isinstance(selections, list) or not selections:
                    raise IdentityResolutionError("market selections must be non-empty")
                selection_ids: set[str] = set()
                for selection in selections:
                    if not isinstance(selection, Mapping):
                        raise IdentityResolutionError("selection must be an object")
                    selection_id = _require_string(selection.get("selection_id"), "selection_id", pattern=PERIOD_ID_RE)
                    if selection_id in selection_ids:
                        raise IdentityResolutionError("selection_id must be unique within market")
                    selection_ids.add(selection_id)
                    aliases = selection.get("aliases")
                    if not isinstance(aliases, Mapping):
                        raise IdentityResolutionError("selection aliases must be an object")
                    for source_id, values in aliases.items():
                        _require_string(source_id, "selection alias source_id", pattern=SOURCE_ID_RE)
                        if source_id not in source_ids or not isinstance(values, list) or not values:
                            raise IdentityResolutionError("selection aliases must reference a known source and be non-empty")
                        normalized = [normalize_alias(item) for item in values]
                        if len(normalized) != len(set(normalized)):
                            raise IdentityResolutionError("selection aliases must be unique per source")
        except IdentityResolutionError as exc:
            errors.append({"path": path, "message": str(exc)})
    if len(event_ids) != len(set(event_ids)):
        errors.append({"path": "events", "message": "event_id values must be unique"})
    return errors


def load_registry(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityResolutionError("registry cannot be loaded") from exc
    if not isinstance(value, Mapping):
        raise IdentityResolutionError("registry must be an object")
    errors = validate_registry(value)
    if errors:
        raise IdentityResolutionError("registry validation failed: %s" % json.dumps(errors, ensure_ascii=False, sort_keys=True))
    return value


def prepare_registry(registry: Any) -> PreparedRegistry:
    """Validate once and freeze a JSON snapshot for bounded deterministic replay."""

    errors = validate_registry(registry)
    if errors:
        raise IdentityResolutionError("registry validation failed: %s" % json.dumps(errors, ensure_ascii=False, sort_keys=True))
    try:
        registry_json = _json_bytes(registry)
    except (TypeError, ValueError) as exc:
        raise IdentityResolutionError("registry cannot be frozen as canonical JSON") from exc
    return PreparedRegistry(registry_json=registry_json, registry_sha256=_sha256(registry_json))


def _observation(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or _contains_float(value):
        raise IdentityResolutionError("observation must be an object without binary floats")
    required = {
        "source_id",
        "source_version_sha256",
        "source_payload_sha256",
        "source_event_ref",
        "sport_id",
        "competition_id",
        "home_alias",
        "away_alias",
        "start_time",
        "source_timezone",
        "market_code",
        "period_id",
        "line",
        "selection_alias",
    }
    if set(value) != required:
        raise IdentityResolutionError("observation fields must be exact; unsupported data cannot influence identity")
    return {
        "source_id": _require_string(value["source_id"], "source_id", pattern=SOURCE_ID_RE),
        "source_version_sha256": _require_sha256(value["source_version_sha256"], "source_version_sha256"),
        "source_payload_sha256": _require_sha256(value["source_payload_sha256"], "source_payload_sha256"),
        "source_event_ref": _require_string(value["source_event_ref"], "source_event_ref", pattern=REFERENCE_RE),
        "sport_id": _canonical_identifier(value["sport_id"], "sport_id"),
        "competition_id": _canonical_identifier(value["competition_id"], "competition_id"),
        "home_alias": normalize_alias(value["home_alias"]),
        "away_alias": normalize_alias(value["away_alias"]),
        "start_time_utc": canonicalize_start_time(value["start_time"], value["source_timezone"]),
        "market_code": _canonical_market_code(value["market_code"], "market_code"),
        "period_id": _canonical_period(value["period_id"], "period_id"),
        "line": canonicalize_line(value["line"]),
        "selection_alias": normalize_alias(value["selection_alias"]),
    }


def confidence_action(value: Any) -> Dict[str, Any]:
    """Apply the sole S07/P01 hard threshold without rounding a Decimal."""

    if isinstance(value, (bool, float)):
        raise IdentityResolutionError("confidence must not use a binary float or boolean")
    confidence = Decimal(str(value))
    if not confidence.is_finite() or confidence < 0 or confidence > 1:
        raise IdentityResolutionError("confidence must be a finite value between zero and one")
    normalized_decimal = confidence.quantize(Decimal("0.0001"))
    if normalized_decimal != confidence:
        raise IdentityResolutionError("confidence must not contain precision beyond four decimal places")
    normalized = format(normalized_decimal, "f")
    eligible = confidence >= CONFIDENCE_THRESHOLD
    return {
        "identity_confidence": normalized,
        "identity_confidence_threshold": "0.9950",
        "identity_eligible": eligible,
        "identity_action": IDENTITY_ELIGIBLE if eligible else NO_ADVICE,
    }


def _event_source_reference(event: Mapping[str, Any], source_id: str, source_event_ref: str) -> bool:
    return any(
        isinstance(row, Mapping) and row.get("source_id") == source_id and row.get("source_event_ref") == source_event_ref
        for row in event.get("source_references", [])
    )


def _participant_matches(participant: Mapping[str, Any], source_id: str, alias: str) -> bool:
    try:
        return alias in _alias_values(participant.get("aliases"), source_id=source_id, field="participant.aliases")
    except IdentityResolutionError:
        return False


def _event_candidates(registry: Mapping[str, Any], observation: Mapping[str, Any]) -> List[Tuple[Mapping[str, Any], int, bool]]:
    observed_start = datetime.fromisoformat(str(observation["start_time_utc"]).replace("Z", "+00:00"))
    candidates: List[Tuple[Mapping[str, Any], int, bool]] = []
    for event in registry.get("events", []):
        if not isinstance(event, Mapping):
            continue
        if event.get("sport_id") != observation["sport_id"] or event.get("competition_id") != observation["competition_id"]:
            continue
        participants = event.get("participants")
        if not isinstance(participants, Mapping):
            continue
        home = participants.get("HOME")
        away = participants.get("AWAY")
        if not isinstance(home, Mapping) or not isinstance(away, Mapping):
            continue
        if not _participant_matches(home, str(observation["source_id"]), str(observation["home_alias"])):
            continue
        if not _participant_matches(away, str(observation["source_id"]), str(observation["away_alias"])):
            continue
        scheduled = datetime.fromisoformat(str(event["scheduled_start_utc"]).replace("Z", "+00:00"))
        delta = abs(int((scheduled - observed_start).total_seconds()))
        if delta <= TIME_TOLERANCE_SECONDS:
            candidates.append((event, delta, _event_source_reference(event, str(observation["source_id"]), str(observation["source_event_ref"]))))
    return candidates


def _market_selection(event: Mapping[str, Any], observation: Mapping[str, Any]) -> Tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    matching_markets = [
        market
        for market in event.get("markets", [])
        if isinstance(market, Mapping)
        and market.get("market_code") == observation["market_code"]
        and market.get("period_id") == observation["period_id"]
        and canonicalize_line(market.get("line")) == observation["line"]
    ]
    if len(matching_markets) != 1:
        return None
    market = matching_markets[0]
    selections = [
        selection
        for selection in market.get("selections", [])
        if isinstance(selection, Mapping)
        and observation["selection_alias"] in _alias_values(selection.get("aliases"), source_id=str(observation["source_id"]), field="selection.aliases")
    ]
    return (market, selections[0]) if len(selections) == 1 else None


def build_identity_key(event: Mapping[str, Any], market: Mapping[str, Any], selection: Mapping[str, Any]) -> str:
    material = {
        "event_id": event["event_id"],
        "market_code": market["market_code"],
        "market_id": market["market_id"],
        "period_id": market["period_id"],
        "line": canonicalize_line(market["line"]),
        "selection_id": selection["selection_id"],
    }
    return "IDK-S07P01-" + _sha256(_json_bytes(material))


def _no_advice(reason_codes: Iterable[str], *, confidence: Decimal = Decimal("0"), observation: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    gate = confidence_action(confidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": NO_ADVICE,
        "identity_key": None,
        "canonical": None,
        "reason_codes": sorted(set(str(item) for item in reason_codes)),
        "source_provenance": {
            "source_id": observation.get("source_id") if observation else None,
            "source_version_sha256": observation.get("source_version_sha256") if observation else None,
            "source_payload_sha256": observation.get("source_payload_sha256") if observation else None,
        },
        **gate,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
    }


def _resolve_validated_registry(registry: Mapping[str, Any], observation: Any) -> Dict[str, Any]:
    try:
        normalized = _observation(observation)
    except IdentityResolutionError as exc:
        return _no_advice(["MALFORMED_OBSERVATION", type(exc).__name__])
    source = _source_map(registry).get(normalized["source_id"])
    if source is None:
        return _no_advice(["UNKNOWN_SOURCE"], observation=normalized)
    if source.get("source_version_sha256") != normalized["source_version_sha256"]:
        return _no_advice(["SOURCE_VERSION_HASH_MISMATCH"], observation=normalized)
    candidates = _event_candidates(registry, normalized)
    if not candidates:
        return _no_advice(["EVENT_NOT_UNIQUELY_IDENTIFIED"], observation=normalized)
    if len(candidates) != 1:
        return _no_advice(["AMBIGUOUS_EVENT_CANDIDATES"], observation=normalized)
    event, delta_seconds, source_reference_match = candidates[0]
    reference_required = bool(source.get("source_reference_binding_required"))
    if reference_required and not source_reference_match:
        return _no_advice(["SOURCE_EVENT_REFERENCE_UNBOUND"], observation=normalized)
    market_selection = _market_selection(event, normalized)
    if market_selection is None:
        return _no_advice(["MARKET_OR_SELECTION_NOT_UNIQUELY_IDENTIFIED"], observation=normalized)
    market, selection = market_selection
    confidence = Decimal("1.0000") if source_reference_match and delta_seconds == 0 else Decimal("0.9950") if delta_seconds == 0 else Decimal("0.9949")
    gate = confidence_action(confidence)
    if not gate["identity_eligible"]:
        return _no_advice(["IDENTITY_CONFIDENCE_BELOW_THRESHOLD", "START_TIME_NOT_EXACT"], confidence=confidence, observation=normalized)
    canonical = {
        "event_id": event["event_id"],
        "sport_id": event["sport_id"],
        "competition_id": event["competition_id"],
        "scheduled_start_utc": event["scheduled_start_utc"],
        "market_id": market["market_id"],
        "market_code": market["market_code"],
        "period_id": market["period_id"],
        "line": canonicalize_line(market["line"]),
        "selection_id": selection["selection_id"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "IDENTITY_RESOLVED",
        "identity_key": build_identity_key(event, market, selection),
        "canonical": canonical,
        "reason_codes": [],
        "source_provenance": {
            "source_id": normalized["source_id"],
            "source_version_sha256": normalized["source_version_sha256"],
            "source_payload_sha256": normalized["source_payload_sha256"],
        },
        **gate,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
    }


def resolve_prepared_identity(prepared: Any, observation: Any) -> Dict[str, Any]:
    """Resolve against a validated immutable snapshot without a real-time wait."""

    if not isinstance(prepared, PreparedRegistry):
        return _no_advice(["REGISTRY_INVALID"])
    if _sha256(prepared.registry_json) != prepared.registry_sha256:
        return _no_advice(["REGISTRY_SNAPSHOT_HASH_MISMATCH"])
    try:
        registry = json.loads(prepared.registry_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _no_advice(["REGISTRY_INVALID"])
    if not isinstance(registry, Mapping):
        return _no_advice(["REGISTRY_INVALID"])
    return _resolve_validated_registry(registry, observation)


def resolve_identity(registry: Any, observation: Any) -> Dict[str, Any]:
    """Resolve an observed market selection or return an explicit fail-closed result."""

    try:
        prepared = prepare_registry(registry)
    except IdentityResolutionError:
        return _no_advice(["REGISTRY_INVALID"])
    return resolve_prepared_identity(prepared, observation)


def deterministic_resolution_hash(registry: Any, observation: Any) -> str:
    return _sha256(_json_bytes(resolve_identity(registry, observation)))
