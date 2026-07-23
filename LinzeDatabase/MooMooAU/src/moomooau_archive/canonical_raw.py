"""Authorized Gmail RAW fetch preserving the returned RFC message bytes exactly."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesHeaderParser
from typing import cast

from .gmail_discovery import HeaderSnapshot
from .gmail_guard import GmailEndpointGuard, get_message_request
from .sender_registry import (
    RawFetchPermit,
    SenderDecision,
    SenderRegistry,
    SenderVerifier,
)

_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]*={0,2}$")


class CanonicalRawError(RuntimeError):
    """RAW fetch failed without exposing message content or identifiers."""


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalRaw:
    message_id: str
    thread_id: str
    internal_date_ms: int
    label_ids: tuple[str, ...]
    plaintext_sha256: str
    byte_count: int
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            _ID.fullmatch(self.message_id) is None
            or _ID.fullmatch(self.thread_id) is None
            or type(self.internal_date_ms) is not int
            or self.internal_date_ms < 0
            or len(self.label_ids) != len(set(self.label_ids))
            or any(_ID.fullmatch(label) is None for label in self.label_ids)
            or self.byte_count != len(self.data)
            or hashlib.sha256(self.data).hexdigest() != self.plaintext_sha256
        ):
            raise CanonicalRawError("canonical RAW identity is invalid")

    def __repr__(self) -> str:
        return (
            "CanonicalRaw(message_id=<redacted>, thread_id=<redacted>, "
            f"internal_date_ms=<redacted>, label_count={len(self.label_ids)}, "
            "plaintext_sha256=<redacted>, byte_count=<redacted>, data=<redacted>)"
        )


class CanonicalRawFetcher:
    def __init__(
        self,
        guard: GmailEndpointGuard,
        verifier: SenderVerifier,
        *,
        maximum_encoded_bytes: int = 64 * 1024 * 1024,
        maximum_raw_bytes: int = 48 * 1024 * 1024,
    ) -> None:
        if maximum_encoded_bytes <= 0 or maximum_raw_bytes <= 0:
            raise ValueError("RAW size limits must be positive")
        self._guard = guard
        self._verifier = verifier
        self._maximum_encoded_bytes = maximum_encoded_bytes
        self._maximum_raw_bytes = maximum_raw_bytes

    def fetch(self, permit: RawFetchPermit, registry: SenderRegistry) -> CanonicalRaw:
        if (
            permit.registry_version != registry.registry_version
            or permit.registry_digest != registry.digest
        ):
            raise CanonicalRawError("sender registry changed after PRE_RAW verification")
        response = self._guard.send(get_message_request(permit.message_id, message_format="raw"))
        if response.status != 200:
            raise CanonicalRawError("messages.get RAW failed")
        if len(response.body) > self._maximum_encoded_bytes + 1024 * 1024:
            raise CanonicalRawError("messages.get RAW response exceeds the safe limit")
        payload = _decode_object(response.body)
        message_id = payload.get("id")
        thread_id = payload.get("threadId")
        internal_date = payload.get("internalDate")
        labels = payload.get("labelIds", [])
        raw_value = payload.get("raw")
        if (
            message_id != permit.message_id
            or not isinstance(thread_id, str)
            or _ID.fullmatch(thread_id) is None
            or not isinstance(internal_date, str)
            or not internal_date.isdigit()
            or int(internal_date) != permit.internal_date_ms
            or not isinstance(labels, list)
            or not all(isinstance(item, str) and _ID.fullmatch(item) for item in labels)
            or not isinstance(raw_value, str)
        ):
            raise CanonicalRawError("messages.get RAW response identity is invalid")
        if "SENT" in labels or "DRAFT" in labels:
            raise CanonicalRawError("outbound Gmail message cannot become Canonical Raw")
        raw = decode_gmail_raw(
            raw_value,
            maximum_encoded_bytes=self._maximum_encoded_bytes,
            maximum_raw_bytes=self._maximum_raw_bytes,
        )
        raw_headers = _selected_raw_headers(raw, registry.requested_header_names)
        raw_verification = self._verifier.verify_headers(raw_headers, registry)
        if (
            raw_verification.decision is not SenderDecision.VERIFIED
            or raw_verification.entry_id != permit.entry_id
            or raw_verification.verification_digest != permit.verification_digest
        ):
            raise CanonicalRawError("RAW headers differ from PRE_RAW verification")
        digest = hashlib.sha256(raw).hexdigest()
        return CanonicalRaw(
            message_id=permit.message_id,
            thread_id=thread_id,
            internal_date_ms=int(internal_date),
            label_ids=tuple(sorted(cast(list[str], labels))),
            plaintext_sha256=digest,
            byte_count=len(raw),
            data=raw,
        )


def decode_gmail_raw(
    value: str,
    *,
    maximum_encoded_bytes: int,
    maximum_raw_bytes: int,
) -> bytes:
    if (
        not value
        or not value.isascii()
        or len(value) > maximum_encoded_bytes
        or _BASE64URL.fullmatch(value) is None
        or len(value.rstrip("=")) % 4 == 1
    ):
        raise CanonicalRawError("Gmail RAW base64url is invalid")
    unpadded = value.rstrip("=")
    padding = b"=" * (-len(unpadded) % 4)
    try:
        decoded = base64.b64decode(
            unpadded.encode("ascii") + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise CanonicalRawError("Gmail RAW base64url decode failed") from exc
    if not decoded or len(decoded) > maximum_raw_bytes:
        raise CanonicalRawError("decoded Gmail RAW exceeds the safe limit")
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != unpadded:
        raise CanonicalRawError("Gmail RAW base64url is not canonical")
    return decoded


def _selected_raw_headers(raw: bytes, names: tuple[str, ...]) -> HeaderSnapshot:
    try:
        parsed = BytesHeaderParser(policy=policy.default).parsebytes(raw, headersonly=True)
    except Exception as exc:
        raise CanonicalRawError("Gmail RAW headers cannot be parsed") from exc
    if parsed.defects:
        raise CanonicalRawError("Gmail RAW contains malformed headers")
    selected: list[tuple[str, str]] = []
    requested = {name.casefold() for name in names}
    for name, value in parsed.items():
        if name.casefold() in requested:
            defects = getattr(value, "defects", ())
            if defects:
                raise CanonicalRawError("Gmail RAW contains a malformed selected header")
            selected.append((name, str(value)))
    return HeaderSnapshot(tuple(selected))


def _decode_object(body: bytes) -> dict[str, object]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalRawError("messages.get RAW response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CanonicalRawError("messages.get RAW response must be an object")
    return cast(dict[str, object], value)
