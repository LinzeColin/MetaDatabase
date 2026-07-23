from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from stage4_support import (
    classification_registry_payload,
    csv_statement,
    verified_inputs,
)

from moomooau_archive.attachment_inspector import AttachmentKind
from moomooau_archive.processed_models import (
    ClassificationActivation,
    ClassificationRegistry,
    DocumentClass,
    DocumentClassifier,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_t0401_all_frozen_document_classes_are_unique_and_verified_unknown_is_retained() -> None:
    expected = (
        "DAILY_STATEMENT",
        "MONTHLY_STATEMENT",
        "FINANCIAL_YEAR_SUMMARY",
        "CONTRACT_NOTE",
        "TRADE_NOTICE",
        "CASH_NOTICE",
        "FX_NOTICE",
        "DIVIDEND_NOTICE",
        "TAX_NOTICE",
        "CORPORATE_ACTION",
        "TRANSFER_CUSTODY",
        "SECURITY_ALERT",
        "KYC_COMPLIANCE",
        "SUPPORT",
        "FEE_NOTICE",
        "PROMOTION_REWARD",
        "RESEARCH_MARKETING",
        "VERIFIED_UNKNOWN",
    )
    assert tuple(value.value for value in DocumentClass) == expected
    payload = classification_registry_payload(
        tuple(
            (document_class, AttachmentKind.CSV)
            for document_class in DocumentClass
            if document_class is not DocumentClass.VERIFIED_UNKNOWN
        )
    )
    registry = ClassificationRegistry.from_json(payload)
    schema = json.loads(
        (
            PROJECT_ROOT / "machine/stages/S4/public-schemas/classification-registry-v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        list(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                json.loads(payload)
            )
        )
        == []
    )
    classifier = DocumentClassifier()
    observed: list[DocumentClass] = []
    for index, expected_class in enumerate(DocumentClass, start=1):
        verified = verified_inputs(
            expected_class,
            csv_statement(),
            AttachmentKind.CSV,
            message_suffix=str(index),
        )
        result = classifier.classify(
            verified.canonical,
            verified.verification,
            verified.attachments,
            registry,
        )
        observed.append(result.document_class)
        if expected_class is DocumentClass.VERIFIED_UNKNOWN:
            assert result.reason_code == "NO_PROTECTED_PROFILE_MATCH"
            assert result.matched_rule_id is None
        else:
            assert result.document_class is expected_class
            assert result.reason_code == "EXACT_PROFILE_MATCH"
            assert result.matched_rule_id is not None
    assert tuple(observed) == tuple(DocumentClass)


def test_t0401_production_classification_registry_stays_empty_without_protected_evidence() -> None:
    path = PROJECT_ROOT / "machine/stages/S4/registry/document-classification.v1.json"
    registry = ClassificationRegistry.from_json(path.read_bytes())
    assert registry.registry_version == "1.0.0"
    assert registry.activation is ClassificationActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
    assert registry.rules == ()
    assert "synthetic.invalid" not in path.read_text(encoding="utf-8")
