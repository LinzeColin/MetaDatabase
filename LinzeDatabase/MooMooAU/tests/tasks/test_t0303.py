from __future__ import annotations

import json
from pathlib import Path

import pytest
from stage3_support import metadata_headers, registry_payload, synthetic_address, synthetic_registry

from moomooau_archive.gmail_discovery import HeaderSnapshot, MessageRef, MinimalMessage
from moomooau_archive.sender_registry import (
    RegistryActivation,
    SenderDecision,
    SenderRegistry,
    SenderRegistryError,
    SenderVerifier,
    VerificationPhase,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _minimal(sender: str) -> MinimalMessage:
    return MinimalMessage(
        ref=MessageRef("synthetic-1", "thread-synthetic-1"),
        history_id="100",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        headers=HeaderSnapshot(metadata_headers(sender=sender)),
    )


def test_t0303_committed_registry_is_versioned_empty_and_requires_protected_evidence() -> None:
    path = PROJECT_ROOT / "machine/stages/S3/registry/verified-senders.v1.json"
    registry = SenderRegistry.from_json(path.read_bytes())
    assert registry.registry_version == "1.0.0"
    assert registry.activation is RegistryActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
    assert registry.entries == ()
    assert registry.requested_header_names == (
        "Authentication-Results",
        "From",
        "Subject",
    )
    assert chr(64) not in path.read_text(encoding="utf-8")


def test_t0303_unknown_sender_never_receives_raw_fetch_permit() -> None:
    registry = synthetic_registry()
    unknown = _minimal(synthetic_address("new-template"))
    result = SenderVerifier().verify_message(
        unknown,
        registry,
        phase=VerificationPhase.PRE_RAW,
    )
    assert result.decision is SenderDecision.UNKNOWN
    assert result.reason_code == "SENDER_NOT_REGISTERED"
    assert result.raw_fetch_permit is None
    assert synthetic_address("new-template") not in repr(result)


def test_t0303_active_registry_accepts_only_exact_canonical_evidence_backed_entry() -> None:
    registry = synthetic_registry()
    assert registry.activation is RegistryActivation.ACTIVE
    assert len(registry.entries) == 1
    assert registry.entries[0].exact_address == synthetic_address()
    assert registry.active_entry_for(synthetic_address()) is not None
    assert registry.active_entry_for(synthetic_address("other")) is None
    assert synthetic_address() not in repr(registry)
    assert synthetic_address() not in repr(registry.entries[0])
    assert registry.entries[0].entry_id not in repr(registry.entries[0])


@pytest.mark.parametrize(
    "mutation",
    [
        "wildcard",
        "uppercase_local_part",
        "third_party_weak",
        "unverified_source",
        "invalid_activation",
    ],
)
def test_t0303_registry_rejects_wildcards_weak_third_parties_and_unknown_evidence(
    mutation: str,
) -> None:
    payload = json.loads(registry_payload())
    entry = payload["entries"][0]
    if mutation == "wildcard":
        entry["exact_address"] = "*" + chr(64) + "synthetic.invalid"
    elif mutation == "uppercase_local_part":
        entry["exact_address"] = entry["exact_address"].replace("statements", "STATEMENTS")
    elif mutation == "third_party_weak":
        entry["third_party"] = True
        entry["fingerprint"]["required_headers"] = []
    elif mutation == "unverified_source":
        entry["evidence"]["source_type"] = "UNVERIFIED_CANDIDATE"
    else:
        payload["activation_state"] = "UNRECOGNIZED"
    with pytest.raises(SenderRegistryError):
        SenderRegistry.from_json(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
