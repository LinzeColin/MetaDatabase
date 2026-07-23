from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from stage3_support import (
    SyntheticGmailMessage,
    SyntheticGmailTransport,
    make_raw_message,
    metadata_headers,
)

from moomooau_archive.gmail_discovery import (
    FullMailboxDiscoverer,
    GmailDiscoveryError,
    GmailReadClient,
    GmailReconciler,
    MessageRef,
    ReconcileMode,
    SyncState,
)
from moomooau_archive.gmail_guard import GmailEndpointGuard

SYDNEY = ZoneInfo("Australia/Sydney")


def _message(
    message_id: str,
    history_id: str = "200",
    *,
    labels: tuple[str, ...] = ("INBOX",),
) -> SyntheticGmailMessage:
    return SyntheticGmailMessage(
        message_id=message_id,
        thread_id="thread-" + message_id,
        labels=labels,
        history_id=history_id,
        internal_date_ms=1_767_225_600_000,
        headers=metadata_headers(),
        raw=make_raw_message(message_id=message_id),
    )


def _reconciler(transport: SyntheticGmailTransport) -> GmailReconciler:
    client = GmailReadClient(GmailEndpointGuard(transport))
    return GmailReconciler(client, FullMailboxDiscoverer(client))


def test_t0302_history_pages_apply_once_and_advance_watermark_only_at_end() -> None:
    pages = (
        {
            "history": [
                {
                    "id": "101",
                    "messagesAdded": [
                        {"message": {"id": "synthetic-2", "threadId": "thread-synthetic-2"}}
                    ],
                    "labelsAdded": [
                        {"message": {"id": "synthetic-1", "threadId": "thread-synthetic-1"}}
                    ],
                }
            ],
            "historyId": "101",
            "nextPageToken": "history-page-2",
        },
        {
            "history": [
                {
                    "id": "102",
                    "messagesDeleted": [
                        {"message": {"id": "synthetic-0", "threadId": "thread-synthetic-0"}}
                    ],
                }
            ],
            "historyId": "102",
        },
    )
    transport = SyntheticGmailTransport(
        (_message("synthetic-1"), _message("synthetic-2")), history_pages=pages
    )
    state = SyncState(
        "100",
        (
            MessageRef("synthetic-0", "thread-synthetic-0"),
            MessageRef("synthetic-1", "thread-synthetic-1"),
        ),
    )
    result = _reconciler(transport).reconcile(
        state,
        now_sydney=datetime(2026, 7, 20, 4, 30, tzinfo=SYDNEY),
    )
    assert result.mode is ReconcileMode.INCREMENTAL
    assert result.state.history_id == "102"
    assert [item.message_id for item in result.state.known_refs] == [
        "synthetic-1",
        "synthetic-2",
    ]
    assert [item.message_id for item in result.changed_refs] == [
        "synthetic-1",
        "synthetic-2",
    ]
    assert result.history_pages_read == 2
    assert state.history_id == "100"


@pytest.mark.parametrize(
    ("now", "history_status", "difference", "force_full", "expected"),
    [
        (datetime(2026, 7, 26, 4, 30, tzinfo=SYDNEY), 200, False, False, ReconcileMode.FULL_SUNDAY),
        (
            datetime(2026, 7, 20, 4, 30, tzinfo=SYDNEY),
            404,
            False,
            False,
            ReconcileMode.FULL_HISTORY_EXPIRED,
        ),
        (
            datetime(2026, 7, 20, 4, 30, tzinfo=SYDNEY),
            200,
            True,
            False,
            ReconcileMode.FULL_DIFFERENCE,
        ),
        (
            datetime(2026, 7, 20, 4, 30, tzinfo=SYDNEY),
            200,
            False,
            True,
            ReconcileMode.FULL_MANUAL,
        ),
    ],
)
def test_t0302_sunday_404_difference_and_manual_modes_full_reconcile(
    now: datetime,
    history_status: int,
    difference: bool,
    force_full: bool,
    expected: ReconcileMode,
) -> None:
    transport = SyntheticGmailTransport(
        (_message("synthetic-1", "500"),), history_status=history_status
    )
    state = SyncState("100", (MessageRef("synthetic-old", "thread-synthetic-old"),))
    result = _reconciler(transport).reconcile(
        state,
        now_sydney=now,
        difference_detected=difference,
        force_full=force_full,
    )
    assert result.mode is expected
    assert result.state.history_id == "500"
    assert [item.message_id for item in result.state.known_refs] == ["synthetic-1"]
    assert result.discovery is not None
    assert transport.raw_fetches == []


def test_t0302_interrupted_pagination_does_not_mutate_input_watermark() -> None:
    pages = (
        {"history": [], "historyId": "101", "nextPageToken": "next"},
        {"history": [], "historyId": "102"},
    )
    transport = SyntheticGmailTransport((), history_pages=pages, fail_history_page=1)
    state = SyncState("100", (MessageRef("synthetic-1", "thread-synthetic-1"),))
    with pytest.raises(OSError, match="interrupted"):
        _reconciler(transport).reconcile(
            state,
            now_sydney=datetime(2026, 7, 20, 4, 30, tzinfo=SYDNEY),
        )
    assert state.history_id == "100"
    assert [item.message_id for item in state.known_refs] == ["synthetic-1"]


def test_t0302_incremental_history_refetches_metadata_and_excludes_outbound_labels() -> None:
    message_ids = ("synthetic-inbound", "synthetic-sent", "synthetic-draft")
    pages = (
        {
            "history": [
                {
                    "id": "101",
                    "messagesAdded": [
                        {
                            "message": {
                                "id": message_id,
                                "threadId": "thread-" + message_id,
                            }
                        }
                        for message_id in message_ids
                    ],
                }
            ],
            "historyId": "101",
        },
    )
    transport = SyntheticGmailTransport(
        (
            _message("synthetic-inbound"),
            _message("synthetic-sent", labels=("SENT",)),
            _message("synthetic-draft", labels=("DRAFT",)),
        ),
        history_pages=pages,
    )
    result = _reconciler(transport).reconcile(
        SyncState("100", ()),
        now_sydney=datetime(2026, 7, 20, 4, 30, tzinfo=SYDNEY),
    )
    assert [item.message_id for item in result.state.known_refs] == ["synthetic-inbound"]
    assert [item.message_id for item in result.changed_refs] == ["synthetic-inbound"]
    assert sorted(transport.metadata_fetches) == sorted(message_ids)
    assert transport.raw_fetches == []


def test_t0302_reconciliation_requires_iana_sydney_timezone() -> None:
    transport = SyntheticGmailTransport(())
    with pytest.raises(GmailDiscoveryError, match="Australia/Sydney"):
        _reconciler(transport).reconcile(
            None,
            now_sydney=datetime(2026, 7, 20, 4, 30),
        )
