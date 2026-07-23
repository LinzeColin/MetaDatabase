from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from stage6_support import canonical_with_attachments, synthetic_pdf

from moomooau_archive.attachment_inspector import (
    AttachmentDecision,
    AttachmentInspector,
    AttachmentKind,
)
from moomooau_archive.canonical_raw import CanonicalRawError, decode_gmail_raw
from moomooau_archive.gmail_guard import GmailEndpointGuard, GmailEndpointRejected
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.load_probe import LogicalObjectIndex
from moomooau_archive.public_inventory import (
    DatasetAvailability,
    PrivateDatasetObservation,
    PublicConclusion,
    PublicNextAction,
    PublicRunConclusion,
    PublicRunState,
    StrictPublicInventoryPublisher,
)
from moomooau_archive.secret_values import SecretBytes

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(200, b"{}")


@settings(max_examples=100, derandomize=True, database=None, deadline=None)
@given(st.binary(min_size=1, max_size=4096))
def test_t0601_canonical_gmail_raw_round_trip_property(raw: bytes) -> None:
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    assert (
        decode_gmail_raw(
            encoded,
            maximum_encoded_bytes=8192,
            maximum_raw_bytes=4096,
        )
        == raw
    )
    with pytest.raises(CanonicalRawError):
        decode_gmail_raw(
            encoded + "!",
            maximum_encoded_bytes=8192,
            maximum_raw_bytes=4096,
        )


@settings(max_examples=80, derandomize=True, database=None, deadline=None)
@given(
    st.sampled_from(
        (
            "messages/{value}/delete",
            "messages/{value}/modify",
            "messages/batchDelete",
            "messages/send",
            "threads/{value}/trash",
        )
    ),
    st.from_regex(r"[A-Za-z0-9_-]{1,32}", fullmatch=True),
)
def test_t0601_forbidden_gmail_endpoint_fuzz_rejects_before_transport(
    template: str,
    value: str,
) -> None:
    transport = RecordingTransport()
    guard = GmailEndpointGuard(transport)
    path = template.format(value=value)
    request = HttpRequest("POST", "https://gmail.googleapis.com/gmail/v1/users/me/" + path)
    with pytest.raises(GmailEndpointRejected):
        guard.send(request)
    assert transport.requests == []
    assert guard.metrics.forbidden_network_calls == 0


@settings(max_examples=80, derandomize=True, database=None, deadline=None)
@given(
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=30
    )
)
def test_t0601_path_fuzz_and_magic_byte_contract(name: str) -> None:
    canonical = canonical_with_attachments(
        (
            ("../" + name + ".pdf", "application", "pdf", synthetic_pdf()),
            ("safe.bin", "application", "octet-stream", synthetic_pdf()),
            (
                "active.pdf",
                "application",
                "pdf",
                b"%PDF-1.7\n/OpenAction /JavaScript\n%%EOF\n",
            ),
        ),
        suffix="property-attachment",
    )
    report = AttachmentInspector().inspect(canonical)
    assert report.attachments[0].decision is AttachmentDecision.QUARANTINED
    assert report.attachments[0].content is None
    assert report.attachments[1].kind is AttachmentKind.PDF
    assert report.attachments[1].decision is AttachmentDecision.SAFE
    assert report.attachments[2].reason_code == "ACTIVE_OR_POLYGLOT_PDF"


@settings(max_examples=100, derandomize=True, database=None, deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=80, unique=True))
def test_t0601_logical_idempotency_property(ordinals: list[int]) -> None:
    first = LogicalObjectIndex()
    second = LogicalObjectIndex()
    items = [
        (f"obj-{ordinal}", hashlib.sha256(str(ordinal).encode("ascii")).hexdigest())
        for ordinal in ordinals
    ]
    for object_id, digest in items:
        first.upsert(object_id, digest)
        first.upsert(object_id, digest)
    for object_id, digest in reversed(items):
        second.upsert(object_id, digest)
    assert first.object_count == second.object_count == len(items)
    assert first.merkle_root() == second.merkle_root()


@settings(max_examples=60, derandomize=True, database=None, deadline=None)
@given(
    st.binary(min_size=32, max_size=32),
    st.integers(min_value=1_000, max_value=1_000_000),
)
def test_t0601_public_redaction_property(private_root_bytes: bytes, exact_count: int) -> None:
    private_root = private_root_bytes.hex()
    observation = PrivateDatasetObservation(
        dataset_name="statements",
        schema_version="1.0.0",
        parser_versions=("1.0.0",),
        availability=DatasetAvailability.AVAILABLE,
        exact_count=exact_count,
        latest_recorded_at_utc=datetime(2026, 7, 20, tzinfo=UTC),
        private_snapshot_root=private_root,
    )
    conclusion = PublicRunConclusion(
        PublicRunState.HEALTHY,
        PublicConclusion.PASS,
        PublicConclusion.PASS,
        PublicNextAction.NONE,
    )
    key = SecretBytes(b"synthetic-stage6-property-root-key")
    try:
        document = StrictPublicInventoryPublisher().render(
            (observation,),
            conclusion,
            now_utc=datetime(2026, 7, 20, 1, tzinfo=UTC),
            opaque_root_key=key,
        )
    finally:
        key.destroy()
    text = document.payload.decode("utf-8")
    assert private_root not in text
    assert str(exact_count) not in text
    assert "private_snapshot_root" not in text


def test_t0601_stage6_contract_catalog_is_closed_and_machine_readable() -> None:
    local = json.loads(
        (PROJECT_ROOT / "machine/stages/S6/contracts/stage6_acceptance_contract.json").read_text(
            encoding="utf-8"
        )
    )
    items = local["acceptance_contracts"]
    assert [item["id"] for item in items] == [f"S6AC-00{index}" for index in range(1, 9)]
    assert [item["task_id"] for item in items] == [f"T060{index}" for index in range(1, 9)]
    assert all(
        set(item)
        >= {
            "environment",
            "input",
            "oracle",
            "threshold",
            "evidence_required",
            "verification",
            "failure_action",
        }
        for item in items
    )
