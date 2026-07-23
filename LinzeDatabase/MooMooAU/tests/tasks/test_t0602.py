from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from stage5_support import SyntheticM3Transport, pre_m3_message, recovery_context, timeline_event

from moomooau_archive.adapters import EphemeralAgeSession
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.m3 import (
    ExactMessageTrashExecutor,
    GmailLabelConfirmationClient,
    M3State,
    MutationBudget,
    MutationPhase,
)
from moomooau_archive.publication_saga import (
    PrivateFirstPublicationSaga,
    PrivateState,
    PublicationSagaError,
    PublicState,
    SourceMutationState,
)
from moomooau_archive.remote_recovery_gate import RemoteRecoveryGate
from moomooau_archive.timeline_publish import (
    MemoryTimelineReleaseRemote,
    MemoryTimelineStateStore,
    SingleLatestTimelinePublisher,
    TimelinePublishAction,
)
from moomooau_archive.timeline_render import DeterministicTimelineRenderer


def test_t0602_private_failure_blocks_public_success_and_m3_before_any_attempt() -> None:
    saga = PrivateFirstPublicationSaga()
    saga.record_private(committed=False, recovery_verified=False)
    with pytest.raises(PublicationSagaError, match="private recovery"):
        saga.record_public(remote_verified=True)
    with pytest.raises(PublicationSagaError, match="private recovery"):
        saga.record_source_mutation(confirmed=True)
    snapshot = saga.snapshot
    assert snapshot.private_state is PrivateState.FAILED
    assert snapshot.public_state is PublicState.NOT_STARTED
    assert snapshot.source_mutation_state is SourceMutationState.NOT_ATTEMPTED
    assert snapshot.private_attempts == 1
    assert snapshot.public_attempts == snapshot.source_mutation_attempts == 0
    assert not snapshot.public_success_claimed
    assert not snapshot.m3_authorized


def test_t0602_public_failure_is_pending_and_compensates_without_repeating_private_or_m3() -> None:
    saga = PrivateFirstPublicationSaga()
    saga.record_private(committed=True, recovery_verified=True)
    saga.record_public(remote_verified=False)
    saga.record_source_mutation(confirmed=True)
    pending = saga.snapshot
    assert pending.public_state is PublicState.PENDING_RECONCILIATION
    assert pending.source_mutation_state is SourceMutationState.CONFIRMED
    assert not pending.public_success_claimed
    saga.reconcile_public(remote_verified=True)
    repaired = saga.snapshot
    assert repaired.public_state is PublicState.VERIFIED
    assert repaired.private_attempts == 1
    assert repaired.public_attempts == 2
    assert repaired.source_mutation_attempts == 1
    with pytest.raises(PublicationSagaError, match="reconciled"):
        saga.reconcile_public(remote_verified=True)


def test_t0602_recovery_proof_then_exact_source_message_m3_end_to_end() -> None:
    with recovery_context() as context:
        proof = RemoteRecoveryGate(context.reader, context.decryptor).verify(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.processed_bundle,
            context.processed_plan,
        )
        message, second = pre_m3_message(context)
        transport = SyntheticM3Transport(message.ref.message_id)
        guard = GmailEndpointGuard(transport)
        result = ExactMessageTrashExecutor(
            guard,
            GmailLabelConfirmationClient(guard),
        ).execute(
            message,
            context.first_verification,
            second,
            proof,
            MutationBudget.for_phase(MutationPhase.CANARY),
        )
        assert result.state is M3State.TRASHED
        assert result.mutation_calls == 1
        assert [request.method for request in transport.requests] == ["POST", "GET"]
        assert all(
            "threads" not in request.url and "delete" not in request.url
            for request in transport.requests
        )


def test_t0602_same_and_changed_timeline_snapshots_converge_to_one_encrypted_asset() -> None:
    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        remote = MemoryTimelineReleaseRemote()
        publisher = SingleLatestTimelinePublisher(
            DeterministicTimelineRenderer(),
            crypto,
            remote,
            MemoryTimelineStateStore(),
        )
        first = publisher.publish(
            (event,),
            processed_snapshot_root="b" * 64,
            key_epoch="synthetic-stage6",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        same = publisher.publish(
            (event,),
            processed_snapshot_root="b" * 64,
            key_epoch="synthetic-stage6",
            now_utc=datetime(2026, 7, 20, 1, tzinfo=UTC),
        )
        changed = publisher.publish(
            (replace(event, m3_state=M3State.ALREADY_TRASHED),),
            processed_snapshot_root="c" * 64,
            key_epoch="synthetic-stage6",
            now_utc=datetime(2026, 7, 21, tzinfo=UTC),
        )
        assert first.asset_count == same.asset_count == changed.asset_count == 1
        assert same.action is TimelinePublishAction.NO_CHANGE
        assert changed.action is TimelinePublishAction.ASSET_REPLACED
        assert remote.maximum_observed_asset_count == 1
