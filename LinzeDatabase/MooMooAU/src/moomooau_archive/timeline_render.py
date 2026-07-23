"""Byte-deterministic, fixed-layout private Timeline PNG renderer."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from .market_calendar import USMarketCalendar
from .timeline_event import TimelineEvent

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class TimelineRenderError(RuntimeError):
    """Timeline rendering failed without disclosing private event values."""


@dataclass(frozen=True, slots=True, repr=False)
class RenderedTimeline:
    processed_snapshot_root: str
    timeline_plaintext_sha256: str
    event_count: int
    png: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            _SHA256.fullmatch(self.processed_snapshot_root) is None
            or _SHA256.fullmatch(self.timeline_plaintext_sha256) is None
            or self.timeline_plaintext_sha256 != hashlib.sha256(self.png).hexdigest()
            or not self.png.startswith(_PNG_SIGNATURE)
            or type(self.event_count) is not int
            or self.event_count < 0
        ):
            raise TimelineRenderError("rendered Timeline is invalid")

    def __repr__(self) -> str:
        return (
            "RenderedTimeline(processed_snapshot_root=<redacted>, "
            "timeline_plaintext_sha256=<redacted>, "
            f"event_count={self.event_count}, png=<redacted>)"
        )


class TimelineRendererPort(Protocol):
    def render(
        self,
        events: tuple[TimelineEvent, ...],
        processed_snapshot_root: str,
    ) -> RenderedTimeline: ...


class DeterministicTimelineRenderer:
    """Fixed pixels, bundled Pillow default font, order and PNG encoding."""

    width = 1200
    height = 720
    maximum_events = 5000

    def __init__(self, market_calendar: USMarketCalendar | None = None) -> None:
        self._market_calendar = market_calendar or USMarketCalendar()

    def render(
        self,
        events: tuple[TimelineEvent, ...],
        processed_snapshot_root: str,
    ) -> RenderedTimeline:
        if _SHA256.fullmatch(processed_snapshot_root) is None:
            raise TimelineRenderError("Processed snapshot root is invalid")
        if len(events) > self.maximum_events:
            raise TimelineRenderError("Timeline event limit exceeded")
        ordered = tuple(sorted(events, key=_event_key))
        if len({item.source_id for item in ordered}) != len(ordered):
            raise TimelineRenderError("Timeline source IDs are not unique")

        image = Image.new("RGB", (self.width, self.height), "#ffffff")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.text((40, 28), "MooMoo AU Archive Timeline", fill="#17202a", font=font)
        draw.text(
            (40, 50),
            "Sydney arrival from Gmail internalDate; statement dates are business labels",
            fill="#566573",
            font=font,
        )
        left, right = 80, self.width - 60
        top, bottom = 110, self.height - 100
        draw.rectangle((left, top, right, bottom), outline="#aeb6bf", width=1)

        dates = [item.email_received_at_sydney.date() for item in ordered]
        dates.extend(
            item.statement_label_date for item in ordered if item.statement_label_date is not None
        )
        start = min(dates) if dates else date(2000, 1, 1)
        end = max(dates) if dates else start
        span = max(1, (end - start).days)

        for offset in range(span + 1):
            day = start + timedelta(days=offset)
            x = _x(day, start, span, left, right)
            next_x = _x(day + timedelta(days=1), start, span, left, right)
            if day.weekday() >= 5:
                draw.rectangle((x, top + 1, next_x, bottom - 1), fill="#f4f6f7")
            elif not self._market_calendar.is_session(day):
                draw.rectangle((x, top + 1, next_x, bottom - 1), fill="#fdf2e9")
        draw.line((left, bottom - 35, right, bottom - 35), fill="#5d6d7e", width=2)

        lanes = max(1, min(24, len(ordered)))
        for index, event in enumerate(ordered):
            y = top + 28 + (index % lanes) * max(16, (bottom - top - 90) // lanes)
            arrival_x = _x(event.email_received_at_sydney.date(), start, span, left, right)
            statement_x = (
                _x(event.statement_label_date, start, span, left, right)
                if event.statement_label_date is not None
                else None
            )
            color = _event_color(event.document_class)
            if statement_x is not None:
                draw.line((statement_x, y, arrival_x, y), fill=color, width=2)
                _statement_shape(draw, statement_x, y, event.document_class, color)
            draw.rectangle((arrival_x - 4, y - 4, arrival_x + 4, y + 4), fill=color)
            draw.text(
                (max(left, arrival_x - 5), y + 6),
                _m3_marker(event.m3_state.value),
                fill=color,
                font=font,
            )
            if event.calendar_lag_days is not None:
                draw.text(
                    (min(arrival_x + 6, right - 80), y - 7),
                    f"{event.calendar_lag_days}d/{event.us_market_session_lag}s",
                    fill="#34495e",
                    font=font,
                )

        draw.text((left, bottom + 14), start.isoformat(), fill="#34495e", font=font)
        end_label = end.isoformat()
        draw.text((right - 70, bottom + 14), end_label, fill="#34495e", font=font)
        draw.text(
            (left, self.height - 45),
            "circle/diamond = statement label; square = Gmail arrival; "
            "grey = weekend; tan = XNYS closed",
            fill="#566573",
            font=font,
        )

        sink = io.BytesIO()
        image.save(sink, format="PNG", optimize=False, compress_level=9, pnginfo=None)
        png = sink.getvalue()
        return RenderedTimeline(
            processed_snapshot_root=processed_snapshot_root,
            timeline_plaintext_sha256=hashlib.sha256(png).hexdigest(),
            event_count=len(ordered),
            png=png,
        )


def _event_key(event: TimelineEvent) -> tuple[date, str, str]:
    label = event.statement_label_date or event.email_received_at_sydney.date()
    return (label, event.email_internal_date_utc.isoformat(), event.source_id)


def _x(value: date, start: date, span: int, left: int, right: int) -> int:
    return left + round((value - start).days * (right - left) / span)


def _event_color(document_class: str) -> str:
    if document_class == "MONTHLY_STATEMENT":
        return "#8e44ad"
    if document_class == "FINANCIAL_YEAR_SUMMARY":
        return "#d35400"
    if document_class == "CONTRACT_NOTE":
        return "#117864"
    return "#21618c"


def _m3_marker(state: str) -> str:
    return {
        "TRASHED": "T",
        "ALREADY_TRASHED": "A",
        "ELIGIBLE": "E",
        "NOT_ELIGIBLE": "N",
        "FAILED": "F",
        "UNKNOWN": "?",
    }[state]


def _statement_shape(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    document_class: str,
    color: str,
) -> None:
    if document_class in {"MONTHLY_STATEMENT", "FINANCIAL_YEAR_SUMMARY"}:
        draw.polygon(((x, y - 6), (x + 6, y), (x, y + 6), (x - 6, y)), fill=color)
    else:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)
