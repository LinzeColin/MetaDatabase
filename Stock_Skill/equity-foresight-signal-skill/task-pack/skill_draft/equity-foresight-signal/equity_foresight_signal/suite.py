from __future__ import annotations

import copy
from itertools import islice
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes, sha256_hex, strict_json_loads
from .engine import (
    DEFAULT_LIMITS,
    PreparedBundle,
    RUNTIME_VERSION,
    STABLE_ID,
    evaluate_prepared,
    prepare_bundle,
    validate_bundle,
)
from .errors import EFSError

SUITE_SCHEMA = "efs.forecast_suite.v1"
SUITE_RESULT_SCHEMA = "efs.forecast_suite_result.v1"
MAX_SUITE_HORIZONS = 8
_SUITE_TOKEN = object()


def _bounded_iterable(value: Any, *, field: str, maximum: int) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray, dict)):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an iterable of items")
    try:
        items = list(islice(iter(value), maximum + 1))
    except TypeError as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} must be iterable") from exc
    if len(items) > maximum:
        raise EFSError("RESOURCE_LIMIT", f"{field} exceeds the allowed item limit")
    return items


def _horizon_key(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an integer")
    try:
        horizon = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} must be an integer") from exc
    if horizon < 1 or horizon > 2520:
        raise EFSError("CONTRACT_INVALID", f"{field} is outside the allowed range")
    if not isinstance(value, int) and str(horizon) != str(value):
        raise EFSError("CONTRACT_INVALID", f"{field} must use canonical integer text")
    return horizon


def _normalize_bundle(value: dict[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = canonical_json_bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise EFSError("CONTRACT_INVALID", "suite bundle must be an object or JSON payload")
    parsed = strict_json_loads(raw, max_bytes=DEFAULT_LIMITS["bundle_bytes"])
    if not isinstance(parsed, dict):
        raise EFSError("CONTRACT_INVALID", "suite bundle must be an object")
    validate_bundle(parsed)
    return parsed


class PreparedForecastSuite:
    """Opaque set of one-horizon bundles with a frozen shared scope."""

    __slots__ = (
        "__prepared",
        "calendar_id",
        "horizons",
        "scope_sha256",
        "suite_sha256",
    )

    def __init__(
        self,
        prepared: dict[int, PreparedBundle],
        *,
        calendar_id: str,
        scope_sha256: str,
        suite_sha256: str,
        token: object,
    ) -> None:
        if token is not _SUITE_TOKEN:
            raise TypeError("PreparedForecastSuite must be created by prepare_suite")
        self.__prepared = prepared
        self.calendar_id = calendar_id
        self.horizons = tuple(sorted(prepared))
        self.scope_sha256 = scope_sha256
        self.suite_sha256 = suite_sha256

    def _bundle_for(self, horizon: int, token: object) -> PreparedBundle:
        if token is not _SUITE_TOKEN:
            raise TypeError("suite internals are private")
        try:
            return self.__prepared[horizon]
        except KeyError as exc:
            raise EFSError("HORIZON_UNSUPPORTED", "requested horizon is not in the frozen suite") from exc


def prepare_suite(
    bundles: Iterable[dict[str, Any] | str | bytes],
    *,
    required_horizons: Iterable[int] | None = None,
) -> PreparedForecastSuite:
    source_bundles = _bounded_iterable(bundles, field="forecast suite bundles", maximum=MAX_SUITE_HORIZONS)
    normalized = [_normalize_bundle(item) for item in source_bundles]
    if not normalized:
        raise EFSError("CONTRACT_INVALID", "forecast suite must contain at least one bundle")

    prepared: dict[int, PreparedBundle] = {}
    first_scope = canonical_json_bytes(normalized[0]["scope"])
    first_calendar = normalized[0]["calendar_id"]
    for index, bundle in enumerate(normalized):
        horizons = bundle["horizons"]
        if len(horizons) != 1:
            raise EFSError("CONTRACT_INVALID", f"suite bundle {index} must bind exactly one horizon")
        horizon = int(horizons[0])
        if horizon in prepared:
            raise EFSError("CONTRACT_INVALID", "forecast suite contains a duplicate horizon")
        if canonical_json_bytes(bundle["scope"]) != first_scope:
            raise EFSError("UNIVERSE_MISMATCH", "all suite bundles must share an identical frozen scope")
        if bundle["calendar_id"] != first_calendar:
            raise EFSError("CONTRACT_INVALID", "all suite bundles must share a calendar")
        prepared[horizon] = prepare_bundle(bundle)

    if required_horizons is not None:
        source_required = _bounded_iterable(
            required_horizons,
            field="required horizons",
            maximum=MAX_SUITE_HORIZONS,
        )
        required = sorted({_horizon_key(item, field="required horizon") for item in source_required})
        if sorted(prepared) != required:
            raise EFSError("HORIZON_UNSUPPORTED", "suite does not exactly match the required horizon set")

    descriptor = {
        "schema": SUITE_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "calendar_id": first_calendar,
        "scope_sha256": sha256_hex(strict_json_loads(first_scope)),
        "bundles": [
            {
                "horizon": horizon,
                "bundle_id": prepared[horizon].bundle_id,
                "bundle_sha256": prepared[horizon].bundle_sha256,
                "model_set_sha256": prepared[horizon].model_set_sha256,
            }
            for horizon in sorted(prepared)
        ],
    }
    return PreparedForecastSuite(
        prepared,
        calendar_id=first_calendar,
        scope_sha256=descriptor["scope_sha256"],
        suite_sha256=sha256_hex(descriptor),
        token=_SUITE_TOKEN,
    )


def evaluate_suite(
    requests: Mapping[int | str, dict[str, Any] | str | bytes],
    suite: PreparedForecastSuite,
    trust_contexts: Mapping[int | str, dict[str, Any] | str | bytes | None] | None = None,
    *,
    require_complete: bool = True,
) -> dict[str, Any]:
    if not isinstance(suite, PreparedForecastSuite):
        raise EFSError("CONTRACT_INVALID", "prepared forecast suite is required")
    if not isinstance(requests, Mapping):
        raise EFSError("CONTRACT_INVALID", "suite requests must be a mapping")
    if len(requests) > MAX_SUITE_HORIZONS:
        raise EFSError("RESOURCE_LIMIT", "suite requests exceed the horizon limit")
    if not isinstance(require_complete, bool):
        raise EFSError("CONTRACT_INVALID", "require_complete must be a boolean")
    normalized_requests: dict[int, dict[str, Any] | str | bytes] = {}
    for raw_horizon, request in requests.items():
        horizon = _horizon_key(raw_horizon, field="suite request horizon")
        if horizon in normalized_requests:
            raise EFSError("CONTRACT_INVALID", "suite requests contain a duplicate horizon")
        normalized_requests[horizon] = request

    suite_horizons = set(suite.horizons)
    request_horizons = set(normalized_requests)
    if not request_horizons.issubset(suite_horizons):
        raise EFSError("HORIZON_UNSUPPORTED", "suite request contains an unsupported horizon")
    if require_complete and request_horizons != suite_horizons:
        raise EFSError("HORIZON_UNSUPPORTED", "complete suite evaluation requires every frozen horizon")

    if trust_contexts is None:
        trust_contexts = {}
    elif not isinstance(trust_contexts, Mapping):
        raise EFSError("CONTRACT_INVALID", "suite trust contexts must be a mapping")
    if len(trust_contexts) > MAX_SUITE_HORIZONS:
        raise EFSError("RESOURCE_LIMIT", "suite trust contexts exceed the horizon limit")
    normalized_trust: dict[int, Any] = {}
    for key, context in trust_contexts.items():
        horizon = _horizon_key(key, field="suite trust-context horizon")
        if horizon not in suite_horizons:
            raise EFSError("HORIZON_UNSUPPORTED", "trust context targets an unsupported horizon")
        if horizon in normalized_trust:
            raise EFSError("CONTRACT_INVALID", "suite trust contexts contain a duplicate horizon")
        normalized_trust[horizon] = context

    results: list[dict[str, Any]] = []
    for horizon in sorted(normalized_requests):
        prepared = suite._bundle_for(horizon, _SUITE_TOKEN)
        result = evaluate_prepared(normalized_requests[horizon], prepared, normalized_trust.get(horizon))
        if result.get("horizon") not in {None, horizon}:
            raise EFSError("CONTRACT_INVALID", "suite request key and request payload horizon disagree")
        results.append(result)

    forecast_count = sum(item.get("status") == "FORECAST" for item in results)
    if forecast_count == len(results):
        status = "ALL_FORECAST"
    elif forecast_count == 0:
        status = "ALL_ABSTAIN"
    else:
        status = "PARTIAL_ABSTAIN"
    envelope: dict[str, Any] = {
        "schema": SUITE_RESULT_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "suite_sha256": suite.suite_sha256,
        "calendar_id": suite.calendar_id,
        "scope_sha256": suite.scope_sha256,
        "horizons": list(suite.horizons),
        "status": status,
        "results": results,
        "cross_horizon_semantics": "NO_COMPOSITE_SCORE_NO_AUTOMATIC_TRADE_DECISION",
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    envelope["result_sha256"] = sha256_hex(envelope)
    return envelope
