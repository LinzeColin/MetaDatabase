from __future__ import annotations

import json
import shutil

import pytest

from moomooau_archive.adapters import (
    AgeOperationError,
    EphemeralAgeSession,
    MemoryCiphertextStore,
    TrackedSyntheticSource,
)
from moomooau_archive.contracts import validate_json_contract
from moomooau_archive.fixtures import build_fixture_set
from moomooau_archive.models import VerificationDecision
from moomooau_archive.pipeline import archive_candidate
from moomooau_archive.verification import SyntheticVerifier


def test_t0104_official_age_remote_recovery_is_byte_exact_and_ciphertext_only() -> None:
    assert shutil.which("age") is not None
    assert shutil.which("age-keygen") is not None
    fixtures = build_fixture_set()
    source = TrackedSyntheticSource((fixtures.verified, fixtures.unrelated, fixtures.spoofed))
    remote = MemoryCiphertextStore()
    verifier = SyntheticVerifier()
    with EphemeralAgeSession() as cipher:
        for rejected in (fixtures.unrelated, fixtures.spoofed):
            result = archive_candidate(
                rejected.metadata,
                source=source,
                verifier=verifier,
                cipher=cipher,
                remote=remote,
            )
            assert result.decision is VerificationDecision.REJECTED
            assert not result.raw_fetched
        result = archive_candidate(
            fixtures.verified.metadata,
            source=source,
            verifier=verifier,
            cipher=cipher,
            remote=remote,
        )

    assert source.raw_fetches == [fixtures.verified.metadata.source_id]
    assert result.plaintext_sha256 == result.recovered_sha256
    assert result.remote_recovered
    assert remote.put_calls == remote.fetch_calls == 1
    assert all(name.endswith(".age") for name in remote.object_names())
    assert all(fixtures.verified.raw not in value for value in remote.ciphertexts())
    validate_json_contract("evidence", result.public_evidence)
    assert result.public_evidence["run_status"] == "DEGRADED"
    assert result.public_evidence["gates"]["gmail_production"] == "NOT_RUN"
    public_text = json.dumps(result.public_evidence, sort_keys=True)
    assert fixtures.verified.metadata.source_id not in public_text
    assert fixtures.verified.metadata.sender not in public_text


def test_t0104_corrupted_remote_ciphertext_fails_closed() -> None:
    class CorruptingStore(MemoryCiphertextStore):
        def fetch(self, object_name: str) -> bytes:
            ciphertext = super().fetch(object_name)
            return ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])

    fixtures = build_fixture_set()
    source = TrackedSyntheticSource((fixtures.verified,))
    remote = CorruptingStore()
    with EphemeralAgeSession() as cipher, pytest.raises(AgeOperationError):
        archive_candidate(
            fixtures.verified.metadata,
            source=source,
            verifier=SyntheticVerifier(),
            cipher=cipher,
            remote=remote,
        )
    assert source.raw_fetches == [fixtures.verified.metadata.source_id]
    assert remote.put_calls == remote.fetch_calls == 1
    with pytest.raises(ValueError):
        remote.put("Raw/plaintext.age", fixtures.verified.raw)
