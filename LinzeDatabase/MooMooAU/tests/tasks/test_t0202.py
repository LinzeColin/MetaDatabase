from __future__ import annotations

import pytest

from moomooau_archive.gmail_guard import (
    GmailEndpointGuard,
    GmailEndpointRejected,
    get_message_request,
    list_filters_request,
    list_history_request,
    list_messages_request,
    trash_message_request,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(200, b"{}")


def test_t0202_only_five_exact_gmail_operations_reach_network() -> None:
    transport = RecordingTransport()
    guard = GmailEndpointGuard(transport)
    allowed = (
        list_messages_request((("maxResults", "100"), ("includeSpamTrash", "false"))),
        get_message_request("synthetic_message_001", message_format="raw"),
        list_history_request("123456"),
        list_filters_request(),
        trash_message_request("synthetic_message_001"),
    )
    for request in allowed:
        guard.send(request)
    assert len(transport.requests) == 5

    forbidden = (
        HttpRequest(
            "POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", body=b"{}"
        ),
        HttpRequest("DELETE", "https://gmail.googleapis.com/gmail/v1/users/me/messages/synthetic"),
        HttpRequest("GET", "https://gmail.googleapis.com/gmail/v1/users/me/threads"),
        HttpRequest("POST", "https://gmail.googleapis.com/batch/gmail/v1", body=b"{}"),
        HttpRequest(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/synthetic/modify",
            body=b"{}",
        ),
        HttpRequest("GET", "https://gmail.googleapis.com/gmail/v1/users/other/messages"),
        HttpRequest("GET", "https://gmail.googleapis.com.evil.invalid/gmail/v1/users/me/messages"),
        HttpRequest("GET", "https://gmail.googleapis.com:443/gmail/v1/users/me/messages"),
        HttpRequest(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/synthetic?format=full",
        ),
    )
    for request in forbidden:
        with pytest.raises(GmailEndpointRejected):
            guard.send(request)

    assert len(transport.requests) == 5
    assert guard.metrics.allowed_calls == 5
    assert guard.metrics.blocked_calls == len(forbidden)
    assert guard.metrics.forbidden_network_calls == 0


def test_t0202_trash_is_message_level_empty_body_only() -> None:
    transport = RecordingTransport()
    guard = GmailEndpointGuard(transport)
    exact = trash_message_request("message_only_001")
    guard.send(exact)
    assert exact.url.endswith("/messages/message_only_001/trash")

    for request in (
        HttpRequest("POST", exact.url, body=b"{}"),
        HttpRequest("POST", exact.url + "?unexpected=true", body=b""),
        HttpRequest("POST", exact.url.replace("/messages/", "/threads/"), body=b""),
    ):
        with pytest.raises(GmailEndpointRejected):
            guard.send(request)
    assert len(transport.requests) == 1
