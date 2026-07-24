"""Fail-closed, metadata-only Stage 1 synthetic verifier."""

from __future__ import annotations

from dataclasses import dataclass

from .fixtures import verified_synthetic_sender
from .models import CandidateMetadata, VerificationDecision, VerificationResult


@dataclass(frozen=True, slots=True)
class SyntheticVerifier:
    """A narrow fixture verifier; it makes no production sender claim."""

    allowed_sender: str = verified_synthetic_sender()

    def verify(self, candidate: CandidateMetadata) -> VerificationResult:
        if not candidate.synthetic_origin:
            return VerificationResult(VerificationDecision.REJECTED, None, "NON_SYNTHETIC_INPUT")
        if candidate.sender.casefold() != self.allowed_sender.casefold():
            return VerificationResult(VerificationDecision.REJECTED, None, "SENDER_NOT_ALLOWLISTED")
        if not candidate.authentication.all_pass:
            return VerificationResult(VerificationDecision.REJECTED, None, "AUTHENTICATION_FAILED")
        return VerificationResult(
            VerificationDecision.VERIFIED,
            "DAILY_STATEMENT",
            "SYNTHETIC_EXACT_MATCH",
        )
