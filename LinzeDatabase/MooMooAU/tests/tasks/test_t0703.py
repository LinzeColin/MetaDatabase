from __future__ import annotations

from datetime import UTC, datetime

import pytest
from stage5_support import SyntheticM3Transport, pre_m3_message, recovery_context
from stage7_support import (
    canary_context,
    canary_message,
    m3_canary_context,
    m3_canary_message,
    phase_observation,
)

from moomooau_archive.canary_runtime import CanaryRuntimeError
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.m3 import (
    ExactMessageTrashExecutor,
    GmailLabelConfirmationClient,
    M3Error,
    MutationBudget,
    MutationPhase,
)
from moomooau_archive.release_control import (
    FeatureFlags,
    GateStatus,
    ReleaseControlError,
    ReleasePhase,
    Stage7ReleaseGate,
)
from moomooau_archive.remote_recovery_gate import RemoteRecoveryError, RemoteRecoveryGate


def test_t0703_m3_canary_requires_budget_one_recovery_and_seven_days() -> None:
    with pytest.raises(ReleaseControlError, match="current parser"):
        FeatureFlags.for_phase(ReleasePhase.M3_CANARY)
    flags = FeatureFlags.for_phase(
        ReleasePhase.M3_CANARY,
        parser_current_version="1.0.0",
    )
    assert flags.processing_enabled and flags.m3_enabled
    assert not flags.timeline_enabled and flags.mutation_budget_per_run == 1

    alpha = phase_observation(ReleasePhase.ALPHA)
    beta = phase_observation(ReleasePhase.BETA_RAW_ONLY)
    m3_promotion = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.M3_CANARY,
        (alpha, beta),
        beta_message_budget=1,
        parser_current_version="1.0.0",
    )
    assert m3_promotion.status is GateStatus.READY
    complete = phase_observation(ReleasePhase.M3_CANARY)
    report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.BLUE_GREEN,
        (alpha, beta, complete),
        beta_message_budget=1,
        parser_current_version="1.0.0",
    )
    assert report.status is GateStatus.READY

    short = phase_observation(ReleasePhase.M3_CANARY, days=6, scheduled_runs=6)
    wrong_budget = phase_observation(ReleasePhase.M3_CANARY, mutation_budget_max=2)
    no_recovery = phase_observation(
        ReleasePhase.M3_CANARY,
        recovery_successes=6,
    )
    for observation, code in (
        (short, "M3_SEVEN_DAY_WINDOW_INCOMPLETE"),
        (wrong_budget, "M3_MUTATION_BUDGET_NOT_ONE"),
        (no_recovery, "M3_RECOVERY_NOT_ONE_HUNDRED_PERCENT"),
    ):
        blocked = Stage7ReleaseGate().evaluate_promotion(
            ReleasePhase.BLUE_GREEN,
            (alpha, beta, observation),
            beta_message_budget=1,
            parser_current_version="1.0.0",
        )
        assert blocked.status is GateStatus.BLOCKED
        assert code in blocked.reasons

    no_processed_or_safe_deferred = phase_observation(
        ReleasePhase.M3_CANARY,
        processed_messages=0,
    )
    downstream_blocked = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.BLUE_GREEN,
        (alpha, beta, no_processed_or_safe_deferred),
        beta_message_budget=1,
        parser_current_version="1.0.0",
    )
    assert "M3_NO_PROCESSED_OR_SAFE_DEFERRED_MESSAGE" in downstream_blocked.reasons


def test_t0703_mutations_cannot_exceed_verified_messages_or_per_run_budget() -> None:
    with pytest.raises(ReleaseControlError, match="per-run budget"):
        phase_observation(
            ReleasePhase.M3_CANARY,
            observed_runs=7,
            verified_messages=8,
            source_mutations=8,
            recovery_attempts=8,
            recovery_successes=8,
        )


def test_t0703_beta_raw_only_runner_cannot_reach_m3() -> None:
    message = canary_message("msg-stage7-m3-unreachable")
    with canary_context((message,)) as context:
        with pytest.raises(CanaryRuntimeError, match="configuration is invalid"):
            context.runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
                beta_message_budget=1,
            )
        assert context.transport.trashed_ids == []
        assert context.transport.inner.raw_fetches == []
        assert context.store.create_calls == 0


def test_t0703_raw_only_recovery_proof_cannot_authorize_m3() -> None:
    with recovery_context() as context:
        raw_only_proof = RemoteRecoveryGate(context.reader, context.decryptor).verify_raw_only(
            context.canonical,
            context.first_verification,
            context.raw_plan,
        )
        message, second = pre_m3_message(context)
        transport = SyntheticM3Transport(message.ref.message_id)
        guard = GmailEndpointGuard(transport)
        with pytest.raises(M3Error, match="not bound"):
            ExactMessageTrashExecutor(
                guard,
                GmailLabelConfirmationClient(guard),
            ).execute(
                message,
                context.first_verification,
                second,
                raw_only_proof,
                MutationBudget.for_phase(MutationPhase.CANARY),
            )
        assert transport.requests == []


def test_t0703_m3_runner_recovers_processed_then_mutates_exactly_one_and_retries_idempotently() -> (
    None
):
    messages = (
        m3_canary_message("msg-stage7-m3-first"),
        m3_canary_message("msg-stage7-m3-second"),
    )
    observed = datetime(2026, 7, 22, tzinfo=UTC)
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with m3_canary_context(messages) as context:
        first = context.runner.run(
            ReleasePhase.M3_CANARY,
            maximum_verified_candidates=2,
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            observed_at_utc=observed,
            predecessor_observations=predecessors,
            beta_message_budget=1,
        )
        assert first.processed_complete == first.full_recovery_successes == 2
        assert first.mutation_calls == first.confirmed_trashed == 1
        assert first.deferred_mutations == 1
        public = first.to_public_dict()
        assert public["mutation_calls_bucket"] == "ONE"
        assert "mutation_calls" not in public and "confirmed_trashed" not in public
        assert public["production_health_claimed"] is False
        assert len(context.transport.trashed_ids) == 1
        trash_index = context.events.index("trash")
        assert "recover" in context.events[:trash_index]
        raw_writes = context.raw_store.create_calls
        processed_writes = context.processed_store.write_calls

        second = context.runner.run(
            ReleasePhase.M3_CANARY,
            maximum_verified_candidates=2,
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            observed_at_utc=observed,
            predecessor_observations=predecessors,
            beta_message_budget=1,
        )
        assert second.processed_complete == second.full_recovery_successes == 2
        assert second.already_trashed == 1
        assert second.mutation_calls == second.confirmed_trashed == 1
        assert len(context.transport.trashed_ids) == 2
        assert context.raw_store.create_calls == raw_writes
        assert context.processed_store.write_calls == processed_writes
        assert first.maximum_live_timeline_assets == second.maximum_live_timeline_assets == 0


def test_t0703_m3_runner_allows_explicit_safe_deferred_but_not_corrupt_recovery() -> None:
    deferred_message = m3_canary_message(
        "msg-stage7-m3-safe-deferred",
        with_supported_attachment=False,
    )
    observed = datetime(2026, 7, 22, tzinfo=UTC)
    predecessors = (
        phase_observation(ReleasePhase.ALPHA),
        phase_observation(ReleasePhase.BETA_RAW_ONLY),
    )
    with m3_canary_context((deferred_message,)) as context:
        result = context.runner.run(
            ReleasePhase.M3_CANARY,
            maximum_verified_candidates=1,
            key_epoch="synthetic-epoch-1",
            parser_current_version="1.0.0",
            observed_at_utc=observed,
            predecessor_observations=predecessors,
            beta_message_budget=1,
        )
        assert result.processed_complete == 0
        assert result.processed_safe_deferred == result.full_recovery_successes == 1
        assert result.confirmed_trashed == 1

    with m3_canary_context((m3_canary_message("msg-stage7-m3-corrupt"),)) as context:
        context.reader.corrupt_next = True
        with pytest.raises(RemoteRecoveryError, match="missing or differs"):
            context.runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                observed_at_utc=observed,
                predecessor_observations=predecessors,
                beta_message_budget=1,
            )
        assert context.transport.trashed_ids == []


def test_t0703_m3_runner_requires_protected_beta_predecessor_before_any_network() -> None:
    with m3_canary_context((m3_canary_message("msg-stage7-m3-no-beta"),)) as context:
        with pytest.raises(CanaryRuntimeError, match="predecessor gate is blocked"):
            context.runner.run(
                ReleasePhase.M3_CANARY,
                maximum_verified_candidates=1,
                key_epoch="synthetic-epoch-1",
                parser_current_version="1.0.0",
                observed_at_utc=datetime(2026, 7, 22, tzinfo=UTC),
                predecessor_observations=(phase_observation(ReleasePhase.ALPHA),),
                beta_message_budget=1,
            )
        assert context.transport.inner.requests == []
        assert context.raw_store.create_calls == 0
        assert context.processed_store.write_calls == 0
        assert context.transport.trashed_ids == []
