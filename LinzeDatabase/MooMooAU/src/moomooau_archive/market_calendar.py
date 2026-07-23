"""Pinned XNYS session semantics and fail-closed statement expectation policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

import exchange_calendars as xcals

from .processed_models import ProcessingState


class MarketCalendarError(RuntimeError):
    """The pinned exchange calendar could not answer a bounded date query."""


class ExpectationState(StrEnum):
    EXPECTED = "EXPECTED"
    NOT_EXPECTED = "NOT_EXPECTED"
    NOT_OBSERVED = "NOT_OBSERVED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ExpectationAssessment:
    state: ExpectationState
    reason_code: str

    def __post_init__(self) -> None:
        if not self.reason_code:
            raise MarketCalendarError("expectation assessment requires a reason")


class USMarketCalendar:
    """NYSE calendar adapter; sessions are counted after label date through arrival date."""

    calendar_name = "XNYS"

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar(self.calendar_name)

    def is_session(self, value: date) -> bool:
        try:
            return bool(self._calendar.is_session(value.isoformat()))
        except Exception as exc:
            raise MarketCalendarError("XNYS session lookup failed") from exc

    def session_lag(self, statement_label_date: date, arrival_sydney_date: date) -> int:
        if statement_label_date == arrival_sydney_date:
            return 0
        direction = 1 if arrival_sydney_date > statement_label_date else -1
        lower = min(statement_label_date, arrival_sydney_date)
        upper = max(statement_label_date, arrival_sydney_date)
        try:
            sessions = self._calendar.sessions_in_range(
                (lower + timedelta(days=1)).isoformat(),
                upper.isoformat(),
            )
        except Exception as exc:
            raise MarketCalendarError("XNYS session range lookup failed") from exc
        return direction * len(sessions)


class ExpectationPolicy:
    """Never infer a missing Daily Statement from the market calendar alone."""

    def assess(
        self,
        *,
        observed: bool,
        independent_activity_evidence: bool | None,
        market_session_expected: bool | None,
        sla_exceeded: bool | None,
        parser_state: ProcessingState | None,
    ) -> ExpectationAssessment:
        if parser_state is ProcessingState.WAITING_FOR_PDF_PASSWORD:
            return ExpectationAssessment(
                ExpectationState.UNKNOWN,
                "OBSERVED_BUT_PARSER_WAITING_FOR_PASSWORD",
            )
        if market_session_expected is False:
            return ExpectationAssessment(
                ExpectationState.NOT_EXPECTED,
                "US_MARKET_NOT_IN_SESSION",
            )
        if independent_activity_evidence is False:
            return ExpectationAssessment(
                ExpectationState.NOT_EXPECTED,
                "INDEPENDENT_ACTIVITY_ABSENT",
            )
        if independent_activity_evidence is True:
            if observed:
                return ExpectationAssessment(
                    ExpectationState.EXPECTED,
                    "INDEPENDENT_ACTIVITY_AND_STATEMENT_OBSERVED",
                )
            if sla_exceeded is True:
                return ExpectationAssessment(
                    ExpectationState.MISSING,
                    "INDEPENDENT_ACTIVITY_AND_SLA_EXCEEDED",
                )
            if sla_exceeded is False:
                return ExpectationAssessment(
                    ExpectationState.NOT_OBSERVED,
                    "INDEPENDENT_ACTIVITY_WITHIN_SLA",
                )
            return ExpectationAssessment(ExpectationState.UNKNOWN, "SLA_STATE_UNKNOWN")
        if not observed:
            return ExpectationAssessment(
                ExpectationState.NOT_OBSERVED,
                "NO_INDEPENDENT_ACTIVITY_EVIDENCE",
            )
        return ExpectationAssessment(
            ExpectationState.UNKNOWN,
            "OBSERVED_WITHOUT_INDEPENDENT_EXPECTATION_BASIS",
        )
