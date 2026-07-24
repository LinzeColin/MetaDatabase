"""Deterministic private Timeline Event derived from Gmail internalDate."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import cast
from zoneinfo import ZoneInfo

from .m3 import M3State
from .market_calendar import ExpectationAssessment, ExpectationState, USMarketCalendar
from .processed_models import DocumentClass, DocumentEnvelope, ProcessingState

_SOURCE_ID = re.compile(r"^[0-9a-f]{64}$")


class TimelineEventError(RuntimeError):
    """Timeline input or time semantics are invalid."""


@dataclass(frozen=True, slots=True, repr=False)
class TimelineEvent:
    source_id: str
    document_class: str
    statement_label_date: date | None
    email_internal_date_utc: datetime
    email_received_at_sydney: datetime
    date_header_observed: str | None
    calendar_lag_days: int | None
    elapsed_hours: float | None
    us_market_session_lag: int | None
    lag_reason_code: str | None
    label_state_at_discovery: tuple[str, ...]
    m3_state: M3State
    expectation_state: str
    expectation_reason_code: str
    parser_state: str

    def __post_init__(self) -> None:
        utc_offset = self.email_internal_date_utc.utcoffset()
        sydney_offset = self.email_received_at_sydney.utcoffset()
        lags = (self.calendar_lag_days, self.elapsed_hours, self.us_market_session_lag)
        known_document_classes = {item.value for item in DocumentClass}
        known_expectation_states = {item.value for item in ExpectationState}
        known_parser_states = {item.value for item in ProcessingState}
        if (
            _SOURCE_ID.fullmatch(self.source_id) is None
            or self.document_class not in known_document_classes
            or (
                self.statement_label_date is not None
                and type(self.statement_label_date) is not date
            )
            or self.email_internal_date_utc.tzinfo is None
            or utc_offset is None
            or utc_offset.total_seconds() != 0
            or self.email_received_at_sydney.tzinfo is None
            or sydney_offset is None
            or getattr(self.email_received_at_sydney.tzinfo, "key", None) != "Australia/Sydney"
            or self.email_received_at_sydney.astimezone(UTC) != self.email_internal_date_utc
            or (self.statement_label_date is None) != all(value is None for value in lags)
            or (self.statement_label_date is None) != (self.lag_reason_code is not None)
            or (self.calendar_lag_days is not None and type(self.calendar_lag_days) is not int)
            or (
                self.elapsed_hours is not None
                and (type(self.elapsed_hours) is not float or not math.isfinite(self.elapsed_hours))
            )
            or (
                self.us_market_session_lag is not None
                and type(self.us_market_session_lag) is not int
            )
            or not isinstance(self.m3_state, M3State)
            or self.label_state_at_discovery != tuple(sorted(self.label_state_at_discovery))
            or len(self.label_state_at_discovery) != len(set(self.label_state_at_discovery))
            or any(
                not isinstance(label, str)
                or not label
                or len(label) > 256
                or "\r" in label
                or "\n" in label
                for label in self.label_state_at_discovery
            )
            or self.expectation_state not in known_expectation_states
            or not _safe_reason(self.expectation_reason_code)
            or self.parser_state not in known_parser_states
            or (self.lag_reason_code is not None and not _safe_reason(self.lag_reason_code))
            or (
                self.date_header_observed is not None
                and (
                    not self.date_header_observed
                    or len(self.date_header_observed) > 16_384
                    or "\r" in self.date_header_observed
                    or "\n" in self.date_header_observed
                )
            )
        ):
            raise TimelineEventError("Timeline Event is invalid")

    def __repr__(self) -> str:
        return (
            "TimelineEvent(source_id=<redacted>, "
            f"document_class={self.document_class!r}, statement_label_date=<redacted>, "
            "email_internal_date_utc=<redacted>, email_received_at_sydney=<redacted>, "
            f"m3_state={self.m3_state.value!r}, "
            f"expectation_state={self.expectation_state!r}, parser_state={self.parser_state!r})"
        )

    def to_private_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "source_id": self.source_id,
            "document_class": self.document_class,
            "statement_label_date": (
                self.statement_label_date.isoformat()
                if self.statement_label_date is not None
                else None
            ),
            "email_internal_date_utc": _utc_text(self.email_internal_date_utc),
            "email_received_at_sydney": self.email_received_at_sydney.isoformat(),
            "date_header_observed": self.date_header_observed,
            "calendar_lag_days": self.calendar_lag_days,
            "elapsed_hours": self.elapsed_hours,
            "us_market_session_lag": self.us_market_session_lag,
            "lag_reason_code": self.lag_reason_code,
            "label_state_at_discovery": list(self.label_state_at_discovery),
            "m3_state": self.m3_state.value,
            "expectation_state": self.expectation_state,
            "expectation_reason_code": self.expectation_reason_code,
            "parser_state": self.parser_state,
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_private_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, payload: bytes) -> TimelineEvent:
        if not payload or len(payload) > 1024 * 1024:
            raise TimelineEventError("Timeline Event payload exceeds the safe limit")
        try:
            value = json.loads(payload, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise TimelineEventError("Timeline Event payload is invalid JSON") from exc
        required = {
            "schema_version",
            "source_id",
            "document_class",
            "statement_label_date",
            "email_internal_date_utc",
            "email_received_at_sydney",
            "date_header_observed",
            "calendar_lag_days",
            "elapsed_hours",
            "us_market_session_lag",
            "lag_reason_code",
            "label_state_at_discovery",
            "m3_state",
            "expectation_state",
            "expectation_reason_code",
            "parser_state",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schema_version") != "1.0.0"
        ):
            raise TimelineEventError("Timeline Event payload schema is invalid")
        item = cast(dict[str, object], value)
        labels = item.get("label_state_at_discovery")
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise TimelineEventError("Timeline Event labels are invalid")
        statement_text = item.get("statement_label_date")
        if statement_text is not None and not isinstance(statement_text, str):
            raise TimelineEventError("Timeline Event statement date is invalid")
        date_header = item.get("date_header_observed")
        lag_reason = item.get("lag_reason_code")
        if date_header is not None and not isinstance(date_header, str):
            raise TimelineEventError("Timeline Event Date header is invalid")
        if lag_reason is not None and not isinstance(lag_reason, str):
            raise TimelineEventError("Timeline Event lag reason is invalid")
        try:
            event = cls(
                source_id=_required_string(item, "source_id"),
                document_class=_required_string(item, "document_class"),
                statement_label_date=(
                    date.fromisoformat(statement_text) if statement_text is not None else None
                ),
                email_internal_date_utc=_parse_utc(
                    _required_string(item, "email_internal_date_utc")
                ),
                email_received_at_sydney=_parse_sydney(
                    _required_string(item, "email_received_at_sydney")
                ),
                date_header_observed=date_header,
                calendar_lag_days=_optional_int(item, "calendar_lag_days"),
                elapsed_hours=_optional_number(item, "elapsed_hours"),
                us_market_session_lag=_optional_int(item, "us_market_session_lag"),
                lag_reason_code=lag_reason,
                label_state_at_discovery=tuple(labels),
                m3_state=M3State(_required_string(item, "m3_state")),
                expectation_state=_required_string(item, "expectation_state"),
                expectation_reason_code=_required_string(item, "expectation_reason_code"),
                parser_state=_required_string(item, "parser_state"),
            )
        except (TypeError, ValueError) as exc:
            raise TimelineEventError("Timeline Event payload value is invalid") from exc
        if event.canonical_bytes() != payload:
            raise TimelineEventError("Timeline Event payload is not canonical")
        return event


class TimelineEventFactory:
    """Use statement label date for business lag and never parse Date as arrival truth."""

    def __init__(self, market_calendar: USMarketCalendar) -> None:
        self._market_calendar = market_calendar

    def issue(
        self,
        envelope: DocumentEnvelope,
        *,
        statement_label_date: date | None,
        date_header_observed: str | None,
        m3_state: M3State,
        expectation: ExpectationAssessment,
    ) -> TimelineEvent:
        arrival = envelope.received_at_sydney
        calendar_lag: int | None = None
        elapsed_hours: float | None = None
        market_lag: int | None = None
        lag_reason: str | None = "STATEMENT_LABEL_DATE_UNKNOWN"
        if statement_label_date is not None:
            calendar_lag = (arrival.date() - statement_label_date).days
            statement_midnight = datetime.combine(
                statement_label_date,
                time.min,
                tzinfo=arrival.tzinfo,
            )
            elapsed_hours = round(
                (arrival.astimezone(UTC) - statement_midnight.astimezone(UTC)).total_seconds()
                / 3600,
                6,
            )
            market_lag = self._market_calendar.session_lag(
                statement_label_date,
                arrival.date(),
            )
            lag_reason = None
        return TimelineEvent(
            source_id=envelope.source_id,
            document_class=envelope.document_class.value,
            statement_label_date=statement_label_date,
            email_internal_date_utc=envelope.internal_date_utc,
            email_received_at_sydney=arrival,
            date_header_observed=date_header_observed,
            calendar_lag_days=calendar_lag,
            elapsed_hours=elapsed_hours,
            us_market_session_lag=market_lag,
            lag_reason_code=lag_reason,
            label_state_at_discovery=envelope.label_state,
            m3_state=m3_state,
            expectation_state=expectation.state.value,
            expectation_reason_code=expectation.reason_code,
            parser_state=envelope.processing_state.value,
        )


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_reason(value: str) -> bool:
    return bool(value) and len(value) <= 256 and "\r" not in value and "\n" not in value


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise TimelineEventError("Timeline Event string field is invalid")
    return item


def _optional_int(value: dict[str, object], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, int) or isinstance(item, bool):
        raise TimelineEventError("Timeline Event integer field is invalid")
    return item


def _optional_number(value: dict[str, object], key: str) -> float | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise TimelineEventError("Timeline Event numeric field is invalid")
    number = float(item)
    if not math.isfinite(number):
        raise TimelineEventError("Timeline Event numeric field is invalid")
    return number


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise TimelineEventError("Timeline Event UTC timestamp is invalid")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise TimelineEventError("Timeline Event UTC timestamp is invalid")
    return parsed.astimezone(UTC)


def _parse_sydney(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TimelineEventError("Timeline Event Sydney timestamp is invalid")
    sydney = parsed.astimezone(ZoneInfo("Australia/Sydney"))
    if sydney.isoformat() != value:
        raise TimelineEventError("Timeline Event Sydney offset is invalid")
    return sydney


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is forbidden")
