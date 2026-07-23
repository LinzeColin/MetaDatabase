"""Exact Gmail REST endpoint allowlist enforced before the transport boundary."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit

from .http_boundary import HttpRequest, HttpResponse, HttpTransport

GMAIL_API_ORIGIN = "https://gmail.googleapis.com"
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_LABEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_HEADER_NAME = re.compile(r"^[!-9;-~]{1,64}$")
_HISTORY_TYPES = {"messageAdded", "messageDeleted", "labelAdded", "labelRemoved"}
_METADATA_RESPONSE_FIELDS = "id,threadId,labelIds,historyId,internalDate,payload/headers"


class GmailEndpointRejected(RuntimeError):
    pass


class GmailOperation(StrEnum):
    MESSAGES_LIST = "messages.list"
    MESSAGES_GET = "messages.get"
    HISTORY_LIST = "history.list"
    FILTERS_LIST = "filters.list"
    MESSAGE_TRASH = "messages.trash"


@dataclass(frozen=True, slots=True)
class GmailGuardMetrics:
    allowed_calls: int
    blocked_calls: int
    forbidden_network_calls: int


class GmailEndpointGuard:
    """Validate raw HTTP messages, then and only then delegate to an injected transport."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport
        self._allowed_calls = 0
        self._blocked_calls = 0

    @property
    def metrics(self) -> GmailGuardMetrics:
        return GmailGuardMetrics(self._allowed_calls, self._blocked_calls, 0)

    def send(self, request: HttpRequest) -> HttpResponse:
        try:
            self._validate(request)
        except GmailEndpointRejected:
            self._blocked_calls += 1
            raise
        self._allowed_calls += 1
        return self._transport.send(request)

    def _validate(self, request: HttpRequest) -> GmailOperation:
        try:
            parsed = urlsplit(request.url)
            port = parsed.port
        except ValueError as exc:
            raise GmailEndpointRejected("Gmail URL is invalid") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != "gmail.googleapis.com"
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise GmailEndpointRejected("Gmail authority is not allowed")
        if request.method not in {"GET", "POST"}:
            raise GmailEndpointRejected("Gmail method is not allowed")
        self._validate_headers(request.headers)
        try:
            query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise GmailEndpointRejected("Gmail query is invalid") from exc
        operation = self._classify(request.method, parsed.path)
        self._validate_query(operation, query)
        if operation is GmailOperation.MESSAGE_TRASH:
            if request.body not in {None, b""}:
                raise GmailEndpointRejected("messages.trash requires an empty body")
        elif request.body is not None:
            raise GmailEndpointRejected("Gmail read operations must not have a body")
        return operation

    @staticmethod
    def _validate_headers(headers: tuple[tuple[str, str], ...]) -> None:
        allowed = {"accept", "authorization", "content-type", "user-agent"}
        seen: set[str] = set()
        for name, value in headers:
            lowered = name.casefold()
            if (
                lowered not in allowed
                or lowered in seen
                or "\r" in name
                or "\n" in name
                or "\r" in value
                or "\n" in value
            ):
                raise GmailEndpointRejected("Gmail header is not allowed")
            seen.add(lowered)

    @staticmethod
    def _classify(method: str, path: str) -> GmailOperation:
        if method == "GET" and path == "/gmail/v1/users/me/messages":
            return GmailOperation.MESSAGES_LIST
        match = re.fullmatch(r"/gmail/v1/users/me/messages/([A-Za-z0-9_-]{1,256})", path)
        if method == "GET" and match:
            return GmailOperation.MESSAGES_GET
        if method == "GET" and path == "/gmail/v1/users/me/history":
            return GmailOperation.HISTORY_LIST
        if method == "GET" and path == "/gmail/v1/users/me/settings/filters":
            return GmailOperation.FILTERS_LIST
        trash = re.fullmatch(r"/gmail/v1/users/me/messages/([A-Za-z0-9_-]{1,256})/trash", path)
        if method == "POST" and trash:
            return GmailOperation.MESSAGE_TRASH
        raise GmailEndpointRejected("Gmail endpoint is not allowlisted")

    @staticmethod
    def _validate_query(operation: GmailOperation, query: list[tuple[str, str]]) -> None:
        allowed: dict[GmailOperation, set[str]] = {
            GmailOperation.MESSAGES_LIST: {
                "includeSpamTrash",
                "labelIds",
                "maxResults",
                "pageToken",
                "q",
            },
            GmailOperation.MESSAGES_GET: {"fields", "format", "metadataHeaders"},
            GmailOperation.HISTORY_LIST: {
                "historyTypes",
                "labelId",
                "maxResults",
                "pageToken",
                "startHistoryId",
            },
            GmailOperation.FILTERS_LIST: set(),
            GmailOperation.MESSAGE_TRASH: set(),
        }
        counts = Counter(key for key, _ in query)
        repeatable = {"labelIds", "metadataHeaders", "historyTypes"}
        if any(key not in allowed[operation] or not value for key, value in query):
            raise GmailEndpointRejected("Gmail query parameter is not allowed")
        if any(count > 1 and key not in repeatable for key, count in counts.items()):
            raise GmailEndpointRejected("Gmail query parameter is duplicated")
        values = dict(query)
        if "maxResults" in values and (
            not values["maxResults"].isdigit() or not 1 <= int(values["maxResults"]) <= 500
        ):
            raise GmailEndpointRejected("Gmail maxResults is invalid")
        if values.get("includeSpamTrash") not in {None, "true", "false"}:
            raise GmailEndpointRejected("Gmail includeSpamTrash is invalid")
        if values.get("format") not in {None, "metadata", "minimal", "raw"}:
            raise GmailEndpointRejected("Gmail message format is invalid")
        if "startHistoryId" in values and not values["startHistoryId"].isdigit():
            raise GmailEndpointRejected("Gmail startHistoryId is invalid")
        if operation is GmailOperation.MESSAGES_GET:
            message_format = values.get("format")
            if message_format is None:
                raise GmailEndpointRejected("Gmail message format is required")
            if "metadataHeaders" in counts and message_format != "metadata":
                raise GmailEndpointRejected("metadata headers require metadata format")
            response_fields = values.get("fields")
            if message_format == "metadata":
                if response_fields != _METADATA_RESPONSE_FIELDS:
                    raise GmailEndpointRejected(
                        "Gmail metadata partial response fields are required"
                    )
            elif response_fields is not None:
                raise GmailEndpointRejected(
                    "Gmail partial response fields are not allowed for this format"
                )
        if operation is GmailOperation.HISTORY_LIST and "startHistoryId" not in values:
            raise GmailEndpointRejected("Gmail startHistoryId is required")
        for key, value in query:
            if key == "labelIds" and _LABEL_ID.fullmatch(value) is None:
                raise GmailEndpointRejected("Gmail label ID is invalid")
            if key == "metadataHeaders" and _HEADER_NAME.fullmatch(value) is None:
                raise GmailEndpointRejected("Gmail metadata header is invalid")
            if key == "historyTypes" and value not in _HISTORY_TYPES:
                raise GmailEndpointRejected("Gmail history type is invalid")
            if key == "pageToken" and (
                len(value) > 4096
                or not value.isascii()
                or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
            ):
                raise GmailEndpointRejected("Gmail page token is invalid")
            if key == "q" and (
                len(value) > 2048 or "\r" in value or "\n" in value or not value.strip()
            ):
                raise GmailEndpointRejected("Gmail query is invalid")


def list_messages_request(parameters: tuple[tuple[str, str], ...] = ()) -> HttpRequest:
    query = urlencode(parameters, doseq=True)
    suffix = "?" + query if query else ""
    return HttpRequest("GET", GMAIL_API_ORIGIN + "/gmail/v1/users/me/messages" + suffix)


def get_message_request(
    message_id: str,
    *,
    message_format: str,
    metadata_headers: tuple[str, ...] = (),
) -> HttpRequest:
    _require_message_id(message_id)
    parameters: list[tuple[str, str]] = [("format", message_format)]
    if message_format == "metadata":
        parameters.append(("fields", _METADATA_RESPONSE_FIELDS))
    parameters.extend(("metadataHeaders", header) for header in metadata_headers)
    query = urlencode(parameters)
    return HttpRequest(
        "GET", GMAIL_API_ORIGIN + f"/gmail/v1/users/me/messages/{message_id}?{query}"
    )


def list_history_request(
    start_history_id: str,
    *,
    max_results: int = 500,
    page_token: str | None = None,
    history_types: tuple[str, ...] = (
        "messageAdded",
        "messageDeleted",
        "labelAdded",
        "labelRemoved",
    ),
) -> HttpRequest:
    if not start_history_id.isdigit():
        raise GmailEndpointRejected("Gmail startHistoryId is invalid")
    parameters: list[tuple[str, str]] = [
        ("startHistoryId", start_history_id),
        ("maxResults", str(max_results)),
    ]
    parameters.extend(("historyTypes", history_type) for history_type in history_types)
    if page_token is not None:
        parameters.append(("pageToken", page_token))
    query = urlencode(parameters)
    return HttpRequest("GET", GMAIL_API_ORIGIN + f"/gmail/v1/users/me/history?{query}")


def list_filters_request() -> HttpRequest:
    return HttpRequest("GET", GMAIL_API_ORIGIN + "/gmail/v1/users/me/settings/filters")


def trash_message_request(message_id: str) -> HttpRequest:
    _require_message_id(message_id)
    return HttpRequest(
        "POST",
        GMAIL_API_ORIGIN + f"/gmail/v1/users/me/messages/{message_id}/trash",
        body=b"",
    )


def _require_message_id(message_id: str) -> None:
    if _MESSAGE_ID.fullmatch(message_id) is None:
        raise GmailEndpointRejected("Gmail Message ID is invalid")
