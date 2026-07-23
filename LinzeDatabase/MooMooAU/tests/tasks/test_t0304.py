from __future__ import annotations

import json

import pytest
from stage3_support import (
    authentication_results,
    metadata_headers,
    registry_payload,
    synthetic_address,
    synthetic_registry,
)

from moomooau_archive.gmail_discovery import HeaderSnapshot, MessageRef, MinimalMessage
from moomooau_archive.sender_registry import (
    SenderDecision,
    SenderRegistry,
    SenderVerifier,
    VerificationPhase,
    double_verification_matches,
)


def _minimal(
    *,
    message_id: str = "synthetic-1",
    sender: str | None = None,
    auth: str | None = None,
    subject: str = "Synthetic Moomoo AU Daily fixture",
    template: str = "AU-DAILY-V1",
    labels: tuple[str, ...] = ("INBOX",),
    history_id: str = "100",
) -> MinimalMessage:
    return MinimalMessage(
        ref=MessageRef(message_id, "thread-" + message_id),
        history_id=history_id,
        internal_date_ms=1_767_225_600_000,
        label_ids=labels,
        headers=HeaderSnapshot(
            metadata_headers(
                sender=sender,
                auth_results=auth,
                subject=subject,
                template=template,
            )
        ),
    )


def test_t0304_independent_pre_raw_and_pre_m3_verification_match_only_when_stable() -> None:
    registry = synthetic_registry()
    verifier = SenderVerifier()
    first = verifier.verify_message(
        _minimal(history_id="100"),
        registry,
        phase=VerificationPhase.PRE_RAW,
    )
    second = verifier.verify_message(
        _minimal(history_id="101", labels=("CATEGORY_UPDATES",)),
        registry,
        phase=VerificationPhase.PRE_M3,
    )
    assert first.decision is second.decision is SenderDecision.VERIFIED
    assert first.raw_fetch_permit is not None
    assert second.raw_fetch_permit is None
    assert double_verification_matches(first, second)
    assert first.message_id not in repr(first)
    assert str(first.internal_date_ms) not in repr(first)
    assert first.entry_id is not None and first.entry_id not in repr(first)
    assert first.entry_id not in repr(first.raw_fetch_permit)

    different_message = verifier.verify_message(
        _minimal(message_id="synthetic-2", history_id="101"),
        registry,
        phase=VerificationPhase.PRE_M3,
    )
    assert different_message.decision is SenderDecision.VERIFIED
    assert not double_verification_matches(first, different_message)

    changed = verifier.verify_message(
        _minimal(template="AU-CHANGED-V2"),
        registry,
        phase=VerificationPhase.PRE_M3,
    )
    assert changed.decision is SenderDecision.REJECTED
    assert not double_verification_matches(first, changed)

    new_payload = json.loads(registry_payload())
    new_payload["registry_version"] = "1.0.1"
    newer = SenderRegistry.from_json(
        json.dumps(new_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    new_second = verifier.verify_message(
        _minimal(),
        newer,
        phase=VerificationPhase.PRE_M3,
    )
    assert new_second.decision is SenderDecision.VERIFIED
    assert not double_verification_matches(first, new_second)


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (
            _minimal(sender=synthetic_address("statements", "synthetic-lookalike.invalid")),
            SenderDecision.UNKNOWN,
        ),
        (
            _minimal(auth=authentication_results(dkim="fail")),
            SenderDecision.REJECTED,
        ),
        (
            _minimal(auth=authentication_results(spf="fail")),
            SenderDecision.REJECTED,
        ),
        (
            _minimal(auth=authentication_results(dmarc="fail")),
            SenderDecision.REJECTED,
        ),
        (
            _minimal(subject="Unrelated synthetic subject"),
            SenderDecision.REJECTED,
        ),
        (
            _minimal(labels=("SENT",)),
            SenderDecision.REJECTED,
        ),
        (
            _minimal(labels=("DRAFT",)),
            SenderDecision.REJECTED,
        ),
    ],
)
def test_t0304_spoof_auth_fingerprint_and_outbound_cases_fail_closed(
    candidate: MinimalMessage,
    expected: SenderDecision,
) -> None:
    result = SenderVerifier().verify_message(
        candidate,
        synthetic_registry(),
        phase=VerificationPhase.PRE_RAW,
    )
    assert result.decision is expected
    assert result.raw_fetch_permit is None


def test_t0304_conflicting_trusted_authentication_results_and_multiple_from_quarantine() -> None:
    valid = metadata_headers()
    conflicting = HeaderSnapshot(
        valid
        + (
            (
                "Authentication-Results",
                authentication_results(dkim="fail"),
            ),
        )
    )
    message = MinimalMessage(
        ref=MessageRef("synthetic-1", "thread-synthetic-1"),
        history_id="100",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        headers=conflicting,
    )
    result = SenderVerifier().verify_message(
        message,
        synthetic_registry(),
        phase=VerificationPhase.PRE_RAW,
    )
    assert result.decision is SenderDecision.REJECTED
    assert result.raw_fetch_permit is None

    duplicate_from = HeaderSnapshot(valid + (("From", "Another <" + synthetic_address() + ">"),))
    duplicate = MinimalMessage(
        ref=message.ref,
        history_id=message.history_id,
        internal_date_ms=message.internal_date_ms,
        label_ids=message.label_ids,
        headers=duplicate_from,
    )
    duplicate_result = SenderVerifier().verify_message(
        duplicate,
        synthetic_registry(),
        phase=VerificationPhase.PRE_RAW,
    )
    assert duplicate_result.decision is SenderDecision.QUARANTINED
    assert duplicate_result.raw_fetch_permit is None


def test_t0304_rfc8601_dkim_header_i_is_verified_without_weakening_conflicts() -> None:
    sender = synthetic_address()
    gmail_style = (
        "mx.google.com; "
        f"spf=pass smtp.mailfrom={sender}; "
        "dkim=pass header.i=@synthetic.invalid; "
        "dmarc=pass header.from=synthetic.invalid"
    )
    verified = SenderVerifier().verify_message(
        _minimal(auth=gmail_style),
        synthetic_registry(),
        phase=VerificationPhase.PRE_RAW,
    )
    assert verified.decision is SenderDecision.VERIFIED
    assert verified.raw_fetch_permit is not None

    conflicting = gmail_style.replace(
        "header.i=@synthetic.invalid",
        "header.i=@synthetic.invalid header.d=unrelated.invalid",
    )
    rejected = SenderVerifier().verify_message(
        _minimal(auth=conflicting),
        synthetic_registry(),
        phase=VerificationPhase.PRE_RAW,
    )
    assert rejected.decision is SenderDecision.REJECTED
    assert rejected.raw_fetch_permit is None


def test_t0304_one_thousand_unrelated_metadata_records_yield_zero_raw_permits() -> None:
    verifier = SenderVerifier()
    registry = synthetic_registry()
    decisions = [
        verifier.verify_message(
            _minimal(
                message_id=f"unrelated-{index:04d}",
                sender=synthetic_address(f"newsletter-{index:04d}", "unrelated.invalid"),
            ),
            registry,
            phase=VerificationPhase.PRE_RAW,
        )
        for index in range(1000)
    ]
    assert all(item.decision is SenderDecision.UNKNOWN for item in decisions)
    assert sum(item.raw_fetch_permit is not None for item in decisions) == 0
