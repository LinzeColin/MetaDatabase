"""Minimal synthetic RAW -> verify -> age -> recover -> public evidence pipeline."""

from __future__ import annotations

import hashlib

from .evidence import build_public_evidence
from .models import ArchiveResult, CandidateMetadata, VerificationDecision
from .ports import AgeCipher, CiphertextStore, RawMessageSource
from .verification import SyntheticVerifier


class RecoveryMismatch(RuntimeError):
    pass


def archive_candidate(
    candidate: CandidateMetadata,
    *,
    source: RawMessageSource,
    verifier: SyntheticVerifier,
    cipher: AgeCipher,
    remote: CiphertextStore,
) -> ArchiveResult:
    verification = verifier.verify(candidate)
    if verification.decision is not VerificationDecision.VERIFIED:
        return ArchiveResult(
            decision=verification.decision,
            raw_fetched=False,
            remote_recovered=False,
            plaintext_sha256=None,
            recovered_sha256=None,
            public_evidence=build_public_evidence(recovery_ok=False, verified_count=0),
        )

    raw = source.get_raw(candidate.source_id)
    plaintext_sha256 = hashlib.sha256(raw).hexdigest()
    ciphertext = cipher.encrypt(raw)
    object_name = "Raw/" + candidate.source_id + ".eml.age"
    remote.put(object_name, ciphertext)
    recovered = cipher.decrypt(remote.fetch(object_name))
    recovered_sha256 = hashlib.sha256(recovered).hexdigest()
    if recovered != raw or recovered_sha256 != plaintext_sha256:
        raise RecoveryMismatch("remote recovery did not reproduce canonical Gmail RAW bytes")
    return ArchiveResult(
        decision=verification.decision,
        raw_fetched=True,
        remote_recovered=True,
        plaintext_sha256=plaintext_sha256,
        recovered_sha256=recovered_sha256,
        public_evidence=build_public_evidence(recovery_ok=True, verified_count=1),
    )
