from __future__ import annotations

from datetime import date

from moomooau_archive.market_calendar import (
    ExpectationPolicy,
    ExpectationState,
    USMarketCalendar,
)
from moomooau_archive.processed_models import ProcessingState


def test_t0504_xnys_session_lag_excludes_weekends_and_us_independence_day_closure() -> None:
    calendar = USMarketCalendar()
    assert not calendar.is_session(date(2026, 7, 3))
    assert not calendar.is_session(date(2026, 7, 4))
    assert not calendar.is_session(date(2026, 7, 5))
    assert calendar.is_session(date(2026, 7, 6))
    assert calendar.session_lag(date(2026, 7, 2), date(2026, 7, 6)) == 1
    assert calendar.session_lag(date(2026, 7, 6), date(2026, 7, 2)) == -1


def test_t0504_missing_requires_independent_activity_and_exceeded_sla() -> None:
    policy = ExpectationPolicy()
    missing = policy.assess(
        observed=False,
        independent_activity_evidence=True,
        market_session_expected=True,
        sla_exceeded=True,
        parser_state=None,
    )
    no_evidence = policy.assess(
        observed=False,
        independent_activity_evidence=None,
        market_session_expected=True,
        sla_exceeded=True,
        parser_state=None,
    )
    closed = policy.assess(
        observed=False,
        independent_activity_evidence=True,
        market_session_expected=False,
        sla_exceeded=True,
        parser_state=None,
    )
    waiting = policy.assess(
        observed=True,
        independent_activity_evidence=True,
        market_session_expected=True,
        sla_exceeded=True,
        parser_state=ProcessingState.WAITING_FOR_PDF_PASSWORD,
    )
    assert missing.state is ExpectationState.MISSING
    assert no_evidence.state is ExpectationState.NOT_OBSERVED
    assert closed.state is ExpectationState.NOT_EXPECTED
    assert waiting.state is ExpectationState.UNKNOWN
    assert all(
        item.state is not ExpectationState.MISSING for item in (no_evidence, closed, waiting)
    )
