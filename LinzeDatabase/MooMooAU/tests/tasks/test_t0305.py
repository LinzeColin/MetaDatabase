from __future__ import annotations

import hashlib

import pytest
from stage3_support import (
    SyntheticGmailMessage,
    SyntheticGmailTransport,
    make_raw_message,
    metadata_headers,
    synthetic_address,
    synthetic_registry,
)

from moomooau_archive.canonical_raw import (
    CanonicalRawError,
    CanonicalRawFetcher,
    decode_gmail_raw,
)
from moomooau_archive.gmail_discovery import GmailReadClient
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.sender_registry import SenderDecision, SenderVerifier, VerificationPhase


def _transport_message(*, sender: str | None = None) -> SyntheticGmailMessage:
    message_id = "synthetic-raw-1"
    raw = make_raw_message(
        message_id=message_id,
        sender=sender,
        attachments=(
            ("synthetic.pdf", "application", "octet-stream", b"%PDF-1.7\n%%EOF\n"),
            ("synthetic.csv", "text", "csv", b"kind,value\nsynthetic,1\n"),
        ),
    )
    return SyntheticGmailMessage(
        message_id=message_id,
        thread_id="thread-synthetic-raw-1",
        labels=("INBOX",),
        history_id="300",
        internal_date_ms=1_767_225_600_000,
        headers=metadata_headers(sender=sender),
        raw=raw,
    )


def test_t0305_authorized_gmail_raw_is_byte_exact_and_never_reconstructed() -> None:
    message = _transport_message()
    transport = SyntheticGmailTransport((message,))
    guard = GmailEndpointGuard(transport)
    client = GmailReadClient(guard)
    registry = synthetic_registry()
    verifier = SenderVerifier()
    metadata = client.get_metadata(
        message.message_id,
        header_names=registry.requested_header_names,
    )
    verification = verifier.verify_message(
        metadata,
        registry,
        phase=VerificationPhase.PRE_RAW,
    )
    assert verification.decision is SenderDecision.VERIFIED
    assert verification.raw_fetch_permit is not None

    canonical = CanonicalRawFetcher(guard, verifier).fetch(
        verification.raw_fetch_permit,
        registry,
    )
    assert canonical.data == message.raw
    assert canonical.byte_count == len(message.raw)
    assert canonical.plaintext_sha256 == hashlib.sha256(message.raw).hexdigest()
    assert transport.metadata_fetches == [message.message_id]
    assert transport.raw_fetches == [message.message_id]
    assert message.message_id not in repr(canonical)
    assert str(message.internal_date_ms) not in repr(canonical)
    assert str(len(message.raw)) not in repr(canonical)
    assert message.raw.hex()[:32] not in repr(canonical)


def test_t0305_unknown_sender_cannot_obtain_the_required_raw_permit() -> None:
    message = _transport_message(sender=synthetic_address("unknown"))
    transport = SyntheticGmailTransport((message,))
    guard = GmailEndpointGuard(transport)
    registry = synthetic_registry()
    metadata = GmailReadClient(guard).get_metadata(
        message.message_id,
        header_names=registry.requested_header_names,
    )
    verification = SenderVerifier().verify_message(
        metadata,
        registry,
        phase=VerificationPhase.PRE_RAW,
    )
    assert verification.decision is SenderDecision.UNKNOWN
    assert verification.raw_fetch_permit is None
    assert transport.raw_fetches == []


@pytest.mark.parametrize(
    "value",
    [
        "",
        "!!!",
        "A",
        "AB",
        "c3ludGhldGlj\n",
        "c3ludGhldGlj===",
    ],
)
def test_t0305_strict_base64url_decoder_rejects_ambiguous_or_invalid_input(value: str) -> None:
    with pytest.raises(CanonicalRawError):
        decode_gmail_raw(
            value,
            maximum_encoded_bytes=1024,
            maximum_raw_bytes=1024,
        )


def test_t0305_raw_fetch_refuses_registry_change_after_first_verification() -> None:
    message = _transport_message()
    transport = SyntheticGmailTransport((message,))
    guard = GmailEndpointGuard(transport)
    first_registry = synthetic_registry()
    metadata = GmailReadClient(guard).get_metadata(
        message.message_id,
        header_names=first_registry.requested_header_names,
    )
    verifier = SenderVerifier()
    first = verifier.verify_message(metadata, first_registry, phase=VerificationPhase.PRE_RAW)
    assert first.raw_fetch_permit is not None

    from_json = first_registry.from_json
    changed_payload = (
        b'{"activation_state":"EMPTY_PROTECTED_EVIDENCE_REQUIRED","entries":[],"issued_at_utc":'
        b'"2026-01-01T00:00:00Z","registry_version":"1.0.1","schema_version":'
        b'"moomooau.sender-registry.v1"}'
    )
    changed_registry = from_json(changed_payload)
    with pytest.raises(CanonicalRawError, match="registry changed"):
        CanonicalRawFetcher(guard, verifier).fetch(first.raw_fetch_permit, changed_registry)
    assert transport.raw_fetches == []
