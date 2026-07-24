from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from moomooau_archive.run_schedule import (
    TARGET_CRON,
    TARGET_TIMEZONE,
    RunMode,
    RunPlanner,
    RunScheduleError,
    RunTrigger,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_t0507_sydney_schedule_is_dst_aware_and_sunday_is_full_reconcile() -> None:
    planner = RunPlanner()
    winter = planner.plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 18, 18, 30, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 7, 18),
    )
    summer = planner.plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 1, 3, 17, 30, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 1, 3),
    )
    assert winter.run_date_sydney == date(2026, 7, 19)
    assert winter.target_at_sydney.isoformat() == "2026-07-19T04:30:00+10:00"
    assert summer.target_at_sydney.isoformat() == "2026-01-04T04:30:00+11:00"
    assert winter.mode is summer.mode is RunMode.FULL_SUNDAY
    assert winter.full_reconcile and summer.full_reconcile


def test_t0507_delayed_schedule_catches_up_without_claiming_platform_sla() -> None:
    plan = RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 19, 18, 37, tzinfo=UTC),
        last_successful_run_date_sydney=date(2026, 7, 17),
    )
    assert plan.run_date_sydney == date(2026, 7, 20)
    assert plan.mode is RunMode.INCREMENTAL
    assert plan.schedule_delay_minutes == 7
    assert plan.missed_run_days == 2
    assert plan.catch_up_required
    assert plan.to_public_dict()["platform_sla_claimed"] is False


def test_t0507_manual_dispatch_is_full_and_pre_target_schedule_fails_closed() -> None:
    manual = RunPlanner().plan(
        RunTrigger.WORKFLOW_DISPATCH,
        started_at_utc=datetime(2026, 7, 20, 3, tzinfo=UTC),
        last_successful_run_date_sydney=None,
    )
    assert manual.mode is RunMode.FULL_MANUAL
    assert manual.schedule_delay_minutes is None
    with pytest.raises(RunScheduleError, match="before"):
        RunPlanner().plan(
            RunTrigger.SCHEDULE,
            started_at_utc=datetime(2026, 7, 19, 18, 29, tzinfo=UTC),
            last_successful_run_date_sydney=None,
        )


def test_t0507_workflow_has_exact_schedule_and_no_persistent_image_channel() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/moomooau-production.yml").read_text(
        encoding="utf-8"
    )
    assert f'cron: "{TARGET_CRON}"' in workflow
    assert f'timezone: "{TARGET_TIMEZONE}"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "MOOMOOAU_PRODUCTION_ENABLED" in workflow
    assert "self-hosted" not in workflow
    assert "actions/cache" not in workflow
    assert "upload-artifact" not in workflow
    assert "download-artifact" not in workflow
