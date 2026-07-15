from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.sec_incremental_sync import (
    AUTO_DISABLE_AFTER_CONSECUTIVE_FAILURES,
    SCHEMA_VERSION,
    SecIncrementalSyncError,
    consecutive_leading_failures,
    handle_sec_incremental_sync_job,
    next_occurrence_key,
)


def test_consecutive_leading_failures_counts_from_most_recent() -> None:
    assert consecutive_leading_failures([]) == 0
    assert consecutive_leading_failures(["succeeded", "failed", "failed"]) == 0
    assert consecutive_leading_failures(["failed", "succeeded", "failed"]) == 1
    assert consecutive_leading_failures(["failed", "failed", "failed"]) == 3
    assert consecutive_leading_failures(["failed"] * 5 + ["succeeded"]) == 5


def test_auto_disable_threshold_is_three() -> None:
    assert AUTO_DISABLE_AFTER_CONSECUTIVE_FAILURES == 3


def test_next_occurrence_key_is_date_scoped_and_idempotent() -> None:
    after = datetime(2026, 7, 16, 8, 30, tzinfo=UTC)
    key, next_at = next_occurrence_key("sec_edgar", after)
    assert key == "sec-incremental-sync:sec_edgar:2026-07-17"
    assert next_at.date().isoformat() == "2026-07-17"
    key2, _ = next_occurrence_key("sec_edgar", after)
    assert key2 == key


def test_handler_rejects_wrong_schema_and_missing_network_optin() -> None:
    with pytest.raises(SecIncrementalSyncError):
        handle_sec_incremental_sync_job(
            {"id": "j1", "payload": {"schema_version": "wrong"}}
        )
    with pytest.raises(SecIncrementalSyncError):
        handle_sec_incremental_sync_job(
            {"id": "j2", "payload": {"schema_version": SCHEMA_VERSION}}
        )
