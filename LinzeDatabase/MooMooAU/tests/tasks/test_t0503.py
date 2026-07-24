from __future__ import annotations

import json
from datetime import UTC, date
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from stage5_support import recovery_context, timeline_event

from moomooau_archive.m3 import M3State
from moomooau_archive.market_calendar import ExpectationPolicy, USMarketCalendar
from moomooau_archive.timeline_event import TimelineEventFactory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_t0503_internal_date_is_utc_truth_and_sydney_dst_display_is_exact() -> None:
    with recovery_context() as context:
        event = timeline_event(context)
        assert event.email_internal_date_utc.tzinfo is UTC
        assert event.email_internal_date_utc == context.envelope.internal_date_utc
        assert event.email_received_at_sydney.isoformat() == "2026-01-01T11:00:00+11:00"
        assert event.statement_label_date == date(2025, 12, 31)
        assert event.calendar_lag_days == 1
        assert event.elapsed_hours == 35.0
        assert event.us_market_session_lag == 0
        assert event.date_header_observed == "Thu, 01 Jan 2099 00:00:00 +0000"
        assert event.label_state_at_discovery == ("CATEGORY_UPDATES", "INBOX")
        assert event.m3_state is M3State.TRASHED


def test_t0503_unknown_statement_date_keeps_all_lags_null_with_reason() -> None:
    with recovery_context(safe_deferred=True) as context:
        expectation = ExpectationPolicy().assess(
            observed=True,
            independent_activity_evidence=None,
            market_session_expected=None,
            sla_exceeded=None,
            parser_state=context.envelope.processing_state,
        )
        event = TimelineEventFactory(USMarketCalendar()).issue(
            context.envelope,
            statement_label_date=None,
            date_header_observed=None,
            m3_state=M3State.ELIGIBLE,
            expectation=expectation,
        )
        value = event.to_private_dict()
        assert value["statement_label_date"] is None
        assert value["calendar_lag_days"] is None
        assert value["elapsed_hours"] is None
        assert value["us_market_session_lag"] is None
        assert value["lag_reason_code"] == "STATEMENT_LABEL_DATE_UNKNOWN"
        assert value["parser_state"] == "UNSUPPORTED"
        schema = json.loads(
            (
                PROJECT_ROOT
                / "machine/stages/S5/public-schemas/timeline-event-complete-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        assert (
            list(
                Draft202012Validator(
                    schema,
                    format_checker=FormatChecker(),
                ).iter_errors(value)
            )
            == []
        )
