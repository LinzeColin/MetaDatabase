from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from stage3_support import (
    SyntheticGmailMessage,
    SyntheticGmailTransport,
    make_raw_message,
    metadata_headers,
)

from moomooau_archive.gmail_discovery import FullMailboxDiscoverer, GmailReadClient
from moomooau_archive.gmail_guard import GmailEndpointGuard


def _message(message_id: str, label: str) -> SyntheticGmailMessage:
    return SyntheticGmailMessage(
        message_id=message_id,
        thread_id="thread-" + message_id,
        labels=(label,),
        history_id=str(1000 + int(message_id.rsplit("-", 1)[-1])),
        internal_date_ms=1_767_225_600_000,
        headers=metadata_headers(),
        raw=make_raw_message(message_id=message_id),
    )


def test_t0301_all_mail_and_label_scans_page_deduplicate_and_audit_filters() -> None:
    messages = (
        _message("synthetic-1", "INBOX"),
        _message("synthetic-2", "CATEGORY_UPDATES"),
        _message("synthetic-3", "SPAM"),
        _message("synthetic-4", "TRASH"),
        _message("synthetic-5", "SENT"),
        _message("synthetic-6", "DRAFT"),
    )
    filters = (
        {"id": "filter-1", "criteria": {"from": "synthetic"}, "action": {"addLabelIds": ["X"]}},
        {"id": "filter-2", "criteria": {"query": "synthetic"}, "action": {"forward": "redacted"}},
    )
    transport = SyntheticGmailTransport(messages, page_size=1, filters=filters)
    guard = GmailEndpointGuard(transport)
    result = FullMailboxDiscoverer(GmailReadClient(guard)).scan()

    assert [item.message_id for item in result.refs] == [
        "synthetic-1",
        "synthetic-2",
        "synthetic-3",
        "synthetic-4",
    ]
    scopes = dict(result.scope_ids)
    assert scopes["ALL_MAIL"] == {
        "synthetic-1",
        "synthetic-2",
        "synthetic-3",
        "synthetic-4",
    }
    assert scopes["INBOX"] == {"synthetic-1"}
    assert scopes["SPAM"] == {"synthetic-3"}
    assert scopes["TRASH"] == {"synthetic-4"}
    assert result.filter_audit.filter_count == 2
    assert result.filter_audit.label_action_count == 1
    assert result.filter_audit.forwarding_action_count == 1
    assert result.watermark_message_id == "synthetic-1"
    assert transport.raw_fetches == []
    assert transport.metadata_fetches == []
    assert transport.filter_reads == 1
    assert guard.metrics.blocked_calls == guard.metrics.forbidden_network_calls == 0

    list_requests = [
        request
        for request in transport.requests
        if urlsplit(request.url).path == "/gmail/v1/users/me/messages"
    ]
    assert list_requests
    for request in list_requests:
        query = parse_qs(urlsplit(request.url).query)
        assert request.method == "GET"
        assert query["includeSpamTrash"] == ["true"]
        assert query["q"] == ["-in:sent -in:drafts"]
    assert all(request.method == "GET" for request in transport.requests)


def test_t0301_empty_mailbox_still_audits_all_four_scopes() -> None:
    transport = SyntheticGmailTransport((), filters=())
    result = FullMailboxDiscoverer(GmailReadClient(GmailEndpointGuard(transport))).scan()
    assert result.refs == ()
    assert [name for name, _ in result.scope_ids] == ["ALL_MAIL", "INBOX", "SPAM", "TRASH"]
    assert all(not ids for _, ids in result.scope_ids)
    assert result.pages_read == 4
    assert result.watermark_message_id is None
