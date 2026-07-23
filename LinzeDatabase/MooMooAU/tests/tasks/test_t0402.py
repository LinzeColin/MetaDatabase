from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from stage4_support import stage4_context

from moomooau_archive.processed_models import ProcessingBoundaryError, ProcessingState

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_t0402_document_envelope_binds_verified_raw_times_labels_attachments_and_lineage() -> None:
    context = stage4_context()
    envelope = context.envelope
    private = envelope.to_private_dict()

    assert envelope.source_id == context.raw_plan.opaque_message_id
    assert envelope.source_id != context.canonical.message_id
    assert envelope.verification_decision == "VERIFIED"
    assert envelope.internal_date_utc.tzinfo is UTC
    assert envelope.received_at_sydney.tzinfo is not None
    assert getattr(envelope.received_at_sydney.tzinfo, "key", None) == "Australia/Sydney"
    assert envelope.received_at_sydney.astimezone(UTC) == envelope.internal_date_utc
    assert envelope.label_state == ("CATEGORY_UPDATES", "INBOX")
    assert len(envelope.attachments) == 1
    assert envelope.attachments[0].object_id is not None
    assert envelope.processing_state is ProcessingState.RAW_ONLY
    assert envelope.lineage.raw_plaintext_digest_private == context.canonical.plaintext_sha256
    assert envelope.lineage.raw_ciphertext_digest == context.raw_plan.objects[0].ciphertext_sha256
    assert envelope.lineage.attachment_object_ids == (envelope.attachments[0].object_id,)
    assert dict(envelope.lineage.field_lineage).keys() >= {
        "/document_class",
        "/gmail/internal_date_utc",
        "/gmail/label_state",
        "/verification",
        "/attachments/0",
    }
    assert private["source_id"] == envelope.source_id
    assert private["verification"]["sender_registry_version"] == "1.0.0"  # type: ignore[index]
    schema = json.loads(
        (
            PROJECT_ROOT / "machine/stages/S4/public-schemas/document-envelope-v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(private))
        == []
    )
    assert context.canonical.message_id not in repr(envelope)
    assert context.canonical.plaintext_sha256 not in repr(envelope)


def test_t0402_processing_lineage_merges_without_permitting_conflicting_provenance() -> None:
    envelope = stage4_context(message_suffix="lineage").envelope
    processed = envelope.with_processing(
        ProcessingState.UNSUPPORTED,
        "PROTECTED_PARSER_PROFILE_NOT_AVAILABLE",
        parser_name="protected-profile-parser",
        parser_version="1.0.0",
        field_lineage=(("/parser_state", "parser:explicit-safe-deferred"),),
    )
    lineage = dict(processed.lineage.field_lineage)
    assert lineage["/verification"] == "sender-verifier:pre-raw"
    assert lineage["/parser_state"] == "parser:explicit-safe-deferred"

    with pytest.raises(ProcessingBoundaryError, match="conflicts"):
        envelope.with_processing(
            ProcessingState.UNSUPPORTED,
            "PROTECTED_PARSER_PROFILE_NOT_AVAILABLE",
            parser_name="protected-profile-parser",
            parser_version="1.0.0",
            field_lineage=(("/verification", "untrusted:replacement"),),
        )
