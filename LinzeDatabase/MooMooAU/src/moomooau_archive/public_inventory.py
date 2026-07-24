"""Strict bucket-only public inventory rendering for Stage 4."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .secret_values import SecretBytes

_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_SENTINEL = object()
_DATASETS = {
    "analytics",
    "cash_flows",
    "corporate_actions",
    "dividends",
    "document_envelopes",
    "fx",
    "statements",
    "timeline_events",
    "transactions",
}


class PublicInventoryError(RuntimeError):
    """Private details could not be reduced to the strict public contract."""


class DatasetAvailability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CountBucket(StrEnum):
    ZERO = "0"
    ONE_TO_NINE = "1-9"
    TEN_TO_NINETY_NINE = "10-99"
    ONE_HUNDRED_PLUS = "100+"


class FreshnessBucket(StrEnum):
    UNDER_24_HOURS = "<24h"
    ONE_TO_SEVEN_DAYS = "1-7d"
    OVER_SEVEN_DAYS = ">7d"
    NO_DATA = "no-data"


class PublicConclusion(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class PublicRunState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED_RAW_ONLY = "DEGRADED_RAW_ONLY"
    WAITING_PASSWORD = "WAITING_PASSWORD"  # pragma: allowlist secret
    M3_FAILED = "M3_FAILED"
    TIMELINE_FAILED = "TIMELINE_FAILED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"


class PublicNextAction(StrEnum):
    NONE = "NONE"
    RETRY = "RETRY"
    REPROCESS_WITH_PROTECTED_SECRET = (  # pragma: allowlist secret
        "REPROCESS_WITH_PROTECTED_SECRET"
    )
    REPAIR_M3 = "REPAIR_M3"
    REPAIR_TIMELINE = "REPAIR_TIMELINE"
    INVESTIGATE = "INVESTIGATE"
    RUN_PRODUCTION_ACCEPTANCE = "RUN_PRODUCTION_ACCEPTANCE"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDatasetObservation:
    dataset_name: str
    schema_version: str
    parser_versions: tuple[str, ...]
    availability: DatasetAvailability
    exact_count: int
    latest_recorded_at_utc: datetime | None
    private_snapshot_root: str

    def __post_init__(self) -> None:
        offset = (
            self.latest_recorded_at_utc.utcoffset()
            if self.latest_recorded_at_utc is not None
            else None
        )
        if (
            self.dataset_name not in _DATASETS
            or _SEMVER.fullmatch(self.schema_version) is None
            or not self.parser_versions
            or self.parser_versions != tuple(sorted(set(self.parser_versions)))
            or any(_SEMVER.fullmatch(value) is None for value in self.parser_versions)
            or type(self.exact_count) is not int
            or self.exact_count < 0
            or (self.exact_count == 0) != (self.latest_recorded_at_utc is None)
            or (self.availability is DatasetAvailability.AVAILABLE and self.exact_count == 0)
            or (self.availability is DatasetAvailability.UNAVAILABLE and self.exact_count != 0)
            or (
                self.latest_recorded_at_utc is not None
                and (
                    self.latest_recorded_at_utc.tzinfo is None
                    or offset is None
                    or offset.total_seconds() != 0
                )
            )
            or _SHA256.fullmatch(self.private_snapshot_root) is None
        ):
            raise PublicInventoryError("private dataset observation is invalid")

    def __repr__(self) -> str:
        return (
            f"PrivateDatasetObservation(dataset_name={self.dataset_name!r}, "
            f"schema_version={self.schema_version!r}, parser_versions={self.parser_versions!r}, "
            f"availability={self.availability.value!r}, exact_count=<redacted>, "
            "latest_recorded_at_utc=<redacted>, private_snapshot_root=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class PublicRunConclusion:
    run_state: PublicRunState
    test_conclusion: PublicConclusion
    recovery_conclusion: PublicConclusion
    next_action: PublicNextAction

    def __post_init__(self) -> None:
        required_action = {
            PublicRunState.HEALTHY: PublicNextAction.NONE,
            PublicRunState.DEGRADED_RAW_ONLY: PublicNextAction.RETRY,
            PublicRunState.WAITING_PASSWORD: PublicNextAction.REPROCESS_WITH_PROTECTED_SECRET,
            PublicRunState.M3_FAILED: PublicNextAction.REPAIR_M3,
            PublicRunState.TIMELINE_FAILED: PublicNextAction.REPAIR_TIMELINE,
            PublicRunState.FAILED: PublicNextAction.INVESTIGATE,
            PublicRunState.NOT_RUN: PublicNextAction.RUN_PRODUCTION_ACCEPTANCE,
        }[self.run_state]
        if self.next_action is not required_action:
            raise PublicInventoryError("public run state and next action do not match")
        if self.run_state is PublicRunState.HEALTHY and (
            self.test_conclusion is not PublicConclusion.PASS
            or self.recovery_conclusion is not PublicConclusion.PASS
        ):
            raise PublicInventoryError("healthy public conclusion lacks passing evidence")
        if self.run_state is PublicRunState.NOT_RUN and (
            self.test_conclusion is not PublicConclusion.NOT_RUN
            or self.recovery_conclusion is not PublicConclusion.NOT_RUN
        ):
            raise PublicInventoryError("not-run public conclusion is inconsistent")


@dataclass(frozen=True, slots=True, repr=False)
class PublicInventoryDocument:
    schema_version: str
    opaque_root: str
    dataset_count: int
    payload_sha256: str
    payload: bytes = field(repr=False)
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._sentinel is not _PUBLIC_SENTINEL
            or self.schema_version != "1.0.0"
            or _SHA256.fullmatch(self.opaque_root) is None
            or type(self.dataset_count) is not int
            or self.dataset_count <= 0
            or _SHA256.fullmatch(self.payload_sha256) is None
            or hashlib.sha256(self.payload).hexdigest() != self.payload_sha256
            or not self.payload.endswith(b"\n")
        ):
            raise PublicInventoryError("public inventory document is invalid")

    def __repr__(self) -> str:
        return (
            f"PublicInventoryDocument(schema_version={self.schema_version!r}, "
            "opaque_root=<redacted>, "
            f"dataset_count={self.dataset_count}, payload_sha256={self.payload_sha256!r}, "
            "payload=<redacted>)"
        )


class StrictPublicInventoryPublisher:
    """Render only allowlisted buckets and HMAC roots; this class performs no external write."""

    def render(
        self,
        observations: tuple[PrivateDatasetObservation, ...],
        conclusion: PublicRunConclusion,
        *,
        now_utc: datetime,
        opaque_root_key: SecretBytes,
    ) -> PublicInventoryDocument:
        current = _require_utc(now_utc)
        if not observations:
            raise PublicInventoryError("public inventory requires at least one dataset")
        ordered = tuple(sorted(observations, key=lambda item: item.dataset_name))
        if len({item.dataset_name for item in ordered}) != len(ordered):
            raise PublicInventoryError("public inventory dataset names are duplicated")
        key = opaque_root_key.reveal()
        if len(key) < 32:
            raise PublicInventoryError("public opaque-root key is too short")
        private_binding = _canonical_json(
            [
                {
                    "dataset_name": item.dataset_name,
                    "private_snapshot_root": item.private_snapshot_root,
                }
                for item in ordered
            ]
        )
        opaque_root = hmac.digest(
            key,
            b"moomooau-public-inventory-root\x00" + private_binding,
            "sha256",
        ).hex()
        value = {
            "schema_version": "moomooau.public-inventory.v1",
            "opaque_root": opaque_root,
            "run": {
                "state": conclusion.run_state.value,
                "test_conclusion": conclusion.test_conclusion.value,
                "recovery_conclusion": conclusion.recovery_conclusion.value,
                "next_action": conclusion.next_action.value,
            },
            "datasets": [
                {
                    "dataset_name": item.dataset_name,
                    "schema_version": item.schema_version,
                    "parser_versions": list(item.parser_versions),
                    "availability": item.availability.value,
                    "count_bucket": _count_bucket(item.exact_count).value,
                    "freshness_bucket": _freshness_bucket(
                        item.latest_recorded_at_utc,
                        current,
                    ).value,
                }
                for item in ordered
            ],
        }
        payload = _canonical_json(value) + b"\n"
        _validate_public_shape(payload)
        return PublicInventoryDocument(
            schema_version="1.0.0",
            opaque_root=opaque_root,
            dataset_count=len(ordered),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            payload=payload,
            _sentinel=_PUBLIC_SENTINEL,
        )


def _count_bucket(exact_count: int) -> CountBucket:
    if exact_count == 0:
        return CountBucket.ZERO
    if exact_count < 10:
        return CountBucket.ONE_TO_NINE
    if exact_count < 100:
        return CountBucket.TEN_TO_NINETY_NINE
    return CountBucket.ONE_HUNDRED_PLUS


def _freshness_bucket(latest: datetime | None, now: datetime) -> FreshnessBucket:
    if latest is None:
        return FreshnessBucket.NO_DATA
    if latest > now:
        raise PublicInventoryError("private dataset freshness is in the future")
    age = now - latest
    if age < timedelta(hours=24):
        return FreshnessBucket.UNDER_24_HOURS
    if age <= timedelta(days=7):
        return FreshnessBucket.ONE_TO_SEVEN_DAYS
    return FreshnessBucket.OVER_SEVEN_DAYS


def _validate_public_shape(payload: bytes) -> None:
    text = payload.decode("utf-8")
    forbidden = (
        "MooMooAU/",
        "source_id",
        "message_id",
        "subject",
        "sender",
        "filename",
        "account",
        "ticker",
        "amount",
        "exact_count",
        "latest_recorded_at",
        "private_snapshot_root",
        "commit_url",
    )
    if any(token.casefold() in text.casefold() for token in forbidden):
        raise PublicInventoryError("public inventory contains a forbidden private field")
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        raise PublicInventoryError("public inventory contains an email address")


def _require_utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise PublicInventoryError("public inventory clock must be UTC")
    return value.astimezone(UTC)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
