"""Synthetic-only Stage 3 Gmail fixtures and deterministic HTTP transport."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from urllib.parse import parse_qs, urlsplit

import pikepdf

from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.sender_registry import SenderRegistry


def synthetic_address(local: str = "statements", domain: str = "synthetic.invalid") -> str:
    return local + chr(64) + domain


def synthetic_pdf() -> bytes:
    """Build a deterministic, structurally valid, inert one-page PDF fixture."""

    sink = io.BytesIO()
    with pikepdf.Pdf.new() as document:
        document.add_blank_page(page_size=(72, 72))
        document.save(sink, static_id=True, deterministic_id=True)
    return sink.getvalue()


def authentication_results(
    *,
    sender: str | None = None,
    spf: str = "pass",
    dkim: str = "pass",
    dmarc: str = "pass",
    dkim_domain: str = "synthetic.invalid",
    from_domain: str = "synthetic.invalid",
) -> str:
    mail_from = sender or synthetic_address()
    return (
        "mx.google.com; "
        f"spf={spf} smtp.mailfrom={mail_from}; "
        f"dkim={dkim} header.d={dkim_domain}; "
        f"dmarc={dmarc} header.from={from_domain}"
    )


def make_raw_message(
    *,
    message_id: str,
    sender: str | None = None,
    subject: str = "Synthetic Moomoo AU Daily fixture",
    auth_results: str | None = None,
    template: str = "AU-DAILY-V1",
    attachments: tuple[tuple[str, str, str, bytes], ...] = (),
) -> bytes:
    address = sender or synthetic_address()
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "Synthetic Sender <" + address + ">"
    message["To"] = synthetic_address("owner")
    message["Subject"] = subject
    message["Date"] = "Thu, 01 Jan 2026 00:00:00 +0000"
    message["Message-ID"] = "<" + message_id + chr(64) + "synthetic.invalid>"
    message["Authentication-Results"] = auth_results or authentication_results(sender=address)
    message["X-MMAU-Synthetic-Template"] = template
    message.set_content("Synthetic fixture only. No production content.")
    for filename, maintype, subtype, content in attachments:
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    if attachments:
        message.set_boundary("=_MMAU_STAGE3_FIXED_BOUNDARY_001")
    return message.as_bytes(policy=policy.SMTP.clone(linesep="\r\n", max_line_length=78))


def metadata_headers(
    *,
    sender: str | None = None,
    subject: str = "Synthetic Moomoo AU Daily fixture",
    auth_results: str | None = None,
    template: str = "AU-DAILY-V1",
) -> tuple[tuple[str, str], ...]:
    address = sender or synthetic_address()
    return (
        ("From", "Synthetic Sender <" + address + ">"),
        ("Subject", subject),
        ("Authentication-Results", auth_results or authentication_results(sender=address)),
        ("X-MMAU-Synthetic-Template", template),
    )


def registry_payload(*, active: bool = True, third_party: bool = False) -> bytes:
    entries: list[dict[str, object]] = []
    activation = "EMPTY_PROTECTED_EVIDENCE_REQUIRED"
    if active:
        activation = "ACTIVE"
        entries.append(
            {
                "entry_id": "SYNTHETIC_PRIMARY_001",
                "exact_address": synthetic_address(),
                "header_from_domain": "synthetic.invalid",
                "authentication": {
                    "trusted_authserv_ids": ["mx.google.com"],
                    "dkim_domains": ["synthetic.invalid"],
                    "spf_mail_from_domains": ["synthetic.invalid"],
                    "dmarc_from_domains": ["synthetic.invalid"],
                },
                "fingerprint": {
                    "subject_prefixes": ["Synthetic Moomoo AU Daily"],
                    "required_headers": [
                        {"name": "X-MMAU-Synthetic-Template", "value": "AU-DAILY-V1"}
                    ],
                },
                "evidence": {
                    "source_type": "PROTECTED_OWNER",
                    "source_digest": "a" * 64,
                },
                "first_verified_at_utc": "2026-01-01T00:00:00Z",
                "last_verified_at_utc": "2026-01-01T00:00:00Z",
                "status": "ACTIVE",
                "third_party": third_party,
                "replaces_entry_id": None,
            }
        )
    payload = {
        "schema_version": "moomooau.sender-registry.v1",
        "registry_version": "1.0.0",
        "issued_at_utc": "2026-01-01T00:00:00Z",
        "activation_state": activation,
        "entries": entries,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def synthetic_registry() -> SenderRegistry:
    return SenderRegistry.from_json(registry_payload())


@dataclass(frozen=True, slots=True)
class SyntheticGmailMessage:
    message_id: str
    thread_id: str
    labels: tuple[str, ...]
    history_id: str
    internal_date_ms: int
    headers: tuple[tuple[str, str], ...]
    raw: bytes


class SyntheticGmailTransport:
    """Emulate only the allowlisted Gmail reads used by Stage 3."""

    def __init__(
        self,
        messages: tuple[SyntheticGmailMessage, ...],
        *,
        page_size: int = 500,
        filters: tuple[dict[str, object], ...] = (),
        history_pages: tuple[dict[str, object], ...] = (),
        history_status: int = 200,
        fail_history_page: int | None = None,
    ) -> None:
        self.messages = messages
        self.page_size = page_size
        self.filters = filters
        self.history_pages = history_pages
        self.history_status = history_status
        self.fail_history_page = fail_history_page
        self.requests: list[HttpRequest] = []
        self.raw_fetches: list[str] = []
        self.metadata_fetches: list[str] = []
        self.filter_reads = 0
        self.history_reads = 0

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        parsed = urlsplit(request.url)
        query = parse_qs(parsed.query)
        if parsed.path == "/gmail/v1/users/me/messages":
            return self._list_messages(query)
        if parsed.path == "/gmail/v1/users/me/settings/filters":
            self.filter_reads += 1
            return _json_response(200, {"filter": list(self.filters)})
        if parsed.path == "/gmail/v1/users/me/history":
            return self._list_history(query)
        prefix = "/gmail/v1/users/me/messages/"
        if parsed.path.startswith(prefix) and "/" not in parsed.path.removeprefix(prefix):
            return self._get_message(parsed.path.removeprefix(prefix), query)
        raise AssertionError("synthetic transport received an unexpected endpoint")

    def _list_messages(self, query: dict[str, list[str]]) -> HttpResponse:
        assert query.get("includeSpamTrash") == ["true"]
        assert query.get("maxResults") == ["500"]
        assert query.get("q") == ["-in:sent -in:drafts"]
        label = query.get("labelIds", [None])[0]
        candidates = [
            item
            for item in self.messages
            if "SENT" not in item.labels
            and "DRAFT" not in item.labels
            and (label is None or label in item.labels)
        ]
        offset = int(query.get("pageToken", ["0"])[0])
        page = candidates[offset : offset + self.page_size]
        payload: dict[str, object] = {
            "messages": [{"id": item.message_id, "threadId": item.thread_id} for item in page]
        }
        if offset + self.page_size < len(candidates):
            payload["nextPageToken"] = str(offset + self.page_size)
        return _json_response(200, payload)

    def _get_message(self, message_id: str, query: dict[str, list[str]]) -> HttpResponse:
        message = next(item for item in self.messages if item.message_id == message_id)
        message_format = query.get("format", [None])[0]
        payload: dict[str, object] = {
            "id": message.message_id,
            "threadId": message.thread_id,
            "labelIds": list(message.labels),
            "historyId": message.history_id,
            "internalDate": str(message.internal_date_ms),
        }
        if message_format == "metadata":
            self.metadata_fetches.append(message_id)
            requested = {name.casefold() for name in query.get("metadataHeaders", [])}
            payload["payload"] = {
                "headers": [
                    {"name": name, "value": value}
                    for name, value in message.headers
                    if name.casefold() in requested
                ]
            }
        elif message_format == "raw":
            self.raw_fetches.append(message_id)
            payload["raw"] = base64.urlsafe_b64encode(message.raw).rstrip(b"=").decode("ascii")
        else:
            raise AssertionError("synthetic transport received an unexpected message format")
        return _json_response(200, payload)

    def _list_history(self, query: dict[str, list[str]]) -> HttpResponse:
        if self.history_status != 200:
            return _json_response(self.history_status, {"error": "synthetic"})
        page_index = self.history_reads
        self.history_reads += 1
        if self.fail_history_page is not None and page_index == self.fail_history_page:
            raise OSError("synthetic interrupted page")
        if page_index >= len(self.history_pages):
            return _json_response(200, {"history": [], "historyId": query["startHistoryId"][0]})
        return _json_response(200, self.history_pages[page_index])


def _json_response(status: int, payload: object) -> HttpResponse:
    return HttpResponse(
        status,
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
