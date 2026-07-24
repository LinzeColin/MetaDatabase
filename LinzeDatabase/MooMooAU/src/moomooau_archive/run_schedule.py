"""Timezone-aware daily, Sunday and manual run planning without local state."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")
TARGET_LOCAL_TIME = time(4, 30)
TARGET_CRON = "30 4 * * *"
TARGET_TIMEZONE = "Australia/Sydney"


class RunScheduleError(RuntimeError):
    """A run trigger or remote watermark is invalid."""


class RunTrigger(StrEnum):
    SCHEDULE = "schedule"
    WORKFLOW_DISPATCH = "workflow_dispatch"


class RunMode(StrEnum):
    INCREMENTAL = "INCREMENTAL"
    FULL_SUNDAY = "FULL_SUNDAY"
    FULL_MANUAL = "FULL_MANUAL"


@dataclass(frozen=True, slots=True)
class ScheduledRunPlan:
    trigger: RunTrigger
    mode: RunMode
    run_date_sydney: date
    target_at_sydney: datetime
    started_at_utc: datetime
    schedule_delay_minutes: int | None
    missed_run_days: int
    catch_up_required: bool
    full_reconcile: bool

    def __post_init__(self) -> None:
        offset = self.started_at_utc.utcoffset()
        if (
            self.started_at_utc.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
            or getattr(self.target_at_sydney.tzinfo, "key", None) != TARGET_TIMEZONE
            or self.target_at_sydney.date() != self.run_date_sydney
            or self.target_at_sydney.timetz().replace(tzinfo=None) != TARGET_LOCAL_TIME
            or self.missed_run_days < 0
            or self.catch_up_required != (self.missed_run_days > 0)
            or self.full_reconcile != (self.mode is not RunMode.INCREMENTAL)
            or (self.trigger is RunTrigger.SCHEDULE) != (self.schedule_delay_minutes is not None)
        ):
            raise RunScheduleError("scheduled run plan is invalid")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.scheduled-run-plan.v1",
            "trigger": self.trigger.value,
            "mode": self.mode.value,
            "run_date_sydney": self.run_date_sydney.isoformat(),
            "target_time": "04:30",
            "timezone": TARGET_TIMEZONE,
            "schedule_delay_minutes": self.schedule_delay_minutes,
            "missed_run_days": self.missed_run_days,
            "catch_up_required": self.catch_up_required,
            "full_reconcile": self.full_reconcile,
            "platform_sla_claimed": False,
        }


class RunPlanner:
    def plan(
        self,
        trigger: RunTrigger,
        *,
        started_at_utc: datetime,
        last_successful_run_date_sydney: date | None,
    ) -> ScheduledRunPlan:
        offset = started_at_utc.utcoffset()
        if started_at_utc.tzinfo is None or offset is None or offset.total_seconds() != 0:
            raise RunScheduleError("run start must be UTC")
        local = started_at_utc.astimezone(SYDNEY)
        run_date = local.date()
        target = datetime.combine(run_date, TARGET_LOCAL_TIME, tzinfo=SYDNEY)
        if last_successful_run_date_sydney is not None and (
            last_successful_run_date_sydney >= run_date
        ):
            missed = 0
        elif last_successful_run_date_sydney is None:
            missed = 0
        else:
            missed = max(0, (run_date - last_successful_run_date_sydney).days - 1)

        delay: int | None = None
        if trigger is RunTrigger.SCHEDULE:
            delay = round((local - target).total_seconds() / 60)
            if delay < 0:
                raise RunScheduleError("scheduled run started before its Sydney target")
            mode = RunMode.FULL_SUNDAY if run_date.weekday() == 6 else RunMode.INCREMENTAL
        else:
            mode = RunMode.FULL_MANUAL
        return ScheduledRunPlan(
            trigger=trigger,
            mode=mode,
            run_date_sydney=run_date,
            target_at_sydney=target,
            started_at_utc=started_at_utc,
            schedule_delay_minutes=delay,
            missed_run_days=missed,
            catch_up_required=missed > 0,
            full_reconcile=mode is not RunMode.INCREMENTAL,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", choices=[item.value for item in RunTrigger], required=True)
    parser.add_argument("--now-utc")
    parser.add_argument("--last-successful-run-date-sydney")
    args = parser.parse_args(argv)
    now = datetime.now(UTC) if args.now_utc is None else _parse_utc(args.now_utc)
    last = (
        None
        if args.last_successful_run_date_sydney is None
        else date.fromisoformat(args.last_successful_run_date_sydney)
    )
    result = RunPlanner().plan(
        RunTrigger(args.event_name),
        started_at_utc=now,
        last_successful_run_date_sydney=last,
    )
    print(json.dumps(result.to_public_dict(), sort_keys=True, separators=(",", ":")))
    return 0


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunScheduleError("run timestamp is invalid") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise RunScheduleError("run timestamp must be UTC")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
