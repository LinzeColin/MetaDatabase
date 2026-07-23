from __future__ import annotations

import pytest
from stage5_support import recovery_context

from moomooau_archive.processed_models import ProcessingState
from moomooau_archive.remote_recovery_gate import (
    MemoryRemoteCiphertextReader,
    RemoteRecoveryError,
    RemoteRecoveryGate,
)


class FailingDecryptor:
    def decrypt(self, ciphertext: bytes) -> bytes:
        raise ValueError("synthetic wrong identity")


def test_t0501_refetches_and_decrypts_every_raw_and_complete_processed_object() -> None:
    with recovery_context() as context:
        proof = RemoteRecoveryGate(context.reader, context.decryptor).verify(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.processed_bundle,
            context.processed_plan,
        )
        expected = len(context.raw_plan.objects) + len(context.processed_plan.immutable_objects) + 1
        assert proof.processed_state is ProcessingState.COMPLETE
        assert proof.recovered_object_count == expected
        assert context.reader.fetch_calls == expected
        assert proof.raw_plaintext_sha256 == context.canonical.plaintext_sha256
        assert context.canonical.message_id not in repr(proof)


def test_t0501_explicit_safe_deferred_processed_state_is_recovered_and_m3_eligible() -> None:
    with recovery_context(safe_deferred=True) as context:
        proof = RemoteRecoveryGate(context.reader, context.decryptor).verify(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.processed_bundle,
            context.processed_plan,
        )
        assert proof.processed_state is ProcessingState.UNSUPPORTED
        assert context.statement is None


def test_t0501_missing_or_corrupt_remote_ciphertext_never_issues_a_proof() -> None:
    with recovery_context() as context:
        target = context.raw_plan.objects[0]
        context.reader.replace_for_test(target.relative_path, b"corrupt")
        with pytest.raises(RemoteRecoveryError, match="missing or differs"):
            RemoteRecoveryGate(context.reader, context.decryptor).verify(
                context.canonical,
                context.first_verification,
                context.raw_plan,
                context.processed_bundle,
                context.processed_plan,
            )

    with recovery_context() as context:
        missing_reader = MemoryRemoteCiphertextReader()
        all_objects = list(context.raw_plan.objects) + list(
            context.processed_plan.immutable_objects
        )
        if context.processed_plan.current_pointer is not None:
            all_objects.append(context.processed_plan.current_pointer)
        for item in all_objects[1:]:
            missing_reader.put(item.relative_path, item.ciphertext)
        with pytest.raises(RemoteRecoveryError, match="missing or differs"):
            RemoteRecoveryGate(missing_reader, context.decryptor).verify(
                context.canonical,
                context.first_verification,
                context.raw_plan,
                context.processed_bundle,
                context.processed_plan,
            )

    with recovery_context() as context:
        with pytest.raises(RemoteRecoveryError, match="decryption failed"):
            RemoteRecoveryGate(context.reader, FailingDecryptor()).verify(
                context.canonical,
                context.first_verification,
                context.raw_plan,
                context.processed_bundle,
                context.processed_plan,
            )
