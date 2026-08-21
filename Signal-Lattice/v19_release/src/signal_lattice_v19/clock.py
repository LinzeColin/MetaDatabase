from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sydney(value: datetime) -> datetime:
    return value.astimezone(SYDNEY)


def slot_start(value: datetime, seconds: int = 15) -> datetime:
    value = value.astimezone(timezone.utc)
    floored = value.second - (value.second % seconds)
    return value.replace(second=floored, microsecond=0)


def next_slot(value: datetime, seconds: int = 15) -> datetime:
    current = slot_start(value, seconds)
    if current <= value.astimezone(timezone.utc):
        current += timedelta(seconds=seconds)
    return current


def next_formal_review(value: datetime, minutes: int = 60) -> datetime:
    local = sydney(value)
    interval = max(1, min(int(minutes), 60))
    current = local.replace(
        minute=local.minute - (local.minute % interval), second=0, microsecond=0
    )
    return (current + timedelta(minutes=interval)).astimezone(timezone.utc)


def format_sydney(value: datetime) -> str:
    return sydney(value).strftime("%Y-%m-%d %H:%M:%S")


def sydney_date(value: datetime) -> str:
    return sydney(value).strftime("%Y-%m-%d")
