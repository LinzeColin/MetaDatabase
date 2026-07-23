"""Fail-closed Gmail discovery and reconciliation using metadata-only reads."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from zoneinfo import ZoneInfo

from .gmail_guard import (
    GmailEndpointGuard,
    get_message_request,
    list_filters_request,
    list_history_request,
    list_messages_request,
)

_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_HISTORY_ID = re.compile(r"^[0-9]{1,64}$")
_HEADER_NAME = re.compile(r"^[!-9;-~]{1,64}$")
_DISCOVERY_QUERY = "-in:sent -in:drafts"
_DISCOVERY_SCOPES: tuple[tuple[str, str | None], ...] = (
    ("ALL_MAIL", None),
    ("INBOX", "INBOX"),
    ("SPAM", "SPAM"),
    ("TRASH", "TRASH"),
)
_SYDNEY = ZoneInfo("Australia/Sydney")


class GmailDiscoveryError(RuntimeError):
    """Public-safe Gmail discovery failure without response content."""


class HistoryExpired(GmailDiscoveryError):
    """The stored Gmail History watermark is no longer valid."""


class ReconcileMode(StrEnum):
    INCREMENTAL = "INCREMENTAL"
    FULL_INITIAL = "FULL_INITIAL"
    FULL_SUNDAY = "FULL_SUNDAY"
    FULL_HISTORY_EXPIRED = "FULL_HISTORY_EXPIRED"
    FULL_DIFFERENCE = "FULL_DIFFERENCE"
    FULL_MANUAL = "FULL_MANUAL"


@dataclass(frozen=True, slots=True, repr=False)
class MessageRef:
    message_id: str
    thread_id: str

    def __post_init__(self) -> None:
        _require_opaque_id(self.message_id, "message")
        _require_opaque_id(self.thread_id, "thread")

    def __repr__(self) -> str:
        return "MessageRef(message_id=<redacted>, thread_id=<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class HeaderSnapshot:
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if len(self.values) > 64:
            raise GmailDiscoveryError("metadata header count exceeds the safe limit")
        for name, value in self.values:
            if (
                _HEADER_NAME.fullmatch(name) is None
                or len(value) > 16_384
                or "\r" in value
                or "\n" in value
            ):
                raise GmailDiscoveryError("metadata header is invalid")

    def __repr__(self) -> str:
        return f"HeaderSnapshot(count={len(self.values)}, values=<redacted>)"

    def all(self, name: str) -> tuple[str, ...]:
        folded = name.casefold()
        return tuple(value for header, value in self.values if header.casefold() == folded)

    def one(self, name: str) -> str | None:
        matches = self.all(name)
        return matches[0] if len(matches) == 1 else None

    def digest(self) -> str:
        canonical = json.dumps(
            [(name.casefold(), value) for name, value in self.values],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class MinimalMessage:
    ref: MessageRef
    history_id: str
    internal_date_ms: int
    label_ids: tuple[str, ...]
    headers: HeaderSnapshot

    def __post_init__(self) -> None:
        if _HISTORY_ID.fullmatch(self.history_id) is None:
            raise GmailDiscoveryError("message history ID is invalid")
        if type(self.internal_date_ms) is not int or self.internal_date_ms < 0:
            raise GmailDiscoveryError("message internal date is invalid")
        if len(self.label_ids) != len(set(self.label_ids)) or any(
            _OPAQUE_ID.fullmatch(label) is None for label in self.label_ids
        ):
            raise GmailDiscoveryError("message labels are invalid")

    def __repr__(self) -> str:
        return (
            "MinimalMessage(ref=<redacted>, history_id=<redacted>, "
            f"internal_date_ms=<redacted>, label_count={len(self.label_ids)}, "
            "headers=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class MessageListPage:
    refs: tuple[MessageRef, ...]
    next_page_token: str | None


@dataclass(frozen=True, slots=True)
class FilterAudit:
    filter_count: int
    label_action_count: int
    forwarding_action_count: int


@dataclass(frozen=True, slots=True, repr=False)
class DiscoveryResult:
    refs: tuple[MessageRef, ...]
    scope_ids: tuple[tuple[str, frozenset[str]], ...]
    filter_audit: FilterAudit
    watermark_message_id: str | None
    pages_read: int

    def __repr__(self) -> str:
        return (
            f"DiscoveryResult(message_count={len(self.refs)}, scopes={len(self.scope_ids)}, "
            f"filter_count={self.filter_audit.filter_count}, pages_read={self.pages_read})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class HistoryPage:
    upserts: tuple[MessageRef, ...]
    deleted_ids: tuple[str, ...]
    touched: tuple[MessageRef, ...]
    history_id: str
    next_page_token: str | None

    def __repr__(self) -> str:
        return (
            f"HistoryPage(upserts={len(self.upserts)}, deleted={len(self.deleted_ids)}, "
            f"touched={len(self.touched)}, history_id=<redacted>, "
            f"has_next={self.next_page_token is not None})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class SyncState:
    history_id: str | None
    known_refs: tuple[MessageRef, ...]

    def __post_init__(self) -> None:
        if self.history_id is not None and _HISTORY_ID.fullmatch(self.history_id) is None:
            raise GmailDiscoveryError("sync history ID is invalid")
        ids = [ref.message_id for ref in self.known_refs]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise GmailDiscoveryError("sync state refs must be sorted and unique")

    def __repr__(self) -> str:
        return f"SyncState(history_id=<redacted>, known_message_count={len(self.known_refs)})"


@dataclass(frozen=True, slots=True, repr=False)
class ReconcileResult:
    mode: ReconcileMode
    state: SyncState
    changed_refs: tuple[MessageRef, ...]
    discovery: DiscoveryResult | None
    history_pages_read: int

    def __repr__(self) -> str:
        return (
            f"ReconcileResult(mode={self.mode.value!r}, known={len(self.state.known_refs)}, "
            f"changed={len(self.changed_refs)}, history_pages={self.history_pages_read})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ReconcileAuditResult:
    """One reconciliation result plus a truthful full-vs-incremental comparison.

    ``full_difference_count`` is ``None`` when there was no independently computable
    incremental candidate (for example first import or an expired History watermark).  Callers
    must not turn that state into a zero-difference claim.
    """

    result: ReconcileResult
    full_reconcile_runs: int
    full_difference_count: int | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.result, ReconcileResult)
            or self.full_reconcile_runs not in {0, 1}
            or (
                self.full_difference_count is not None
                and (
                    type(self.full_difference_count) is not int
                    or self.full_difference_count < 0
                    or self.full_reconcile_runs != 1
                )
            )
            or (self.full_reconcile_runs == 0 and self.result.mode is not ReconcileMode.INCREMENTAL)
        ):
            raise GmailDiscoveryError("reconciliation audit result is invalid")

    def __repr__(self) -> str:
        status = "COMPARED" if self.full_difference_count is not None else "NOT_COMPARABLE"
        return (
            f"ReconcileAuditResult(mode={self.result.mode.value!r}, "
            f"full_runs={self.full_reconcile_runs}, comparison={status!r}, "
            "private_values=<redacted>)"
        )


class GmailReadClient:
    """Parse only the response fields needed by deterministic discovery."""

    def __init__(self, guard: GmailEndpointGuard) -> None:
        self._guard = guard

    def list_message_page(
        self,
        *,
        label_id: str | None,
        page_token: str | None,
    ) -> MessageListPage:
        parameters: list[tuple[str, str]] = [
            ("includeSpamTrash", "true"),
            ("maxResults", "500"),
            ("q", _DISCOVERY_QUERY),
        ]
        if label_id is not None:
            parameters.append(("labelIds", label_id))
        if page_token is not None:
            parameters.append(("pageToken", page_token))
        response = self._guard.send(list_messages_request(tuple(parameters)))
        if response.status != 200:
            raise GmailDiscoveryError("messages.list failed")
        payload = _decode_object(response.body, "messages.list")
        raw_messages = payload.get("messages", [])
        if not isinstance(raw_messages, list):
            raise GmailDiscoveryError("messages.list response is invalid")
        refs = tuple(_parse_ref(item) for item in raw_messages)
        if len({item.message_id for item in refs}) != len(refs):
            raise GmailDiscoveryError("messages.list page contains duplicate IDs")
        return MessageListPage(refs, _optional_token(payload.get("nextPageToken")))

    def get_metadata(
        self,
        message_id: str,
        *,
        header_names: tuple[str, ...],
    ) -> MinimalMessage:
        if (
            not header_names
            or len(header_names) > 32
            or len(set(map(str.casefold, header_names))) != len(header_names)
        ):
            raise GmailDiscoveryError("metadata header request is invalid")
        response = self._guard.send(
            get_message_request(
                message_id,
                message_format="metadata",
                metadata_headers=header_names,
            )
        )
        if response.status != 200:
            raise GmailDiscoveryError("messages.get metadata failed")
        payload = _decode_object(response.body, "messages.get metadata")
        if payload.get("raw") not in {None, ""} or payload.get("snippet") not in {None, ""}:
            raise GmailDiscoveryError("metadata response unexpectedly contains message content")
        ref = _parse_ref(payload)
        if ref.message_id != message_id:
            raise GmailDiscoveryError("metadata response message ID mismatch")
        history_id = payload.get("historyId")
        internal_date = payload.get("internalDate")
        labels = payload.get("labelIds", [])
        message_payload = payload.get("payload")
        if (
            not isinstance(history_id, str)
            or _HISTORY_ID.fullmatch(history_id) is None
            or not isinstance(internal_date, str)
            or not internal_date.isdigit()
            or not isinstance(labels, list)
            or not all(isinstance(item, str) for item in labels)
            or not isinstance(message_payload, dict)
            or message_payload.get("body") not in (None, {})
            or message_payload.get("parts") not in (None, [])
        ):
            raise GmailDiscoveryError("metadata response shape is invalid")
        raw_headers = message_payload.get("headers", [])
        if not isinstance(raw_headers, list):
            raise GmailDiscoveryError("metadata headers are invalid")
        headers: list[tuple[str, str]] = []
        requested = {name.casefold() for name in header_names}
        for item in raw_headers:
            if not isinstance(item, dict):
                raise GmailDiscoveryError("metadata header item is invalid")
            name = item.get("name")
            value = item.get("value")
            if (
                not isinstance(name, str)
                or not isinstance(value, str)
                or name.casefold() not in requested
            ):
                raise GmailDiscoveryError("metadata response contains an unrequested header")
            headers.append((name, value))
        return MinimalMessage(
            ref=ref,
            history_id=history_id,
            internal_date_ms=int(internal_date),
            label_ids=tuple(sorted(cast(list[str], labels))),
            headers=HeaderSnapshot(tuple(headers)),
        )

    def list_filters(self) -> FilterAudit:
        response = self._guard.send(list_filters_request())
        if response.status != 200:
            raise GmailDiscoveryError("filters.list failed")
        payload = _decode_object(response.body, "filters.list")
        filters = payload.get("filter", [])
        if not isinstance(filters, list):
            raise GmailDiscoveryError("filters.list response is invalid")
        label_actions = 0
        forwarding_actions = 0
        for item in filters:
            if not isinstance(item, dict):
                raise GmailDiscoveryError("filter entry is invalid")
            action = item.get("action", {})
            criteria = item.get("criteria", {})
            if not isinstance(action, dict) or not isinstance(criteria, dict):
                raise GmailDiscoveryError("filter entry shape is invalid")
            if action.get("addLabelIds") or action.get("removeLabelIds"):
                label_actions += 1
            if action.get("forward"):
                forwarding_actions += 1
        return FilterAudit(len(filters), label_actions, forwarding_actions)

    def list_history_page(
        self,
        start_history_id: str,
        *,
        page_token: str | None,
    ) -> HistoryPage:
        response = self._guard.send(list_history_request(start_history_id, page_token=page_token))
        if response.status == 404:
            raise HistoryExpired("Gmail History watermark expired")
        if response.status != 200:
            raise GmailDiscoveryError("history.list failed")
        payload = _decode_object(response.body, "history.list")
        history_id = payload.get("historyId")
        records = payload.get("history", [])
        if (
            not isinstance(history_id, str)
            or _HISTORY_ID.fullmatch(history_id) is None
            or not isinstance(records, list)
        ):
            raise GmailDiscoveryError("history.list response is invalid")
        upserts: dict[str, MessageRef] = {}
        touched: dict[str, MessageRef] = {}
        deleted: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise GmailDiscoveryError("history record is invalid")
            _collect_history_refs(record.get("messagesAdded", []), upserts, touched)
            _collect_history_refs(record.get("labelsAdded", []), {}, touched)
            _collect_history_refs(record.get("labelsRemoved", []), {}, touched)
            raw_deleted = record.get("messagesDeleted", [])
            if not isinstance(raw_deleted, list):
                raise GmailDiscoveryError("history deleted messages are invalid")
            for item in raw_deleted:
                ref = _parse_history_message(item)
                deleted.add(ref.message_id)
                touched[ref.message_id] = ref
        for message_id in deleted:
            upserts.pop(message_id, None)
        return HistoryPage(
            upserts=tuple(upserts[key] for key in sorted(upserts)),
            deleted_ids=tuple(sorted(deleted)),
            touched=tuple(touched[key] for key in sorted(touched)),
            history_id=history_id,
            next_page_token=_optional_token(payload.get("nextPageToken")),
        )


class FullMailboxDiscoverer:
    def __init__(
        self,
        client: GmailReadClient,
        *,
        max_pages: int = 10_000,
        max_message_refs: int = 5_000_000,
    ) -> None:
        if max_pages <= 0 or max_message_refs <= 0:
            raise ValueError("discovery limits must be positive")
        self._client = client
        self._max_pages = max_pages
        self._max_message_refs = max_message_refs

    def scan(self) -> DiscoveryResult:
        union: dict[str, MessageRef] = {}
        scope_ids: list[tuple[str, frozenset[str]]] = []
        watermark: str | None = None
        pages_read = 0
        for scope_name, label_id in _DISCOVERY_SCOPES:
            current: dict[str, MessageRef] = {}
            page_token: str | None = None
            seen_tokens: set[str] = set()
            while True:
                pages_read += 1
                if pages_read > self._max_pages:
                    raise GmailDiscoveryError("messages.list page limit exceeded")
                page = self._client.list_message_page(
                    label_id=label_id,
                    page_token=page_token,
                )
                if scope_name == "ALL_MAIL" and watermark is None and page.refs:
                    watermark = page.refs[0].message_id
                for ref in page.refs:
                    _merge_ref(current, ref)
                    _merge_ref(union, ref)
                if len(union) > self._max_message_refs:
                    raise GmailDiscoveryError("mailbox message limit exceeded")
                if page.next_page_token is None:
                    break
                if page.next_page_token in seen_tokens:
                    raise GmailDiscoveryError("messages.list repeated a page token")
                seen_tokens.add(page.next_page_token)
                page_token = page.next_page_token
            scope_ids.append((scope_name, frozenset(current)))
        all_mail = dict(scope_ids)["ALL_MAIL"]
        if any(not ids.issubset(all_mail) for name, ids in scope_ids if name != "ALL_MAIL"):
            raise GmailDiscoveryError("label scan differs from includeSpamTrash All Mail scan")
        audit = self._client.list_filters()
        return DiscoveryResult(
            refs=tuple(union[key] for key in sorted(union)),
            scope_ids=tuple(scope_ids),
            filter_audit=audit,
            watermark_message_id=watermark,
            pages_read=pages_read,
        )


class GmailReconciler:
    """Commit a new watermark only after a complete page sequence succeeds."""

    def __init__(
        self,
        client: GmailReadClient,
        discoverer: FullMailboxDiscoverer,
        *,
        max_history_pages: int = 10_000,
    ) -> None:
        if max_history_pages <= 0:
            raise ValueError("history page limit must be positive")
        self._client = client
        self._discoverer = discoverer
        self._max_history_pages = max_history_pages

    def reconcile(
        self,
        state: SyncState | None,
        *,
        now_sydney: datetime,
        difference_detected: bool = False,
        force_full: bool = False,
    ) -> ReconcileResult:
        _require_sydney(now_sydney)
        if state is None or state.history_id is None:
            return self._full(ReconcileMode.FULL_INITIAL)
        if force_full:
            return self._full(ReconcileMode.FULL_MANUAL)
        if difference_detected:
            return self._full(ReconcileMode.FULL_DIFFERENCE)
        if now_sydney.weekday() == 6:
            return self._full(ReconcileMode.FULL_SUNDAY)
        try:
            return self._incremental(state)
        except HistoryExpired:
            return self._full(ReconcileMode.FULL_HISTORY_EXPIRED)

    def reconcile_for_run(
        self,
        state: SyncState | None,
        *,
        now_sydney: datetime,
        full_reconcile: bool,
    ) -> ReconcileAuditResult:
        """Reconcile one scheduled run and audit a requested Full Reconciliation.

        A Sunday/manual full run first computes the Gmail History candidate when a valid prior
        watermark exists, then independently scans the full mailbox.  Only equality of those two
        states yields an integer difference count.  Initial and History-expired recovery remain
        explicitly not comparable instead of being reported as a synthetic zero.
        """

        _require_sydney(now_sydney)
        if type(full_reconcile) is not bool:
            raise GmailDiscoveryError("full reconciliation selector must be boolean")
        if not full_reconcile:
            result = self.reconcile(state, now_sydney=now_sydney)
            return ReconcileAuditResult(
                result,
                int(result.mode is not ReconcileMode.INCREMENTAL),
                None,
            )
        if state is None or state.history_id is None:
            return ReconcileAuditResult(self._full(ReconcileMode.FULL_INITIAL), 1, None)
        try:
            incremental = self._incremental(state)
        except HistoryExpired:
            return ReconcileAuditResult(
                self._full(ReconcileMode.FULL_HISTORY_EXPIRED),
                1,
                None,
            )
        mode = ReconcileMode.FULL_SUNDAY if now_sydney.weekday() == 6 else ReconcileMode.FULL_MANUAL
        full = self._full(mode)
        return ReconcileAuditResult(
            full,
            1,
            _sync_state_difference_count(incremental.state, full.state),
        )

    def _full(self, mode: ReconcileMode) -> ReconcileResult:
        discovery = self._discoverer.scan()
        history_id: str | None = None
        if discovery.watermark_message_id is not None:
            watermark = self._client.get_metadata(
                discovery.watermark_message_id,
                header_names=("From",),
            )
            history_id = watermark.history_id
        state = SyncState(history_id, discovery.refs)
        return ReconcileResult(mode, state, discovery.refs, discovery, 0)

    def _incremental(self, state: SyncState) -> ReconcileResult:
        assert state.history_id is not None
        known = {ref.message_id: ref for ref in state.known_refs}
        changed: dict[str, MessageRef] = {}
        page_token: str | None = None
        seen_tokens: set[str] = set()
        pages = 0
        final_history_id = state.history_id
        while True:
            pages += 1
            if pages > self._max_history_pages:
                raise GmailDiscoveryError("history.list page limit exceeded")
            page = self._client.list_history_page(state.history_id, page_token=page_token)
            final_history_id = page.history_id
            for message_id in page.deleted_ids:
                known.pop(message_id, None)
                changed.pop(message_id, None)
            for ref in page.upserts:
                _merge_ref(known, ref)
                changed[ref.message_id] = ref
            for ref in page.touched:
                if ref.message_id not in page.deleted_ids:
                    _merge_ref(known, ref)
                    changed[ref.message_id] = ref
            if page.next_page_token is None:
                break
            if page.next_page_token in seen_tokens:
                raise GmailDiscoveryError("history.list repeated a page token")
            seen_tokens.add(page.next_page_token)
            page_token = page.next_page_token
        for message_id in sorted(tuple(changed)):
            current = self._client.get_metadata(message_id, header_names=("From",))
            if "SENT" in current.label_ids or "DRAFT" in current.label_ids:
                known.pop(message_id, None)
                changed.pop(message_id, None)
                continue
            _merge_ref(known, current.ref)
            changed[message_id] = current.ref
        next_state = SyncState(final_history_id, tuple(known[key] for key in sorted(known)))
        return ReconcileResult(
            ReconcileMode.INCREMENTAL,
            next_state,
            tuple(changed[key] for key in sorted(changed)),
            None,
            pages,
        )


def _decode_object(body: bytes, operation: str) -> dict[str, object]:
    if len(body) > 64 * 1024 * 1024:
        raise GmailDiscoveryError(f"{operation} response exceeds the safe limit")
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GmailDiscoveryError(f"{operation} response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise GmailDiscoveryError(f"{operation} response must be an object")
    return cast(dict[str, object], value)


def _parse_ref(value: object) -> MessageRef:
    if not isinstance(value, dict):
        raise GmailDiscoveryError("Gmail message reference is invalid")
    message_id = value.get("id")
    thread_id = value.get("threadId")
    if not isinstance(message_id, str) or not isinstance(thread_id, str):
        raise GmailDiscoveryError("Gmail message reference is incomplete")
    return MessageRef(message_id, thread_id)


def _parse_history_message(value: object) -> MessageRef:
    if not isinstance(value, dict) or "message" not in value:
        raise GmailDiscoveryError("Gmail history message is invalid")
    return _parse_ref(value["message"])


def _collect_history_refs(
    raw_items: object,
    upserts: dict[str, MessageRef],
    touched: dict[str, MessageRef],
) -> None:
    if not isinstance(raw_items, list):
        raise GmailDiscoveryError("Gmail history collection is invalid")
    for item in raw_items:
        ref = _parse_history_message(item)
        if upserts is not None:
            _merge_ref(upserts, ref)
        _merge_ref(touched, ref)


def _merge_ref(target: dict[str, MessageRef], ref: MessageRef) -> None:
    existing = target.get(ref.message_id)
    if existing is not None and existing.thread_id != ref.thread_id:
        raise GmailDiscoveryError("Gmail message changed thread identity")
    target[ref.message_id] = ref


def _sync_state_difference_count(left: SyncState, right: SyncState) -> int:
    left_refs = {item.message_id: item.thread_id for item in left.known_refs}
    right_refs = {item.message_id: item.thread_id for item in right.known_refs}
    return sum(
        left_refs.get(message_id) != right_refs.get(message_id)
        for message_id in left_refs.keys() | right_refs.keys()
    )


def _optional_token(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise GmailDiscoveryError("Gmail next page token is invalid")
    return value


def _require_opaque_id(value: str, kind: str) -> None:
    if _OPAQUE_ID.fullmatch(value) is None:
        raise GmailDiscoveryError(f"Gmail {kind} ID is invalid")


def _require_sydney(value: datetime) -> None:
    if value.tzinfo is None or getattr(value.tzinfo, "key", None) != _SYDNEY.key:
        raise GmailDiscoveryError("reconciliation time must use Australia/Sydney")
