"""Immutable boundary models for the Stage 1 synthetic pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class VerificationDecision(StrEnum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class AuthenticationResults:
    spf: str
    dkim: str
    dmarc: str

    @property
    def all_pass(self) -> bool:
        return all(value == "PASS" for value in (self.spf, self.dkim, self.dmarc))


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    source_id: str
    sender: str
    internal_date_ms: int
    labels: tuple[str, ...]
    authentication: AuthenticationResults
    synthetic_origin: bool


@dataclass(frozen=True, slots=True)
class SyntheticMessage:
    metadata: CandidateMetadata
    raw: bytes


@dataclass(frozen=True, slots=True)
class VerificationResult:
    decision: VerificationDecision
    document_class: str | None
    reason_code: str
    verifier_version: str = "stage1-synthetic-v1"


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    decision: VerificationDecision
    raw_fetched: bool
    remote_recovered: bool
    plaintext_sha256: str | None
    recovered_sha256: str | None
    public_evidence: dict[str, Any]
