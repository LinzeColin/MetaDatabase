"""Fail-closed Stage 4 classification, document-envelope and lineage models."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from enum import StrEnum
from pathlib import PurePosixPath
from typing import cast
from zoneinfo import ZoneInfo

from .attachment_inspector import (
    AttachmentDecision,
    AttachmentInspectionReport,
    AttachmentKind,
    InspectedAttachment,
)
from .canonical_raw import CanonicalRaw
from .raw_commit import RawCommitPlan, RawObjectRole
from .sender_registry import MessageVerification, SenderDecision, VerificationPhase

_CLASSIFICATION_SCHEMA = "moomooau.classification-registry.v1"
_REGISTRY_VERSION = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_RULE_ID = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
_OPAQUE_ID = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PARSER_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_KEY_EPOCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_CLASSIFICATION_SENTINEL = object()
_ENVELOPE_SENTINEL = object()


class ProcessingBoundaryError(RuntimeError):
    """Sensitive processing input failed before any persistence boundary."""


class DocumentClass(StrEnum):
    DAILY_STATEMENT = "DAILY_STATEMENT"
    MONTHLY_STATEMENT = "MONTHLY_STATEMENT"
    FINANCIAL_YEAR_SUMMARY = "FINANCIAL_YEAR_SUMMARY"
    CONTRACT_NOTE = "CONTRACT_NOTE"
    TRADE_NOTICE = "TRADE_NOTICE"
    CASH_NOTICE = "CASH_NOTICE"
    FX_NOTICE = "FX_NOTICE"
    DIVIDEND_NOTICE = "DIVIDEND_NOTICE"
    TAX_NOTICE = "TAX_NOTICE"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    TRANSFER_CUSTODY = "TRANSFER_CUSTODY"
    SECURITY_ALERT = "SECURITY_ALERT"
    KYC_COMPLIANCE = "KYC_COMPLIANCE"
    SUPPORT = "SUPPORT"
    FEE_NOTICE = "FEE_NOTICE"
    PROMOTION_REWARD = "PROMOTION_REWARD"
    RESEARCH_MARKETING = "RESEARCH_MARKETING"
    VERIFIED_UNKNOWN = "VERIFIED_UNKNOWN"


class ProcessingState(StrEnum):
    COMPLETE = "COMPLETE"
    WAITING_FOR_PDF_PASSWORD = "WAITING_FOR_PDF_PASSWORD"  # pragma: allowlist secret
    UNSUPPORTED = "UNSUPPORTED"
    QUARANTINED = "QUARANTINED"
    RAW_ONLY = "RAW_ONLY"


class ClassificationActivation(StrEnum):
    ACTIVE = "ACTIVE"
    EMPTY_PROTECTED_EVIDENCE_REQUIRED = "EMPTY_PROTECTED_EVIDENCE_REQUIRED"


@dataclass(frozen=True, slots=True, repr=False)
class ClassificationRule:
    rule_id: str
    document_class: DocumentClass
    subject_phrases_all: tuple[str, ...]
    attachment_kinds_any: tuple[AttachmentKind, ...]
    filename_suffixes_any: tuple[str, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        if (
            _RULE_ID.fullmatch(self.rule_id) is None
            or self.document_class is DocumentClass.VERIFIED_UNKNOWN
            or _SHA256.fullmatch(self.evidence_digest) is None
            or not (
                self.subject_phrases_all or self.attachment_kinds_any or self.filename_suffixes_any
            )
            or len(self.subject_phrases_all) > 16
            or len(self.attachment_kinds_any) > len(AttachmentKind)
            or len(self.filename_suffixes_any) > 16
        ):
            raise ProcessingBoundaryError("classification rule identity is invalid")
        for value in self.subject_phrases_all:
            if not _safe_rule_text(value, maximum=256):
                raise ProcessingBoundaryError("classification subject signal is invalid")
        for value in self.filename_suffixes_any:
            if (
                not _safe_rule_text(value, maximum=64)
                or not value.startswith(".")
                or "/" in value
                or "\\" in value
            ):
                raise ProcessingBoundaryError("classification filename signal is invalid")
        if len(set(self.attachment_kinds_any)) != len(self.attachment_kinds_any):
            raise ProcessingBoundaryError("classification attachment kinds are duplicated")

    def __repr__(self) -> str:
        return (
            f"ClassificationRule(rule_id=<redacted>, document_class={self.document_class.value!r}, "
            "signals=<redacted>, evidence_digest=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ClassificationRegistry:
    registry_version: str
    issued_at_utc: datetime
    activation: ClassificationActivation
    rules: tuple[ClassificationRule, ...]
    digest: str

    def __post_init__(self) -> None:
        offset = self.issued_at_utc.utcoffset()
        if (
            _REGISTRY_VERSION.fullmatch(self.registry_version) is None
            or self.issued_at_utc.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
            or _SHA256.fullmatch(self.digest) is None
            or tuple(rule.rule_id for rule in self.rules)
            != tuple(sorted(rule.rule_id for rule in self.rules))
            or len({rule.rule_id for rule in self.rules}) != len(self.rules)
        ):
            raise ProcessingBoundaryError("classification registry identity is invalid")
        if self.activation is ClassificationActivation.ACTIVE and not self.rules:
            raise ProcessingBoundaryError("active classification registry has no rules")
        if (
            self.activation is ClassificationActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
            and self.rules
        ):
            raise ProcessingBoundaryError("empty classification registry cannot contain rules")

    def __repr__(self) -> str:
        return (
            f"ClassificationRegistry(version={self.registry_version!r}, "
            f"activation={self.activation.value!r}, rule_count={len(self.rules)}, "
            "digest=<redacted>)"
        )

    @classmethod
    def from_json(cls, payload: bytes) -> ClassificationRegistry:
        if len(payload) > 2 * 1024 * 1024:
            raise ProcessingBoundaryError("classification registry exceeds the safe limit")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProcessingBoundaryError("classification registry is not valid JSON") from exc
        if not isinstance(value, dict):
            raise ProcessingBoundaryError("classification registry must be an object")
        required = {
            "schema_version",
            "registry_version",
            "issued_at_utc",
            "activation_state",
            "rules",
        }
        rules = value.get("rules")
        if (
            set(value) != required
            or value.get("schema_version") != _CLASSIFICATION_SCHEMA
            or not isinstance(rules, list)
        ):
            raise ProcessingBoundaryError("classification registry schema is invalid")
        try:
            return cls(
                registry_version=_required_string(value, "registry_version"),
                issued_at_utc=_parse_utc(_required_string(value, "issued_at_utc")),
                activation=ClassificationActivation(_required_string(value, "activation_state")),
                rules=tuple(_parse_rule(item) for item in rules),
                digest=hashlib.sha256(_canonical_json(value)).hexdigest(),
            )
        except ValueError as exc:
            raise ProcessingBoundaryError("classification registry enum value is invalid") from exc


@dataclass(frozen=True, slots=True, repr=False)
class DocumentClassification:
    document_class: DocumentClass
    reason_code: str
    registry_version: str
    registry_digest: str
    matched_rule_id: str | None
    canonical_plaintext_sha256: str
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._sentinel is not _CLASSIFICATION_SENTINEL
            or not self.reason_code
            or _REGISTRY_VERSION.fullmatch(self.registry_version) is None
            or _SHA256.fullmatch(self.registry_digest) is None
            or _SHA256.fullmatch(self.canonical_plaintext_sha256) is None
            or (
                self.matched_rule_id is not None
                and _RULE_ID.fullmatch(self.matched_rule_id) is None
            )
            or (self.document_class is DocumentClass.VERIFIED_UNKNOWN)
            != (self.matched_rule_id is None)
        ):
            raise ProcessingBoundaryError("classification was not issued by the classifier")

    def __repr__(self) -> str:
        return (
            f"DocumentClassification(document_class={self.document_class.value!r}, "
            f"reason_code={self.reason_code!r}, registry_version={self.registry_version!r}, "
            "registry_digest=<redacted>, matched_rule_id=<redacted>, "
            "canonical_plaintext_sha256=<redacted>)"
        )


class DocumentClassifier:
    """Classify only previously verified Canonical Raw using exact protected profiles."""

    classifier_version = "document-classifier-v1"

    def classify(
        self,
        canonical: CanonicalRaw,
        verification: MessageVerification,
        attachments: AttachmentInspectionReport,
        registry: ClassificationRegistry,
    ) -> DocumentClassification:
        _require_verified_canonical(canonical, verification, attachments)
        if attachments.message_quarantined:
            return self._unknown(canonical, registry, "ATTACHMENT_REPORT_QUARANTINED")
        subject = _subject_from_raw(canonical.data)
        if subject is None:
            return self._unknown(canonical, registry, "SUBJECT_MISSING_OR_AMBIGUOUS")
        matches = [
            rule for rule in registry.rules if _rule_matches(rule, subject, attachments.attachments)
        ]
        if len(matches) != 1:
            reason = "NO_PROTECTED_PROFILE_MATCH" if not matches else "PROFILE_MATCH_CONFLICT"
            return self._unknown(canonical, registry, reason)
        match = matches[0]
        return DocumentClassification(
            document_class=match.document_class,
            reason_code="EXACT_PROFILE_MATCH",
            registry_version=registry.registry_version,
            registry_digest=registry.digest,
            matched_rule_id=match.rule_id,
            canonical_plaintext_sha256=canonical.plaintext_sha256,
            _sentinel=_CLASSIFICATION_SENTINEL,
        )

    @staticmethod
    def _unknown(
        canonical: CanonicalRaw,
        registry: ClassificationRegistry,
        reason_code: str,
    ) -> DocumentClassification:
        return DocumentClassification(
            document_class=DocumentClass.VERIFIED_UNKNOWN,
            reason_code=reason_code,
            registry_version=registry.registry_version,
            registry_digest=registry.digest,
            matched_rule_id=None,
            canonical_plaintext_sha256=canonical.plaintext_sha256,
            _sentinel=_CLASSIFICATION_SENTINEL,
        )


@dataclass(frozen=True, slots=True, repr=False)
class AttachmentReference:
    ordinal: int
    object_id: str | None
    kind: AttachmentKind
    decision: AttachmentDecision

    def __post_init__(self) -> None:
        if self.ordinal <= 0 or (
            self.object_id is not None and _OPAQUE_ID.fullmatch(self.object_id) is None
        ):
            raise ProcessingBoundaryError("attachment reference is invalid")

    def __repr__(self) -> str:
        return (
            f"AttachmentReference(ordinal={self.ordinal}, object_id=<redacted>, "
            f"kind={self.kind.value!r}, decision={self.decision.value!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class PrivateLineage:
    source_id: str
    source_message_id_hmac: str
    raw_ciphertext_digest: str
    raw_plaintext_digest_private: str
    attachment_object_ids: tuple[str, ...]
    parser_name: str
    parser_version: str
    schema_version: str
    imported_at_utc: datetime
    field_lineage: tuple[tuple[str, str], ...]
    key_epoch: str

    def __post_init__(self) -> None:
        offset = self.imported_at_utc.utcoffset()
        if (
            _OPAQUE_ID.fullmatch(self.source_id) is None
            or _OPAQUE_ID.fullmatch(self.source_message_id_hmac) is None
            or _SHA256.fullmatch(self.raw_ciphertext_digest) is None
            or _SHA256.fullmatch(self.raw_plaintext_digest_private) is None
            or any(_OPAQUE_ID.fullmatch(value) is None for value in self.attachment_object_ids)
            or len(set(self.attachment_object_ids)) != len(self.attachment_object_ids)
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _REGISTRY_VERSION.fullmatch(self.parser_version) is None
            or _REGISTRY_VERSION.fullmatch(self.schema_version) is None
            or self.imported_at_utc.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
            or _KEY_EPOCH.fullmatch(self.key_epoch) is None
            or not self.field_lineage
            or tuple(key for key, _ in self.field_lineage)
            != tuple(sorted(key for key, _ in self.field_lineage))
            or len({key for key, _ in self.field_lineage}) != len(self.field_lineage)
            or any(not key.startswith("/") or not value for key, value in self.field_lineage)
        ):
            raise ProcessingBoundaryError("private lineage is invalid")

    def __repr__(self) -> str:
        return (
            "PrivateLineage(source_id=<redacted>, source_message_id_hmac=<redacted>, "
            "raw_ciphertext_digest=<redacted>, raw_plaintext_digest_private=<redacted>, "
            f"attachment_count={len(self.attachment_object_ids)}, "
            f"parser_name={self.parser_name!r}, parser_version={self.parser_version!r}, "
            f"schema_version={self.schema_version!r}, imported_at_utc=<redacted>, "
            "field_lineage=<redacted>, key_epoch=<redacted>)"
        )

    def to_private_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_message_id_hmac": self.source_message_id_hmac,
            "raw_ciphertext_digest": self.raw_ciphertext_digest,
            "raw_plaintext_digest_private": self.raw_plaintext_digest_private,
            "attachment_object_ids": list(self.attachment_object_ids),
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "schema_version": self.schema_version,
            "imported_at_utc": _utc_text(self.imported_at_utc),
            "field_lineage": dict(self.field_lineage),
            "key_epoch": self.key_epoch,
        }


@dataclass(frozen=True, slots=True, repr=False)
class DocumentEnvelope:
    schema_version: str
    source_id: str
    document_class: DocumentClass
    classification_reason: str
    verification_decision: str
    verifier_version: str
    sender_registry_version: str
    classification_registry_version: str
    internal_date_utc: datetime
    received_at_sydney: datetime
    label_state: tuple[str, ...]
    attachments: tuple[AttachmentReference, ...]
    processing_state: ProcessingState
    processing_reason: str
    lineage: PrivateLineage
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        utc_offset = self.internal_date_utc.utcoffset()
        sydney_offset = self.received_at_sydney.utcoffset()
        if (
            self._sentinel is not _ENVELOPE_SENTINEL
            or self.schema_version != "1.0.0"
            or self.source_id != self.lineage.source_id
            or not self.classification_reason
            or self.verification_decision != "VERIFIED"
            or not self.verifier_version
            or _REGISTRY_VERSION.fullmatch(self.sender_registry_version) is None
            or _REGISTRY_VERSION.fullmatch(self.classification_registry_version) is None
            or self.internal_date_utc.tzinfo is None
            or utc_offset is None
            or utc_offset.total_seconds() != 0
            or self.received_at_sydney.tzinfo is None
            or sydney_offset is None
            or self.received_at_sydney.astimezone(UTC) != self.internal_date_utc
            or tuple(sorted(self.label_state)) != self.label_state
            or len(set(self.label_state)) != len(self.label_state)
            or any(_SAFE_LABEL.fullmatch(label) is None for label in self.label_state)
            or any(label in {"SENT", "DRAFT"} for label in self.label_state)
            or tuple(item.ordinal for item in self.attachments)
            != tuple(range(1, len(self.attachments) + 1))
            or not self.processing_reason
        ):
            raise ProcessingBoundaryError("document envelope is invalid")

    def __repr__(self) -> str:
        return (
            f"DocumentEnvelope(schema_version={self.schema_version!r}, source_id=<redacted>, "
            f"document_class={self.document_class.value!r}, "
            f"verification_decision={self.verification_decision!r}, "
            "internal_date_utc=<redacted>, received_at_sydney=<redacted>, "
            f"label_count={len(self.label_state)}, attachment_count={len(self.attachments)}, "
            f"processing_state={self.processing_state.value!r}, "
            f"processing_reason={self.processing_reason!r}, lineage=<redacted>)"
        )

    def with_processing(
        self,
        state: ProcessingState,
        reason_code: str,
        *,
        parser_name: str,
        parser_version: str,
        field_lineage: tuple[tuple[str, str], ...],
    ) -> DocumentEnvelope:
        combined_lineage = dict(self.lineage.field_lineage)
        for key, value in field_lineage:
            prior = combined_lineage.get(key)
            if prior is not None and prior != value:
                raise ProcessingBoundaryError("processing lineage conflicts with envelope lineage")
            combined_lineage[key] = value
        lineage = replace(
            self.lineage,
            parser_name=parser_name,
            parser_version=parser_version,
            field_lineage=tuple(sorted(combined_lineage.items())),
        )
        return replace(
            self,
            processing_state=state,
            processing_reason=reason_code,
            lineage=lineage,
            _sentinel=_ENVELOPE_SENTINEL,
        )

    def to_private_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "document_class": self.document_class.value,
            "classification": {
                "reason_code": self.classification_reason,
                "registry_version": self.classification_registry_version,
            },
            "verification": {
                "decision": self.verification_decision,
                "verifier_version": self.verifier_version,
                "sender_registry_version": self.sender_registry_version,
            },
            "gmail": {
                "internal_date_utc": _utc_text(self.internal_date_utc),
                "received_at_sydney": self.received_at_sydney.isoformat(),
                "label_state": list(self.label_state),
            },
            "attachments": [
                {
                    "ordinal": item.ordinal,
                    "object_id": item.object_id,
                    "kind": item.kind.value,
                    "decision": item.decision.value,
                }
                for item in self.attachments
            ],
            "processing_state": self.processing_state.value,
            "processing_reason": self.processing_reason,
            "lineage": self.lineage.to_private_dict(),
        }


class DocumentEnvelopeFactory:
    """Bind a classifier result to the verified Raw plan without exposing Gmail IDs."""

    verifier_version = "sender-verifier-v1"

    def issue(
        self,
        canonical: CanonicalRaw,
        verification: MessageVerification,
        attachments: AttachmentInspectionReport,
        raw_plan: RawCommitPlan,
        classification: DocumentClassification,
        *,
        imported_at_utc: datetime,
        recovered_raw_ciphertext_sha256: str | None = None,
    ) -> DocumentEnvelope:
        _require_verified_canonical(canonical, verification, attachments)
        if (
            classification.canonical_plaintext_sha256 != canonical.plaintext_sha256
            or classification.registry_version == ""
            or raw_plan.key_epoch == ""
        ):
            raise ProcessingBoundaryError("classification or Raw plan is not bound to the message")
        raw_objects = [item for item in raw_plan.objects if item.role is RawObjectRole.MESSAGE]
        if (
            len(raw_objects) != 1
            or raw_objects[0].plaintext_sha256 != canonical.plaintext_sha256
            or raw_plan.opaque_message_id == canonical.message_id
            or (
                recovered_raw_ciphertext_sha256 is not None
                and _SHA256.fullmatch(recovered_raw_ciphertext_sha256) is None
            )
        ):
            raise ProcessingBoundaryError("Raw plan does not identify the Canonical Raw")
        attachment_ids = _attachment_ids(raw_plan)
        references: list[AttachmentReference] = []
        for attachment in attachments.attachments:
            object_id = (
                attachment_ids.get(attachment.plaintext_sha256)
                if attachment.plaintext_sha256 is not None
                else None
            )
            if attachment.content is not None and object_id is None:
                raise ProcessingBoundaryError("Raw plan omitted an inspected attachment object")
            references.append(
                AttachmentReference(
                    ordinal=attachment.ordinal,
                    object_id=object_id,
                    kind=attachment.kind,
                    decision=attachment.decision,
                )
            )
        imported = _require_utc(imported_at_utc)
        internal = datetime.fromtimestamp(canonical.internal_date_ms / 1000, tz=UTC)
        initial_state = (
            ProcessingState.QUARANTINED
            if attachments.message_quarantined
            else ProcessingState.RAW_ONLY
        )
        initial_reason = attachments.message_reason_code or "PARSER_NOT_RUN"
        field_lineage = tuple(
            sorted(
                {
                    "/document_class": "classifier:protected-profile-or-verified-unknown",
                    "/gmail/internal_date_utc": "gmail:internalDate",
                    "/gmail/label_state": "gmail:labelIds",
                    "/verification": "sender-verifier:pre-raw",
                    **{
                        f"/attachments/{item.ordinal - 1}": f"canonical-mime-part:{item.ordinal}"
                        for item in references
                    },
                }.items()
            )
        )
        lineage = PrivateLineage(
            source_id=raw_plan.opaque_message_id,
            source_message_id_hmac=raw_plan.opaque_message_id,
            raw_ciphertext_digest=(
                recovered_raw_ciphertext_sha256 or raw_objects[0].ciphertext_sha256
            ),
            raw_plaintext_digest_private=canonical.plaintext_sha256,
            attachment_object_ids=tuple(
                sorted({item.object_id for item in references if item.object_id is not None})
            ),
            parser_name="document-classifier",
            parser_version=classification.registry_version,
            schema_version="1.0.0",
            imported_at_utc=imported,
            field_lineage=field_lineage,
            key_epoch=raw_plan.key_epoch,
        )
        return DocumentEnvelope(
            schema_version="1.0.0",
            source_id=raw_plan.opaque_message_id,
            document_class=classification.document_class,
            classification_reason=classification.reason_code,
            verification_decision="VERIFIED",
            verifier_version=self.verifier_version,
            sender_registry_version=verification.registry_version,
            classification_registry_version=classification.registry_version,
            internal_date_utc=internal,
            received_at_sydney=internal.astimezone(ZoneInfo("Australia/Sydney")),
            label_state=tuple(sorted(canonical.label_ids)),
            attachments=tuple(references),
            processing_state=initial_state,
            processing_reason=initial_reason,
            lineage=lineage,
            _sentinel=_ENVELOPE_SENTINEL,
        )


def _parse_rule(value: object) -> ClassificationRule:
    if not isinstance(value, dict):
        raise ProcessingBoundaryError("classification rule must be an object")
    required = {
        "rule_id",
        "document_class",
        "subject_phrases_all",
        "attachment_kinds_any",
        "filename_suffixes_any",
        "evidence_digest",
    }
    if set(value) != required:
        raise ProcessingBoundaryError("classification rule schema is invalid")
    return ClassificationRule(
        rule_id=_required_string(value, "rule_id"),
        document_class=DocumentClass(_required_string(value, "document_class")),
        subject_phrases_all=_string_tuple(value, "subject_phrases_all"),
        attachment_kinds_any=tuple(
            AttachmentKind(item) for item in _string_tuple(value, "attachment_kinds_any")
        ),
        filename_suffixes_any=_string_tuple(value, "filename_suffixes_any"),
        evidence_digest=_required_string(value, "evidence_digest"),
    )


def _rule_matches(
    rule: ClassificationRule,
    subject: str,
    attachments: tuple[InspectedAttachment, ...],
) -> bool:
    folded_subject = _fold(subject)
    if rule.subject_phrases_all and not all(
        _fold(phrase) in folded_subject for phrase in rule.subject_phrases_all
    ):
        return False
    safe_attachments = [item for item in attachments if item.decision is AttachmentDecision.SAFE]
    if rule.attachment_kinds_any and not any(
        item.kind in rule.attachment_kinds_any for item in safe_attachments
    ):
        return False
    if rule.filename_suffixes_any and not any(
        any(_fold(item.filename).endswith(_fold(suffix)) for suffix in rule.filename_suffixes_any)
        for item in safe_attachments
    ):
        return False
    return True


def _require_verified_canonical(
    canonical: CanonicalRaw,
    verification: MessageVerification,
    attachments: AttachmentInspectionReport,
) -> None:
    if (
        verification.phase is not VerificationPhase.PRE_RAW
        or verification.decision is not SenderDecision.VERIFIED
        or verification.raw_fetch_permit is None
        or verification.message_id != canonical.message_id
        or verification.internal_date_ms != canonical.internal_date_ms
        or attachments.canonical_plaintext_sha256 != canonical.plaintext_sha256
        or any(label in {"SENT", "DRAFT"} for label in canonical.label_ids)
    ):
        raise ProcessingBoundaryError("processing input is not verified Canonical Raw")


def _subject_from_raw(raw: bytes) -> str | None:
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except (TypeError, ValueError) as exc:
        raise ProcessingBoundaryError("Canonical Raw headers cannot be parsed") from exc
    if message.defects:
        return None
    subjects = message.get_all("Subject", [])
    if len(subjects) != 1:
        return None
    subject = str(subjects[0])
    return subject if _safe_rule_text(subject, maximum=2048) else None


def _attachment_ids(plan: RawCommitPlan) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in plan.objects:
        if item.role is not RawObjectRole.ATTACHMENT:
            continue
        name = PurePosixPath(item.relative_path).name
        if not name.endswith(".bin.age"):
            raise ProcessingBoundaryError("Raw attachment path is invalid")
        object_id = name.removesuffix(".bin.age")
        if _OPAQUE_ID.fullmatch(object_id) is None:
            raise ProcessingBoundaryError("Raw attachment object ID is invalid")
        prior = result.setdefault(item.plaintext_sha256, object_id)
        if prior != object_id:
            raise ProcessingBoundaryError("Raw attachment digest maps to multiple objects")
    return result


def _safe_rule_text(value: str, *, maximum: int) -> bool:
    return (
        bool(value)
        and len(value) <= maximum
        and unicodedata.normalize("NFKC", value) == value
        and not any(unicodedata.category(character).startswith("C") for character in value)
    )


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ProcessingBoundaryError(f"classification registry field {key} is invalid")
    return item


def _string_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or not all(isinstance(entry, str) for entry in item):
        raise ProcessingBoundaryError(f"classification registry list {key} is invalid")
    return tuple(cast(list[str], item))


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProcessingBoundaryError("classification registry timestamp is invalid") from exc
    return _require_utc(parsed)


def _require_utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ProcessingBoundaryError("timestamp must be UTC")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
